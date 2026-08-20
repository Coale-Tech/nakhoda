# Copyright (c) 2026, Nakhoda and contributors
# For license information, please see license.txt
"""What the AI Provider settings tab reads and probes.

Two endpoints, mirroring the pair Insights' AI Analytics page calls
(`insights.ai.openrouter_client.get_ai_status` / `.test_connection`), against
this app's single provider table (`agent/providers.py`) instead of its
per-provider client classes.

`test_connection` reaches a third-party endpoint on the caller's behalf, so it
is gated on write permission for the settings - a read-only user must not be
able to make this site emit authenticated outbound requests. `status` is gated
on read for the same doctype: it reports which provider is configured and how
much quota is left, which is settings content, not public information.
"""

from __future__ import annotations

from typing import Any

import frappe
import requests
from frappe import _

from nakhoda.agent import providers, quota

DOCTYPE = "Nakhoda Settings"
TIMEOUT = 10


@frappe.whitelist()
def status() -> dict[str, Any]:
	"""Everything the tab's header badge and usage strip show: whether AI is
	on, whether a call could actually be made, and where the quota stands."""
	frappe.has_permission(DOCTYPE, "read", throw=True)

	settings = frappe.get_single(DOCTYPE)
	spec = providers.provider(settings)
	primary, fallback = providers.models(settings)
	return {
		"enabled": providers.enabled(settings),
		"configured": providers.configured(settings),
		"provider": spec.key,
		"provider_label": spec.label,
		"base_url": providers.base_url(settings, spec),
		"model": primary,
		"fallback_model": fallback,
		**quota.status(settings),
	}


def _ollama_tags(url: str, api_key: str) -> dict[str, Any]:
	"""Ollama's own model listing. `/api/tags` sits on the daemon root, one
	level above the OpenAI-compatible `/v1` surface everything else uses, and
	is the only way to learn which models an install actually has pulled."""
	root = url[: -len("/v1")] if url.endswith("/v1") else url
	headers = {"Authorization": f"Bearer {api_key}"} if api_key and api_key != "ollama" else {}
	response = requests.get(f"{root}/api/tags", headers=headers, timeout=TIMEOUT)
	if response.status_code != 200:
		return {"success": False, "error": f"Ollama returned HTTP {response.status_code}."}
	models = [m.get("name", "") for m in response.json().get("models", [])]
	return {
		"success": True,
		"message": _("Connected"),
		"data": {"models": models, "model_count": len(models)},
	}


def _openai_compatible_models(
	url: str, api_key: str, headers: dict[str, str] | None = None
) -> dict[str, Any]:
	"""`GET /models` - the one call every OpenAI-compatible gateway answers,
	and the cheapest proof that this key reaches this endpoint."""
	request_headers = {"Authorization": f"Bearer {api_key}"}
	request_headers.update(headers or {})
	response = requests.get(f"{url}/models", headers=request_headers, timeout=TIMEOUT)
	if response.status_code == 401:
		return {"success": False, "error": _("The endpoint rejected this credential (HTTP 401).")}
	if response.status_code != 200:
		return {"success": False, "error": f"API returned status {response.status_code}."}
	models = [m.get("id", "") for m in response.json().get("data", [])]
	return {
		"success": True,
		"message": _("Connected"),
		"data": {"models": models, "model_count": len(models)},
	}


@frappe.whitelist()
def test_connection(provider: str | None = None) -> dict[str, Any]:
	"""Probe one provider with its *saved* credential and report what happened.

	`provider` names which one, so the page can test a provider the admin just
	switched to without it having to be the saved selection. The credential
	itself is always the stored one - this endpoint never accepts a key over
	the wire, so a probe cannot be used to exfiltrate one by pointing it at an
	attacker's base URL.

	Never raises for an unreachable endpoint: "could not connect" is the
	answer the page is asking for, not a server error.
	"""
	frappe.has_permission(DOCTYPE, "write", throw=True)

	settings = frappe.get_single(DOCTYPE)
	spec = providers.PROVIDERS.get(provider or "") or providers.provider(settings)

	try:
		api_key, url = providers.credentials(settings, spec)
	except providers.ModelError as exc:
		return {"success": False, "error": str(exc)}

	try:
		if spec.key in ("ollama", "ollama_cloud"):
			return _ollama_tags(url, api_key)
		if providers._openai_subscription(settings, spec):
			# The ChatGPT backend has no `/models`; the cheapest live proof
			# that the subscription token still works is one tiny completion.
			primary, _fallback = providers.models(settings)
			providers._codex_complete("ping", primary, settings)
			return {"success": True, "message": _("ChatGPT subscription active")}
		return _openai_compatible_models(url, api_key, providers.subscription_headers(settings))
	except requests.Timeout:
		return {"success": False, "error": _("The connection timed out.")}
	except requests.ConnectionError:
		return {"success": False, "error": _("Could not reach {0}.").format(url)}
	except providers.ModelError as exc:
		return {"success": False, "error": str(exc)}
	except Exception as exc:  # the page renders whatever went wrong
		return {"success": False, "error": str(exc)[:200]}
