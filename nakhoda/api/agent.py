# Copyright (c) 2026, Nakhoda and contributors
# For license information, please see license.txt
"""The agent's whitelisted surface.

`ask` answers one question; `converse` spends several steps on one prompt and
may propose a dashboard change (`agent/thread.py`). Neither raises for a
model's mistake - both return a dict carrying the failure - so the only
`throw` here is the permission check `converse` owes its dashboard, which is a
refusal rather than a result.

`run_chart` re-executes what one already-answered question ran. A written
report refers to its own evidence by `chart://<agent run>` rather than by
embedding rows, so the numbers a reader sees are computed under *that
reader's* permissions at the moment they read - a report shared with someone
who may not see a cost centre shows them nothing for it, instead of a
snapshot taken under the author's grants."""

from __future__ import annotations

from typing import Any

import frappe

from nakhoda.agent import charts
from nakhoda.agent.manager import _resolve_source
from nakhoda.agent.manager import ask as ask_agent
from nakhoda.agent.thread import converse as converse_agent
from nakhoda.api import run as run_pipeline
from nakhoda.nakhoda.doctype.nakhoda_query.nakhoda_query import provider as query_provider


@frappe.whitelist()
def ask(
	question: str, space: str | None = None, data_source: str | None = None, limit: int | None = None
) -> dict[str, Any]:
	"""Answer a question as the current user. See `agent/manager.py:ask`."""
	return ask_agent(
		question, space=space or None, data_source=data_source or None, limit=int(limit) if limit else None
	)


@frappe.whitelist()
def converse(question: str, dashboard: str | None = None, space: str | None = None) -> dict[str, Any]:
	"""Spend a bounded loop on one prompt. See `agent/thread.py:converse`.

	`read` on the dashboard is checked here rather than only inside the loop:
	this endpoint can cause writes (`Nakhoda Thread Turn`, and a
	`Nakhoda Agent Run` per question the loop asks), and a caller who cannot
	read the dashboard must not be able to make those rows exist by naming it -
	`rule://frappe-app-standards`. The loop checks again on the document it
	actually loads; a name that turns out not to exist is that check's refusal,
	not this one's."""
	if dashboard:
		frappe.has_permission("Nakhoda Intelligence Template", doc=dashboard, throw=True)
	return converse_agent(question, dashboard=dashboard or None, space=space or None)


@frappe.whitelist()
def get_thread_turn(name: str) -> dict[str, Any]:
	"""The persisted turn, mirroring how the browser already fetches a
	`Nakhoda Agent Run` before showing an answer. `if_owner` on
	`Nakhoda Thread Turn` scopes this to whoever asked."""
	doc = frappe.get_doc("Nakhoda Thread Turn", name)
	doc.check_permission("read")
	return doc.as_dict()


@frappe.whitelist()
def run_chart(agent_run: str, limit: int | None = None) -> dict[str, Any]:
	"""Re-run the pipeline behind one answer and return flint's input shape.

	The source is resolved the same way the answer resolved it - the verified
	query's own source when one matched, otherwise the space's - because an
	`Nakhoda Agent Run` records the operations it ran but not where it ran
	them, and guessing `default_source()` for a verified answer would draw a
	chart from the wrong warehouse.
	"""
	doc = frappe.get_doc("Nakhoda Agent Run", agent_run)
	doc.check_permission("read")
	ops = frappe.parse_json(str(doc.get("operations") or "[]"))
	if not ops:
		frappe.throw(frappe._("That answer ran no pipeline, so there is nothing to draw."))

	matched = str(doc.get("matched_verified_query") or "")
	space = doc.get("space")
	source = str(
		frappe.get_cached_value("Nakhoda Verified Query", matched, "data_source")
		if matched
		else _resolve_source(str(space) if space else None, None)
	)
	result = run_pipeline(operations=ops, data_source=source, limit=int(limit) if limit else None)
	semantic_types, field_display_names = charts.semantics(result["columns"], ops, query_provider(source))
	return {
		**result,
		"title": doc.get("question"),
		"chart_type": None,
		"semantic_types": semantic_types,
		"field_display_names": field_display_names,
	}
