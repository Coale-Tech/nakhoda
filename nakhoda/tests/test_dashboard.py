# Copyright (c) 2026, Nakhoda and contributors
# For license information, please see license.txt
"""Phase 10's two CI gates, `docs/plan/12-build-plan.md` §Phase 10 / gate index
rows "patch previews as a diff..." and "every touched item is named...".

`validate_patch` and `apply_patch` are pure functions of `(panels, ops) ->
(panels, diff)` - they never read the database, resolve a table or execute a
query (`engine/dashboard.py`'s own docstring). That is what lets both gates
run on a bare interpreter, the same discipline `test_operations.py` and
`test_ml.py` apply to the query and ML grammars.

Applying a patch through `Nakhoda Intelligence Template.apply_patch` and
reverting through a real `Nakhoda Dashboard Version` row need a site
(`bench --site <site> run-tests --app nakhoda`) and live in
`test_dashboard_live.py` instead, matching `test_templates.py`'s GateA/GateB
split.
"""

from __future__ import annotations

import unittest

from nakhoda.engine.dashboard import PATCH_OPS, PatchError, apply_patch, validate_patch

EXISTING = [
	{
		"i": "chart_1",
		"type": "chart",
		"chart_type": "bar",
		"query": "q_ageing",
		"title": "Ageing buckets",
		"layout": {"x": 0, "y": 0, "w": 10, "h": 8},
		"filters": [],
		"removed": False,
	},
	{
		"i": "chart_3",
		"type": "chart",
		"chart_type": "bar",
		"query": "q_credit_limit",
		"title": "Top 10 customers by credit limit",
		"layout": {"x": 10, "y": 0, "w": 10, "h": 8},
		"filters": [],
		"removed": False,
	},
]


class Grammar(unittest.TestCase):
	"""The closed op set, and the adversarial-prompt gate it exists for."""

	def test_three_ops_and_no_others(self):
		self.assertEqual(PATCH_OPS, ("add_chart", "set_filter", "remove_item"))

	def test_a_write_or_drop_fails_because_the_grammar_has_no_op_for_it(self):
		# Not a filter catching the string "DROP" - `op` simply is not a member
		# of `PATCH_OPS`, so this is rejected the same way a typo would be.
		for adversarial in (
			{"op": "execute_sql", "sql": "DROP TABLE tabSales Invoice"},
			{"op": "write", "table": "tabSales Invoice", "values": {"grand_total": 0}},
			{"op": "delete_item", "i": "chart_1"},
		):
			with self.assertRaises(PatchError):
				validate_patch([adversarial])

	def test_empty_patch_is_rejected(self):
		with self.assertRaises(PatchError):
			validate_patch([])

	def test_ops_must_be_a_list(self):
		with self.assertRaises(PatchError):
			validate_patch({"op": "remove_item", "i": "chart_1"})


class AddChart(unittest.TestCase):
	def op(self, **overrides):
		base = {
			"op": "add_chart",
			"chart_type": "line",
			"query": "q_collections",
			"layout": {"x": 0, "y": 0, "w": 10, "h": 8},
		}
		base.update(overrides)
		return base

	def test_requires_chart_type_query_and_layout(self):
		for missing in ("chart_type", "query", "layout"):
			op = self.op()
			del op[missing]
			with self.assertRaises(PatchError):
				validate_patch([op])

	def test_layout_needs_exactly_x_y_w_h(self):
		with self.assertRaises(PatchError):
			validate_patch([self.op(layout={"x": 0, "y": 0, "w": 10})])
		with self.assertRaises(PatchError):
			validate_patch([self.op(layout={"x": 0, "y": 0, "w": 10, "h": -1})])

	def test_appends_a_new_item_and_names_it_added_in_the_diff(self):
		new_panels, diff = apply_patch(EXISTING, [self.op(title="Collections forecast")])

		self.assertEqual(len(new_panels), 3)
		added = new_panels[-1]
		self.assertEqual(added["i"], "chart_4")  # next after the highest existing index
		self.assertEqual(added["chart_type"], "line")
		self.assertFalse(added["removed"])

		self.assertEqual(len(diff), 1)
		self.assertEqual(
			diff[0],
			{
				"i": "chart_4",
				"title": "Collections forecast",
				"state": "added",
				"field": "layout",
				"op": "add_chart",
			},
		)


class SetFilter(unittest.TestCase):
	def op(self, **overrides):
		base = {
			"op": "set_filter",
			"i": "chart_1",
			"column": "due_date",
			"operator": "between",
			"value": ["2026-04-01", "2027-03-31"],
		}
		base.update(overrides)
		return base

	def test_unknown_target_item_is_rejected(self):
		with self.assertRaises(PatchError):
			apply_patch(EXISTING, [self.op(i="chart_does_not_exist")])

	def test_unknown_operator_is_rejected(self):
		with self.assertRaises(PatchError):
			validate_patch([self.op(operator="LIKE")])

	def test_between_needs_a_two_element_value(self):
		with self.assertRaises(PatchError):
			validate_patch([self.op(operator="between", value=["2026-04-01"])])

	def test_scopes_the_named_item_and_names_it_will_change_in_the_diff(self):
		new_panels, diff = apply_patch(EXISTING, [self.op()])

		scoped = next(p for p in new_panels if p["i"] == "chart_1")
		self.assertEqual(
			scoped["filters"],
			[{"column": "due_date", "operator": "between", "value": ["2026-04-01", "2027-03-31"]}],
		)
		# the other item is untouched
		untouched = next(p for p in new_panels if p["i"] == "chart_3")
		self.assertEqual(untouched["filters"], [])

		self.assertEqual(len(diff), 1)
		self.assertEqual(diff[0]["i"], "chart_1")
		self.assertEqual(diff[0]["title"], "Ageing buckets")
		self.assertEqual(diff[0]["state"], "will_change")
		self.assertEqual(diff[0]["field"], "filters")

	def test_a_second_filter_on_the_same_column_replaces_rather_than_stacks(self):
		new_panels, _ = apply_patch(EXISTING, [self.op(value=["2026-01-01", "2026-06-30"])])
		new_panels, _ = apply_patch(new_panels, [self.op(value=["2026-04-01", "2027-03-31"])])
		scoped = next(p for p in new_panels if p["i"] == "chart_1")
		self.assertEqual(len(scoped["filters"]), 1)
		self.assertEqual(scoped["filters"][0]["value"], ["2026-04-01", "2027-03-31"])


class RemoveItem(unittest.TestCase):
	def test_unknown_target_item_is_rejected(self):
		with self.assertRaises(PatchError):
			apply_patch(EXISTING, [{"op": "remove_item", "i": "chart_does_not_exist"}])

	def test_the_removed_item_stays_in_panels_flagged_not_deleted(self):
		"""Gate index row "10 - every touched item named...removed items stay
		on the page as `removed`": a patch that silently drops a chart from
		the array is exactly the defect this asserts against."""
		new_panels, diff = apply_patch(EXISTING, [{"op": "remove_item", "i": "chart_3"}])

		self.assertEqual(len(new_panels), len(EXISTING))  # nothing vanished
		removed = next(p for p in new_panels if p["i"] == "chart_3")
		self.assertTrue(removed["removed"])
		self.assertEqual(removed["title"], "Top 10 customers by credit limit")  # title survives

		self.assertEqual(
			diff,
			[
				{
					"i": "chart_3",
					"title": "Top 10 customers by credit limit",
					"state": "removed",
					"field": None,
					"op": "remove_item",
				}
			],
		)


class SplitRevenueByTerritoryAndAddLastYear(unittest.TestCase):
	"""The build-plan's own worked example (`12-build-plan.md` Phase 10 gate):
	a three-op patch - add a chart, re-scope a filter, drop one that no
	longer fits - previews as a diff naming every touched item."""

	def test_three_ops_each_named_in_the_diff(self):
		ops = [
			{
				"op": "add_chart",
				"chart_type": "line",
				"query": "q_revenue_by_territory_last_year",
				"title": "Revenue by territory · last year",
				"layout": {"x": 0, "y": 8, "w": 10, "h": 8},
			},
			{
				"op": "set_filter",
				"i": "chart_1",
				"column": "posting_date",
				"operator": ">=",
				"value": "2025-01-01",
			},
			{"op": "remove_item", "i": "chart_3"},
		]

		new_panels, diff = apply_patch(EXISTING, ops)

		self.assertEqual(len(diff), 3)
		by_state = {row["state"]: row for row in diff}
		self.assertEqual(set(by_state), {"added", "will_change", "removed"})
		for row in diff:
			self.assertTrue(row["i"], "every diff row names its target item")
			self.assertTrue(row["title"], "every diff row names the target's title")

		# nothing shrank - the removal is a flag, three ops in, three items out
		# plus the one added, none vanished
		self.assertEqual(len(new_panels), 3)
		self.assertTrue(next(p for p in new_panels if p["i"] == "chart_3")["removed"])

	def test_applying_never_mutates_the_caller_s_list(self):
		"""What lets `revert` restore `prior_panels` byte-for-byte later: the
		list handed in survives the call untouched, so storing it verbatim
		before the call captures exactly what existed before the patch."""
		import copy

		before = copy.deepcopy(EXISTING)
		apply_patch(EXISTING, [{"op": "remove_item", "i": "chart_1"}])
		self.assertEqual(EXISTING, before)


if __name__ == "__main__":
	unittest.main()
