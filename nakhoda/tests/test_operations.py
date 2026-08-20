# Copyright (c) 2026, Nakhoda and contributors
# For license information, please see license.txt
"""Phase 8: the grammar's own rules around the four ML operations.

`test_engine.py`'s Gate A proves the seven Phase 0 operations against real SQL
and needs the DuckDB fixture for that. Nothing here compiles a query - it is
`validate_pipeline` and `split_pipeline` read as pure functions, so it runs on
a bare interpreter with no fixture and no site, the same as `ibis_utils.py`'s
equivalent surface should have.
"""

from __future__ import annotations

import unittest

from nakhoda.engine.operations import (
	ML_OPERATIONS,
	OPERATIONS,
	OperationError,
	query_reference,
	source_tables,
	split_pipeline,
	validate_pipeline,
)

SOURCE = {"type": "source", "table": "tabSales Invoice"}


class Grammar(unittest.TestCase):
	"""The shape claims in `docs/plan/12-build-plan.md` §5, checked."""

	def test_eleven_operations_four_of_them_ml(self):
		self.assertEqual(len(OPERATIONS), 11, "the grammar grew; the ceiling is 14, say why in the plan")
		self.assertEqual(set(ML_OPERATIONS), {"forecast", "detect_anomalies", "segment", "score"})
		self.assertTrue(set(ML_OPERATIONS).issubset(OPERATIONS))

	def test_an_ml_operation_must_be_last(self):
		"""SQL, then optionally one ML step, never SQL-ML-SQL (`operations.py:_KEY` region)."""
		forecast = {"type": "forecast", "date_column": "d", "column": "v", "periods": 3}
		with self.assertRaises(OperationError):
			validate_pipeline([SOURCE, forecast, {"type": "limit", "n": 10}])
		# Legal at the end.
		validate_pipeline([SOURCE, forecast])

	def test_two_ml_operations_in_one_pipeline_is_rejected(self):
		forecast = {"type": "forecast", "date_column": "d", "column": "v", "periods": 3}
		anomalies = {"type": "detect_anomalies", "column": "v"}
		with self.assertRaises(OperationError):
			validate_pipeline([SOURCE, forecast, anomalies])

	def test_split_pipeline_separates_the_trailing_ml_step(self):
		forecast = {"type": "forecast", "date_column": "d", "column": "v", "periods": 3}
		prefix, ml_op = split_pipeline([SOURCE, forecast])
		self.assertEqual(prefix, [SOURCE])
		self.assertEqual(ml_op, forecast)

	def test_split_pipeline_is_a_noop_without_an_ml_step(self):
		prefix, ml_op = split_pipeline([SOURCE, {"type": "limit", "n": 10}])
		self.assertEqual(prefix, [SOURCE, {"type": "limit", "n": 10}])
		self.assertIsNone(ml_op)


class Forecast(unittest.TestCase):
	def op(self, **overrides):
		return {"type": "forecast", "date_column": "d", "column": "v", "periods": 3, **overrides}

	def test_requires_date_column_and_column(self):
		with self.assertRaises(OperationError):
			validate_pipeline([SOURCE, self.op(date_column="")])
		with self.assertRaises(OperationError):
			validate_pipeline([SOURCE, {"type": "forecast", "date_column": "d", "periods": 3}])

	def test_periods_must_be_a_positive_integer(self):
		with self.assertRaises(OperationError):
			validate_pipeline([SOURCE, self.op(periods=0)])
		with self.assertRaises(OperationError):
			validate_pipeline([SOURCE, self.op(periods=True)])  # bool is not an int here

	def test_method_and_freq_are_admitted_lists(self):
		with self.assertRaises(OperationError):
			validate_pipeline([SOURCE, self.op(method="prophet")])
		with self.assertRaises(OperationError):
			validate_pipeline([SOURCE, self.op(freq="fortnight")])
		validate_pipeline([SOURCE, self.op(method="holt_winters", freq="M")])

	def test_confidence_must_be_an_open_interval(self):
		with self.assertRaises(OperationError):
			validate_pipeline([SOURCE, self.op(confidence=1.0)])
		with self.assertRaises(OperationError):
			validate_pipeline([SOURCE, self.op(confidence=0)])
		validate_pipeline([SOURCE, self.op(confidence=0.8)])


class DetectAnomalies(unittest.TestCase):
	def test_contamination_bounds(self):
		op = {"type": "detect_anomalies", "column": "v"}
		validate_pipeline([SOURCE, op])
		with self.assertRaises(OperationError):
			validate_pipeline([SOURCE, {**op, "contamination": 0}])
		with self.assertRaises(OperationError):
			validate_pipeline([SOURCE, {**op, "contamination": 0.51}])

	def test_only_isolation_forest_is_admitted(self):
		op = {"type": "detect_anomalies", "column": "v", "method": "lof"}
		with self.assertRaises(OperationError):
			validate_pipeline([SOURCE, op])


class Segment(unittest.TestCase):
	def op(self, **overrides):
		return {"type": "segment", "id_column": "id", "date_column": "d", "value_column": "v", **overrides}

	def test_requires_the_three_rfm_columns(self):
		with self.assertRaises(OperationError):
			validate_pipeline([SOURCE, {"type": "segment", "date_column": "d", "value_column": "v"}])

	def test_clusters_must_be_at_least_two(self):
		with self.assertRaises(OperationError):
			validate_pipeline([SOURCE, self.op(clusters=1)])
		validate_pipeline([SOURCE, self.op(clusters=2)])


class Score(unittest.TestCase):
	def op(self, **overrides):
		return {
			"type": "score",
			"target": "churned",
			"id_column": "id",
			"feature_columns": ["age", "tenure"],
			**overrides,
		}

	def test_target_cannot_also_be_a_feature(self):
		with self.assertRaises(OperationError):
			validate_pipeline([SOURCE, self.op(feature_columns=["age", "churned"])])

	def test_feature_columns_must_be_a_non_empty_list(self):
		with self.assertRaises(OperationError):
			validate_pipeline([SOURCE, self.op(feature_columns=[])])
		with self.assertRaises(OperationError):
			validate_pipeline([SOURCE, self.op(feature_columns="age")])

	def test_only_admitted_methods(self):
		with self.assertRaises(OperationError):
			validate_pipeline([SOURCE, self.op(method="random_forest")])
		validate_pipeline([SOURCE, self.op(method="logistic")])


class Composition(unittest.TestCase):
	"""A table slot may name another stored query - the capability the workbook's
	derived queries and `linked_queries` closure are built on.

	Pure here: `validate_pipeline` and `source_tables` never touch a database, so
	the grammar's acceptance and the provenance walk are provable without a
	fixture. `test_engine.py::Composition` proves the compiled result.
	"""

	def ref(self, name: str) -> dict:
		return {"type": "query", "query_name": name}

	def test_a_source_may_be_a_query_reference(self):
		validate_pipeline([{"type": "source", "table": self.ref("q-base")}])

	def test_a_join_may_read_a_query(self):
		validate_pipeline(
			[
				SOURCE,
				{
					"type": "join",
					"table": self.ref("q-base"),
					"left_on": {"col": "customer"},
					"right_on": {"col": "name"},
					"select": [{"name": "tier", "expr": {"col": "tier"}}],
				},
			]
		)

	def test_a_table_object_must_be_a_query_reference(self):
		for bad in ({"type": "table", "name": "x"}, {"query_name": "q"}, {"type": "query"}, 7, None, ""):
			with self.assertRaises(OperationError, msg=repr(bad)):
				validate_pipeline([{"type": "source", "table": bad}])

	def test_query_reference_reads_the_one_shape(self):
		self.assertEqual(query_reference(self.ref("q-base")), "q-base")
		self.assertIsNone(query_reference("tabSales Invoice"))
		self.assertIsNone(query_reference({"type": "query", "query_name": ""}))

	def test_source_tables_names_physical_tables_only(self):
		"""Provenance must answer with tables, not with the query in between -
		a receipt naming `q-base` tells a reader nothing about what was read."""
		ops = [{"type": "source", "table": self.ref("q-base")}]
		base = {"q-base": [SOURCE, {"type": "limit", "n": 10}]}
		self.assertEqual(source_tables(ops, base.get), ["tabSales Invoice"])

	def test_source_tables_follows_more_than_one_hop(self):
		stored = {
			"q-top": [{"type": "source", "table": self.ref("q-mid")}],
			"q-mid": [
				SOURCE,
				{
					"type": "join",
					"table": "tabSales Invoice Item",
					"left_on": {"col": "name"},
					"right_on": {"col": "parent"},
					"select": [{"name": "qty", "expr": {"col": "qty"}}],
				},
			],
		}
		found = source_tables([{"type": "source", "table": self.ref("q-top")}], stored.get)
		self.assertEqual(found, ["tabSales Invoice", "tabSales Invoice Item"])

	def test_source_tables_survives_a_cycle(self):
		"""Provenance is read-only and must not hang on a pair of queries that
		reference each other - a user can save that one document at a time."""
		stored = {
			"a": [{"type": "source", "table": self.ref("b")}],
			"b": [{"type": "source", "table": self.ref("a")}],
		}
		self.assertEqual(source_tables([{"type": "source", "table": self.ref("a")}], stored.get), [])

	def test_source_tables_names_the_query_nothing_when_unresolvable(self):
		"""Without a provider there is nothing to follow; the walk still returns
		rather than raising, because the inspector must render for a pipeline
		that runs."""
		self.assertEqual(source_tables([{"type": "source", "table": self.ref("q")}]), [])


if __name__ == "__main__":
	unittest.main()
