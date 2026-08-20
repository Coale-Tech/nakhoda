# Copyright (c) 2026, Nakhoda and contributors
# For license information, please see license.txt
"""Carry the single `agent_provider`/`agent_base_url`/`agent_api_key` trio and
the three tier-model fields onto the per-provider fields that replaced them
(`nakhoda_settings.json`, and `agent/providers.py` for why).

Runs post-model-sync, so the new fields exist by the time it writes. The old
values are read straight out of `tabSingles`/`__Auth` - the columns are gone
from the doctype JSON, but a Single's values are rows, not columns, and they
survive the schema change until something deletes them, which this patch does
last so a re-run after a failure still finds them.

Idempotent: every write is guarded on the destination being empty, so running
it twice cannot clobber a key an admin typed in between.
"""

from __future__ import annotations

import frappe
from frappe.query_builder import DocType
from frappe.utils.password import get_decrypted_password, remove_encrypted_password, set_encrypted_password

DOCTYPE = "Nakhoda Settings"

#: Old `agent_provider` label -> new `ai_provider` key. "Other
#: (OpenAI-Compatible)" has no named counterpart; it was almost always an
#: OpenAI-compatible gateway, which `openai` + a Base URL still expresses.
PROVIDER_MAP = {
	"OpenRouter": "openrouter",
	"OpenAI": "openai",
	"Ollama": "ollama",
	"NVIDIA": "nvidia",
	"Moonshot (Kimi)": "moonshot",
	"Other (OpenAI-Compatible)": "openai",
}

#: Which provider's credential and model fields the old anonymous pair maps to.
KEY_FIELD = {
	"openrouter": "openrouter_api_key",
	"openai": "openai_api_key",
	"nvidia": "nvidia_api_key",
	"ollama": "ollama_api_key",
	"moonshot": "moonshot_api_key",
}
BASE_URL_FIELD = {"openai": "openai_base_url", "ollama": "ollama_base_url"}
MODEL_FIELD = {
	"openrouter": "ai_model",
	"openai": "openai_model",
	"nvidia": "nvidia_model",
	"ollama": "ollama_model",
	"moonshot": "moonshot_model",
}

OLD_FIELDS = (
	"agent_provider",
	"agent_base_url",
	"agent_api_key",
	"agent_auth_mode",
	"model_fast",
	"model_balanced",
	"model_premium",
)


def _old(fieldname: str) -> str:
	"""A pre-migration value, read from the Single's own rows rather than
	through the doctype - the field is no longer in the meta, so
	`get_single_value` would `throw` on it.

	The query builder, not `frappe.db.get_value`: the latter defaults to
	`ORDER BY creation`, and `tabSingles` has three columns and no metadata
	(`MySQLdb.OperationalError: Unknown column 'creation' in 'ORDER BY'`).
	"""
	singles = DocType("Singles")
	rows = (
		frappe.qb.from_(singles)
		.select(singles.value)
		.where((singles.doctype == DOCTYPE) & (singles.field == fieldname))
		.run()
	)
	value = rows[0][0] if rows else None
	return str(value) if value else ""


def _first_model(raw: str) -> str:
	"""The old fields held a comma-separated fallback list; the new ones hold
	one id each, so keep the first - the one that was actually tried first."""
	return next((m.strip() for m in raw.split(",") if m.strip()), "")


def _row_written(fieldname: str) -> bool:
	"""Whether the Single already has a row for `fieldname`. Distinct from
	`_old(...) == ""`: a Check field stored as "0" is a written row, and this
	patch must not overwrite an admin's explicit "off"."""
	singles = DocType("Singles")
	return bool(
		frappe.qb.from_(singles)
		.select(singles.field)
		.where((singles.doctype == DOCTYPE) & (singles.field == fieldname))
		.run()
	)


def _fill(fieldname: str, value: str) -> None:
	if value and not frappe.db.get_single_value(DOCTYPE, fieldname):
		frappe.db.set_single_value(DOCTYPE, fieldname, value)


def execute() -> None:
	if not frappe.db.exists("DocType", DOCTYPE):
		return

	provider = PROVIDER_MAP.get(_old("agent_provider"), "openrouter")
	_fill("ai_provider", provider)

	# An install that was answering questions before this patch must keep
	# answering them after it. The new master switch defaults to 1 for a fresh
	# install, but this Single's row was written before the field existed, so
	# it has no row of its own - and a Check field with no row reads back as 0
	# (`BaseDocument.init_valid_columns`), i.e. off. Writing the row makes the
	# value explicit, which is the only state `providers.enabled()` can trust.
	if not _row_written("enable_ai"):
		frappe.db.set_single_value(DOCTYPE, "enable_ai", 1)

	if _old("agent_auth_mode") == "ChatGPT Subscription":
		_fill("openai_auth_mode", "ChatGPT Subscription")

	base_url_field = BASE_URL_FIELD.get(provider)
	if base_url_field:
		_fill(base_url_field, _old("agent_base_url"))

	_fill(MODEL_FIELD[provider], _first_model(_old("model_fast")))
	if provider == "openrouter":
		_fill("ai_model_fallback", _first_model(_old("model_balanced")))

	# Two old values have no destination, and dropping either one silently
	# would change which model answers without telling anyone: PREMIUM is
	# environment-only now (`agent/tiers.py`), and only OpenRouter carries a
	# second model on the page. Say so once, here, where an upgrade is being
	# watched - not in a log nobody reads afterwards.
	dropped = {"model_premium": _old("model_premium")}
	if provider != "openrouter":
		dropped["model_balanced"] = _old("model_balanced")
	for fieldname, value in dropped.items():
		if value:
			print(
				f"Nakhoda: {fieldname} = {value!r} has no field in the new AI Provider tab. "
				f"Set NAKHODA_AGENT_MODEL_{fieldname.split('_')[1].upper()} to keep that rung."
			)

	old_key = get_decrypted_password(DOCTYPE, DOCTYPE, "agent_api_key", raise_exception=False)
	key_field = KEY_FIELD[provider]
	if old_key and not get_decrypted_password(DOCTYPE, DOCTYPE, key_field, raise_exception=False):
		set_encrypted_password(DOCTYPE, DOCTYPE, old_key, key_field)
		# The Password field's own row holds the masking dummy, not the secret
		# (`base_document._save_passwords`); without it the settings form shows
		# an empty box over a stored credential.
		frappe.db.set_single_value(DOCTYPE, key_field, "*" * len(old_key))

	remove_encrypted_password(DOCTYPE, DOCTYPE, "agent_api_key")
	frappe.db.delete("Singles", {"doctype": DOCTYPE, "field": ("in", OLD_FIELDS)})
