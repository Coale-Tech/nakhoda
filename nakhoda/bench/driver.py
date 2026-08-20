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

#: What the model is asked to emit, for the two targets the benchmark
#: measures (`00-REPORT.md` §6.2's 95.8%/95.0%). A third target,
#: `"ops_annotated"`, exists below for `nakhoda.agent.manager`'s live path
#: only - it asks for the same `ops` array plus an `assumptions` list, is
#: deliberately excluded from this tuple, and has never been benchmarked.
TARGETS = ("sql", "ops")

#: Context arms. A is the DDL a warehouse sees; B is the semantic layer.
ARMS = ("A_raw", "B_semantic")

_FENCE = re.compile(r"```[a-zA-Z]*\n(.*?)```", re.S)


def _fenced(text: str) -> str:
	"""The contents of the first fenced block, or the whole text."""
	m = _FENCE.search(text)
	return m.group(1) if m else text


def grammar() -> str:
	"""The operation grammar, rendered from the engine that implements it.

	`docs/plan/12-build-plan.md` Phase 8 folded ML into the same grammar: an
	agent asks for a forecast, an anomaly flag, a segment or a score the same
	way it asks for a filter or a join - one more operation type, validated
	and compiled by the same engine. `validate_pipeline` is what actually
	restricts an ML step to at most one, and only last; this prompt states
	that restriction, it does not enforce it."""
	from nakhoda.engine.expression import FUNCTIONS
	from nakhoda.engine.operations import (
		ANOMALY_METHODS,
		FORECAST_FREQS,
		FORECAST_METHODS,
		JOIN_TYPES,
		OPERATIONS,
		SCORE_METHODS,
		SEGMENT_METHODS,
	)

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
		"forecast": (
			'{"type": "forecast", "column": NAME, "date_column": COLUMN, "periods": POSITIVE INTEGER,\n'
			'    "method": ' + " | ".join(json.dumps(m) for m in FORECAST_METHODS) + ",\n"
			'    "freq": ' + " | ".join(json.dumps(f) for f in FORECAST_FREQS) + ' (default "D"),\n'
			'    "confidence": NUMBER IN (0, 1) (default 0.95)}'
		),
		"detect_anomalies": (
			'{"type": "detect_anomalies", "column": NAME,\n'
			'    "method": '
			+ " | ".join(json.dumps(m) for m in ANOMALY_METHODS)
			+ ' (default "isolation_forest"),\n'
			'    "contamination": NUMBER IN (0, 0.5] (default 0.05)}'
		),
		"segment": (
			'{"type": "segment", "id_column": COLUMN, "date_column": COLUMN, "value_column": COLUMN,\n'
			'    "method": ' + " | ".join(json.dumps(m) for m in SEGMENT_METHODS) + ' (default "rfm"),\n'
			'    "clusters": INTEGER >= 2 (default 4)}'
		),
		"score": (
			'{"type": "score", "target": COLUMN, "id_column": COLUMN, "feature_columns": [COLUMN, ...],\n'
			'    "method": ' + " | ".join(json.dumps(m) for m in SCORE_METHODS) + ' (default "auto")}'
		),
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
		"  `forecast`, `detect_anomalies`, `segment` and `score` may appear at most",
		"    once, and only as the pipeline's last operation.",
	]
	return "\n".join(lines)


#: A model may state `"applied"` for a choice the semantic model settled
#: unambiguously, or `"needs_you"` for one where another reading was equally
#: plausible. Mirrors `AssumptionRow.vue`'s two states exactly - the frontend
#: never invents a third.
ASSUMPTION_STATES = ("applied", "needs_you")


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
	elif target == "ops_annotated":
		ask = (
			"Answer the question with a pipeline in the operation grammar above.\n"
			'Reply with one JSON object: {"ops": [...], "assumptions": [...]}.\n'
			"\n"
			"`ops` is the JSON array described above.\n"
			"\n"
			"`assumptions` lists every choice you made that the question did not spell\n"
			'out, each {"tag": SHORT_LABEL, "state": "applied" | "needs_you", "text": SENTENCE}.\n'
			'`state` is "applied" when the schema settled the choice unambiguously - name it\n'
			'anyway, do not hide a resolved judgment call - and "needs_you" when another\n'
			'reading was equally plausible and you picked one. For a "needs_you" entry, also\n'
			'include "counterfactual" (one sentence naming what the other reading would have\n'
			'produced), "alt_label" and "keep_label" (short button labels for the two choices).\n'
			"If nothing was ambiguous, `assumptions` may be [].\n"
			"Reply with the JSON object and nothing else."
		)
		spec = grammar() + "\n\n"
	else:
		raise ValueError(f"unknown target {target!r}")

	return f"{context}\n\n{spec}Question: {question}\n\n{ask}\n"


#: How much of a rejected answer the repair prompt echoes. A reply that failed
#: to parse can be any length at all, and the prompt it rides in already carries
#: the whole semantic model - so the echo is bounded rather than trusted.
REPAIR_ECHO = 4000


def repair(text_prompt: str, rejected: str, error: str) -> str:
	"""The same prompt, plus the answer that was refused and the refusal.

	`agent/providers.py:complete` samples at temperature 0 on purpose, so asking
	a model the identical prompt twice cannot produce a different pipeline - the
	only thing that makes a second attempt worth its latency is telling the
	model what was wrong with the first. Every refusal this engine raises names
	the offending node (`engine/operations.py`, `engine/expression.py`), which is
	also why `api.validate` returns a reason instead of raising one: its
	docstring names "a model correcting itself" as the consumer, and this is that
	caller.

	`rejected` is what the model produced, rendered by the caller: the pipeline
	when there was one, else the reply verbatim - a reply that did not parse is
	itself the thing to correct, and a placeholder in its place would ask the
	model to guess what it had said.
	"""
	echo = rejected[:REPAIR_ECHO]
	if len(rejected) > REPAIR_ECHO:
		echo = f"{echo}\n... (truncated)"
	return (
		f"{text_prompt}\n"
		"Your previous answer was rejected.\n"
		"\n"
		f"It was:\n{echo}\n"
		"\n"
		f"The reason:\n{error}\n"
		"\n"
		"Correct exactly that, keeping everything else. The grammar above is closed:\n"
		"if a shape you want is not in it, express the same intent with the shapes\n"
		"that are. Reply with the JSON object and nothing else.\n"
	)


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


def _valid_assumptions(raw: Any) -> list[dict]:
	"""Best-effort validation of the model's `assumptions` list. Malformed
	entries are dropped rather than failing the whole extraction - `ops` is
	the product's non-negotiable artifact (module docstring); a garbled
	explanation of it must never cost a valid pipeline its answer."""
	if not isinstance(raw, list):
		return []
	out = []
	for entry in raw:
		if not isinstance(entry, dict):
			continue
		tag, state, text = entry.get("tag"), entry.get("state"), entry.get("text")
		if not (
			isinstance(tag, str) and tag and state in ASSUMPTION_STATES and isinstance(text, str) and text
		):
			continue
		row = {"tag": tag, "state": state, "text": text}
		if state == "needs_you":
			counterfactual, alt_label, keep_label = (
				entry.get("counterfactual"),
				entry.get("alt_label"),
				entry.get("keep_label"),
			)
			if (
				isinstance(counterfactual, str)
				and counterfactual
				and isinstance(alt_label, str)
				and alt_label
				and isinstance(keep_label, str)
				and keep_label
			):
				row.update(counterfactual=counterfactual, alt_label=alt_label, keep_label=keep_label)
		out.append(row)
	return out


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

	if target == "ops_annotated":
		# The annotated envelope is a JSON object; a model that ignores the
		# extra ask and replies with the bare `ops` array (the shape `target
		# == "ops"` has always accepted) still answers, just with no
		# assumptions - see the module docstring's non-negotiable.
		obrace, obracket = body.find("{"), body.find("[")
		if obrace >= 0 and (obracket < 0 or obrace < obracket):
			cbrace = body.rfind("}")
			if cbrace < obrace:
				return None, "no JSON object in completion"
			try:
				payload = json.loads(body[obrace : cbrace + 1])
			except json.JSONDecodeError as e:
				return None, f"invalid JSON: {e.msg}"
			if not isinstance(payload, dict):
				return None, "JSON is not an object"
			ops = payload.get("ops")
			if not isinstance(ops, list):
				return None, "'ops' is not an array"
			return {"ops": ops, "assumptions": _valid_assumptions(payload.get("assumptions"))}, None
		start, end = obracket, body.rfind("]")
		if start < 0 or end < start:
			return None, "no JSON object or array in completion"
		try:
			ops = json.loads(body[start : end + 1])
		except json.JSONDecodeError as e:
			return None, f"invalid JSON: {e.msg}"
		if not isinstance(ops, list):
			return None, "JSON is not an array"
		return {"ops": ops, "assumptions": []}, None

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
