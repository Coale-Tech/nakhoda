"""The operation grammar: an ordered pipeline, compiled to one ibis expression.

Eleven operations, and the list is closed:

    source            pick the table that defines the grain
    join              bring named columns from another table into scope
    filter            drop rows
    select            choose and rename the columns in scope
    summarize         change the grain: group keys + aggregate measures
    order_by          sort
    limit             truncate
    forecast          project a value column forward in time
    detect_anomalies  flag outlying rows in a value column
    segment           cluster rows into groups (RFM + k-means)
    score             train on labelled rows, score every row

Static analysis of the forty gold queries (build plan §5, Phase 0) put the
first seven inside these seven; the last four are Phase 8 (`docs/plan/
12-build-plan.md` §5, `docs/plan/15-ml-dashboards.md` §4 Move 1). Fourteen is
the ceiling; `custom_operation`, `sql` and `code` are a standing refusal
rather than a later decision.

Two properties this shape buys, both of which the alternative - handing a model
a SQL string - gives up:

*Scope is explicit.* Each operation names what it puts in scope, so a column
reference that cannot resolve fails at that step, naming the step. After
`summarize`, only the group keys and measures are in scope: a pipeline cannot
read through an aggregation back to the raw grain by accident.

*Joins do not collide.* `join` states which columns it takes from the right
table and what to call them, instead of merging two namespaces and letting a
suffix rule decide. `{"table": "tabCustomer", "select": [{"name":
"customer_territory", ...}]}` is reviewable by someone who does not know either
schema; `si_territory_y` is not.

*The ML operations are the one deliberate break.* ibis cannot express
Holt-Winters, isolation forests or k-means, so `forecast` / `detect_anomalies`
/ `segment` / `score` cannot compile to SQL - `compile_pipeline` refuses a
pipeline that contains one. `validate_pipeline` restricts them to the last
position, so a pipeline is always "SQL, then optionally one ML step" and
never SQL-ML-SQL. `nakhoda.engine.pipeline.run` is what runs the whole thing:
it compiles everything before the break to one SQL statement - so permissions
and caching apply exactly as they do to any other query - materialises that
result, and only then, if the pipeline asked for it, hands the frame to
`nakhoda.engine.ml.apply`.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

import ibis.expr.types as ir

from nakhoda.engine.errors import GrammarError
from nakhoda.engine.expression import ExpressionError, compile_expr, is_aggregate, validate

#: The join key column, projected away before the caller sees the table.
_KEY = "__nk_join_key"

JOIN_TYPES = ("inner", "left")
FORECAST_METHODS = ("auto", "holt_winters", "linear")
FORECAST_FREQS = ("D", "W", "M", "Q", "Y")
ANOMALY_METHODS = ("isolation_forest",)
SEGMENT_METHODS = ("rfm",)
SCORE_METHODS = ("auto", "logistic", "gradient_boosting")
ML_OPERATIONS = ("forecast", "detect_anomalies", "segment", "score")
OPERATIONS = ("source", "join", "filter", "select", "summarize", "order_by", "limit", *ML_OPERATIONS)

#: Resolves a table name to an ibis table. Supplied by the connector, so the
#: compiler never learns which backend it is targeting.
TableResolver = Callable[[str], ir.Table]

#: Resolves a stored query's name to its operations. Supplied by the caller for
#: the same reason `TableResolver` is: reading a `Nakhoda Query` row is a
#: document concern, and this module never imports Frappe. Without one, a
#: pipeline that reads another query is refused rather than silently emptied.
QueryProvider = Callable[[str], Any]

#: How deep query composition may nest. A query reading a query reading a query
#: is a real thing analysts build; ten levels is not, and an unbounded walk
#: turns one page load into an unbounded number of document reads.
MAX_QUERY_DEPTH = 10


class OperationError(GrammarError):
	"""A malformed pipeline."""


def _named_list(spec: Any, path: str, *, allow_empty: bool = False) -> list[dict]:
	if not isinstance(spec, Sequence) or isinstance(spec, str):
		raise OperationError(f"{path}: expected a list")
	if not spec and not allow_empty:
		raise OperationError(f"{path}: must not be empty")
	out = []
	seen: set[str] = set()
	for i, item in enumerate(spec):
		if not isinstance(item, dict):
			raise OperationError(f"{path}[{i}]: expected an object")
		name = item.get("name")
		if not isinstance(name, str) or not name:
			raise OperationError(f"{path}[{i}]: name must be a non-empty string")
		if name in seen:
			raise OperationError(f"{path}[{i}]: duplicate name {name!r}")
		seen.add(name)
		validate(item.get("expr"), path=f"{path}[{i}].expr")
		out.append(item)
	return out


def validate_pipeline(operations: Any) -> list[dict]:
	"""Check pipeline structure without a database.

	Everything checkable without a schema is checked here, so a stored query can
	be rejected on save rather than at run time. Column existence is not
	checkable here - that needs the table - and is checked during compilation.
	"""
	if not isinstance(operations, Sequence) or isinstance(operations, str):
		raise OperationError("operations must be a list")
	if not operations:
		raise OperationError("a pipeline needs at least a source")

	for i, op in enumerate(operations):
		if not isinstance(op, dict):
			raise OperationError(f"operations[{i}]: expected an object")
		kind = op.get("type")
		if kind not in OPERATIONS:
			raise OperationError(f"operations[{i}]: unknown operation {kind!r}. Admitted: {list(OPERATIONS)}")
		if (kind == "source") != (i == 0):
			raise OperationError(
				f"operations[{i}]: `source` must be the first operation and appear exactly once"
			)
		if op.get("type") in ML_OPERATIONS and i != len(operations) - 1:
			raise OperationError(
				f"operations[{i}]: {op['type']!r} must be the last operation - a pipeline is "
				f"SQL, then optionally one ML step, never SQL-ML-SQL (see `compile_pipeline`)"
			)
		_validate_one(op, f"operations[{i}]")

	return list(operations)


def query_reference(spec: Any) -> str | None:
	"""The stored query this table spec reads, or `None` for a physical table.

	One reader for the one shape, so the compiler, the provenance walk and the
	document layer that records which queries a query depends on cannot disagree
	about what a reference looks like.
	"""
	if isinstance(spec, dict) and spec.get("type") == "query":
		name = spec.get("query_name")
		return name if isinstance(name, str) and name else None
	return None


def _validate_table(spec: Any, path: str) -> None:
	"""A table is a physical table name, or another query's result.

	Composition is the reason the workbook exists: an analyst builds a base
	query once and derives from it, rather than pasting the same six operations
	into four pipelines. The reference is by name, not by value, so editing the
	base changes every query that reads it - which is the point, and also why
	`compile_pipeline` refuses a cycle instead of following one.
	"""
	if isinstance(spec, str):
		if not spec:
			raise OperationError(f"{path}: table must be a non-empty string")
		return
	if isinstance(spec, dict):
		if spec.get("type") != "query":
			raise OperationError(
				f"{path}: a table object must be {{'type': 'query', 'query_name': ...}}, got {spec!r}"
			)
		if not query_reference(spec):
			raise OperationError(f"{path}: query_name must be a non-empty string")
		return
	raise OperationError(f"{path}: table must be a table name or a query reference, got {spec!r}")


def _validate_one(op: dict, path: str) -> None:
	kind = op["type"]

	if kind == "source":
		_validate_table(op.get("table"), path)

	elif kind == "join":
		_validate_table(op.get("table"), path)
		how = op.get("how", "inner")
		if how not in JOIN_TYPES:
			raise OperationError(f"{path}: how must be one of {list(JOIN_TYPES)}, got {how!r}")
		validate(op.get("left_on"), path=f"{path}.left_on")
		validate(op.get("right_on"), path=f"{path}.right_on")
		for side in ("left_on", "right_on"):
			if is_aggregate(op[side]):
				raise OperationError(f"{path}.{side}: a join key cannot be an aggregate")
		_named_list(op.get("select") or [], f"{path}.select", allow_empty=True)

	elif kind == "filter":
		validate(op.get("where"), path=f"{path}.where")
		if is_aggregate(op["where"]):
			raise OperationError(
				f"{path}.where: cannot filter on an aggregate. Summarize first, then filter "
				f"the result - a post-aggregate filter is a separate step, not a HAVING clause."
			)

	elif kind == "select":
		for c in _named_list(op.get("columns"), f"{path}.columns"):
			if is_aggregate(c["expr"]):
				raise OperationError(f"{path}: `select` cannot aggregate; use `summarize`")

	elif kind == "summarize":
		by = _named_list(op.get("by") or [], f"{path}.by", allow_empty=True)
		measures = _named_list(op.get("measures"), f"{path}.measures")
		for b in by:
			if is_aggregate(b["expr"]):
				raise OperationError(f"{path}.by: a group key cannot be an aggregate")
		for m in measures:
			if not is_aggregate(m["expr"]):
				raise OperationError(
					f"{path}.measures: {m['name']!r} does not aggregate. Every measure must "
					f"collapse rows, or the grain the summarize claims is not the grain it has."
				)
		clash = {b["name"] for b in by} & {m["name"] for m in measures}
		if clash:
			raise OperationError(f"{path}: {sorted(clash)} named as both a group key and a measure")

	elif kind == "order_by":
		keys = op.get("keys")
		if not isinstance(keys, Sequence) or isinstance(keys, str) or not keys:
			raise OperationError(f"{path}.keys: must be a non-empty list")
		for i, k in enumerate(keys):
			if not isinstance(k, dict):
				raise OperationError(f"{path}.keys[{i}]: expected an object")
			validate(k.get("expr"), path=f"{path}.keys[{i}].expr")
			if not isinstance(k.get("desc", False), bool):
				raise OperationError(f"{path}.keys[{i}].desc: must be a boolean")

	elif kind == "limit":
		n = op.get("n")
		if not isinstance(n, int) or isinstance(n, bool) or n <= 0:
			raise OperationError(f"{path}.n: must be a positive integer, got {n!r}")

	elif kind == "forecast":
		for field in ("column", "date_column"):
			if not isinstance(op.get(field), str) or not op[field]:
				raise OperationError(f"{path}.{field}: must be a non-empty string")
		periods = op.get("periods")
		if not isinstance(periods, int) or isinstance(periods, bool) or periods <= 0:
			raise OperationError(f"{path}.periods: must be a positive integer, got {periods!r}")
		method = op.get("method", "auto")
		if method not in FORECAST_METHODS:
			raise OperationError(f"{path}.method: must be one of {list(FORECAST_METHODS)}, got {method!r}")
		freq = op.get("freq", "D")
		if freq not in FORECAST_FREQS:
			raise OperationError(f"{path}.freq: must be one of {list(FORECAST_FREQS)}, got {freq!r}")
		confidence = op.get("confidence", 0.95)
		if not isinstance(confidence, (int, float)) or isinstance(confidence, bool) or not 0 < confidence < 1:
			raise OperationError(f"{path}.confidence: must be a number in (0, 1), got {confidence!r}")

	elif kind == "detect_anomalies":
		if not isinstance(op.get("column"), str) or not op["column"]:
			raise OperationError(f"{path}.column: must be a non-empty string")
		method = op.get("method", "isolation_forest")
		if method not in ANOMALY_METHODS:
			raise OperationError(f"{path}.method: must be one of {list(ANOMALY_METHODS)}, got {method!r}")
		contamination = op.get("contamination", 0.05)
		if (
			not isinstance(contamination, (int, float))
			or isinstance(contamination, bool)
			or not 0 < contamination <= 0.5
		):
			raise OperationError(f"{path}.contamination: must be a number in (0, 0.5], got {contamination!r}")

	elif kind == "segment":
		for field in ("id_column", "date_column", "value_column"):
			if not isinstance(op.get(field), str) or not op[field]:
				raise OperationError(f"{path}.{field}: must be a non-empty string")
		method = op.get("method", "rfm")
		if method not in SEGMENT_METHODS:
			raise OperationError(f"{path}.method: must be one of {list(SEGMENT_METHODS)}, got {method!r}")
		clusters = op.get("clusters", 4)
		if not isinstance(clusters, int) or isinstance(clusters, bool) or clusters < 2:
			raise OperationError(f"{path}.clusters: must be an integer >= 2, got {clusters!r}")

	elif kind == "score":
		for field in ("target", "id_column"):
			if not isinstance(op.get(field), str) or not op[field]:
				raise OperationError(f"{path}.{field}: must be a non-empty string")
		features = op.get("feature_columns")
		if not isinstance(features, Sequence) or isinstance(features, str) or not features:
			raise OperationError(f"{path}.feature_columns: must be a non-empty list")
		for i, f in enumerate(features):
			if not isinstance(f, str) or not f:
				raise OperationError(f"{path}.feature_columns[{i}]: must be a non-empty string")
		if op["target"] in features:
			raise OperationError(f"{path}: target {op['target']!r} cannot also be a feature column")
		method = op.get("method", "auto")
		if method not in SCORE_METHODS:
			raise OperationError(f"{path}.method: must be one of {list(SCORE_METHODS)}, got {method!r}")


def split_pipeline(operations: Sequence[dict]) -> tuple[list[dict], dict | None]:
	"""The ibis-compilable prefix, and the trailing ML operation if there is one.

	`validate_pipeline` already restricts an ML operation to the last position,
	so this is a slice, not a scan.
	"""
	ops = list(operations)
	if ops and ops[-1]["type"] in ML_OPERATIONS:
		return ops[:-1], ops[-1]
	return ops, None


def source_tables(operations: Any, queries: QueryProvider | None = None) -> list[str]:
	"""Every physical table this pipeline reads, following query references.

	Provenance and the permission notice both answer "which doctypes did this
	touch". Reading only the top-level `table` slots would answer that wrongly
	for a derived query - it would name the query, not the tables underneath -
	and a receipt that omits a table the statement read is worse than no
	receipt. Unresolvable references are skipped rather than raised: this is
	read-only provenance, and refusing here would break the inspector for a
	pipeline that still runs.
	"""
	found: list[str] = []
	seen: set[str] = set()

	def walk(ops: Any, visiting: tuple[str, ...]) -> None:
		for op in validate_pipeline(ops):
			if op["type"] not in ("source", "join"):
				continue
			spec = op["table"]
			name = query_reference(spec)
			if name is None:
				if spec not in seen:
					seen.add(spec)
					found.append(spec)
				continue
			if queries is None or name in visiting or len(visiting) >= MAX_QUERY_DEPTH:
				continue
			try:
				inner = queries(name)
			except Exception:
				continue
			walk(inner, (*visiting, name))

	walk(operations, ())
	return found


def compile_pipeline(
	operations: Any, resolve: TableResolver, queries: QueryProvider | None = None
) -> ir.Table:
	"""Compile a pipeline to a single unexecuted ibis table expression.

	Refuses a pipeline that ends in an ML operation - `forecast` and friends
	cannot compile to SQL. Run those through `nakhoda.engine.pipeline.run`,
	which compiles the prefix here and applies the ML step separately.

	`queries` resolves a stored query named as a source into its operations, so
	a derived query compiles to one statement with the base as a subquery. The
	base's tables go through the same `resolve`, which is what keeps a
	viewer's row and column filters applied underneath the composition: a
	reader cannot see through a colleague's query to rows of their own that
	permissions exclude.
	"""
	return _compile(operations, resolve, queries, ())


def _compile(
	operations: Any, resolve: TableResolver, queries: QueryProvider | None, visiting: tuple[str, ...]
) -> ir.Table:
	ops = validate_pipeline(operations)
	prefix, ml_op = split_pipeline(ops)
	if ml_op is not None:
		raise OperationError(
			f"operations: pipeline ends in {ml_op['type']!r}, which cannot compile to SQL. "
			f"Use `nakhoda.engine.pipeline.run`, not `compile_pipeline`, for a pipeline with "
			f"an ML step."
		)

	table = _table(prefix[0]["table"], resolve, queries, visiting, "operations[0]")
	for i, op in enumerate(prefix[1:], start=1):
		table = _apply(op, table, resolve, queries, visiting, f"operations[{i}]")

	return table


def _table(
	spec: Any,
	resolve: TableResolver,
	queries: QueryProvider | None,
	visiting: tuple[str, ...],
	path: str,
) -> ir.Table:
	"""One table slot: a physical table, or another query compiled inline."""
	name = query_reference(spec)
	if name is None:
		return resolve(spec)

	if queries is None:
		raise OperationError(
			f"{path}: this pipeline reads the stored query {name!r}, and no query source was "
			f"supplied to resolve it. Run it through an endpoint that passes one."
		)
	if name in visiting:
		cycle = " -> ".join((*visiting, name))
		raise OperationError(f"{path}: query {name!r} reads itself ({cycle}).")
	if len(visiting) >= MAX_QUERY_DEPTH:
		raise OperationError(
			f"{path}: query composition is more than {MAX_QUERY_DEPTH} deep. Flatten the chain "
			f"or store an intermediate result."
		)

	# Whatever the provider raises propagates untouched. A missing or unreadable
	# query is the *document* layer's refusal - a permission error, not a
	# malformed pipeline - and rewrapping it here would render a 403 as "invalid
	# pipeline" and tell the user to fix operations they got right.
	return _compile(queries(name), resolve, queries, (*visiting, name))


def _boolean(value: ir.Value, path: str) -> ir.BooleanValue:
	"""A predicate slot needs a predicate.

	Without this, `filter` on a bare string column reaches ibis and fails with a
	message about ibis internals. The pipeline knows what it asked for.
	"""
	if not isinstance(value, ir.BooleanValue):
		raise OperationError(
			f"{path}: expected a condition, got {value.type()}. "
			f"Wrap it in a comparison - eq, gt, is_null - to make it a condition."
		)
	return value


def _apply(
	op: dict,
	table: ir.Table,
	resolve: TableResolver,
	queries: QueryProvider | None,
	visiting: tuple[str, ...],
	path: str,
) -> ir.Table:
	kind = op["type"]

	if kind == "join":
		return _join(op, table, resolve, queries, visiting, path)

	if kind == "filter":
		where = compile_expr(op["where"], table, path=f"{path}.where")
		return table.filter(_boolean(where, f"{path}.where"))

	if kind == "select":
		return table.select(
			**{c["name"]: compile_expr(c["expr"], table, path=f"{path}.columns") for c in op["columns"]}
		)

	if kind == "summarize":
		by = {b["name"]: compile_expr(b["expr"], table, path=f"{path}.by") for b in op.get("by") or []}
		measures = {
			m["name"]: compile_expr(m["expr"], table, path=f"{path}.measures") for m in op["measures"]
		}
		if not by:
			return table.aggregate(**measures)
		return table.group_by(**by).aggregate(**measures)

	if kind == "order_by":
		keys: list[ir.Value] = []
		for k in op["keys"]:
			e = compile_expr(k["expr"], table, path=f"{path}.keys")
			keys.append(e.desc() if k.get("desc") else e.asc())  # type: ignore[attr-defined]
		return table.order_by(keys)  # type: ignore[arg-type]

	if kind == "limit":
		return table.limit(op["n"])

	raise OperationError(f"{path}: unreachable operation {kind!r}")


def _join(
	op: dict,
	left: ir.Table,
	resolve: TableResolver,
	queries: QueryProvider | None,
	visiting: tuple[str, ...],
	path: str,
) -> ir.Table:
	"""Join, taking only the named columns from the right table.

	The right side is narrowed to the key plus its named selections *before* the
	join, so the two namespaces never overlap and ibis is never asked to invent a
	disambiguating suffix. A name that would shadow a left column is an error
	here rather than a silently renamed column downstream.
	"""
	right = _table(op["table"], resolve, queries, visiting, path)
	selections = op.get("select") or []

	projection = {_KEY: compile_expr(op["right_on"], right, path=f"{path}.right_on")}
	for sel in selections:
		projection[sel["name"]] = compile_expr(sel["expr"], right, path=f"{path}.select")

	clash = set(projection) & set(left.columns)
	if clash:
		raise OperationError(
			f"{path}: {sorted(clash)} already in scope. Name the joined column something else - "
			f"this pipeline does not merge namespaces."
		)

	right_slim = right.select(**projection)
	left_key = compile_expr(op["left_on"], left, path=f"{path}.left_on")

	joined = left.join(right_slim, left_key == right_slim[_KEY], how=op.get("how", "inner"))
	return joined.drop(_KEY)


__all__ = [
	"ANOMALY_METHODS",
	"FORECAST_FREQS",
	"FORECAST_METHODS",
	"JOIN_TYPES",
	"MAX_QUERY_DEPTH",
	"ML_OPERATIONS",
	"OPERATIONS",
	"SCORE_METHODS",
	"SEGMENT_METHODS",
	"ExpressionError",
	"GrammarError",
	"OperationError",
	"QueryProvider",
	"compile_pipeline",
	"query_reference",
	"source_tables",
	"split_pipeline",
	"validate_pipeline",
]
