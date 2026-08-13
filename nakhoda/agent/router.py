# Copyright (c) 2026, Nakhoda and contributors
# For license information, please see license.txt
"""Route on structure, never on a string.

The fork this replaces picks a tier by keyword-matching raw user text, twice,
with the two passes disagreeing on which keywords mean "expensive"
(`12-build-plan.md` Phase 4, "do not adopt"). Nakhoda does not have to guess:
before any model is called, `Nakhoda Verified Query` matching is checked for
free (`agent/verified.py`) and the semantic layer already knows how many
tables a question spans and whether they need a join
(`nakhoda.semantic.retrieval.Index.select`). Route on that vector instead.

This module is pure - no network, no database beyond the `Index` it is handed
- so `tests/test_router.py` grades it without a model or a site.
"""

from __future__ import annotations

from dataclasses import dataclass

from nakhoda.agent.tiers import LADDER, Tier
from nakhoda.semantic.retrieval import Index


@dataclass(frozen=True)
class Route:
	tier: Tier
	#: Why this tier, in a sentence that can sit on a `Nakhoda Agent Run` row
	#: unexplained. A router that cannot explain its own choice cannot be
	#: audited (`12-build-plan.md` Phase 4).
	reason: str
	tables: tuple[str, ...]


def route(question: str, index: Index, budget: int | None = None) -> Route:
	"""The starting tier for one question - never `PREMIUM`.

	`PREMIUM` is earned only by `escalate()` below, on a validation failure;
	a structural router that could reach it directly would let a wide question
	skip the tier the gate measures without ever failing anything.
	"""
	from nakhoda.semantic.retrieval import BUDGET

	tables = tuple(index.select(question, budget if budget is not None else BUDGET))
	if not tables:
		return Route(
			Tier.FAST,
			"no table matched the question; cheapest tier - a bad match should fail "
			"validation cheaply rather than be given the expensive one on a guess",
			tables,
		)

	has_child = any(index.tables[name].is_child for name in tables if name in index.tables)
	if len(tables) > 1 or has_child:
		reason = f"{len(tables)} tables selected" if len(tables) > 1 else "1 table selected"
		if has_child:
			reason += ", including a child table that needs its parent joined"
		return Route(Tier.BALANCED, reason, tables)
	return Route(Tier.FAST, "single table, no join", tables)


def escalate(tier: Tier) -> Tier | None:
	"""The next tier up the ladder, or `None` at `PREMIUM` - there is nowhere
	left to escalate to."""
	idx = LADDER.index(tier)
	return LADDER[idx + 1] if idx + 1 < len(LADDER) else None
