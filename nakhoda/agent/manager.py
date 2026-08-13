# Copyright (c) 2026, Nakhoda and contributors
# For license information, please see license.txt
"""One question in, one `Nakhoda Agent Run` out. Never raises to the caller
(`12-build-plan.md` Phase 4, point 3) - every terminal state is a value
carrying `error` instead.

The loop is deliberately not a multi-turn ReAct agent. The grammar is closed
and the benchmark that measured 95.8%/95.0% (`00-REPORT.md` §6.2) did it with
one completion per question, not a tool-calling conversation - there is no
tool-selection ambiguity for a loop to resolve, only a pipeline to emit and
validate. Adding a turn loop here would be new, unmeasured surface with
nothing in `13-agent-design.md` to justify it.

Compilation, permission injection and execution are not reimplemented here.
`nakhoda.api.run` already is "safe for a model" by construction
(`api/__init__.py`'s own docstring); calling it in-process is one source of
truth for what a pipeline is allowed to touch, and a `frappe.ValidationError`
out of it is how this module learns a generated pipeline does not compile -
the only trigger this app uses to escalate a tier.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

import frappe

from nakhoda.agent import providers, verified
from nakhoda.agent.router import Route, route
from nakhoda.agent.tiers import LADDER, Tier
from nakhoda.agent.tiers import models as tier_models
from nakhoda.api import default_source, execute_verified
from nakhoda.api import run as run_pipeline
from nakhoda.bench.driver import extract
from nakhoda.bench.driver import prompt as build_prompt
from nakhoda.semantic import model as semantic_model
from nakhoda.semantic.retrieval import build_index

#: Three consecutive rate-limits, anywhere in the ladder, and the manager stops
#: trying rather than keep burning the circuit breaker's namesake quota
#: (`12-build-plan.md` Phase 4, point 3).
RATE_LIMIT_CIRCUIT = 3


class Outcome(Enum):
	OK = "ok"
	#: The pipeline failed to parse or to validate - a quality signal. The only
	#: outcome this module escalates a tier for.
	INVALID = "invalid"
	#: Every model in the tier errored or none is configured - an availability
	#: signal, handled by moving on rather than by trying harder here.
	UNAVAILABLE = "unavailable"
	CIRCUIT_OPEN = "circuit_open"


@dataclass
class Attempt:
	outcome: Outcome
	model: str | None = None
	ops: list | None = None
	result: dict[str, Any] | None = None
	detail: str | None = None


def _try_tier(
	tier: Tier, text_prompt: str, rate_limits: list[int], *, data_source: str, limit: int | None
) -> Attempt:
	"""Every model configured for one tier, in order. Returns the first that
	produces a pipeline `nakhoda.api.run` accepts; short of that, the first
	validation failure seen beats a plain unavailability, because a failure
	that names what is wrong is the more useful thing to escalate on."""
	candidates = tier_models(tier)
	if not candidates:
		return Attempt(Outcome.UNAVAILABLE, detail=f"no model configured for tier {tier.value}")

	invalid: Attempt | None = None
	for model in candidates:
		try:
			raw = providers.complete(text_prompt, model)
		except providers.RateLimited as exc:
			rate_limits[0] += 1
			if rate_limits[0] >= RATE_LIMIT_CIRCUIT:
				return Attempt(Outcome.CIRCUIT_OPEN, model=model, detail=str(exc))
			continue
		except Exception:
			# Any other provider failure - misconfiguration, network, an SDK this
			# module has never seen - is unavailability, not a crash. Degrade
			# never fail is unconditional at this boundary.
			rate_limits[0] = 0
			continue

		rate_limits[0] = 0
		ops, err = extract(raw, "ops")
		if err:
			invalid = invalid or Attempt(Outcome.INVALID, model=model, detail=err)
			continue
		try:
			result = run_pipeline(operations=json.dumps(ops), data_source=data_source, limit=limit)
		except frappe.ValidationError as exc:
			invalid = invalid or Attempt(Outcome.INVALID, model=model, ops=ops, detail=str(exc))
			continue
		return Attempt(Outcome.OK, model=model, ops=ops, result=result)

	if invalid:
		return invalid
	return Attempt(Outcome.UNAVAILABLE, detail=f"every model in tier {tier.value} was unavailable")


def _resolve_source(space: str | None, data_source: str | None) -> str:
	if data_source:
		return data_source
	if space:
		space_doc = frappe.get_doc("Nakhoda Space", space)
		space_doc.check_permission("read")
		return space_doc.resolve_source()
	return default_source()


def _log(user: str | None, space: str | None, question: str, **fields: Any):
	doc = frappe.get_doc(
		{"doctype": "Nakhoda Agent Run", "user": user, "space": space, "question": question, **fields}
	)
	# An audit log the caller cannot write is still owed to the caller who
	# asked - the same reasoning `Error Log` and `Activity Log` already use.
	# `if_owner` on `Nakhoda Agent Run` still scopes reads to `owner`, which
	# Frappe sets to `frappe.session.user` regardless of this flag.
	doc.insert(ignore_permissions=True)
	return doc


def ask(
	question: str, *, space: str | None = None, data_source: str | None = None, limit: int | None = None
) -> dict[str, Any]:
	"""Answer one question as `frappe.session.user` (invariant 2: never
	elevate). Always returns a dict with either the result shape
	`nakhoda.api.run`/`execute_verified` produce, plus `agent_run`, or
	`{"error": ..., "agent_run": ...}`."""
	user = frappe.session.user
	question = (question or "").strip()
	started = time.monotonic()

	if not question:
		run = _log(user, space, "", status="error", error="empty question")
		return {"error": "empty question", "agent_run": run.name}

	matched = verified.match(question)
	if matched:
		try:
			result = execute_verified(matched, limit=limit)
		except Exception as exc:
			run = _log(
				user,
				space,
				question,
				source="verified",
				matched_verified_query=matched,
				status="error",
				error=str(exc),
				execution_time=time.monotonic() - started,
			)
			return {"error": str(exc), "agent_run": run.name}
		run = _log(
			user,
			space,
			question,
			source="verified",
			matched_verified_query=matched,
			status="ok",
			operations=frappe.db.get_value("Nakhoda Verified Query", matched, "operations"),
			sql=result.get("sql"),
			row_count=result.get("row_count"),
			execution_time=time.monotonic() - started,
		)
		return {**result, "agent_run": run.name}

	try:
		source_name = _resolve_source(space, data_source)
	except Exception as exc:
		run = _log(user, space, question, status="error", error=str(exc))
		return {"error": str(exc), "agent_run": run.name}

	try:
		index = build_index()
	except Exception as exc:
		run = _log(user, space, question, status="error", error=f"could not build the semantic index: {exc}")
		return {"error": str(exc), "agent_run": run.name}

	initial: Route = route(question, index)
	context = semantic_model.render(
		[semantic_model.describe(frappe.get_meta(name)) for name in initial.tables]
	)
	text_prompt = build_prompt(context, question, "ops")

	rate_limits = [0]
	escalation_reason: str | None = None
	degradation_reason: str | None = None
	final: Attempt | None = None
	used_tier = initial.tier

	for tier in LADDER[LADDER.index(initial.tier) :]:
		attempt = _try_tier(tier, text_prompt, rate_limits, data_source=source_name, limit=limit)
		if attempt.outcome is Outcome.OK:
			final = attempt
			used_tier = tier
			break
		if attempt.outcome is Outcome.CIRCUIT_OPEN:
			error = f"rate limited repeatedly: {attempt.detail}"
			run = _log(
				user,
				space,
				question,
				status="error",
				error=error,
				tier=initial.tier.value,
				tier_reason=initial.reason,
				execution_time=time.monotonic() - started,
			)
			return {"error": error, "agent_run": run.name}
		if attempt.outcome is Outcome.INVALID:
			escalation_reason = escalation_reason or attempt.detail
		elif attempt.outcome is Outcome.UNAVAILABLE:
			degradation_reason = degradation_reason or attempt.detail

	if final is None:
		error = escalation_reason or degradation_reason or "no model available"
		run = _log(
			user,
			space,
			question,
			status="error",
			error=error,
			tier=initial.tier.value,
			tier_reason=initial.reason,
			escalated=bool(escalation_reason),
			escalation_reason=escalation_reason,
			degraded=bool(degradation_reason),
			degradation_reason=degradation_reason,
			execution_time=time.monotonic() - started,
		)
		return {"error": error, "agent_run": run.name}

	escalated = used_tier != initial.tier and escalation_reason is not None
	degraded = degradation_reason is not None
	result = final.result or {}
	run = _log(
		user,
		space,
		question,
		source="generated",
		status="ok",
		tier=used_tier.value,
		tier_reason=initial.reason,
		model=final.model,
		escalated=escalated,
		escalation_reason=escalation_reason if escalated else None,
		degraded=degraded,
		degradation_reason=degradation_reason if degraded else None,
		operations=frappe.as_json(final.ops or []),
		sql=result.get("sql"),
		row_count=result.get("row_count"),
		execution_time=time.monotonic() - started,
	)
	return {**result, "agent_run": run.name}
