# Copyright (c) 2026, Nakhoda and contributors
# For license information, please see license.txt
"""One row of `Nakhoda Intelligence Template.ml` - which Phase 8 ML operation the
domain dashboard attaches, and to which output column. Pure data; validated by
`engine/operations.py` at pipeline-compile time, not here."""

from __future__ import annotations

from frappe.model.document import Document


class NakhodaIntelligenceMLOperation(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		column: DF.Data | None
		operation: DF.Literal["forecast", "detect_anomalies", "segment", "score"]
		params: DF.JSON | None
		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
	# end: auto-generated types
