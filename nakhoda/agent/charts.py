# Copyright (c) 2026, Nakhoda and contributors
# For license information, please see license.txt
"""Auto-visualization for `ask()` answers.

Phase 5's chart gate ("bar height proportional to value, 0px axis drift",
`12-build-plan.md` §5) is measured against `Chart.vue`'s own grid-based bar
geometry (`frontend/tests/chart-geometry.spec.js`) — that component already
satisfies it by construction, via `grid-rows-[auto_1fr]` resolving each
bar's `height:N%` against its own plot track rather than a column that also
holds the value label. What was missing was ever populating
`turn.answer.chart`: neither `nakhoda.api.run` nor `execute_verified` picked
a chart, so `src/agent.js` left it unset and every answer fell through to
the table branch.

A chart is only ever *inferred*, never requested: the operation grammar has
no `chart` step (§2's refusal of a drag-and-drop pipeline builder extends to
not adding a visualization DSL either), so this is pattern matching on the
*result shape* a `summarize` operation naturally produces — one label
column, one numeric measure column, few enough rows to read as bars.
Anything else (a scalar metric, three-plus columns, a wide table) is left
alone and renders as the table branch instead: `Turn.vue` picks `chart` XOR
`table`, never both, so over-triggering here would silently hide the table
a user actually asked to see.
"""

from __future__ import annotations

import numbers
from collections.abc import Mapping
from typing import Any

#: `Chart.vue` renders one row of bars, not a paginated visualization - past
#: this many categories a bar chart stops being readable and the table
#: (which sorts, scrolls, and shows every row) is the honest answer.
MAX_BARS = 12

#: Below this a "chart" has nothing to compare - a single bar is a Metric,
#: not a series.
MIN_BARS = 2


def _is_measure(value: Any) -> bool:
	"""True for anything chartable as a bar height: plain `int`/`float`,
	numpy's `int64`/`float64` (both register against `numbers.Number` per
	PEP 3141), and `Decimal`. `bool` is excluded despite `bool` being a
	subclass of `int` in Python - a true/false column is not a measure."""
	return isinstance(value, numbers.Number) and not isinstance(value, bool)


def pick(columns: list[str], rows: list[dict[str, Any]]) -> dict[str, Any] | None:
	"""Infer a bar-chart series from a pipeline result, or `None` if the
	shape does not support one.

	Requires exactly two columns, `MIN_BARS`-`MAX_BARS` rows, and every row
	agreeing on which column is numeric - a column that mixes types across
	rows is not a measure column, and two numeric (or two non-numeric)
	columns leave no honest way to pick which is the measure.
	"""
	if len(columns) != 2 or not (MIN_BARS <= len(rows) <= MAX_BARS):
		return None

	measure_col: str | None = None
	label_col: str | None = None
	for col in columns:
		if all(_is_measure(row.get(col)) for row in rows):
			if measure_col is not None:
				return None  # two numeric columns - ambiguous which is the measure
			measure_col = col
		else:
			if label_col is not None:
				return None  # two non-numeric columns - no measure at all
			label_col = col

	if measure_col is None or label_col is None:
		return None

	return {"series": [{"label": str(row[label_col]), "value": float(row[measure_col])} for row in rows]}


#: Frappe fieldtype -> `flint-chart` semantic type. Deliberately partial: a
#: fieldtype with no honest mapping (`Text Editor`, `Attach`, `Password`,
#: `Table`) is *absent*, so flint falls back to inferring from values rather
#: than being told something false.
#:
#: `Select` -> `Category`, not `Status`: flint colours `Status` on a good/bad
#: ordinal, and plenty of Frappe Selects (`gender`, `naming_series`) carry no
#: sentiment. `Int` -> `Number`, not `Count`: `Count` claims the column counts
#: things, which is true of an aggregate and false of `idx`.
FIELDTYPE_SEMANTICS = {
	"Currency": "Amount",
	"Percent": "Percentage",
	"Float": "Quantity",
	"Int": "Number",
	"Long Int": "Number",
	"Rating": "Score",
	"Duration": "Duration",
	"Date": "Date",
	"Datetime": "DateTime",
	"Time": "Time",
	"Check": "Boolean",
	"Select": "Category",
	"Autocomplete": "Category",
	"Link": "Name",
	"Dynamic Link": "Name",
	"Data": "Name",
}

#: Aggregates whose result counts rows rather than summing a column's own
#: units. `count_distinct(voucher_no)` is a `Count`, not a `Name`.
COUNTING_FUNCTIONS = frozenset({"count", "count_distinct"})


def _expr_column(expr: Any) -> str | None:
	"""The first `{"col": X}` in an expression tree, depth-first."""
	if isinstance(expr, Mapping):
		col = expr.get("col")
		if isinstance(col, str):
			return col
		for arg in expr.get("args") or ():
			found = _expr_column(arg)
			if found:
				return found
	return None


def _measure_exprs(operations: Any) -> dict[str, Any]:
	"""`{output column: expression}` for every `summarize` key and measure.

	`summarize` renames columns, so a result's column names are frequently
	measure names (`total`, `m0`) that match no fieldname anywhere. A later
	`summarize` shadows an earlier one, which is exactly the grain in scope.
	"""
	out: dict[str, Any] = {}
	for op in operations or ():
		if not isinstance(op, Mapping) or op.get("type") != "summarize":
			continue
		for entry in (*(op.get("by") or ()), *(op.get("measures") or ())):
			if isinstance(entry, Mapping) and isinstance(entry.get("name"), str):
				out[entry["name"]] = entry.get("expr")
	return out


def annotate(
	columns: list[str], fields: Mapping[str, tuple[str | None, str | None]], operations: Any = None
) -> tuple[dict[str, str], dict[str, str]]:
	"""`(semantic_types, field_display_names)` for a result.

	`fields` maps a fieldname to `(fieldtype, label)`. Pure - no Frappe, no
	site; `semantics()` below is the wrapper that reads the real metas.

	A column resolves in three steps: its own fieldname, else the first column
	inside the `summarize` expression that produced it, else it is omitted. An
	aggregate inherits its argument's meaning (`sum(grand_total)` is an
	`Amount`) but not its label - "Grand Total" is the wrong axis title for a
	total of many rows - except when the outer function counts, in which case
	the result is a `Count` whatever it counted.
	"""
	exprs = _measure_exprs(operations)
	types: dict[str, str] = {}
	display: dict[str, str] = {}

	for col in columns:
		field = fields.get(col)
		if field is not None:
			semantic = FIELDTYPE_SEMANTICS.get(field[0] or "")
			if semantic:
				types[col] = semantic
			if field[1]:
				display[col] = field[1]
			continue

		if col not in exprs:
			continue
		expr = exprs[col]
		if isinstance(expr, Mapping) and expr.get("fn") in COUNTING_FUNCTIONS:
			types[col] = "Count"
			continue
		inner = _expr_column(expr)
		semantic = FIELDTYPE_SEMANTICS.get((fields.get(inner) or (None, None))[0] or "") if inner else None
		if semantic:
			types[col] = semantic

	return types, display


def semantics(
	columns: list[str], operations: Any, queries: Any = None
) -> tuple[dict[str, str], dict[str, str]]:
	"""`annotate()` against this site's real DocType metas.

	The division of labour `flint-chart` makes possible: only Frappe knows a
	column is a `Currency` and that its axis reads "Grand Total", so meaning is
	resolved here and geometry is left to the browser. Every other flint host
	recovers semantic types by sniffing values; Frappe declared them at design
	time.

	Never raises. An unresolvable pipeline yields `({}, {})` and flint infers,
	which is the same graceful-absence contract `pick()` has.
	"""
	import frappe

	from nakhoda.engine.operations import source_tables

	try:
		tables = source_tables(operations, queries)
	except Exception:
		return {}, {}

	fields: dict[str, tuple[str | None, str | None]] = {}
	for table in tables:
		doctype = table[3:] if table.startswith("tab") else table
		try:
			meta = frappe.get_meta(doctype)
		except Exception:
			continue
		for df in meta.fields:
			if not df.fieldname:
				continue
			# First table wins: a join's two `name` columns are renamed by the
			# grammar, so a collision here is between fields that mean the same
			# thing anyway.
			fields.setdefault(df.fieldname, (df.fieldtype, df.label))

	return annotate(columns, fields, operations)
