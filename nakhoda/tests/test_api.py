"""Phase 0: the whitelisted surface, against a real site.

What is specific to this layer, and therefore what is tested here: that the
closed grammar is enforced at the endpoint rather than somewhere behind it, that
a stored pipeline is rejected on save, that the row cap applies, and that the
answer a caller gets is bounded by the caller's own permissions.

The engine's permission behaviour itself is proved elsewhere and deterministically
- `test_permissions.py` drives it from recorded Frappe output against a fixed
DuckDB fixture, because a development site's permissions are whatever they
happen to be today. What this file adds is that the *endpoint* is wired to that
machinery and not around it.

Writes are records, never schema. Everything inserted here rolls back; an
earlier test in this app added a Custom Field, `ALTER TABLE` committed
implicitly, and the column outlived the run on a site with real data.
"""

from __future__ import annotations

import unittest

import frappe

from nakhoda import api

INVOICES = "tabSales Invoice"

#: A pipeline that is valid, cheap and returns rows on any ERPNext site.
COUNT_INVOICES = [
	{"type": "source", "table": INVOICES},
	{"type": "summarize", "measures": [{"name": "n", "expr": {"fn": "count", "args": []}}]},
]

#: The three operations the grammar refuses by design, not by omission.
REFUSED = ["sql", "code", "custom_operation"]


def connected() -> bool:
	return bool(getattr(frappe, "db", None))


@unittest.skipUnless(connected(), "needs a site: bench --site <site> run-tests --app nakhoda")
class Endpoints(unittest.TestCase):
	def setUp(self) -> None:
		frappe.set_user("Administrator")

	def tearDown(self) -> None:
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def make_user(self, email: str, roles: list[str]) -> str:
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": email.split("@")[0],
				"send_welcome_email": 0,
				"roles": [{"role": r} for r in roles],
			}
		)
		user.flags.ignore_permissions = True
		user.insert()
		return str(user.name)

	def make_query(self, operations=None) -> str:
		doc = frappe.get_doc(
			{
				"doctype": "Nakhoda Query",
				"title": "Invoice count",
				"data_source": api.default_source(),
				"operations": frappe.as_json(operations or COUNT_INVOICES),
			}
		).insert()
		return str(doc.name)

	# -- the grammar, at the boundary ---------------------------------------

	def test_refused_operations_never_reach_a_database(self):
		"""`sql`, `code` and `custom_operation` are a standing refusal.

		Insights has all three, which is why its equivalent surface needs a
		trusted caller. Their absence is what lets this endpoint accept a
		pipeline from anyone - including, later, from a model.
		"""
		for kind in REFUSED:
			with self.subTest(kind):
				pipeline = [{"type": "source", "table": INVOICES}, {"type": kind, "raw": "SELECT 1"}]
				report = api.validate(pipeline)
				self.assertFalse(report["valid"])
				self.assertIn(kind, report["error"])
				with self.assertRaises(frappe.ValidationError):
					api.run(pipeline)

	def test_validate_reports_a_refusal_instead_of_raising_it(self):
		"""So an editor - or a model correcting itself - can see the reason."""
		report = api.validate([{"type": "summarize", "measures": []}])
		self.assertFalse(report["valid"])
		self.assertTrue(report["error"])
		self.assertEqual(api.validate(COUNT_INVOICES), {"valid": True, "error": None})

	def test_a_stored_query_is_rejected_on_save(self):
		"""A pipeline that cannot run cannot be stored."""
		with self.assertRaises(frappe.ValidationError):
			self.make_query([{"type": "nonsense"}])

	# -- execution ----------------------------------------------------------

	def test_ad_hoc_pipeline_returns_rows(self):
		result = api.run(COUNT_INVOICES)
		self.assertEqual(result["columns"], ["n"])
		self.assertEqual(result["row_count"], 1)
		self.assertGreater(int(result["rows"][0]["n"]), 0)
		self.assertIn("tabSales Invoice", result["sql"])

	def test_the_row_cap_truncates_and_says_so(self):
		listing = [
			{"type": "source", "table": INVOICES},
			{"type": "select", "columns": [{"name": "name", "expr": {"col": "name"}}]},
		]
		result = api.run(listing, limit=5)
		self.assertEqual(result["row_count"], 5)
		self.assertTrue(result["truncated"])

	def test_a_stored_query_executes_and_records_the_run(self):
		name = self.make_query()
		result = api.execute(name)
		self.assertGreater(int(result["rows"][0]["n"]), 0)

		self.assertTrue(frappe.db.get_value("Nakhoda Query", name, "cache_key"))
		self.assertEqual(frappe.db.get_value("Nakhoda Query", name, "last_row_count"), 1)
		self.assertEqual(frappe.db.get_value("Nakhoda Query", name, "last_executed_by"), "Administrator")

	# -- the boundary -------------------------------------------------------

	def test_a_caller_without_the_role_cannot_execute(self):
		"""The endpoint checks the document, not just the data underneath it."""
		name = self.make_query()
		outsider = self.make_user("nakhoda-outsider@example.com", ["Blogger"])
		frappe.set_user(outsider)
		with self.assertRaises(frappe.PermissionError):
			api.execute(name)

	def test_results_are_bounded_by_the_callers_own_permissions(self):
		"""The same stored query, two callers, and the data decides.

		The restricted user holds `Nakhoda User`, so the app lets them in; they
		hold nothing that grants Sales Invoice, so the engine gives them
		nothing. Both halves are the point - a denial here is zero rows, not an
		exception, and not somebody else's total.
		"""
		name = self.make_query()
		privileged = api.execute(name)
		self.assertGreater(int(privileged["rows"][0]["n"]), 0)

		analyst = self.make_user("nakhoda-analyst@example.com", ["Nakhoda User"])
		self.assertFalse(
			frappe.has_permission("Sales Invoice", "read", user=analyst),
			"this test needs a user who cannot read invoices",
		)

		frappe.set_user(analyst)
		restricted = api.execute(name)
		self.assertEqual(int(restricted["rows"][0]["n"]), 0)

	def test_two_callers_do_not_share_a_cache_entry(self):
		"""Different permissions compile to different SQL, so the key differs.

		This is the property that made a shared cache safe. Without it the
		second caller would be served the first caller's rows - the shape of the
		bug in `insights/api/ml/utils.py:cached_run`.
		"""
		name = self.make_query()
		api.execute(name)
		privileged_key = frappe.db.get_value("Nakhoda Query", name, "cache_key")

		analyst = self.make_user("nakhoda-analyst2@example.com", ["Nakhoda User"])
		frappe.set_user(analyst)
		api.execute(name)
		restricted_key = frappe.db.get_value("Nakhoda Query", name, "cache_key")

		self.assertNotEqual(privileged_key, restricted_key)


if __name__ == "__main__":
	unittest.main()
