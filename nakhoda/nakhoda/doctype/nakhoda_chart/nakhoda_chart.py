# Copyright (c) 2026, Nakhoda and contributors
# For license information, please see license.txt
"""A saved chart: one query, plus how to draw it.

`config` is the same shape `agent/charts.py` already emits and `Chart.vue`
already renders. That is not a coincidence to preserve casually - it is what
lets a chart the agent proposed in a chat turn be saved into a workbook without
a translation layer, and it is why this DocType stores the config rather than
re-deriving it from the query.

**A chart holds no pipeline of its own.** Insights gives every chart a hidden
`Insights Query v3` (`insights_chart_v3.py:set_data_query`) so chart-level
transforms can stack on top of the source query. Nakhoda does not, for two
reasons. `Nakhoda Query` has `data_source` and `operations` as `reqd`, so the
hidden row would need a synthetic data source and a synthetic empty pipeline to
exist at all - inventing two required values to store nothing. And that hidden
row is the single source of the orphan it leaves behind on workbook delete
(see `nakhoda_workbook.py`). Chart-level shaping belongs in `config`, which the
renderer already reads; when a chart genuinely needs different rows, the honest
answer is a second query the user can see and correct.

`folder` is `Data`, not a `Link`. Folders are per-workbook rows and a chart may
sit at the root, so the alternative is a nullable Link whose target is scoped by
a second field - a constraint the database cannot express either way.
"""

from __future__ import annotations

import frappe
from frappe.model.document import Document


class NakhodaChart(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		chart_type: DF.Data | None
		config: DF.JSON | None
		folder: DF.Data | None
		is_public: DF.Check
		query: DF.Link | None
		sort_order: DF.Int
		title: DF.Data | None
		workbook: DF.Link

	# end: auto-generated types

	def validate(self) -> None:
		self.validate_query_workbook()

	def validate_query_workbook(self) -> None:
		"""A chart may only read a query in its own workbook, or a loose one.

		Reading across workbooks would make a workbook's export incomplete -
		the copy would carry a chart whose query is not in the payload, and
		restore would hand it a dangling Link. Ad-hoc queries (no workbook at
		all, the ones the agent writes) are allowed: they belong to nobody, so
		naming one costs the container nothing.
		"""
		if not self.query:
			return

		# `Nakhoda Workbook` is autoincrement-named, so a Link to it is an `int`
		# on an in-memory document and a varchar in the database. Comparing the
		# two raw would refuse every chart whose query is in this very workbook.
		owner = frappe.db.get_value("Nakhoda Query", self.query, "workbook")
		if owner and str(owner) != str(self.workbook):
			frappe.throw(
				frappe._("Query {0} belongs to another workbook.").format(frappe.bold(self.query)),
				title=frappe._("Query is not in this workbook"),
			)

	def on_trash(self) -> None:
		self.cleanup_empty_folder()

	def cleanup_empty_folder(self) -> None:
		"""Drop the folder this chart was the last thing in.

		A folder is a grouping, not a place - an empty one is a row the sidebar
		has to render and the user has to tidy. Charts and queries can share a
		folder label, so both are checked before the row goes.
		"""
		if not self.folder:
			return

		still_used = frappe.db.exists(
			"Nakhoda Chart", {"workbook": self.workbook, "folder": self.folder, "name": ("!=", self.name)}
		) or frappe.db.exists("Nakhoda Query", {"workbook": self.workbook, "folder": self.folder})
		if still_used:
			return

		folder = frappe.db.get_value(
			"Nakhoda Folder", {"workbook": self.workbook, "title": self.folder, "type": "chart"}, "name"
		)
		if folder:
			frappe.delete_doc("Nakhoda Folder", str(folder), ignore_permissions=True, force=True)
