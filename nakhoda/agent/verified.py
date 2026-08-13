# Copyright (c) 2026, Nakhoda and contributors
# For license information, please see license.txt
"""Gate B: prefer a verified query over generating SQL when one already
answers the question (`nakhoda_verified_query.py`, `12-build-plan.md` Phase 3).

Matching is normalised text equality, not embeddings or fuzzy scoring - there
is no vector store anywhere in this app, and inventing one to answer "does this
match" for a handful of curated questions per site would be the expensive
answer to a cheap problem. `frappe.get_all` already applies permissions, so a
verified query the caller cannot read is never offered to them (invariant 2:
the agent runs as `frappe.session.user`, never elevated).
"""

from __future__ import annotations

import re

import frappe

_PUNCTUATION = re.compile(r"[^\w\s]", re.UNICODE)
_WHITESPACE = re.compile(r"\s+")


def normalize(text: str) -> str:
	"""Case, punctuation and whitespace stripped - matching is on words, not phrasing."""
	stripped = _PUNCTUATION.sub(" ", text.lower())
	return _WHITESPACE.sub(" ", stripped).strip()


def match(question: str) -> str | None:
	"""A submitted `Nakhoda Verified Query` whose `question` normalises to the
	same text, or `None`. Drafts and cancelled queries are excluded here too,
	even though `execute()` would refuse them anyway - a router should not
	route toward an answer it already knows is unservable."""
	needle = normalize(question)
	if not needle:
		return None
	candidates = frappe.get_all(
		"Nakhoda Verified Query", filters={"docstatus": 1}, fields=["name", "question"]
	)
	for candidate in candidates:
		if normalize(candidate.question) == needle:
			return candidate.name
	return None
