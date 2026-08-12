"""Phase 1, Gate A (scale): retrieval finds the right tables inside the budget.

The semantic layer is only worth what a model can be shown of it. On this bench the
1,011 non-single DocTypes render to 187,242 tokens, and the layer that measured 95.8%
execution accuracy was 7,843 - a 24x cut. Something has to choose, and if it chooses
wrong the accuracy number belongs to a hand-picked eight-table file rather than to
the app. This gate makes the choice answerable: for at least 90% of the forty gold
questions, every table the gold SQL touches must survive selection, under the same
budget that produced the measured result.

Live only, and deliberately so. Retrieval is the one part of the semantic layer whose
difficulty is a property of the *site*: eight tables always fit, and 1,011 tables with
this site's custom fields, its dead DocTypes and its 103,736-row `Customer
Requisition` are what make ranking hard. An offline fixture would grade an easier
problem than the one that ships.

`test_each_mechanism_earns_its_place` is the load-bearing one. The scorer is tuned -
five weights, chosen by measuring - and a tuned scorer is the shape of thing that
passes its benchmark for the wrong reason. So each mechanism is switched off in turn
and recall must fall. A mechanism that can be removed without cost is not evidence,
it is decoration, and this test deletes it.

Needs a site:

    bench --site <site> run-tests --app nakhoda --module nakhoda.tests.test_retrieval
"""

from __future__ import annotations

import unittest

import sqlglot
from sqlglot import exp

from nakhoda.semantic.retrieval import BUDGET, Index, build_index
from nakhoda.tests.semantic_bench.questions import Q

#: The gate. Below this, retrieval is the accuracy ceiling rather than the layer.
GATE = 0.90


def gold_tables(sql: str) -> set[str]:
	"""The DocTypes the gold answer reads, from the gold SQL itself.

	Derived, never declared. A hand-written list of expected tables per question is
	a second place for the truth to live, and it would drift from the SQL that the
	engine gate runs.
	"""
	parsed = sqlglot.parse_one(sql, dialect="duckdb")
	return {t.name.removeprefix("tab") for t in parsed.find_all(exp.Table)}


def measure(index: Index, budget: int = BUDGET) -> tuple[int, list[str]]:
	"""How many questions keep all their tables, and which do not."""
	kept, lost = 0, []
	for question in Q:
		wanted = gold_tables(question["sql"])
		got = set(index.select(question["q"], budget=budget))
		if wanted <= got:
			kept += 1
		else:
			lost.append(f"{question['id']} missing {sorted(wanted - got)}")
	return kept, lost


class Retrieval(unittest.TestCase):
	@classmethod
	def setUpClass(cls) -> None:
		cls.index = build_index()

	def test_recall_clears_the_gate(self):
		"""Nine questions in ten keep every table their answer needs."""
		kept, lost = measure(self.index)
		self.assertGreaterEqual(
			kept / len(Q),
			GATE,
			f"recall {kept}/{len(Q)} below {GATE:.0%}; lost: {lost}",
		)

	def test_every_selection_fits_the_budget(self):
		"""The budget is a promise, not a preference: nothing may exceed it."""
		for question in Q:
			with self.subTest(question["id"]):
				chosen = self.index.select(question["q"])
				self.assertLessEqual(self.index.cost(chosen), BUDGET)

	def test_a_child_never_arrives_without_its_parent(self):
		"""`parent` is an opaque key. A child table alone cannot be joined to anything."""
		for question in Q:
			chosen = self.index.select(question["q"])
			for name in chosen:
				table = self.index.tables[name]
				if table.is_child:
					with self.subTest(f"{question['id']}/{name}"):
						self.assertTrue(
							set(table.parents) & set(chosen),
							f"{name} selected with no parent among {chosen}",
						)

	def test_an_unused_table_never_outranks_a_used_one_it_mirrors(self):
		"""This site has never written a `POS Invoice`, so it cannot answer about one.

		The concrete case that motivated the usage prior: `POS Invoice` is a near
		copy of `Sales Invoice`, matches every invoice question about as well, and
		was consuming 2,138 tokens of budget on a business that has never used it.
		"""
		if self.index.tables["POS Invoice"].rows:
			self.skipTest("this site does use POS Invoice")

		ranked = dict(self.index.rank("How many invoices have been fully paid?"))
		self.assertLess(ranked["POS Invoice"], ranked["Sales Invoice"])

	def test_a_prose_match_never_beats_a_name_match(self):
		"""Labels and descriptions are free text, and free text lies.

		`Item.no_of_months` is labelled "No of Months (Revenue)", which made `Item`
		the top hit for "gross revenue excluding any returns" - above every table
		that records a sale. Prose stays in the index because it sometimes carries
		the only business word a schema has, but it is worth a fraction of a name.
		"""
		self.assertLess(Index.PROSE, Index.NAME)
		self.assertLess(Index.PROSE, Index.COLUMN)

	def test_each_mechanism_earns_its_place(self):
		"""Switch off one mechanism at a time; recall must fall.

		Weights are set by measurement, so the honest question is not whether the
		number is good but whether each part of the scorer is doing work. Zeroing a
		weight is the mutation: if recall survives it, the mechanism was never the
		reason and the code should go.

		It has gone three times. A weight on link-target words, a currency-column
		bonus gated on an English money lexicon, and a bonus for being joinable to an
		already-chosen table all failed this test, and deleting all three took recall
		from 90.0% to 92.5%. Any mechanism added here must beat that bar.
		"""
		baseline, _ = measure(self.index)

		for mechanism in ("NAME", "ENUM", "COLUMN", "PROSE", "USAGE", "REDUNDANCY"):
			with self.subTest(mechanism):
				original = getattr(Index, mechanism)
				try:
					setattr(Index, mechanism, 0.0)
					crippled, _ = measure(self.index)
				finally:
					setattr(Index, mechanism, original)

				self.assertLess(
					crippled,
					baseline,
					f"{mechanism} can be removed without cost ({crippled} = {baseline})",
				)

	def test_the_index_is_the_thing_the_model_reads(self):
		"""Retrieval ranks the rendered artifact, so the two cannot disagree.

		A column indexed but not rendered buys recall the model cannot use; a column
		rendered but not indexed is invisible to the search that must find it. One
		artifact, read twice.
		"""
		import frappe

		from nakhoda.semantic.model import describe, render

		table = self.index.tables["Sales Invoice"]
		rendered = render([describe(frappe.get_meta("Sales Invoice"))])

		for term in sorted(table.column_terms)[:40]:
			with self.subTest(term):
				self.assertIn(term[:4], rendered.lower())


if __name__ == "__main__":
	unittest.main()
