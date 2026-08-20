# Copyright (c) 2026, Nakhoda and contributors
# For license information, please see license.txt
"""One row of `Nakhoda Dashboard.linked_charts`.

A child table with a single Link, derived on every save from the dashboard's
`items` JSON. It carries no state of its own on purpose: it is an index, and an
index that could disagree with the thing it indexes would be worse than no
index. See `nakhoda_dashboard.py:set_linked_charts`.
"""

from __future__ import annotations

from frappe.model.document import Document


class NakhodaDashboardChart(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		chart: DF.Link
		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data

	# end: auto-generated types
	pass
