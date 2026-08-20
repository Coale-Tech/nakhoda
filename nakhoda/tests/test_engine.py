"""Phase 0, Gate A: the operation pipeline agrees with SQL, row for row.

Each of the forty gold questions is run twice against the same DuckDB fixture -
once as gold SQL, once as an operation pipeline compiled through ibis - and the
two results must match. A gate that only checked "returns some rows" would pass
an engine that silently dropped a filter.

Runs on a bare interpreter: DuckDB and ibis only, no Frappe, no site. The
fixture is built by `semantic_bench/build.py`, which seeds an authentic
ERPNext-shaped schema; if it is absent the tests skip rather than pass.
"""

from __future__ import annotations

import unittest
from decimal import Decimal
from pathlib import Path

FIXTURE = Path("/tmp/semantic-bench/erp.duckdb")


def _available() -> bool:
	if not FIXTURE.exists():
		return False
	try:
		import duckdb
		import ibis
	except ImportError:
		return False
	return True


def _normalise(value):
	"""Compare values across two paths that may disagree about container types.

	DuckDB hands the same DECIMAL column back as `Decimal` on one path and, when
	an intermediate has been cast, as `float` on the other. That is a difference
	in how a number arrived, not in the number. Nulls are collapsed so that None
	and NaN - which are the same absent value - compare equal.
	"""
	if value is None:
		return None
	if isinstance(value, Decimal):
		return float(value)
	if isinstance(value, float) and value != value:  # NaN
		return None
	if isinstance(value, bool):
		return int(value)
	try:
		import pandas as pd

		if value is pd.NaT:
			return None
		if isinstance(value, pd.Timestamp):
			return value.to_pydatetime()
	except ImportError:
		pass
	return value


def _rows(df) -> list[tuple]:
	return [tuple(_normalise(v) for v in row) for row in df.itertuples(index=False, name=None)]


@unittest.skipUnless(_available(), f"needs the DuckDB fixture at {FIXTURE}: run semantic_bench/build.py")
class GateA(unittest.TestCase):
	"""Forty questions, two paths, one answer."""

	@classmethod
	def setUpClass(cls) -> None:
		import duckdb
		import ibis

		from nakhoda.tests.gold_pipelines import PIPELINES
		from nakhoda.tests.semantic_bench.questions import Q

		cls.duck = duckdb.connect(str(FIXTURE), read_only=True)
		cls.con = ibis.duckdb.connect(str(FIXTURE), read_only=True)
		cls.pipelines = PIPELINES
		cls.questions = {q["id"]: q for q in Q}

	@classmethod
	def tearDownClass(cls) -> None:
		cls.duck.close()

	def _resolve(self, name):
		return self.con.table(name)

	def _run_pipeline(self, ops):
		from nakhoda.engine.operations import compile_pipeline

		return compile_pipeline(ops, self._resolve).to_pandas()

	def test_every_question_has_a_pipeline(self):
		"""The gate covers the whole set, or it is not the gate the plan states."""
		self.assertEqual(
			sorted(self.questions), sorted(self.pipelines), "gold questions and pipelines disagree"
		)
		self.assertEqual(len(self.pipelines), 40)

	def test_pipelines_match_gold_sql(self):
		"""Row for row, column for column, against the SQL the benchmark graded."""
		failures = []

		for qid in sorted(self.questions):
			question = self.questions[qid]
			gold_sql = question["sql"]
			try:
				gold = self.duck.execute(gold_sql).df()
			except Exception as e:  # a broken fixture must not read as a passing gate
				failures.append(f"{qid}: gold SQL failed: {type(e).__name__}: {e}")
				continue

			try:
				got = self._run_pipeline(self.pipelines[qid])
			except Exception as e:
				failures.append(f"{qid}: pipeline failed: {type(e).__name__}: {e}")
				continue

			if list(gold.columns) != list(got.columns):
				failures.append(f"{qid}: columns {list(got.columns)} != gold {list(gold.columns)}")
				continue

			gold_rows, got_rows = _rows(gold), _rows(got)

			# An unordered query has no row order to preserve, so comparing in
			# arrival order would fail on an irrelevant difference. An ordered one
			# is compared as it arrives: the order is part of the answer.
			if "order by" not in gold_sql.lower():
				gold_rows = sorted(gold_rows, key=repr)
				got_rows = sorted(got_rows, key=repr)

			if gold_rows != got_rows:
				diff = next(
					(
						f"row {i}: {g!r} != {w!r}"
						for i, (g, w) in enumerate(zip(got_rows, gold_rows, strict=False))
						if g != w
					),
					f"lengths {len(got_rows)} != {len(gold_rows)}",
				)
				failures.append(f"{qid} ({question['trap']}): {diff}")

		self.assertEqual(failures, [], "\n" + "\n".join(failures))

	def test_expressibility_holds_at_seven_operations(self):
		"""The plan's claim, checked rather than asserted.

		Every question fits inside the seven Phase 0 operations - the forty gold
		queries predate Phase 8's four ML operations, so they must not need one.
		A pipeline that needed an eighth query operation would show up here before
		it showed up in the grammar.
		"""
		from nakhoda.engine.operations import ML_OPERATIONS, OPERATIONS

		query_operations = tuple(op for op in OPERATIONS if op not in ML_OPERATIONS)
		used = {op["type"] for ops in self.pipelines.values() for op in ops}
		self.assertLessEqual(used, set(query_operations))
		self.assertEqual(len(query_operations), 7, "the grammar grew; the ceiling is 14, say why in the plan")
		self.assertEqual(
			len(OPERATIONS), 11, "Phase 8 adds forecast/detect_anomalies/segment/score; the ceiling is 14"
		)


@unittest.skipUnless(_available(), f"needs the DuckDB fixture at {FIXTURE}: run semantic_bench/build.py")
class Composition(unittest.TestCase):
	"""A query reading a query compiles to one statement, and answers the same
	thing the flattened pipeline does.

	This is the property the workbook needs: an analyst stores a base query and
	derives from it, and the derived query must not be a second, slower path
	with its own semantics. `test_operations.py::Composition` covers the grammar
	and the provenance walk; only real SQL can show the answers agree.
	"""

	@classmethod
	def setUpClass(cls) -> None:
		import ibis

		cls.con = ibis.duckdb.connect(str(FIXTURE), read_only=True)

	def _resolve(self, name):
		return self.con.table(name)

	def _compile(self, ops, stored=None):
		from nakhoda.engine.operations import compile_pipeline

		provider = None if stored is None else stored.get
		return compile_pipeline(ops, self._resolve, provider)

	def test_a_derived_query_answers_what_the_flat_pipeline_answers(self):
		base = [
			{"type": "source", "table": "tabSales Invoice"},
			{"type": "filter", "where": {"fn": "eq", "args": [{"col": "docstatus"}, {"lit": 1}]}},
		]
		summarize = {
			"type": "summarize",
			"by": [{"name": "territory", "expr": {"col": "territory"}}],
			"measures": [{"name": "total", "expr": {"fn": "sum", "args": [{"col": "base_grand_total"}]}}],
		}

		flat = self._compile([*base, summarize]).to_pandas()
		derived = self._compile(
			[{"type": "source", "table": {"type": "query", "query_name": "q-base"}}, summarize],
			{"q-base": base},
		).to_pandas()

		self.assertEqual(
			_rows(flat.sort_values(list(flat.columns)).reset_index(drop=True)),
			_rows(derived.sort_values(list(derived.columns)).reset_index(drop=True)),
		)

	def test_the_base_is_a_subquery_not_a_second_statement(self):
		"""One `run` means one statement: the base appears inside the SQL, so the
		row cap and the cache key cover the composition rather than a fragment
		of it."""
		base = [{"type": "source", "table": "tabSales Invoice"}, {"type": "limit", "n": 5}]
		expression = self._compile(
			[
				{"type": "source", "table": {"type": "query", "query_name": "q-base"}},
				{"type": "summarize", "measures": [{"name": "n", "expr": {"fn": "count", "args": []}}]},
			],
			{"q-base": base},
		)
		sql = str(self.con.compile(expression))
		self.assertEqual(sql.upper().count("SELECT") > 1, True, sql)
		self.assertIn("tabSales Invoice", sql)

	def test_a_join_may_read_a_stored_query(self):
		base = [
			{"type": "source", "table": "tabSales Invoice Item"},
			{
				"type": "summarize",
				"by": [{"name": "parent", "expr": {"col": "parent"}}],
				"measures": [{"name": "lines", "expr": {"fn": "count", "args": []}}],
			},
		]
		frame = self._compile(
			[
				{"type": "source", "table": "tabSales Invoice"},
				{
					"type": "join",
					"table": {"type": "query", "query_name": "q-lines"},
					"left_on": {"col": "name"},
					"right_on": {"col": "parent"},
					"select": [{"name": "lines", "expr": {"col": "lines"}}],
				},
				{"type": "limit", "n": 10},
			],
			{"q-lines": base},
		).to_pandas()
		self.assertIn("lines", frame.columns)

	def test_a_cycle_is_refused_rather_than_followed(self):
		from nakhoda.engine.operations import OperationError

		stored = {
			"a": [{"type": "source", "table": {"type": "query", "query_name": "b"}}],
			"b": [{"type": "source", "table": {"type": "query", "query_name": "a"}}],
		}
		with self.assertRaises(OperationError) as caught:
			self._compile([{"type": "source", "table": {"type": "query", "query_name": "a"}}], stored)
		self.assertIn("reads itself", str(caught.exception))

	def test_a_chain_deeper_than_the_ceiling_is_refused(self):
		from nakhoda.engine.operations import MAX_QUERY_DEPTH, OperationError

		depth = MAX_QUERY_DEPTH + 3
		stored = {
			f"q{i}": [{"type": "source", "table": {"type": "query", "query_name": f"q{i + 1}"}}]
			for i in range(depth)
		}
		stored[f"q{depth}"] = [{"type": "source", "table": "tabSales Invoice"}]
		with self.assertRaises(OperationError) as caught:
			self._compile([{"type": "source", "table": {"type": "query", "query_name": "q0"}}], stored)
		self.assertIn("deep", str(caught.exception))

	def test_a_reference_without_a_provider_is_refused_not_silently_empty(self):
		from nakhoda.engine.operations import OperationError

		with self.assertRaises(OperationError) as caught:
			self._compile([{"type": "source", "table": {"type": "query", "query_name": "q"}}])
		self.assertIn("no query source was supplied", str(caught.exception))


if __name__ == "__main__":
	unittest.main()
