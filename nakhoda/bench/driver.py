# Copyright (c) 2026, Nakhoda and contributors
# For license information, please see license.txt
"""Stage 1: turn questions into prompts. Stage 2's input, and the only place
that decides what a model is asked.

Two generation targets, because the benchmark and the product disagree about
what is being generated. `10-eval-methodology.md` §6 measured **SQL**; the
product's first non-negotiable is that the agent emits **Operation JSON, never
raw SQL**, so the number that was measured describes a path the product has
rejected (§9). Both targets run here against the same questions, same context
and same gold data, so the delta between them is the price of inspectability -
measured once rather than assumed either way.

The Operation JSON prompt is generated from the engine, not written beside it:
the operation list comes from `OPERATIONS` and the function table from
`FUNCTIONS`, with arity and doc strings as the registry states them. A function
added to the engine appears in the prompt on the next run, and a prompt that
describes a grammar the engine does not implement is not expressible.

There are no worked examples in either prompt. A example resembling the gold
answer is the cheapest way to flatter a benchmark, and with 40 questions over
one module the resemblance is hard to avoid; the grammar is specified instead.
That makes this a harder test than a few-shot product prompt would face, which
is the right direction for the bias to point.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

#: Model tiers, named as `semantic_bench/generated.json` names them.
TIERS = ("smol", "default", "slow")

#: What the model is asked to emit.
TARGETS = ("sql", "ops")

#: Context arms. A is the DDL a warehouse sees; B is the semantic layer.
ARMS = ("A_raw", "B_semantic")

_FENCE = re.compile(r"```[a-zA-Z]*\n(.*?)```", re.S)


def _fenced(text: str) -> str:
	"""The contents of the first fenced block, or the whole text."""
	m = _FENCE.search(text)
	return m.group(1) if m else text


def grammar() -> str:
	"""The operation grammar, rendered from the engine that implements it."""
	from nakhoda.engine.expression import FUNCTIONS
	from nakhoda.engine.operations import JOIN_TYPES, OPERATIONS

	shapes = {
		"source": '{"type": "source", "table": TABLE}',
		"join": (
			'{"type": "join", "table": TABLE, "left_on": EXPR, "right_on": EXPR,\n'
			'    "how": ' + " | ".join(json.dumps(j) for j in JOIN_TYPES) + ",\n"
			'    "select": [{"name": NAME, "expr": EXPR}, ...]}'
		),
		"filter": '{"type": "filter", "where": EXPR}',
		"select": '{"type": "select", "columns": [{"name": NAME, "expr": EXPR}, ...]}',
		"summarize": (
			'{"type": "summarize", "by": [{"name": NAME, "expr": EXPR}, ...],\n'
			'    "measures": [{"name": NAME, "expr": EXPR}, ...]}'
		),
		"order_by": '{"type": "order_by", "keys": [{"expr": EXPR, "desc": true | false}, ...]}',
		"limit": '{"type": "limit", "n": POSITIVE INTEGER}',
	}
	missing = set(OPERATIONS) - set(shapes)
	if missing:  # the engine grew an operation and this prompt does not describe it
		raise RuntimeError(f"grammar() does not describe {sorted(missing)}")

	lines = [
		"A pipeline is a JSON array of operations, applied in order. The first",
		"must be `source`. Each operation reads the table the previous one produced.",
		"",
		"OPERATIONS",
	]
	lines += [f"  {shapes[name]}" for name in OPERATIONS]
	lines += [
		"",
		"EXPR is one of:",
		'  {"col": COLUMN}                 a column in scope',
		'  {"lit": VALUE}                  a string, number, boolean or null',
		'  {"fn": NAME, "args": [EXPR, ...]}',
		"",
		"FUNCTIONS",
	]
	for name in sorted(FUNCTIONS):
		fn = FUNCTIONS[name]
		hi = "n" if fn.max_args is None else fn.max_args
		arity = f"{fn.min_args}" if fn.min_args == hi else f"{fn.min_args}-{hi}"
		lines.append(f"  {name:<15} {fn.kind:<10} args {arity:<4} {fn.doc}")
	lines += [
		"",
		"RULES",
		"  `select` cannot aggregate; use `summarize`.",
		"  Every `summarize` measure must aggregate; every `by` key must not.",
		"  `filter` takes a condition, and cannot filter on an aggregate: to filter",
		"    an aggregated result, summarize first and filter the result.",
		"  After `summarize`, only its `by` keys and `measures` are in scope.",
		"  `join` brings in only the columns it names in `select`, under those names.",
		"    Those names must not already be in scope: namespaces are not merged and",
		"    nothing is auto-suffixed, so a joined `docstatus` beside an existing one",
		"    is an error. Name it `invoice_docstatus` or similar.",
		"  Column names are the physical names in the schema above.",
	]
	return "\n".join(lines)


def prompt(context: str, question: str, target: str) -> str:
	"""What the model sees. The only difference between targets is the ask."""
	if target == "sql":
		ask = "Write one DuckDB SQL query that answers the question.\nReply with the query and nothing else."
		spec = ""
	elif target == "ops":
		ask = (
			"Answer the question with a pipeline in the operation grammar above.\n"
			"Reply with the JSON array and nothing else."
		)
		spec = grammar() + "\n\n"
	else:
		raise ValueError(f"unknown target {target!r}")

	return f"{context}\n\n{spec}Question: {question}\n\n{ask}\n"


def sha(text: str) -> str:
	return hashlib.sha256(text.encode()).hexdigest()[:16]


def plan(
	questions: list[dict],
	contexts: dict[str, str],
	*,
	targets: tuple[str, ...] = TARGETS,
	tiers: tuple[str, ...] = TIERS,
) -> list[dict]:
	"""Every call the run will make, as data.

	`contexts` maps arm name to context text, so an arm is added by supplying
	one rather than by editing this function.
	"""
	rows = []
	for q in questions:
		for arm, context in contexts.items():
			for target in targets:
				text = prompt(context, q["q"], target)
				for tier in tiers:
					rows.append(
						{
							"qid": q["id"],
							"arm": arm,
							"target": target,
							"tier": tier,
							"prompt_sha": sha(text),
							"prompt": text,
						}
					)
	return rows


def extract(text: str, target: str) -> tuple[Any, str | None]:
	"""The artifact inside a completion, or why there is none.

	Models wrap answers in prose and fences whatever the instruction says, and
	an extraction failure scored as a wrong answer would blame the model for the
	harness. Failures are recorded as their own status instead.
	"""
	body = _fenced(text).strip()
	if not body:
		return None, "empty completion"

	if target == "sql":
		return body.rstrip().rstrip(";"), None

	start, end = body.find("["), body.rfind("]")
	if start < 0 or end < start:
		return None, "no JSON array in completion"
	try:
		ops = json.loads(body[start : end + 1])
	except json.JSONDecodeError as e:
		return None, f"invalid JSON: {e.msg}"
	if not isinstance(ops, list):
		return None, "JSON is not an array"
	return ops, None


def write_jsonl(path: Path, rows: list[dict]) -> None:
	path.write_text("".join(json.dumps(r) + "\n" for r in rows))


def read_jsonl(path: Path) -> list[dict]:
	return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
