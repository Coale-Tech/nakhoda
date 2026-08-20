# Copyright (c) 2026, Nakhoda and contributors
# For license information, please see license.txt
"""A flat grouping label inside one workbook section.

The name oversells it, and deliberately so - it matches what users call the
thing. There is no nesting: a folder has no parent, holds no children, and owns
nothing. Queries and charts carry a `folder` **Data** field naming one, and
`sort_order` decides what comes first. Insights' `Insights Folder` behaves the
same way despite reading like a tree.

A real tree would need recursive reads for the sidebar, cycle checks on move,
and a decision about what happens to descendants on delete. It would buy
one visual affordance. Two levels of grouping - section, then folder - is what
a workbook of a few dozen documents actually needs.

`type` scopes the folder to one section, because a folder that appeared under
both Queries and Charts would be two different groupings wearing one name.
"""

from __future__ import annotations

from frappe.model.document import Document


class NakhodaFolder(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		is_expanded: DF.Check
		sort_order: DF.Int
		title: DF.Data
		type: DF.Literal["query", "chart"]
		workbook: DF.Link

	# end: auto-generated types
	pass
