"""The four ML operations: forecast, detect_anomalies, segment, score.

Each function here takes the pandas frame the ibis-compilable prefix of a
pipeline already produced - already filtered, already permission-scoped
(`engine/permissions.py`), already capped (`engine/pipeline.py`) - and returns
a new frame. Nothing here reads the database, checks a permission or knows
about a user: by the time `apply()` is called, the row is already decided by
`compile_pipeline` and `permitted_resolver`. This is Move 1 of
`docs/plan/15-ml-dashboards.md` §4: making an ML result inherit filtering for
free instead of re-deriving it.

Method, not code. `sales_forecasting`, `gl_anomaly` and `customer_segmentation`
below are written against `statsmodels`/`scikit-learn` directly, from reading
`jkm/apps/insights` for *what estimator, what parameters, what it does with a
sparse series* - never from its source, which is AGPL-3.0 and would decide
Nakhoda's own licence question by accident (build plan §7, Phase 8). The
modelling is generic; only the wrapper is new.

Every estimator is fit fresh, on the frame in hand, every call. No model is
persisted between requests - there is no snapshot registry here, deliberately:
Phase 8 only asks for the operation union, and a training-and-caching layer on
top is a later decision, not one this module should make silently. Caching is
inherited too: `engine/pipeline.py` caches the *result* the same way it caches
any other query result, keyed by the SQL that produced the input plus this
operation's parameters (see `pipeline.py`'s cache-key comment).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from nakhoda.engine.operations import OperationError

if TYPE_CHECKING:
	import pandas as pd

#: Points per cycle for a seasonal Holt-Winters fit, keyed by `freq`. `Y` has
#: no shorter natural cycle to detect seasonality against, so it is absent -
#: a yearly series is always fit trend-only.
_SEASONAL_PERIODS: dict[str, int] = {"D": 7, "W": 52, "M": 12, "Q": 4}


def apply(op: dict, frame: pd.DataFrame) -> pd.DataFrame:
	"""Run one ML operation. `op["type"]` is one of `engine.operations.ML_OPERATIONS`."""
	kind = op["type"]
	if kind == "forecast":
		return _forecast(op, frame)
	if kind == "detect_anomalies":
		return _detect_anomalies(op, frame)
	if kind == "segment":
		return _segment(op, frame)
	if kind == "score":
		return _score(op, frame)
	raise OperationError(f"ml.apply: not an ML operation: {kind!r}")


def _require_columns(frame: pd.DataFrame, columns: list[str], op_name: str) -> None:
	"""Fail naming the step, same discipline `compile_expr` applies to a `col` reference.

	The ibis-compilable prefix already decided which columns exist and are
	permitted; a name missing here is a pipeline authoring error, not a
	permissions question.
	"""
	missing = [c for c in columns if c not in frame.columns]
	if missing:
		raise OperationError(f"{op_name}: column(s) {missing} not in scope. In scope: {list(frame.columns)}")


# --------------------------------------------------------------------------
# forecast
# --------------------------------------------------------------------------


def _forecast(op: dict, frame: pd.DataFrame) -> pd.DataFrame:
	"""Project `column` forward `periods` steps of `freq`, past `date_column`.

	Output has one row per historical date plus one per forecast period,
	carrying `date_column`, `column` (actual, null on forecast rows),
	`forecast`, `forecast_lower`, `forecast_upper` (all three null on
	historical rows). That shape is what `Chart.vue`'s `series[].forecast`
	flag already expects (`frontend/src/components/Chart.vue:24`): a bar's
	`value` is `column ?? forecast`, its `forecast` flag is `column is null`.
	No chart-side special case is needed - this *is* the ordinary shape.
	"""
	import numpy as np
	import pandas as pd

	date_col, value_col = op["date_column"], op["column"]
	periods, freq, confidence = op["periods"], op.get("freq", "D"), op.get("confidence", 0.95)
	_require_columns(frame, [date_col, value_col], "forecast")

	history = frame[[date_col, value_col]].copy()
	history[date_col] = pd.to_datetime(history[date_col])
	history[value_col] = pd.to_numeric(history[value_col], errors="coerce")
	history = history.dropna(subset=[date_col, value_col]).sort_values(date_col)
	history = history.groupby(date_col, as_index=True)[value_col].sum()

	if len(history) < 2:
		raise OperationError(f"forecast: needs at least 2 historical points, got {len(history)}")

	# A sparse series (a date with no rows) is a real zero, not a missing
	# observation - `asfreq` only introduces the gap, `fillna` closes it.
	series = history.asfreq(freq).fillna(0.0).astype(float)

	method = op.get("method", "auto")
	if method == "auto":
		seasonal_periods = _SEASONAL_PERIODS.get(freq)
		method = "holt_winters" if seasonal_periods and len(series) >= 2 * seasonal_periods else "linear"

	if method == "holt_winters":
		forecast, lower, upper = _holt_winters(series, periods, freq, confidence)
	else:
		forecast, lower, upper = _linear_trend(series, periods, confidence)

	future_index = pd.date_range(series.index[-1], periods=periods + 1, freq=freq)[1:]
	# `np.nan`, not `None`: an all-`None` column concatenated against a float
	# column is an all-NA object column until pandas infers otherwise, which a
	# future pandas release stops doing silently (FutureWarning, verified
	# against pandas 2.2.3). `np.nan` keeps every one of these five columns
	# float64 on both sides of the concat, so there is nothing to infer.
	historical = pd.DataFrame(
		{
			date_col: series.index,
			value_col: series.to_numpy(),
			"forecast": np.nan,
			"forecast_lower": np.nan,
			"forecast_upper": np.nan,
		}
	)
	projected = pd.DataFrame(
		{
			date_col: future_index,
			value_col: np.nan,
			"forecast": forecast,
			"forecast_lower": lower,
			"forecast_upper": upper,
		}
	)
	return pd.concat([historical, projected], ignore_index=True)


def _holt_winters(series: pd.Series, periods: int, freq: str, confidence: float):
	"""Additive-trend Holt-Winters, seasonal when the series is long enough to fit one."""
	from statsmodels.tsa.holtwinters import ExponentialSmoothing

	seasonal_periods = _SEASONAL_PERIODS.get(freq)
	seasonal = bool(seasonal_periods) and len(series) >= 2 * seasonal_periods
	model = ExponentialSmoothing(
		series,
		trend="add",
		seasonal="add" if seasonal else None,
		seasonal_periods=seasonal_periods if seasonal else None,
		initialization_method="estimated",
	).fit()
	forecast = model.forecast(periods).to_numpy()
	resid = model.resid.to_numpy()
	lower, upper = _confidence_band(forecast, resid, confidence, ddof=2)
	return forecast, lower, upper


def _linear_trend(series: pd.Series, periods: int, confidence: float):
	"""Ordinary least squares against a time index - the fallback for a series too short to seasonally fit."""
	import numpy as np

	y = series.to_numpy(dtype=float)
	x = np.arange(len(y), dtype=float)
	slope, intercept = np.polyfit(x, y, 1)
	future_x = np.arange(len(y), len(y) + periods, dtype=float)
	forecast = intercept + slope * future_x
	resid = y - (intercept + slope * x)
	lower, upper = _confidence_band(forecast, resid, confidence, ddof=2)
	return forecast, lower, upper


def _confidence_band(forecast, resid, confidence: float, *, ddof: int):
	"""A symmetric band around `forecast`, `confidence` wide, from the fit's own residual spread."""
	from scipy.stats import norm

	n = len(resid)
	resid_std = float(resid.std(ddof=ddof)) if n > ddof else 0.0
	z = norm.ppf(0.5 + confidence / 2)
	return forecast - z * resid_std, forecast + z * resid_std


# --------------------------------------------------------------------------
# detect_anomalies
# --------------------------------------------------------------------------


def _detect_anomalies(op: dict, frame: pd.DataFrame) -> pd.DataFrame:
	"""Flag outliers in `column` with an isolation forest.

	Every input row survives, gaining `anomaly_score` (higher = more
	anomalous) and `is_anomaly`. Rows where `column` is not numeric are
	scored 0 / not-anomalous rather than dropped - a pipeline result should
	not silently lose rows a caller may have filtered for.
	"""
	import pandas as pd
	from sklearn.ensemble import IsolationForest

	column = op["column"]
	contamination = op.get("contamination", 0.05)
	_require_columns(frame, [column], "detect_anomalies")

	values = pd.to_numeric(frame[column], errors="coerce")
	mask = values.notna()
	if int(mask.sum()) < 2:
		raise OperationError(f"detect_anomalies: needs at least 2 non-null values in {column!r}")

	model = IsolationForest(contamination=contamination, random_state=0)
	fitted = model.fit(values.loc[mask].to_frame())
	scores = pd.Series(0.0, index=frame.index)
	flags = pd.Series(False, index=frame.index)
	scores.loc[mask] = -fitted.score_samples(values.loc[mask].to_frame())
	flags.loc[mask] = fitted.predict(values.loc[mask].to_frame()) == -1

	result = frame.copy()
	result["anomaly_score"] = scores
	result["is_anomaly"] = flags
	return result


# --------------------------------------------------------------------------
# segment
# --------------------------------------------------------------------------


def _segment(op: dict, frame: pd.DataFrame) -> pd.DataFrame:
	"""RFM segmentation: recency/frequency/monetary per `id_column`, clustered with k-means.

	Output is one row per distinct id: `id_column`, `recency` (days since
	that id's last row, as of the frame's latest date), `frequency` (row
	count), `monetary` (sum of `value_column`), `segment` (cluster label,
	`0..clusters-1` - not ranked or named, so a caller does not read
	"segment 0" as worse than "segment 3").
	"""
	import pandas as pd
	from sklearn.cluster import KMeans
	from sklearn.preprocessing import StandardScaler

	id_col, date_col, value_col = op["id_column"], op["date_column"], op["value_column"]
	clusters = op.get("clusters", 4)
	_require_columns(frame, [id_col, date_col, value_col], "segment")

	data = frame[[id_col, date_col, value_col]].copy()
	data[date_col] = pd.to_datetime(data[date_col], errors="coerce")
	data[value_col] = pd.to_numeric(data[value_col], errors="coerce")
	data = data.dropna(subset=[id_col, date_col, value_col])
	if data.empty:
		raise OperationError("segment: no rows with a non-null id, date and value")

	as_of = data[date_col].max()
	rfm = data.groupby(id_col).agg(
		recency=(date_col, lambda s: (as_of - s.max()).days),
		frequency=(date_col, "count"),
		monetary=(value_col, "sum"),
	)
	rfm = rfm.reset_index()

	n_clusters = min(clusters, len(rfm))
	if n_clusters < 2:
		raise OperationError(
			f"segment: needs at least 2 distinct {id_col!r} values to cluster, got {len(rfm)}"
		)

	features = StandardScaler().fit_transform(rfm[["recency", "frequency", "monetary"]])
	labels = KMeans(n_clusters=n_clusters, random_state=0, n_init=10).fit_predict(features)
	rfm["segment"] = labels
	return rfm


# --------------------------------------------------------------------------
# score
# --------------------------------------------------------------------------


def _score(op: dict, frame: pd.DataFrame) -> pd.DataFrame:
	"""Train on the rows where `target` is known, score every row.

	`target` is the label column - a row with a non-null `target` is training
	data, every row (labelled or not) is scored. Output is `id_column`,
	`target` (as given, for calibration against known outcomes), `score` (the
	trained model's probability of the positive class). No model is kept
	after this call returns; see the module docstring.
	"""
	import pandas as pd

	target, features, id_col = op["target"], op["feature_columns"], op["id_column"]
	method = op.get("method", "auto")
	_require_columns(frame, [*features, target, id_col], "score")

	data = frame[[id_col, target, *features]].copy()
	for column in features:
		data[column] = pd.to_numeric(data[column], errors="coerce")

	train = data[data[target].notna()]
	if train[target].nunique() < 2:
		raise OperationError("score: target needs at least two distinct labelled classes to train on")
	if len(train) < 10:
		raise OperationError(f"score: needs at least 10 labelled rows, got {len(train)}")

	fill = train[features].mean()
	train_x = train[features].fillna(fill)
	labels = train[target]
	estimator = _estimator(method)
	estimator.fit(train_x, labels)

	all_x = data[features].fillna(fill)
	scores = estimator.predict_proba(all_x)[:, -1]

	result = data[[id_col, target]].copy()
	result["score"] = scores
	return result


def _estimator(method: str):
	if method in ("auto", "gradient_boosting"):
		from sklearn.ensemble import GradientBoostingClassifier

		return GradientBoostingClassifier(random_state=0)
	if method == "logistic":
		from sklearn.linear_model import LogisticRegression

		return LogisticRegression(max_iter=1000)
	# Unreachable through the API: `engine.operations._validate_one` admits
	# only `SCORE_METHODS`, which is exactly these two plus `auto`.
	raise OperationError(f"score: unknown method {method!r}")


__all__ = ["apply"]
