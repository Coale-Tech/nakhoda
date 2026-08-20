"""Runs a validated pipeline end to end: compile, cache, execute - and, when
the pipeline ends in an ML operation, the one deliberate break the grammar
allows (`engine/operations.py`, `engine/ml.py`).

Before this module, `Nakhoda Query`, `Nakhoda Verified Query` and the ad-hoc
`api.run` endpoint each rebuilt the same five steps - resolve, compile, cap,
hash the SQL, cache - independently. That duplication is exactly the kind of
drift that reopened Insights issue #919 across separate call sites; `run()`
is the one place it happens now.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from nakhoda.engine import cache
from nakhoda.engine.operations import (
	compile_pipeline,
	source_tables,
	split_pipeline,
	validate_pipeline,
)

if TYPE_CHECKING:
	import pandas as pd

	from nakhoda.connectors import Connector
	from nakhoda.engine.operations import QueryProvider, TableResolver


@dataclass(frozen=True)
class Run:
	"""One pipeline execution, cached or freshly computed.

	`sql` is the statement that actually ran against the backend - the
	ibis-compilable prefix, which is the whole pipeline when there is no ML
	step. `ml_operation` is that trailing operation's dict when there was
	one, else `None`: callers use it to label the response (`source:
	"forecast"` and friends) without operations.py or ml.py knowing anything
	about a response shape.
	"""

	frame: pd.DataFrame
	sql: str
	elapsed: float
	cache_key: str
	ml_operation: dict | None


def run(
	operations: Any,
	resolve: TableResolver,
	connector: Connector,
	*,
	cap: int,
	ttl: int,
	queries: QueryProvider | None = None,
) -> Run:
	"""Validate, compile, execute and cache one pipeline.

	`cap` bounds the ibis-compilable prefix - the same cap an ML step then
	computes over (`docs/plan/15-ml-dashboards.md` §4 Move 1, "under the
	existing row cap"): a forecast or segmentation sees at most `cap` input
	rows, same as any other query would.

	`queries` resolves stored queries named as sources, so a derived query is
	one statement against a subquery. It is a parameter rather than a default
	because reading a `Nakhoda Query` row is a document concern this module
	deliberately does not have (`engine/operations.py`, `QueryProvider`), and
	because the cache key then covers the composed SQL, not the reference.
	"""
	ops = validate_pipeline(operations)
	prefix, ml_op = split_pipeline(ops)

	expression = compile_pipeline(prefix, resolve, queries).limit(cap)
	sql = connector.sql(expression)
	# The ML step's parameters are part of what produced this result, so they
	# are part of the cache key - two `forecast` calls against the same SQL
	# with different `periods` must not collide (`engine/cache.py`'s own
	# docstring makes the parallel argument for permissions).
	cache_input = sql if ml_op is None else f"{sql}\n-- ml: {json.dumps(ml_op, sort_keys=True, default=str)}"

	started = time.monotonic()
	frame = cache.cached(
		cache_input,
		connector.identity,
		lambda: _compute(expression, ml_op, connector),
		ttl=ttl,
	)
	elapsed = time.monotonic() - started

	return Run(
		frame=frame,
		sql=sql,
		elapsed=elapsed,
		cache_key=cache.key(cache_input, connector.identity),
		ml_operation=ml_op,
	)


def _compute(expression, ml_op: dict | None, connector: Connector) -> pd.DataFrame:
	frame = connector.execute(expression)
	if ml_op is None:
		return frame
	from nakhoda.engine import ml

	return ml.apply(ml_op, frame)


def _raw_prefix(operations: list[dict]) -> list[dict]:
	"""The pipeline truncated to `source`/`join`/`filter` - the raw rows a
	`summarize` or `select` would collapse or reshape. "How many records" and
	"how much of one measure" are questions about that grain, not about
	however many rows the full pipeline's own aggregation happens to return -
	running the full pipeline here would report "1 territory" as "1 record"
	for any answer that summarizes.
	"""
	prefix: list[dict] = []
	for op in operations:
		if op["type"] not in ("source", "join", "filter"):
			break
		prefix.append(op)
	return prefix


def _single_sum_measure(operations: list[dict]) -> str | None:
	"""The one column a pipeline's `summarize` sums, when there is exactly
	one measure and it is a plain `sum` of a column - the only shape
	unambiguous enough to total over excluded rows without guessing which
	column is a measure, the same refusal `agent.charts.pick` applies to an
	answer's own result."""
	for op in operations:
		if op["type"] == "summarize":
			measures = op.get("measures") or []
			if len(measures) != 1:
				return None
			expr = measures[0]["expr"]
			if not isinstance(expr, dict) or expr.get("fn") != "sum":
				return None
			args = expr.get("args")
			if not isinstance(args, list) or len(args) != 1 or not isinstance(args[0], dict):
				return None
			col = args[0].get("col")
			return col if isinstance(col, str) else None
	return None


def _format_amount(value: Any) -> str:
	if value is None:
		return ""
	total = float(value)
	return str(int(total)) if total.is_integer() else str(round(total, 2))


def notice(
	operations: Any,
	resolve: TableResolver,
	policy: Any,
	connector: Connector,
	queries: QueryProvider | None = None,
) -> dict | None:
	"""How many records (and, when the pipeline names one clear sum measure,
	how much of it) a policy's row filter hid from this exact question -
	`14-frontend-design.md` §3's answer to Insights issue #919, computed
	rather than logged.

	Cheap when there is nothing to report: every table the pipeline touches
	is checked against `policy.rows()` before anything is compiled, so a
	question with no row-level restriction anywhere never pays for a second
	query. When at least one table is restricted, `_raw_prefix` of the
	identical pipeline runs again as one `count()` (+ `sum()`, when
	`_single_sum_measure` finds one) against the structural complement of the
	permitted rows (`engine.permissions.excluded_resolver`) - the honest way
	to answer "what did permissions remove from this query", as opposed to
	the whole unfiltered table, which would also include rows the query's own
	filters (`docstatus`, date ranges, ...) would have dropped regardless of
	who is asking.
	"""
	from nakhoda.engine.permissions import doctype_of, excluded_resolver

	ops = validate_pipeline(operations)
	# `source_tables`, not the top-level `table` slots: a derived query names
	# another query there, and the filters that matter belong to the tables
	# underneath it.
	doctypes = {doctype_of(table) for table in source_tables(ops, queries)}
	if not any(policy.rows(dt)[1] for dt in doctypes):
		return None

	excl_resolve, reasons = excluded_resolver(resolve, policy)
	measure_col = _single_sum_measure(ops)

	try:
		raw = compile_pipeline(_raw_prefix(ops), excl_resolve, queries)
		aggs = {"__n": raw.count()}
		if measure_col and measure_col in raw.columns:
			aggs["__sum"] = raw[measure_col].sum()
		row = connector.execute(raw.aggregate(**aggs)).iloc[0]
	except Exception:
		return None

	if not reasons:
		return None
	count = int(row["__n"])
	if count == 0:
		return None

	return {
		"excluded_count": count,
		"excluded_amount": _format_amount(row["__sum"]) if "__sum" in row else "",
		"reason": " and ".join(sorted(set(reasons.values()))),
	}


def injected(operations: Any, policy: Any, queries: QueryProvider | None = None) -> list[dict] | None:
	"""Which tables this pipeline touches carry a row-level permission filter
	`engine.permissions.permitted_resolver` structurally applied while
	compiling it - read-only provenance for the inspector
	(`14-frontend-design.md` §6, origin badges), named the same way
	`notice()` names what a filter excluded.

	Deliberately not part of the compiled `operations` themselves: the filter
	is injected at the resolver boundary precisely so a caller cannot see it
	as a step to edit or omit (`engine/permissions.py`'s own docstring). This
	answers "did permissions touch this query, and where" without ever
	returning something a re-run could feed back in as an operation.

	Cheap and always available - unlike `notice()`, it never compiles or
	executes anything, so it still answers for a cached or already-rendered
	run, not only a fresh one.
	"""
	from nakhoda.engine.permissions import doctype_of, filters_applied

	ops = validate_pipeline(operations)
	doctypes = sorted({doctype_of(table) for table in source_tables(ops, queries)})
	if not doctypes:
		return None
	found = filters_applied(doctypes, policy)
	return found or None


__all__ = ["Run", "injected", "notice", "run"]
