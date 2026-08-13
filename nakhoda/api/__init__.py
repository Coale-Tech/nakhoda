# Copyright (c) 2026, Nakhoda and contributors
# For license information, please see license.txt
"""The whitelisted surface.

Every endpoint here runs as `frappe.session.user` and gets its tables from
`permissions.for_user`, so the answer is bounded by what that user could have
read through the Desk. That is checked, not asserted: `tests/test_api.py`.

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

import time
from typing import Any

import frappe

from nakhoda.engine import cache
from nakhoda.engine.operations import OperationError, compile_pipeline, validate_pipeline
from nakhoda.engine.permissions import for_user


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

	try:
		pipeline = validate_pipeline(frappe.parse_json(operations))
	except OperationError as exc:
		frappe.throw(str(exc), title=frappe._("Invalid pipeline"))

	connector = source.connector()
	resolver = for_user(connector.resolve, frappe.session.user)
	cap = int(limit or settings.max_rows or 100_000)
	expression = compile_pipeline(pipeline, resolver).limit(cap)

	sql = connector.sql(expression)
	started = time.monotonic()
	frame = cache.cached(
		sql,
		connector.identity,
		lambda: connector.execute(expression),
		ttl=int(settings.cache_ttl or cache.DEFAULT_TTL),
	)
	return {
		"columns": list(frame.columns),
		"rows": frame.to_dict(orient="records"),
		"row_count": len(frame),
		"truncated": len(frame) >= cap,
		"execution_time": time.monotonic() - started,
		"sql": sql,
	}


@frappe.whitelist()
def validate(operations: Any) -> dict[str, Any]:
	"""Check a pipeline's structure without running it.

	Returns the refusal instead of raising it: this exists so an editor - or a
	model correcting itself - can see what is wrong before spending a query.
	"""
	try:
		validate_pipeline(frappe.parse_json(operations))
	except (OperationError, ValueError, TypeError) as exc:
		return {"valid": False, "error": str(exc)}
	return {"valid": True, "error": None}


@frappe.whitelist()
def default_source() -> str:
	"""The default data source, created on demand.

	A fresh install can answer a question without being configured first: the
	site's own database is already a valid source and needs no credentials.
	"""
	existing = frappe.get_all("Nakhoda Data Source", filters={"is_default": 1}, pluck="name", limit=1)
	if existing:
		return existing[0]
	any_source = frappe.get_all("Nakhoda Data Source", pluck="name", limit=1)
	if any_source:
		return any_source[0]

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
