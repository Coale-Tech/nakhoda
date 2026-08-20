# Copyright (c) 2026, Nakhoda and contributors
# For license information, please see license.txt
"""One row per attempted warehouse import - the audit trail behind the Data
Store page's state badge.

Ported from Insights' `Insights Table Import Log`
(`insights/insights/doctype/insights_data_source_v3/data_warehouse.py:157-236`,
verified on this bench), which is the reason the row exists at all: once
`import_table` enqueues instead of blocking the request, the HTTP response can
no longer carry the outcome, and without a durable row a failed background job
is invisible except in `Error Log`.

Two departures from the Insights original:

1. Every write here is `db_set(..., update_modified=False)` inside the worker's
   own transaction, and each is followed by an explicit commit. A background
   job that dies mid-import must still leave the started row behind - that is
   precisely what `expire_stale_imports` later reads - so buffering these
   writes until the job's final commit would defeat the mechanism.
2. `output` is truncated before it is stored. Insights writes the raw driver
   output; a wide ERPNext import can emit a multi-megabyte ibis traceback, and
   `frappe.log_error`'s own `CharacterLengthExceededError` is exactly the
   failure this app already worked around in `insights.ai.openrouter_client`.
"""

from __future__ import annotations

import frappe
from frappe.model.document import Document
from frappe.utils import get_datetime, now_datetime

#: `output` is a Code field (LONGTEXT), so this is not a column limit - it is a
#: readability limit. Anything past the first few thousand characters of an
#: ibis/DuckDB traceback is repeated frame noise that the Error Log already has
#: in full.
MAX_OUTPUT = 4000


class NakhodaTableImportLog(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		data_source: DF.Link | None
		document_type: DF.Link | None
		ended_at: DF.Datetime | None
		memory_limit: DF.Int
		output: DF.Code | None
		row_count: DF.Int
		row_limit: DF.Int
		started_at: DF.Datetime | None
		status: DF.Literal["In Progress", "Completed", "Failed"]  # type: ignore[reportUndefinedVariable]
		table_name: DF.Data | None
		time_taken: DF.Float
	# end: auto-generated types

	def log_output(self, message: str, commit: bool = False) -> None:
		"""Append a line to `output`, keeping only the tail once it is long.

		The tail, not the head: when an import fails the interesting line is
		the last one written, and clipping from the front is what keeps it.
		"""
		text = f"{self.output or ''}{message}\n"
		if len(text) > MAX_OUTPUT:
			text = "... (truncated)\n" + text[-MAX_OUTPUT:]
		self.db_set("output", text, update_modified=False)
		if commit:
			frappe.db.commit()  # nosemgrep - the worker owns its transaction

	def finish(self, status: str, row_count: int = 0, message: str = "") -> None:
		"""Close the row. Called on both the success and failure paths so a
		log never stays `In Progress` when its worker actually returned."""
		ended = now_datetime()
		# A row that somehow reached `finish()` with neither `started_at` nor a
		# `creation` stamp still has to close; a zero duration beats raising
		# inside the worker's own cleanup path.
		started = get_datetime(self.started_at or self.creation) or ended
		self.db_set(
			{
				"status": status,
				"ended_at": ended,
				"row_count": row_count,
				"time_taken": (ended - started).total_seconds(),
			},
			update_modified=False,
		)
		if message:
			self.log_output(message)
		frappe.db.commit()  # nosemgrep - the worker owns its transaction
