# Copyright (c) 2026, Nakhoda and contributors
# For license information, please see license.txt
"""Executes one notebook cell against a persistent namespace. Pure and
frappe-free by construction - it is the payload that runs *inside* the
isolated container (`docker/notebook_kernel/main.py` wires it to stdio) and
is also imported directly by `tests/test_notebook.py`, so its correctness is
provable without Docker.

The isolation Phase 7's gate cares about is a property of the process
boundary in `engine/notebook.py`, not of this function - this file is
deliberately as unrestricted as a real Python REPL, because the boundary,
not the language, is the sandbox (`00-REPORT.md` §6.3: "run cells in a
separate process ... not in the web worker"). Nothing here does what
Insights' `ibis_utils.py` shim tried and failed to do (`00-REPORT.md` §2.3)
- guard a dangerous surface with a Python-level wrapper. There is no guard;
the surface is unrestricted, and the container around it is what has to
hold.
"""

from __future__ import annotations

import ast
import contextlib
import io
import traceback
from typing import Any


def run_cell_in_namespace(code: str, namespace: dict[str, Any]) -> dict[str, Any]:
	"""Exec `code` against `namespace` in place - so state persists across
	calls sharing the same dict, the way notebook cells share a kernel - and
	return a JSON-safe result: `stdout`, `stderr`, `result` (the `repr` of a
	trailing bare expression's value, `None` if the cell has none or it
	evaluated to `None`), `error` (the formatted exception/traceback, or
	`None`).

	A trailing bare expression is treated like a REPL line and reported as
	`result`, matching what `15 + 27` or `df.head()` as the last line of a
	notebook cell means to a user - everything before it just executes.
	"""
	stdout, stderr = io.StringIO(), io.StringIO()
	result_repr: str | None = None
	error: str | None = None

	try:
		tree = ast.parse(code, mode="exec")
	except SyntaxError:
		return {"stdout": "", "stderr": "", "result": None, "error": traceback.format_exc()}

	body = tree.body
	tail_expr: ast.Expression | None = None
	if body and isinstance(body[-1], ast.Expr):
		tail_expr = ast.Expression(body[-1].value)
		body = body[:-1]

	try:
		with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
			if body:
				exec(compile(ast.Module(body=body, type_ignores=[]), "<cell>", "exec"), namespace)
			if tail_expr is not None:
				value = eval(compile(tail_expr, "<cell>", "eval"), namespace)
				if value is not None:
					result_repr = repr(value)
	except Exception:
		error = traceback.format_exc()

	return {
		"stdout": stdout.getvalue(),
		"stderr": stderr.getvalue(),
		"result": result_repr,
		"error": error,
	}


__all__ = ["run_cell_in_namespace"]
