# Copyright (c) 2026, Nakhoda and contributors
# For license information, please see license.txt
"""Site-wide defaults.

Note what is *not* here: a switch for user permissions. Insights ships one and
it defaults to off (`insights_settings.json`, `apply_user_permissions`), which
is how a BI tool ends up showing every viewer every row and calling it
configuration. In this app permissions are injected by the resolver that builds
every pipeline, so there is no code path that could honour such a switch.
"""

from __future__ import annotations

from frappe.model.document import Document


class NakhodaSettings(Document):

	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		cache_ttl: DF.Int
		max_rows: DF.Int
		model: DF.Data | None
		model_provider: DF.Literal["OpenAI", "Anthropic", "OpenRouter", "Local"]
		strict_columns: DF.Check
		token_budget: DF.Int
	# end: auto-generated types
	pass
