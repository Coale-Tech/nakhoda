# Copyright (c) 2026, Nakhoda and contributors
# For license information, please see license.txt
"""One call, one model. Everything about *degrading* across models and tiers
is the manager's job (`agent/manager.py`); this module only knows how to make
one request, which endpoint and credential that request uses, and how to tell
a rate limit apart from any other failure - the one distinction the manager
cannot infer from an exception class it has never seen.

`nakhoda.bench.models.openai_compatible()` already does this for the benchmark
harness. This is a separate client rather than a shared one, because the two
callers must not be able to affect each other: grading a change to the prompt
should never compete with a live user for the same rate limit, and a live
outage should never make a CI run flaky.

Provider resolution is a port of Insights' `insights/ai/*_client.py` family
(verified on this bench), collapsed into one table. Insights spends a class
per provider because each one carries its own quota accounting, prompt
assembly and chat cascade; here all three live elsewhere (`agent/quota.py`,
`bench/driver.py`, `agent/manager.py`), so what is actually provider-specific
is a base URL, a credential field, an env var and a model - i.e. a row in
`PROVIDERS`, not a subclass.

Two providers are two services under one name, and the auth mode picks which:

- `openai` + "ChatGPT Subscription" bills a Plus/Pro account instead of a
  metered key. That traffic must go to the ChatGPT backend, which speaks the
  Responses API over SSE and rejects `chat/completions` outright - hence
  `_codex_complete` rather than the SDK path (`agent/chatgpt_subscription_auth.py`
  is the login side).
- `moonshot` + "Kimi Subscription" is the Kimi Code plan: a different host,
  different model ids, and an Open Platform key is rejected there with 401
  (`agent/kimi_subscription_auth.py`). It does speak `chat/completions`, so
  only its headers and base URL differ.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from dataclasses import dataclass

#: SSE framing of the Responses API. `data:` is the only field carrying an
#: event; `[DONE]` closes the stream without one.
_SSE_DATA = "data:"
_SSE_DONE = "[DONE]"
#: Events repeating the whole finished message rather than a delta of it.
_TERMINAL_EVENTS = frozenset({"response.completed", "response.done"})
#: Content parts that are answer text. Everything else in an output item is
#: not (reasoning summaries, refusals, tool calls).
_TEXT_PARTS = frozenset({"output_text", "text"})


class ModelError(Exception):
	"""This model failed. The manager's answer is "try the next one"."""


class RateLimited(ModelError):
	"""This model is out of quota right now. Counted toward the manager's
	three-consecutive-rate-limits circuit breaker (`12-build-plan.md` Phase 4,
	point 3)."""


CHATGPT_BACKEND = "https://chatgpt.com/backend-api/codex"

#: Hosts that mean "this machine". A stored `ollama_base_url` of
#: `http://localhost:11434` is the shipped default, which is meaningless for
#: Ollama Cloud - so on the cloud provider a loopback address is ignored in
#: favour of ollama.com rather than silently probing the local daemon.
_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "0.0.0.0", "::1", "[::1]"})

#: GPT-5.x / o-series bill hidden reasoning tokens against the output budget.
_REASONING_PREFIXES = ("gpt-5", "o1", "o3", "o4")
_REASONING_MIN_OUTPUT_TOKENS = 25000


@dataclass(frozen=True)
class Provider:
	"""One endpoint, and the fields on `Nakhoda Settings` that configure it."""

	key: str
	label: str
	#: Where requests go when nothing overrides it.
	base_url: str
	#: `Nakhoda Settings` Password field holding the credential; empty when the
	#: provider needs none (a local Ollama daemon).
	key_field: str
	#: Provider-specific environment variable, checked when the field is blank.
	env_key: str
	#: Model fields, in tier order: FAST first, BALANCED second.
	model_field: str
	default_model: str
	fallback_field: str = ""
	default_fallback: str = ""
	#: Data field overriding `base_url`, when the endpoint is configurable.
	base_url_field: str = ""
	env_base_url: str = ""


PROVIDERS: dict[str, Provider] = {
	"openrouter": Provider(
		key="openrouter",
		label="OpenRouter",
		base_url="https://openrouter.ai/api/v1",
		key_field="openrouter_api_key",
		env_key="OPENROUTER_API_KEY",
		model_field="ai_model",
		default_model="nvidia/nemotron-3-super-120b-a12b:free",
		fallback_field="ai_model_fallback",
		default_fallback="nvidia/nemotron-3-ultra-550b-a55b:free",
	),
	"openai": Provider(
		key="openai",
		label="OpenAI",
		base_url="https://api.openai.com/v1",
		key_field="openai_api_key",
		env_key="OPENAI_API_KEY",
		model_field="openai_model",
		default_model="gpt-5.6-terra",
		base_url_field="openai_base_url",
		env_base_url="OPENAI_BASE_URL",
	),
	"nvidia": Provider(
		key="nvidia",
		label="NVIDIA NIM",
		base_url="https://integrate.api.nvidia.com/v1",
		key_field="nvidia_api_key",
		env_key="NVIDIA_API_KEY",
		model_field="nvidia_model",
		default_model="nvidia/nemotron-3-super-120b-a12b",
	),
	"ollama": Provider(
		key="ollama",
		label="Ollama",
		base_url="http://localhost:11434",
		key_field="",
		env_key="",
		model_field="ollama_model",
		default_model="llama3.1",
		base_url_field="ollama_base_url",
		env_base_url="OLLAMA_BASE_URL",
	),
	"ollama_cloud": Provider(
		key="ollama_cloud",
		label="Ollama Cloud",
		base_url="https://ollama.com",
		key_field="ollama_api_key",
		env_key="OLLAMA_API_KEY",
		model_field="ollama_model",
		default_model="llama3.1",
		base_url_field="ollama_base_url",
		env_base_url="OLLAMA_BASE_URL",
	),
	"moonshot": Provider(
		key="moonshot",
		label="Kimi (Moonshot)",
		base_url="https://api.moonshot.ai/v1",
		key_field="moonshot_api_key",
		env_key="MOONSHOT_API_KEY",
		model_field="moonshot_model",
		default_model="kimi-k3",
		env_base_url="MOONSHOT_BASE_URL",
	),
}

DEFAULT_PROVIDER = "openrouter"


def _settings():
	import frappe

	return frappe.get_single("Nakhoda Settings")


def provider(settings=None) -> Provider:
	"""The selected provider row. Falls back to OpenRouter for an unset or
	unrecognised `ai_provider`, so a hand-edited value degrades to the shipped
	default rather than raising out of every code path that reads settings."""
	settings = settings or _settings()
	return PROVIDERS.get(getattr(settings, "ai_provider", "") or "", PROVIDERS[DEFAULT_PROVIDER])


def enabled(settings=None) -> bool:
	"""The master switch. Off means no model is ever called.

	An *absent* value is not "off": the field defaults to 1
	(`nakhoda_settings.json`), and a Single whose row was written before the
	field existed - or a fresh install nobody has saved settings on - has no
	row for it at all. `setting_enabled` is where that rule lives; the Data
	Store's own switch needs the identical treatment, so the two share it
	rather than keeping a copy each.
	"""
	from nakhoda.nakhoda.doctype.nakhoda_settings.nakhoda_settings import setting_enabled

	return setting_enabled("enable_ai", settings or _settings())


def _is_loopback(url: str) -> bool:
	if not url:
		return True
	host = url.split("//")[-1].split("/")[0].rsplit("@", 1)[-1]
	# Strip the port, keeping bracketed IPv6 literals intact.
	if host.startswith("["):
		host = host.split("]")[0] + "]"
	else:
		host = host.split(":")[0]
	return host.lower() in _LOOPBACK_HOSTS


def _stored_key(settings, fieldname: str) -> str:
	if not fieldname:
		return ""
	return str(settings.get_password(fieldname, raise_exception=False) or "")


def base_url(settings=None, spec: Provider | None = None) -> str:
	"""The endpoint the selected provider is actually called on - what the UI
	shows and what `_client()` uses, resolved the same way in both places.

	`spec` overrides which provider that is, for the settings page's "Test
	Connection" on a provider that is configured but not currently selected."""
	settings = settings or _settings()
	spec = spec or provider(settings)

	if _openai_subscription(settings, spec):
		return CHATGPT_BACKEND
	if _kimi_subscription(settings, spec):
		from nakhoda.agent.kimi_subscription_auth import CODING_BASE_URL

		return CODING_BASE_URL

	configured = str(getattr(settings, spec.base_url_field, "") or "") if spec.base_url_field else ""
	if spec.key == "ollama_cloud" and _is_loopback(configured):
		configured = ""
	url = (
		configured or (os.environ.get(spec.env_base_url) if spec.env_base_url else "") or spec.base_url
	).rstrip("/")
	# Ollama serves an OpenAI-compatible surface under /v1; its own settings
	# field holds the daemon root (`http://localhost:11434`), matching what
	# `/api/tags` model discovery needs.
	if spec.key in ("ollama", "ollama_cloud") and not url.endswith("/v1"):
		url = f"{url}/v1"
	return url


def _openai_subscription(settings, spec: Provider | None = None) -> bool:
	spec = spec or provider(settings)
	return spec.key == "openai" and getattr(settings, "openai_auth_mode", "") == "ChatGPT Subscription"


def _kimi_subscription(settings, spec: Provider | None = None) -> bool:
	spec = spec or provider(settings)
	return spec.key == "moonshot" and getattr(settings, "moonshot_auth_mode", "") == "Kimi Subscription"


def credentials(settings=None, spec: Provider | None = None) -> tuple[str, str]:
	"""API key and base URL for the selected provider.

	DB-first (`Nakhoda Settings`, an admin's change takes effect without a
	redeploy) else the provider's own environment variable else the legacy
	`NAKHODA_AGENT_API_KEY`/`NAKHODA_AGENT_BASE_URL` pair, which ops installs
	predating the per-provider fields still set. Raises `ModelError` rather
	than `KeyError` when nothing is configured, because a missing credential is
	the same "try the next model" signal as any other model failure to
	`_try_tier`'s caller - not a crash.

	In either subscription mode the pair returned is a live OAuth access token
	plus that subscription's own backend; the provider's API Key field is
	ignored while the mode is selected (the auth modules are the only writers
	of those tokens, this function only ever reads them).
	"""
	settings = settings or _settings()
	spec = spec or provider(settings)

	if not enabled(settings):
		raise ModelError("AI is turned off (Nakhoda Settings AI Provider tab).")

	if _openai_subscription(settings, spec):
		from nakhoda.agent.chatgpt_subscription_auth import get_access_token

		token = get_access_token(settings)
		if not token:
			raise ModelError("ChatGPT Subscription selected but not connected (AI Provider settings tab).")
		return str(token), CHATGPT_BACKEND

	if _kimi_subscription(settings, spec):
		from nakhoda.agent.kimi_subscription_auth import get_access_token

		token = get_access_token(settings)
		if not token:
			raise ModelError("Kimi Subscription selected but not connected (AI Provider settings tab).")
		return str(token), base_url(settings, spec)

	url = base_url(settings, spec)
	api_key = (
		_stored_key(settings, spec.key_field)
		or (os.environ.get(spec.env_key) if spec.env_key else "")
		or os.environ.get("NAKHODA_AGENT_API_KEY")
		or ""
	)
	if not api_key:
		if spec.key == "ollama":
			# A local daemon authenticates nobody, but the OpenAI SDK refuses to
			# construct a client without some key - send the placeholder Ollama
			# itself documents rather than failing a working configuration.
			return "ollama", url
		raise ModelError(f"No API key configured for {spec.label} (Nakhoda Settings AI Provider tab).")
	return api_key, url


def configured(settings=None, spec: Provider | None = None) -> bool:
	"""Whether a model call could be made at all - the AI Provider tab's
	"Active" badge, and the skip condition for the live tests."""
	try:
		credentials(settings, spec)
	except Exception:
		return False
	return True


def models(settings=None) -> tuple[str, str]:
	"""`(primary, fallback)` for the selected provider - FAST and BALANCED
	respectively (`agent/tiers.py` maps them onto the ladder). The fallback is
	empty for every provider whose settings offer one model; the Kimi Code
	subscription is the exception, since it serves a fixed pair."""
	settings = settings or _settings()
	spec = provider(settings)

	if _kimi_subscription(settings, spec):
		from nakhoda.agent.kimi_subscription_auth import SUBSCRIPTION_MODELS

		return SUBSCRIPTION_MODELS[0], SUBSCRIPTION_MODELS[-1]

	primary = str(getattr(settings, spec.model_field, "") or "") or spec.default_model
	fallback = ""
	if spec.fallback_field:
		fallback = str(getattr(settings, spec.fallback_field, "") or "") or spec.default_fallback
	return primary, fallback


def subscription_headers(settings=None) -> dict[str, str] | None:
	"""Extra headers a subscription backend requires to key quota off the
	connected account. `None` outside subscription mode, so `_client()` never
	sends these to an ordinary OpenAI-compatible endpoint that would reject the
	unrecognised headers."""
	import uuid

	settings = settings or _settings()
	spec = provider(settings)

	if _openai_subscription(settings, spec):
		# Header contract taken from the Codex client, same as Insights'
		# `openai_client.py`: the backend keys quota off the account id and
		# gates the Responses surface behind a beta flag.
		return {
			"chatgpt-account-id": getattr(settings, "chatgpt_oauth_account_id", "") or "",
			"OpenAI-Beta": "responses=experimental",
			"originator": "nakhoda",
			"session_id": str(uuid.uuid4()),
		}
	if _kimi_subscription(settings, spec):
		# Kimi ties the grant to a stable device id; send back the one the
		# device-login flow registered.
		return {
			"X-Msh-Platform": "kimi_cli",
			"X-Msh-Device-Id": getattr(settings, "kimi_device_id", "") or "",
		}
	return None


def _client(settings=None):
	from openai import OpenAI

	settings = settings or _settings()
	api_key, url = credentials(settings)
	headers = subscription_headers(settings)
	if headers:
		return OpenAI(api_key=api_key, base_url=url, default_headers=headers)
	return OpenAI(api_key=api_key, base_url=url)


def _sse_events(raw: str) -> Iterator[dict]:
	"""Decode the JSON frames of one SSE body.

	Skips what carries no event: comment/keepalive lines, the `[DONE]`
	sentinel, and any frame whose payload is not JSON - a truncated body is a
	short answer here, not an exception, because the caller has no retry that
	could produce the missing bytes.
	"""
	for frame in raw.splitlines():
		if not frame.startswith(_SSE_DATA):
			continue
		payload = frame[len(_SSE_DATA) :].strip()
		if not payload or payload == _SSE_DONE:
			continue
		try:
			yield json.loads(payload)
		except ValueError:
			continue


def _message_text(event: dict) -> str:
	"""The text of one terminal Responses event, joined across every text part
	of every output item. Non-text parts (reasoning summaries, tool calls) are
	not answer text and are dropped."""
	items = (event.get("response") or {}).get("output") or []
	parts = (part for item in items for part in (item.get("content") or []))
	return "".join(str(p.get("text") or "") for p in parts if p.get("type") in _TEXT_PARTS)


def _parse_responses_sse(raw: str) -> str:
	"""The answer text carried by a Responses API SSE body.

	Two encodings of the same answer can arrive in one stream: incremental
	`output_text.delta` events, and a terminal event repeating the whole
	message. Deltas win when there are any - they are what a streaming backend
	sends - and the terminal copy is the fallback for a backend that only ever
	sends the finished message, so neither shape returns empty.
	"""
	deltas: list[str] = []
	finished = ""
	for event in _sse_events(raw):
		kind = event.get("type") or ""
		if kind == "response.output_text.delta":
			deltas.append(str(event.get("delta") or ""))
		elif kind in _TERMINAL_EVENTS:
			finished += _message_text(event)
	return "".join(deltas) or finished


def _codex_complete(prompt: str, model: str, settings) -> str:
	"""One completion against the ChatGPT backend, on behalf of a Plus/Pro
	subscription. `api.openai.com`'s `chat/completions` is not reachable with a
	subscription token, and the backend that is speaks the Responses API over
	SSE - so this path is a hand-rolled request rather than the SDK's.
	"""
	import requests

	token, url = credentials(settings)
	headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
	headers.update(subscription_headers(settings) or {})

	payload: dict[str, object] = {"model": model, "stream": True, "store": False, "input": prompt}
	if str(model or "").startswith(_REASONING_PREFIXES):
		# Reasoning tokens are charged as output; a small cap returns an empty
		# message. Keep effort low - emitting a pipeline is not deep-reasoning
		# work, and `13-agent-design.md` §1 wants the deterministic sampler.
		payload["reasoning"] = {"effort": "low"}
		payload["max_output_tokens"] = _REASONING_MIN_OUTPUT_TOKENS

	try:
		response = requests.post(f"{url}/responses", headers=headers, json=payload, timeout=180)
	except requests.RequestException as exc:
		raise ModelError(str(exc)) from exc

	if response.status_code == 429:
		raise RateLimited("ChatGPT subscription rate limit reached.")
	if response.status_code == 401:
		raise ModelError(
			"ChatGPT subscription token was rejected. Reconnect from the AI Provider settings tab."
		)
	if response.status_code != 200:
		# Surface the upstream body verbatim: this is where a plan-entitlement
		# refusal shows up, and it is not guessable.
		raise ModelError(
			f"ChatGPT backend error (HTTP {response.status_code}): {(response.text or '')[:300]}"
		)

	return _parse_responses_sse(response.text)


def complete(prompt: str, model: str) -> str:
	"""Call one model with one prompt at temperature 0 - SQL generation wants
	the deterministic sampler, never the bot's own default (`13-agent-design.md`
	§1, the Raven `ModelSettings` finding this corrects).

	Raises `RateLimited` or `ModelError`; never returns an empty string to mean
	failure, because an empty completion is itself meaningful (`bench.driver.extract`
	reports it as "empty completion" rather than a parse error).
	"""
	import openai

	settings = _settings()
	if _openai_subscription(settings):
		return _codex_complete(prompt, model, settings)

	client = _client(settings)
	try:
		response = client.chat.completions.create(
			model=model,
			messages=[{"role": "user", "content": prompt}],
			temperature=0,
		)
	except openai.RateLimitError as exc:
		raise RateLimited(str(exc)) from exc
	except openai.APIError as exc:
		raise ModelError(str(exc)) from exc
	return response.choices[0].message.content or ""
