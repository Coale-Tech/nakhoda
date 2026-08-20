# Copyright (c) 2026, Nakhoda and contributors
# For license information, please see license.txt
"""The Data Sources surface: the configured `Nakhoda Data Source` rows, the
tables each one exposes, and a bounded preview of any one of them.

Split out of `api/data_store.py` when the page grew past a status list. That
module owns *movement* - copying a DocType's rows into the warehouse and the
log that records it; this one owns *description* - what sources exist, whether
they answer, and what is in them.

Ported from `insights/api/data_sources.py`, verified on this bench, including
the parts an earlier pass deliberately left out: creating an external source
from a connection form, probing it before saving, listing its tables, previewing
one, reading its columns, and refreshing the joins it declares.

Three places where this is not a transcription, each because the two apps store
different things:

- **Tables are not a doctype here.** Insights caches every remote table as an
  `Insights Table v3` row and ships an "Update Table Links" button because that
  registry goes stale. Nakhoda lists remotes live and memoises the answer in
  redis under a key containing the row's `modified` stamp, so re-pointing a
  source at another host cannot serve the previous host's tables, and there is
  no registry to reconcile.
- **Two kinds of source, two kinds of permission.** For the site database and
  the warehouse, a table *is* a DocType, so listing and previewing run through
  `api.query.list_sources` and `engine.permissions.for_connector` - the same
  paths a real query takes, so no second accessor can disagree about who may see
  what. An external database has no `tabDocPerm` to filter by; access to it is
  the read permission on the source row itself, and `for_connector` states that
  by handing the compiler an `UnrestrictedPolicy` rather than by skipping the
  resolver boundary - the same wrap, a policy with nothing to remove.
- **The AI agent still only sees DocTypes.** `semantic/model.py` describes
  tables from Frappe metadata - labels, links, field types - and none of that
  exists for a foreign schema. The query builder can drive an external source
  because it asks for columns explicitly; the agent is not told the source
  exists, because it could not be told anything true about its columns.
"""

from __future__ import annotations

import json
from typing import Any, cast

import frappe
from frappe.utils import cint, now_datetime

from nakhoda.api.data_store import WAREHOUSE_SOURCE_TYPE, tracked_tables
from nakhoda.api.query import list_sources
from nakhoda.engine import cache, pipeline
from nakhoda.engine.permissions import for_connector, table_name
from nakhoda.nakhoda.doctype.nakhoda_data_source.nakhoda_data_source import (
	NakhodaDataSource,
)
from nakhoda.nakhoda.doctype.nakhoda_settings.nakhoda_settings import NakhodaSettings

DOCTYPE = "Nakhoda Data Source"
EXTERNAL_SOURCE_TYPE = "External Database"

#: Rows returned by `get_source_table`. A preview is for recognising a table,
#: not for reading it - the query builder is where a real result comes from.
PREVIEW_ROWS = 100

#: How long a remote table list or link graph is trusted. Long enough that
#: browsing a source is not a sequence of network sweeps, short enough that a
#: table added upstream shows up the same working day without a button.
LISTING_TTL = 6 * 60 * 60

#: Fields the connection form may set. An allowlist, not the whole document:
#: a create endpoint that copied the payload wholesale would let a caller set
#: `is_frappe_db`, `status`, or `is_default` - three fields whose whole purpose
#: is to be decided by the backend.
CONNECTION_FIELDS = (
	"title",
	"database_type",
	"host",
	"port",
	"username",
	"password",
	"database_name",
	"use_ssl",
	"connection_string",
	"schema",
	"http_headers",
	"is_ducklake",
)


@frappe.whitelist()
def list_data_sources() -> list[dict[str, Any]]:
	"""Every configured source, with reachability and table count.

	Unfiltered by permission on purpose: `Nakhoda Data Source` carries its own
	doctype permissions (read for `Nakhoda User`, write for the two admin
	roles), and a source row is a connection, not data. What is *in* it is
	filtered per user by `list_source_tables`.
	"""
	rows = frappe.get_all(
		DOCTYPE,
		fields=[
			"name",
			"title",
			"source_type",
			"database_type",
			"status",
			"is_default",
			"is_frappe_db",
			"last_checked",
			"owner",
			"creation",
			"modified",
		],
		order_by="is_default desc, title asc",
	)
	stored = sum(1 for row in tracked_tables().values() if row.stored_in_warehouse)
	readable = len(list_sources())
	users = _owner_names(rows)
	for row in rows:
		row["owner_name"] = users.get(row.owner) or row.owner
		if row.source_type == WAREHOUSE_SOURCE_TYPE:
			row["table_count"] = stored
		elif row.source_type == EXTERNAL_SOURCE_TYPE:
			# Counting an external source's tables means a network sweep per
			# row on a page that exists to load fast. The count is the one
			# thing on this screen worth fetching only when asked for, which
			# the per-source page does.
			row["table_count"] = None
		else:
			row["table_count"] = readable
	return rows


def _owner_names(rows: list[dict[str, Any]]) -> dict[str, str]:
	"""Full names for the owners on this page, in one query.

	Insights resolves these in the browser through its user store, which is a
	request per unseen owner. There are never many distinct owners of a
	connection, so one `in` lookup here is cheaper than the round trips and
	leaves the list a single call.
	"""
	owners = {row["owner"] for row in rows if row.get("owner")}
	if not owners:
		return {}
	return {
		user["name"]: user["full_name"]
		for user in frappe.get_all(
			"User", filters={"name": ("in", list(owners))}, fields=["name", "full_name"]
		)
	}


@frappe.whitelist()
def get_data_source(name: str) -> dict[str, Any]:
	"""One source: the per-source page's header, and the edit form's own fields.

	External rows carry their connection back so re-pointing one is an edit
	rather than a re-entry - a form that opened blank would make changing a port
	mean retyping a host somebody else configured. The password is the one field
	never returned: `update_data_source` writes only what a payload carries, so
	leaving the box empty keeps the stored credential rather than clearing it.
	"""
	doc = _source(name)
	header = {
		"name": str(doc.name),
		"title": doc.title,
		"source_type": doc.source_type,
		"database_type": doc.database_type,
		"status": doc.status,
		"is_default": bool(doc.is_default),
		"is_frappe_db": bool(doc.is_frappe_db),
		"last_checked": doc.last_checked,
	}
	if doc.source_type == EXTERNAL_SOURCE_TYPE:
		header.update({field: doc.get(field) for field in CONNECTION_FIELDS if field != "password"})
	return header


@frappe.whitelist()
def test_data_source(name: str) -> dict[str, str]:
	"""Probe a saved source and record the result on the row.

	Thin wrapper over the document's own `test_connection`, which reports the
	failure rather than raising it - a source being down is a fact about the
	source, not an error in the request that asked.
	"""
	doc = _source(name, "write")
	return doc.test_connection()


@frappe.whitelist()
def test_connection(data_source: dict[str, Any] | str) -> dict[str, str]:
	"""Probe a connection that has not been saved yet.

	The New Source dialog's Test button. Insights has the same endpoint for the
	same reason: a form that can only be tested by saving it leaves a broken
	row behind on every typo, and the row is what other users then see.

	Nothing is written - not even `status` - because there is no row to write
	to. The document is built in memory purely to reuse one connect path.

	A payload may name an existing row (`name`), which is the edit form asking
	to test the connection it is showing. The stored password fills in when the
	form leaves that box empty: `get_data_source` never hands the secret to the
	browser, so without this the Connect button on an edit could only ever fail.
	"""
	frappe.has_permission(DOCTYPE, "create", throw=True)
	raw = _parsed(data_source)
	existing = str(raw.pop("name", "") or "")
	if existing and not raw.get("password"):
		raw["password"] = _source(existing, "write").get_password("password", raise_exception=False)

	doc = _unsaved_source(raw)
	try:
		doc.table_list()
	except Exception as exc:
		return {"status": "Unreachable", "message": str(exc)}
	return {"status": "Reachable", "message": frappe._("Connected.")}


@frappe.whitelist()
def create_data_source(data_source: dict[str, Any] | str) -> dict[str, Any]:
	"""Save a new external source from the connection form.

	Only external sources can be created here. The site database and the
	warehouse are made on demand by the backend the first time they are needed
	(`nakhoda.api.default_source`, `data_store._warehouse_source`), and a
	second row claiming to be either of them is refused by the document's
	`before_insert` - a duplicate would be a question the resolver cannot
	answer, not a configuration.
	"""
	frappe.has_permission(DOCTYPE, "create", throw=True)
	doc = _unsaved_source(data_source)
	doc.insert()
	return get_data_source(str(doc.name))


@frappe.whitelist()
def update_data_source(name: str, data_source: dict[str, Any] | str) -> dict[str, Any]:
	"""Re-point an existing external source.

	Editing the site row's connection is refused rather than ignored: its
	credentials come from `site_config.json`, so a form that appeared to
	accept them would be writing fields nothing reads.

	A changed title is a rename, not a column write. This DocType is
	`autoname: field:title`, so leaving the name behind would produce a row
	labelled one thing and keyed another - and every saved query points at the
	key. `Document.rename` is Frappe's own path for that (`allow_rename: 1`):
	it re-points each Link that named the old row in the same transaction.
	"""
	doc = _source(name, "write")
	if doc.source_type != EXTERNAL_SOURCE_TYPE:
		frappe.throw(
			frappe._("{0} is configured by this site, not by a form.").format(doc.source_type),
			frappe.ValidationError,
		)

	payload = _payload(data_source)
	title = str(payload.pop("title", "") or "").strip()
	for field in CONNECTION_FIELDS:
		if field in payload:
			doc.set(field, payload[field])
	doc.save()

	if title and title != doc.name:
		doc.rename(title)
	return get_data_source(str(doc.name))


@frappe.whitelist()
def delete_data_source(name: str) -> dict[str, str]:
	"""Remove an external source. Built-in rows refuse in `on_trash`."""
	doc = _source(name, "delete")
	doc.delete()
	return {"name": name}


@frappe.whitelist()
def set_default_data_source(name: str) -> dict[str, Any]:
	"""Make `name` the source new queries start from.

	The exclusivity is enforced in `NakhodaDataSource.validate`, not here, so
	a row saved through the Desk cannot end up as a second default.
	"""
	doc = _source(name, "write")
	doc.is_default = 1
	doc.save()
	return {"name": str(doc.name), "is_default": True}


@frappe.whitelist()
def list_source_tables(
	data_source: str, search_term: str | None = None, limit: int = 100
) -> list[dict[str, Any]]:
	"""The tables one source exposes to the current user.

	The source types answer differently, and the difference is the point:

	- the **site database** exposes every DocType the caller may read;
	- the **warehouse** exposes only what somebody deliberately imported - a
	  DocType copied by `api/data_store` or a file copied by `api/files` - so a
	  DuckDB table nobody asked for is absent rather than listed as un-synced;
	- an **external database** exposes whatever it has, because there is no
	  DocType to check and this app will not pretend otherwise.

	Every row carries `table`: the identifier the preview endpoints take back,
	which is a DocType name for Frappe-shaped sources and a physical table name
	for the other two. One field rather than "use `doctype`, unless it is null,
	then use `table_name`" - the list page keys rows and builds links off it.
	"""
	from nakhoda.api.files import uploaded_tables

	doc = _source(data_source)

	if doc.source_type == EXTERNAL_SOURCE_TYPE:
		return _external_tables(doc, search_term, cint(limit))

	sources = list_sources()
	needle = search_term.lower() if search_term else None
	if needle:
		sources = [s for s in sources if needle in s["label"].lower()]

	tracked = tracked_tables()
	warehouse = doc.source_type == WAREHOUSE_SOURCE_TYPE

	out = []
	for source in sources:
		row = tracked.get(source["name"])
		if warehouse and not (row and row.stored_in_warehouse):
			continue
		out.append(
			{
				"table": source["name"],
				"doctype": source["name"],
				"label": source["label"],
				"table_name": source["table"],
				"is_child": source["is_child"],
				"row_count": row.row_count if row else None,
				"last_synced": row.last_synced if row else None,
			}
		)
		if len(out) >= cint(limit):
			break

	if warehouse:
		for upload in uploaded_tables(str(doc.name)):
			if needle and needle not in (upload.label or upload.table_name).lower():
				continue
			if len(out) >= cint(limit):
				break
			out.append(
				{
					"table": upload.table_name,
					"doctype": None,
					"label": upload.label or upload.table_name,
					"table_name": upload.table_name,
					"is_child": False,
					"row_count": upload.row_count,
					"last_synced": upload.last_synced,
				}
			)
	return out


@frappe.whitelist()
def refresh_source_tables(data_source: str) -> dict[str, Any]:
	"""Forget the memoised listing for a source and re-sweep it.

	Insights' "Update Table Links" / table-refresh action, which there rebuilds
	a doctype registry. Here there is nothing to rebuild - dropping the cached
	answer is the whole operation, and the next list is live.
	"""
	doc = _source(data_source, "write")
	doc.clear_table_cache()
	tables = list_source_tables(data_source)
	return {"name": str(doc.name), "table_count": len(tables)}


@frappe.whitelist()
def get_source_table(data_source: str, table: str) -> dict[str, Any]:
	"""A bounded preview of one table.

	For the site database and a DocType in the warehouse, `table` is a DocType
	name, not a physical table: the caller never names a raw table, so there is
	nothing to escape, and the rows come back through `engine.pipeline.run` with
	the same `for_connector` resolver every query uses - a viewer's preview is
	already row- and column-filtered before it is capped.

	For an external database, `table` is a name that source itself reported
	from `list_source_tables`; it is looked up through the backend's own
	`table()` (a parameterised catalogue call, not string-built SQL) and no
	row filter is claimed, because there is none to apply.

	An uploaded file in the warehouse takes the external path for the same
	reason: a CSV has no `tabDocPerm` row describing it, so what guards it is
	read permission on the warehouse source, and pretending otherwise by
	routing it through a DocType resolver would filter it by a DocType that
	does not exist.
	"""
	doc = _source(data_source)

	if doc.source_type == EXTERNAL_SOURCE_TYPE:
		return _external_preview(doc, table)

	if _upload(doc, table):
		return _warehouse_upload_preview(doc, table)

	if not frappe.has_permission(table, "read"):
		frappe.throw(frappe._("Not permitted to read {0}").format(table), frappe.PermissionError)

	settings = cast(NakhodaSettings, frappe.get_cached_doc("Nakhoda Settings"))
	connector = doc.connector()
	resolver = for_connector(connector, str(frappe.session.user))
	result = pipeline.run(
		[{"type": "source", "table": table_name(table)}],
		resolver,
		connector,
		cap=PREVIEW_ROWS,
		ttl=cint(settings.cache_ttl) or cache.DEFAULT_TTL,
	)
	return {
		"doctype": table,
		"data_source": str(doc.name),
		"table_name": table_name(table),
		"columns": list(result.frame.columns),
		"rows": result.frame.to_dict(orient="records"),
		"row_count": len(result.frame),
		"truncated": len(result.frame) >= PREVIEW_ROWS,
		"fetched_at": now_datetime(),
	}


@frappe.whitelist()
def get_source_table_columns(data_source: str, table: str) -> list[dict[str, str]]:
	"""Column names and types for one table, for the query builder.

	A DocType answers from Frappe metadata (`semantic.model.describe`), which
	knows labels and field types the database itself does not. An external
	source and an uploaded file answer from the backend's own schema, which is
	all there is to know about either.
	"""
	doc = _source(data_source)
	upload = _upload(doc, table)

	if doc.source_type != EXTERNAL_SOURCE_TYPE and not upload:
		if not frappe.has_permission(table, "read"):
			frappe.throw(frappe._("Not permitted to read {0}").format(table), frappe.PermissionError)
		from nakhoda.semantic.model import describe

		schema = describe(table)
		return [{"column": c["column"], "label": c["label"], "type": c["type"]} for c in schema["columns"]]

	expr = doc.ibis_table(table if upload else _external_table(doc, table))
	return [
		{"column": column, "label": column, "type": str(datatype)}
		for column, datatype in expr.schema().items()
	]


@frappe.whitelist()
def get_source_table_row_count(data_source: str, table: str) -> int:
	"""How many rows one table holds, when the listing does not already know.

	Separate from the listing because it is the expensive question: a `COUNT(*)`
	on a wide remote table can take seconds, and the list of tables should not
	wait for the slowest one. A DocType and an uploaded file already carry their
	counts on `Nakhoda Table`, so they answer from that row.
	"""
	doc = _source(data_source)
	upload = _upload(doc, table)

	if upload:
		return cint(upload.row_count)

	if doc.source_type != EXTERNAL_SOURCE_TYPE:
		if not frappe.has_permission(table, "read"):
			frappe.throw(frappe._("Not permitted to read {0}").format(table), frappe.PermissionError)
		row = tracked_tables().get(table)
		return cint(row.row_count) if row else 0

	return int(doc.ibis_table(_external_table(doc, table)).count().execute())


@frappe.whitelist()
def get_table_links(data_source: str) -> list[dict[str, str]]:
	"""Joins this source declares, memoised.

	Only Frappe-shaped sources answer at all (see the document's
	`table_links`), so an ordinary Postgres returns an empty list rather than
	a guess.
	"""
	doc = _source(data_source)

	key = f"{doc.cache_key()}:links"
	stored = cache.get(key)
	if stored is not None:
		try:
			return json.loads(stored)
		except ValueError:
			pass

	links = [dict(link) for link in doc.table_links()]
	cache.put(key, json.dumps(links, default=str), ttl=LISTING_TTL)
	return links


@frappe.whitelist()
def update_table_links(data_source: str) -> dict[str, Any]:
	"""Re-read the joins a source declares.

	Insights' endpoint of the same name rebuilds `Insights Table Link v3` rows.
	Here the links are derived on read, so this drops the memo and re-derives
	- which is also why the result cannot end up describing a schema the source
	no longer has.
	"""
	doc = _source(data_source, "write")
	cache.drop(f"{doc.cache_key()}:links")
	return {"name": str(doc.name), "links": len(get_table_links(data_source))}


# -- helpers -----------------------------------------------------------------


def _source(name: str, ptype: str = "read") -> NakhodaDataSource:
	"""One source row, permission-checked before any caller touches it.

	Every endpoint above opens this way, which is the point of the helper:
	`frappe.whitelist` decides who may call a method, never which rows they may
	act on. The separation that matters here is the one in
	`nakhoda_data_source.json` - `Nakhoda User` reads, the two admin roles
	write - and it only holds if no endpoint forgets to ask.
	"""
	doc = cast(NakhodaDataSource, frappe.get_doc(DOCTYPE, name))
	doc.check_permission(ptype)
	return doc


def _parsed(data_source: dict[str, Any] | str) -> dict[str, Any]:
	"""The request's connection object, whatever encoding it arrived in.

	`frappe.whitelist` hands over whatever the request carried: a dict for a
	JSON body, a string for a form-encoded one. Parsing here rather than at
	four call sites is the difference between one shape and four.
	"""
	parsed = frappe.parse_json(data_source) if isinstance(data_source, str) else data_source
	if isinstance(parsed, dict):
		return {str(key): value for key, value in parsed.items()}
	# `frappe.throw` raises, but it is not typed `NoReturn` - see
	# `connectors/__init__.py:external` for the same shape.
	frappe.throw(frappe._("Connection details must be an object."), frappe.ValidationError)
	raise frappe.ValidationError


def _payload(data_source: dict[str, Any] | str) -> dict[str, Any]:
	"""Just the fields the connection form owns.

	The filter is the point: a create endpoint that copied the payload
	wholesale would let a caller set `is_frappe_db`, `status`, or `is_default` -
	three fields whose whole purpose is to be decided by the backend.
	"""
	parsed = _parsed(data_source)
	return {field: parsed[field] for field in CONNECTION_FIELDS if field in parsed}


def _unsaved_source(data_source: dict[str, Any] | str) -> NakhodaDataSource:
	"""A `Nakhoda Data Source` document built from a form, not yet inserted.

	`source_type` is set here, not taken from the payload: this endpoint pair
	exists for external servers, and letting a form declare itself the site
	database would put a typed credential where the app expects
	`site_config.json`.
	"""
	doc = cast(NakhodaDataSource, frappe.new_doc(DOCTYPE))
	doc.source_type = EXTERNAL_SOURCE_TYPE
	for field, value in _payload(data_source).items():
		doc.set(field, value)
	doc.run_method("validate")
	return doc


def _external_tables(doc: NakhodaDataSource, search_term: str | None, limit: int) -> list[dict[str, Any]]:
	"""One external source's tables, memoised in redis.

	The cache key carries the row's `modified` stamp (see the document's
	`cache_key`), so an edited connection is a different key rather than a
	stale hit - the failure this replaces is a table list from the host the
	source used to point at.
	"""
	stored = cache.get(doc.cache_key())
	tables: list[str] | None = None
	if stored is not None:
		try:
			tables = json.loads(stored)
		except ValueError:
			tables = None
	if tables is None:
		tables = doc.table_list()
		cache.put(doc.cache_key(), json.dumps(tables), ttl=LISTING_TTL)

	if search_term:
		needle = search_term.lower()
		tables = [t for t in tables if needle in t.lower()]

	return [
		{
			"table": table,
			"doctype": None,
			"label": table,
			"table_name": table,
			"is_child": False,
			"row_count": None,
			"last_synced": None,
		}
		for table in tables[:limit]
	]


def _upload(doc: NakhodaDataSource, table: str) -> Any | None:
	"""The `Nakhoda Table` row if `table` is an uploaded file, else `None`.

	Asked before every DocType-shaped branch in this module, because an upload
	is the one warehouse table with no DocType behind it. The lookup is by row,
	not by the `upload_` prefix alone: a prefix is a naming convention, a row is
	a fact about what was imported.
	"""
	from nakhoda.api.files import uploaded_table

	if doc.source_type != WAREHOUSE_SOURCE_TYPE:
		return None
	return uploaded_table(str(doc.name), table)


def _warehouse_upload_preview(doc: NakhodaDataSource, table: str) -> dict[str, Any]:
	"""`PREVIEW_ROWS` from an uploaded warehouse table.

	The `_external_preview` shape, against the warehouse: an uploaded file has
	no DocType, so there is no row filter to apply and none is claimed. Read
	permission on this source row is what admitted the caller.
	"""
	frame = doc.connector().execute(doc.ibis_table(table).head(PREVIEW_ROWS))
	return {
		"doctype": None,
		"data_source": str(doc.name),
		"table_name": table,
		"columns": list(frame.columns),
		"rows": frame.to_dict(orient="records"),
		"row_count": len(frame),
		"truncated": len(frame) >= PREVIEW_ROWS,
		"fetched_at": now_datetime(),
	}


def _external_table(doc: NakhodaDataSource, table: str) -> str:
	"""`table`, once the source has confirmed it has it.

	The check is not decoration. `table` reaches the backend's catalogue lookup,
	and a name the source never reported is either a typo worth a clear error or
	an attempt to reach a table the listing deliberately hid (`^_`, `^sqlite_`).
	"""
	names = {row["table_name"] for row in _external_tables(doc, None, 10_000)}
	if table not in names:
		frappe.throw(frappe._("{0} has no table named {1}.").format(doc.name, table))
	return table


def _external_preview(doc: NakhodaDataSource, table: str) -> dict[str, Any]:
	"""`PREVIEW_ROWS` from an external table.

	Not routed through `engine.pipeline.run`: that path exists to compile a
	user's pipeline against a permission-filtered resolver, and there is no
	permission to filter by here. Bypassing it is stated rather than hidden -
	`engine/permissions.py` never claims to cover foreign schemas.
	"""
	expr = doc.ibis_table(_external_table(doc, table)).head(PREVIEW_ROWS)
	frame = doc.connector().execute(expr)
	return {
		"doctype": None,
		"data_source": doc.name,
		"table_name": table,
		"columns": list(frame.columns),
		"rows": frame.to_dict(orient="records"),
		"row_count": len(frame),
		"truncated": len(frame) >= PREVIEW_ROWS,
		"fetched_at": now_datetime(),
	}
