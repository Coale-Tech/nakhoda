"""Phase 3: a governed answer, against a real site.

Gate A is the whole of this file's claim: an unapproved query is not servable,
approval is a Frappe `submit` permission rather than a flag this app
interprets, and an answer sourced from a verified query says so. Gate B
(the agent preferring a verified query over generating SQL) cannot be tested
until Phase 4 exists - it is exercised there, against this behaviour.

Writes are records, never schema; everything inserted here rolls back.
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


def connected() -> bool:
	return bool(getattr(frappe, "db", None))


@unittest.skipUnless(connected(), "needs a site: bench --site <site> run-tests --app nakhoda")
class VerifiedQuery(unittest.TestCase):
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

	def make_verified_query(self, operations=None, submit: bool = False) -> str:
		doc = frappe.get_doc(
			{
				"doctype": "Nakhoda Verified Query",
				"title": "Invoice count",
				"question": "How many invoices are there?",
				"data_source": api.default_source(),
				"operations": frappe.as_json(operations or COUNT_INVOICES),
			}
		).insert()
		if submit:
			doc.submit()
			doc.reload()
		return str(doc.name)

	# -- Gate A: governance --------------------------------------------------

	def test_a_stored_pipeline_is_rejected_on_save(self):
		"""Same grammar as `Nakhoda Query` - a query that cannot run cannot be stored."""
		with self.assertRaises(frappe.ValidationError):
			self.make_verified_query([{"type": "nonsense"}])

	def test_a_draft_query_is_not_servable(self):
		"""Gate A's core claim: unapproved means unservable, unconditionally."""
		name = self.make_verified_query()
		with self.assertRaises(frappe.PermissionError):
			api.execute_verified(name)

	def test_a_cancelled_query_is_not_servable(self):
		"""Withdrawal turns an answer back off, the same way non-approval does."""
		name = self.make_verified_query(submit=True)
		api.execute_verified(name)  # sanity: it answers while submitted

		doc = frappe.get_doc("Nakhoda Verified Query", name)
		doc.cancel()
		with self.assertRaises(frappe.PermissionError):
			api.execute_verified(name)

	def test_authorship_and_approval_are_different_permissions(self):
		"""`Nakhoda User` can draft; only an admin role can submit.

		This is what makes approval a Frappe permission rather than a button
		this app chooses to hide: `doc.submit()` is refused by Frappe core, not
		by any check this app wrote.
		"""
		source = api.default_source()
		author = self.make_user("nakhoda-author@example.com", ["Nakhoda User"])
		frappe.set_user(author)
		doc = frappe.get_doc(
			{
				"doctype": "Nakhoda Verified Query",
				"title": "Invoice count",
				"question": "How many invoices are there?",
				"data_source": source,
				"operations": frappe.as_json(COUNT_INVOICES),
			}
		).insert()

		with self.assertRaises(frappe.PermissionError):
			doc.submit()

	def test_submit_records_who_and_when(self):
		name = self.make_verified_query(submit=True)
		doc = frappe.get_doc("Nakhoda Verified Query", name)
		self.assertEqual(doc.verified_by, "Administrator")
		self.assertTrue(doc.verified_on)

	# -- the labelled answer --------------------------------------------------

	def test_a_verified_answer_says_so(self):
		"""§Gate A's second half: a served answer is labelled, not just allowed."""
		name = self.make_verified_query(submit=True)
		result = api.execute_verified(name)
		self.assertEqual(result["source"], "verified")
		self.assertEqual(result["question"], "How many invoices are there?")
		self.assertEqual(result["verified_by"], "Administrator")
		self.assertGreater(int(result["rows"][0]["n"]), 0)

	def test_execution_is_recorded(self):
		name = self.make_verified_query(submit=True)
		api.execute_verified(name)
		self.assertTrue(frappe.db.get_value("Nakhoda Verified Query", name, "cache_key"))
		self.assertEqual(
			frappe.db.get_value("Nakhoda Verified Query", name, "last_executed_by"), "Administrator"
		)

	# -- the boundary, unchanged from `Nakhoda Query` --------------------------

	def test_results_are_still_bounded_by_the_callers_own_permissions(self):
		"""Verification governs *whether* an answer is served, not *what* it can see.

		The permission-injection engine is unmoved by approval status - the
		same stored, verified query still returns zero rows to a caller who
		cannot read the underlying table.
		"""
		name = self.make_verified_query(submit=True)
		privileged = api.execute_verified(name)
		self.assertGreater(int(privileged["rows"][0]["n"]), 0)

		analyst = self.make_user("nakhoda-verified-analyst@example.com", ["Nakhoda User"])
		self.assertFalse(
			frappe.has_permission("Sales Invoice", "read", user=analyst),
			"this test needs a user who cannot read invoices",
		)

		frappe.set_user(analyst)
		restricted = api.execute_verified(name)
		self.assertEqual(int(restricted["rows"][0]["n"]), 0)


if __name__ == "__main__":
	unittest.main()
