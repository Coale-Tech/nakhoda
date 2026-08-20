# Copyright (c) 2026, Nakhoda and contributors
# For license information, please see license.txt
"""Frappe-shaped databases, ported from Insights'
`insights_data_source_v3/connectors/frappe_db.py`.

Two jobs. The site's own database, which is where every question starts and
needs no credentials from a user - and *other* Frappe sites added as external
sources, which get the same join graph as the local one because a Frappe schema
carries its relationships in `tabDocField`/`tabCustom Field` rather than in
foreign keys ibis could read.
"""

from __future__ import annotations

from typing import Any

import frappe
from ibis import _

from nakhoda.connectors.mariadb import DEFAULT_PORT as MARIADB_PORT
from nakhoda.connectors.mariadb import get_mariadb_connection
from nakhoda.connectors.postgresql import DEFAULT_PORT as POSTGRES_PORT
from nakhoda.connectors.postgresql import get_postgres_connection


class SiteCredentials(frappe._dict):
	"""The site's own connection details, shaped like a `Nakhoda Data Source`.

	The per-backend connectors take a document and call `get_password`, so the
	site connection - which comes out of `site_config.json`, not out of a row -
	needs the same shape. Insights solves this by loading its `Site DB` row and
	overwriting fields in memory; that costs a document read on a path taken
	several times per question, and breaks if the row was renamed or deleted.
	The site's own database is not user-configurable state, so it does not need
	a row to be connectable.
	"""

	def get_password(self, fieldname: str = "password", raise_exception: bool = True) -> str | None:
		return self.get(fieldname)


def get_frappedb_connection(data_source: Any) -> Any:
	"""Whichever engine this Frappe database actually runs on."""
	if data_source.database_type == "PostgreSQL":
		return get_postgres_connection(data_source)
	return get_mariadb_connection(data_source)


def get_primary_data_source() -> SiteCredentials:
	"""The current site's own database, from its own config.

	The Frappe convention this relies on: a site's database user *is* its
	database name (`bench new-site` creates them as a pair), which is why
	`username` and `database_name` read the same key.
	"""
	conf = frappe.conf
	database_type = "PostgreSQL" if conf.db_type == "postgres" else "MariaDB"
	return SiteCredentials(
		database_type=database_type,
		host=conf.db_host or "127.0.0.1",
		port=int(conf.db_port or (POSTGRES_PORT if database_type == "PostgreSQL" else MARIADB_PORT)),
		username=conf.db_name,
		password=conf.db_password,
		database_name=conf.db_name,
		use_ssl=False,
		connection_string=None,
		schema=None,
	)


def get_replica_data_source() -> SiteCredentials:
	"""The read replica, where one is configured.

	Same keys `frappe.database` itself reads, so a bench already pointing
	Frappe at a replica points analytics at it too without a second setting.
	"""
	source = get_primary_data_source()
	conf = frappe.conf

	if conf.replica_host:
		source.host = conf.replica_host
	if conf.replica_db_port:
		source.port = int(conf.replica_db_port)
	if conf.replica_db_name:
		source.database_name = conf.replica_db_name

	if conf.different_credentials_for_replica:
		source.username = conf.replica_db_user or conf.replica_db_name or conf.db_name
		source.password = conf.replica_db_password or conf.db_password

	return source


def get_sitedb_connection() -> Any:
	"""Open the site's own database, preferring a replica when one is set.

	A replica that refuses the connection falls back to the primary rather
	than failing the question: reporting off a replica is an optimisation, and
	a stale or restarting replica should slow answers down, not stop them.
	"""
	if frappe.conf.read_from_replica:
		try:
			return get_frappedb_connection(get_replica_data_source())
		except Exception:
			frappe.log_error(title="Nakhoda: replica unreachable, using primary")

	return get_frappedb_connection(get_primary_data_source())


def is_frappe_db(data_source: Any) -> bool:
	"""Whether an external database is itself a Frappe site.

	Decided by the one table every Frappe install has and almost nothing else
	does. Used to set `is_frappe_db` on the row, which is what unlocks the
	link graph below - guessing from the title would be wrong the first time
	somebody names a Postgres source "erp".
	"""
	backend = None
	try:
		backend = get_frappedb_connection(data_source)
		rows = backend.raw_sql("SELECT name FROM tabDocType LIMIT 1").fetchall()
		return len(rows) > 0
	except Exception:
		return False
	finally:
		if backend is not None:
			try:
				backend.disconnect()
			except Exception:
				pass


def get_frappedb_table_links(backend: Any) -> list[frappe._dict]:
	"""Every join a Frappe schema declares, as `left`/`right` column pairs.

	`Link` fields point child -> parent, `Table` fields point parent -> child
	rows carrying a `parent` column: two directions, one list, so the query
	builder can offer a join without the user knowing which side declared it.
	Custom fields are read from `tabCustom Field` because a site's own
	customisations are exactly the joins a report tends to need.
	"""
	docfield = backend.table("tabDocField")
	custom_field = backend.table("tabCustom Field")

	standard = (
		docfield.select(_.fieldname, _.fieldtype, _.options, _.parent)
		.filter((_.fieldtype == "Link") | (_.fieldtype == "Table"))
		.execute()
		.to_dict(orient="records")
	)
	custom = (
		custom_field.select(_.fieldname, _.fieldtype, _.options, _.dt.name("parent"))
		.filter((_.fieldtype == "Link") | (_.fieldtype == "Table"))
		.execute()
		.to_dict(orient="records")
	)

	links: list[frappe._dict] = []
	for row in standard + custom:
		link = frappe._dict(row)
		if not link.options or not link.parent:
			# A `Link` with no target is a half-finished customisation; joining
			# on it would produce a column reference to nothing.
			continue
		if link.fieldtype == "Link":
			links.append(
				frappe._dict(
					left_table=link.options,
					left_column="name",
					right_table=link.parent,
					right_column=link.fieldname,
				)
			)
		elif link.fieldtype == "Table":
			links.append(
				frappe._dict(
					left_table=link.parent,
					left_column="name",
					right_table=link.options,
					right_column="parent",
				)
			)

	return links
