# Copyright (c) 2026, Nakhoda and contributors
# For license information, please see license.txt
"""A grid of tiles inside a workbook.

Distinct from `Nakhoda Intelligence Template`, and the distinction is the
reason this DocType exists. A template is a *shipped artifact* - a bundle with a
manifest and a checksum that a site imports, and whose panels are authored
upstream. A dashboard is something a user builds here, out of charts that live
in the same workbook. Both render tiles; only one of them can be edited by the
person looking at it.

The layout lives in `items` as JSON rather than in a child table. A child table
would give free validation of the chart Link and a queryable row per tile, but
tile geometry changes on every drag - a child table means Frappe diffs and
re-inserts rows for what is, semantically, one document edit. `linked_charts`
buys back the only thing the JSON column costs: it is derived from `items` on
every save, so "which dashboards use this chart" stays a `frappe.get_all` and
never a scan.
"""

from __future__ import annotations

from typing import Any

import frappe
from frappe.model.document import Document


class NakhodaDashboard(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		from nakhoda.nakhoda.doctype.nakhoda_dashboard_chart.nakhoda_dashboard_chart import (
			NakhodaDashboardChart,
		)

		is_public: DF.Check
		items: DF.JSON | None
		linked_charts: DF.TableMultiSelect[NakhodaDashboardChart]
		preview_image: DF.Data | None
		share_link: DF.Data | None
		title: DF.Data | None
		vertical_compact_layout: DF.Check
		workbook: DF.Link

	# end: auto-generated types

	def before_save(self) -> None:
		self.set_linked_charts()

	def set_linked_charts(self) -> None:
		"""Mirror the chart tiles in `items` into the child table.

		Rebuilt wholesale rather than diffed: the list is small, and a partial
		update is how a stale link survives a tile being removed. Duplicates
		collapse - two tiles may show the same chart, but "uses this chart" is
		answered once.
		"""
		charts: list[str] = []
		for item in self.get_items():
			if item.get("type") != "chart":
				continue
			chart = item.get("chart")
			if chart and chart not in charts:
				charts.append(chart)

		self.linked_charts = []
		for chart in charts:
			self.append("linked_charts", {"chart": chart})

	def get_items(self) -> list[dict[str, Any]]:
		"""The tiles, as a list of dicts, whatever the column happens to hold.

		`items` arrives as a JSON string from the REST layer, as a list from a
		Python caller, and as `None` on a dashboard that has never been saved.
		Callers should not each have to know that.
		"""
		parsed = frappe.parse_json(self.items) if isinstance(self.items, str) else self.items
		if not isinstance(parsed, list):
			return []
		return [item for item in parsed if isinstance(item, dict)]
