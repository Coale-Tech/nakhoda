"""The workbook container: what deletion takes with it, and what a copy becomes.

A workbook owns its contents by `Link`, not by child table, so nothing about
that ownership is enforced by Frappe. Every guarantee this file grades is one
this app's code has to keep by hand:

- deleting a workbook deletes its queries, charts, dashboards and folders, and
  does not leave `Nakhoda Dashboard Chart` rows behind in their own table
  (Insights' `insights_workbook.py:40-42` leaks exactly those);
- undeleting it brings the tree back, because `on_trash` wrote a snapshot before
  destroying anything;
- a duplicate is a *separate* workbook - its queries reference its own copies,
  not the original's, which is the one thing a naive copy always gets wrong;
- a rename or a reorder does not bump `modified` on an open document, because
  the browser autosaves and would read its own sidebar click as a conflict.

The reference-rewriting tests are the load-bearing ones. A pipeline reads
another query by name inside `operations` JSON, and a dashboard tile names a
chart inside `items` JSON; both survive a copy only because `restore_contents`
walks that JSON. Asserting "the copy has three queries" would pass on a broken
implementation that pointed all three at the original's rows.

Permission tests use a real second user rather than a mocked `has_permission`:
the guard being graded is `frappe.has_permission(WORKBOOK, ...)` resolving
through a DocShare, and a mock of the thing under test proves nothing.
"""

from __future__ import annotations

import unittest
from typing import Any

import frappe
from frappe.core.doctype.deleted_document.deleted_document import restore as restore_deleted
from frappe.utils import cint

from nakhoda import api as api_root
from nakhoda.api import workbooks as api

WORKBOOK = "Nakhoda Workbook"
QUERY = "Nakhoda Query"
CHART = "Nakhoda Chart"
DASHBOARD = "Nakhoda Dashboard"
FOLDER = "Nakhoda Folder"
DASHBOARD_CHART = "Nakhoda Dashboard Chart"

OTHER_USER = "workbook-reader@nakhoda.test"


def connected() -> bool:
	return bool(getattr(frappe, "db", None))


@unittest.skipUnless(connected(), "needs a site: bench --site <site> run-tests --app nakhoda")
class Workbooks(unittest.TestCase):
	def setUp(self) -> None:
		frappe.set_user("Administrator")

	def tearDown(self) -> None:
		frappe.set_user("Administrator")
		frappe.db.rollback()

	# -- fixtures ---------------------------------------------------------

	def workbook(self, title: str = "Test Workbook") -> Any:
		return frappe.get_doc({"doctype": WORKBOOK, "title": title}).insert()

	def source(self) -> str:
		"""The site's own database, created on demand.

		`Nakhoda Query.data_source` is `reqd` - a pipeline with no source cannot
		run - so every query fixture needs one. `default_source` is the same
		helper the app itself uses, rather than a bespoke test row that could
		drift from what a real install has.
		"""
		return api_root.default_source()

	def query(self, workbook: str, title: str, operations: list | None = None) -> Any:
		"""A query whose pipeline is valid against the operation grammar.

		`source` naming a DocType is the cheapest shape the grammar accepts;
		the tests here never execute a pipeline, only move it around.
		"""
		return frappe.get_doc(
			{
				"doctype": QUERY,
				"title": title,
				"workbook": workbook,
				"data_source": self.source(),
				"operations": frappe.as_json(
					operations if operations is not None else [{"type": "source", "table": "Currency"}]
				),
			}
		).insert()

	def reading_query(self, workbook: str, title: str, upstream: str) -> Any:
		"""A query that reads another query - the reference a copy must rewrite."""
		return self.query(
			workbook,
			title,
			[{"type": "source", "table": {"type": "query", "query_name": upstream}}],
		)

	def chart(self, workbook: str, title: str, query: str) -> Any:
		return frappe.get_doc(
			{
				"doctype": CHART,
				"title": title,
				"workbook": workbook,
				"query": query,
				"chart_type": "Bar",
				"config": frappe.as_json({"x_axis": "name"}),
			}
		).insert()

	def dashboard(self, workbook: str, title: str, charts: list[str]) -> Any:
		return frappe.get_doc(
			{
				"doctype": DASHBOARD,
				"title": title,
				"workbook": workbook,
				"items": frappe.as_json(
					[
						{
							"type": "chart",
							"chart": name,
							"layout": {"i": name, "x": 0, "y": i, "w": 10, "h": 8},
						}
						for i, name in enumerate(charts)
					]
				),
			}
		).insert()

	def full_workbook(self, title: str = "Full Workbook") -> Any:
		"""One of everything, wired the way the builder wires it."""
		wb = self.workbook(title)
		base = self.query(wb.name, "Base")
		derived = self.reading_query(wb.name, "Derived", base.name)
		chart = self.chart(wb.name, "Revenue", derived.name)
		self.dashboard(wb.name, "Board", [chart.name])
		api.create_folder(wb.name, "Drafts", "query")
		return wb

	def second_user(self) -> str:
		if not frappe.db.exists("User", OTHER_USER):
			frappe.get_doc(
				{
					"doctype": "User",
					"email": OTHER_USER,
					"first_name": "Workbook",
					"last_name": "Reader",
					"roles": [{"role": "Nakhoda User"}],
				}
			).insert(ignore_permissions=True)
		return OTHER_USER

	# -- deletion ---------------------------------------------------------

	def test_deleting_a_workbook_takes_its_contents(self) -> None:
		"""Children are Links, not child rows: nothing deletes them for free."""
		wb = self.full_workbook()

		frappe.delete_doc(WORKBOOK, wb.name)

		for doctype in (QUERY, CHART, DASHBOARD, FOLDER):
			self.assertEqual(
				frappe.db.count(doctype, {"workbook": wb.name}),
				0,
				f"{doctype} rows outlived their workbook",
			)

	def test_deleting_a_workbook_leaves_no_orphan_dashboard_chart_rows(self) -> None:
		"""The bug Insights has: bulk-deleting parents skips child cleanup.

		`Nakhoda Dashboard Chart` is a child table, so its rows are only removed
		by `delete_doc` on the parent. `on_trash` uses `frappe.db.delete` for
		speed and therefore has to clear them itself.
		"""
		wb = self.workbook()
		query = self.query(wb.name, "Base")
		chart = self.chart(wb.name, "Revenue", query.name)
		board = self.dashboard(wb.name, "Board", [chart.name])

		self.assertEqual(
			frappe.db.count(DASHBOARD_CHART, {"parent": board.name}),
			1,
			"linked_charts was never derived from items",
		)

		frappe.delete_doc(WORKBOOK, wb.name)

		self.assertEqual(frappe.db.count(DASHBOARD_CHART, {"parent": board.name}), 0)

	def test_deleting_a_workbook_snapshots_it_first(self) -> None:
		"""`Deleted Document` is only useful if the tree is inside it."""
		wb = self.full_workbook()

		frappe.delete_doc(WORKBOOK, wb.name)

		deleted = frappe.db.get_value(
			"Deleted Document", {"deleted_doctype": WORKBOOK, "deleted_name": wb.name}, "data"
		)
		self.assertTrue(deleted, "no Deleted Document row was written")
		payload = frappe.parse_json(str(deleted))
		backup = frappe.parse_json(payload.get("data_backup") or "{}")
		self.assertIn(QUERY, backup.get("dependencies") or {})
		self.assertEqual(len(backup["dependencies"][QUERY]), 2)

	def test_undeleting_a_workbook_rebuilds_its_contents(self) -> None:
		"""Restore replays the snapshot: one row back, N children with it.

		The row comes back under a *new* id. `Nakhoda Workbook` is
		autoincrement-named and `set_new_name` clears the name it was given
		before taking the next sequence value (`frappe/model/naming.py:158-163`),
		so the old id is not recoverable - Insights' workbooks behave the same
		way. What has to survive is the tree, attached to whatever id the
		restored row lands on.
		"""
		wb = self.full_workbook("Restore Me")
		frappe.delete_doc(WORKBOOK, wb.name)

		deleted = frappe.db.get_value(
			"Deleted Document", {"deleted_doctype": WORKBOOK, "deleted_name": wb.name}, "name"
		)
		# `restore` is a module function on `Deleted Document`, not a method
		# (`frappe/core/doctype/deleted_document/deleted_document.py:41`).
		restore_deleted(str(deleted))

		restored = frappe.db.get_value(WORKBOOK, {"title": "Restore Me"}, "name")
		self.assertTrue(restored, "the workbook itself did not come back")
		self.assertNotEqual(str(restored), str(wb.name))
		self.assertEqual(frappe.db.count(QUERY, {"workbook": restored}), 2)
		self.assertEqual(frappe.db.count(CHART, {"workbook": restored}), 1)
		self.assertEqual(frappe.db.count(DASHBOARD, {"workbook": restored}), 1)
		self.assertEqual(frappe.db.count(FOLDER, {"workbook": restored}), 1)

	def test_a_restored_workbook_keeps_no_data_backup(self) -> None:
		"""The field is a courier, not storage.

		Left populated, the next `after_insert` on a duplicate of this workbook
		would restore the tree twice.
		"""
		wb = self.full_workbook()
		copy_name = wb.duplicate()

		self.assertFalse(frappe.db.get_value(WORKBOOK, copy_name, "data_backup"))

	# -- duplication ------------------------------------------------------

	def test_duplicating_a_workbook_copies_every_layer(self) -> None:
		wb = self.full_workbook()

		copy_name = wb.duplicate()

		self.assertNotEqual(copy_name, wb.name)
		self.assertEqual(frappe.db.count(QUERY, {"workbook": copy_name}), 2)
		self.assertEqual(frappe.db.count(CHART, {"workbook": copy_name}), 1)
		self.assertEqual(frappe.db.count(DASHBOARD, {"workbook": copy_name}), 1)
		self.assertEqual(frappe.db.count(FOLDER, {"workbook": copy_name}), 1)

	def test_a_copied_pipeline_reads_the_copy_not_the_original(self) -> None:
		"""The reference rewrite, which is the whole reason `restore_contents` walks JSON.

		Without it the copy's `Derived` query still names the *original's* `Base`,
		so deleting the original silently breaks a workbook nobody touched.
		"""
		wb = self.workbook()
		base = self.query(wb.name, "Base")
		self.reading_query(wb.name, "Derived", base.name)

		copy_name = wb.duplicate()

		copied = frappe.get_all(
			QUERY, filters={"workbook": copy_name}, fields=["name", "title", "operations"]
		)
		derived = next(row for row in copied if row["title"] == "Derived")
		copied_base = next(row for row in copied if row["title"] == "Base")

		named = frappe.as_json(frappe.parse_json(derived["operations"]))
		self.assertIn(copied_base["name"], named)
		self.assertNotIn(base.name, named)

	def test_a_copied_dashboard_tile_points_at_the_copied_chart(self) -> None:
		wb = self.workbook()
		query = self.query(wb.name, "Base")
		chart = self.chart(wb.name, "Revenue", query.name)
		self.dashboard(wb.name, "Board", [chart.name])

		copy_name = wb.duplicate()

		copied_chart = frappe.db.get_value(CHART, {"workbook": copy_name}, "name")
		items = frappe.db.get_value(DASHBOARD, {"workbook": copy_name}, "items")
		tiles = frappe.parse_json(str(items))

		self.assertEqual(tiles[0]["chart"], copied_chart)
		self.assertNotEqual(tiles[0]["chart"], chart.name)

	def test_a_copied_chart_reads_the_copied_query(self) -> None:
		wb = self.workbook()
		query = self.query(wb.name, "Base")
		self.chart(wb.name, "Revenue", query.name)

		copy_name = wb.duplicate()

		copied_query = frappe.db.get_value(QUERY, {"workbook": copy_name}, "name")
		self.assertEqual(frappe.db.get_value(CHART, {"workbook": copy_name}, "query"), copied_query)

	def test_export_omits_execution_telemetry(self) -> None:
		"""A copy has never run. Carrying the original's run stats would attribute
		one workbook's activity to another."""
		wb = self.workbook()
		query = self.query(wb.name, "Base")
		frappe.db.set_value(QUERY, query.name, {"cache_key": "deadbeef", "last_row_count": 42})

		exported = wb.export()
		fields = next(iter(exported["dependencies"][QUERY].values()))

		self.assertNotIn("cache_key", fields)
		self.assertNotIn("last_row_count", fields)
		self.assertIn("operations", fields)

	def test_importing_an_export_recreates_the_workbook(self) -> None:
		wb = self.full_workbook()
		payload = wb.export()

		imported = api.import_workbook(payload)

		self.assertEqual(frappe.db.count(QUERY, {"workbook": imported}), 2)
		self.assertEqual(frappe.db.count(CHART, {"workbook": imported}), 1)

	def test_importing_something_that_is_not_a_workbook_is_refused(self) -> None:
		with self.assertRaises(frappe.ValidationError):
			api.import_workbook({"title": "Not an export"})

	# -- moving things between workbooks ---------------------------------

	def test_importing_a_chart_brings_the_query_it_draws(self) -> None:
		"""A chart cannot read across workbooks, so the query comes with it.

		The alternative is a container that exports a Link into a workbook the
		payload does not contain - it restores on another site pointing at
		nothing. The duplicate is deliberate.
		"""
		source = self.workbook("Source")
		target = self.workbook("Target")
		query = self.query(source.name, "Base")
		chart = self.chart(source.name, "Revenue", query.name)

		imported = target.import_chart(frappe.get_doc(CHART, chart.name).as_dict())

		copied = frappe.db.get_value(CHART, imported, "query")
		self.assertNotEqual(copied, query.name)
		self.assertEqual(frappe.db.get_value(QUERY, copied, "workbook"), str(target.name))
		self.assertEqual(frappe.db.count(QUERY, {"workbook": target.name}), 1)

	def test_importing_a_derived_query_brings_the_query_it_reads(self) -> None:
		"""The closure crosses, and the copy reads the copy - not the original."""
		source = self.workbook("Source")
		target = self.workbook("Target")
		base = self.query(source.name, "Base")
		derived = self.reading_query(source.name, "Derived", base.name)

		imported = target.import_query(frappe.get_doc(QUERY, derived.name).as_dict())

		self.assertEqual(frappe.db.count(QUERY, {"workbook": target.name}), 2)
		operations = frappe.parse_json(str(frappe.db.get_value(QUERY, imported, "operations")))
		named = str(operations[0]["table"]["query_name"])
		self.assertNotEqual(named, base.name)
		self.assertEqual(frappe.db.get_value(QUERY, named, "workbook"), str(target.name))
		linked = frappe.parse_json(str(frappe.db.get_value(QUERY, imported, "linked_queries")))
		self.assertEqual(linked, [named])

	def test_an_imported_item_loses_a_folder_it_cannot_have(self) -> None:
		"""`folder` is a label scoped to one workbook, not a Link."""
		source = self.workbook("Source")
		target = self.workbook("Target")
		api.create_folder(source.name, "Drafts", "query")
		query = self.query(source.name, "Base")
		api.move_item_to_folder(
			"query", query.name, frappe.db.get_value(FOLDER, {"workbook": source.name}, "name")
		)

		imported = target.import_query(frappe.get_doc(QUERY, query.name).as_dict())

		self.assertIsNone(frappe.db.get_value(QUERY, imported, "folder"))

	# -- folders ----------------------------------------------------------

	def test_renaming_a_folder_moves_the_items_that_name_it(self) -> None:
		"""The label lives on every item, so a rename that touched only the
		folder row would scatter its contents."""
		wb = self.workbook()
		folder = api.create_folder(wb.name, "Drafts", "query")
		query = self.query(wb.name, "Base")
		api.move_item_to_folder("query", query.name, folder)

		api.rename_folder(folder, "Reviewed")

		self.assertEqual(frappe.db.get_value(QUERY, query.name, "folder"), "Reviewed")
		self.assertEqual(frappe.db.get_value(FOLDER, folder, "title"), "Reviewed")

	def test_deleting_a_folder_keeps_its_items_by_default(self) -> None:
		wb = self.workbook()
		folder = api.create_folder(wb.name, "Drafts", "query")
		query = self.query(wb.name, "Base")
		api.move_item_to_folder("query", query.name, folder)

		api.delete_folder(folder)

		self.assertTrue(frappe.db.exists(QUERY, query.name))
		self.assertIsNone(frappe.db.get_value(QUERY, query.name, "folder"))

	def test_deleting_a_folder_can_take_its_items(self) -> None:
		wb = self.workbook()
		folder = api.create_folder(wb.name, "Drafts", "query")
		query = self.query(wb.name, "Base")
		api.move_item_to_folder("query", query.name, folder)

		api.delete_folder(folder, move_items_to_root=False)

		self.assertFalse(frappe.db.exists(QUERY, query.name))

	def test_a_chart_folder_will_not_hold_a_query(self) -> None:
		"""Sections are separate trees; one label cannot span both."""
		wb = self.workbook()
		folder = api.create_folder(wb.name, "Visuals", "chart")
		query = self.query(wb.name, "Base")

		with self.assertRaises(frappe.ValidationError):
			api.move_item_to_folder("query", query.name, folder)

	def test_a_folder_from_another_workbook_is_refused(self) -> None:
		other = self.workbook("Other")
		folder = api.create_folder(other.name, "Drafts", "query")
		wb = self.workbook()
		query = self.query(wb.name, "Base")

		with self.assertRaises(frappe.ValidationError):
			api.move_item_to_folder("query", query.name, folder)

	def test_the_last_chart_out_of_a_folder_takes_the_folder_with_it(self) -> None:
		"""An empty folder is litter the user cannot see a reason for."""
		wb = self.workbook()
		folder = api.create_folder(wb.name, "Visuals", "chart")
		query = self.query(wb.name, "Base")
		chart = self.chart(wb.name, "Revenue", query.name)
		api.move_item_to_folder("chart", chart.name, folder)

		frappe.delete_doc(CHART, chart.name)

		self.assertFalse(frappe.db.exists(FOLDER, folder))

	# -- writes that are not edits ---------------------------------------

	def test_reordering_the_sidebar_does_not_touch_modified(self) -> None:
		"""An open document autosaves. A sidebar drag that bumped `modified`
		would make the browser's next save look like someone else's edit."""
		wb = self.workbook()
		query = self.query(wb.name, "Base")
		before = frappe.db.get_value(QUERY, query.name, "modified")

		api.update_sort_orders(wb.name, [{"item_type": "query", "item_name": query.name, "sort_order": 7}])

		self.assertEqual(frappe.db.get_value(QUERY, query.name, "modified"), before)
		self.assertEqual(cint(frappe.db.get_value(QUERY, query.name, "sort_order")), 7)

	def test_expanding_a_folder_does_not_touch_modified(self) -> None:
		wb = self.workbook()
		folder = api.create_folder(wb.name, "Drafts", "query")
		before = frappe.db.get_value(FOLDER, folder, "modified")

		api.toggle_folder_expanded(folder, True)

		self.assertEqual(frappe.db.get_value(FOLDER, folder, "modified"), before)
		self.assertTrue(cint(frappe.db.get_value(FOLDER, folder, "is_expanded")))

	def test_reordering_will_not_touch_a_row_in_another_workbook(self) -> None:
		"""The caller proved write access to one workbook, not to any row it names."""
		wb = self.workbook()
		other = self.workbook("Other")
		outsider = self.query(other.name, "Outsider")

		api.update_sort_orders(wb.name, [{"item_type": "query", "item_name": outsider.name, "sort_order": 9}])

		self.assertEqual(cint(frappe.db.get_value(QUERY, outsider.name, "sort_order")), 0)

	# -- linked queries ---------------------------------------------------

	def test_a_query_records_what_it_reads(self) -> None:
		"""The builder loads a query's dependencies before running it; walking
		the pipeline in the browser would mean a round trip per operation."""
		wb = self.workbook()
		base = self.query(wb.name, "Base")
		derived = self.reading_query(wb.name, "Derived", base.name)

		self.assertEqual(frappe.parse_json(derived.linked_queries), [base.name])

	def test_linked_queries_are_transitive(self) -> None:
		"""A reads B reads C: loading A must fetch C, or its pipeline cannot compile."""
		wb = self.workbook()
		c = self.query(wb.name, "C")
		b = self.reading_query(wb.name, "B", c.name)
		a = self.reading_query(wb.name, "A", b.name)

		self.assertEqual(set(frappe.parse_json(a.linked_queries)), {b.name, c.name})

	def test_a_pipeline_that_reads_itself_does_not_hang(self) -> None:
		"""Nothing stops a user pointing a query at itself in the JSON. The walk
		has to terminate even though the pipeline is nonsense."""
		wb = self.workbook()
		query = self.query(wb.name, "Base")
		query.operations = frappe.as_json(
			[{"type": "source", "table": {"type": "query", "query_name": query.name}}]
		)
		query.save()

		self.assertEqual(frappe.parse_json(query.linked_queries), [query.name])

	# -- sharing ----------------------------------------------------------

	def test_sharing_grants_read_and_revoking_removes_it(self) -> None:
		wb = self.workbook()
		user = self.second_user()

		api.update_share_permissions(wb.name, [{"user": user, "write": 0}])
		self.assertEqual(
			frappe.db.count("DocShare", {"share_doctype": WORKBOOK, "share_name": wb.name, "user": user}),
			1,
		)

		api.update_share_permissions(wb.name, [])
		self.assertEqual(
			frappe.db.count("DocShare", {"share_doctype": WORKBOOK, "share_name": wb.name, "user": user}),
			0,
		)

	def test_a_shared_reader_can_read_but_not_write(self) -> None:
		"""The permission that matters is Frappe's, resolved through the DocShare -
		so this asserts against a real second user rather than a mocked check."""
		wb = self.workbook()
		user = self.second_user()
		api.update_share_permissions(wb.name, [{"user": user, "write": 0}])

		frappe.set_user(user)
		self.assertTrue(frappe.has_permission(WORKBOOK, "read", doc=wb.name))
		self.assertFalse(frappe.has_permission(WORKBOOK, "write", doc=wb.name))

	def test_organization_access_is_one_row_and_replaces_itself(self) -> None:
		"""Flipping view/edit must not accumulate `everyone` shares - two rows
		would leave the effective grant to whichever Frappe reads first."""
		wb = self.workbook()

		api.update_share_permissions(wb.name, [], organization_access="view")
		api.update_share_permissions(wb.name, [], organization_access="edit")

		shares = frappe.get_all(
			"DocShare",
			filters={"share_doctype": WORKBOOK, "share_name": wb.name, "everyone": 1},
			fields=["name", "write"],
		)
		self.assertEqual(len(shares), 1)
		self.assertTrue(cint(shares[0]["write"]))

		api.update_share_permissions(wb.name, [], organization_access=None)
		self.assertEqual(
			frappe.db.count("DocShare", {"share_doctype": WORKBOOK, "share_name": wb.name, "everyone": 1}),
			0,
		)

	def test_an_organization_share_belongs_to_nobody(self) -> None:
		"""`share.add_docshare` would stamp the acting user onto the row; the
		switch is not a grant to whoever flipped it."""
		wb = self.workbook()

		api.update_share_permissions(wb.name, [], organization_access="view")

		user = frappe.db.get_value(
			"DocShare", {"share_doctype": WORKBOOK, "share_name": wb.name, "everyone": 1}, "user"
		)
		self.assertFalse(user)

	def test_the_owner_is_never_listed_as_a_share(self) -> None:
		"""Owner access is structural. A row for it could be revoked to no effect."""
		wb = self.workbook()

		api.update_share_permissions(wb.name, [{"user": "Administrator", "write": 1}])

		self.assertEqual(frappe.db.count("DocShare", {"share_doctype": WORKBOOK, "share_name": wb.name}), 0)

	def test_share_state_reads_back_as_the_dialog_sent_it(self) -> None:
		wb = self.workbook()
		user = self.second_user()

		api.update_share_permissions(wb.name, [{"user": user, "write": 1}], organization_access="view")
		state = api.get_share_permissions(wb.name)

		self.assertEqual(state["organization_access"], "view")
		self.assertEqual(len(state["user_permissions"]), 1)
		self.assertEqual(state["user_permissions"][0]["user"], user)
		self.assertTrue(state["user_permissions"][0]["write"])

	def test_an_unknown_organization_access_is_refused(self) -> None:
		wb = self.workbook()

		with self.assertRaises(frappe.ValidationError):
			api.update_share_permissions(wb.name, [], organization_access="admin")

	# -- the share picker -------------------------------------------------

	def test_the_picker_offers_users_of_this_app(self) -> None:
		"""A candidate to share with is someone who can open the app at all."""
		wb = self.workbook()
		user = self.second_user()

		offered = api.list_shareable_users(wb.name)

		self.assertIn(user, [row["user"] for row in offered])

	def test_the_picker_searches_by_name_and_email(self) -> None:
		wb = self.workbook()
		user = self.second_user()

		self.assertIn(user, [row["user"] for row in api.list_shareable_users(wb.name, "Reader")])
		self.assertIn(user, [row["user"] for row in api.list_shareable_users(wb.name, user.split("@")[0])])
		self.assertEqual(api.list_shareable_users(wb.name, "nobody-by-that-name"), [])

	def test_the_picker_is_gated_on_the_workbook_not_on_a_role(self) -> None:
		"""The user directory is not a reward for holding `Nakhoda User`: a reader
		of someone else's workbook administers nothing and is offered nobody."""
		wb = self.workbook()
		user = self.second_user()
		api.update_share_permissions(wb.name, [{"user": user, "write": 1}])

		frappe.set_user(user)
		with self.assertRaises(frappe.PermissionError):
			api.list_shareable_users(wb.name)

	def test_an_editor_someone_else_added_is_not_offered_the_dialog(self) -> None:
		"""`update_share_permissions` grants read and write, never share, so the
		document has to say whether Manage Access would open or 403."""
		wb = self.workbook()
		user = self.second_user()
		api.update_share_permissions(wb.name, [{"user": user, "write": 1}])

		self.assertTrue(wb.as_dict()["can_share"])

		frappe.set_user(user)
		self.assertFalse(frappe.get_doc(WORKBOOK, wb.name).as_dict()["can_share"])

	# -- the list ---------------------------------------------------------

	def test_the_list_says_which_workbooks_are_shared_and_how_often_seen(self) -> None:
		"""Both columns are batched reads; a per-row lookup would make this list
		slower with every workbook on the site."""
		wb = self.workbook("Findable Workbook")
		wb.track_view()
		api.update_share_permissions(wb.name, [], organization_access="view")

		row = next(r for r in api.get_workbooks(search_term="Findable") if r["name"] == wb.name)

		self.assertTrue(row["shared_with_organization"])
		self.assertEqual(row["views"], 1)

	def test_the_list_names_the_person_a_workbook_is_shared_with(self) -> None:
		"""The Access column shows a person when exactly one holds the workbook,
		so the row has to carry a name: an email there would be the only login
		printed anywhere on the page."""
		wb = self.workbook("Named Share")
		user = self.second_user()
		api.update_share_permissions(wb.name, [{"user": user, "read": 1}])

		row = next(r for r in api.get_workbooks(search_term="Named Share") if r["name"] == wb.name)

		self.assertEqual(row["shared_with"], [user])
		self.assertEqual(row["shared_with_names"], [frappe.db.get_value("User", user, "full_name")])

	def test_a_view_is_counted_once_per_viewer_per_window(self) -> None:
		"""The list sorts by views, so an unthrottled counter measures refreshes."""
		wb = self.workbook()

		wb.track_view()
		wb.track_view()

		self.assertEqual(
			frappe.db.count("View Log", {"reference_doctype": WORKBOOK, "reference_name": wb.name}),
			1,
		)

	def test_the_list_search_matches_titles(self) -> None:
		self.workbook("Quarterly Revenue")
		self.workbook("Headcount")

		titles = [row["title"] for row in api.get_workbooks(search_term="Quarterly")]

		self.assertIn("Quarterly Revenue", titles)
		self.assertNotIn("Headcount", titles)

	def test_the_list_is_scoped_to_the_caller(self) -> None:
		"""`frappe.get_all` documents itself as **not** checking permissions
		(`frappe/__init__.py:1383`), so a list built on it names rows that refuse
		when clicked. Only `get_list` reaches `nakhoda.permissions`."""
		mine = self.workbook("Administrator only")

		frappe.set_user(self.second_user())
		names = [row["name"] for row in api.get_workbooks()]

		self.assertNotIn(mine.name, names)

	# -- the document payload the builder loads ---------------------------

	def test_loading_a_workbook_returns_its_tree_in_one_document(self) -> None:
		"""Four collections plus the row, so opening a workbook is one request
		rather than five."""
		wb = self.full_workbook()

		payload = frappe.get_doc(WORKBOOK, wb.name).as_dict()

		self.assertEqual(len(payload["queries"]), 2)
		self.assertEqual(len(payload["charts"]), 1)
		self.assertEqual(len(payload["dashboards"]), 1)
		self.assertEqual(len(payload["folders"]), 1)
		self.assertFalse(payload["read_only"])

	def test_a_reader_is_told_the_workbook_is_read_only(self) -> None:
		"""The tabs decide affordances from this flag; asking per section would
		be a permission round trip per tab."""
		wb = self.workbook()
		user = self.second_user()
		api.update_share_permissions(wb.name, [{"user": user, "write": 0}])

		frappe.set_user(user)
		payload = frappe.get_doc(WORKBOOK, wb.name).as_dict()

		self.assertTrue(payload["read_only"])

	# -- an answer becoming a workbook ------------------------------------

	def agent_run(self, question: str = "Revenue by territory", status: str = "ok") -> Any:
		"""The audit row a chat turn leaves behind - the thing a save reads from."""
		return frappe.get_doc(
			{
				"doctype": "Nakhoda Agent Run",
				"user": frappe.session.user,
				"question": question,
				"status": status,
				"operations": frappe.as_json([{"type": "source", "table": "Currency"}]),
				"sql": "select 1",
				"row_count": 1,
			}
		).insert(ignore_permissions=True)

	def test_saving_an_answer_builds_the_workbook_it_needs(self) -> None:
		""" "Build me a workbook" is the same call as "save this answer", without
		a target: one workbook, one query, one chart, titled by the question."""
		run = self.agent_run()

		saved = api.save_answer(run.name, chart={"series": [{"label": "West", "value": 10.0}]})

		self.assertEqual(frappe.db.get_value(WORKBOOK, saved["workbook"], "title"), "Revenue by territory")
		self.assertEqual(frappe.db.get_value(QUERY, saved["query"], "workbook"), str(saved["workbook"]))
		self.assertEqual(frappe.db.get_value(CHART, saved["chart"], "query"), saved["query"])
		self.assertEqual(frappe.db.get_value(CHART, saved["chart"], "chart_type"), "Bar")

	def test_a_saved_answer_carries_the_pipeline_that_answered(self) -> None:
		"""The endpoint takes no operations at all: the query it writes is the
		run's own pipeline, so "save this answer" cannot save a different one."""
		run = self.agent_run()

		saved = api.save_answer(run.name)

		self.assertEqual(
			frappe.parse_json(str(frappe.db.get_value(QUERY, saved["query"], "operations"))),
			frappe.parse_json(str(run.operations)),
		)
		self.assertIsNone(saved["chart"], "no series was supplied, so there is nothing to draw")

	def test_a_saved_answer_records_which_answer_it_came_from(self) -> None:
		"""`12-build-plan.md` §4 requires a stored artifact to say what produced
		it. The run is the record that carries the question, the source and the
		model, so the query names the run rather than copying three fields."""
		run = self.agent_run()

		saved = api.save_answer(run.name)

		self.assertEqual(frappe.db.get_value(QUERY, saved["query"], "agent_run"), run.name)
		self.assertEqual(
			frappe.db.get_value("Nakhoda Agent Run", run.name, "question"), "Revenue by territory"
		)

	def test_an_answers_run_cannot_be_deleted_while_a_query_cites_it(self) -> None:
		"""The account is only worth recording if it survives: Frappe refuses to
		delete a linked document, so the origin cannot silently become a dangling
		name after the fact."""
		run = self.agent_run()
		api.save_answer(run.name)

		with self.assertRaises(frappe.LinkExistsError):
			frappe.delete_doc("Nakhoda Agent Run", run.name)

	def test_a_copied_query_does_not_claim_the_original_answer(self) -> None:
		"""A copy was produced by a copy. Carrying the link would also break a
		cross-site import, where that run does not exist (`EXPORT_FIELDS`)."""
		run = self.agent_run()
		saved = api.save_answer(run.name)
		source = frappe.get_doc(WORKBOOK, saved["workbook"])

		copy = frappe.get_doc(WORKBOOK, source.duplicate())

		copied = frappe.get_all(QUERY, filters={"workbook": copy.name}, fields=["name", "agent_run"])
		self.assertEqual(len(copied), 1)
		self.assertIsNone(copied[0].agent_run)

	def test_saving_into_an_existing_workbook_adds_to_it(self) -> None:
		wb = self.workbook("Sales Review")
		run = self.agent_run()

		saved = api.save_answer(run.name, workbook=wb.name)

		self.assertEqual(str(saved["workbook"]), str(wb.name))
		self.assertEqual(frappe.db.count(QUERY, {"workbook": wb.name}), 1)
		self.assertEqual(frappe.db.count(WORKBOOK, {"title": "Sales Review"}), 1)

	def test_an_answer_that_failed_has_nothing_to_save(self) -> None:
		"""A run with no pipeline would produce a query that cannot run - the
		error belongs at the save, not at the first click in the builder."""
		run = self.agent_run(status="error")

		with self.assertRaises(frappe.ValidationError):
			api.save_answer(run.name)

	def test_a_long_question_is_trimmed_into_a_title(self) -> None:
		run = self.agent_run(question="Revenue " * 40)

		saved = api.save_answer(run.name)

		title = str(frappe.db.get_value(QUERY, saved["query"], "title"))
		self.assertLessEqual(len(title), 140)
		self.assertTrue(title.endswith("..."))

	def test_saving_into_a_workbook_a_reader_cannot_write_is_refused(self) -> None:
		"""The save is a write to somebody else's container; read access to the
		answer is not access to the workbook."""
		wb = self.workbook()
		user = self.second_user()
		api.update_share_permissions(wb.name, [{"user": user, "write": 0}])

		frappe.set_user(user)
		run = self.agent_run()
		with self.assertRaises(frappe.PermissionError):
			api.save_answer(run.name, workbook=wb.name)

	def test_one_user_cannot_save_another_users_answer(self) -> None:
		"""`Nakhoda Agent Run` is `if_owner` for readers, and the save reads it
		- so the run is a boundary, not just a lookup key."""
		run = self.agent_run()
		user = self.second_user()

		frappe.set_user(user)
		with self.assertRaises(frappe.PermissionError):
			api.save_answer(run.name)


if __name__ == "__main__":
	unittest.main()
