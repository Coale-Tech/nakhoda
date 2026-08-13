# Copyright (c) 2026, Nakhoda and contributors
# For license information, please see license.txt
"""One call, one model. Everything about *degrading* across models and tiers
is the manager's job (`agent/manager.py`); this module only knows how to make
one request and how to tell a rate limit apart from any other failure, because
that distinction is the one thing the manager cannot infer from an exception
class it has never seen.

`nakhoda.bench.models.openai_compatible()` already does this for the benchmark
harness. This is a separate, `NAKHODA_AGENT_*`-namespaced client rather than a
shared one, because the two callers must not be able to affect each other:
grading a change to the prompt should never compete with a live user for the
same rate limit, and a live outage should never make a CI run flaky.
"""

from __future__ import annotations

import os


class ModelError(Exception):
	"""This model failed. The manager's answer is "try the next one"."""


class RateLimited(ModelError):
	"""This model is out of quota right now. Counted toward the manager's
	three-consecutive-rate-limits circuit breaker (`12-build-plan.md` Phase 4,
	point 3)."""


def _client():
	from openai import OpenAI

	return OpenAI(
		api_key=os.environ["NAKHODA_AGENT_API_KEY"],
		base_url=os.environ.get("NAKHODA_AGENT_BASE_URL") or None,
	)


def complete(prompt: str, model: str) -> str:
	"""Call one model with one prompt at temperature 0 - SQL generation wants
	the deterministic sampler, never the bot's own default (`13-agent-design.md`
	§1, the Raven `ModelSettings` finding this corrects).

	Raises `RateLimited` or `ModelError`; never returns an empty string to mean
	failure, because an empty completion is itself meaningful (`bench.driver.extract`
	reports it as "empty completion" rather than a parse error).
	"""
	import openai

	client = _client()
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
