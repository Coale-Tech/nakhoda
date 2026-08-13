# Copyright (c) 2026, Nakhoda and contributors
# For license information, please see license.txt
"""The `DashboardPatch` surface. Two endpoints, both thin wrappers over
`NakhodaIntelligenceTemplate.apply_patch`/`revert` (`engine/dashboard.py` has
the grammar, validation and diffing; the doctype method has the admin gate and
the `Nakhoda Dashboard Version` bookkeeping; there is nothing left for this
file to do beyond resolving `dashboard_name` to a document and returning what
the method returns)."""

from __future__ import annotations

from typing import Any

import frappe


@frappe.whitelist()
def apply_dashboard_patch(dashboard_name: str, ops: list[dict] | str) -> dict[str, Any]:
	"""Validate and apply `ops` to `dashboard_name`'s panels. Returns the diff
	the approval screen renders plus the `Nakhoda Dashboard Version` name a
	caller passes to `revert_dashboard_patch` later. Raises on an op the
	closed grammar has no member for, or on an `i` naming no item on the
	dashboard - see `engine/dashboard.py:PatchError`."""
	doc = frappe.get_doc("Nakhoda Intelligence Template", dashboard_name)
	return doc.apply_patch(frappe.parse_json(ops) if isinstance(ops, str) else ops)


@frappe.whitelist()
def revert_dashboard_patch(dashboard_name: str, version_name: str) -> None:
	"""Restore `dashboard_name`'s panels to what they were immediately before
	`version_name`'s patch applied."""
	doc = frappe.get_doc("Nakhoda Intelligence Template", dashboard_name)
	doc.revert(version_name)
