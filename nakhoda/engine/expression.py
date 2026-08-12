"""The expression grammar: a closed AST over a fixed function registry.

Three node shapes, and there is no fourth:

    {"col": "base_grand_total"}          a column in the current scope
    {"lit": 1}                           a JSON scalar
    {"fn": "sum", "args": [...]}         a registry function

`custom`, `sql` and `code` are absent by design (build plan §2). They are how a
grammar stops being closed: one passthrough node and every downstream guarantee
- permission filtering, cost estimation, inspectability - becomes advisory.
An expression this module cannot compile is an error, never a string handed to
the database.

Why a registry rather than `getattr(column, name)`: the set of things a model
may emit has to be enumerable to be reviewable, and ibis method names are not a
vetted vocabulary. Each entry below states the arity it accepts, so a wrong-arity
call fails at validation with a message about the call, rather than inside ibis
with a message about ibis.
"""

from __future__ import annotations

import datetime
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

import ibis
import ibis.expr.types as ir

SCALAR = "scalar"
AGGREGATE = "aggregate"


class ExpressionError(ValueError):
	"""A malformed or unadmitted expression."""


@dataclass(frozen=True)
class Fn:
	kind: str
	min_args: int
	max_args: int | None  # None == variadic
	build: Callable[..., ir.Value] | None  # None: compiled structurally, needs the table
	doc: str

	def check_arity(self, name: str, n: int) -> None:
		if n < self.min_args or (self.max_args is not None and n > self.max_args):
			want = (
				f"{self.min_args}"
				if self.max_args == self.min_args
				else f"{self.min_args}+"
				if self.max_args is None
				else f"{self.min_args}-{self.max_args}"
			)
			raise ExpressionError(f"{name}() takes {want} argument(s), got {n}")


def _in(value: ir.Value, *options: ir.Value) -> ir.Value:
	return value.isin(list(options))


def _and(*args: ir.Value) -> ir.Value:
	out = args[0]
	for a in args[1:]:
		out = out & a
	return out


def _or(*args: ir.Value) -> ir.Value:
	out = args[0]
	for a in args[1:]:
		out = out | a
	return out


def _date(value: ir.Value) -> ir.Value:
	return value.cast("date")


def _date_trunc(unit: ir.Value, value: ir.Value) -> ir.Value:
	# The unit is a literal, not a column: read it back out before calling ibis.
	try:
		literal = unit.op().value
	except AttributeError:
		raise ExpressionError("date_trunc() unit must be a literal, not a column")
	allowed = {"year", "quarter", "month", "week", "day", "hour", "minute", "second"}
	if literal not in allowed:
		raise ExpressionError(f"date_trunc() unit {literal!r} not in {sorted(allowed)}")
	return value.truncate(literal)


def _real(value: ir.Value) -> ir.Value:
	"""Force a real-valued result.

	ibis types `mean(decimal(18,6))` as `decimal(18,6)` and coerces the result on
	materialisation, so an average of money silently loses everything past the
	sixth decimal - measured against DuckDB, 14013.415371 where the database
	computed 14013.41537131387. An average is not a member of the input domain
	and must not be rounded into it. Same for division.
	"""
	return value.cast("float64")


def _promote(build: Callable[[ir.Value, ir.Value], ir.Value]) -> Callable[..., ir.Value]:
	"""Standard numeric promotion, which ibis does not apply to decimal x float.

	DuckDB gives `DECIMAL(18,6) * DOUBLE` a DOUBLE, and ibis calls the same
	expression a decimal; the narrower inferred type then rounds the wider
	computed one at the boundary. Where either operand is floating, so is the
	result.
	"""

	def apply(a: ir.Value, b: ir.Value) -> ir.Value:
		out = build(a, b)
		operand_is_real = a.type().is_floating() or b.type().is_floating()
		if operand_is_real and not out.type().is_floating():
			return out.cast("float64")
		return out

	return apply


#: The admitted vocabulary. Every entry is either used by the gold question set
#: or is the closure of an operator family that is - a comparison set without
#: `lt` is not a comparison set, and a model asked for "invoices under 1000"
#: would have nothing to emit and would fail in a worse way than being wrong.
FUNCTIONS: dict[str, Fn] = {
	# -- aggregates ---------------------------------------------------------
	"count": Fn(AGGREGATE, 0, 1, None, "row count; count(x) counts non-null x"),
	"count_distinct": Fn(AGGREGATE, 1, 1, lambda x: x.nunique(), "distinct non-null values"),
	"sum": Fn(AGGREGATE, 1, 1, lambda x: x.sum(), "sum; keeps the operand's type"),
	"avg": Fn(AGGREGATE, 1, 1, lambda x: _real(x.mean()), "arithmetic mean, real-valued"),
	"min": Fn(AGGREGATE, 1, 1, lambda x: x.min(), "minimum"),
	"max": Fn(AGGREGATE, 1, 1, lambda x: x.max(), "maximum"),
	# -- arithmetic ---------------------------------------------------------
	"add": Fn(SCALAR, 2, 2, _promote(lambda a, b: a + b), "a + b"),
	"sub": Fn(SCALAR, 2, 2, _promote(lambda a, b: a - b), "a - b"),
	"mul": Fn(SCALAR, 2, 2, _promote(lambda a, b: a * b), "a * b"),
	"div": Fn(SCALAR, 2, 2, lambda a, b: _real(a / b), "a / b, always real-valued"),
	# -- comparison ---------------------------------------------------------
	"eq": Fn(SCALAR, 2, 2, lambda a, b: a == b, "a = b"),
	"ne": Fn(SCALAR, 2, 2, lambda a, b: a != b, "a <> b"),
	"gt": Fn(SCALAR, 2, 2, lambda a, b: a > b, "a > b"),
	"gte": Fn(SCALAR, 2, 2, lambda a, b: a >= b, "a >= b"),
	"lt": Fn(SCALAR, 2, 2, lambda a, b: a < b, "a < b"),
	"lte": Fn(SCALAR, 2, 2, lambda a, b: a <= b, "a <= b"),
	"in": Fn(SCALAR, 2, None, _in, "a IN (...)"),
	"is_null": Fn(SCALAR, 1, 1, lambda a: a.isnull(), "a IS NULL"),
	"is_not_null": Fn(SCALAR, 1, 1, lambda a: a.notnull(), "a IS NOT NULL"),
	# -- logical ------------------------------------------------------------
	"and": Fn(SCALAR, 2, None, _and, "conjunction"),
	"or": Fn(SCALAR, 2, None, _or, "disjunction"),
	"not": Fn(SCALAR, 1, 1, lambda a: ~a, "negation"),
	# -- scalar -------------------------------------------------------------
	"abs": Fn(SCALAR, 1, 1, lambda a: a.abs(), "absolute value"),
	"coalesce": Fn(SCALAR, 2, None, lambda *a: ibis.coalesce(*a), "first non-null"),
	"date": Fn(SCALAR, 1, 1, _date, "cast to date"),
	"date_trunc": Fn(
		SCALAR,
		2,
		2,
		_date_trunc,
		"date_trunc(unit, value); unit is a literal: year|quarter|month|week|day|hour|minute|second",
	),
}

_LITERAL_TYPES = (str, int, float, bool, type(None), datetime.date, datetime.datetime)


def is_aggregate(node: Any) -> bool:
	"""True when evaluating `node` collapses rows.

	Used to keep aggregates out of `filter` (that is HAVING, not shipped) and out
	of `summarize.by`, where they would silently change the grain.
	"""
	if not isinstance(node, dict):
		return False
	if "fn" in node:
		fn = FUNCTIONS.get(node["fn"])
		if fn is not None and fn.kind == AGGREGATE:
			return True
		return any(is_aggregate(a) for a in node.get("args") or [])
	return False


def validate(node: Any, *, path: str = "expr") -> None:
	"""Reject a malformed expression before any of it reaches ibis."""
	if not isinstance(node, dict):
		raise ExpressionError(f"{path}: expected an object, got {type(node).__name__}")

	keys = {"col", "lit", "fn"} & set(node)
	if len(keys) != 1:
		raise ExpressionError(
			f"{path}: expected exactly one of col/lit/fn, got {sorted(set(node)) or 'nothing'}"
		)

	if "col" in node:
		if not isinstance(node["col"], str) or not node["col"]:
			raise ExpressionError(f"{path}: col must be a non-empty string")
		return

	if "lit" in node:
		if not isinstance(node["lit"], _LITERAL_TYPES):
			raise ExpressionError(f"{path}: lit must be a JSON scalar, got {type(node['lit']).__name__}")
		return

	name = node["fn"]
	fn = FUNCTIONS.get(name) if isinstance(name, str) else None
	if fn is None:
		raise ExpressionError(f"{path}: unknown function {name!r}. Admitted: {sorted(FUNCTIONS)}")

	args = node.get("args") or []
	if not isinstance(args, Sequence) or isinstance(args, str):
		raise ExpressionError(f"{path}: args must be a list")
	fn.check_arity(name, len(args))

	if fn.kind == AGGREGATE:
		for i, a in enumerate(args):
			if is_aggregate(a):
				raise ExpressionError(f"{path}.args[{i}]: {name}() cannot take another aggregate")

	for i, a in enumerate(args):
		validate(a, path=f"{path}.args[{i}]")


def compile_expr(node: Any, table: ir.Table, *, path: str = "expr") -> ir.Value:
	"""Compile a validated expression against `table`.

	`table` is the scope: the only columns an expression can name are the ones
	the pipeline has put in scope at this step. After `summarize` that is the
	group keys and the measures, and nothing else - which is what stops a
	pipeline from silently reading through an aggregation to the raw grain.
	"""
	validate(node, path=path)
	return _compile(node, table, path)


def _compile(node: dict, table: ir.Table, path: str) -> ir.Value:
	if "col" in node:
		name = node["col"]
		if name not in table.columns:
			raise ExpressionError(f"{path}: no column {name!r} in scope. Available: {sorted(table.columns)}")
		return table[name]

	if "lit" in node:
		return ibis.literal(node["lit"])

	name = node["fn"]
	fn = FUNCTIONS[name]
	args = [_compile(a, table, f"{path}.args[{i}]") for i, a in enumerate(node.get("args") or [])]

	if fn.build is None:
		# Structural: `count` needs the table, which no registry lambda can see.
		# count() is over the table; count(x) is over a column that skips nulls.
		assert name == "count", f"{name} has no builder and no structural case"
		return table.count() if not args else args[0].count()  # type: ignore[attr-defined]

	try:
		return fn.build(*args)
	except ExpressionError:
		raise
	except Exception as e:  # ibis rejected a type combination we do not model
		raise ExpressionError(f"{path}: {name}() rejected its arguments: {e}")
