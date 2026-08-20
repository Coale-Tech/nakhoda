# Copyright (c) 2026, Nakhoda and contributors
# For license information, please see license.txt
"""A cap on model calls, and the window it resets in.

Ported from Insights' AI Analytics quota (`insights/ai/*_client.py`'s
`check_quota`/`increment_quota` plus `analytics/ml_engine.reset_ai_quota`),
with one correction. Insights offers Daily/Weekly/Monthly on the settings page
but resets the counter from a *daily* scheduler event regardless
(`hooks.py:166` -> `reset_ai_quota()` zeroes `ai_quota_used` every midnight),
so two of its three options do nothing. Here the window is stored
(`quota_window_start`) and evaluated on read, which fixes that and also makes
the cap correct on a site whose scheduler is paused - a background job that
never runs would otherwise lock every user out permanently rather than merely
delay a reset.

`daily_ai_quota = 0` means uncapped. That is the honest reading of "no cap"
for an app whose primary surface is `ask()`: an admin who wants unlimited
questions should not have to invent a large number.
"""

from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import add_to_date, get_datetime, now_datetime

DOCTYPE = "Nakhoda Settings"

#: How long one quota window lasts, as `(days, months)` per
#: `quota_reset_schedule` option.
WINDOWS: dict[str, tuple[int, int]] = {
	"Daily": (1, 0),
	"Weekly": (7, 0),
	"Monthly": (0, 1),
}


def _settings():
	return frappe.get_single(DOCTYPE)


def _cap(settings) -> int:
	value = getattr(settings, "daily_ai_quota", None)
	return int(value) if value not in (None, "") else 100


def _used(settings) -> int:
	return int(getattr(settings, "ai_quota_used", 0) or 0)


def _schedule(settings) -> str:
	return str(getattr(settings, "quota_reset_schedule", "") or "Daily")


def _due(settings) -> bool:
	"""Whether the current window has elapsed. A missing `quota_window_start`
	counts as due: the counter has been running without a window since before
	this field existed, so the first read opens one."""
	schedule = _schedule(settings)
	if schedule == "Disabled":
		return False
	window = WINDOWS.get(schedule)
	if not window:
		return False
	started = getattr(settings, "quota_window_start", None)
	if not started:
		return True
	days, months = window
	return now_datetime() >= add_to_date(get_datetime(started), days=days, months=months)


def reset_if_due(settings=None) -> bool:
	"""Zero the counter and open a new window when the old one has elapsed.

	Called from every quota read *and* from the daily scheduler event
	(`hooks.py`), so the cap stays correct whether or not background jobs run.
	Returns whether a reset happened.
	"""
	settings = settings or _settings()
	if not _due(settings):
		return False
	frappe.db.set_single_value(DOCTYPE, {"ai_quota_used": 0, "quota_window_start": now_datetime()})
	return True


def available(settings=None) -> bool:
	"""Whether one more model call is allowed right now."""
	settings = settings or _settings()
	if reset_if_due(settings):
		return True
	cap = _cap(settings)
	return cap <= 0 or _used(settings) < cap


def consume(settings=None) -> None:
	"""Count one answered question, and record when it happened.

	Counts *questions*, not HTTP calls to a provider: one `manager.ask()` may
	retry across models and tiers, and charging a user three times because the
	first two candidates were rate-limited would make the cap unpredictable
	from the only place it is visible - the settings page.
	"""
	settings = settings or _settings()
	reset_if_due(settings)
	frappe.db.set_single_value(
		DOCTYPE,
		{"ai_quota_used": _used(_settings()) + 1, "last_ai_answer": now_datetime()},
	)


def status(settings=None) -> dict[str, Any]:
	"""Quota half of the AI Provider tab's status strip."""
	settings = settings or _settings()
	reset_if_due(settings)
	settings = _settings()
	cap = _cap(settings)
	return {
		"quota_used": _used(settings),
		"daily_quota": cap,
		"unlimited": cap <= 0,
		"reset_schedule": _schedule(settings),
		"window_start": getattr(settings, "quota_window_start", None),
		"last_answer": getattr(settings, "last_ai_answer", None),
	}


def reset_quota() -> None:
	"""Scheduler entry point (`hooks.py`, daily). Only a backstop - the reads
	above already open a new window when one is due."""
	reset_if_due()
	frappe.db.commit()  # nosemgrep - background job owns its own transaction
