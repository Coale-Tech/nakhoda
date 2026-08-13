# Copyright (c) 2026, Nakhoda and contributors
# For license information, please see license.txt
"""One row per `NotebookKernel` invocation - the audit trail for Phase 7's
arbitrary-code-execution surface, the same reasoning `nakhoda_agent_run.py`
gives for logging every agent turn. Written by `api/notebooks.py` with
`ignore_permissions=True`, like `Nakhoda Agent Run`: there is no `Nakhoda
User` permission row on this doctype at all, deliberately - `run_cell` is
`Nakhoda Admin`/`System Manager`-only (see `api/notebooks.py`), so nothing
below that gate should be able to read its own log either, unlike a
question-answering turn.
"""

from __future__ import annotations

from frappe.model.document import Document


class NakhodaNotebookRun(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		cell_count: DF.Int
		code: DF.Code | None
		duration: DF.Float
		error: DF.SmallText | None
		results: DF.Code | None
		session: DF.Data
		status: DF.Literal["ok", "error", "unavailable"]
		user: DF.Link
	# end: auto-generated types
