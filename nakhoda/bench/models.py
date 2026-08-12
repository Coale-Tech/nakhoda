# Copyright (c) 2026, Nakhoda and contributors
# For license information, please see license.txt
"""Stage 2: call a model. The only stage that needs one, and the only stage
that costs money.

A generator is `(prompt, tier) -> text` and nothing else. Two ship here, and the
harness that produced the first measurements supplies a third of its own - which
is the point of the signature being that small. `semantic_bench`'s generation
step was unreproducible because it was welded to the session that ran it.

`replay` is not a convenience. CI has to detect a regression in retrieval, the
semantic layer or the engine without paying for 240 completions per commit, and
those three are exactly what a re-grade of frozen completions still exercises.
It is keyed by prompt hash, so the one thing replay must never do - answer a
question that was never asked - fails loudly instead.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from nakhoda.bench.driver import read_jsonl

#: `(prompt, tier) -> completion text`.
Generate = Callable[[str, str], str]


def replay(path: Path) -> Generate:
	"""Serve recorded completions, matched on the exact prompt."""
	recorded = {(r["prompt_sha"], r["tier"]): r["raw"] for r in read_jsonl(path)}

	def generate(prompt: str, tier: str) -> str:
		from nakhoda.bench.driver import sha

		key = (sha(prompt), tier)
		if key not in recorded:
			raise KeyError(
				f"no recorded completion for tier {tier} and this prompt ({key[0]}). "
				f"The prompt changed; regenerate rather than replaying a stale answer."
			)
		return recorded[key]

	return generate


def openai_compatible() -> Generate:
	"""Any OpenAI-shaped endpoint, configured by environment.

	NAKHODA_BENCH_API_KEY     required
	NAKHODA_BENCH_BASE_URL    optional, for a gateway or a local server
	NAKHODA_BENCH_MODEL_SMOL      the three tier -> model mappings,
	NAKHODA_BENCH_MODEL_DEFAULT   required for whichever tiers are run
	NAKHODA_BENCH_MODEL_SLOW
	"""
	from openai import OpenAI

	client = OpenAI(
		api_key=os.environ["NAKHODA_BENCH_API_KEY"],
		base_url=os.environ.get("NAKHODA_BENCH_BASE_URL") or None,
	)

	def generate(prompt: str, tier: str) -> str:
		var = f"NAKHODA_BENCH_MODEL_{tier.upper()}"
		if var not in os.environ:
			raise KeyError(f"tier {tier!r} needs {var}")
		completion = client.chat.completions.create(
			model=os.environ[var],
			messages=[{"role": "user", "content": prompt}],
			temperature=0,
		)
		return completion.choices[0].message.content or ""

	return generate


def run(prompts: list[dict], generate: Generate, *, workers: int = 8) -> list[dict]:
	"""Every planned call, in parallel. One row out per row in, in input order.

	A model call that raises is recorded as a failed call rather than lost: a
	run that drops rows silently reports accuracy over the subset that happened
	to succeed, which is the failure mode most likely to flatter a result.
	"""
	from nakhoda.bench.driver import extract

	def one(row: dict) -> dict:
		out = {k: row[k] for k in ("qid", "arm", "target", "tier", "prompt_sha")}
		try:
			raw = generate(row["prompt"], row["tier"])
		except Exception as e:
			return {**out, "raw": "", "artifact": None, "err": f"{type(e).__name__}: {e}"}
		artifact, err = extract(raw, row["target"])
		return {**out, "raw": raw, "artifact": artifact, "err": err}

	with ThreadPoolExecutor(max_workers=workers) as pool:
		return list(pool.map(one, prompts))
