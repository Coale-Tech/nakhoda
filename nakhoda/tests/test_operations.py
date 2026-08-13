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


if __name__ == "__main__":
	unittest.main()
