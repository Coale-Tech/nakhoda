# Copyright (c) 2026, Nakhoda and contributors
# For license information, please see license.txt
"""Agent scope: which source it answers from and what it is told beyond that.

Kept deliberately small for Phase 4. Verified queries are not scoped here - the
agent matches a question against every `Nakhoda Verified Query` the caller can
read (`agent/verified.py`), the same way Frappe permissions already bound that
set; a second membership list on this doctype would be a second place the two
could drift. MCP servers are Phase 6's child table, added to this doctype then,
not stubbed now.
"""

from __future__ import annotations

import frappe
from frappe.model.document import Document

#: Databricks states longer degrades quality (`12-build-plan.md` invariant 5).
#: Twenty lines, not twenty-thousand characters: the ceiling is about how much a
#: model can be expected to actually follow, not a storage limit.
MAX_INSTRUCTION_LINES = 20


class NakhodaSpace(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		default_source: DF.Link | None
		disabled: DF.Check
		instructions: DF.SmallText | None
		is_default: DF.Check
		title: DF.Data
	# end: auto-generated types

	def validate(self) -> None:
		lines = [ln for ln in (self.instructions or "").splitlines() if ln.strip()]
		if len(lines) > MAX_INSTRUCTION_LINES:
			frappe.throw(
				frappe._("Instructions must be {0} lines or fewer (got {1}).").format(
					MAX_INSTRUCTION_LINES, len(lines)
				)
			)
		if self.is_default:
			existing = frappe.get_all(
				self.doctype, filters={"is_default": 1, "name": ["!=", self.name]}, pluck="name"
			)
			for other in existing:
				frappe.db.set_value(self.doctype, other, "is_default", 0)

	def resolve_source(self) -> str:
		"""This space's source, or the site-wide default when it names none."""
		from nakhoda.api import default_source

		return self.default_source or default_source()
