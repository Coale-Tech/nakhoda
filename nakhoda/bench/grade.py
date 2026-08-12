# Copyright (c) 2026, Nakhoda and contributors
# For license information, please see license.txt
"""Stage 3: execution accuracy, and whether a difference between two arms is
real.

The metric is the frozen one. `semantic_bench/grade.py` compares result sets
rather than query text, with three guards - NULL handling, row order, column
shape - and this reimplements those semantics rather than improving on them: a
grader that scores differently cannot be compared against the 115/120 it is
meant to reproduce. `test_bench.py` re-grades the archived generations through
this module and requires every published figure back.

Comparing result sets is also what makes the second generation target free.
`10-eval-methodology.md` §9.2 called this out: a pipeline compiles to SQL and
produces rows, so Operation JSON is graded by the same function against the same
gold data. Only the execution step differs, and it is four lines.
"""

from __future__ import annotations

import datetime as dt
import math
from decimal import Decimal
from typing import Any

#: Questions whose text demands a ranking, copied from `semantic_bench/grade.py`.
#:
#: Not derived from the gold SQL: seventeen of the forty carry an `ORDER BY`, but
#: only these ten *ask* for one - the rest sort for a stable answer. Deriving the
#: set would enforce order on questions that never requested it, scoring stricter
#: than the run this must reproduce. `test_bench.py` checks it against the frozen
#: script so the two cannot drift apart.
ORDERED = frozenset({"q24", "q25", "q29", "q30", "q33", "q34", "q35", "q36", "q37", "q39"})


def scal(v: Any) -> Any:
	"""One cell, normalised so that presentation differences are not failures."""
	if v is None:
		return None
	if isinstance(v, bool):
		return bool(v)
	if isinstance(v, Decimal | float | int):
		f = float(v)
		return None if math.isnan(f) else round(f, 2)
	if isinstance(v, dt.datetime | dt.date):
		return str(v)[:10]
	return str(v)


def _rows(df) -> list[tuple]:
	return [tuple(scal(v) for v in r) for r in df.itertuples(index=False, name=None)]


def match(pred_df, gold_df, ordered: bool) -> tuple[bool, str]:
	"""Every gold column must appear as some predicted column, on the same rows.

	Column *names* are not compared. A model that returns the right numbers
	under its own aliases has answered the question; a harness that failed it
	for naming would be measuring instruction-following.
	"""
	if len(pred_df) != len(gold_df):
		return False, f"{len(pred_df)} rows vs {len(gold_df)} gold"

	p_rows, g_rows = _rows(pred_df), _rows(gold_df)
	if not ordered:
		order = sorted(range(len(p_rows)), key=lambda i: tuple(str(x) for x in p_rows[i]))
		p_rows = [p_rows[i] for i in order]
		g_rows = sorted(g_rows, key=lambda t: tuple(str(x) for x in t))

	p_cols = list(zip(*p_rows, strict=False)) if p_rows else []
	g_cols = list(zip(*g_rows, strict=False)) if g_rows else []

	used: set[int] = set()
	for gi, gcol in enumerate(g_cols):
		hit = next((j for j, pcol in enumerate(p_cols) if j not in used and pcol == gcol), None)
		if hit is None:
			return False, f"gold col {gi} unmatched"
		used.add(hit)
	return True, ""


def execute(record: dict, con, resolve) -> tuple[Any, str | None]:
	"""Run one artifact. SQL goes to the database; a pipeline compiles first."""
	if record["target"] == "sql":
		try:
			return con.execute(record["artifact"]).df(), None
		except Exception as e:
			return None, f"{type(e).__name__}: {str(e)[:90]}"

	from nakhoda.engine.operations import compile_pipeline

	try:
		return compile_pipeline(record["artifact"], resolve).to_pandas(), None
	except Exception as e:
		return None, f"{type(e).__name__}: {str(e)[:90]}"


def grade(records: list[dict], gold: dict, con, resolve) -> list[dict]:
	"""Status per record. `gold` maps question id to its gold dataframe."""
	out = []
	for r in records:
		row = {k: r[k] for k in ("qid", "arm", "target", "tier")}
		gd = gold[r["qid"]]

		if r["artifact"] is None:
			out.append({**row, "status": "no_artifact", "detail": r.get("err") or ""})
			continue

		df, err = execute(r, con, resolve)
		if err:
			out.append({**row, "status": "error", "detail": err})
			continue
		if df.shape[1] < gd.shape[1]:
			out.append({**row, "status": "wrong_shape", "detail": f"{df.shape[1]} cols vs {gd.shape[1]}"})
			continue

		ordered = r["qid"] in ORDERED
		ok, why = match(df, gd, ordered)
		if ok:
			out.append({**row, "status": "pass", "detail": ""})
		elif ordered and match(df, gd, False)[0]:
			out.append({**row, "status": "wrong_order", "detail": ""})
		else:
			out.append({**row, "status": "wrong_values", "detail": why})
	return out


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
	"""Score interval for a proportion. Reported instead of k/n alone because at
	n = 40 the interval is roughly +/- 10 points, which is the finding."""
	if not n:
		return 0.0, 0.0
	p = k / n
	d = 1 + z * z / n
	centre = (p + z * z / (2 * n)) / d
	half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
	return max(0.0, centre - half), min(1.0, centre + half)


def mcnemar_exact(b: int, c: int) -> float:
	"""Two-sided exact test on discordant pairs.

	The design is paired - the same question under two conditions - so the
	unpaired test would throw away the pairing and lose the power that makes
	n = 40 sufficient. Only the discordant pairs carry information.
	"""
	n = b + c
	if not n:
		return 1.0
	lo = min(b, c)
	tail = sum(math.comb(n, i) for i in range(lo + 1)) * (0.5**n)
	return min(1.0, 2 * tail)


def discordant(left: list[dict], right: list[dict]) -> tuple[int, int]:
	"""(left passed and right failed, right passed and left failed), paired on
	question and tier."""

	def index(rows):
		return {(r["qid"], r["tier"]): r["status"] == "pass" for r in rows}

	a, b = index(left), index(right)
	shared = a.keys() & b.keys()
	return (
		sum(1 for k in shared if a[k] and not b[k]),
		sum(1 for k in shared if b[k] and not a[k]),
	)
