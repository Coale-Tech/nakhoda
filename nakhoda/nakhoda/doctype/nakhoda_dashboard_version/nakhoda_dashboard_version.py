# Copyright (c) 2026, Nakhoda and contributors
# For license information, please see license.txt
"""One row per applied `DashboardPatch` - a full `panels` snapshot taken
*before* the patch, not the patch's inverse. `NakhodaIntelligenceTemplate.
revert` reads `prior_panels` back verbatim, so reverting restores exactly
what existed a moment ago rather than replaying an inverse op sequence that
could drift from the recorded diff (`engine/dashboard.py`'s own docstring).

Written by `NakhodaIntelligenceTemplate.apply_patch` with
`ignore_permissions=True` - like `Nakhoda Agent Run`, a caller who is
already authorized to patch the dashboard should not also need `create` on
the log of having done so.
"""

from __future__ import annotations

from frappe.model.document import Document


class NakhodaDashboardVersion(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		applied_by: DF.Link
		applied_on: DF.Datetime
		dashboard: DF.Link
		diff: DF.JSON
		patch_ops: DF.JSON
		prior_panels: DF.JSON
		reverted: DF.Check
		reverted_by: DF.Link | None
		reverted_on: DF.Datetime | None
	# end: auto-generated types
