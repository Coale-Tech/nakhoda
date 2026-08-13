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

#: Free-first allocation of one shared daily budget (`12-build-plan.md` Phase 4,
#: point 2): `FAST` and `BALANCED` both on free-tier models, `PREMIUM` on paid.
#: Data for a future quota accountant, not enforced by this module - nothing
#: here calls out to a spend tracker yet, so a catalog naming only free models
#: at every tier is a valid, if conservative, configuration.
BUDGET_SPLIT: dict[Tier, int] = {Tier.FAST: 70, Tier.BALANCED: 25, Tier.PREMIUM: 5}


def models(tier: Tier) -> list[str]:
	"""Model ids configured for one tier, in fallback order.

	Read from `NAKHODA_AGENT_MODEL_<TIER>`, a comma-separated list - the first
	entry is tried first, later ones only on a model error (`agent/manager.py`).
	An unset or empty variable means the tier has no candidates, which the
	manager treats as unavailable rather than an error: a fresh install with no
	provider configured degrades all the way to "no model available" instead of
	crashing, which is the no-AI fallback the build plan is ordered to protect.
	"""
	raw = os.environ.get(f"NAKHODA_AGENT_MODEL_{tier.value}", "")
	return [m.strip() for m in raw.split(",") if m.strip()]
