# Copyright (c) 2026, Nakhoda and contributors
# For license information, please see license.txt
"""One name for "the grammar rejected this".

`OperationError` (a malformed pipeline) and `ExpressionError` (a malformed
expression) are two layers of one event as far as any caller is concerned: the
operations supplied are not something this engine will run, and the answer is
to return the message, never to raise past the boundary.

Callers kept enumerating the pair and missing a member. On 2026-08-16 a live
model emitted `{"and": [...]}` - the shorthand for a conjunction the grammar
spells `{"fn": "and", "args": [...]}` - and `api.run` caught `OperationError`
only, so the `ExpressionError` travelled out of `manager._try_tier` (which
watches for `frappe.ValidationError`) and reached the browser as HTTP 500 with
no `Nakhoda Agent Run` row and no error on screen: a question that vanished.
The same gap made both doctypes report a malformed expression as "Operations
must be valid JSON", which the JSON was.

Catching this base is what fixes that class of bug rather than its instances,
and a third grammar error added later needs no call-site edit.
"""

from __future__ import annotations


class GrammarError(ValueError):
	"""The engine's grammar rejected the input.

	`ValueError` remains the base so existing `except (ValueError, TypeError)`
	fallbacks - the JSON-shaped ones - keep behaving as they did.
	"""
