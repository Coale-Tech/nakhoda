# Copyright (c) 2026, Nakhoda and contributors
# For license information, please see license.txt
"""Query CRUD surface. Execution lives in `nakhoda.api.__init__` (`run`,
`execute`, `validate`) because ad-hoc pipelines and stored queries share one
engine path; this file only owns the `Nakhoda Query` document lifecycle."""

from __future__ import annotations

from typing import Any

import frappe
from frappe.permissions import get_doctypes_with_read

from nakhoda.api import default_source
from nakhoda.semantic.model import describe


@frappe.whitelist()
def list_sources() -> list[dict[str, Any]]:
	"""Readable DocTypes that exist as tables in the active database.

	Returns a list sorted by label, with a machine table name for every
	DocType the current user is permitted to read. Child tables are included
	but flagged; child tables are only useful after a source or join that
	carries their `parent`.

	Three queries, not three per DocType. The obvious spelling of this - walk
	`information_schema`, then `frappe.db.exists` + `has_permission` +
	`get_meta` per row - measured 13s warm and 44s cold on this site's 1,103
	tables, because `has_permission` and `get_meta` each build a DocType's
	meta from the database on a cold cache. The picker that opens on every
	Ask, and the Data Sources list that renders on navigation, cannot cost
	that. So: one `information_schema` sweep, one `DocType` read for names and
	`istable`, and one role-permission pass.

	`get_doctypes_with_read` is the role-permission half of `has_permission`
	(`frappe/permissions.py`), read from `DocPerm` / `Custom DocPerm` for the
	user's roles in a couple of cached queries. It differs from
	`has_permission` in one direction: a DocType the user reaches *only*
	because a single document was shared with them no longer appears in the
	picker. That is the right narrowing for a table list - a table you can see
	one row of is not a source - and nothing downstream relies on this call
	for enforcement: `get_schema`, `engine.permissions.for_connector` and every
	read path still ask `has_permission` for the specific DocType.
	"""
	# `get_tables` caches the `information_schema` sweep in redis; the raw
	# query costs seconds on a cold buffer pool here, because it stats every
	# one of this site's tables.
	tables = set(frappe.db.get_tables() or [])
	# `frappe.get_all` ignores permissions, which is what we want: the read
	# filter below is the DocType-level one, applied explicitly.
	doctypes = frappe.get_all("DocType", fields=["name", "istable"])
	# Administrator short-circuits `has_permission` itself, so asking the
	# permission tables for them would answer a narrower question than the
	# one the app enforces.
	readable = None if frappe.session.user == "Administrator" else set(get_doctypes_with_read())

	out = [
		{
			"name": row.name,
			"label": row.name,
			"table": f"tab{row.name}",
			"is_child": bool(row.istable),
		}
		for row in doctypes
		if f"tab{row.name}" in tables and (readable is None or row.name in readable)
	]
	out.sort(key=lambda row: row["label"])
	return out


@frappe.whitelist()
def get_schema(doctype: str) -> dict[str, Any]:
	"""Permitted schema for one DocType, in the same shape the engine uses.

	Columns are filtered to the fields the current user is allowed to read,
	so the UI can only build pipelines the permission resolver will accept.
	"""
	user = frappe.session.user
	if not frappe.has_permission(doctype, "read", user=user):
		frappe.throw(frappe._("Not permitted to read {0}").format(doctype), frappe.PermissionError)

	meta = frappe.get_meta(doctype)
	raw = describe(meta)

	from frappe.model import get_permitted_fields

	permitted = set(get_permitted_fields(doctype, user=user))
	permitted.add("name")
	if meta.get("is_submittable"):
		permitted.add("docstatus")
	if meta.get("istable"):
		permitted.add("parent")
		permitted.add("parenttype")

	columns = [c for c in raw["columns"] if c["name"] in permitted]
	return {
		"doctype": raw["doctype"],
		"table": raw["table"],
		"flags": raw["flags"],
		"description": raw["description"],
		"columns": columns,
	}


@frappe.whitelist()
def list_queries(data_source: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
	"""The caller's unfiled queries - the ones no workbook holds - newest first.

	Two deliberate narrowings, both of which this used to get wrong:

	`get_list`, not `get_all`: `get_all` documents itself as **not** checking
	permissions (`frappe/__init__.py:1383`), so it skipped
	`permissions.get_permission_query_conditions` and listed titles belonging to
	every other user. A list that refuses when clicked is worse than a short one.

	`workbook is not set`: a query saved into a workbook is already listed in
	that workbook's own sidebar (`WorkbookSidebarSection`), so listing it here
	too made this page a shadow of every workbook. What is left is the shape
	Insights cannot have - `insights_query_v3.workbook` is `reqd`, ours is not,
	so the standalone builder can save a query that belongs to no container,
	and that query needs one home. This is it.
	"""
	filters: dict[str, Any] = {"workbook": ("is", "not set")}
	if data_source:
		filters["data_source"] = data_source

	fields = ["name", "title", "data_source", "modified", "last_executed_on", "last_row_count"]
	return frappe.get_list(
		"Nakhoda Query",
		fields=fields,
		filters=filters,
		limit_page_length=int(limit),
		order_by="modified desc",
	)


@frappe.whitelist()
def get_query(name: str) -> dict[str, Any]:
	"""Fetch one query if the current user may read it."""
	doc = frappe.get_doc("Nakhoda Query", name)
	doc.check_permission("read")
	return {
		"name": doc.name,
		"title": doc.title,
		"data_source": doc.data_source,
		"operations": frappe.parse_json(doc.operations),
		"last_executed_on": doc.last_executed_on,
		"last_row_count": doc.last_row_count,
		"last_execution_time": doc.last_execution_time,
	}


@frappe.whitelist()
def save_query(
	name: str | None = None,
	title: str | None = None,
	data_source: str | None = None,
	operations: Any = None,
	workbook: str | None = None,
) -> dict[str, Any]:
	"""Create or update a `Nakhoda Query`. The document's own `validate` rejects
	malformed pipelines, so the grammar is enforced on save.

	`workbook` places a *new* query in a container and is checked here, because
	`Nakhoda Query.workbook` is a plain Link that no permission of its own
	guards - write access to the query would otherwise be enough to file it
	inside someone else's workbook. An existing query keeps the workbook it
	has: moving one between containers is `import_query`'s job
	(`api/workbooks.py`), which copies rather than reassigns so a chart already
	reading it does not silently lose its source.
	"""
	if not title:
		frappe.throw(frappe._("Title is required"), title=frappe._("Missing title"))
	if operations is None:
		frappe.throw(frappe._("Operations are required"), title=frappe._("Missing pipeline"))

	source = data_source or default_source()

	# `Any` for the same reason `api/workbooks.py` does it: `workbook` is this
	# app's own field, and the generic document class Pyright infers from
	# `get_doc` declares none of them.
	doc: Any
	if name:
		doc = frappe.get_doc("Nakhoda Query", name)
		doc.check_permission("write")
	else:
		doc = frappe.get_doc({"doctype": "Nakhoda Query"})
		if workbook:
			frappe.has_permission("Nakhoda Workbook", "write", doc=workbook, throw=True)
			doc.workbook = workbook

	doc.title = title
	doc.data_source = source
	doc.operations = frappe.as_json(operations)
	doc.save()

	return {
		"name": doc.name,
		"title": doc.title,
		"data_source": doc.data_source,
		"workbook": doc.workbook,
		"operations": frappe.parse_json(doc.operations),
	}


@frappe.whitelist()
def delete_query(name: str) -> None:
	"""Delete a query the current user may write."""
	doc = frappe.get_doc("Nakhoda Query", name)
	doc.check_permission("write")
	doc.delete()
