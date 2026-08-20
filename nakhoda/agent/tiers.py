# Copyright (c) 2026, Nakhoda and contributors
# For license information, please see license.txt
"""Tiers are named, models are data.

`FAST` / `BALANCED` / `PREMIUM` are the only place a model id may appear
anywhere in Nakhoda (`12-build-plan.md` Phase 4, point 1). The fork this was
adopted from learned this the hard way - `llama-3.1` and `claude-3.5` ids were
delisted upstream while the tier names survived it. A catalog refresh is
therefore an environment change, never a code change.

`PREMIUM` is reachable only by escalation (`agent/router.py`) - never a
structural router's first pick. The gate that matters
(`12-build-plan.md` Phase 4) runs the benchmark with `PREMIUM` disabled
entirely and still requires >=95%; if the semantic layer needs the expensive
tier to pass, phase 1 is under-built, not this router.

Where the ids come from changed with the per-provider settings
(`nakhoda_settings.json`, ported from Insights' AI Analytics tab): the page now
configures *the selected provider's* models - a Primary and, for OpenRouter, a
Fallback - rather than three free-text tier fields. So this module maps that
pair onto the ladder instead of reading a field per tier:

    FAST     -> the provider's primary model
    BALANCED -> its fallback model, else the primary again
    PREMIUM  -> ops-only, `NAKHODA_AGENT_MODEL_PREMIUM`

`PREMIUM` deliberately has no field on the settings page. Insights offers no
third model and neither should a page claiming parity with it; an install that
genuinely wants an escalation-only expensive model sets the environment
variable, and one that does not gets a two-rung ladder rather than a control
that looks like it does something.
"""

from __future__ import annotations

import os
from enum import Enum


class Tier(str, Enum):
	FAST = "FAST"
	BALANCED = "BALANCED"
	PREMIUM = "PREMIUM"


#: Escalation order - a validation failure or an unavailable tier moves right,
#: never left. `router.escalate()` is the only caller that advances along it.
LADDER: tuple[Tier, ...] = (Tier.FAST, Tier.BALANCED, Tier.PREMIUM)


def _env_models(tier: Tier) -> list[str] | None:
	"""`NAKHODA_AGENT_MODEL_<TIER>` as a candidate list, or `None` when ops has
	not set that variable at all.

	Presence is the signal, not truthiness: a variable set to the empty string
	is ops saying "this tier has no models", and must not fall through to a
	provider default that would put the tier back into service.
	"""
	key = f"NAKHODA_AGENT_MODEL_{tier.value}"
	if key not in os.environ:
		return None
	return [m.strip() for m in os.environ[key].split(",") if m.strip()]


def models(tier: Tier) -> list[str]:
	"""Candidate model ids for `tier`, best first.

	Precedence, per rung: the selected provider's own settings field (an
	admin's change takes effect without a redeploy) else
	`NAKHODA_AGENT_MODEL_<TIER>` - a comma-separated list, first entry tried
	first, later ones only on a model error (`agent/manager.py`) - else the
	provider's shipped default.

	An empty list means the tier has no candidates, which the manager treats as
	unavailable rather than an error: a fresh install with no provider
	configured degrades all the way to "no model available" instead of
	crashing, which is the no-AI fallback the build plan is ordered to protect.
	"""
	from nakhoda.agent import providers

	settings = providers._settings()
	# No `enable_ai` check here: the master switch is one gate, enforced once,
	# in `manager.ask()` - a tier list is "which ids", not "may we call one".

	spec = providers.provider(settings)
	primary, fallback = providers.models(settings)

	if tier is Tier.PREMIUM:
		return _env_models(tier) or []

	configured = primary if tier is Tier.FAST else fallback
	# `providers.models()` already applied the provider's default, so an
	# explicitly-set env var only speaks for a tier the settings left blank.
	stored_field = spec.model_field if tier is Tier.FAST else spec.fallback_field
	explicit = bool(stored_field and getattr(settings, stored_field, ""))
	if not explicit:
		from_env = _env_models(tier)
		if from_env is not None:
			return from_env

	if tier is Tier.BALANCED and not configured:
		# Providers whose settings offer a single model still need a second
		# rung: escalating means "ask again, having failed validation once",
		# and one configured model is the only thing there is to ask.
		configured = primary
	return [configured] if configured else []
