# Copyright (c) 2026, Nakhoda and contributors
# For license information, please see license.txt
"""The 205-question set is what it says it is.

A question set is data, and data rots quietly: an id repeats, a gold query
returns nothing on the current fixture, a "cross-module" question turns out to
read one table. None of that fails loudly at run time - it produces a number,
and the number looks fine. These are the claims the set makes about itself,
each one written so that a plausible edit breaks it.

The claim that matters most is that the frozen forty are carried unedited.
`10-eval-methodology.md` reports 95.8% on them; if extending the set is allowed
to also revise them, the two figures stop being comparable and the published one
quietly becomes unreproducible. `test_frozen_questions_are_carried_verbatim`
compares text and SQL byte for byte against the module that shipped them.

Needs `duckdb` and the fixture. Build it first:

    python -m nakhoda.bench.fixture
"""

from __future__ import annotations

import collections
import re
import unittest
from pathlib import Path

from nakhoda.bench import fixture
from nakhoda.bench.grade import ORDERED
from nakhoda.bench.questions import Q
from nakhoda.tests.semantic_bench.questions import Q as FROZEN

DB = Path("/tmp/nakhoda-fixture/erp.duckdb")


def _available() -> bool:
	try:
		import duckdb

		del duckdb
	except ImportError:
		return False
	return DB.exists()


def _norm(text: str) -> str:
	return " ".join(re.sub(r"[^a-z0-9 ]", " ", text.lower()).split())


def _documented_traps() -> set[str]:
	"""Trap names described in either module's docstring, `name - meaning`."""
	import nakhoda.bench.questions as new
	import nakhoda.tests.semantic_bench.questions as old

	pattern = r"^\s+(\w+)\s+-\s+\S"
	return {m for doc in (new.__doc__ or "", old.__doc__ or "") for m in re.findall(pattern, doc, re.M)}


class Shape(unittest.TestCase):
	"""Claims that need no database."""

	def test_ids_are_unique_and_the_new_ones_are_contiguous(self):
		"""A repeated id silently drops a question: the grader keys gold by it."""
		ids = [q["id"] for q in Q]
		self.assertEqual(len(set(ids)), len(ids))
		new = sorted(i for i in ids if i not in {q["id"] for q in FROZEN})
		self.assertEqual(new, [f"q{i:03d}" for i in range(41, 41 + len(new))])

	def test_frozen_questions_are_carried_verbatim(self):
		"""The published 95.8% is over these forty. Extending the set must not
		edit them, or the two numbers are of different things."""
		carried = {q["id"]: q for q in Q}
		for original in FROZEN:
			with self.subTest(original["id"]):
				here = carried[original["id"]]
				self.assertEqual(here["q"], original["q"])
				self.assertEqual(here["sql"], original["sql"])
				self.assertEqual(here["trap"], original["trap"])

	def test_frozen_ordering_comes_from_the_grader_not_a_second_opinion(self):
		"""`ordered` is written per question now, but re-deciding it for the
		forty could disagree with the run this set extends."""
		for q in Q:
			if q["id"] in {f["id"] for f in FROZEN}:
				with self.subTest(q["id"]):
					self.assertEqual(q["ordered"], q["id"] in ORDERED)

	def test_every_question_carries_every_key(self):
		"""`ordered` missing reads as False, which silently stops checking a
		ranking the question asked for."""
		for q in Q:
			with self.subTest(q["id"]):
				self.assertEqual(sorted(q), ["id", "module", "ordered", "q", "sql", "trap"])
				self.assertIsInstance(q["ordered"], bool)
				self.assertTrue(q["q"].strip() and q["sql"].strip())

	def test_no_question_is_asked_twice(self):
		"""Two phrasings of one question inflate n without adding evidence."""
		seen: dict[str, str] = {}
		for q in Q:
			key = _norm(q["q"])
			self.assertNotIn(key, seen, f"{q['id']} repeats {seen.get(key)}")
			seen[key] = q["id"]

	def test_a_ranking_question_has_gold_that_fixes_the_ranking(self):
		"""`ordered=True` tells the grader to compare row order. Gold without an
		ORDER BY leaves that order up to the engine, so the check is a coin toss."""
		for q in Q:
			if q["ordered"]:
				with self.subTest(q["id"]):
					self.assertIn("order by", q["sql"].lower())

	def test_every_trap_in_use_is_documented(self):
		"""An undocumented trap name is a category nobody can interpret."""
		used = {q["trap"] for q in Q}
		self.assertEqual(used - _documented_traps(), set())

	def test_the_set_spans_at_least_three_modules(self):
		"""The build plan asks for breadth across modules, not a longer list of
		Selling questions."""
		counts = collections.Counter(q["module"] for q in Q)
		self.assertGreaterEqual(len(counts), 3)
		for module, n in counts.items():
			with self.subTest(module):
				self.assertGreaterEqual(n, 20)

	def test_cross_module_questions_actually_cross(self):
		"""The label is the only thing making these questions interesting; if a
		query reads one module the label is decoration."""
		groups = {module: {f"tab{name}" for name in names} for module, names in fixture.MODULES.items()}
		for q in Q:
			if q["module"] != "cross":
				continue
			with self.subTest(q["id"]):
				touched = {m for m, tables in groups.items() if any(t in q["sql"] for t in tables)}
				self.assertGreaterEqual(len(touched), 2, f"reads only {touched}")

	def test_single_module_questions_read_their_own_module(self):
		"""A question filed under Stock that never touches a Stock table is
		mis-filed, and the per-module accuracy it feeds is wrong."""
		for q in Q:
			if q["module"] == "cross":
				continue
			tables = [f"tab{name}" for name in fixture.MODULES[q["module"].title()]]
			with self.subTest(q["id"]):
				self.assertTrue(any(t in q["sql"] for t in tables))


@unittest.skipUnless(_available(), "needs duckdb and the fixture")
class Gold(unittest.TestCase):
	"""Claims that need the database the questions are asked about."""

	@classmethod
	def setUpClass(cls) -> None:
		import duckdb

		cls.con = duckdb.connect(str(DB), read_only=True)

	@classmethod
	def tearDownClass(cls) -> None:
		cls.con.close()

	def test_every_gold_query_runs(self):
		"""Gold that raises is graded as a question nobody can pass."""
		for q in Q:
			with self.subTest(q["id"]):
				self.con.execute(q["sql"]).df()

	def test_no_gold_answer_is_empty(self):
		"""An empty result is passed by any query that also returns nothing,
		including one that filtered everything away by accident."""
		for q in Q:
			with self.subTest(q["id"]):
				self.assertGreater(len(self.con.execute(q["sql"]).df()), 0)

	def test_enough_answers_are_more_than_one_row(self):
		"""A single scalar can be hit by luck. The set is only as discriminating
		as the share of questions whose shape has to be right too."""
		multi = sum(1 for q in Q if len(self.con.execute(q["sql"]).df()) > 1)
		self.assertGreater(multi, len(Q) // 3)


if __name__ == "__main__":
	unittest.main()
