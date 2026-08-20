# Copyright (c) 2026, Nakhoda and contributors
# For license information, please see license.txt
"""One row per user prompt on a dashboard - the loop's own audit record.

Deliberately *not* folded into `Nakhoda Agent Run`. That row is asserted on by
the Phase 4 gate ("every run records its tier and the structural reason it was
chosen"), and it is immutable and single-purpose: one question, one pipeline,
one SQL statement. A loop is a different unit - it may ask two questions and
write a report - and hanging a steps blob and a report off an audit record
would muddy the one column that gate reads.

So the two nest instead: a turn is the parent, and every `ask_data` the loop
delegated becomes a `Nakhoda Agent Run` pointing back through `thread_turn`.
Every SQL statement the loop caused stays a first-class, permission-checked,
individually auditable row - the property `13-agent-design.md` §5 asks for -
while the turn records what the loop *decided*.

Written with `ignore_permissions=True` for the same reason the manager writes
its runs that way: a caller who asked a question should not also need `create`
on the log of it. `if_owner` still scopes `Nakhoda User` reads to their own
turns.

Nothing here validates: every field is read-only and written by
`agent/thread.py`, the `Select` options are enforced by the fieldtype, and the
two JSON blobs were already validated by the grammars that produced them
(`bench/driver.extract` for `steps`, `engine/dashboard.validate_patch` for
`patch_ops`).
"""

from __future__ import annotations

from frappe.model.document import Document


class NakhodaThreadTurn(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		applied_version: DF.Link | None
		dashboard: DF.Link | None
		error: DF.SmallText | None
		execution_time: DF.Float
		patch_diff: DF.Code | None
		patch_ops: DF.Code | None
		question: DF.SmallText
		report: DF.LongText | None
		space: DF.Link | None
		status: DF.Literal["ok", "error", "budget"]
		step_count: DF.Int
		steps: DF.Code | None
		user: DF.Link
	# end: auto-generated types
