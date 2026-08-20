# Copyright (c) 2026, Nakhoda and contributors
# For license information, please see license.txt
"""Many steps per prompt, one closed action set.

`agent/manager.py` answers exactly one question and stops. That is the right
shape for the ask box and the wrong shape for a dashboard: "why did margin
drop in Q3, and put the answer on the board" is three questions, a comparison
and a chart. This module is the loop that spends several steps on one prompt -
and the discipline that keeps a loop from becoming an unbounded agent.

Four actions and nothing else (`docs/plan/16-agentic-dashboards.md` §5.4), the
same closed-grammar move `engine/operations.py` makes for the query pipeline
and `engine/dashboard.py` makes for patches, applied to a third surface:

    ask_data       delegate one question to `manager.ask()`
    propose_patch  validate + diff a `DashboardPatch`; never applies it
    write_report   finish with markdown
    reply          finish with a sentence

A model cannot emit `run_sql`, `write_row` or `install_app` here, because the
envelope parser has no name for them - not because a filter caught a keyword.

Three bounds, all of them because an unbounded loop is a billing and
context-window bug rather than a smarter agent:

* **Steps.** `MAX_STEPS` reasoning turns, `MAX_DATA_STEPS` of which may query.
  Exhausting the budget yields `status="budget"` carrying whatever was learned,
  never a silent truncation.
* **Observations.** `ask_data` feeds back columns, `row_count` and
  `SAMPLE_ROWS` rows - never the frame. The full answer stays reachable through
  the `Nakhoda Agent Run` the step names.
* **Quota.** Every `ask_data` is a real answered question and is counted by
  `manager.ask` itself; the loop's own reasoning costs one more on top. A loop
  that can spend six times a user's quota per prompt without saying so is a
  billing bug.

Nothing here elevates permission (invariant 2): `ask_data` runs as
`frappe.session.user` through the same `manager.ask`, so row and column
policies are injected exactly as they are for a single question, and
`propose_patch` produces a diff for a human to approve rather than a write.
"""

from __future__ import annotations

import json
import time
from typing import Any

import frappe

from nakhoda.agent import manager, providers, quota
from nakhoda.agent.router import route
from nakhoda.agent.tiers import Tier
from nakhoda.agent.tiers import models as tier_models
from nakhoda.bench.driver import _fenced as fenced
from nakhoda.bench.driver import repair as driver_repair
from nakhoda.engine.dashboard import PatchError, apply_patch, normalise, validate_patch
from nakhoda.engine.operations import source_tables
from nakhoda.nakhoda.doctype.nakhoda_query.nakhoda_query import provider as query_provider
from nakhoda.semantic.retrieval import build_index
from nakhoda.semantic.retrieval import context as semantic_context

#: Reasoning turns per prompt, and how many of them may query. Six and three
#: are the numbers the plan fixes; they are budgets, not tuning knobs - raising
#: them raises what one prompt can cost.
MAX_STEPS = 6
MAX_DATA_STEPS = 3

#: Rows fed back from an `ask_data` answer. Five is enough to see the shape of
#: a result and reason about the next question; the frame itself stays in the
#: `Nakhoda Agent Run` the observation names.
SAMPLE_ROWS = 5

#: Consecutive rate-limits before the loop stops trying, mirroring
#: `manager.RATE_LIMIT_CIRCUIT` - the same provider, the same reason.
RATE_LIMIT_CIRCUIT = manager.RATE_LIMIT_CIRCUIT

ACTIONS = ("ask_data", "propose_patch", "write_report", "reply")

#: The three that end the turn. `ask_data` is the only action that continues,
#: which is what makes the step budget a bound rather than a suggestion.
TERMINAL = frozenset({"propose_patch", "write_report", "reply"})

_MENU = """Reply with ONE JSON object naming ONE action.

{"action": "ask_data", "question": "<one question in plain English>"}
    Ask the data one question. You get back its columns, row count and a few
    sample rows. Use this before asserting anything about the numbers.

{"action": "propose_patch", "ops": [<patch ops>]}
    Propose a change to the dashboard. It is shown to a human for approval and
    is NOT applied by you. Ends the turn. The ops are exactly three:
      {"op": "add_chart", "chart_type": "bar", "query": "<an existing query>",
       "layout": {"x": 0, "y": 0, "w": 10, "h": 8},
       "title": "...", "dimension": "...", "measure": "..."}
      {"op": "set_filter", "i": "<panel id>", "column": "...",
       "operator": "=|!=|>|>=|<|<=|between|in", "value": ...}
      {"op": "remove_item", "i": "<panel id>"}

{"action": "write_report", "markdown": "<the answer as markdown>"}
    Finish with a written answer. Ends the turn. To show one of the results you
    queried, put its run id on a line of its own as `chart://<agent_run>` -
    the `agent_run` value from that step above. The reader's own permissions
    are applied when it is drawn, so cite a run rather than pasting numbers
    you were shown.

{"action": "reply", "text": "<one or two sentences>"}
    Finish with a short reply. Ends the turn.

There is no other action. If what you want is not here, express the same
intent with what is."""


def _envelope(text: str) -> tuple[dict[str, Any] | None, str | None]:
	"""The action object inside a completion, or why there is none.

	Same fenced-JSON tolerance as `bench/driver.py:extract` - models wrap
	answers in prose whatever the instruction says - and the same refusal
	style: a reason a model can act on, because it is handed straight back
	through `driver.repair`.
	"""
	body = fenced(text).strip()
	if not body:
		return None, "empty completion"
	start, end = body.find("{"), body.rfind("}")
	if start < 0 or end < start:
		return None, "no JSON object in completion"
	try:
		payload = json.loads(body[start : end + 1])
	except json.JSONDecodeError as exc:
		return None, f"invalid JSON: {exc.msg}"
	if not isinstance(payload, dict):
		return None, "JSON is not an object"
	action = payload.get("action")
	if action not in ACTIONS:
		return None, f"'action' must be one of {list(ACTIONS)}, got {action!r}"
	return payload, None


def _complete(text_prompt: str, rate_limits: list[int]) -> tuple[str | None, str | None]:
	"""One model call, degrading across the tier ladder's ids rather than
	failing. Reasoning steps never escalate to `PREMIUM`: escalation exists to
	rescue a *refused pipeline* (`agent/router.py`), and nothing here is
	validated by the engine, so there is no refusal to escalate on - only a
	more expensive opinion."""
	tried: list[str] = []
	for tier in (Tier.FAST, Tier.BALANCED):
		for model in tier_models(tier):
			if model in tried:
				continue
			tried.append(model)
			try:
				return providers.complete(text_prompt, model), None
			except providers.RateLimited as exc:
				rate_limits[0] += 1
				if rate_limits[0] >= RATE_LIMIT_CIRCUIT:
					return None, f"rate limited repeatedly: {exc}"
			except Exception:
				rate_limits[0] = 0
				continue
	if not tried:
		return None, "No AI model is configured (Nakhoda Settings, AI Provider tab)."
	return None, f"every model was unavailable: {', '.join(tried)}"


def _step(text_prompt: str, rate_limits: list[int]) -> tuple[dict[str, Any] | None, str | None]:
	"""One reasoning turn: a completion, parsed, with one repair on malformed
	output and then failing closed. A model that cannot use a precise
	correction will not use a third prompt either - the same budget
	`manager._try_tier` gives a refused pipeline."""
	raw, error = _complete(text_prompt, rate_limits)
	if raw is None:
		return None, error
	envelope, why = _envelope(raw)
	if envelope is not None:
		return envelope, None

	raw, error = _complete(driver_repair(text_prompt, raw, why or ""), rate_limits)
	if raw is None:
		return None, error
	envelope, why = _envelope(raw)
	return envelope, why


def _dashboard(name: str | None) -> tuple[Any, list[dict], list[str], list[dict]]:
	"""`(doc, panels, source_tables, queries)` for a dashboard the caller may
	read, or empties when the prompt is not about one.

	Panels come back canonicalised so the `i` values shown to the model are the
	ones `set_filter` and `remove_item` can actually name (`engine/dashboard.py`,
	`normalise`). `queries` is every `Nakhoda Query` on the same data source:
	`add_chart` must name one that exists, and a model told nothing about them
	invents a name, which `validate_patch` then rejects for the wrong reason.
	"""
	if not name:
		return None, [], [], []
	doc = frappe.get_doc("Nakhoda Intelligence Template", name)
	doc.check_permission("read")
	panels = normalise(frappe.parse_json(str(doc.get("panels") or "[]")), doc.get("metrics") or [])
	source = str(doc.get("source") or "")
	if not source:
		return doc, panels, [], []

	ops = str(frappe.get_cached_value("Nakhoda Verified Query", source, "operations") or "[]")
	data_source = str(frappe.get_cached_value("Nakhoda Verified Query", source, "data_source") or "")
	try:
		tables = source_tables(frappe.parse_json(ops), query_provider(data_source))
	except Exception:
		# An unresolvable source costs the prompt its table list, not the turn:
		# the router below still picks tables for the question itself.
		tables = []
	queries = frappe.get_all(
		"Nakhoda Query", filters={"data_source": data_source}, fields=["name", "title"], limit=50
	)
	return doc, panels, tables, queries


def _prompt(
	question: str,
	*,
	context: str,
	panels: list[dict],
	queries: list[dict],
	skill: str | None,
	instructions: str | None,
	steps: list[dict],
	steps_left: int,
	data_left: int,
) -> str:
	"""The loop's prompt. Everything the closed action set needs to name real
	targets, and nothing else.

	`skill` is `Nakhoda Intelligence Template.skill` - "a playbook fragment
	routed into the agent's prompt", per that field's own description. This is
	the caller that finally makes it true.
	"""
	parts = [
		"You are a data analyst working on a Frappe dashboard.",
		"",
		"The data you can query:",
		context or "(no semantic context available)",
	]
	if panels:
		parts += ["", "Panels currently on this dashboard:", json.dumps(panels, indent=1, default=str)]
	if queries:
		listed = "\n".join(f"  {q['name']}: {q.get('title') or ''}".rstrip() for q in queries)
		parts += ["", "Queries `add_chart` may name:", listed]
	if skill and skill.strip():
		parts += ["", "Playbook for this dashboard:", skill.strip()]
	if instructions and instructions.strip():
		parts += ["", "Standing instructions:", instructions.strip()]
	parts += ["", f"The question:\n{question}"]
	if steps:
		parts += ["", "What you have done so far:", json.dumps(steps, indent=1, default=str)]
	parts += [
		"",
		f"Budget: {steps_left} step(s) left, {data_left} of them may query."
		if data_left
		else f"Budget: {steps_left} step(s) left. You may NOT query again - finish now.",
		"",
		_MENU,
	]
	return "\n".join(parts)


def _observe(question: str, answer: dict[str, Any]) -> dict[str, Any]:
	"""One `ask_data` answer, bounded. The frame is deliberately not here: an
	unbounded transcript is how a loop turns one question into a
	context-window overflow."""
	step: dict[str, Any] = {"action": "ask_data", "question": question, "agent_run": answer.get("agent_run")}
	if answer.get("error"):
		step["error"] = answer["error"]
		return step
	rows = answer.get("rows") or []
	step["columns"] = answer.get("columns") or []
	step["row_count"] = answer.get("row_count", len(rows))
	step["sample"] = rows[:SAMPLE_ROWS]
	if len(rows) > SAMPLE_ROWS:
		step["sample_note"] = f"first {SAMPLE_ROWS} of {step['row_count']} rows"
	return step


def _record(
	question: str,
	*,
	dashboard: str | None,
	space: str | None,
	steps: list[dict],
	runs: list[str],
	status: str,
	started: float,
	report: str | None = None,
	patch_ops: list[dict] | None = None,
	patch_diff: list[dict] | None = None,
	error: str | None = None,
) -> dict[str, Any]:
	"""Persist the turn and point every question it asked back at it.

	Written with `ignore_permissions=True` for the same reason
	`manager._log` is: a caller answering their own prompt should not also need
	`create` on the log of it, and `if_owner` on `Nakhoda Thread Turn` still
	scopes reads to whoever asked.
	"""
	turn = frappe.get_doc(
		{
			"doctype": "Nakhoda Thread Turn",
			"user": frappe.session.user,
			"space": space,
			"dashboard": dashboard,
			"question": question,
			"steps": frappe.as_json(steps) if steps else None,
			"step_count": len(steps),
			"report": report,
			"patch_ops": frappe.as_json(patch_ops) if patch_ops else None,
			"patch_diff": frappe.as_json(patch_diff) if patch_diff else None,
			"status": status,
			"error": error,
			"execution_time": time.monotonic() - started,
		}
	)
	turn.insert(ignore_permissions=True)
	for run in runs:
		# Every SQL statement the loop caused stays its own permission-checked
		# row; this is the only link back to the prompt that caused it.
		frappe.db.set_value("Nakhoda Agent Run", run, "thread_turn", turn.name, update_modified=False)
	out: dict[str, Any] = {"thread_turn": turn.name, "status": status, "steps": steps}
	if report:
		out["report"] = report
	if patch_ops:
		out["patch"] = {"ops": patch_ops, "diff": patch_diff or []}
	if error:
		out["error"] = error
	return out


def converse(question: str, *, dashboard: str | None = None, space: str | None = None) -> dict[str, Any]:
	"""Spend up to `MAX_STEPS` on one prompt. Always returns a dict carrying
	`thread_turn` and `status` - `ok`, `error` or `budget` - never raises for a
	model's mistake, and never applies a patch."""
	question = (question or "").strip()
	started = time.monotonic()
	steps: list[dict] = []
	runs: list[str] = []

	def fail(error: str) -> dict[str, Any]:
		return _record(
			question,
			dashboard=dashboard,
			space=space,
			steps=steps,
			runs=runs,
			status="error",
			started=started,
			error=error,
		)

	if not question:
		return fail("empty question")
	if not providers.enabled():
		return fail("AI is turned off (Nakhoda Settings, AI Provider tab).")
	if not quota.available():
		return fail("The AI request quota for this period is used up (Nakhoda Settings, AI Provider tab).")

	try:
		doc, panels, tables, queries = _dashboard(dashboard)
		index = build_index()
	except frappe.PermissionError:
		raise
	except Exception as exc:
		return fail(str(exc))

	# The dashboard's own tables when it has a source; otherwise the router's
	# structural pick for this question, which is what a bare ask box gets.
	context = semantic_context(tables or route(question, index).tables, index)
	instructions = str(frappe.db.get_value("Nakhoda Space", space, "instructions") or "") if space else ""
	rate_limits = [0]
	data_steps = 0

	for step_no in range(MAX_STEPS):
		steps_left = MAX_STEPS - step_no
		data_left = 0 if steps_left <= 1 else MAX_DATA_STEPS - data_steps
		envelope, why = _step(
			_prompt(
				question,
				context=context,
				panels=panels,
				queries=queries,
				skill=doc.get("skill") if doc else None,
				instructions=instructions,
				steps=steps,
				steps_left=steps_left,
				data_left=max(data_left, 0),
			),
			rate_limits,
		)
		if envelope is None:
			quota.consume()
			return fail(why or "the model produced no action")

		action = envelope["action"]

		if action == "ask_data":
			if data_left <= 0:
				# Refused, not fatal: the model still has steps to finish with,
				# and saying why is what lets it use them.
				steps.append(
					{
						"action": "ask_data",
						"question": envelope.get("question"),
						"error": "the data budget for this turn is spent - finish with a report or a reply",
					}
				)
				continue
			sub = (envelope.get("question") or "").strip()
			if not sub:
				steps.append({"action": "ask_data", "error": "'question' was empty"})
				continue
			data_steps += 1
			answer = manager.ask(sub, space=space)
			if answer.get("agent_run"):
				runs.append(str(answer["agent_run"]))
			steps.append(_observe(sub, answer))
			continue

		if action == "propose_patch":
			try:
				ops = validate_patch(envelope.get("ops"))
				_, diff = apply_patch(panels, ops)
			except PatchError as exc:
				# A malformed patch is correctable, so it is an observation
				# rather than the end of the turn - the same second chance
				# `driver.repair` gives a refused pipeline.
				steps.append({"action": "propose_patch", "error": str(exc)})
				continue
			steps.append({"action": "propose_patch", "ops": ops, "diff": diff})
			quota.consume()
			return _record(
				question,
				dashboard=dashboard,
				space=space,
				steps=steps,
				runs=runs,
				status="ok",
				started=started,
				patch_ops=ops,
				patch_diff=diff,
			)

		text = str(envelope.get("markdown") if action == "write_report" else envelope.get("text") or "")
		if not text.strip():
			steps.append({"action": action, "error": "the answer was empty"})
			continue
		steps.append({"action": action})
		quota.consume()
		return _record(
			question,
			dashboard=dashboard,
			space=space,
			steps=steps,
			runs=runs,
			status="ok",
			started=started,
			report=text,
		)

	# Budget spent. Everything learned is still on the row, and the caller is
	# told which of the three it was rather than being handed a truncated
	# answer that looks finished.
	quota.consume()
	return _record(
		question,
		dashboard=dashboard,
		space=space,
		steps=steps,
		runs=runs,
		status="budget",
		started=started,
		error=f"no answer within {MAX_STEPS} steps",
	)


__all__ = ["ACTIONS", "MAX_DATA_STEPS", "MAX_STEPS", "TERMINAL", "converse"]
