# Copyright (c) 2026, Nakhoda and contributors
# For license information, please see license.txt
"""A domain dashboard as a declarative record - `key`/`title`/`icon`/`color` for
identity, `source` for its one query, `metrics`/`panels`/`skill`/`ml` for its
content. This file has nothing to validate that the doctype's own field types
don't already enforce: `metrics`/`ml` are Table fields, so Frappe rejects a
malformed row before `validate()` would ever see one; `panels` is a JSON field,
so a malformed document is rejected on save the same way `operations` is on
`Nakhoda Verified Query`.

Shipping and versioning - discovery, import, update-in-place, and the
`migrate`-time sync - live in `api/templates.py`, not here, because none of it
needs a bound document to run against; it operates on the shipped
`manifest.json`/`template.json` pairs and this doctype's rows as data.

`apply_patch`/`revert` are the one thing that *does* need a bound document:
the closed `add_chart` / `set_filter` / `remove_item` grammar validation and
diffing live in `engine/dashboard.py` (bare data in, bare data out, no site
needed); this controller is only the thin, permission-checked wrapper that
persists the result and the `Nakhoda Dashboard Version` snapshot it needs to
`revert` later.
"""

from __future__ import annotations

import json

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime

from nakhoda.engine.dashboard import apply_patch as compile_patch

_ADMIN_ROLES = ["Nakhoda Admin", "System Manager"]


class NakhodaIntelligenceTemplate(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		from nakhoda.nakhoda.doctype.nakhoda_intelligence_metric.nakhoda_intelligence_metric import (
			NakhodaIntelligenceMetric,
		)
		from nakhoda.nakhoda.doctype.nakhoda_intelligence_ml_operation.nakhoda_intelligence_ml_operation import (
			NakhodaIntelligenceMLOperation,
		)

		color: DF.Data | None
		from_template: DF.Data | None
		icon: DF.Data | None
		imported_checksum: DF.Data | None
		imported_version: DF.Int
		key: DF.Data
		metrics: DF.Table[NakhodaIntelligenceMetric]
		ml: DF.Table[NakhodaIntelligenceMLOperation]
		panels: DF.JSON
		skill: DF.LongText | None
		source: DF.Link | None
		title: DF.Data
	# end: auto-generated types

	def apply_patch(self, ops: list[dict]) -> dict:
		"""Validate `ops` against `PATCH_OPS`, apply them to `panels`, record the
		prior snapshot on a new `Nakhoda Dashboard Version` row, and persist the
		result. Returns `{"diff": [...], "version": <name>}` - what the approval
		screen renders and what a caller passes to `revert` later.

		Admin-gated the same way `api/templates.py`'s import/update endpoints
		are: a dashboard that anyone could repoint at an arbitrary query would
		make the approval step decorative.
		"""
		frappe.only_for(_ADMIN_ROLES)

		current = frappe.parse_json(self.panels) if self.panels else []
		new_panels, diff = compile_patch(current, ops)

		version = frappe.get_doc(
			{
				"doctype": "Nakhoda Dashboard Version",
				"dashboard": self.name,
				"applied_by": frappe.session.user,
				"applied_on": now_datetime(),
				"patch_ops": json.dumps(list(ops)),
				"diff": json.dumps(diff),
				"prior_panels": json.dumps(current),
			}
		)
		version.insert(ignore_permissions=True)

		self.db_set("panels", json.dumps(new_panels), update_modified=False)
		return {"diff": diff, "version": version.name}

	def revert(self, version_name: str) -> None:
		"""Restore `panels` to exactly what `Nakhoda Dashboard Version.
		prior_panels` recorded before that version's patch applied - a row
		read back verbatim, not an inverse patch replayed."""
		frappe.only_for(_ADMIN_ROLES)

		version = frappe.get_doc("Nakhoda Dashboard Version", version_name)
		if version.get("dashboard") != self.name:
			frappe.throw(frappe._("{0} does not belong to this dashboard").format(version_name))
		if version.get("reverted"):
			frappe.throw(frappe._("{0} has already been reverted").format(version_name))

		self.db_set("panels", version.get("prior_panels"), update_modified=False)
		version.db_set("reverted", 1, update_modified=False)
		version.db_set("reverted_by", frappe.session.user, update_modified=False)
		version.db_set("reverted_on", now_datetime(), update_modified=False)
