# Copyright (c) 2026, Nakhoda and contributors
# For license information, please see license.txt
"""One column of `Nakhoda Semantic Model.fields`.

Pure data, like `Nakhoda Intelligence Metric` is to its template: the parent's
`validate` already reads these rows (a field synonym marks the parent curated),
and `semantic/curation.py` is what writes them. There is nothing here that the
fieldtypes do not already enforce.

`empty` is the one field worth knowing about while reading a row: it means this
site has never written a value in the column, so `semantic/profile.py` has already
dropped it from the description a model is shown. A synonym on an empty column
therefore buys nothing, which is exactly why the flag is visible in the grid.
"""

from __future__ import annotations

from frappe.model.document import Document


class NakhodaSemanticField(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		domain: DF.SmallText | None
		empty: DF.Check
		fieldname: DF.Data
		fieldtype: DF.Data | None
		join_target: DF.Link | None
		label: DF.Data | None
		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
		synonyms: DF.Data | None
	# end: auto-generated types
