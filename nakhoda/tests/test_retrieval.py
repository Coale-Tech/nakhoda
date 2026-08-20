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

from nakhoda.semantic.retrieval import BUDGET, Index, build_index, context, estimate_tokens
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


#: What each mechanism claims to improve, and therefore what removing it must cost.
#:
#: Recall alone is too coarse to price a scorer. It asks whether every gold table
#: survived selection - pass or fail per question - so it cannot see a mechanism that
#: lifts a gold table from rank 7 to rank 1 while it was being kept either way, and it
#: is blind by construction to packing, which `rank()` never applies. Judged on recall
#: alone this site indicts `PROSE` and `REDUNDANCY`, and both are doing exactly the
#: work they claim: removing `PROSE` costs +0.47 mean gold rank and helps nowhere,
#: removing `REDUNDANCY` takes same-kind duplicate pairs in the selections from 16 to
#: 65. So each mechanism declares its own measure, and is held to that one. Declaring
#: the lenient measure is how decoration would survive, which is why the claim is
#: written here beside the mechanism rather than chosen after seeing the numbers.
CLAIMS = {
	"NAME": "recall",
	"COLUMN": "recall",
	"USAGE": "recall",
	"REPORTED": "recall",
	"PROSE": "rank",
	"REDUNDANCY": "duplicates",
}


def outcomes(index: Index, budget: int = BUDGET) -> dict[str, float]:
	"""The three things a mechanism here can be worth, in one pass over the questions.

	`recall` counts questions keeping every gold table - higher is better. `rank` is the
	mean position of the gold tables in the ranking, and `duplicates` counts pairs of
	selected same-kind tables that mostly repeat each other - lower is better for both,
	so both are negated. One direction for every measure means the test reads the same
	way for all three.
	"""
	recall, ranks, duplicates = 0, [], 0
	for question in Q:
		wanted = gold_tables(question["sql"])
		chosen = index.select(question["q"], budget=budget)
		if wanted <= set(chosen):
			recall += 1

		ranked = [name for name, _ in index.rank(question["q"])]
		found = [ranked.index(t) for t in sorted(wanted) if t in ranked]
		if found:
			ranks.append(sum(found) / len(found))

		for i, first in enumerate(chosen):
			for second in chosen[i + 1 :]:
				a, b = index.tables[first], index.tables[second]
				if a.kind == b.kind and index._redundancy(b, [first]) > 0.5:
					duplicates += 1

	return {
		"recall": recall,
		"rank": -(sum(ranks) / len(ranks)) if ranks else 0.0,
		"duplicates": -duplicates,
	}


#: The words this site's questions use that its schema never says, for the seven
#: documents a curator would reach for first. A fixture, not shipped data: what
#: "revenue" means is a claim about one business, and `semantic/curation.py`
#: deliberately ships no opinion about it - the settings tab exists so a person can.
#:
#: It is here because `CURATED` is the one mechanism whose input is a person rather
#: than the schema, so the mutation test above cannot reach it: on a site where
#: nobody has written anything, zeroing the weight changes nothing and the gate
#: would report a load-bearing mechanism as decoration. This dict is the smallest
#: input that makes the claim measurable.
CURATION = {
	"Sales Invoice": "revenue turnover sold billing topline takings",
	"Sales Invoice Item": "sold revenue line items sold quantity sold",
	"Purchase Invoice": "spend cost purchases payable outgoings",
	"Payment Entry": "paid receipts collections settlement",
	"Item": "product sku goods",
	"Delivery Note": "shipped dispatched",
	"Customer": "client account buyer",
}


def index_with(curated: dict[str, str]) -> Index:
	"""`build_index()`, with a curator's words in place of an empty site.

	Built rather than written: seeding `Nakhoda Semantic Model` rows would leave a
	test's opinions on a real site's documents, and the index is the only thing
	under test here.
	"""
	import frappe

	from nakhoda.semantic import profile

	names = frappe.get_all("DocType", filters={"issingle": 0}, pluck="name")
	return Index(
		(frappe.get_meta(name) for name in names),
		row_counts=profile.row_counts(),
		empty_columns=profile.empty_columns(),
		reports=profile.reporting_counts(),
		curated=curated,
	)


class Retrieval(unittest.TestCase):
	@classmethod
	def setUpClass(cls) -> None:
		# The gate measures the shipped configuration, and the shipped configuration
		# has a column profile: `bench migrate` and the daily job both build one. On a
		# site that has never had either, build it here rather than measure a
		# deployment nobody runs - it is a 68-second scan, once.
		from nakhoda.semantic import profile

		if not profile.empty_columns():
			profile.refresh()
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
		"""The budget is a promise, not a preference: nothing may exceed it.

		Measured twice, on purpose. `cost()` is what `select()` packs against, and
		`context()` is what the model is actually handed; an earlier version of this
		file only checked the first, and the prompt was rendering unpruned columns the
		budget had never been told about.
		"""
		for question in Q:
			with self.subTest(question["id"]):
				chosen = self.index.select(question["q"])
				self.assertLessEqual(self.index.cost(chosen), BUDGET)
				self.assertLessEqual(estimate_tokens(context(chosen, self.index)), BUDGET)

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

		`Item.no_of_months` is labelled "No of Months (Revenue)", which made `Item` the
		top hit for "gross revenue excluding any returns" - above every table that
		records a sale. Prose stays in the index because it sometimes carries the only
		business word a schema has, and it is the only note kind that survived
		measurement: enum domains and link targets were both deleted. It is worth a
		fraction of a name.
		"""
		self.assertLess(Index.PROSE, Index.NAME)
		self.assertLess(Index.PROSE, Index.COLUMN)

	def test_each_mechanism_earns_its_place(self):
		"""Remove one mechanism at a time; what it claims to improve must get worse.

		Weights are set by measurement, so the honest question is not whether the number
		is good but whether each part of the scorer is doing work. Zeroing a weight is
		the mutation: if the outcome it claims survives, the mechanism was never the
		reason and the code should go.

		Eight have gone that way: a weight on link-target words, a currency-column bonus
		gated on an English money lexicon, a bonus for being joinable to an already
		chosen table, a multiplicative pairing of the two priors, a flat ledger prior, a
		metric vocabulary derived from GL accounts, two repairs to packing, and the enum
		domains - which read like controlled vocabulary and measured as workflow states
		hundreds of tables share. See `semantic/retrieval.py` - "What is not here".

		The measure each mechanism answers to is declared in `CLAIMS`, above, not chosen
		here. A single mechanism is allowed to be inert on one measure - `REDUNDANCY`
		cannot move a ranking it is never applied to - but nothing is allowed to be inert
		on the one it exists for.
		"""
		baseline = outcomes(self.index)

		for mechanism, claim in CLAIMS.items():
			with self.subTest(f"{mechanism}/{claim}"):
				original = getattr(Index, mechanism)
				try:
					setattr(Index, mechanism, 0.0)
					crippled = outcomes(self.index)
				finally:
					setattr(Index, mechanism, original)

				self.assertLess(
					crippled[claim],
					baseline[claim],
					f"{mechanism} can be removed without cost to {claim} "
					f"({crippled[claim]} = {baseline[claim]}); it is decoration, delete it",
				)

	def test_pruning_earns_its_place(self):
		"""The same mutation for the input a weight cannot switch off.

		Dropping the columns this site never fills is not a weight, so zeroing cannot
		test it: it changes what every table costs and what words it holds. The
		mutation is to build the index without the profile, which is also exactly what
		a site that has never run `profile.refresh` gets.
		"""
		import frappe

		from nakhoda.semantic import profile

		names = frappe.get_all("DocType", filters={"issingle": 0}, pluck="name")
		unpruned = Index(
			(frappe.get_meta(name) for name in names),
			row_counts=profile.row_counts(),
			reports=profile.reporting_counts(),
		)

		baseline, _ = measure(self.index)
		crippled, lost = measure(unpruned)
		self.assertLess(
			crippled,
			baseline,
			f"pruning can be removed without cost ({crippled} = {baseline})",
		)
		self.assertTrue(lost, "an unpruned index lost nothing, so it lost nothing to prune")

	def test_the_index_is_the_thing_the_model_reads(self):
		"""Retrieval ranks the rendered artifact, so the two cannot disagree.

		A column indexed but not rendered buys recall the model cannot use; a column
		rendered but not indexed is invisible to the search that must find it. One
		artifact, read twice - which is why the render here goes through `context()`,
		the function the manager calls, rather than through `describe` directly.
		"""
		table = self.index.tables["Sales Invoice"]
		rendered = context(["Sales Invoice"], self.index)

		for term in sorted(table.column_terms)[:40]:
			with self.subTest(term):
				self.assertIn(term[:4], rendered.lower())

		# And the other direction, which pruning made possible to get wrong: a column
		# dropped from the index must not reappear in what the model is handed.
		for column in sorted(table.empty)[:20]:
			with self.subTest(f"empty/{column}"):
				self.assertNotIn(f"| {column} |", rendered)


class Curation(unittest.TestCase):
	"""The half of the semantic layer a person writes, held to the same standard.

	Everything in `Retrieval` above measures the derived layer: schema, counts, the
	column profile. This class measures the one input the site cannot supply. Three
	of the forty gold questions ask about "revenue" and "sold", and neither word
	appears in any table's vocabulary on this bench - not in a name, not in a column,
	not in a chart title. Two attempts to derive them were built and deleted (a flat
	ledger prior, a metric vocabulary mined from GL account names; see
	`semantic/retrieval.py` - "What is not here"), which is what makes hand-written
	synonyms a mechanism rather than a convenience.
	"""

	@classmethod
	def setUpClass(cls) -> None:
		from nakhoda.semantic import profile

		if not profile.empty_columns():
			profile.refresh()
		cls.shipped = build_index()
		cls.curated = index_with(CURATION)

	def test_curation_recovers_what_the_schema_cannot_say(self):
		"""Seven documents named by hand, and the gate goes from holding to clearing."""
		before, lost = measure(self.shipped)
		if not lost:
			self.skipTest("this site's schema already answers every question")

		after, still_lost = measure(self.curated)
		self.assertGreater(
			after,
			before,
			f"curation changed nothing ({after} = {before}); it is decoration, delete it",
		)
		self.assertEqual(after, len(Q), f"curation left: {still_lost}")

	def test_the_curated_weight_earns_its_place(self):
		"""The mutation the class-level test cannot run: zero the weight, keep the words.

		This separates the two halves of the mechanism. If recall holds with the weight
		at zero, then the words were reaching the ranking some other way - through
		`vocabulary()` into the name or column term sets - and `CURATED` is a number
		with no job.
		"""
		baseline, _ = measure(self.curated)
		original = Index.CURATED
		try:
			Index.CURATED = 0.0
			crippled, _ = measure(self.curated)
		finally:
			Index.CURATED = original

		self.assertLess(
			crippled,
			baseline,
			f"the curated weight can be zeroed without cost ({crippled} = {baseline})",
		)

	def test_the_weight_is_not_fitted_to_the_benchmark(self):
		"""A tuned weight that only works at its tuned value is a fitted weight.

		Measured on this bench: 0.5 recovers one of the two lost questions, 0.75
		recovers both, and every value from there to 3.0 holds 40/40. The shipped 3.0 -
		equal to `NAME`, because a word a person declares is worth what a word the
		schema declares is worth - therefore sits four times clear of the cliff rather
		than balanced on it. The test asserts the clearance, not the number: at a
		quarter of the shipped weight the gate must still hold. It fails in both
		directions, which is the point - raise the cliff and it catches that too.
		"""
		baseline, _ = measure(self.curated)
		original = Index.CURATED
		try:
			Index.CURATED = original / 4
			reduced, lost = measure(self.curated)
		finally:
			Index.CURATED = original

		self.assertEqual(
			reduced,
			baseline,
			f"CURATED={original / 4} loses {lost}; the shipped {original} is fitted, not clear",
		)


if __name__ == "__main__":
	unittest.main()
