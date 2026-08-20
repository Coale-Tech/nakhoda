# Copyright (c) 2026, Nakhoda and contributors
# For license information, please see license.txt
"""Where a query's tables come from.

The site's own database is the default and needs no configuration, which is the
whole reason this app can be useful the minute it is installed: the data is
already there, described by metadata Frappe already maintains.

External servers, ported from Insights' `Insights Data Source v3`, are the other
half. They are a different kind of object even though they share this table: the
site database is a fact about the deployment, while an external source is a
credential somebody typed, pointing at rows this app cannot describe, permission
-filter, or vouch for. Three consequences run through the code below:

- `source_type` is what the app branches on, not `database_type`. A row is the
  site, the warehouse, or somewhere else; only the last needs a driver.
- Reachability is *recorded* (`status`, `last_checked`), never assumed. A remote
  host that was up when the row was saved is not up when a question is asked.
- Deleting the site row is refused. It is not user-created state; a deployment
  without it cannot answer anything, and re-creating it by hand invites a
  second one.
"""

from __future__ import annotations

import re

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime

from nakhoda.connectors import (
	BACKENDS,
	Connector,
	external,
	get_frappedb_table_links,
	is_frappe_db,
	site_db,
	site_warehouse,
)
from nakhoda.engine import cache

SITE_DATABASE = "Site Database"
WAREHOUSE = "DuckDB Warehouse"
EXTERNAL = "External Database"

#: Tables no listing should offer. `_`-prefixed names are Frappe's internal
#: bookkeeping (`__Auth`, `_deleted_document`); `sqlite_` names are SQLite's
#: own catalogue. Insights blacklists exactly these two shapes.
HIDDEN_TABLE_PATTERNS = ("^_", "^sqlite_")

#: Which fields, per engine, decide whether two saves point at the same data.
#: A change to any of them invalidates a cached table list and re-probes.
CREDENTIAL_FIELDS = {
	"DuckDB": ("database_name", "http_headers", "is_ducklake"),
	"SQLite": ("database_name",),
}
REMOTE_CREDENTIAL_FIELDS = (
	"host",
	"port",
	"username",
	"password",
	"database_name",
	"schema",
	"use_ssl",
	"connection_string",
)


class NakhodaDataSource(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		connection_string: DF.Text | None
		database_name: DF.Data | None
		database_type: DF.Literal["MariaDB", "PostgreSQL", "ClickHouse", "DuckDB", "SQLite"]
		host: DF.Data | None
		http_headers: DF.JSON | None
		is_ducklake: DF.Check
		is_default: DF.Check
		is_frappe_db: DF.Check
		last_checked: DF.Datetime | None
		password: DF.Password | None
		port: DF.Int
		schema: DF.Data | None
		source_type: DF.Literal["Site Database", "DuckDB Warehouse", "External Database"]
		status: DF.Literal["Untested", "Reachable", "Unreachable"]
		title: DF.Data
		use_ssl: DF.Check
		username: DF.Data | None
	# end: auto-generated types

	@property
	def is_external(self) -> bool:
		return self.source_type == EXTERNAL

	def validate(self) -> None:
		if self.is_default:
			existing = frappe.get_all(
				self.doctype,
				filters={"is_default": 1, "name": ["!=", self.name]},
				pluck="name",
			)
			for other in existing:
				frappe.db.set_value(self.doctype, other, "is_default", 0)

		if not self.is_external:
			# Built-in rows carry no credentials. Clearing rather than ignoring
			# them means switching a row back from External cannot leave a
			# password behind for a later reader to try.
			self.set("database_type", None)
			for field in REMOTE_CREDENTIAL_FIELDS:
				self.set(field, None)
			self.set("is_frappe_db", 0)
			return

		if self.database_type not in BACKENDS:
			frappe.throw(
				frappe._("{0} is not a database type this deployment can open.").format(
					self.database_type or frappe._("No type")
				)
			)

		if self.database_type in CREDENTIAL_FIELDS:
			if not self.database_name:
				frappe.throw(
					frappe._("Database Name is required for a {0} source.").format(self.database_type)
				)
			return

		if self.connection_string:
			# A URI carries host, credentials and database in one field; asking
			# for them twice would let the two disagree.
			return

		missing = [f for f in ("host", "username", "password", "database_name") if not self.get(f)]
		if missing:
			labels = ", ".join(self.meta.get_label(f) for f in missing)
			frappe.throw(frappe._("{0} required for a {1} source.").format(labels, self.database_type))

	def before_insert(self) -> None:
		"""One site row, one warehouse row. More than one of either is not a
		configuration, it is a question the resolver cannot answer: two rows
		claiming the same data with different `is_default` flags."""
		if self.is_external:
			return
		if frappe.db.exists(self.doctype, {"source_type": self.source_type, "name": ["!=", self.name]}):
			frappe.throw(frappe._("A {0} source already exists.").format(self.source_type))

	def on_update(self) -> None:
		"""Probe on save, but only when the connection actually changed.

		Insights probes every save of an external row (`on_update` ->
		`test_connection`). Same behaviour here, gated on the credential
		fields: renaming a source or ticking `is_default` should not open a
		socket to a remote host, and a failed probe must not make an unrelated
		edit look like it failed.
		"""
		if not self.is_external or not self.credentials_changed():
			return

		if self.database_type in ("MariaDB", "PostgreSQL"):
			# Whether the far side is a Frappe site decides whether its joins
			# are discoverable. Probed, never inferred from the title.
			self.db_set("is_frappe_db", int(is_frappe_db(self)), update_modified=False)

		self.test_connection()
		self.clear_table_cache()

	def on_trash(self) -> None:
		if not self.is_external:
			frappe.throw(
				frappe._("{0} cannot be deleted - it is how this app reaches the site's own data.").format(
					self.name
				)
			)
		self.clear_table_cache()

	def credentials_changed(self) -> bool:
		"""Whether this save points the row at different data than before."""
		before = self.get_doc_before_save()
		if not before:
			return True
		if before.source_type != self.source_type or before.database_type != self.database_type:
			return True
		fields = CREDENTIAL_FIELDS.get(self.database_type, REMOTE_CREDENTIAL_FIELDS)
		return any(self.get(f) != before.get(f) for f in fields)

	# -- connections ---------------------------------------------------------

	def connector(self) -> Connector:
		"""The engine's handle on this source's data.

		Cached per request for external rows the same way `site_db` is: one
		question touches several tables, and a remote handshake is the most
		expensive thing in the path.
		"""
		if self.source_type == WAREHOUSE:
			return site_warehouse()
		if not self.is_external:
			return site_db()

		cache = getattr(frappe.local, "nakhoda_external_db", None)
		if cache is None:
			cache = {}
			frappe.local.nakhoda_external_db = cache
		cached = cache.get(self.name)
		if cached is not None:
			return cached
		connector = external(self)
		cache[self.name] = connector
		return connector

	def table_list(self) -> list[str]:
		"""Every table this source exposes, without the internal ones.

		The site database answers from Frappe's own cached table list rather
		than a remote sweep - `api/query.py:list_sources` is the permission
		-filtered version of the same question and is what the UI actually
		calls; this path exists so `test_connection` has one thing to try for
		every source type.
		"""
		backend = self.connector().backend

		if self.database_type == "PostgreSQL" and not self.connection_string:
			# Postgres hides tables behind schemas, and `list_tables` without
			# one returns only the search path - which on a fresh role is
			# empty, making a healthy database look empty.
			tables: list[str] = []
			for schema in (self.schema or "public").split(","):
				schema = schema.strip()
				if not schema:
					continue
				tables.extend(
					f"{schema}.{t}" for t in backend.list_tables(database=(self.database_name, schema))
				)
		else:
			tables = list(backend.list_tables())

		return [t for t in tables if not any(re.match(p, t) for p in HIDDEN_TABLE_PATTERNS)]

	def ibis_table(self, table_name: str):
		"""One table, by the name `table_list` returned."""
		backend = self.connector().backend
		if self.database_type == "PostgreSQL" and "." in table_name:
			schema, table = table_name.split(".", 1)
			return backend.table(table, database=schema)
		return backend.table(table_name)

	def table_links(self) -> list[frappe._dict]:
		"""Joins this source declares, or nothing.

		Only Frappe-shaped databases answer: their relationships live in
		`tabDocField`, which is readable. A foreign schema's foreign keys are
		not something this app pretends to infer - offering a guessed join is
		worse than offering none, because a wrong join silently changes counts.
		The warehouse answers nothing either: it holds copies of tables whose
		relationships are already described by the site they came from.
		"""
		if self.source_type == WAREHOUSE:
			return []
		if self.is_external and not self.is_frappe_db:
			return []
		return get_frappedb_table_links(self.connector().backend)

	# -- state ---------------------------------------------------------------

	@frappe.whitelist()
	def test_connection(self) -> dict[str, str]:
		"""Reachability, recorded. Reports the failure rather than raising it."""
		try:
			self.table_list()
			status = "Reachable"
			message = frappe._("Connected.")
		except Exception as exc:
			status = "Unreachable"
			message = str(exc)
		self.db_set({"status": status, "last_checked": now_datetime()}, update_modified=False)
		return {"status": status, "message": message}

	def cache_key(self) -> str:
		"""Keyed on `modified` so re-pointing a source cannot serve the old
		server's table list."""
		return f"nakhoda:tables:{self.name}:{self.modified}"

	def clear_table_cache(self) -> None:
		cache.drop(self.cache_key())
