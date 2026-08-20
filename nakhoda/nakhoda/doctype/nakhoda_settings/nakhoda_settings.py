# Copyright (c) 2026, Nakhoda and contributors
# For license information, please see license.txt
"""Site-wide defaults.

Note what is *not* here: a switch for user permissions. Insights ships one and
it defaults to off (`insights_settings.json`, `apply_user_permissions`), which
is how a BI tool ends up showing every viewer every row and calling it
configuration. In this app permissions are injected by the resolver that builds
every pipeline, so there is no code path that could honour such a switch.

The AI half is a port of Insights' own AI Analytics settings
(`insights/insights/doctype/insights_settings/insights_settings.json`, verified
on this bench): one named provider (`ai_provider`) selecting which credential
and model fields are read, rather than a single anonymous Base URL/API Key
pair. That shape was chosen over the previous `agent_provider`/`agent_base_url`/
`agent_api_key` trio for one concrete reason - Ollama, NVIDIA, the Moonshot
Open Platform and the two subscription backends each need *different*
credentials and hosts, and a single pair cannot hold two of them at once, so
switching providers meant retyping a key that had been working the day before.
Per-provider fields keep each one where it was left. `nakhoda/patches/v1_0/
migrate_ai_provider_settings.py` carries the old trio's values across.

Readers of these fields, all DB-first, env-fallback (an admin's change takes
effect without a redeploy; a fresh install with nothing set here still runs on
the ops-configured environment variables):

- `agent/providers.py` - `credentials()`, `subscription_headers()`
- `agent/tiers.py` - `models()`, FAST/BALANCED off `ai_model`/`ai_model_fallback`
- `agent/quota.py` - `check()`, `increment()`, `reset_if_due()`
- `agent/chatgpt_subscription_auth.py`, `agent/kimi_subscription_auth.py` -
  the only writers of the `*_oauth_*` fields

The Data Store half (`enable_data_store`, `max_records_to_sync`,
`max_memory_usage`) is ported from Insights' own data-store settings tab.

`enable_data_store` gates *movement*, not *reading*: with it off no new table
may be copied and the daily refresh stops, but tables already in the warehouse
stay queryable. The alternative - a switch that makes landed data vanish from
answers - would give two different results for one question depending on a
checkbox nobody re-reads, which is worse than no switch. `import_table` refuses
with a message naming the setting rather than failing silently, because a
disabled feature that behaves like a broken one costs an afternoon.

All three fields share the unwritten-Single hazard: a fresh site has no
`tabSingles` row, so a Check reads `0` and an Int reads `0` (the bug
`agent/providers.py:enabled` documents). The shipped defaults are therefore
`1`/`1000000`/`512` in the schema *and* re-asserted in the readers - the
Ints fall back with `or 1_000_000` / `or 512`, and the Check is read through
`data_store_enabled()`, which treats "never written" as enabled rather than as
an admin's explicit off.

Readers: `api/data_store.py` - `data_store_enabled()`, `_row_limit()`,
`_memory_limit()`.
"""

from __future__ import annotations

import frappe
from frappe.model.document import Document
from frappe.query_builder import DocType

DOCTYPE = "Nakhoda Settings"

#: The two Data Store caps, in one place because three parties need the same
#: number: `validate` below (so the form can never store a value the readers
#: would have to override), `api/data_store.py`'s `_row_limit`/`_memory_limit`
#: (so a never-written Single still imports), and the settings page's
#: placeholders. `0` is not a legal value for either - a zero row cap would
#: import nothing and a zero memory cap would make DuckDB refuse to run - so
#: it is read as "unset", never as "none allowed".
DEFAULT_ROW_LIMIT = 1_000_000
DEFAULT_MEMORY_MB = 512


def setting_enabled(fieldname: str, settings=None) -> bool:
	"""Read a Check field where *absent* must not read as *off*.

	`getattr` on the loaded document cannot tell the two apart:
	`BaseDocument.init_valid_columns` casts a missing value to `0`
	(`apps/frappe/frappe/model/base_document.py`), so a field whose row was
	never written - a fresh install, or a Single saved before the field
	existed - is indistinguishable from an admin's explicit off. Every such
	field here ships `"default": "1"`, so reading the cast zero as off would
	disable the feature on exactly the sites that never touched it.

	`tabSingles` holds one row per *written* field, so presence there is the
	only honest signal. The cheap answer is therefore trusted only when it
	says on; a zero is checked against the row before it is believed, which
	costs one indexed lookup and only on the off path.

	Callers: `agent/providers.py:enabled` (`enable_ai`),
	`api/data_store.py:data_store_enabled` (`enable_data_store`).
	`patches/v1_0/migrate_ai_provider_settings.py` deliberately keeps its own
	copy - a patch must go on meaning what it meant when it was written, even
	if this helper later changes.
	"""
	settings = settings or frappe.get_cached_doc(DOCTYPE)
	if int(getattr(settings, fieldname, 0) or 0):
		return True

	singles = DocType("Singles")
	written = (
		frappe.qb.from_(singles)
		.select(singles.field)
		.where((singles.doctype == DOCTYPE) & (singles.field == fieldname))
		.run()
	)
	return not written


class NakhodaSettings(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		ai_model: DF.Data | None
		ai_model_fallback: DF.Data | None
		ai_provider: DF.Literal["openrouter", "openai", "nvidia", "ollama", "ollama_cloud", "moonshot"]  # type: ignore[reportUndefinedVariable]
		ai_quota_used: DF.Int
		cache_ttl: DF.Int
		chatgpt_oauth_access_token: DF.Password | None
		chatgpt_oauth_account_id: DF.Data | None
		chatgpt_oauth_account_label: DF.Data | None
		chatgpt_oauth_expires_at: DF.Int
		chatgpt_oauth_refresh_token: DF.Password | None
		daily_ai_quota: DF.Int
		enable_ai: DF.Check
		enable_data_store: DF.Check
		kimi_device_id: DF.Data | None
		kimi_oauth_access_token: DF.Password | None
		kimi_oauth_account_label: DF.Data | None
		kimi_oauth_expires_at: DF.Int
		kimi_oauth_refresh_token: DF.Password | None
		last_ai_answer: DF.Datetime | None
		max_memory_usage: DF.Int
		max_records_to_sync: DF.Int
		max_rows: DF.Int
		moonshot_api_key: DF.Password | None
		moonshot_auth_mode: DF.Literal["API Key", "Kimi Subscription"]  # type: ignore[reportUndefinedVariable]
		moonshot_model: DF.Data | None
		nvidia_api_key: DF.Password | None
		nvidia_model: DF.Data | None
		ollama_api_key: DF.Password | None
		ollama_base_url: DF.Data | None
		ollama_model: DF.Data | None
		openai_api_key: DF.Password | None
		openai_auth_mode: DF.Literal["API Key", "ChatGPT Subscription"]  # type: ignore[reportUndefinedVariable]
		openai_base_url: DF.Data | None
		openai_model: DF.Data | None
		openrouter_api_key: DF.Password | None
		quota_reset_schedule: DF.Literal["Disabled", "Daily", "Weekly", "Monthly"]  # type: ignore[reportUndefinedVariable]
		quota_window_start: DF.Datetime | None
		strict_columns: DF.Check
	# end: auto-generated types

	def validate(self) -> None:
		"""Replace a blank or zero cap with the shipped default.

		Both fields are Int, so clearing the box on the settings page stores
		`0` - and `0` is the one value neither cap can mean literally. The
		readers already override it (`_row_limit`/`_memory_limit`), which kept
		imports correct but left the page showing `0` over a worker copying a
		million rows: two answers to "what is the limit", and the wrong one on
		screen. Writing the real number back on save keeps the form, the
		worker and the DB saying the same thing, and makes clearing the box a
		way to ask for the default rather than a way to break the import.
		"""
		self.max_records_to_sync = int(self.max_records_to_sync or 0) or DEFAULT_ROW_LIMIT
		self.max_memory_usage = int(self.max_memory_usage or 0) or DEFAULT_MEMORY_MB
