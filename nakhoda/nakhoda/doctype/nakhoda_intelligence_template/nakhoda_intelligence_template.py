# Copyright (c) 2026, Nakhoda and contributors
# For license information, please see license.txt
"""A domain dashboard as a declarative record - `key`/`title`/`icon`/`color` for
identity, `source` for its one query, `metrics`/`panels`/`skill`/`ml` for its
content. This file has nothing to validate that the doctype's own field types
don't already enforce: `metrics`/`ml` are Table fields, so Frappe rejects a
malformed row before `validate()` would ever see one; `panels` is a JSON field,
so a malformed document is rejected on save the same way `operations` is on
`Nakhoda Verified Query`.

Shipping and versioning - discovery, import, update-in-place, and the
`migrate`-time sync - live in `api/templates.py`, not here, because none of it
needs a bound document to run against; it operates on the shipped
`manifest.json`/`template.json` pairs and this doctype's rows as data.
"""

from __future__ import annotations

from frappe.model.document import Document


class NakhodaIntelligenceTemplate(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		from nakhoda.nakhoda.doctype.nakhoda_intelligence_metric.nakhoda_intelligence_metric import (
			NakhodaIntelligenceMetric,
		)
		from nakhoda.nakhoda.doctype.nakhoda_intelligence_ml_operation.nakhoda_intelligence_ml_operation import (
			NakhodaIntelligenceMLOperation,
		)

		color: DF.Data | None
		from_template: DF.Data | None
		icon: DF.Data | None
		imported_checksum: DF.Data | None
		imported_version: DF.Int
		key: DF.Data
		metrics: DF.Table[NakhodaIntelligenceMetric]
		ml: DF.Table[NakhodaIntelligenceMLOperation]
		panels: DF.JSON
		skill: DF.LongText | None
		source: DF.Link | None
		title: DF.Data
	# end: auto-generated types
