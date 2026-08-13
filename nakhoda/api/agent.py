# Copyright (c) 2026, Nakhoda and contributors
# For license information, please see license.txt
"""The agent's whitelisted surface. One endpoint - `ask` never raises
(`agent/manager.py`), so there is nothing here for a second endpoint to do
that a non-2xx response would do better."""

from __future__ import annotations

from typing import Any

import frappe

from nakhoda.agent.manager import ask as ask_agent


@frappe.whitelist()
def ask(
	question: str, space: str | None = None, data_source: str | None = None, limit: int | None = None
) -> dict[str, Any]:
	"""Answer a question as the current user. See `agent/manager.py:ask`."""
	return ask_agent(
		question, space=space or None, data_source=data_source or None, limit=int(limit) if limit else None
	)
