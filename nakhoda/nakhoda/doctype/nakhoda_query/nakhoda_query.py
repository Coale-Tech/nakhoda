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
compiler, and `permissions.for_connector` is the only resolver this method
constructs. That is what makes the boundary structural rather than a rule
someone has to remember - the failure that produced Insights issue #919, and the
one that left 17 whitelisted endpoints in a fork of it reading every company's
ledger, were both a caller reaching past a helper. Here there is nothing to
reach past.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime

from nakhoda.engine import cache, pipeline
from nakhoda.engine.operations import GrammarError, validate_pipeline
from nakhoda.engine.permissions import for_connector

DOCTYPE = "Nakhoda Query"


class NakhodaQuery(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		agent_run: DF.Link | None
		cache_key: DF.Data | None
		data_source: DF.Link | None
		folder: DF.Data | None
		last_executed_by: DF.Link | None
		last_executed_on: DF.Datetime | None
		last_execution_time: DF.Float
		last_row_count: DF.Int
		linked_queries: DF.JSON | None
		operations: DF.JSON
		sort_order: DF.Int
		title: DF.Data
		workbook: DF.Link | None

	# end: auto-generated types
	def validate(self) -> None:
		try:
			validate_pipeline(frappe.parse_json(self.operations))
		except GrammarError as exc:
			frappe.throw(str(exc), title=frappe._("Invalid pipeline"))
		except (ValueError, TypeError) as exc:
			frappe.throw(frappe._("Operations must be valid JSON: {0}").format(exc))

	def before_save(self) -> None:
		self.set_linked_queries()

	def set_linked_queries(self) -> None:
		"""Record, transitively, which other queries this pipeline reads.

		A pipeline can source another query (`{"table": {"type": "query",
		"query_name": ...}}`), and that one can source a third. The workbook
		needs the closure, not the direct edges: "what breaks if I delete this"
		has to see the query two hops downstream, and a sidebar that only knew
		direct readers would let a user delete a table out from under a chart.

		Each hop reads the *stored* `linked_queries` of its parent rather than
		re-walking that query's operations, so the cost is one row read per
		distinct upstream query instead of a full recursive parse. The visited
		set is not an optimisation: a pipeline referencing a query that
		references it back would otherwise recurse forever, and nothing stops
		a user from saving that pair one document at a time. A pipeline that
		names *itself* is recorded rather than dropped - it does read itself,
		and a closure that hid that edge would tell the sidebar a self-feeding
		query was safe to delete. Visiting it once is what stops the walk.
		"""
		direct = _referenced_queries(frappe.parse_json(self.operations))

		closure: list[str] = []
		seen: set[str] = set()
		frontier = list(direct)
		while frontier:
			name = frontier.pop()
			if name in seen:
				continue
			seen.add(name)
			closure.append(name)
			upstream = frappe.db.get_value(DOCTYPE, name, "linked_queries")
			frontier.extend(frappe.parse_json(upstream) if isinstance(upstream, str) else [])

		self.linked_queries = frappe.as_json(closure)

	def execute(self, limit: int | None = None) -> dict[str, Any]:
		"""Run the pipeline as whoever is asking.

		The row cap is applied after permissions, never instead of them: a cap
		trims a result the viewer is entitled to, it does not decide what they
		are entitled to.
		"""
		settings = frappe.get_cached_doc("Nakhoda Settings")
		source = frappe.get_cached_doc("Nakhoda Data Source", self.data_source)
		connector = source.connector()

		resolver = for_connector(connector, str(frappe.session.user))
		cap = int(limit or settings.max_rows or 100_000)
		result = pipeline.run(
			frappe.parse_json(self.operations),
			resolver,
			connector,
			cap=cap,
			ttl=int(settings.cache_ttl or cache.DEFAULT_TTL),
			queries=provider(str(self.data_source)),
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


def provider(data_source: str) -> Callable[[str], Any]:
	"""Resolve a stored query's operations, for a pipeline that reads one.

	The engine compiles a query reference into a subquery but deliberately
	cannot read a `Nakhoda Query` row (`engine/operations.py`, `QueryProvider`).
	This is that missing half, and it is where the two refusals composition
	needs live:

	- **Read permission on the referenced document.** A query is a saved
	  statement someone may not have shared. Without this check, naming it as a
	  source would let a reader run it - and, worse, read its definition through
	  the SQL the inspector shows back. `has_permission` is the same gate the
	  document API applies; composition does not get a quieter one.
	- **One data source per pipeline.** Table names are resolved by the
	  connector, so a query on the site database composed into a query on a
	  Postgres source would compile `tabSales Invoice` into a Postgres
	  statement. That is not a permission bug, it is nonsense, and it fails
	  deep inside the backend driver if it is not refused here.

	Row permissions are *not* applied here and must not be: the viewer's own
	`permitted_resolver` is what compiles the inner query's tables, so reading
	someone's query never inherits the rows they can see.
	"""

	def resolve(name: str) -> Any:
		rows = frappe.get_all(
			DOCTYPE,
			filters={"name": name},
			fields=["operations", "data_source"],
			limit=1,
			ignore_permissions=True,
		)
		if not rows:
			frappe.throw(frappe._("Query {0} does not exist.").format(name))
		row = dict(rows[0])
		if not frappe.has_permission(DOCTYPE, "read", doc=name):
			raise frappe.PermissionError(frappe._("Not permitted to read query {0}.").format(name))
		if row["data_source"] != data_source:
			frappe.throw(
				frappe._("Query {0} reads {1}, not {2} - one pipeline cannot span two sources.").format(
					name, row["data_source"], data_source
				)
			)
		return frappe.parse_json(row["operations"])

	return resolve


def _referenced_queries(operations: Any) -> list[str]:
	"""Every query named directly by a pipeline, in first-seen order.

	Walks the structure without interpreting it. `validate` has already run the
	grammar over these operations, so this does not re-check shape - it only
	looks for the one node type that carries a query name, wherever the grammar
	happens to put it. A join's right-hand table and a source's table are the
	same node, and staying structure-agnostic means a new operation that reads a
	query is picked up without touching this function.
	"""
	found: list[str] = []

	def walk(node: Any) -> None:
		if isinstance(node, dict):
			if node.get("type") == "query":
				name = node.get("query_name")
				if isinstance(name, str) and name and name not in found:
					found.append(name)
			for value in node.values():
				walk(value)
		elif isinstance(node, list):
			for item in node:
				walk(item)

	walk(operations)
	return found
