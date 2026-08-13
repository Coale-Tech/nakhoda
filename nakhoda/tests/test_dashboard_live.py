# Copyright (c) 2026, Nakhoda and contributors
# For license information, please see license.txt
"""Phase 10 against a real site: `NakhodaIntelligenceTemplate.apply_patch`/
`revert` writing an actual `Nakhoda Dashboard Version` row and persisting
`panels`. The admin gate itself (`frappe.only_for`) is not exercised here:
`frappe.only_for` short-circuits unconditionally whenever `frappe.flags.
in_test` is set (`frappe/__init__.py:only_for`), which `bench run-tests`
sets for the whole run - the same reason no other admin-gated method in this
app (`api/templates.py`'s `_require_admin`) is tested for denial either.

The grammar and diff themselves - the closed op set, the adversarial-prompt
rejection, "removed stays visible" - are already proven site-independent in
`test_dashboard.py`; this file only proves the doctype wiring around them.

Writes are records, never schema; everything inserted here rolls back.
"""

from __future__ import annotations

import unittest

import frappe

DASHBOARD_DOCTYPE = "Nakhoda Intelligence Template"

PANELS = [
	{
		"i": "chart_1",
		"type": "chart",
		"chart_type": "bar",
		"query": "q_ageing",
		"title": "Ageing buckets",
		"layout": {"x": 0, "y": 0, "w": 10, "h": 8},
		"filters": [],
		"removed": False,
	}
]


def connected() -> bool:
	return bool(getattr(frappe, "db", None))


@unittest.skipUnless(connected(), "needs a site: bench --site <site> run-tests --app nakhoda")
class DashboardPatching(unittest.TestCase):
	def setUp(self) -> None:
		frappe.set_user("Administrator")

	def tearDown(self) -> None:
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def make_dashboard(self, panels=None) -> str:
		doc = frappe.get_doc(
			{
				"doctype": DASHBOARD_DOCTYPE,
				"key": "test_dashboard_live",
				"title": "Test Dashboard",
				"panels": frappe.as_json(panels if panels is not None else PANELS),
			}
		).insert(ignore_permissions=True)
		return str(doc.name)

	# -- apply_patch ------------------------------------------------------

	def test_a_valid_patch_persists_new_panels_and_returns_a_diff(self):
		name = self.make_dashboard()
		doc = frappe.get_doc(DASHBOARD_DOCTYPE, name)

		result = doc.apply_patch([{"op": "remove_item", "i": "chart_1"}])

		self.assertEqual(len(result["diff"]), 1)
		self.assertEqual(result["diff"][0]["state"], "removed")
		self.assertTrue(result["version"])

		reloaded = frappe.get_doc(DASHBOARD_DOCTYPE, name)
		panels = frappe.parse_json(reloaded.panels)
		self.assertTrue(panels[0]["removed"])  # stayed on the page, flagged

	def test_apply_patch_writes_a_dashboard_version_snapshot(self):
		name = self.make_dashboard()
		doc = frappe.get_doc(DASHBOARD_DOCTYPE, name)

		result = doc.apply_patch([{"op": "remove_item", "i": "chart_1"}])
		version = frappe.get_doc("Nakhoda Dashboard Version", result["version"])

		self.assertEqual(version.dashboard, name)
		self.assertEqual(version.applied_by, "Administrator")
		self.assertFalse(version.reverted)
		prior = frappe.parse_json(version.prior_panels)
		self.assertEqual(prior, PANELS)  # verbatim, from before the patch

	def test_an_adversarial_op_is_rejected_and_nothing_is_written(self):
		name = self.make_dashboard()
		doc = frappe.get_doc(DASHBOARD_DOCTYPE, name)

		with self.assertRaises(ValueError):
			doc.apply_patch([{"op": "execute_sql", "sql": "DROP TABLE tabSales Invoice"}])

		self.assertEqual(frappe.db.count("Nakhoda Dashboard Version", {"dashboard": name}), 0)
		reloaded = frappe.get_doc(DASHBOARD_DOCTYPE, name)
		self.assertEqual(frappe.parse_json(reloaded.panels), PANELS)  # untouched

	# -- revert -------------------------------------------------------------

	def test_revert_restores_the_prior_panels_verbatim(self):
		name = self.make_dashboard()
		doc = frappe.get_doc(DASHBOARD_DOCTYPE, name)
		result = doc.apply_patch(
			[
				{
					"op": "add_chart",
					"chart_type": "line",
					"query": "q_new",
					"layout": {"x": 0, "y": 8, "w": 10, "h": 8},
				}
			]
		)

		doc = frappe.get_doc(DASHBOARD_DOCTYPE, name)
		doc.revert(result["version"])

		reloaded = frappe.get_doc(DASHBOARD_DOCTYPE, name)
		self.assertEqual(frappe.parse_json(reloaded.panels), PANELS)

		version = frappe.get_doc("Nakhoda Dashboard Version", result["version"])
		self.assertTrue(version.reverted)
		self.assertEqual(version.reverted_by, "Administrator")
		self.assertTrue(version.reverted_on)

	def test_a_version_cannot_be_reverted_twice(self):
		name = self.make_dashboard()
		doc = frappe.get_doc(DASHBOARD_DOCTYPE, name)
		result = doc.apply_patch([{"op": "remove_item", "i": "chart_1"}])

		doc = frappe.get_doc(DASHBOARD_DOCTYPE, name)
		doc.revert(result["version"])

		doc = frappe.get_doc(DASHBOARD_DOCTYPE, name)
		with self.assertRaises(frappe.ValidationError):
			doc.revert(result["version"])

	def test_reverting_a_version_from_another_dashboard_is_rejected(self):
		name_a = self.make_dashboard()
		name_b = self.make_dashboard()
		doc_a = frappe.get_doc(DASHBOARD_DOCTYPE, name_a)
		result = doc_a.apply_patch([{"op": "remove_item", "i": "chart_1"}])

		doc_b = frappe.get_doc(DASHBOARD_DOCTYPE, name_b)
		with self.assertRaises(frappe.ValidationError):
			doc_b.revert(result["version"])


if __name__ == "__main__":
	unittest.main()
