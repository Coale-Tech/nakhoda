# Copyright (c) 2026, Nakhoda and contributors
# For license information, please see license.txt
"""Live proof for `get_dashboard_data` - success criterion 1's "renders data"
half. `test_templates.py` proves shipping/versioning; this proves a real
instantiated dashboard actually computes its metrics end to end, through the
same `engine.pipeline.run` every other execution surface uses, against the
real site database (no mocks) - the way `test_agent_live.py` proves the chat
round-trip live rather than through `route`/`providers.complete` mocks.
"""

from __future__ import annotations

import json
import unittest

try:
	import frappe

	from nakhoda.api import templates as api_templates
except ImportError:
	frappe = None
	api_templates = None

DOCTYPE = "Nakhoda Intelligence Template"


def connected() -> bool:
	return bool(getattr(frappe, "db", None))


@unittest.skipUnless(connected(), "needs a site: bench --site <site> run-tests --app nakhoda")
class DashboardData(unittest.TestCase):
	def setUp(self) -> None:
		frappe.set_user("Administrator")

	def tearDown(self) -> None:
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def _data_source(self) -> str:
		existing = frappe.get_all(
			"Nakhoda Data Source", filters={"source_type": "Site Database"}, pluck="name", limit=1
		)
		if existing:
			return existing[0]
		return (
			frappe.get_doc(
				{"doctype": "Nakhoda Data Source", "title": "Site Database", "source_type": "Site Database"}
			)
			.insert(ignore_permissions=True)
			.name
		)

	def _verified_query(self, data_source: str) -> str:
		doc = frappe.get_doc(
			{
				"doctype": "Nakhoda Verified Query",
				"title": "Dashboard data test - all invoices",
				"question": "How many sales invoices are there?",
				"data_source": data_source,
				"operations": json.dumps([{"type": "source", "table": "tabSales Invoice"}]),
			}
		).insert(ignore_permissions=True)
		doc.submit()
		return doc.name

	def _dashboard(self, source: str) -> str:
		"""A real instantiated dashboard, imported the same way the frontend's
		`TemplateGallery.vue` does - `create_intelligence_template` - then wired
		to `source` and given one metric, exactly what an admin does after
		import since every shipped template ships with `source: null`."""
		name = api_templates.create_intelligence_template("nakhoda/sales")["name"]
		doc = frappe.get_doc(DOCTYPE, name)
		doc.source = source
		doc.set(
			"metrics",
			[
				{
					"label": "Invoice Count",
					"expression": json.dumps({"fn": "count", "args": []}),
					"format": "Number",
				}
			],
		)
		doc.save(ignore_permissions=True)
		return name

	def test_instantiated_dashboard_computes_real_metric_values(self) -> None:
		data_source = self._data_source()
		query = self._verified_query(data_source)
		dashboard = self._dashboard(query)

		result = api_templates.get_dashboard_data(dashboard)

		self.assertTrue(result["metrics_available"], result.get("reason"))
		self.assertIsNone(result["reason"])
		self.assertEqual(result["name"], dashboard)
		self.assertEqual(result["title"], "Sales Intelligence")
		self.assertEqual(len(result["metrics"]), 1)
		metric = result["metrics"][0]
		self.assertEqual(metric["label"], "Invoice Count")
		self.assertIsInstance(metric["value"], int)
		self.assertEqual(metric["value"], frappe.db.count("Sales Invoice"))

	def test_a_shipped_template_arrives_wired_and_answers_on_import(self) -> None:
		"""Every `template.json` ships its own `source_query`, so a template is
		answerable the moment it is imported - no hand-linking step. This used
		to be the reverse: templates imported with `source: null` and rendered
		empty panels forever, which is what `_link_source_query` closed."""
		name = api_templates.create_intelligence_template("nakhoda/financial")

		result = api_templates.get_dashboard_data(name["name"])

		self.assertTrue(result["metrics_available"], result.get("reason"))
		self.assertIsNone(result["reason"])
		self.assertTrue(frappe.db.get_value(api_templates.DOCTYPE, name["name"], "source"))
		self.assertTrue(result["metrics"])

	def test_a_dashboard_without_a_source_reports_a_reason_without_throwing(self) -> None:
		"""A dashboard whose source is gone - a query deleted after import, or
		one built by hand in the Desk - still renders its panel layout."""
		name = api_templates.create_intelligence_template("nakhoda/financial")["name"]
		frappe.db.set_value(api_templates.DOCTYPE, name, "source", None)
		frappe.clear_document_cache(api_templates.DOCTYPE, name)

		result = api_templates.get_dashboard_data(name)

		self.assertFalse(result["metrics_available"])
		self.assertEqual(result["reason"], "No source query configured")
		self.assertEqual(result["metrics"], [])
		self.assertTrue(result["panels"])

	def test_unverified_source_reports_reason_without_throwing(self) -> None:
		data_source = self._data_source()
		draft = frappe.get_doc(
			{
				"doctype": "Nakhoda Verified Query",
				"title": "Dashboard data test - draft",
				"question": "Draft, never submitted",
				"data_source": data_source,
				"operations": json.dumps([{"type": "source", "table": "tabSales Invoice"}]),
			}
		).insert(ignore_permissions=True)

		name = api_templates.create_intelligence_template("nakhoda/inventory")["name"]
		doc = frappe.get_doc(DOCTYPE, name)
		doc.source = draft.name
		doc.save(ignore_permissions=True)

		result = api_templates.get_dashboard_data(name)
		self.assertFalse(result["metrics_available"])
		self.assertEqual(result["reason"], "Source query is not verified")


if __name__ == "__main__":
	unittest.main()
