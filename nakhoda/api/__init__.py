# Copyright (c) 2026, Nakhoda and contributors
# For license information, please see license.txt
"""The whitelisted surface.

Every endpoint here runs as `frappe.session.user` and gets its tables from
`permissions.for_connector`, so the answer is bounded by what that user could
have read through the Desk - and, for an external source, by the read permission
on its `Nakhoda Data Source` row, since a foreign schema has no DocPerm rules to
apply (`permissions.UnrestrictedPolicy` says so out loud rather than skipping the
wrap). That is checked, not asserted: `tests/test_api.py`.

`run` accepts a pipeline straight from the caller, which is worth being explicit
about because it looks like the dangerous kind of endpoint and is not. Two
properties make it safe, and both are structural:

*The grammar is closed.* A pipeline is seven operations over a fixed function
registry. There is no `sql` operation, no `code` operation and no expression
escape - Insights has all three (`ibis_utils.py`, `exec_with_return`), which is
why its equivalent surface needs a trusted caller. Anything unrecognised is
rejected before compilation, by name, with the admitted list.

*The tables are already filtered.* The resolver handed to the compiler yields
permitted tables only, so a pipeline naming a table the caller cannot read
compiles fine and returns nothing.

An endpoint that is safe for a human is therefore safe for a model, which is the
property phase 4 is built on. Getting it here, before there is an agent, is
cheaper than retrofitting it after.
"""

from __future__ import annotations

from typing import Any

import frappe

from nakhoda.engine import cache, pipeline
from nakhoda.engine.operations import GrammarError, validate_pipeline
from nakhoda.engine.permissions import for_connector, policy_for
from nakhoda.nakhoda.doctype.nakhoda_query.nakhoda_query import provider as query_provider


@frappe.whitelist()
def execute(query: str, limit: int | None = None) -> dict[str, Any]:
	"""Run a stored `Nakhoda Query` as the current user."""
	doc = frappe.get_doc("Nakhoda Query", query)
	doc.check_permission("read")
	return doc.execute(limit=int(limit) if limit else None)


@frappe.whitelist()
def execute_verified(query: str, limit: int | None = None) -> dict[str, Any]:
	"""Run a `Nakhoda Verified Query` as the current user.

	Separate from `execute` above so the two answer shapes are never confused
	at the boundary: this one is refused unless the document is submitted
	(Gate A, `nakhoda_verified_query.py`), and its response always carries
	`source: "verified"` plus the question it answers and who approved it.
	"""
	doc = frappe.get_doc("Nakhoda Verified Query", query)
	doc.check_permission("read")
	return doc.execute(limit=int(limit) if limit else None)


@frappe.whitelist()
def run(operations: Any, data_source: str | None = None, limit: int | None = None) -> dict[str, Any]:
	"""Run a pipeline that was never stored.

	The caller supplies the operations; the boundary is unchanged.
	"""
	source_name = data_source or default_source()
	source = frappe.get_cached_doc("Nakhoda Data Source", source_name)
	source.check_permission("read")
	settings = frappe.get_cached_doc("Nakhoda Settings")

	connector = source.connector()
	policy = policy_for(connector, str(frappe.session.user))
	resolver = for_connector(connector, str(frappe.session.user))
	cap = int(limit or settings.max_rows or 100_000)
	ttl = int(settings.cache_ttl or cache.DEFAULT_TTL)
	queries = query_provider(source_name)

	# One parse, shared: nothing downstream mutates the operations, and the
	# payload is the largest thing this endpoint receives.
	ops = frappe.parse_json(operations)
	try:
		validate_pipeline(ops)
		result = pipeline.run(ops, resolver, connector, cap=cap, ttl=ttl, queries=queries)
		notice = pipeline.notice(ops, connector.resolve, policy, connector, queries)
		injected = pipeline.injected(ops, policy, queries)
	except GrammarError as exc:
		# Every grammar refusal, wherever it is raised, is a validation error at
		# this boundary - `manager._try_tier` reads `frappe.ValidationError` as
		# "the model answered badly" and escalates. Two escaped as 500s before
		# this guard existed: an `ExpressionError` from validation, and an
		# `OperationError` from *compilation* (a join colliding with a name only
		# the real schema knows), which validation cannot see and so cannot
		# refuse earlier.
		# `frappe.throw` raises, but it is not typed `NoReturn` - same shape as
		# `api/data_sources.py:_parsed`.
		frappe.throw(str(exc), title=frappe._("Invalid pipeline"))
		raise frappe.ValidationError
	return {
		"columns": list(result.frame.columns),
		"rows": result.frame.to_dict(orient="records"),
		"row_count": len(result.frame),
		"truncated": len(result.frame) >= cap,
		"execution_time": result.elapsed,
		"sql": result.sql,
		"ml_operation": result.ml_operation,
		"notice": notice,
		"injected": injected,
	}


@frappe.whitelist()
def validate(operations: Any) -> dict[str, Any]:
	"""Check a pipeline's structure without running it.

	Returns the refusal instead of raising it: this exists so an editor - or a
	model correcting itself - can see what is wrong before spending a query.
	"""
	try:
		validate_pipeline(frappe.parse_json(operations))
	except (ValueError, TypeError) as exc:
		return {"valid": False, "error": str(exc)}
	return {"valid": True, "error": None}


@frappe.whitelist()
def default_source() -> str:
	"""The default data source, created on demand.

	A fresh install can answer a question without being configured first: the
	site's own database is already a valid source and needs no credentials.

	Deleting the default row is allowed, so "no row carries the flag" is a
	reachable state. Electing a replacement here without writing the flag back
	would leave the engine using a source the Data Sources page draws no
	`Default` badge on, and `list_data_sources`' `is_default desc` sort with
	nothing to sort by. One invariant instead: if a row exists, one is default.
	"""
	existing = frappe.get_all("Nakhoda Data Source", filters={"is_default": 1}, pluck="name", limit=1)
	if existing:
		return existing[0]
	orphaned = frappe.get_all("Nakhoda Data Source", pluck="name", order_by="creation", limit=1)
	if orphaned:
		frappe.db.set_value("Nakhoda Data Source", orphaned[0], "is_default", 1)
		return orphaned[0]

	if not frappe.has_permission("Nakhoda Data Source", "create"):
		frappe.throw(frappe._("No data source is configured."), frappe.PermissionError)
	doc = frappe.get_doc(
		{
			"doctype": "Nakhoda Data Source",
			"title": "Site Database",
			"source_type": "Site Database",
			"is_default": 1,
		}
	).insert()
	return doc.name
