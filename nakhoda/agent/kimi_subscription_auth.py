# Copyright (c) 2026, Nakhoda and contributors
# For license information, please see license.txt
"""Kimi Code subscription auth for the Moonshot provider - ported from
`apps/insights/insights/ai/kimi_code_auth.py` (verified on this workstation)
onto `Nakhoda Settings`, and shaped like this app's other device flow
(`agent/chatgpt_subscription_auth.py`).

Kimi has two entirely separate auth worlds and they are NOT interchangeable:

- Moonshot Open Platform - a metered API key against ``api.moonshot.ai``.
- Kimi Code subscription  - OAuth against ``auth.kimi.com``, served from
  ``api.kimi.com/coding/v1``. An Open Platform key is rejected there with 401.

The subscription side uses the RFC 8628 device flow, which needs no browser on
the server and no loopback callback - the only OAuth variant a headless Frappe
host can complete:

    1. POST /api/oauth/device_authorization -> device_code + user_code
    2. operator approves at kimi.com/code/authorize_device
    3. POST /api/oauth/token                -> access + refresh token
       (returns 400 `authorization_pending` until step 2 completes)

Unlike OpenAI's, these endpoints read *form* parameters and reject a JSON body,
and every call must carry a stable device id the grant is bound to - hence
`_headers()` and `_device_id()` rather than the plain JSON POST used by
`chatgpt_subscription_auth.py`.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

import frappe
import requests
from frappe import _

DOCTYPE = "Nakhoda Settings"

# Public Kimi CLI client id, as used by the Kimi Code device flow.
CLIENT_ID = "17e5f671-d194-4dfb-9706-5516cb48c098"
DEFAULT_OAUTH_HOST = "https://auth.kimi.com"
CODING_BASE_URL = "https://api.kimi.com/coding/v1"
DEVICE_GRANT = "urn:ietf:params:oauth:grant-type:device_code"

PENDING_CACHE_KEY = "nakhoda:kimi_code_device_login"
PENDING_TTL = 1800  # Kimi device codes live 30 minutes
REFRESH_SKEW = 120  # refresh this many seconds before nominal expiry

#: Models served by the Kimi Code subscription - distinct from the Open
#: Platform ids, and the pair `providers.models()` maps onto FAST/BALANCED.
SUBSCRIPTION_MODELS = ("kimi-for-coding", "kimi-for-coding-highspeed")

#: What the token endpoint's `error` means while nobody has finished approving
#: or rejecting the device code yet, or after the window closes.
_ERROR_STATUS = {
	"authorization_pending": "pending",
	"slow_down": "pending",
	"expired_token": "expired",
	"invalid_grant": "expired",
	"access_denied": "denied",
}


def _oauth_host() -> str:
	import os

	return (os.environ.get("KIMI_CODE_OAUTH_HOST") or DEFAULT_OAUTH_HOST).rstrip("/")


def _guard() -> None:
	"""Only someone who may edit the settings may move the credential."""
	frappe.has_permission(DOCTYPE, "write", throw=True)


def _device_id() -> str:
	"""Stable per-site device id; Kimi ties the grant to it, so it is minted
	once and reused rather than regenerated per request."""
	existing = frappe.db.get_single_value(DOCTYPE, "kimi_device_id")
	if existing:
		return str(existing)
	generated = uuid.uuid4().hex
	frappe.db.set_single_value(DOCTYPE, "kimi_device_id", generated)
	frappe.db.commit()  # nosemgrep - the id must survive the request that minted it
	return generated


def _headers() -> dict[str, str]:
	"""Identify as a Kimi CLI-style client. The form content type is not
	optional: the OAuth endpoints reject a JSON body outright."""
	return {
		"Content-Type": "application/x-www-form-urlencoded",
		"User-Agent": "Nakhoda/1.0",
		"X-Msh-Platform": "kimi_cli",
		"X-Msh-Device-Id": _device_id(),
	}


def _oauth_request(path: str, payload: dict[str, str]) -> tuple[int, dict[str, Any], str]:
	"""One form POST at an OAuth endpoint. Returns `(http_status, parsed_body,
	transport_error)` so start/poll/refresh branch on the same three-way shape
	instead of each re-wrapping `requests.RequestException` and a possibly
	non-JSON body on their own."""
	try:
		response = requests.post(f"{_oauth_host()}{path}", data=payload, headers=_headers(), timeout=30)
	except requests.RequestException as exc:
		return 0, {}, str(exc)
	try:
		return response.status_code, response.json(), ""
	except ValueError:
		return response.status_code, {}, ""


def _persist(tokens: dict[str, Any]) -> str:
	"""Store a freshly minted credential and report the label it is shown as."""
	access_token = tokens.get("access_token") or ""
	if not access_token:
		frappe.throw(_("Kimi returned no access token."))

	label = _("Kimi Code subscription")
	updates = {
		"kimi_oauth_access_token": access_token,
		"kimi_oauth_refresh_token": tokens.get("refresh_token") or "",
		"kimi_oauth_expires_at": int(time.time()) + int(tokens.get("expires_in") or 3600),
		"kimi_oauth_account_label": label,
		# Connecting is the intent to use it - otherwise the credential sits
		# stored but ignored while the client stays on the metered key.
		"moonshot_auth_mode": "Kimi Subscription",
	}
	for fieldname, value in updates.items():
		if fieldname == "kimi_oauth_refresh_token" and not value:
			continue
		frappe.db.set_single_value(DOCTYPE, fieldname, value)
	frappe.db.commit()  # nosemgrep - land the newly minted credential now, not at request end
	return label


@frappe.whitelist()
def start_kimi_login() -> dict[str, Any]:
	"""Ask Kimi for a device code and hand the operator something to type in at
	the verification URL."""
	_guard()
	status_code, body, network_error = _oauth_request(
		"/api/oauth/device_authorization", {"client_id": CLIENT_ID}
	)
	if network_error:
		return {"success": False, "error": _("Could not reach Kimi: {0}").format(network_error[:200])}
	if status_code != 200:
		return {"success": False, "error": f"Kimi rejected the request (HTTP {status_code})."}

	device_code = body.get("device_code")
	user_code = body.get("user_code")
	if not device_code or not user_code:
		return {"success": False, "error": _("The device-code response was missing required fields.")}

	frappe.cache().set_value(PENDING_CACHE_KEY, {"device_code": device_code}, expires_in_sec=PENDING_TTL)
	return {
		"success": True,
		"user_code": user_code,
		"verification_url": body.get("verification_uri_complete") or body.get("verification_uri"),
		"interval": int(body.get("interval") or 5),
		"expires_in": int(body.get("expires_in") or PENDING_TTL),
	}


@frappe.whitelist()
def poll_kimi_login() -> dict[str, Any]:
	"""Ask once whether the operator has approved the device code yet - the
	browser tab drives the retry cadence, this only answers the current
	question."""
	_guard()
	pending = frappe.cache().get_value(PENDING_CACHE_KEY)
	if not pending:
		return {
			"success": False,
			"status": "expired",
			"error": _("Start the login again - the code expired."),
		}

	status_code, body, network_error = _oauth_request(
		"/api/oauth/token",
		{"client_id": CLIENT_ID, "device_code": pending["device_code"], "grant_type": DEVICE_GRANT},
	)
	if network_error:
		return {"success": False, "status": "error", "error": network_error[:200]}

	if status_code == 200:
		label = _persist(body)
		frappe.cache().delete_value(PENDING_CACHE_KEY)
		return {"success": True, "status": "connected", "account": {"account_label": label}}

	resolved = _ERROR_STATUS.get(body.get("error") or "")
	if resolved == "pending":
		return {"success": False, "status": "pending"}
	if resolved in ("expired", "denied"):
		frappe.cache().delete_value(PENDING_CACHE_KEY)
		message = (
			_("The code expired. Start again.") if resolved == "expired" else _("Authorization was denied.")
		)
		return {"success": False, "status": resolved, "error": message}

	fallback_message = body.get("error_description") or body.get("error") or f"HTTP {status_code}"
	return {"success": False, "status": "error", "error": fallback_message}


@frappe.whitelist()
def disconnect_kimi() -> dict[str, Any]:
	"""Forget the stored subscription credential and fall back to the API key."""
	_guard()
	reset_fields = {
		"kimi_oauth_access_token": "",
		"kimi_oauth_refresh_token": "",
		"kimi_oauth_account_label": "",
		"kimi_oauth_expires_at": 0,
		"moonshot_auth_mode": "API Key",
	}
	for fieldname, value in reset_fields.items():
		frappe.db.set_single_value(DOCTYPE, fieldname, value)
	frappe.db.commit()  # nosemgrep - land the disconnect now, not at request end
	frappe.cache().delete_value(PENDING_CACHE_KEY)
	return {"success": True}


@frappe.whitelist()
def kimi_auth_status() -> dict[str, Any]:
	"""Read-only view of the stored credential - the caller learns whether one
	exists and whether it has gone stale, never the token itself."""
	settings = frappe.get_single(DOCTYPE)
	expires_at = int(getattr(settings, "kimi_oauth_expires_at", 0) or 0)
	return {
		"connected": bool(settings.get_password("kimi_oauth_access_token", raise_exception=False)),
		"account_label": getattr(settings, "kimi_oauth_account_label", "") or "",
		"expires_at": expires_at,
		"expired": bool(expires_at) and expires_at <= int(time.time()),
		"models": list(SUBSCRIPTION_MODELS),
	}


def _refresh(settings) -> str | None:
	"""Trade a stored refresh token for a new access token, shortly before the
	old one goes stale."""
	refresh_token = settings.get_password("kimi_oauth_refresh_token", raise_exception=False)
	if not refresh_token:
		return None

	status_code, body, network_error = _oauth_request(
		"/api/oauth/token",
		{"client_id": CLIENT_ID, "grant_type": "refresh_token", "refresh_token": refresh_token},
	)
	if network_error or status_code != 200:
		return None

	# A refresh response may omit the refresh token entirely - carry the
	# working one forward instead of losing it.
	body.setdefault("refresh_token", refresh_token)
	_persist(body)
	return body.get("access_token")


def get_access_token(settings=None) -> str | None:
	"""Return a usable access token, refreshing it first when it is close
	enough to expiring that the caller's own request would otherwise race it."""
	settings = settings or frappe.get_single(DOCTYPE)
	token = settings.get_password("kimi_oauth_access_token", raise_exception=False)
	if not token:
		return None
	expires_at = int(getattr(settings, "kimi_oauth_expires_at", 0) or 0)
	about_to_expire = bool(expires_at) and expires_at - REFRESH_SKEW <= int(time.time())
	return (_refresh(settings) or token) if about_to_expire else token
