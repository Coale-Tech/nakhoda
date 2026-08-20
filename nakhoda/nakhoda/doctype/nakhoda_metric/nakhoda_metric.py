# Copyright (c) 2026, Nakhoda and contributors
# For license information, please see license.txt
"""A measure a person certified: what "revenue" means here, and who says so.

`Nakhoda Semantic Model` describes documents; this describes the numbers read off
them. The distinction is not cosmetic - a metric is the one thing in the semantic
layer with an owner and an approval, because "revenue" is a business definition
before it is an expression, and two teams disagreeing about it is the normal case.

Only the *names* reach retrieval. A certified metric contributes `metric_name` and
its `synonyms` to its document's term set (`semantic/curation.py:_collect`), which is
how a question asking for "turnover" finds `Sales Invoice`. The `definition` never
does: it is an expression for a human to read and a model to imitate, and indexing it
would mean matching a question against SQL fragments - measured on prose elsewhere in
this layer, that is worth 0.4 of a name match at best (`semantic/retrieval.py:PROSE`).

`certified` gates that contribution rather than decorating it: an uncertified metric
is someone's draft, and a draft that silently changes which tables a question
retrieves is the kind of thing that makes an analytics tool untrustworthy.
"""

from __future__ import annotations

import frappe
from frappe.model.document import Document


class NakhodaMetric(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		aggregate: DF.Literal["Sum", "Count", "Distinct Count", "Average", "Min", "Max"]
		certified: DF.Check
		definition: DF.SmallText | None
		document: DF.Link
		fieldname: DF.Data | None
		filters: DF.SmallText | None
		grain: DF.Data | None
		metric_name: DF.Data
		steward: DF.Link | None
		synonyms: DF.Data | None
	# end: auto-generated types

	def validate(self) -> None:
		"""A certified measure has to say who certified it and what it counts.

		Both are refusals rather than defaults. A steward defaulting to the last
		editor would attribute a business definition to whoever fixed a typo, and an
		aggregate over no column defaulting to `Count` would answer a revenue
		question with a row count - wrong, quietly, in the direction of looking
		plausible.
		"""
		if self.aggregate != "Count" and not self.fieldname:
			frappe.throw(
				frappe._("{0} needs a column to {1} over.").format(self.metric_name, self.aggregate),
				title=frappe._("Incomplete Measure"),
			)

		if self.certified and not self.steward:
			frappe.throw(
				frappe._("A certified measure needs a steward: someone answers for this definition."),
				title=frappe._("No Steward"),
			)

	def on_update(self) -> None:
		self._forget()

	def on_trash(self) -> None:
		self._forget()

	def _forget(self) -> None:
		"""Drop the curated-term cache retrieval reads.

		Imported inside the method for the same reason `Nakhoda Semantic Model` does:
		`curation` imports `profile` and `model`, and this controller is loaded on
		every request that touches a metric.
		"""
		from nakhoda.semantic import curation

		curation.forget()
