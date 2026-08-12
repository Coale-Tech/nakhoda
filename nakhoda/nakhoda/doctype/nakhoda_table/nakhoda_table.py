# Copyright (c) 2026, Nakhoda and contributors
# For license information, please see license.txt
"""One physical table, and what the warehouse knows about it."""

from __future__ import annotations

import frappe
from frappe.model.document import Document


class NakhodaTable(Document):

	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		data_source: DF.Link | None
		document_type: DF.Link | None
		is_child_table: DF.Check
		label: DF.Data | None
		last_synced: DF.Datetime | None
		row_count: DF.Int
		stored_in_warehouse: DF.Check
		sync_error: DF.SmallText | None
		sync_state: DF.Literal["Never", "Syncing", "Synced", "Failed"]
		table_name: DF.Data
	# end: auto-generated types

	def validate(self) -> None:
		if self.document_type and not self.label:
			self.label = frappe.get_meta(self.document_type).get_label()
		if self.document_type:
			self.is_child_table = bool(getattr(frappe.get_meta(self.document_type), "istable", 0))
