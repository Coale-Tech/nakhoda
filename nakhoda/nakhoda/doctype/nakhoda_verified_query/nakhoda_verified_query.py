# Copyright (c) 2026, Nakhoda and contributors
# For license information, please see license.txt
"""A governed answer: a pipeline that has passed approval, refused until it has.

Phase 3 has one job, stated as two gates in `docs/plan/12-build-plan.md`:

Gate A - the asset is governed. A draft (`docstatus` 0) or cancelled (`docstatus`
2) query is not servable; `execute` checks `docstatus` before it checks anything
else, so refusal is unconditional rather than a UI affordance. Approval is a
Frappe `submit` permission, not a flag this controller interprets -
`Nakhoda User` can draft a question and its pipeline, but only `Nakhoda Admin`
and `System Manager` hold `submit` on this doctype
(`nakhoda_verified_query.json`), so authorship and approval are structurally
different actions: `doc.submit()` raises `frappe.PermissionError` for a caller
who lacks it, from Frappe core, before this file runs at all. An answer served
from here always carries `source: "verified"` plus the reviewer and the
question it was verified against, so nothing downstream has to guess where a
number came from.

Gate B - Phase 4's agent prefers a verified query over generating SQL when one
already answers the question. That match happens in the agent, against
`question`; this file only has to make a verified answer cheap and labelled
once found.
"""

from __future__ import annotations

import time
from typing import Any

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime

from nakhoda.engine import cache
from nakhoda.engine.operations import OperationError, compile_pipeline, validate_pipeline
from nakhoda.engine.permissions import for_user


class NakhodaVerifiedQuery(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		cache_key: DF.Data | None
		data_source: DF.Link
		last_executed_by: DF.Link | None
		last_executed_on: DF.Datetime | None
		last_execution_time: DF.Float
		last_row_count: DF.Int
		notes: DF.Text | None
		operations: DF.JSON
		question: DF.SmallText
		title: DF.Data
		verified_by: DF.Link | None
		verified_on: DF.Datetime | None
	# end: auto-generated types

	def validate(self) -> None:
		try:
			validate_pipeline(frappe.parse_json(self.operations))
		except OperationError as exc:
			frappe.throw(str(exc), title=frappe._("Invalid pipeline"))
		except (ValueError, TypeError) as exc:
			frappe.throw(frappe._("Operations must be valid JSON: {0}").format(exc))

	def on_submit(self) -> None:
		"""Record who approved this, and when - the fact `execute` unlocks on."""
		self.db_set("verified_by", frappe.session.user, update_modified=False)
		self.db_set("verified_on", now_datetime(), update_modified=False)

	def execute(self, limit: int | None = None) -> dict[str, Any]:
		"""Run the pipeline as whoever is asking - but only once it is verified.

		The `docstatus` check is the whole of Gate A. It runs before
		permissions, before compilation, before anything: an unsubmitted or
		cancelled query is refused for what it is, not because of who is
		asking.
		"""
		if self.docstatus != 1:
			frappe.throw(
				frappe._("{0} has not been verified.").format(self.doctype),
				frappe.PermissionError,
			)

		settings = frappe.get_cached_doc("Nakhoda Settings")
		source = frappe.get_cached_doc("Nakhoda Data Source", self.data_source)
		connector = source.connector()

		resolver = for_user(connector.resolve, frappe.session.user)
		expression = compile_pipeline(frappe.parse_json(self.operations), resolver)

		cap = int(limit or settings.max_rows or 100_000)
		expression = expression.limit(cap)

		sql = connector.sql(expression)
		started = time.monotonic()
		frame = cache.cached(
			sql,
			connector.identity,
			lambda: connector.execute(expression),
			ttl=int(settings.cache_ttl or cache.DEFAULT_TTL),
		)
		elapsed = time.monotonic() - started

		self._record(cache.key(sql, connector.identity), len(frame), elapsed)
		return {
			"columns": list(frame.columns),
			"rows": frame.to_dict(orient="records"),
			"row_count": len(frame),
			"truncated": len(frame) >= cap,
			"execution_time": elapsed,
			"sql": sql,
			"source": "verified",
			"question": self.question,
			"verified_by": self.verified_by,
			"verified_on": self.verified_on,
		}

	def _record(self, key: str, rows: int, elapsed: float) -> None:
		"""Note the run without demanding write access to do it.

		A viewer with read-only access to a shared query still executes it, so
		this cannot go through the document API. It is diagnostic, and a
		failure to record must never fail the answer.
		"""
		try:
			frappe.db.set_value(
				self.doctype,
				self.name,
				{
					"cache_key": key,
					"last_row_count": rows,
					"last_execution_time": elapsed,
					"last_executed_on": now_datetime(),
					"last_executed_by": frappe.session.user,
				},
				update_modified=False,
			)
		except Exception:
			frappe.log_error(title="Nakhoda: could not record verified query execution")
