# Copyright (c) 2026, Nakhoda and contributors
# For license information, please see license.txt
"""Phase 8: the four ML operations, against synthetic frames.

`ml.apply()` is a pure function of `(op, frame) -> frame` - it never reads the
database or a permission (`engine/ml.py`'s own docstring). That is exactly what
lets these run on a bare interpreter: build a frame by hand, run the operation,
check the shape and the numbers it produced. Skips rather than fails where
`scikit-learn`/`statsmodels`/`scipy` are absent, the same discipline
`test_engine.py` applies to the DuckDB fixture.
"""

from __future__ import annotations

import unittest


def _available() -> bool:
	try:
		import pandas
		import scipy
		import sklearn
		import statsmodels

		del pandas, scipy, sklearn, statsmodels
	except ImportError:
		return False
	return True


@unittest.skipUnless(_available(), "needs pandas/scikit-learn/statsmodels/scipy")
class Forecast(unittest.TestCase):
	def test_output_shape_is_history_plus_periods_with_the_chart_vue_columns(self):
		import pandas as pd

		from nakhoda.engine import ml

		dates = pd.date_range("2026-01-01", periods=20, freq="D")
		frame = pd.DataFrame({"d": dates, "v": [100.0 + 2 * i for i in range(20)]})
		op = {"type": "forecast", "date_column": "d", "column": "v", "periods": 5, "freq": "D"}

		result = ml.apply(op, frame)

		self.assertEqual(len(result), 25)
		self.assertEqual(set(result.columns), {"d", "v", "forecast", "forecast_lower", "forecast_upper"})
		historical, projected = result.iloc[:20], result.iloc[20:]
		# Historical rows carry the actual, forecast columns are null - never both.
		self.assertTrue(historical["forecast"].isna().all())
		self.assertTrue(historical["v"].notna().all())
		# Forecast rows are the inverse: no actual, all three forecast columns filled.
		self.assertTrue(projected["v"].isna().all())
		self.assertTrue(projected["forecast"].notna().all())
		self.assertTrue((projected["forecast_lower"] <= projected["forecast"]).all())
		self.assertTrue((projected["forecast"] <= projected["forecast_upper"]).all())

	def test_a_clear_linear_trend_extrapolates_in_the_right_direction(self):
		import pandas as pd

		from nakhoda.engine import ml

		dates = pd.date_range("2026-01-01", periods=10, freq="D")
		frame = pd.DataFrame({"d": dates, "v": [float(i) for i in range(10)]})  # 0, 1, .. 9
		op = {
			"type": "forecast",
			"date_column": "d",
			"column": "v",
			"periods": 3,
			"freq": "D",
			"method": "linear",
		}

		result = ml.apply(op, frame)
		forecast = result.iloc[10:]["forecast"].to_numpy()

		# Ordinary least squares on 0..9 recovers slope 1, intercept 0 - the
		# next three points should land close to 10, 11, 12.
		self.assertTrue((forecast > 8).all() and (forecast < 14).all())
		self.assertTrue(forecast[0] < forecast[1] < forecast[2], "trend keeps climbing")

	def test_a_sparse_date_is_a_real_zero_not_a_dropped_row(self):
		"""`asfreq().fillna(0.0)` in `_forecast` - a day with no invoices is $0, not missing."""
		import pandas as pd

		from nakhoda.engine import ml

		dates = pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-04", "2026-01-05"])
		frame = pd.DataFrame({"d": dates, "v": [10.0, 10.0, 10.0, 10.0]})
		op = {"type": "forecast", "date_column": "d", "column": "v", "periods": 2, "freq": "D"}

		result = ml.apply(op, frame)
		historical = result.iloc[:5]
		self.assertEqual(len(historical), 5, "2026-01-03 must appear, filled at zero")
		gap_row = historical[historical["d"] == pd.Timestamp("2026-01-03")]
		self.assertEqual(len(gap_row), 1)
		self.assertEqual(gap_row["v"].iloc[0], 0.0)

	def test_fewer_than_two_historical_points_is_refused(self):
		import pandas as pd

		from nakhoda.engine import ml
		from nakhoda.engine.operations import OperationError

		frame = pd.DataFrame({"d": pd.to_datetime(["2026-01-01"]), "v": [10.0]})
		op = {"type": "forecast", "date_column": "d", "column": "v", "periods": 3}
		with self.assertRaises(OperationError):
			ml.apply(op, frame)

	def test_missing_column_names_the_step_not_a_stack_trace(self):
		import pandas as pd

		from nakhoda.engine import ml
		from nakhoda.engine.operations import OperationError

		frame = pd.DataFrame({"d": pd.date_range("2026-01-01", periods=5), "v": range(5)})
		op = {"type": "forecast", "date_column": "d", "column": "does_not_exist", "periods": 3}
		with self.assertRaises(OperationError) as ctx:
			ml.apply(op, frame)
		self.assertIn("does_not_exist", str(ctx.exception))


@unittest.skipUnless(_available(), "needs pandas/scikit-learn/statsmodels/scipy")
class DetectAnomalies(unittest.TestCase):
	def test_every_row_survives_and_gains_two_columns(self):
		import pandas as pd

		from nakhoda.engine import ml

		values = [100.0, 102.0, 98.0, 101.0, 99.0, 103.0, 97.0, 100.0, 5000.0, 101.0]
		frame = pd.DataFrame({"amount": values})
		op = {"type": "detect_anomalies", "column": "amount", "contamination": 0.1}

		result = ml.apply(op, frame)

		self.assertEqual(len(result), len(frame), "no row is ever dropped")
		self.assertEqual(set(result.columns), {"amount", "anomaly_score", "is_anomaly"})
		self.assertTrue(
			result["is_anomaly"].loc[result["amount"] == 5000.0].iloc[0], "the outlier is flagged"
		)
		# The outlier's score dominates every ordinary row's.
		self.assertEqual(result["anomaly_score"].idxmax(), result.index[result["amount"] == 5000.0][0])

	def test_non_numeric_rows_are_scored_not_dropped(self):
		import pandas as pd

		from nakhoda.engine import ml

		frame = pd.DataFrame({"amount": [100.0, 101.0, "not-a-number", 99.0, 102.0]})
		op = {"type": "detect_anomalies", "column": "amount"}

		result = ml.apply(op, frame)
		self.assertEqual(len(result), 5)
		bad_row = result.iloc[2]
		self.assertEqual(bad_row["anomaly_score"], 0.0)
		self.assertFalse(bad_row["is_anomaly"])

	def test_fewer_than_two_numeric_values_is_refused(self):
		import pandas as pd

		from nakhoda.engine import ml
		from nakhoda.engine.operations import OperationError

		frame = pd.DataFrame({"amount": [100.0, None, None]})
		with self.assertRaises(OperationError):
			ml.apply({"type": "detect_anomalies", "column": "amount"}, frame)


@unittest.skipUnless(_available(), "needs pandas/scikit-learn/statsmodels/scipy")
class Segment(unittest.TestCase):
	def test_one_row_per_distinct_id_with_rfm_and_a_cluster_label(self):
		import pandas as pd

		from nakhoda.engine import ml

		rows = []
		# Four customers with clearly separated recency/frequency/monetary so
		# k-means has an unambiguous answer to find.
		for cust, (n_orders, amount, last_day) in {
			"whale": (20, 5000.0, "2026-01-30"),
			"regular": (8, 800.0, "2026-01-28"),
			"lapsed": (3, 150.0, "2025-06-01"),
			"one_timer": (1, 50.0, "2025-01-01"),
		}.items():
			for _ in range(n_orders):
				rows.append({"customer": cust, "date": last_day, "amount": amount / n_orders})
		frame = pd.DataFrame(rows)
		op = {
			"type": "segment",
			"id_column": "customer",
			"date_column": "date",
			"value_column": "amount",
			"clusters": 3,
		}

		result = ml.apply(op, frame)

		self.assertEqual(len(result), 4, "one row per distinct customer")
		self.assertEqual(set(result.columns), {"customer", "recency", "frequency", "monetary", "segment"})
		self.assertEqual(set(result.loc[result["customer"] == "whale", "frequency"]), {20})
		self.assertTrue(result["segment"].between(0, 2).all(), "labels are 0..clusters-1")

	def test_clusters_is_clamped_to_the_number_of_distinct_ids(self):
		import pandas as pd

		from nakhoda.engine import ml

		frame = pd.DataFrame(
			{
				"customer": ["a", "a", "b", "b"],
				"date": ["2026-01-01", "2026-01-02", "2026-01-01", "2026-01-03"],
				"amount": [10.0, 10.0, 20.0, 20.0],
			}
		)
		# clusters=4 requested but only 2 distinct customers exist.
		op = {
			"type": "segment",
			"id_column": "customer",
			"date_column": "date",
			"value_column": "amount",
			"clusters": 4,
		}

		result = ml.apply(op, frame)
		self.assertEqual(len(result), 2)
		self.assertTrue(result["segment"].between(0, 1).all())

	def test_a_single_distinct_id_cannot_be_clustered(self):
		import pandas as pd

		from nakhoda.engine import ml
		from nakhoda.engine.operations import OperationError

		frame = pd.DataFrame(
			{"customer": ["a", "a"], "date": ["2026-01-01", "2026-01-02"], "amount": [10.0, 20.0]}
		)
		op = {"type": "segment", "id_column": "customer", "date_column": "date", "value_column": "amount"}
		with self.assertRaises(OperationError):
			ml.apply(op, frame)


@unittest.skipUnless(_available(), "needs pandas/scikit-learn/statsmodels/scipy")
class Score(unittest.TestCase):
	def _frame(self):
		import pandas as pd

		# A perfectly separable signal: high `tenure` churns, low `tenure` does not.
		# 12 labelled rows (>= the 10-row floor) plus 2 unlabelled rows to score.
		rows = [
			{"id": i, "tenure": t, "age": 30, "churned": 1 if t > 6 else 0}
			for i, t in enumerate(range(1, 13))
		]
		rows.append({"id": 100, "tenure": 1, "age": 30, "churned": None})
		rows.append({"id": 101, "tenure": 24, "age": 30, "churned": None})
		return pd.DataFrame(rows)

	def test_scores_every_row_including_the_unlabelled_ones(self):
		from nakhoda.engine import ml

		op = {
			"type": "score",
			"target": "churned",
			"id_column": "id",
			"feature_columns": ["tenure", "age"],
			"method": "logistic",
		}
		result = ml.apply(op, self._frame())

		self.assertEqual(len(result), 14, "every row is scored, labelled or not")
		self.assertEqual(set(result.columns), {"id", "churned", "score"})
		self.assertTrue((result["score"] >= 0).all() and (result["score"] <= 1).all())
		low_tenure = result.loc[result["id"] == 100, "score"].iloc[0]
		high_tenure = result.loc[result["id"] == 101, "score"].iloc[0]
		self.assertLess(
			low_tenure, high_tenure, "the unlabelled high-tenure row scores as more likely to churn"
		)

	def test_fewer_than_ten_labelled_rows_is_refused(self):
		import pandas as pd

		from nakhoda.engine import ml
		from nakhoda.engine.operations import OperationError

		frame = pd.DataFrame(
			{
				"id": range(5),
				"tenure": [1, 2, 3, 4, 5],
				"age": [30, 30, 30, 30, 30],
				"churned": [0, 1, 0, 1, 0],
			}
		)
		op = {"type": "score", "target": "churned", "id_column": "id", "feature_columns": ["tenure", "age"]}
		with self.assertRaises(OperationError):
			ml.apply(op, frame)

	def test_a_single_labelled_class_cannot_be_trained_on(self):
		import pandas as pd

		from nakhoda.engine import ml
		from nakhoda.engine.operations import OperationError

		frame = pd.DataFrame(
			{
				"id": range(12),
				"tenure": range(12),
				"age": [30] * 12,
				"churned": [0] * 12,  # every label the same class
			}
		)
		op = {"type": "score", "target": "churned", "id_column": "id", "feature_columns": ["tenure", "age"]}
		with self.assertRaises(OperationError):
			ml.apply(op, frame)


class Dispatch(unittest.TestCase):
	def test_apply_rejects_a_non_ml_operation_type(self):
		"""Unreachable through the API - `validate_pipeline` already refuses this - but
		`ml.apply` guards it too rather than trusting the caller silently."""
		from nakhoda.engine import ml
		from nakhoda.engine.operations import OperationError

		with self.assertRaises(OperationError):
			ml.apply({"type": "summarize"}, None)


if __name__ == "__main__":
	unittest.main()
