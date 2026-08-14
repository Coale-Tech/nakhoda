# Copyright (c) 2026, Nakhoda and contributors
# For license information, please see license.txt
"""Query CRUD surface. Execution lives in `nakhoda.api.__init__` (`run`,
`execute`, `validate`) because ad-hoc pipelines and stored queries share one
engine path; this file only owns the `Nakhoda Query` document lifecycle."""

from __future__ import annotations

from typing import Any

import frappe

from nakhoda.api import default_source
from nakhoda.engine.permissions import table_name
from nakhoda.semantic.model import describe


@frappe.whitelist()
def list_sources() -> list[dict[str, Any]]:
	"""Readable DocTypes that exist as tables in the active database.

	Returns a list sorted by label, with a machine table name for every
	DocType the current user is permitted to read. Child tables are included
	but flagged; child tables are only useful after a source or join that
	carries their `parent`.
	"""
	user = frappe.session.user
	rows = frappe.db.sql("""
		SELECT table_name
		FROM information_schema.tables
		WHERE table_schema = DATABASE()
		  AND table_name LIKE 'tab%%'
		ORDER BY table_name
	""")

	out = []
	for (tab_name,) in rows:
		doctype = tab_name[3:]
		if not doctype:
			continue
		if not frappe.db.exists("DocType", doctype):
			continue
		if not frappe.has_permission(doctype, "read", user=user):
			continue
		meta = frappe.get_meta(doctype, cached=True)
		out.append({
			"name": doctype,
			"label": doctype,
			"table": tab_name,
			"is_child": bool(meta.get("istable")),
		})
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
	"""Return the current user's queries, newest first."""
	filters: dict[str, Any] = {}
	if data_source:
		filters["data_source"] = data_source

	fields = ["name", "title", "data_source", "modified", "last_executed_on", "last_row_count"]
	return frappe.get_all("Nakhoda Query", fields=fields, filters=filters, limit_page_length=int(limit), order_by="modified desc")


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
) -> dict[str, Any]:
	"""Create or update a `Nakhoda Query`. The document's own `validate` rejects
	malformed pipelines, so the grammar is enforced on save."""
	if not title:
		frappe.throw(frappe._("Title is required"), title=frappe._("Missing title"))
	if operations is None:
		frappe.throw(frappe._("Operations are required"), title=frappe._("Missing pipeline"))

	source = data_source or default_source()

	if name:
		doc = frappe.get_doc("Nakhoda Query", name)
		doc.check_permission("write")
	else:
		doc = frappe.get_doc({"doctype": "Nakhoda Query"})

	doc.title = title
	doc.data_source = source
	doc.operations = frappe.as_json(operations)
	doc.save()

	return {
		"name": doc.name,
		"title": doc.title,
		"data_source": doc.data_source,
		"operations": frappe.parse_json(doc.operations),
	}


@frappe.whitelist()
def delete_query(name: str) -> None:
	"""Delete a query the current user may write."""
	doc = frappe.get_doc("Nakhoda Query", name)
	doc.check_permission("write")
	doc.delete()
