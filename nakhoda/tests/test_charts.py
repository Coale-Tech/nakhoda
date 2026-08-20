"""`agent/charts.py`'s inference rule: a chart is auto-picked from a result's
*shape*, never requested by a pipeline step - `12-build-plan.md`'s Phase 5
chart gate closes on `pick()` returning the right series (or nothing) for
whatever `nakhoda.api.run`/`execute_verified` actually produced.

Pure - `pick()` takes plain columns/rows, no site, no pipeline, no model.
"""

from __future__ import annotations

import unittest

from nakhoda.agent.charts import MAX_BARS, MIN_BARS, annotate, pick

TERRITORY_ROWS = [
	{"territory": "Kenya", "total": 12400000},
	{"territory": "Tanzania", "total": 6100000},
	{"territory": "Uganda", "total": 2950000},
]


class Charts(unittest.TestCase):
	def test_a_label_and_measure_column_produces_a_series(self):
		chart = pick(["territory", "total"], TERRITORY_ROWS)
		self.assertIsNotNone(chart)
		self.assertEqual(
			chart["series"],
			[
				{"label": "Kenya", "value": 12400000.0},
				{"label": "Tanzania", "value": 6100000.0},
				{"label": "Uganda", "value": 2950000.0},
			],
		)

	def test_column_order_does_not_matter(self):
		"""The measure/label roles are discovered from the values, not from
		which column came first in `summarize`'s `by`/`measures` lists."""
		rows = [{"total": r["total"], "territory": r["territory"]} for r in TERRITORY_ROWS]
		chart = pick(["total", "territory"], rows)
		self.assertIsNotNone(chart)
		self.assertEqual(chart["series"][0], {"label": "Kenya", "value": 12400000.0})

	def test_a_scalar_metric_has_nothing_to_chart(self):
		self.assertIsNone(pick(["n"], [{"n": 42}]))

	def test_a_single_row_is_a_metric_not_a_series(self):
		self.assertIsNone(pick(["territory", "total"], TERRITORY_ROWS[:1]))
		self.assertEqual(MIN_BARS, 2)

	def test_too_many_categories_falls_back_to_the_table(self):
		rows = [{"k": str(i), "n": i} for i in range(MAX_BARS + 1)]
		self.assertIsNone(pick(["k", "n"], rows))
		# Exactly at the boundary is still chartable.
		self.assertIsNotNone(pick(["k", "n"], rows[:MAX_BARS]))

	def test_three_columns_is_a_table_not_a_chart(self):
		rows = [{"territory": "Kenya", "channel": "Retail", "total": 100}]
		self.assertIsNone(pick(["territory", "channel", "total"], rows * 2))

	def test_two_numeric_columns_are_ambiguous(self):
		rows = [{"count": 1, "total": 100}, {"count": 2, "total": 200}]
		self.assertIsNone(pick(["count", "total"], rows))

	def test_two_label_columns_have_no_measure(self):
		rows = [{"territory": "Kenya", "channel": "Retail"}, {"territory": "Uganda", "channel": "Online"}]
		self.assertIsNone(pick(["territory", "channel"], rows))

	def test_a_column_mixing_types_across_rows_is_not_a_measure(self):
		"""One row's `total` came back as a string (e.g. a NULL rendered
		oddly upstream) - not a measure column, so no chart rather than a
		bar for a value that cannot be plotted."""
		rows = [{"territory": "Kenya", "total": 100}, {"territory": "Uganda", "total": "n/a"}]
		self.assertIsNone(pick(["territory", "total"], rows))

	def test_booleans_are_not_measures(self):
		"""`bool` is a subclass of `int` in Python; a flag column must not
		be mistaken for something to sum bar heights from."""
		rows = [{"territory": "Kenya", "active": True}, {"territory": "Uganda", "active": False}]
		self.assertIsNone(pick(["territory", "active"], rows))

	def test_null_measure_values_are_not_chartable(self):
		rows = [{"territory": "Kenya", "total": 100}, {"territory": "Uganda", "total": None}]
		self.assertIsNone(pick(["territory", "total"], rows))


FIELDS = {
	"territory": ("Link", "Territory"),
	"grand_total": ("Currency", "Grand Total"),
	"voucher_no": ("Data", "Voucher No"),
	"posting_date": ("Date", "Posting Date"),
	"notes": ("Text Editor", "Notes"),
	"idx": ("Int", "Index"),
}

SUMMARIZED = [
	{"type": "source", "table": "tabSales Invoice"},
	{
		"type": "summarize",
		"by": [{"name": "territory", "expr": {"col": "territory"}}],
		"measures": [
			{"name": "total", "expr": {"fn": "sum", "args": [{"col": "grand_total"}]}},
			{"name": "invoices", "expr": {"fn": "count_distinct", "args": [{"col": "voucher_no"}]}},
		],
	},
]


class Semantics(unittest.TestCase):
	"""`annotate()` - the half of the flint bridge that needs no site. What it
	*omits* is as load-bearing as what it maps: an absent semantic type makes
	flint infer from values, a wrong one makes it draw the wrong chart."""

	def test_a_declared_fieldtype_carries_its_meaning_and_its_label(self):
		types, display = annotate(["posting_date"], FIELDS)
		self.assertEqual(types, {"posting_date": "Date"})
		self.assertEqual(display, {"posting_date": "Posting Date"})

	def test_an_aggregate_inherits_its_argument_but_not_its_label(self):
		"""`sum(grand_total)` is an `Amount`, and "Grand Total" is the wrong
		axis title for a total across many rows."""
		types, display = annotate(["total"], FIELDS, SUMMARIZED)
		self.assertEqual(types, {"total": "Amount"})
		self.assertEqual(display, {})

	def test_counting_beats_the_column_it_counted(self):
		"""`count_distinct(voucher_no)` counts things; it is not a `Name`."""
		types, _ = annotate(["invoices"], FIELDS, SUMMARIZED)
		self.assertEqual(types, {"invoices": "Count"})

	def test_a_group_key_resolves_through_its_own_fieldname(self):
		types, display = annotate(["territory"], FIELDS, SUMMARIZED)
		self.assertEqual(types, {"territory": "Name"})
		self.assertEqual(display, {"territory": "Territory"})

	def test_an_unmapped_fieldtype_is_absent_rather_than_guessed(self):
		types, display = annotate(["notes"], FIELDS)
		self.assertEqual(types, {})
		# The label is still worth handing over - only the *type* is unknown.
		self.assertEqual(display, {"notes": "Notes"})

	def test_an_unresolvable_column_is_omitted(self):
		self.assertEqual(annotate(["mystery"], FIELDS, SUMMARIZED), ({}, {}))

	def test_int_is_a_number_not_a_count(self):
		"""`idx` is an `Int` that counts nothing."""
		types, _ = annotate(["idx"], FIELDS)
		self.assertEqual(types, {"idx": "Number"})

	def test_a_later_summarize_shadows_an_earlier_one(self):
		ops = [
			*SUMMARIZED,
			{
				"type": "summarize",
				"by": [],
				"measures": [{"name": "total", "expr": {"fn": "count", "args": [{"col": "territory"}]}}],
			},
		]
		types, _ = annotate(["total"], FIELDS, ops)
		self.assertEqual(types, {"total": "Count"})


if __name__ == "__main__":
	unittest.main()
