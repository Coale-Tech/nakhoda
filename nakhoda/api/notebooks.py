# Copyright (c) 2026, Nakhoda and contributors
# For license information, please see license.txt
"""Phase 7's whitelisted surface. One endpoint - `run_cell` - runs an
ordered list of cells against a single fresh `NotebookKernel` and logs the
session to `Nakhoda Notebook Run` before it can raise, mirroring
`agent/manager.py`'s convention for `Nakhoda Agent Run`.

State does not persist across separate `run_cell` calls: Frappe's
deployment is multi-worker with no cross-request session affinity, and
faking one with an in-process dict of live containers would be silently
wrong the moment there is more than one gunicorn worker. A notebook UI
re-sends the ordered list of cells it wants live on every run; `NotebookKernel`
replays them in order inside one container, which is what gives them shared
state *within* that one call.

Arbitrary code execution is Admin-only even though the kernel is sandboxed -
Phase 7's gate proves the sandbox holds, it does not make the capability
safe to hand to every `Nakhoda User` on top of that.
"""

from __future__ import annotations

import json
import secrets
import time
from typing import Any

import frappe

from nakhoda.engine.notebook import NotebookError, NotebookKernel, NotebookUnavailable

ADMIN_ROLES = ["Nakhoda Admin", "System Manager"]


@frappe.whitelist()
def run_cells(cells: list[str] | str) -> dict[str, Any]:
	"""Run `cells` in order against one fresh kernel and return
	`{"session": ..., "cells": [{"stdout", "stderr", "result", "error"}, ...]}`.
	A cell erroring does not stop the ones after it - matching a real
	notebook, where the document is still worth seeing in full. Raises
	(after logging) if Docker itself is unavailable; per Phase 7's "ship
	nothing" fallback, that is not silently downgraded to "run in-process"."""
	frappe.only_for(ADMIN_ROLES)
	cell_list: list[str] = list(frappe.parse_json(cells)) if isinstance(cells, str) else list(cells)
	session = secrets.token_hex(8)
	started = time.monotonic()
	results: list[dict[str, Any]] = []

	try:
		with NotebookKernel() as kernel:
			results = [_as_dict(kernel.run_cell(code)) for code in cell_list]
	except NotebookUnavailable as exc:
		_record(
			session=session,
			cells=cell_list,
			results=[],
			status="unavailable",
			error=str(exc),
			duration=time.monotonic() - started,
		)
		frappe.throw(str(exc), title="Notebook kernel unavailable")
	except NotebookError as exc:
		_record(
			session=session,
			cells=cell_list,
			results=[],
			status="error",
			error=str(exc),
			duration=time.monotonic() - started,
		)
		frappe.throw(str(exc), title="Notebook kernel error")

	first_error = next((r["error"] for r in results if r["error"]), None)
	_record(
		session=session,
		cells=cell_list,
		results=results,
		status="error" if first_error else "ok",
		error=first_error,
		duration=time.monotonic() - started,
	)
	return {"session": session, "cells": results}


def _as_dict(result: Any) -> dict[str, Any]:
	return {"stdout": result.stdout, "stderr": result.stderr, "result": result.result, "error": result.error}


def _record(
	*,
	session: str,
	cells: list[str],
	results: list[dict[str, Any]],
	status: str,
	error: str | None,
	duration: float,
) -> None:
	doc = frappe.get_doc(
		{
			"doctype": "Nakhoda Notebook Run",
			"user": frappe.session.user,
			"session": session,
			"cell_count": len(cells),
			"code": json.dumps(cells),
			"results": json.dumps(results),
			"status": status,
			"error": error,
			"duration": duration,
		}
	)
	# Same reasoning as `Nakhoda Agent Run` (`agent/manager.py`): the caller
	# who ran the cells should not also need `create` on the log of it, and
	# there is no `if_owner` read grant here because `run_cell` is already
	# Admin-only - both roles that can call it also hold `read` on this
	# doctype outright (`nakhoda_notebook_run.json`).
	doc.insert(ignore_permissions=True)
