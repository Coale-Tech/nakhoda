"""The `Nakhoda Query` CRUD surface, against a real site."""

from __future__ import annotations

import unittest

import frappe

from nakhoda.api import default_source, query

COUNT_INVOICES = [
	{"type": "source", "table": "tabSales Invoice"},
	{"type": "summarize", "measures": [{"name": "n", "expr": {"fn": "count", "args": []}}]},
]


def connected() -> bool:
	return bool(getattr(frappe, "db", None))


@unittest.skipUnless(connected(), "needs a site: bench --site <site> run-tests --app nakhoda")
class QueryApi(unittest.TestCase):
	def setUp(self) -> None:
		frappe.set_user("Administrator")

	def tearDown(self) -> None:
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def test_create_query_requires_title_and_operations(self):
		with self.assertRaises(frappe.ValidationError):
			query.save_query(title="Missing pipeline", operations=None)
		with self.assertRaises(frappe.ValidationError):
			query.save_query(title="", operations=COUNT_INVOICES)

	def test_create_and_list_query(self):
		saved = query.save_query(title="Invoice count", operations=COUNT_INVOICES)
		self.assertTrue(saved["name"])
		self.assertEqual(saved["title"], "Invoice count")
		self.assertEqual(saved["data_source"], default_source())

		listed = query.list_queries()
		self.assertIn(saved["name"], [q["name"] for q in listed])

		fetched = query.get_query(saved["name"])
		self.assertEqual(fetched["operations"], COUNT_INVOICES)

	def test_a_query_inside_a_workbook_is_not_listed_here(self):
		"""The page is the home for unfiled queries only.

		A query with a workbook is already a row in that workbook's sidebar;
		listing it here as well made this page a shadow of every workbook.
		"""
		workbook = frappe.get_doc({"doctype": "Nakhoda Workbook", "title": "Query home"}).insert()
		filed = query.save_query(title="Filed count", operations=COUNT_INVOICES, workbook=workbook.name)
		unfiled = query.save_query(title="Unfiled count", operations=COUNT_INVOICES)

		names = [q["name"] for q in query.list_queries()]
		self.assertIn(unfiled["name"], names)
		self.assertNotIn(filed["name"], names)

	def test_the_list_is_the_callers_own(self):
		"""`get_all` does not check permissions, so this listed everyone's rows.

		The resolver in `nakhoda.permissions` only reaches a list query through
		`get_list`; a title that 403s when clicked is the failure this answers.
		"""
		mine = query.save_query(title="Admin count", operations=COUNT_INVOICES)

		other = frappe.get_doc(
			{
				"doctype": "User",
				"email": "nakhoda-query-second@example.com",
				"first_name": "Second",
				"send_welcome_email": 0,
				"roles": [{"role": "Nakhoda User"}],
			}
		)
		other.flags.ignore_permissions = True
		other.insert()

		frappe.set_user(other.name)
		theirs = query.save_query(title="Their count", operations=COUNT_INVOICES)
		names = [q["name"] for q in query.list_queries()]
		self.assertIn(theirs["name"], names)
		self.assertNotIn(mine["name"], names)

	def test_update_query(self):
		saved = query.save_query(title="Invoice count", operations=COUNT_INVOICES)
		updated = query.save_query(name=saved["name"], title="Updated count", operations=COUNT_INVOICES)
		self.assertEqual(updated["name"], saved["name"])
		self.assertEqual(updated["title"], "Updated count")

	def test_malformed_pipeline_rejected_on_save(self):
		with self.assertRaises(frappe.ValidationError):
			query.save_query(title="Bad", operations=[{"type": "nonsense"}])

	def test_delete_query(self):
		saved = query.save_query(title="To delete", operations=COUNT_INVOICES)
		query.delete_query(saved["name"])
		self.assertIsNone(frappe.db.get_value("Nakhoda Query", saved["name"], "name"))

	def test_list_sources_contains_sales_invoice(self):
		sources = query.list_sources()
		names = {s["name"] for s in sources}
		self.assertIn("Sales Invoice", names)
		# every entry carries both a DocType name and a machine table name
		for s in sources:
			self.assertTrue(s["name"])
			self.assertEqual(s["table"], f"tab{s['name']}")
			self.assertIn("label", s)
			self.assertIn("is_child", s)

	def test_get_schema_filters_to_permitted_columns(self):
		schema = query.get_schema("Sales Invoice")
		self.assertEqual(schema["doctype"], "Sales Invoice")
		self.assertEqual(schema["table"], "tabSales Invoice")
		self.assertTrue(schema["columns"])
		self.assertIn("name", [c["name"] for c in schema["columns"]])
		# every column carries the engine shape
		for col in schema["columns"]:
			self.assertIn("name", col)
			self.assertIn("type", col)
			self.assertIn("notes", col)

	def test_get_schema_rejects_unreadable_doctype(self):
		outsider = frappe.get_doc(
			{
				"doctype": "User",
				"email": "nakhoda-schema-outsider@example.com",
				"first_name": "outsider",
				"send_welcome_email": 0,
				"roles": [{"role": "Blogger"}],
			}
		)
		outsider.flags.ignore_permissions = True
		outsider.insert()

		frappe.set_user(outsider.name)
		# Blogger does not have read access to Sales Invoice.
		with self.assertRaises(frappe.PermissionError):
			query.get_schema("Sales Invoice")

	def test_permission_boundary(self):
		"""A reader cannot write, and a non-reader cannot read."""
		saved = query.save_query(title="Invoice count", operations=COUNT_INVOICES)

		outsider = frappe.get_doc(
			{
				"doctype": "User",
				"email": "nakhoda-query-outsider@example.com",
				"first_name": "outsider",
				"send_welcome_email": 0,
				"roles": [{"role": "Blogger"}],
			}
		)
		outsider.flags.ignore_permissions = True
		outsider.insert()

		frappe.set_user(outsider.name)
		with self.assertRaises(frappe.PermissionError):
			query.get_query(saved["name"])
		with self.assertRaises(frappe.PermissionError):
			query.save_query(name=saved["name"], title="Stolen", operations=COUNT_INVOICES)
		with self.assertRaises(frappe.PermissionError):
			query.delete_query(saved["name"])


if __name__ == "__main__":
	unittest.main()
