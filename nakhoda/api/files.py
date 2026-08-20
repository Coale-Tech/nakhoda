# Copyright (c) 2026, Nakhoda and contributors
# For license information, please see license.txt
"""Uploaded files as warehouse tables.

Ported from Insights' `insights/api/files.py` (verified on this bench), which
answers the "Upload CSV" entry in its New Source dialog: a file becomes a
DuckDB table you can query like any other.

Three deliberate differences, each one a consequence of this app having one
warehouse instead of Insights' per-purpose DuckDB files:

1. **The upload lands in the site warehouse, not a second database.** Insights
   creates an `uploads` data source pointing at `insights_file_uploads.duckdb`
   the first time anyone uploads. That is a second warehouse with a second
   sync story, a second row cap and a second thing to back up. Here the file is
   written into the same `site_warehouse` DuckDB that `api/data_store` imports
   DocTypes into, and tracked by the same `Nakhoda Table` row - so an uploaded
   table appears on the Data Store page, carries a row count and a
   `last_synced` stamp, and is queryable from the same `DuckDB Warehouse`
   source as everything else.

2. **Names are namespaced, because one database means one namespace.** A
   DocType import is stored under its physical table name (`tabSales Invoice`);
   an upload is stored as `upload_<scrubbed file name>`. Without the prefix a
   file called `tabItem.csv` would scrub to `tabitem`, and DuckDB identifiers
   are case-insensitive, so it would silently overwrite the warehouse copy of
   `Item`. Insights cannot hit this because its uploads live in their own file.
   Re-uploading the same name replaces the table, which is Insights' behaviour
   (`overwrite=True`) and the only one that does not accumulate `_1`, `_2`.

3. **The store switch and the row cap apply.** Copying a file into the
   warehouse is copying data into the warehouse: it is refused when
   `Nakhoda Settings.enable_data_store` is off, capped by
   `max_records_to_sync`, and it writes a `Nakhoda Table Import Log`, exactly
   as `data_store.import_table` does. Insights' upload path is ungated.

`get_upload_preview` is a read, so it needs no admin role and no store switch -
it parses the file in a throwaway in-memory DuckDB and writes nothing. What it
*does* need is read permission on the `File` row itself: `frappe.get_doc` alone
would let any authenticated caller preview any CSV attached to any document on
the site by passing its name.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

import frappe
from frappe.utils import cint, now_datetime

from nakhoda.api.data_sources import PREVIEW_ROWS
from nakhoda.api.data_store import (
	_memory_limit,
	_row_limit,
	_warehouse_source,
	data_store_enabled,
)
from nakhoda.connectors import site_warehouse

if TYPE_CHECKING:
	import ibis.expr.types as ir
	import pandas as pd
	from frappe.core.doctype.file.file import File

	from nakhoda.nakhoda.doctype.nakhoda_table.nakhoda_table import NakhodaTable
	from nakhoda.nakhoda.doctype.nakhoda_table_import_log.nakhoda_table_import_log import (
		NakhodaTableImportLog,
	)

#: What a file may be. Both are read by DuckDB itself (`excel` is a core
#: extension), so there is no second parser to disagree with the one that
#: writes the table.
EXTENSIONS = ("csv", "xlsx")

#: Uploaded tables are stored under this prefix - see the module docstring for
#: why. `tab` is Frappe's reserved prefix; this is ours, and the two cannot
#: collide however a file is named.
UPLOAD_PREFIX = "upload_"


@frappe.whitelist()
def get_upload_preview(file: str) -> dict[str, Any]:
	"""Columns and the first rows of an uploaded file, before importing it.

	`file` is a `File` document name - what `FileUploader` hands back once the
	bytes are on disk. Nothing is written to the warehouse here: the file is
	parsed in an in-memory DuckDB discarded with the request, so a caller may
	look at a file they are not allowed to import.
	"""
	doc, extension = _file(file)
	table = _read(str(doc.get_full_path()), extension)

	frame = cast("pd.DataFrame", table.head(PREVIEW_ROWS).execute())
	return {
		"file": str(doc.name),
		"file_name": doc.file_name,
		"table": upload_table_name(doc.file_name),
		"label": _label(doc.file_name),
		"extension": extension,
		"columns": [
			{"column": column, "label": column, "type": str(datatype)}
			for column, datatype in table.schema().items()
		],
		"rows": frame.to_dict(orient="records"),
		"row_count": cint(cast("Any", table.count().execute())),
		"preview_rows": len(frame),
		"truncated": len(frame) >= PREVIEW_ROWS,
	}


@frappe.whitelist()
def import_upload(file: str, row_limit: int | None = None) -> dict[str, Any]:
	"""Write an uploaded file into the site warehouse as a table.

	Synchronous, unlike `data_store.import_table`: the rows are already on this
	disk and already capped, so there is no minutes-long remote read for a
	worker to own - and an upload somebody is watching should be either a table
	or an error by the time the dialog closes.

	The `Nakhoda Table` row it creates has no `document_type`, which is what
	marks it as an upload throughout the app: `data_store.tracked_tables`
	ignores it (the DocType picker is not offering to re-import a CSV),
	`sync_stored_tables` skips it (there is no DocType to re-read), and
	`api/data_sources` lists and previews it through the warehouse backend
	rather than through the DocType-shaped path.
	"""
	if not data_store_enabled():
		frappe.throw(
			frappe._("The Data Store is turned off in Nakhoda Settings, so no file can be imported."),
			title=frappe._("Data Store Disabled"),
		)

	frappe.has_permission("Nakhoda Table", "create", throw=True)

	doc, extension = _file(file)
	table = upload_table_name(doc.file_name)
	row = _tracking_row(table, _label(doc.file_name), row_limit)
	cap = _row_limit(row)
	log = _open_log(row, table, cap)

	frame = _materialise(str(doc.get_full_path()), extension, table, cap, row, log)

	row.db_set(
		{
			"sync_state": "Synced",
			"stored_in_warehouse": 1,
			"row_count": len(frame),
			"last_synced": now_datetime(),
			"sync_error": "",
		},
		update_modified=False,
	)
	log.finish("Completed", row_count=len(frame), message=f"Imported {len(frame):,} rows")

	return {
		"data_source": str(row.data_source),
		"table": table,
		"label": str(row.label),
		"row_count": len(frame),
		"truncated": len(frame) >= cap,
		"log": str(log.name),
	}


def uploaded_tables(data_source: str) -> list[Any]:
	"""Every uploaded table in one source, newest first.

	`document_type` empty is the marker, not a flag field: a `Nakhoda Table`
	row either names the DocType it copies or it is an upload, and a second
	column saying the same thing could contradict the first.
	"""
	return frappe.get_all(
		"Nakhoda Table",
		filters={
			"data_source": data_source,
			"stored_in_warehouse": 1,
			"document_type": ["in", ["", None]],
		},
		fields=["name", "table_name", "label", "row_count", "last_synced"],
		order_by="last_synced desc",
	)


def uploaded_table(data_source: str, table: str) -> Any | None:
	"""The `Nakhoda Table` row for one uploaded table, or `None`.

	How `api/data_sources` decides which branch a warehouse table takes: a name
	with a row here is a file somebody uploaded, anything else is a DocType.
	"""
	if not table.startswith(UPLOAD_PREFIX):
		return None
	rows = frappe.get_all(
		"Nakhoda Table",
		filters={
			"data_source": data_source,
			"table_name": table,
			"document_type": ["in", ["", None]],
		},
		fields=["name", "table_name", "label", "row_count", "last_synced"],
		limit=1,
	)
	return rows[0] if rows else None


def upload_table_name(file_name: str | None) -> str:
	"""The warehouse table a file lands in.

	Derived, never taken from the caller: the name reaches DuckDB's DDL, and
	`frappe.scrub` plus a fixed prefix is the difference between a table name
	and an injection point. Two files that scrub alike are the same table, on
	purpose - see the module docstring.
	"""
	stem = (file_name or "").rsplit(".", 1)[0]
	scrubbed = frappe.scrub(stem).strip("_")
	if not scrubbed:
		frappe.throw(frappe._("{0} has no usable table name.").format(file_name or "The file"))
	return f"{UPLOAD_PREFIX}{scrubbed}"


# -- helpers -----------------------------------------------------------------


def _file(name: str) -> tuple[File, str]:
	"""The `File` row, permission-checked, with its extension.

	`check_permission` rather than a bare `get_doc`: File's own
	`has_permission` follows `attached_to_doctype` to the document the file
	hangs off, which is the check a preview endpoint would otherwise skip.
	"""
	doc = cast("File", frappe.get_doc("File", name))
	doc.check_permission("read")

	parts = doc.get_extension()
	extension = (parts[-1] if parts else "").lstrip(".").lower()
	if extension not in EXTENSIONS:
		frappe.throw(
			frappe._("Only {0} files can be imported. {1} is a {2} file.").format(
				" and ".join(e.upper() for e in EXTENSIONS),
				doc.file_name,
				extension.upper() or frappe._("unknown"),
			)
		)
	return doc, extension


def _read(path: str, extension: str) -> ir.Table:
	"""An ibis table over a file on this disk, in a throwaway DuckDB.

	In-memory rather than the warehouse connection: reading through the
	warehouse would register a view inside it, so a failed parse or an
	abandoned preview would leave a view pointing at a file that may be gone.
	"""
	import ibis

	connection = ibis.duckdb.connect()
	if extension == "xlsx":
		return connection.read_xlsx(path)
	return connection.read_csv(path)


def _materialise(
	path: str,
	extension: str,
	table: str,
	cap: int,
	row: NakhodaTable,
	log: NakhodaTableImportLog,
):
	"""Read the file and write the warehouse table. Returns the frame written.

	Every failure lands on the log and the tracking row before it reaches the
	caller, for the same reason `data_store.run_import` records rather than
	raises: the Data Store page reads the row, and a driver traceback is not
	something it can render.
	"""
	try:
		source = _read(path, extension).limit(cap)
		log.log_output(f"Reading {table} (limit {cap:,})", commit=True)
		frame = source.execute()

		warehouse = site_warehouse(read_only=False)
		# A session PRAGMA, not a connect argument, and `site_warehouse` hands
		# back a fresh connection each call - the same reason
		# `data_store.run_import` re-issues it on every import.
		warehouse.backend.raw_sql(f"SET memory_limit='{_memory_limit()}MB'")
		warehouse.backend.create_table(table, obj=frame, schema=source.schema(), overwrite=True)
	except Exception as exc:
		row.db_set({"sync_state": "Failed", "sync_error": str(exc)[:140]}, update_modified=False)
		log.finish("Failed", message=f"Error: {exc}")
		frappe.log_error(title="Nakhoda upload import failed", message=f"{table}: {exc}")
		frappe.throw(
			frappe._("Could not import {0}: {1}").format(table, str(exc)[:140]),
			title=frappe._("Import Failed"),
		)
		# `frappe.throw` raises, but it is not typed `NoReturn`, so the caller
		# would otherwise see a possibly-unbound frame.
		raise
	return frame


def _open_log(row: NakhodaTable, table: str, cap: int) -> NakhodaTableImportLog:
	"""The audit row for one upload, opened before the write.

	Same shape as `data_store._queue_import` writes, minus the queue: an upload
	that fails halfway must leave the same trail a failed DocType import does,
	or the Data Store page's history has a gap exactly where it matters.
	"""
	return cast(
		"NakhodaTableImportLog",
		frappe.get_doc(
			{
				"doctype": "Nakhoda Table Import Log",
				"data_source": row.data_source,
				"table_name": table,
				"status": "In Progress",
				"started_at": now_datetime(),
				"row_limit": cap,
				"memory_limit": _memory_limit(),
			}
		).insert(ignore_permissions=True),
	)


def _tracking_row(table: str, label: str, row_limit: int | None) -> NakhodaTable:
	"""Get-or-create the `Nakhoda Table` row for an uploaded table.

	Same get-or-create shape as `data_store._tracking_row`, keyed on the table
	name instead of a DocType because an upload has no DocType. Saved before
	the write so that a failed import leaves a row saying so.
	"""
	source = _warehouse_source()
	existing = uploaded_table(source, table)
	doc = cast(
		"NakhodaTable",
		frappe.get_doc("Nakhoda Table", existing.name) if existing else frappe.new_doc("Nakhoda Table"),
	)
	doc.data_source = source
	doc.table_name = table
	doc.label = label
	doc.document_type = None
	if row_limit is not None:
		doc.row_limit = cint(row_limit)
	doc.save(ignore_permissions=True)
	return doc


def _label(file_name: str | None) -> str:
	"""What the file is called, for a human: the name without its extension."""
	return (file_name or "").rsplit(".", 1)[0] or "Uploaded table"
