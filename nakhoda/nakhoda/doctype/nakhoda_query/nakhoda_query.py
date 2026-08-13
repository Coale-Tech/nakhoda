# Copyright (c) 2026, Nakhoda and contributors
# For license information, please see license.txt
"""A stored pipeline, and the only thing that runs one.

Two responsibilities, and the split between them is the point.

`validate` rejects a malformed pipeline **on save**. Everything checkable
without a schema - operation names, argument arity, aggregate placement, scope
after a summarize - is checked by the grammar itself, so a query that cannot run
cannot be stored. Column existence needs a table and is checked at compile time.

`execute` builds the pipeline against a resolver bound to the *current viewer*.
There is no second path: the resolver is the only way a table enters the
compiler, and `permissions.for_user` is the only resolver this method
constructs. That is what makes the boundary structural rather than a rule
someone has to remember - the failure that produced Insights issue #919, and the
one that left 17 whitelisted endpoints in a fork of it reading every company's
ledger, were both a caller reaching past a helper. Here there is nothing to
reach past.
"""

from __future__ import annotations

from typing import Any

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime

from nakhoda.engine import cache, pipeline
from nakhoda.engine.operations import OperationError, validate_pipeline
from nakhoda.engine.permissions import for_user


class NakhodaQuery(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		cache_key: DF.Data | None
		data_source: DF.Link | None
		last_executed_by: DF.Link | None
		last_executed_on: DF.Datetime | None
		last_execution_time: DF.Float
		last_row_count: DF.Int
		operations: DF.JSON
		title: DF.Data

	# end: auto-generated types
	def validate(self) -> None:
		try:
			validate_pipeline(frappe.parse_json(self.operations))
		except OperationError as exc:
			frappe.throw(str(exc), title=frappe._("Invalid pipeline"))
		except (ValueError, TypeError) as exc:
			frappe.throw(frappe._("Operations must be valid JSON: {0}").format(exc))

	def execute(self, limit: int | None = None) -> dict[str, Any]:
		"""Run the pipeline as whoever is asking.

		The row cap is applied after permissions, never instead of them: a cap
		trims a result the viewer is entitled to, it does not decide what they
		are entitled to.
		"""
		settings = frappe.get_cached_doc("Nakhoda Settings")
		source = frappe.get_cached_doc("Nakhoda Data Source", self.data_source)
		connector = source.connector()

		resolver = for_user(connector.resolve, frappe.session.user)
		cap = int(limit or settings.max_rows or 100_000)
		result = pipeline.run(
			frappe.parse_json(self.operations),
			resolver,
			connector,
			cap=cap,
			ttl=int(settings.cache_ttl or cache.DEFAULT_TTL),
		)

		self._record(result.cache_key, len(result.frame), result.elapsed)
		return {
			"columns": list(result.frame.columns),
			"rows": result.frame.to_dict(orient="records"),
			"row_count": len(result.frame),
			"truncated": len(result.frame) >= cap,
			"execution_time": result.elapsed,
			"sql": result.sql,
			"ml_operation": result.ml_operation,
		}

	def _record(self, key: str, rows: int, elapsed: float) -> None:
		"""Note the run without demanding write access to do it.

		A viewer with read-only access to a shared query still executes it, so
		this cannot go through the document API. It is diagnostic, and a failure
		to record must never fail the answer.
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
			frappe.log_error(title="Nakhoda: could not record query execution")
