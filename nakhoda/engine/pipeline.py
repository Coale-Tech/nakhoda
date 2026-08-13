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
from nakhoda.engine.operations import compile_pipeline, split_pipeline, validate_pipeline

if TYPE_CHECKING:
	import pandas as pd

	from nakhoda.connectors import Connector
	from nakhoda.engine.operations import TableResolver


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


def run(operations: Any, resolve: TableResolver, connector: Connector, *, cap: int, ttl: int) -> Run:
	"""Validate, compile, execute and cache one pipeline.

	`cap` bounds the ibis-compilable prefix - the same cap an ML step then
	computes over (`docs/plan/15-ml-dashboards.md` §4 Move 1, "under the
	existing row cap"): a forecast or segmentation sees at most `cap` input
	rows, same as any other query would.
	"""
	ops = validate_pipeline(operations)
	prefix, ml_op = split_pipeline(ops)

	expression = compile_pipeline(prefix, resolve).limit(cap)
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


__all__ = ["Run", "run"]
