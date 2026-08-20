# Copyright (c) 2026, Nakhoda and contributors
# For license information, please see license.txt
"""ChatGPT Plus/Pro subscription auth for the OpenAI provider - ported from
`apps/insights/insights/ai/openai_codex_auth.py` (verified on this
workstation), onto `Nakhoda Settings` instead of `Insights Settings` and
`providers.py`'s single-credential-pair shape instead of Insights'
per-provider fields.

Uses OpenAI's device-authorization flow, which needs no loopback callback and
is therefore the only OAuth variant that works on a headless Frappe host:

    1. POST /api/accounts/deviceauth/usercode  -> device_auth_id + user_code
    2. operator approves at auth.openai.com/codex/device
    3. POST /api/accounts/deviceauth/token     -> access + refresh + id token
       (returns 403 `deviceauth_authorization_pending` until step 2 completes)

The resulting credential bills against the ChatGPT subscription rather than a
metered API key, but it is *not* interchangeable with one: subscription
traffic must go to the ChatGPT backend, not api.openai.com - see
`CHATGPT_BACKEND` in `providers.py`.

There is no Claude-subscription counterpart in this module by design: Claude
Code's device flow is scoped to Claude Code itself, and Anthropic has never
published a consumer OAuth API for Claude.ai sessions callable from a
third-party backend (verified 2026-08, per docs.anthropic.com and Claude
Code's own auth docs - only API keys and the Claude Code CLI's own scoped
token are documented integration points). `openai_auth_mode` therefore offers
only "API Key" and "ChatGPT Subscription" - shipping a Claude option here
would be a broken control, not a smaller one.

Request plumbing is deliberately centralised in `_device_request()`: every
step of the flow (start, poll, refresh) is the same "POST JSON, get back
(status, body, transport error)" shape, so the three-way branch lives once
instead of being re-derived at each call site.
"""

from __future__ import annotations

import base64
import json
import time
from typing import Any

import frappe
import requests
from frappe import _

DOCTYPE = "Nakhoda Settings"

# Public Codex client id, as used by the Codex CLI device flow.
CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
SCOPE = "openid profile email offline_access"

_AUTH_HOST = "https://auth.openai.com"
DEVICE_CODE_URL = f"{_AUTH_HOST}/api/accounts/deviceauth/usercode"
DEVICE_TOKEN_URL = f"{_AUTH_HOST}/api/accounts/deviceauth/token"
REFRESH_URL = f"{_AUTH_HOST}/oauth/token"
VERIFICATION_URL = f"{_AUTH_HOST}/codex/device"

# id_token claim namespace carrying the ChatGPT account id / plan.
AUTH_CLAIM_NS = "https://api.openai.com/auth"

PENDING_CACHE_KEY = "nakhoda:chatgpt_device_login"
PENDING_TTL = 900  # device codes expire well inside 15 minutes
REFRESH_SKEW = 120  # refresh this many seconds before nominal expiry

# What the token endpoint's `error.code` means while nobody has finished
# approving or rejecting the device code yet, or after the window closes.
_ERROR_STATUS = {
	"deviceauth_authorization_pending": "pending",
	"deviceauth_expired": "expired",
	"expired_token": "expired",
	"deviceauth_denied": "denied",
	"access_denied": "denied",
}


def _guard() -> None:
	"""Only someone who may edit the settings may move the credential."""
	frappe.has_permission(DOCTYPE, "write", throw=True)


def _device_request(url: str, payload: dict[str, Any]) -> tuple[int, dict[str, Any], str]:
	"""Fire one JSON POST at a device-flow endpoint. Returns
	`(http_status, parsed_body, transport_error)` so start/poll/refresh all
	branch on the same three-way shape instead of each re-wrapping
	`requests.RequestException` and a possibly non-JSON body on their own."""
	try:
		response = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=30)
	except requests.RequestException as exc:
		return 0, {}, str(exc)
	try:
		return response.status_code, response.json(), ""
	except ValueError:
		return response.status_code, {}, ""


def _claims_from_id_token(id_token: str) -> dict[str, Any]:
	"""Best-effort JWT payload read - no signature check needed, this is our
	own freshly minted token from a POST we just made over TLS, not a bearer
	credential arriving from someone else."""
	if not id_token or id_token.count(".") != 2:
		return {}
	_header, body, _signature = id_token.split(".")
	body += "=" * (-len(body) % 4)
	try:
		return json.loads(base64.urlsafe_b64decode(body))
	except (ValueError, TypeError):
		return {}


def _persist(tokens: dict[str, Any]) -> dict[str, str]:
	"""Store a freshly minted credential on Nakhoda Settings and report the
	identity it belongs to."""
	access_token = tokens.get("access_token") or ""
	if not access_token:
		frappe.throw(_("OpenAI returned no access token."))

	claims = _claims_from_id_token(tokens.get("id_token") or "")
	chatgpt_claims = claims.get(AUTH_CLAIM_NS) or {}
	account_id = chatgpt_claims.get("chatgpt_account_id") or ""
	plan = chatgpt_claims.get("chatgpt_plan_type") or ""
	email = claims.get("email") or ""
	label = " \u00b7 ".join(part for part in (email, plan) if part) or _("Connected")
	expires_at = int(time.time()) + int(tokens.get("expires_in") or 3600)

	updates = {
		"chatgpt_oauth_access_token": access_token,
		"chatgpt_oauth_refresh_token": tokens.get("refresh_token") or "",
		"chatgpt_oauth_account_id": account_id,
		"chatgpt_oauth_account_label": label,
		"chatgpt_oauth_expires_at": expires_at,
		# Connecting is the intent to use it - otherwise the credential sits
		# stored but ignored while the client stays on the API key.
		"openai_auth_mode": "ChatGPT Subscription",
	}
	for fieldname, value in updates.items():
		if fieldname == "chatgpt_oauth_refresh_token" and not value:
			continue
		frappe.db.set_single_value(DOCTYPE, fieldname, value)
	frappe.db.commit()  # nosemgrep - land the newly minted credential now, not at request end
	return {"account_id": account_id, "account_label": label}


@frappe.whitelist()
def start_chatgpt_login() -> dict[str, Any]:
	"""Ask OpenAI for a device code and hand the operator something to type
	in at the verification URL."""
	_guard()
	status_code, body, network_error = _device_request(
		DEVICE_CODE_URL, {"client_id": CLIENT_ID, "scope": SCOPE}
	)
	if network_error:
		return {"success": False, "error": _("Could not reach OpenAI: {0}").format(network_error[:200])}
	if status_code != 200:
		return {"success": False, "error": f"OpenAI rejected the request (HTTP {status_code})."}

	device_auth_id = body.get("device_auth_id")
	user_code = body.get("user_code")
	if not device_auth_id or not user_code:
		return {"success": False, "error": _("The device-code response was missing required fields.")}

	frappe.cache().set_value(
		PENDING_CACHE_KEY,
		{"device_auth_id": device_auth_id, "user_code": user_code},
		expires_in_sec=PENDING_TTL,
	)
	return {
		"success": True,
		"user_code": user_code,
		"verification_url": VERIFICATION_URL,
		"interval": int(body.get("interval") or 5),
		"expires_at": body.get("expires_at"),
	}


@frappe.whitelist()
def poll_chatgpt_login() -> dict[str, Any]:
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

	token_payload = {
		"client_id": CLIENT_ID,
		"device_auth_id": pending["device_auth_id"],
		"user_code": pending["user_code"],
	}
	status_code, body, network_error = _device_request(DEVICE_TOKEN_URL, token_payload)
	if network_error:
		return {"success": False, "status": "error", "error": network_error[:200]}

	if status_code == 200:
		account = _persist(body)
		frappe.cache().delete_value(PENDING_CACHE_KEY)
		return {"success": True, "status": "connected", "account": account}

	oauth_code = (body.get("error") or {}).get("code") or ""
	resolved = _ERROR_STATUS.get(oauth_code)
	if resolved == "pending":
		return {"success": False, "status": "pending"}
	if resolved in ("expired", "denied"):
		frappe.cache().delete_value(PENDING_CACHE_KEY)
		message = (
			_("The code expired. Start again.") if resolved == "expired" else _("Authorization was denied.")
		)
		return {"success": False, "status": resolved, "error": message}

	fallback_message = (body.get("error") or {}).get("message") or f"HTTP {status_code}"
	return {"success": False, "status": "error", "error": fallback_message}


@frappe.whitelist()
def disconnect_chatgpt() -> dict[str, Any]:
	"""Forget the stored subscription credential and fall back to the API key."""
	_guard()
	reset_fields = {
		"chatgpt_oauth_access_token": "",
		"chatgpt_oauth_refresh_token": "",
		"chatgpt_oauth_account_id": "",
		"chatgpt_oauth_account_label": "",
		"chatgpt_oauth_expires_at": 0,
		"openai_auth_mode": "API Key",
	}
	for fieldname, value in reset_fields.items():
		frappe.db.set_single_value(DOCTYPE, fieldname, value)
	frappe.db.commit()  # nosemgrep - land the disconnect now, not at request end
	frappe.cache().delete_value(PENDING_CACHE_KEY)
	return {"success": True}


@frappe.whitelist()
def chatgpt_auth_status() -> dict[str, Any]:
	"""Read-only view of the stored credential - the caller learns whether
	one exists and whether it has gone stale, never the token itself."""
	settings = frappe.get_single(DOCTYPE)
	account_id = getattr(settings, "chatgpt_oauth_account_id", "") or ""
	account_label = getattr(settings, "chatgpt_oauth_account_label", "") or ""
	expires_at = int(getattr(settings, "chatgpt_oauth_expires_at", 0) or 0)
	now = int(time.time())
	return {
		"connected": bool(account_id),
		"account_id": account_id,
		"account_label": account_label,
		"expires_at": expires_at,
		"expired": bool(expires_at) and expires_at <= now,
	}


def _refresh(settings) -> str | None:
	"""Trade a stored refresh token for a new access token, shortly before
	the old one goes stale."""
	refresh_token = settings.get_password("chatgpt_oauth_refresh_token", raise_exception=False)
	if not refresh_token:
		return None

	refresh_payload = {
		"client_id": CLIENT_ID,
		"grant_type": "refresh_token",
		"refresh_token": refresh_token,
		"scope": SCOPE,
	}
	status_code, body, network_error = _device_request(REFRESH_URL, refresh_payload)
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
	token = settings.get_password("chatgpt_oauth_access_token", raise_exception=False)
	if not token:
		return None
	expires_at = int(getattr(settings, "chatgpt_oauth_expires_at", 0) or 0)
	about_to_expire = bool(expires_at) and expires_at - REFRESH_SKEW <= int(time.time())
	return (_refresh(settings) or token) if about_to_expire else token
