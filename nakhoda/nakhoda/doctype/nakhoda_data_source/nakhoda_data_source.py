# Copyright (c) 2026, Nakhoda and contributors
# For license information, please see license.txt
"""Where a query's tables come from.

The site's own database is the default and needs no configuration, which is the
whole reason this app can be useful the minute it is installed: the data is
already there, described by metadata Frappe already maintains.
"""

from __future__ import annotations

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime

from nakhoda.connectors import Connector, site_db, site_warehouse

SITE_DATABASE = "Site Database"
WAREHOUSE = "DuckDB Warehouse"


class NakhodaDataSource(Document):

	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		is_default: DF.Check
		last_checked: DF.Datetime | None
		source_type: DF.Literal["Site Database", "DuckDB Warehouse"]
		status: DF.Literal["Untested", "Reachable", "Unreachable"]
		title: DF.Data
	# end: auto-generated types
	def validate(self) -> None:
		if self.is_default:
			existing = frappe.get_all(
				self.doctype,
				filters={"is_default": 1, "name": ["!=", self.name]},
				pluck="name",
			)
			for other in existing:
				frappe.db.set_value(self.doctype, other, "is_default", 0)

	def connector(self) -> Connector:
		if self.source_type == WAREHOUSE:
			return site_warehouse()
		return site_db()

	@frappe.whitelist()
	def test_connection(self) -> dict[str, str]:
		"""Reachability, recorded. Reports the failure rather than raising it."""
		try:
			self.connector().backend.list_tables(like="tabDocType")
			status = "Reachable"
			message = frappe._("Connected.")
		except Exception as exc:
			status = "Unreachable"
			message = str(exc)
		self.db_set({"status": status, "last_checked": now_datetime()}, update_modified=False)
		return {"status": status, "message": message}
