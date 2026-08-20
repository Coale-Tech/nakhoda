# Copyright (c) 2026, Nakhoda and contributors
# For license information, please see license.txt
"""The `DashboardPatch` surface, plus panel execution.

`apply_dashboard_patch`/`revert_dashboard_patch` are thin wrappers over
`NakhodaIntelligenceTemplate.apply_patch`/`revert` (`engine/dashboard.py` has
the grammar, validation and diffing; the doctype method has the admin gate and
the `Nakhoda Dashboard Version` bookkeeping; there is nothing left for this
file to do beyond resolving `dashboard_name` to a document and returning what
the method returns).

`panel_data` is the third endpoint, and the reason a panel can be drawn at
all: `api/templates.py:get_dashboard_data` computes the metric strip in one
execution but never touches `panels[]`, so until now every chart on a
dashboard had a layout, a title and no numbers. It deliberately reuses that
function's execution path - `for_connector` resolver, `pipeline.run`, the
settings' cache TTL and row cap - rather than growing a second one, so row and
column policies and caching apply identically to a panel and a metric.
"""

from __future__ import annotations

from typing import Any

import frappe
from frappe import _

from nakhoda.agent import charts
from nakhoda.engine import cache, pipeline
from nakhoda.engine.dashboard import normalise
from nakhoda.engine.permissions import for_connector
from nakhoda.nakhoda.doctype.nakhoda_query.nakhoda_query import provider as query_provider

DOCTYPE = "Nakhoda Intelligence Template"


@frappe.whitelist()
def apply_dashboard_patch(
	dashboard_name: str, ops: list[dict] | str, thread_turn: str | None = None
) -> dict[str, Any]:
	"""Validate and apply `ops` to `dashboard_name`'s panels. Returns the diff
	the approval screen renders plus the `Nakhoda Dashboard Version` name a
	caller passes to `revert_dashboard_patch` later. Raises on an op the
	closed grammar has no member for, or on an `i` naming no item on the
	dashboard - see `engine/dashboard.py:PatchError`.

	`thread_turn` names the loop turn that proposed this patch, if one did, so
	the proposal and the version it became are one record rather than two
	unrelated rows an auditor has to correlate by timestamp. Stamped the same
	way `agent/thread.py:_record` links its runs: `read` proves ownership
	(`if_owner` on `Nakhoda Thread Turn`), and the write is a field set on a
	read-only audit field the approver is not otherwise granted."""
	doc = frappe.get_doc("Nakhoda Intelligence Template", dashboard_name)
	result = doc.apply_patch(frappe.parse_json(ops) if isinstance(ops, str) else ops)
	if thread_turn:
		frappe.get_doc("Nakhoda Thread Turn", thread_turn).check_permission("read")
		frappe.db.set_value(
			"Nakhoda Thread Turn", thread_turn, "applied_version", result["version"], update_modified=False
		)
	return result


@frappe.whitelist()
def revert_dashboard_patch(dashboard_name: str, version_name: str) -> None:
	"""Restore `dashboard_name`'s panels to what they were immediately before
	`version_name`'s patch applied.

	Any turn pointing at that version stops pointing at it: the field means
	"this proposal is live on the dashboard", and after a revert it is not.
	Cleared by filter rather than per row because the reverted version is
	already the caller's to undo - the admin gate is on `revert` above."""
	doc = frappe.get_doc("Nakhoda Intelligence Template", dashboard_name)
	doc.revert(version_name)
	frappe.db.set_value(
		"Nakhoda Thread Turn",
		{"applied_version": version_name},
		"applied_version",
		None,
		update_modified=False,
	)


def _panel(panels: list[dict], panel_id: str) -> dict:
	for panel in panels:
		if panel.get("i") == panel_id and not panel.get("removed"):
			return panel
	frappe.throw(_("No panel {0} on this dashboard").format(panel_id), frappe.DoesNotExistError)
	raise AssertionError  # unreachable; `frappe.throw` raises


def _metric_expr(doc, measure: str | None) -> Any:
	"""The expression behind a shipped panel's `measure`, which `normalise` has
	already reduced to a `Nakhoda Intelligence Metric` slug. Absent when the
	panel names a metric this dashboard no longer carries - the panel then
	plots its query's own shape rather than throwing, the same graceful
	absence `get_dashboard_data` gives a malformed metric."""
	if not measure:
		return None
	for row in doc.get("metrics") or []:
		if frappe.scrub(row.get("label") or "") == measure or row.get("label") == measure:
			return frappe.parse_json(row.get("expression"))
	return None


def _summarize(dimension: str | None, measure_name: str | None, expr: Any) -> dict | None:
	"""One `summarize` step from a panel's `dimension`/`measure`, or `None`
	when the panel names neither and its query already produces the shape to
	plot.

	A bare `measure` column is summed: a panel is a chart, so its measure is
	per-group, and `sum` is the only aggregate that preserves the column's own
	units. A metric row carries its own expression and is used verbatim - that
	expression is what the metric strip already computes.
	"""
	if not dimension and not measure_name:
		return None
	step: dict[str, Any] = {"type": "summarize"}
	if dimension:
		step["by"] = [{"name": dimension, "expr": {"col": dimension}}]
	if measure_name:
		step["measures"] = [
			{"name": measure_name, "expr": expr or {"fn": "sum", "args": [{"col": measure_name}]}}
		]
	return step


@frappe.whitelist()
def panel_data(dashboard_name: str, panel_id: str, limit: int | None = None) -> dict[str, Any]:
	"""Run one panel and return exactly what `flint-chart` needs to draw it.

	Two panel shapes, one execution path:

	* a panel naming a `Nakhoda Query` runs that query's operations, plus a
	  `summarize` built from its `dimension`/`measure` when it has them;
	* a shipped panel (no `query`) runs the dashboard's own `source` verified
	  query, plus the metric expression its `measure` resolves to.

	Both go through `pipeline.run` with the caller's `for_connector` resolver,
	so a user who may not read a column does not get it here either, and the
	result is cached under the same TTL as every other execution surface.
	"""
	doc = frappe.get_doc(DOCTYPE, dashboard_name)
	doc.check_permission("read")
	panels = normalise(frappe.parse_json(doc.get("panels") or "[]"), doc.get("metrics") or [])
	panel = _panel(panels, panel_id)

	if panel.get("query"):
		query = frappe.get_doc("Nakhoda Query", panel["query"])
		query.check_permission("read")
		base, data_source = frappe.parse_json(query.get("operations")), query.get("data_source")
		expr = None
	else:
		if not doc.get("source"):
			frappe.throw(_("No source query configured"))
		query = frappe.get_doc("Nakhoda Verified Query", doc.get("source"))
		query.check_permission("read")
		base, data_source = frappe.parse_json(query.get("operations")), query.get("data_source")
		expr = _metric_expr(doc, panel.get("measure"))

	step = _summarize(panel.get("dimension"), panel.get("measure"), expr)
	ops = [*base, step] if step else list(base)

	settings = frappe.get_cached_doc("Nakhoda Settings")
	source = frappe.get_cached_doc("Nakhoda Data Source", data_source)
	connector = source.connector()
	queries = query_provider(str(data_source))
	result = pipeline.run(
		ops,
		for_connector(connector, str(frappe.session.user)),
		connector,
		cap=int(limit or settings.get("max_rows") or 100_000),
		ttl=int(settings.get("cache_ttl") or cache.DEFAULT_TTL),
		queries=queries,
	)

	columns = list(result.frame.columns)
	semantic_types, field_display_names = charts.semantics(columns, ops, queries)
	return {
		"columns": columns,
		"rows": result.frame.to_dict(orient="records"),
		"row_count": len(result.frame),
		"chart_type": panel.get("chart_type"),
		"title": panel.get("title"),
		"semantic_types": semantic_types,
		"field_display_names": field_display_names,
		"execution_time": result.elapsed,
	}
