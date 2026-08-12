"""The forty gold questions, expressed in the operation grammar.

`semantic_bench/questions.py` carries each question's gold SQL. This module
carries the same forty as pipelines, so `test_engine.py` can run both and
compare. Two things it is for:

*The Phase 0 gate.* If a pipeline here disagrees with its gold SQL by one row,
the engine is wrong and the gate fails.

*The expressibility claim, made concrete.* The build plan asserts all forty fit
inside seven operations. Assertions in a plan document are not checkable; these
are. Anything that needed an eighth operation would be visible here as a gap.

Column names match the gold SQL's aliases exactly, because the comparison is
positional over named columns and a rename would hide a real difference.
"""

from __future__ import annotations

from typing import Any


def col(name: str) -> dict:
	return {"col": name}


def lit(value: Any) -> dict:
	return {"lit": value}


def fn(name: str, *args: dict) -> dict:
	return {"fn": name, "args": list(args)}


def source(table: str) -> dict:
	return {"type": "source", "table": table}


def where(*conditions: dict) -> dict:
	cond = conditions[0] if len(conditions) == 1 else fn("and", *conditions)
	return {"type": "filter", "where": cond}


def select(**columns: dict) -> dict:
	return {"type": "select", "columns": [{"name": k, "expr": v} for k, v in columns.items()]}


def summarize(measures: dict[str, dict], by: dict[str, dict] | None = None) -> dict:
	return {
		"type": "summarize",
		"by": [{"name": k, "expr": v} for k, v in (by or {}).items()],
		"measures": [{"name": k, "expr": v} for k, v in measures.items()],
	}


def order_by(*keys: tuple[str, bool]) -> dict:
	return {"type": "order_by", "keys": [{"expr": col(name), "desc": desc} for name, desc in keys]}


def limit(n: int) -> dict:
	return {"type": "limit", "n": n}


def join_parent_invoice(*columns: str) -> dict:
	"""Child-table grain: reach the parent Sales Invoice from its line items.

	The `parent`/`parenttype` pair is Frappe's child-table link and carries no
	database foreign key, which is the whole point of the `grain` trap in the
	question set. `parenttype` is not needed here - `tabSales Invoice Item` rows
	only ever belong to a Sales Invoice - but a table shared between parents
	would need it in the predicate.
	"""
	return {
		"type": "join",
		"table": "tabSales Invoice",
		"left_on": col("parent"),
		"right_on": col("name"),
		"how": "inner",
		"select": [{"name": f"si_{c}", "expr": col(c)} for c in columns],
	}


SUBMITTED = fn("eq", col("docstatus"), lit(1))
NOT_RETURN = fn("eq", col("is_return"), lit(0))
SI = "tabSales Invoice"
SII = "tabSales Invoice Item"

#: question id -> pipeline. Keys match `semantic_bench.questions.Q`.
PIPELINES: dict[str, list[dict]] = {
	# -- no trap ------------------------------------------------------------
	"q01": [source("tabCustomer"), summarize({"n": fn("count")})],
	"q02": [source("tabTerritory"), select(name=col("name")), order_by(("name", False))],
	"q03": [
		source("tabItem"),
		where(fn("eq", col("item_group"), lit("Products"))),
		summarize({"n": fn("count")}),
	],
	"q04": [source("tabItem"), summarize({"m": fn("max", col("standard_rate"))})],
	"q05": [source(SI), summarize({"n": fn("count")})],
	# -- docstatus ----------------------------------------------------------
	"q06": [
		source(SI),
		where(SUBMITTED, NOT_RETURN),
		summarize({"total": fn("sum", col("base_grand_total"))}),
	],
	"q07": [source(SI), where(SUBMITTED), summarize({"n": fn("count")})],
	"q08": [
		source(SI),
		where(
			SUBMITTED,
			NOT_RETURN,
			fn("gte", col("posting_date"), fn("date", lit("2025-01-01"))),
			fn("lt", col("posting_date"), fn("date", lit("2026-01-01"))),
		),
		summarize({"total": fn("sum", col("base_grand_total"))}),
	],
	"q09": [
		source(SI),
		where(SUBMITTED, NOT_RETURN),
		summarize({"avg_val": fn("avg", col("base_grand_total"))}),
	],
	"q10": [
		source(SI),
		where(SUBMITTED),
		summarize({"owed": fn("sum", fn("mul", col("outstanding_amount"), col("conversion_rate")))}),
	],
	"q11": [source("tabPayment Entry"), where(SUBMITTED), summarize({"n": fn("count")})],
	"q12": [
		source("tabPayment Entry"),
		where(SUBMITTED),
		summarize({"total": fn("sum", col("base_paid_amount"))}),
	],
	# -- value domain -------------------------------------------------------
	"q13": [
		source(SI),
		where(SUBMITTED, fn("eq", col("status"), lit("Overdue"))),
		summarize({"n": fn("count")}),
	],
	"q14": [
		source(SI),
		where(SUBMITTED, fn("eq", col("status"), lit("Paid"))),
		summarize({"n": fn("count")}),
	],
	"q15": [
		source(SI),
		where(SUBMITTED),
		summarize({"n": fn("count")}, by={"status": col("status")}),
		order_by(("n", True), ("status", False)),
	],
	"q16": [
		source(SI),
		where(SUBMITTED, fn("eq", col("status"), lit("Partly Paid"))),
		summarize({"n": fn("count")}),
	],
	"q17": [source(SI), where(fn("eq", col("docstatus"), lit(0))), summarize({"n": fn("count")})],
	# -- currency -----------------------------------------------------------
	"q18": [
		source(SI),
		where(SUBMITTED, NOT_RETURN),
		summarize({"total": fn("sum", col("base_grand_total"))}),
	],
	"q19": [
		source(SI),
		where(SUBMITTED),
		summarize({"n": fn("count")}, by={"currency": col("currency")}),
		order_by(("n", True), ("currency", False)),
	],
	"q20": [
		source(SI),
		where(SUBMITTED),
		summarize({"total": fn("sum", col("base_grand_total"))}, by={"currency": col("currency")}),
		order_by(("total", True)),
	],
	# -- returns ------------------------------------------------------------
	"q21": [
		source(SI),
		where(SUBMITTED, fn("eq", col("is_return"), lit(1))),
		summarize({"n": fn("count")}),
	],
	"q22": [
		source(SI),
		where(SUBMITTED, NOT_RETURN),
		summarize({"total": fn("sum", col("base_grand_total"))}),
	],
	"q23": [
		source(SI),
		where(SUBMITTED, fn("eq", col("is_return"), lit(1))),
		summarize({"total": fn("abs", fn("sum", col("base_grand_total")))}),
	],
	# -- joins with no foreign key ------------------------------------------
	"q24": [
		source(SI),
		where(SUBMITTED, NOT_RETURN),
		summarize({"total": fn("sum", col("base_grand_total"))}, by={"territory": col("territory")}),
		order_by(("total", True)),
		limit(1),
	],
	"q25": [
		source(SI),
		where(SUBMITTED, NOT_RETURN),
		summarize({"total": fn("sum", col("base_grand_total"))}, by={"territory": col("territory")}),
		order_by(("total", True)),
	],
	"q26": [
		source(SI),
		{
			"type": "join",
			"table": "tabCustomer",
			"left_on": col("customer"),
			"right_on": col("name"),
			"how": "inner",
			"select": [{"name": "cust_territory", "expr": col("territory")}],
		},
		where(SUBMITTED, fn("eq", col("cust_territory"), lit("Germany"))),
		summarize({"total": fn("sum", col("base_grand_total"))}, by={"customer": col("customer")}),
		order_by(("total", True)),
	],
	"q27": [
		source(SI),
		{
			"type": "join",
			"table": "tabCustomer",
			"left_on": col("customer"),
			"right_on": col("name"),
			"how": "inner",
			"select": [{"name": "cust_disabled", "expr": col("disabled")}],
		},
		where(SUBMITTED, fn("eq", col("cust_disabled"), lit(0))),
		summarize({"n": fn("count_distinct", col("customer"))}),
	],
	"q28": [
		source("tabTerritory"),
		where(fn("eq", col("parent_territory"), lit("India"))),
		select(name=col("name")),
		order_by(("name", False)),
	],
	# -- child-table grain --------------------------------------------------
	"q29": [
		source(SII),
		join_parent_invoice("docstatus", "is_return"),
		where(
			fn("eq", col("si_docstatus"), lit(1)),
			fn("eq", col("si_is_return"), lit(0)),
		),
		summarize({"units": fn("sum", col("qty"))}, by={"item_code": col("item_code")}),
		order_by(("units", True)),
		limit(1),
	],
	"q30": [
		source(SII),
		join_parent_invoice("docstatus"),
		where(fn("eq", col("si_docstatus"), lit(1))),
		summarize({"revenue": fn("sum", col("base_amount"))}, by={"item_code": col("item_code")}),
		order_by(("revenue", True)),
		limit(5),
	],
	"q31": [
		source(SII),
		join_parent_invoice("docstatus"),
		where(fn("eq", col("si_docstatus"), lit(1))),
		summarize({"n": fn("count")}),
	],
	"q32": [
		source(SII),
		join_parent_invoice("docstatus"),
		where(fn("eq", col("si_docstatus"), lit(1))),
		summarize(
			{
				"avg_lines": fn(
					"div",
					fn("mul", fn("count"), lit(1.0)),
					fn("count_distinct", col("parent")),
				)
			}
		),
	],
	"q33": [
		source(SII),
		join_parent_invoice("docstatus"),
		where(fn("eq", col("si_docstatus"), lit(1))),
		summarize({"revenue": fn("sum", col("base_amount"))}, by={"item_group": col("item_group")}),
		order_by(("revenue", True)),
	],
	"q34": [
		source(SII),
		join_parent_invoice("docstatus", "territory"),
		where(
			fn("eq", col("si_docstatus"), lit(1)),
			fn("eq", col("si_territory"), lit("Karnataka")),
		),
		summarize({"revenue": fn("sum", col("base_amount"))}, by={"item_group": col("item_group")}),
		order_by(("revenue", True)),
		limit(1),
	],
	# -- id vs display label -------------------------------------------------
	"q35": [
		source(SI),
		where(SUBMITTED, NOT_RETURN),
		summarize(
			{"total": fn("sum", col("base_grand_total"))},
			by={"customer_name": col("customer_name")},
		),
		order_by(("total", True)),
		limit(3),
	],
	# Order and truncate first, then project: `order_by` may only name columns
	# in scope, and `standard_rate` leaves scope the moment `select` runs.
	"q36": [
		source("tabItem"),
		order_by(("standard_rate", True)),
		limit(3),
		select(item_name=col("item_name")),
	],
	# -- combined -------------------------------------------------------------
	"q37": [
		source(SI),
		where(SUBMITTED, NOT_RETURN, fn("gte", col("posting_date"), fn("date", lit("2026-01-01")))),
		summarize(
			{"total": fn("sum", col("base_grand_total"))},
			by={"month": fn("date_trunc", lit("month"), col("posting_date"))},
		),
		order_by(("month", False)),
	],
	"q38": [
		source(SI),
		where(SUBMITTED, fn("gte", col("posting_date"), fn("date", lit("2026-01-01")))),
		summarize({"total": fn("sum", col("base_grand_total"))}),
	],
	"q39": [
		source(SI),
		where(SUBMITTED, NOT_RETURN),
		summarize({"avg_val": fn("avg", col("base_grand_total"))}, by={"territory": col("territory")}),
		order_by(("avg_val", True)),
	],
	"q40": [
		source(SII),
		join_parent_invoice("docstatus"),
		where(fn("eq", col("si_docstatus"), lit(1))),
		summarize(
			{"n": fn("count_distinct", col("item_code"))},
			by={"item_group": col("item_group")},
		),
		order_by(("n", True), ("item_group", False)),
	],
}
