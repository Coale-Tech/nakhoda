# Copyright (c) 2026, Nakhoda and contributors
# For license information, please see license.txt
"""The Data Store surface: DuckDB warehouse tables synced from the site's own
database, plus every readable DocType available to import into it.

Mirrors `nakhoda.api.query.list_sources` for discovery - the query builder's
source picker and this picker read the same permission-filtered table list,
so there is exactly one place a DocType becomes "readable in this app" - and
reuses `nakhoda.connectors.site_db` / `site_warehouse` for the actual data
movement. A synced table is queryable through the same engine path any other
table is: `Nakhoda Table.stored_in_warehouse` plus the warehouse `Nakhoda
Data Source` this module creates on first import, mirroring the get-or-create
shape `nakhoda.api.default_source` already uses for the site database.

`import_table` enqueues rather than copies inline, which is the one structural
change this module has taken from Insights (`insights_data_source_v3/
data_warehouse.py:85-126`, verified on this bench). The synchronous version it
replaces held an HTTP worker open for the length of a full table copy: a real
`Sales Invoice` import on this bench moved 3,730 rows and the wide ERPNext
doctypes are far larger, so the request either blocked a gunicorn worker for
minutes or timed out at the proxy with the copy still running and no record of
it. The durable record is now `Nakhoda Table Import Log`; the request returns
as soon as the job is queued.

The three data-source endpoints that used to live here (`list_data_sources`,
`test_data_source`, `set_default_data_source`) moved to `api/data_sources.py`
when the Data Sources page grew its own per-source table and preview screens.
`_warehouse_source()` stays because it is import machinery, not a source CRUD
surface, and both modules call it.
"""

from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import add_to_date, now_datetime
from frappe.utils.background_jobs import is_job_enqueued

from nakhoda.api.query import list_sources
from nakhoda.connectors import site_db, site_warehouse
from nakhoda.engine.permissions import table_name
from nakhoda.nakhoda.doctype.nakhoda_settings.nakhoda_settings import (
	DEFAULT_MEMORY_MB,
	DEFAULT_ROW_LIMIT,
	setting_enabled,
)

WAREHOUSE_SOURCE_TYPE = "DuckDB Warehouse"

# `DEFAULT_ROW_LIMIT` / `DEFAULT_MEMORY_MB` live on the doctype controller,
# which also writes them back on save (`NakhodaSettings.validate`), so the
# fallbacks below and the numbers the settings page shows cannot drift apart.
# Re-exported here because callers and tests already read them off this module.

#: How long an `In Progress` log may sit before `expire_stale_imports` calls
#: its worker dead. Long enough that a genuinely slow wide-table import is not
#: retired mid-flight; short enough that a killed worker does not leave a table
#: stuck on "Syncing" until someone notices.
STALE_IMPORT_HOURS = 1


def data_store_enabled() -> bool:
	"""Whether new tables may be copied into the warehouse.

	Deliberately narrow: this gates *copying*, never *reading*. Tables already
	in the warehouse stay queryable with the switch off, because a setting
	that changes the answer to a question is not a feature flag, it is a bug
	nobody can reproduce.

	`setting_enabled` (not a bare read) because a Check that was never written
	reads back as `0`, so a site that has saved settings once - before this
	field existed - would otherwise find its Data Store silently switched off
	by an upgrade.
	"""
	return setting_enabled("enable_data_store")


@frappe.whitelist()
def list_tables(search_term: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
	"""Every readable DocType, joined against its `Nakhoda Table` sync state.

	A DocType the current user can read but has never imported still appears,
	with `sync_state: "Never"` - this is a picker over everything importable,
	not only what has already landed in the warehouse (matches Insights'
	`DataStoreList`, whose unimported rows carry the same empty state).
	"""
	sources = list_sources()
	if search_term:
		needle = search_term.lower()
		sources = [s for s in sources if needle in s["label"].lower()]
	sources = sources[: int(limit)]

	tracked = tracked_tables()

	out = []
	for source in sources:
		row = tracked.get(source["name"])
		out.append(
			{
				"doctype": source["name"],
				"label": source["label"],
				"table_name": source["table"],
				"is_child": source["is_child"],
				"nakhoda_table": row["name"] if row else None,
				"sync_state": row["sync_state"] if row else "Never",
				"row_count": row["row_count"] if row else None,
				"row_limit": row["row_limit"] if row else None,
				"last_synced": row["last_synced"] if row else None,
				"sync_error": row["sync_error"] if row else None,
				"stored_in_warehouse": bool(row["stored_in_warehouse"]) if row else False,
			}
		)
	return out


def tracked_tables() -> dict[str, Any]:
	"""`Nakhoda Table` rows keyed by DocType.

	Shared with `api/data_sources.py:list_source_tables`, which shows the same
	sync state scoped to one data source - two pickers over one join, not two
	joins that can disagree about what "Synced" means.
	"""
	return {
		row.document_type: row
		for row in frappe.get_all(
			"Nakhoda Table",
			fields=[
				"name",
				"document_type",
				"table_name",
				"sync_state",
				"row_count",
				"row_limit",
				"last_synced",
				"sync_error",
				"stored_in_warehouse",
			],
		)
		if row.document_type
	}


@frappe.whitelist()
def import_table(doctype: str, row_limit: int | None = None) -> dict[str, Any]:
	"""Queue a copy of `doctype`'s rows into the site's DuckDB warehouse.

	Requires create on `Nakhoda Table` - System Manager or Nakhoda Admin only,
	the same split Insights draws with `session.user.is_admin` gating its
	Import button; `Nakhoda User` can browse the Data Store but not populate
	it. Also requires read on `doctype` itself: importing is not a permission
	escalation, it is a materialisation of rows the caller could already see
	one at a time through the query builder.

	Refuses outright when `Nakhoda Settings.enable_data_store` is off, and says
	which setting refused. An admin who turned the store off and forgot has a
	one-line answer instead of an afternoon; the alternative - accepting the
	call and quietly doing nothing - is the failure mode this whole module's
	logging exists to prevent.

	Returns `{"queued": False, "reason": "in_progress"}` rather than raising
	when a copy of the same table is already running. Two concurrent writers
	of one DuckDB table is a corrupted table, and the button that produced the
	second click is not a caller that wants an exception - it wants to be told
	the work is already happening.
	"""
	if not data_store_enabled():
		frappe.throw(
			frappe._("The Data Store is turned off in Nakhoda Settings, so no table can be imported."),
			title=frappe._("Data Store Disabled"),
		)

	frappe.has_permission("Nakhoda Table", "create", throw=True)
	frappe.has_permission(doctype, "read", throw=True)

	doc = _tracking_row(doctype)
	if row_limit is not None:
		doc.db_set("row_limit", int(row_limit), update_modified=False)

	job_id = _job_id(doctype)
	if is_job_enqueued(job_id) or _open_log(doctype):
		return {"queued": False, "table": doc.name, "log": None, "reason": "in_progress"}

	return {"queued": True, "table": doc.name, "log": _queue_import(doc, job_id)}


def _queue_import(doc, job_id: str) -> str:
	"""Open a log, flip the row to Syncing, enqueue the copy. Returns the log.

	Both callers - the button and the daily refresh - need exactly this
	sequence in exactly this order: the log and the `Syncing` state must be
	committed *before* the job is queued, or a fast worker can load the row
	and find it still marked from the previous run.
	"""
	effective_rows = _row_limit(doc)
	effective_memory = _memory_limit()
	log = frappe.get_doc(
		{
			"doctype": "Nakhoda Table Import Log",
			"data_source": doc.data_source,
			"document_type": doc.document_type,
			"table_name": doc.table_name,
			"status": "In Progress",
			"started_at": now_datetime(),
			"row_limit": effective_rows,
			"memory_limit": effective_memory,
		}
	).insert(ignore_permissions=True)

	doc.db_set({"sync_state": "Syncing", "sync_error": ""}, update_modified=False)
	frappe.db.commit()

	frappe.enqueue(
		"nakhoda.api.data_store.run_import",
		queue="long",
		job_id=job_id,
		# A wide ERPNext doctype can take minutes; the default 300s would kill
		# the job partway and leave the log for `expire_stale_imports`.
		timeout=3600,
		table=doc.name,
		log=log.name,
		row_limit=effective_rows,
		memory_limit=effective_memory,
	)
	return log.name


def run_import(table: str, log: str, row_limit: int, memory_limit: int) -> None:
	"""The enqueued half of `import_table`. Never raises to the worker.

	Every failure is recorded on the log and the tracking row instead, for the
	same reason `NakhodaDataSource.test_connection` reports rather than raises:
	an import that fails halfway is a fact about one table, and a worker
	traceback is not something the Data Store page can render.
	"""
	doc = frappe.get_doc("Nakhoda Table", table)
	entry = frappe.get_doc("Nakhoda Table Import Log", log)
	tab = doc.table_name

	try:
		source_expr = site_db().backend.table(tab).limit(row_limit)
		entry.log_output(f"Reading {tab} (limit {row_limit:,})", commit=True)
		frame = source_expr.execute()

		warehouse = site_warehouse(read_only=False)
		# DuckDB's memory ceiling is a session PRAGMA, not a connect argument,
		# so it has to be issued on this connection before the write - and
		# re-issued every import, because `site_warehouse` hands back a fresh
		# connection each call.
		warehouse.backend.raw_sql(f"SET memory_limit='{int(memory_limit)}MB'")
		# DuckDB infers a fresh table's column types from the pandas frame by
		# default, and refuses to create a column whose every fetched value is
		# NULL (`ibis.exc.IbisTypeError: ... NULL typed columns`) - common on
		# wide ERPNext doctypes with many unset optional fields within the
		# capped row window. Passing the *source* ibis schema (typed from
		# MySQL's own DDL, never NULL) sidesteps the inference entirely.
		warehouse.backend.create_table(tab, obj=frame, schema=source_expr.schema(), overwrite=True)
	except Exception as exc:
		doc.db_set(
			{"sync_state": "Failed", "sync_error": str(exc)[:140]},
			update_modified=False,
		)
		frappe.db.commit()
		entry.finish("Failed", message=f"Error: {exc}")
		frappe.log_error(title="Nakhoda Data Store import failed", message=f"{tab}: {exc}")
		return

	doc.db_set(
		{
			"sync_state": "Synced",
			"stored_in_warehouse": 1,
			"row_count": len(frame),
			"last_synced": now_datetime(),
			"sync_error": "",
		},
		update_modified=False,
	)
	frappe.db.commit()
	entry.finish("Completed", row_count=len(frame), message=f"Imported {len(frame):,} rows")


def sync_stored_tables() -> None:
	"""Daily scheduler entry: refresh every table already in the warehouse.

	Only tables an admin explicitly imported are re-synced. Nothing is ever
	pulled into the warehouse on a schedule that a person did not first ask
	for - the Data Store is opt-in per table, and a cron that widened it would
	be importing data nobody asked to materialise.

	Turning the store off stops this too. A switch that blocked the button but
	left a nightly job writing to the same warehouse would be a switch that
	does not mean what it says.
	"""
	if not data_store_enabled():
		return

	for row in frappe.get_all(
		"Nakhoda Table",
		filters={"stored_in_warehouse": 1},
		fields=["name", "document_type"],
	):
		if not row.document_type:
			continue
		job_id = _job_id(row.document_type)
		if is_job_enqueued(job_id) or _open_log(row.document_type):
			continue
		_queue_import(frappe.get_doc("Nakhoda Table", row.name), job_id)


def expire_stale_imports() -> None:
	"""Hourly scheduler entry: retire logs whose worker never came back.

	Without this a killed worker leaves its `Nakhoda Table` on "Syncing"
	forever, and `import_table`'s own duplicate guard then refuses every
	retry - the table becomes permanently unimportable through the UI. Both
	the log and the tracking row are moved to Failed together, because the
	page reads the row and the audit trail reads the log.
	"""
	cutoff = add_to_date(now_datetime(), hours=-STALE_IMPORT_HOURS)
	stale = frappe.get_all(
		"Nakhoda Table Import Log",
		filters={"status": "In Progress", "started_at": ["<", cutoff]},
		fields=["name", "document_type"],
	)
	for row in stale:
		entry = frappe.get_doc("Nakhoda Table Import Log", row.name)
		entry.finish("Failed", message=f"No result after {STALE_IMPORT_HOURS}h - worker presumed dead")
		table = frappe.db.get_value("Nakhoda Table", {"document_type": row.document_type}, "name")
		if table:
			frappe.get_doc("Nakhoda Table", table).db_set(
				{"sync_state": "Failed", "sync_error": "Import did not finish"},
				update_modified=False,
			)
	if stale:
		frappe.db.commit()  # nosemgrep - scheduler job owns its transaction


def _tracking_row(doctype: str):
	"""Get-or-create the `Nakhoda Table` row for `doctype`, saved and committed
	so the enqueued job can load it from its own connection."""
	existing = frappe.db.get_value("Nakhoda Table", {"document_type": doctype}, "name")
	doc = frappe.get_doc("Nakhoda Table", existing) if existing else frappe.new_doc("Nakhoda Table")
	doc.data_source = _warehouse_source()
	doc.document_type = doctype
	doc.table_name = table_name(doctype)
	doc.save(ignore_permissions=True)
	frappe.db.commit()
	return doc


def _job_id(doctype: str) -> str:
	"""One id per table, so RQ itself rejects the second concurrent import."""
	return f"nakhoda-import::{doctype}"


def _open_log(doctype: str) -> str | None:
	"""An `In Progress` log for `doctype`, if one exists.

	Checked alongside `is_job_enqueued` rather than instead of it: the RQ
	registry forgets a job the moment its worker starts, so mid-import the
	queue looks empty and only the log still says the table is busy.
	"""
	name = frappe.db.get_value(
		"Nakhoda Table Import Log",
		{"document_type": doctype, "status": "In Progress"},
		"name",
	)
	return str(name) if name else None


def _row_limit(doc) -> int:
	"""Per-table override, else the site-wide cap, else the shipped default."""
	return (
		int(doc.row_limit or 0)
		or int(frappe.get_cached_doc("Nakhoda Settings").max_records_to_sync or 0)
		or DEFAULT_ROW_LIMIT
	)


def _memory_limit() -> int:
	return int(frappe.get_cached_doc("Nakhoda Settings").max_memory_usage or 0) or DEFAULT_MEMORY_MB


def _warehouse_source() -> str:
	"""The `Nakhoda Data Source` row identifying the warehouse, created on
	first import - same get-or-create shape as `nakhoda.api.default_source`."""
	existing = frappe.db.get_value("Nakhoda Data Source", {"source_type": WAREHOUSE_SOURCE_TYPE}, "name")
	if existing:
		return existing
	doc = frappe.get_doc(
		{
			"doctype": "Nakhoda Data Source",
			"title": "DuckDB Warehouse",
			"source_type": WAREHOUSE_SOURCE_TYPE,
		}
	).insert(ignore_permissions=True)
	return doc.name
