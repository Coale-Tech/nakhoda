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

		Every question fits inside the seven shipped operations. A pipeline that
		needed an eighth would show up here before it showed up in the grammar.
		"""
		from nakhoda.engine.operations import OPERATIONS

		used = {op["type"] for ops in self.pipelines.values() for op in ops}
		self.assertLessEqual(used, set(OPERATIONS))
		self.assertEqual(len(OPERATIONS), 7, "the grammar grew; the ceiling is 14, say why in the plan")


if __name__ == "__main__":
	unittest.main()
