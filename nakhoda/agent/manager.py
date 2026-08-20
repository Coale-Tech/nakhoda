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

from nakhoda.agent import charts, providers, quota, verified
from nakhoda.agent.router import Route, route
from nakhoda.agent.tiers import LADDER, Tier
from nakhoda.agent.tiers import models as tier_models
from nakhoda.api import default_source, execute_verified
from nakhoda.api import run as run_pipeline
from nakhoda.bench.driver import extract
from nakhoda.bench.driver import prompt as build_prompt
from nakhoda.bench.driver import repair as driver_repair
from nakhoda.nakhoda.doctype.nakhoda_query.nakhoda_query import provider as query_provider
from nakhoda.semantic.retrieval import build_index
from nakhoda.semantic.retrieval import context as semantic_context

#: Three consecutive rate-limits, anywhere in the ladder, and the manager stops
#: trying rather than keep burning the circuit breaker's namesake quota
#: (`12-build-plan.md` Phase 4, point 3).
RATE_LIMIT_CIRCUIT = 3


class Outcome(Enum):
	OK = "ok"
	#: The pipeline failed to parse or to validate - a quality signal. The only
	#: outcome this module escalates a tier for.
	INVALID = "invalid"
	#: Every model in the tier errored - an availability signal, handled by
	#: moving on rather than by trying harder here.
	UNAVAILABLE = "unavailable"
	#: The tier is not a rung at all: nothing is configured for it, or every
	#: model it offers has already been asked this question. Neither is a
	#: degradation - an unconfigured `PREMIUM` is the intended free-first
	#: default (`12-build-plan.md` Phase 4, point 2), and a run that recorded
	#: it as one would mark every failure `degraded` and make the column
	#: unreadable.
	SKIPPED = "skipped"
	CIRCUIT_OPEN = "circuit_open"


@dataclass
class Attempt:
	outcome: Outcome
	model: str | None = None
	ops: list | None = None
	#: The model's own assumption list, validated by `driver._valid_assumptions`.
	#: `[]` when the model reported none; `None` only on a non-OK outcome.
	assumptions: list[dict] | None = None
	result: dict[str, Any] | None = None
	detail: str | None = None


def _attempt(raw: str, model: str, *, data_source: str, limit: int | None) -> Attempt:
	"""One completion, read and run: `OK` with the result, or `INVALID` with the
	reason. Shared by the first ask and its repair so the two are judged by
	exactly the same standard - a repair that parses but does not run is as
	refused as the answer it was correcting."""
	payload, err = extract(raw, "ops_annotated")
	if err:
		return Attempt(Outcome.INVALID, model=model, detail=err)
	ops, assumptions = payload["ops"], payload["assumptions"]
	try:
		result = run_pipeline(operations=json.dumps(ops), data_source=data_source, limit=limit)
	except frappe.ValidationError as exc:
		return Attempt(Outcome.INVALID, model=model, ops=ops, detail=str(exc))
	return Attempt(Outcome.OK, model=model, ops=ops, assumptions=assumptions, result=result)


def _try_tier(
	tier: Tier,
	text_prompt: str,
	rate_limits: list[int],
	tried: set[str],
	*,
	data_source: str,
	limit: int | None,
) -> Attempt:
	"""Every model configured for one tier, in order. Returns the first that
	produces a pipeline `nakhoda.api.run` accepts; short of that, the first
	validation failure seen beats a plain unavailability, because a failure
	that names what is wrong is the more useful thing to escalate on.

	Each candidate gets at most two calls: the ask, and - only if the engine
	refused the answer - one repair carrying that refusal.

	`tried` is every model already asked this question, across tiers. A tier
	whose ids are all in it is skipped rather than re-asked: the prompt does not
	change between rungs, so the same model can only produce the same answer,
	and a site that leaves `ai_model` and `ai_model_fallback` blank has one
	provider default standing in for both tiers. Measured on `jkm`
	2026-08-16: two identical 59-second calls to
	`nvidia/nemotron-3-ultra-550b-a55b` for one identical refusal.
	"""
	candidates = [model for model in tier_models(tier) if model not in tried]
	if not candidates:
		return Attempt(Outcome.SKIPPED, detail=f"no untried model for tier {tier.value}")

	invalid: Attempt | None = None
	#: Why each candidate failed, in order tried. Degrading is unconditional
	#: here, but degrading *silently* left an operator with "unavailable" and
	#: nothing to act on - a missing SDK, a rejected key and an unreachable host
	#: all read identically. The reasons ride along to `ask()`, which returns
	#: this string to the browser and stores it on the run's
	#: `degradation_reason`.
	reasons: list[str] = []
	for model in candidates:
		tried.add(model)
		try:
			raw = providers.complete(text_prompt, model)
		except providers.RateLimited as exc:
			rate_limits[0] += 1
			if rate_limits[0] >= RATE_LIMIT_CIRCUIT:
				return Attempt(Outcome.CIRCUIT_OPEN, model=model, detail=str(exc))
			continue
		except Exception as exc:
			# Any other provider failure - misconfiguration, network, an SDK this
			# module has never seen - is unavailability, not a crash. Degrade
			# never fail is unconditional at this boundary; naming the cause is
			# free. `str(exc)` is empty for some SDK errors, so fall back to the
			# class, which at least says what kind of wrong this was.
			reasons.append(f"{model}: {str(exc).strip() or type(exc).__name__}")
			rate_limits[0] = 0
			continue

		rate_limits[0] = 0
		refused = _attempt(raw, model, data_source=data_source, limit=limit)
		if refused.outcome is Outcome.OK:
			return refused

		# One repair, then this model is done. The refusal names the offending
		# node, and `driver.repair` hands it back with the answer that earned it -
		# the only way a temperature-0 model can answer differently. A second
		# refusal escalates instead of looping: a model that cannot use a precise
		# correction will not use a third prompt either.

		# The pipeline when the reply parsed, else the reply itself - for a parse
		# failure the text *is* the mistake, and `raw` is about to be rebound.
		rejected = json.dumps(refused.ops, indent=2) if refused.ops is not None else raw
		try:
			raw = providers.complete(driver_repair(text_prompt, rejected, refused.detail or ""), model)
		except providers.RateLimited as exc:
			# A rate-limited repair counts against the circuit like any other
			# refused call; swallowing it here would let the ladder burn through
			# the tiers while the provider is already saying stop.
			rate_limits[0] += 1
			if rate_limits[0] >= RATE_LIMIT_CIRCUIT:
				return Attempt(Outcome.CIRCUIT_OPEN, model=model, detail=str(exc))
			invalid = invalid or refused
			continue
		except Exception:
			# The repair call itself failing leaves the first refusal standing:
			# it is the more useful thing to escalate on, and this model already
			# answered once, so the tier is not unavailable.
			invalid = invalid or refused
			continue

		rate_limits[0] = 0
		repaired = _attempt(raw, model, data_source=data_source, limit=limit)
		if repaired.outcome is Outcome.OK:
			return repaired
		# The first refusal is the one worth reporting: it is what the model was
		# asked about, and the second may just be the same node again.
		invalid = invalid or refused

	if invalid:
		return invalid
	detail = f"every model in tier {tier.value} was unavailable"
	if reasons:
		detail = f"{detail}: {'; '.join(reasons)}"
	return Attempt(Outcome.UNAVAILABLE, detail=detail)


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


def _with_chart(result: dict[str, Any], operations: Any = None, source: str | None = None) -> dict[str, Any]:
	"""Attach an inferred `chart` plus flint's semantic annotations to a
	pipeline result, per `agent/charts.py`. Applies uniformly to both answer
	sources - a verified query answering "revenue by territory" charts exactly
	like a generated one would, because chart eligibility is a property of the
	result shape, not of where the pipeline came from.

	`semantic_types` / `field_display_names` are what `flint-chart` cannot infer
	and Frappe declared at design time: that a column is a `Currency` and that
	its axis reads "Grand Total". Absent keys are the contract, not a failure -
	both dicts are omitted when nothing resolved, and flint falls back to
	sniffing values."""
	columns = result.get("columns") or []
	chart = charts.pick(columns, result.get("rows") or [])
	out = {**result, "chart": chart} if chart else dict(result)
	types, display = charts.semantics(
		columns,
		frappe.parse_json(operations) if isinstance(operations, str) else operations,
		query_provider(source) if source else None,
	)
	if types:
		out["semantic_types"] = types
	if display:
		out["field_display_names"] = display
	return out


def _with_assumptions(result: dict[str, Any], assumptions: list[dict] | None) -> dict[str, Any]:
	"""Attach the model's own assumption list, if it emitted one. Generated
	answers only - a verified query never carries this key, matching
	`12-build-plan.md` Phase 3's "no ambiguity" gate for the verified path
	(`Turn.vue`'s docstring). Never fabricated when the model reported
	nothing: an empty or missing list means this key is simply absent, the
	same convention `_with_chart` uses above."""
	return {**result, "assumptions": assumptions} if assumptions else result


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
		# The ops go on the audit row and into the semantic annotation; the
		# source resolves any query references inside them. `execute_verified`
		# just loaded this document, so both reads are warm.
		verified_ops = frappe.get_cached_value("Nakhoda Verified Query", matched, "operations")
		verified_source = frappe.get_cached_value("Nakhoda Verified Query", matched, "data_source")
		run = _log(
			user,
			space,
			question,
			source="verified",
			matched_verified_query=matched,
			status="ok",
			operations=verified_ops,
			sql=result.get("sql"),
			row_count=result.get("row_count"),
			execution_time=time.monotonic() - started,
		)
		return {
			**_with_chart(result, verified_ops, verified_source),
			"agent_run": run.name,
		}

	# Everything below asks a model. The two gates that can refuse it live here,
	# after the verified-query branch on purpose: a matched verified query is
	# free, and must keep answering when AI is off or the quota is spent - that
	# is the no-AI fallback the build plan is ordered to protect, and it would
	# be pointless if the switch also silenced the free path.
	if not providers.enabled():
		error = "AI is turned off (Nakhoda Settings, AI Provider tab)."
		run = _log(
			user, space, question, status="error", error=error, execution_time=time.monotonic() - started
		)
		return {"error": error, "agent_run": run.name}

	if not quota.available():
		error = "The AI request quota for this period is used up (Nakhoda Settings, AI Provider tab)."
		run = _log(
			user, space, question, status="error", error=error, execution_time=time.monotonic() - started
		)
		return {"error": error, "agent_run": run.name}

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
	# One renderer, in retrieval: the tables were selected against a token budget
	# computed from pruned descriptions, so this has to render the same ones.
	context = semantic_context(initial.tables, index)
	text_prompt = build_prompt(context, question, "ops_annotated")

	rate_limits = [0]
	#: Every model asked this question, across every rung. Shared like
	#: `rate_limits`: the ladder's budget is per question, not per tier.
	tried: set[str] = set()
	escalation_reason: str | None = None
	degradation_reason: str | None = None
	#: The model whose refusal ended the climb, so a failed run names one the
	#: way an answered run does - `7u3g3n2ss6` recorded a parse failure with an
	#: empty `model`, which is a bug report nobody can act on.
	refused_model: str | None = None
	final: Attempt | None = None
	used_tier = initial.tier
	#: The last rung that actually asked something. Not `initial.tier` once a
	#: refusal moved the question up, and not advanced by a skipped rung.
	last_tier = initial.tier

	for tier in LADDER[LADDER.index(initial.tier) :]:
		attempt = _try_tier(tier, text_prompt, rate_limits, tried, data_source=source_name, limit=limit)
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
		if attempt.outcome is Outcome.SKIPPED:
			# No model this rung has not already answered with. Nothing happened
			# here, so nothing is recorded and the question did not climb to it.
			continue
		last_tier = tier
		if attempt.outcome is Outcome.INVALID:
			escalation_reason = escalation_reason or attempt.detail
			refused_model = refused_model or attempt.model
		elif attempt.outcome is Outcome.UNAVAILABLE:
			degradation_reason = degradation_reason or attempt.detail

	if final is None:
		# `tried` empty means no rung held a model at all - a configuration
		# problem, not a bad answer and not an outage, so it names the place to
		# fix it the way the AI-off and quota messages do.
		unconfigured = "No AI model is configured (Nakhoda Settings, AI Provider tab)."
		detail = (
			escalation_reason or degradation_reason or (unconfigured if not tried else "no model available")
		)
		# What the row keeps and what the browser is told are not the same
		# string. A refusal detail is a parser or grammar message - `invalid
		# JSON: Expecting ',' delimiter`, a real one from 2026-08-17 - and it
		# answers "why" for whoever opens the run, but alone it reads as though
		# the analyst mistyped something. The sentence says whose failure it
		# was; the parenthesis keeps the diagnosis where it can still be read.
		error = (
			f"The model could not produce a query this engine can run ({detail})"
			if escalation_reason
			else detail
		)
		# `escalated` means the same thing on both exits: a refusal moved this
		# question to a higher rung. A single rung that refused is a refusal,
		# not an escalation, and `error` carries its reason either way.
		escalated = escalation_reason is not None and last_tier != initial.tier
		run = _log(
			user,
			space,
			question,
			status="error",
			error=detail,
			tier=last_tier.value,
			tier_reason=initial.reason,
			model=refused_model,
			escalated=escalated,
			escalation_reason=escalation_reason if escalated else None,
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
		assumptions=frappe.as_json(final.assumptions) if final.assumptions else None,
		sql=result.get("sql"),
		row_count=result.get("row_count"),
		execution_time=time.monotonic() - started,
	)
	# One answered question, one unit of quota - counted after the answer, so a
	# question nobody got an answer to is not billed against the cap.
	quota.consume()
	return {
		**_with_assumptions(_with_chart(result, final.ops, source_name), final.assumptions),
		"agent_run": run.name,
	}
