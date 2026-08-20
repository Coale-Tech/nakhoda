# Copyright (c) 2026, Nakhoda and contributors
# For license information, please see license.txt
"""The harness measured against the run it replaces.

A reimplemented grader is only worth having if it is the same grader. The
archived 240 generations go back through this one and every published figure has
to come out: 78.3% and 95.8%, all six per-model cells, the failure-mode split and
McNemar's p. Anything else means the number in `00-REPORT.md` §6.0 and the number
CI will print are not the same measurement.

The Operation JSON path is checked the other way round - against the forty
hand-written gold pipelines, which `test_engine.py` already proves row-identical
to the gold SQL. They must grade 40/40 through the model path. Until that holds,
a model scoring badly on pipelines could mean the model is bad or the harness is,
and those are not distinguishable from the outside.
"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from nakhoda.bench import driver
from nakhoda.bench import grade as grading

FIXTURE = Path("/tmp/semantic-bench/erp.duckdb")
BENCH = Path(__file__).resolve().parent / "semantic_bench"


def _available() -> bool:
	try:
		import duckdb
		import ibis
	except ImportError:
		return False
	return FIXTURE.exists()


def _archived() -> list[dict]:
	"""`generated.json` in the shape this harness records."""
	return [
		{
			"qid": g["qid"],
			"arm": g["ctx"],
			"target": "sql",
			"tier": g["model"],
			"artifact": g["sql"] or None,
			"err": g["err"],
		}
		for g in json.loads((BENCH / "generated.json").read_text())
	]


class Grader(unittest.TestCase):
	"""Same inputs, same verdicts, or it is a different metric."""

	@classmethod
	def setUpClass(cls) -> None:
		if not _available():
			raise unittest.SkipTest(f"needs the DuckDB fixture at {FIXTURE}")
		import duckdb
		import ibis

		from nakhoda.tests.semantic_bench.questions import Q

		cls.con = duckdb.connect(str(FIXTURE), read_only=True)
		cls.ibis_con = ibis.duckdb.connect(str(FIXTURE), read_only=True)
		cls.questions = Q
		cls.gold = {q["id"]: cls.con.execute(q["sql"]).df() for q in Q}
		cls.graded = grading.grade(_archived(), cls.gold, cls.con, cls.ibis_con.table)

	@classmethod
	def tearDownClass(cls) -> None:
		cls.con.close()

	def _cell(self, **kw) -> list[dict]:
		return [r for r in self.graded if all(r[k] == v for k, v in kw.items())]

	def _passes(self, **kw) -> int:
		return sum(r["status"] == "pass" for r in self._cell(**kw))

	def test_headline_figures_reproduce(self):
		"""78.3% raw DDL, 95.8% semantic layer - the whole of §6.0's claim."""
		self.assertEqual(self._passes(arm="A_raw"), 94)
		self.assertEqual(self._passes(arm="B_semantic"), 115)

	def test_every_per_model_cell_reproduces(self):
		"""The six cells behind the headline, not just their total."""
		expected = {
			("A_raw", "smol"): 21,
			("A_raw", "default"): 38,
			("A_raw", "slow"): 35,
			("B_semantic", "smol"): 38,
			("B_semantic", "default"): 40,
			("B_semantic", "slow"): 37,
		}
		got = {(arm, tier): self._passes(arm=arm, tier=tier) for arm, tier in expected}
		self.assertEqual(got, expected)

	def test_failure_modes_reproduce(self):
		"""A grader can hit the right total by failing different questions."""

		def modes(arm):
			out: dict[str, int] = {}
			for r in self._cell(arm=arm):
				out[r["status"]] = out.get(r["status"], 0) + 1
			return out

		self.assertEqual(modes("A_raw"), {"pass": 94, "wrong_values": 26})
		self.assertEqual(modes("B_semantic"), {"pass": 115, "error": 1, "wrong_values": 4})

	def test_mcnemar_reproduces_the_published_p(self):
		"""p = 1.9e-05, on the same discordant pairs."""
		b, c, n = grading.paired(self._cell(arm="B_semantic"), self._cell(arm="A_raw"))
		self.assertEqual(n, 120)
		self.assertAlmostEqual(grading.mcnemar_exact(b, c), 1.9e-05, places=6)

	def test_gold_pipelines_grade_as_pass(self):
		"""The Operation JSON path, on answers already known to be right.

		Forty pipelines that `test_engine.py` proves row-identical to the gold
		SQL must score 40/40 here. A miss is the harness, not a model.
		"""
		from nakhoda.tests.gold_pipelines import PIPELINES

		records = [
			{
				"qid": qid,
				"arm": "B_semantic",
				"target": "ops",
				"tier": "default",
				"artifact": ops,
				"err": None,
			}
			for qid, ops in PIPELINES.items()
		]
		graded = grading.grade(records, self.gold, self.con, self.ibis_con.table)
		failures = [(r["qid"], r["status"], r["detail"]) for r in graded if r["status"] != "pass"]
		self.assertEqual(failures, [], f"{len(failures)}/40 gold pipelines did not grade as pass")

	def test_every_rule_the_prompt_states_is_one_the_engine_enforces(self):
		"""The RULES block is hand-written; these keep it honest.

		A constraint the engine enforces and the prompt omits shows up as a
		cluster of identical errors in a run - that is how the join name
		collision was found, 15 failures across 10 questions. The inverse is
		invisible: a rule the engine does not have costs the model tokens and
		accuracy forever, and no measurement reveals it. So each rule is pinned
		to a pipeline that must be rejected.
		"""
		from nakhoda.engine.operations import compile_pipeline

		count = {"fn": "count", "args": []}
		violations = {
			"select cannot aggregate": [
				{"type": "source", "table": "tabCustomer"},
				{"type": "select", "columns": [{"name": "n", "expr": count}]},
			],
			"measures must aggregate": [
				{"type": "source", "table": "tabCustomer"},
				{"type": "summarize", "measures": [{"name": "n", "expr": {"col": "name"}}]},
			],
			"by keys must not aggregate": [
				{"type": "source", "table": "tabCustomer"},
				{
					"type": "summarize",
					"by": [{"name": "k", "expr": count}],
					"measures": [{"name": "n", "expr": count}],
				},
			],
			"filter cannot filter on an aggregate": [
				{"type": "source", "table": "tabCustomer"},
				{"type": "filter", "where": {"fn": "gt", "args": [count, {"lit": 1}]}},
			],
			"summarize closes scope": [
				{"type": "source", "table": "tabCustomer"},
				{"type": "summarize", "measures": [{"name": "n", "expr": count}]},
				{"type": "select", "columns": [{"name": "t", "expr": {"col": "territory"}}]},
			],
			"join names must not already be in scope": [
				{"type": "source", "table": "tabSales Invoice Item"},
				{
					"type": "join",
					"table": "tabSales Invoice",
					"left_on": {"col": "parent"},
					"right_on": {"col": "name"},
					"select": [{"name": "docstatus", "expr": {"col": "docstatus"}}],
				},
			],
			"date_trunc unit is a literal": [
				{"type": "source", "table": "tabSales Invoice"},
				{
					"type": "select",
					"columns": [
						{
							"name": "m",
							"expr": {
								"fn": "date_trunc",
								"args": [{"col": "status"}, {"col": "posting_date"}],
							},
						}
					],
				},
			],
		}
		for rule, ops in violations.items():
			with self.subTest(rule):
				with self.assertRaises(Exception):
					compile_pipeline(ops, self.ibis_con.table).to_pandas()


class Baseline(unittest.TestCase):
	"""The committed run, replayed end to end.

	`bench_baseline.jsonl` is 240 real completions keyed by prompt hash. Replaying
	them exercises everything downstream of the model - the prompt, extraction,
	compilation of Operation JSON, execution and grading - for no API spend, which
	is what lets CI run this on every commit.

	It is also the tripwire for the prompt. Change a word of the grammar and the
	hashes stop matching, the replay raises, and the numbers below have to be
	re-earned against models rather than quietly inherited.
	"""

	@classmethod
	def setUpClass(cls) -> None:
		if not _available():
			raise unittest.SkipTest(f"needs the DuckDB fixture at {FIXTURE}")
		import duckdb
		import ibis

		from nakhoda.bench import models
		from nakhoda.tests.semantic_bench.questions import Q

		contexts = {"B_semantic": (BENCH / "context_b.txt").read_text()}
		prompts = driver.plan(Q, contexts)
		generate = models.replay(Path(__file__).resolve().parent / "bench_baseline.jsonl")
		records = models.run(prompts, generate, workers=1)

		cls.con = duckdb.connect(str(FIXTURE), read_only=True)
		ibis_con = ibis.duckdb.connect(str(FIXTURE), read_only=True)
		gold = {q["id"]: cls.con.execute(q["sql"]).df() for q in Q}
		cls.graded = grading.grade(records, gold, cls.con, ibis_con.table)

	@classmethod
	def tearDownClass(cls) -> None:
		cls.con.close()

	def _passes(self, target: str) -> int:
		return sum(r["status"] == "pass" for r in self.graded if r["target"] == target)

	def test_both_targets_hold_their_measured_accuracy(self):
		"""112/120 each. A drop is a regression in retrieval, the engine or the
		grader - the model is frozen, so it cannot be the model."""
		self.assertEqual(self._passes("sql"), 112)
		self.assertEqual(self._passes("ops"), 112)

	def test_operation_json_still_tracks_sql(self):
		"""The §9 finding, as a gate: the product's generation target costs
		nothing against the one the benchmark measured."""
		sql = [r for r in self.graded if r["target"] == "sql"]
		ops = [r for r in self.graded if r["target"] == "ops"]
		b, c, n = grading.paired(ops, sql)
		self.assertEqual(n, 120)
		self.assertGreater(grading.mcnemar_exact(b, c), 0.05)

	def test_accuracy_clears_the_phase_2_gate(self):
		"""≥90.6% - the Wilson lower bound of the offline prototype's 115/120.

		The build plan sets this instead of Databricks' published 80% because
		raw DDL alone scored 78.3% [70.1, 84.8]: an 80% result cannot be told
		apart from having no semantic layer at all.
		"""
		for target in ("sql", "ops"):
			with self.subTest(target):
				self.assertGreaterEqual(100 * self._passes(target) / 120, 90.6)


class Metric(unittest.TestCase):
	"""The parts of the metric that hold without a database."""

	def test_ordered_set_matches_the_frozen_grader(self):
		"""Ten questions demand a ranking. The frozen script says which."""
		source = (BENCH / "grade.py").read_text()
		frozen = re.search(r"ORDERED = \{(.*?)\}", source, re.S)
		if frozen is None:
			self.fail("the frozen grader no longer declares ORDERED")
		self.assertEqual(set(re.findall(r"q\d+", frozen.group(1))), set(grading.ORDERED))

	def test_ordered_is_not_the_derivable_set(self):
		"""Guards the reason ORDERED is copied rather than computed.

		Seventeen gold queries sort; ten questions ask to. If those ever coincide
		the comment above ORDERED is wrong and someone should delete it.
		"""
		from nakhoda.tests.semantic_bench.questions import Q

		sorts = {q["id"] for q in Q if "order by" in q["sql"].lower()}
		self.assertLess(len(grading.ORDERED), len(sorts))
		self.assertTrue(grading.ORDERED < sorts)

	def test_wilson_brackets_the_estimate(self):
		lo, hi = grading.wilson(115, 120)
		self.assertLess(lo, 115 / 120)
		self.assertGreater(hi, 115 / 120)
		self.assertAlmostEqual(lo, 0.905, places=2)

	def test_mcnemar_is_two_sided_and_symmetric(self):
		self.assertEqual(grading.mcnemar_exact(3, 20), grading.mcnemar_exact(20, 3))
		self.assertEqual(grading.mcnemar_exact(0, 0), 1.0)
		self.assertGreater(grading.mcnemar_exact(5, 6), 0.05)
		self.assertLess(grading.mcnemar_exact(0, 15), 0.001)


class Prompting(unittest.TestCase):
	"""What the model is asked, and what is read back."""

	def test_grammar_describes_every_operation_and_function(self):
		"""The prompt is generated from the engine so it cannot fall behind it."""
		from nakhoda.engine.expression import FUNCTIONS
		from nakhoda.engine.operations import OPERATIONS

		spec = driver.grammar()
		for op in OPERATIONS:
			self.assertIn(f'"type": "{op}"', spec, f"{op} is not in the prompt")
		for fn in FUNCTIONS:
			self.assertRegex(spec, rf"\n  {re.escape(fn)}\s", f"{fn} is not in the prompt")

	def test_grammar_carries_no_worked_example(self):
		"""A worked example over these eight tables would leak a gold answer."""
		spec = driver.grammar()
		for table in ("tabSales Invoice", "tabCustomer", "tabItem"):
			self.assertNotIn(table, spec)

	def test_ops_prompt_carries_the_grammar_and_sql_does_not(self):
		context, question = "SCHEMA", "How many customers are on file?"
		self.assertIn("OPERATIONS", driver.prompt(context, question, "ops"))
		self.assertNotIn("OPERATIONS", driver.prompt(context, question, "sql"))
		for target in driver.TARGETS:
			text = driver.prompt(context, question, target)
			self.assertIn(context, text)
			self.assertIn(question, text)

	def test_ops_annotated_prompt_carries_the_grammar_and_asks_for_an_envelope(self):
		context, question = "SCHEMA", "How many customers are on file?"
		text = driver.prompt(context, question, "ops_annotated")
		self.assertIn("OPERATIONS", text)
		self.assertIn('"ops"', text)
		self.assertIn('"assumptions"', text)
		self.assertIn(context, text)
		self.assertIn(question, text)
		# Deliberately excluded from the benchmarked tuple - see its docstring.
		self.assertNotIn("ops_annotated", driver.TARGETS)

	def test_extract_reads_fenced_bare_and_chatty_answers(self):
		sql, err = driver.extract("```sql\nSELECT 1;\n```", "sql")
		self.assertEqual((sql, err), ("SELECT 1", None))
		sql, _ = driver.extract("SELECT 1", "sql")
		self.assertEqual(sql, "SELECT 1")

		ops, err = driver.extract('Here you go:\n```json\n[{"type":"source"}]\n```', "ops")
		self.assertEqual((ops, err), ([{"type": "source"}], None))
		ops, _ = driver.extract('Sure! [{"type":"source"}] hope that helps', "ops")
		self.assertEqual(ops, [{"type": "source"}])

	def test_ops_annotated_extracts_the_envelope_and_validates_assumptions(self):
		raw = (
			'{"ops": [{"type": "source"}], "assumptions": ['
			'{"tag": "period", "state": "applied", "text": "assumed this fiscal year"},'
			'{"tag": "territory", "state": "needs_you", "text": "assumed all territories",'
			' "counterfactual": "Kenya only would total less", "alt_label": "Kenya only", "keep_label": "Keep all"}'
			"]}"
		)
		payload, err = driver.extract(raw, "ops_annotated")
		self.assertIsNone(err)
		self.assertEqual(payload["ops"], [{"type": "source"}])
		self.assertEqual(len(payload["assumptions"]), 2)
		applied, needs_you = payload["assumptions"]
		self.assertEqual(applied["state"], "applied")
		self.assertNotIn("counterfactual", applied)
		self.assertEqual(needs_you["state"], "needs_you")
		self.assertEqual(needs_you["alt_label"], "Kenya only")

	def test_ops_annotated_drops_malformed_assumptions_without_failing_the_pipeline(self):
		"""A garbled explanation must never cost a valid `ops` array its answer."""
		raw = '{"ops": [{"type": "source"}], "assumptions": ["not an object", {"tag": "x"}, {"state": "bogus", "tag": "y", "text": "z"}]}'
		payload, err = driver.extract(raw, "ops_annotated")
		self.assertIsNone(err)
		self.assertEqual(payload["ops"], [{"type": "source"}])
		self.assertEqual(payload["assumptions"], [])

	def test_ops_annotated_needs_you_without_a_counterfactual_still_counts_as_an_assumption(self):
		raw = '{"ops": [{"type": "source"}], "assumptions": [{"tag": "x", "state": "needs_you", "text": "picked one reading"}]}'
		payload, _ = driver.extract(raw, "ops_annotated")
		self.assertEqual(
			payload["assumptions"], [{"tag": "x", "state": "needs_you", "text": "picked one reading"}]
		)

	def test_ops_annotated_accepts_a_bare_array_when_the_model_skips_the_envelope(self):
		"""Backward-compatible with the exact shape `target == "ops"` has always
		accepted, so a model that ignores the extra ask still answers."""
		payload, err = driver.extract('[{"type": "source"}]', "ops_annotated")
		self.assertIsNone(err)
		self.assertEqual(payload, {"ops": [{"type": "source"}], "assumptions": []})

	def test_extraction_failure_is_not_a_wrong_answer(self):
		"""Recorded as its own status: blaming the model for the harness would
		understate accuracy by however often a model chats."""
		for text, target in (("", "sql"), ("no json here", "ops"), ("[not json}", "ops")):
			artifact, err = driver.extract(text, target)
			self.assertIsNone(artifact)
			self.assertTrue(err)

	def test_plan_covers_the_product(self):
		questions = [{"id": "q01", "q": "one"}, {"id": "q02", "q": "two"}]
		rows = driver.plan(questions, {"B_semantic": "S"}, targets=("sql", "ops"), tiers=("smol",))
		self.assertEqual(len(rows), 4)
		self.assertEqual(len({r["prompt_sha"] for r in rows}), 4)

	def test_replay_refuses_a_prompt_it_never_saw(self):
		"""The one thing replay must not do is answer a question never asked."""
		import tempfile

		from nakhoda.bench import models

		with tempfile.TemporaryDirectory() as tmp:
			path = Path(tmp) / "completions.jsonl"
			driver.write_jsonl(path, [{"prompt_sha": driver.sha("asked"), "tier": "smol", "raw": "answer"}])
			generate = models.replay(path)
			self.assertEqual(generate("asked", "smol"), "answer")
			with self.assertRaises(KeyError):
				generate("never asked", "smol")
			with self.assertRaises(KeyError):
				generate("asked", "slow")


if __name__ == "__main__":
	unittest.main()
