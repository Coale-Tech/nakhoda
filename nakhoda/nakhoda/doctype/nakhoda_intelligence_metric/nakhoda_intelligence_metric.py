# Copyright (c) 2026, Nakhoda and contributors
# For license information, please see license.txt
"""One row of `Nakhoda Intelligence Template.metrics` - a KPI card definition. Pure
data; the fork's hardcoded per-domain KPI-calculation branch is exactly what this
table replaces, so there is no logic here to have a counterpart of."""

from __future__ import annotations

from frappe.model.document import Document


class NakhodaIntelligenceMetric(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		direction: DF.Literal["Higher Is Better", "Lower Is Better"]
		expression: DF.Data
		format: DF.Literal["Number", "Currency", "Percent", "Date"]
		label: DF.Data
		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
		target: DF.Float
	# end: auto-generated types
