"""The operation grammar: an ordered pipeline, compiled to one ibis expression.

Seven operations, and the list is closed:

    source     pick the table that defines the grain
    join       bring named columns from another table into scope
    filter     drop rows
    select     choose and rename the columns in scope
    summarize  change the grain: group keys + aggregate measures
    order_by   sort
    limit      truncate

Static analysis of the forty gold queries (build plan §5, Phase 0) put all of
them inside these seven. Fourteen is the ceiling; `custom_operation`, `sql` and
`code` are a standing refusal rather than a later decision.

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
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

import ibis.expr.types as ir

from nakhoda.engine.expression import ExpressionError, compile_expr, is_aggregate, validate

#: The join key column, projected away before the caller sees the table.
_KEY = "__nk_join_key"

JOIN_TYPES = ("inner", "left")
OPERATIONS = ("source", "join", "filter", "select", "summarize", "order_by", "limit")

#: Resolves a table name to an ibis table. Supplied by the connector, so the
#: compiler never learns which backend it is targeting.
TableResolver = Callable[[str], ir.Table]


class OperationError(ValueError):
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
		_validate_one(op, f"operations[{i}]")

	return list(operations)


def _validate_one(op: dict, path: str) -> None:
	kind = op["type"]

	if kind == "source":
		if not isinstance(op.get("table"), str) or not op["table"]:
			raise OperationError(f"{path}: table must be a non-empty string")

	elif kind == "join":
		if not isinstance(op.get("table"), str) or not op["table"]:
			raise OperationError(f"{path}: table must be a non-empty string")
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


def compile_pipeline(operations: Any, resolve: TableResolver) -> ir.Table:
	"""Compile a pipeline to a single unexecuted ibis table expression."""
	ops = validate_pipeline(operations)
	table = resolve(ops[0]["table"])

	for i, op in enumerate(ops[1:], start=1):
		table = _apply(op, table, resolve, f"operations[{i}]")

	return table


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


def _apply(op: dict, table: ir.Table, resolve: TableResolver, path: str) -> ir.Table:
	kind = op["type"]

	if kind == "join":
		return _join(op, table, resolve, path)

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


def _join(op: dict, left: ir.Table, resolve: TableResolver, path: str) -> ir.Table:
	"""Join, taking only the named columns from the right table.

	The right side is narrowed to the key plus its named selections *before* the
	join, so the two namespaces never overlap and ibis is never asked to invent a
	disambiguating suffix. A name that would shadow a left column is an error
	here rather than a silently renamed column downstream.
	"""
	right = resolve(op["table"])
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
	"JOIN_TYPES",
	"OPERATIONS",
	"ExpressionError",
	"OperationError",
	"compile_pipeline",
	"validate_pipeline",
]
