# Copyright (c) 2026, Nakhoda and contributors
# For license information, please see license.txt
"""The container that owns a set of queries, charts and dashboards.

Before this DocType, `Nakhoda Query` was top-level and dashboards were
instances of a shipped `Nakhoda Intelligence Template`. That covers the
"answer one question" and "install a canned board" cases and nothing between
them: there was no way to keep the six queries, three charts and one dashboard
that belong to a single investigation together, hand the set to a colleague, or
move it to another site. A workbook is that unit.

Ownership is by `Link`, not by child table - queries, charts and dashboards are
top-level documents that name their workbook. That is what lets a query be read
and executed by the engine without loading its container, and it is why
deletion needs the care below rather than coming free with the parent.

Three things here are worth reading before changing them.

**Delete snapshots before it destroys.** `on_trash` serialises the whole tree
into `data_backup` and only then removes the children. A failed snapshot is
logged and the delete proceeds: a backup is a courtesy, and refusing to delete
a workbook because its backup failed would strand the row forever. The snapshot
is what makes Frappe's own `Deleted Document` restore path meaningful for a
workbook - undeleting the parent replays the children from one JSON blob
instead of needing N undelete rows in the right order.

**Child rows are deleted explicitly.** The children go out through
`frappe.db.delete`, one statement per DocType, because `delete_doc` per row
would be N+1 round trips through the whole validation stack for documents that
are already doomed. The cost of that shortcut is that Frappe's parent/child
cleanup never runs, so `Nakhoda Dashboard Chart` rows would be orphaned in
their own table. This deletes them by `parent`. Insights' equivalent
(`insights_workbook.py:40-42`) does not, and leaks a row per dashboard chart on
every workbook delete.

**Restore renames.** Inserted children get new names, so every reference
between them - a pipeline reading another query, a dashboard tile naming a
chart - is rewritten through an old-name to new-name map. A restore that
skipped this would produce a workbook whose queries point at documents in the
workbook it was copied from.
"""

from __future__ import annotations

from typing import Any

import frappe
from frappe.model.document import Document
from frappe.utils import add_to_date, cint

CHILD_DOCTYPES = ("Nakhoda Query", "Nakhoda Chart", "Nakhoda Dashboard", "Nakhoda Folder")

# Fields carried across an export. Deliberately not `*`: names, timestamps and
# execution telemetry (`cache_key`, `last_row_count`) describe the run on the
# site being copied *from*, and restoring them would attribute one site's
# activity to another. `agent_run` is excluded for both reasons at once: the
# copy was produced by a copy, not by that answer, and the run it names need
# not exist on the site being imported into - a Link to a missing row would
# fail the insert.
EXPORT_FIELDS = {
	"Nakhoda Folder": ("title", "type", "sort_order", "is_expanded"),
	"Nakhoda Query": ("title", "data_source", "folder", "sort_order", "operations"),
	"Nakhoda Chart": ("title", "query", "chart_type", "config", "folder", "sort_order", "is_public"),
	"Nakhoda Dashboard": ("title", "items", "vertical_compact_layout", "is_public"),
}

JSON_FIELDS = {"operations", "config", "items"}

VIEW_DEDUPE_MINUTES = 5


class NakhodaWorkbook(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		data_backup: DF.JSON | None
		title: DF.Data

	# end: auto-generated types

	def before_save(self) -> None:
		# A workbook is named by autoincrement, so a brand new one has a number
		# before it has a title. Naming it after that number beats an empty
		# sidebar entry the user cannot click.
		if not self.title:
			self.title = frappe._("Workbook {0}").format(cint(self.name))

	def on_trash(self) -> None:
		try:
			self.db_set("data_backup", frappe.as_json(self.export()), update_modified=False)
		except Exception:
			frappe.log_error(title=f"Nakhoda: could not back up workbook {self.name} before delete")

		dashboards = frappe.get_all("Nakhoda Dashboard", filters={"workbook": self.name}, pluck="name")

		for doctype in CHILD_DOCTYPES:
			frappe.db.delete(doctype, {"workbook": self.name})

		# See the module docstring: bulk deletes skip Frappe's child cleanup, so
		# the dashboards' own child table has to be cleared by hand.
		if dashboards:
			frappe.db.delete("Nakhoda Dashboard Chart", {"parent": ("in", dashboards)})

	def after_insert(self) -> None:
		# A fresh workbook has no backup. One that does is a restore or a
		# duplicate, and the payload is the tree to rebuild.
		if not self.data_backup:
			return

		backup = _mapping(self.data_backup)
		self.db_set("data_backup", None, update_modified=False)
		self.restore_contents(backup, ignore_permissions=True)

	def export(self) -> dict[str, Any]:
		"""The whole workbook as one JSON-safe payload.

		Keyed by current document name so `restore_contents` can build the
		rename map; the names themselves are never restored.
		"""
		self.check_permission("read")

		dependencies: dict[str, dict[str, Any]] = {}
		for doctype, fields in EXPORT_FIELDS.items():
			rows = frappe.get_all(
				doctype,
				filters={"workbook": self.name},
				fields=("name", *fields),
				order_by="creation asc",
			)
			bucket: dict[str, Any] = {}
			for row in rows:
				name = row.pop("name")
				for field in JSON_FIELDS & row.keys():
					row[field] = frappe.parse_json(row[field]) or []
				bucket[name] = row
			dependencies[doctype] = bucket

		return {"doctype": self.doctype, "title": self.title, "dependencies": dependencies}

	def restore_contents(self, backup: dict[str, Any], ignore_permissions: bool = False) -> None:
		"""Rebuild an exported tree inside this workbook, rewriting references.

		Insert order is folders, queries, charts, dashboards - each layer only
		references layers already inserted, so one pass over each is enough.
		"""
		dependencies = backup.get("dependencies") or {}
		renamed: dict[str, dict[str, str]] = {}

		for doctype in ("Nakhoda Folder", "Nakhoda Query", "Nakhoda Chart", "Nakhoda Dashboard"):
			mapping: dict[str, str] = {}
			for old_name, fields in (dependencies.get(doctype) or {}).items():
				payload = dict(fields)
				payload["doctype"] = doctype
				payload["workbook"] = self.name

				if doctype == "Nakhoda Query":
					payload["operations"] = _remap_operations(
						payload.get("operations"), renamed.get("Nakhoda Query", {})
					)
				elif doctype == "Nakhoda Chart":
					query = str(payload.get("query") or "")
					payload["query"] = renamed.get("Nakhoda Query", {}).get(query, query)
				elif doctype == "Nakhoda Dashboard":
					payload["items"] = _remap_items(payload.get("items"), renamed.get("Nakhoda Chart", {}))

				doc = frappe.get_doc(payload).insert(ignore_permissions=ignore_permissions)
				mapping[old_name] = str(doc.name)

			renamed[doctype] = mapping

		# A pipeline may read a query defined after it in creation order, which
		# the single pass above cannot have remapped yet. One corrective sweep
		# with the complete map closes that.
		query_map = renamed.get("Nakhoda Query", {})
		if query_map:
			for name in query_map.values():
				operations = frappe.db.get_value("Nakhoda Query", name, "operations")
				remapped = _remap_operations(operations, query_map)
				if remapped != operations:
					frappe.db.set_value("Nakhoda Query", name, "operations", remapped, update_modified=False)

	def as_dict(self, *args, **kwargs) -> Any:
		d = super().as_dict(*args, **kwargs)

		d["folders"] = frappe.get_all(
			"Nakhoda Folder",
			filters={"workbook": self.name},
			fields=["name", "title", "type", "sort_order", "is_expanded"],
			order_by="sort_order asc, creation asc",
		)
		d["queries"] = frappe.get_all(
			"Nakhoda Query",
			filters={"workbook": self.name},
			fields=["name", "title", "data_source", "folder", "sort_order", "modified"],
			order_by="sort_order asc, creation asc",
		)
		d["charts"] = frappe.get_all(
			"Nakhoda Chart",
			filters={"workbook": self.name},
			fields=["name", "title", "query", "chart_type", "folder", "sort_order", "modified"],
			order_by="sort_order asc, creation asc",
		)
		d["dashboards"] = frappe.get_all(
			"Nakhoda Dashboard",
			filters={"workbook": self.name},
			fields=["name", "title", "modified"],
			order_by="creation asc",
		)
		# The sidebar hides create affordances for a reader; the tabs render
		# read-only. Deciding that here means one answer per load rather than a
		# permission round trip per section.
		d["read_only"] = not self.has_permission("write")
		# Sharing is a third level, not a synonym for write: `update_share_permissions`
		# grants read and write only (`api/workbooks.py`), so an editor someone
		# else added holds `write` without `share`. Offering them a Manage Access
		# dialog that 403s on open is the failure this answers.
		d["can_share"] = bool(self.has_permission("share"))
		return d

	@frappe.whitelist()
	def track_view(self) -> None:
		"""Record a view, at most once per viewer every five minutes.

		The list page sorts by view count, so an unthrottled counter would
		measure page refreshes rather than interest.
		"""
		self.check_permission("read")

		log = frappe.qb.DocType("View Log")
		recent = (
			frappe.qb.from_(log)
			.select(log.name)
			.where(log.reference_doctype == self.doctype)
			.where(log.reference_name == self.name)
			.where(log.viewed_by == frappe.session.user)
			.where(log.creation > add_to_date(None, minutes=-VIEW_DEDUPE_MINUTES))
			.limit(1)
			.run()
		)
		if recent:
			return

		# Frappe's own view path: it defers the insert under `read_only` and
		# commits after the response, neither of which is worth reimplementing.
		self.add_viewed(force=True)

	@frappe.whitelist()
	def duplicate(self) -> str:
		"""Copy the workbook and everything in it.

		Implemented as export plus insert-with-backup rather than a bespoke
		copy path, so duplication and restore cannot drift apart.
		"""
		self.check_permission("read")
		frappe.has_permission(self.doctype, "create", throw=True)

		copy = frappe.get_doc(
			{
				"doctype": self.doctype,
				"title": frappe._("{0} (Copy)").format(self.title),
				"data_backup": frappe.as_json(self.export()),
			}
		).insert()
		return str(copy.name)

	@frappe.whitelist()
	def import_query(self, query: dict | str) -> str:
		"""Bring a query into this workbook, and the queries it reads with it."""
		copy, _ = self._import_queries(_mapping(query))
		return copy

	@frappe.whitelist()
	def import_chart(self, chart: dict | str) -> str:
		"""Bring a chart from another workbook into this one, query included.

		A chart may not read across workbooks (`nakhoda_chart.py`'s
		`validate_query_workbook`), because the tree a workbook exports has to
		be closed: a chart whose query lives elsewhere restores on another site
		as a Link pointing at nothing. So the query is copied too, and the
		copy is what the imported chart draws. The duplicate is the price of a
		container that survives leaving this site.
		"""
		fields = _mapping(chart)
		source = str(fields.get("query") or "")

		query_map: dict[str, str] = {}
		if source and frappe.db.exists("Nakhoda Query", source):
			_, query_map = self._import_queries(frappe.get_doc("Nakhoda Query", source).as_dict())
		return self._import("Nakhoda Chart", fields, query_map)

	def _import_queries(self, root: dict[str, Any]) -> tuple[str, dict[str, str]]:
		"""Copy one query and its upstream closure, returning the copy and the map.

		Copying a derived query alone would leave the copy naming its parent in
		the *other* workbook - it would run here, and break the first time this
		workbook was exported anywhere else. So the whole closure comes across.

		Insertion order is by closure size, ascending. A query's closure is
		strictly larger than the closure of anything it reads, so shortest-first
		puts every upstream row in place before the query that reads it, which
		is what lets each copy's own `linked_queries` land correct instead of
		short. A query already in this workbook is shared, not copied again.
		"""
		name = str(root.get("name") or "")
		stored = frappe.db.get_value("Nakhoda Query", name, "linked_queries") if name else None
		upstream = _names(stored) or _names(root.get("linked_queries"))

		rows = [root] + [
			frappe.get_doc("Nakhoda Query", other).as_dict()
			for other in upstream
			if other and other != name and frappe.db.exists("Nakhoda Query", other)
		]
		rows.sort(key=lambda row: len(_names(row.get("linked_queries"))))

		query_map: dict[str, str] = {}
		for row in rows:
			source = str(row.get("name") or "")
			if str(row.get("workbook") or "") == str(self.name):
				query_map[source] = source
				continue
			query_map[source] = self._import("Nakhoda Query", row, query_map)
		return query_map.get(name, name), query_map

	def _import(self, doctype: str, payload: dict | str, query_map: dict[str, str] | None = None) -> str:
		self.check_permission("write")

		fields = _mapping(payload)
		allowed = set(EXPORT_FIELDS[doctype])
		doc = {key: value for key, value in fields.items() if key in allowed}
		doc["doctype"] = doctype
		doc["workbook"] = self.name
		# Folders are per-workbook rows; a label from elsewhere would name one
		# that does not exist here.
		doc["folder"] = None
		if query_map:
			if doctype == "Nakhoda Query":
				doc["operations"] = _remap_operations(doc.get("operations"), query_map)
			elif doctype == "Nakhoda Chart":
				doc["query"] = query_map.get(str(doc.get("query") or ""), doc.get("query"))
		return str(frappe.get_doc(doc).insert().name)


def _mapping(value: Any) -> dict[str, Any]:
	"""A dict, whether it arrived as JSON text, a `_dict` or a real dict."""
	parsed = frappe.parse_json(value) if isinstance(value, str) else value
	return dict(parsed) if isinstance(parsed, dict) else {}


def _names(value: Any) -> list[str]:
	"""A list of document names, whether it arrived as JSON text or a list.

	`linked_queries` is JSON in the database and a list once parsed, and both
	shapes reach here - one from `db.get_value`, the other from a payload that
	has already been through `as_dict()`.
	"""
	parsed = frappe.parse_json(value) if isinstance(value, str) else value
	return [str(name) for name in parsed if name] if isinstance(parsed, list) else []


def _remap_operations(operations: Any, query_map: dict[str, str]) -> str:
	"""Rewrite query references inside a pipeline, returning JSON.

	An operation that reads another query carries it as
	`{"table": {"type": "query", "query_name": ...}}`. Anything else is left
	exactly as it was - this walks the structure, it does not validate it.
	"""
	parsed = frappe.parse_json(operations) if isinstance(operations, str) else operations
	if not parsed:
		return frappe.as_json([])

	def walk(node: Any) -> Any:
		if isinstance(node, dict):
			out = {key: walk(value) for key, value in node.items()}
			if out.get("type") == "query" and out.get("query_name") in query_map:
				out["query_name"] = query_map[out["query_name"]]
			return out
		if isinstance(node, list):
			return [walk(item) for item in node]
		return node

	return frappe.as_json(walk(parsed))


def _remap_items(items: Any, chart_map: dict[str, str]) -> str:
	"""Rewrite chart references in a dashboard's tiles, returning JSON."""
	parsed = frappe.parse_json(items) if isinstance(items, str) else items
	if not parsed:
		return frappe.as_json([])

	out = []
	for item in parsed:
		tile = dict(item) if isinstance(item, dict) else item
		if isinstance(tile, dict) and tile.get("type") == "chart" and tile.get("chart") in chart_map:
			tile["chart"] = chart_map[tile["chart"]]
		out.append(tile)
	return frappe.as_json(out)
