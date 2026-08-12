# Copyright (c) 2026, Nakhoda and contributors
# For license information, please see license.txt
"""The three stages as commands.

    python -m nakhoda.bench plan  --run DIR [--targets sql,ops] [--arms B_semantic]
    python -m nakhoda.bench run   --run DIR --models openai|replay [--from FILE]
    python -m nakhoda.bench grade --run DIR

`run` is the only command that needs a model and the only one that costs
anything; `plan` and `grade` need the app and the DuckDB fixture. Splitting them
is what lets generation happen in a different interpreter, a different machine,
or - as it did for the first measurements - a harness that is not this one.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from nakhoda.bench import driver
from nakhoda.bench import grade as grading

#: The published run and the Phase 2b run, each with everything that must agree
#: with it. They are named rather than assembled from flags because a question
#: set, its contexts and its database are one object: grading `full` questions
#: against the `frozen` fixture is not a configuration, it is a mistake.
#:
#: `frozen` reads its contexts from disk instead of generating them. It is the
#: 40 questions behind the published 95.8% and it is replayed, never rebuilt -
#: regenerating a context that a committed baseline was produced against would
#: silently retire the baseline.
FROZEN_DIR = Path(__file__).resolve().parent.parent / "tests" / "semantic_bench"
CONTEXT_FILES = {"A_raw": "context_a.txt", "B_semantic": "context_b.txt"}
FIXTURES = {"frozen": Path("/tmp/semantic-bench"), "full": Path("/tmp/nakhoda-fixture")}
REBUILD = {
	"frozen": "python -m nakhoda.tests.semantic_bench.build",
	"full": "python -m nakhoda.bench.fixture",
}


def _questions(which: str) -> list[dict]:
	if which == "frozen":
		from nakhoda.tests.semantic_bench.questions import Q

		return Q
	from nakhoda.bench.questions import Q

	return Q


def _contexts(which: str, arms: tuple[str, ...]) -> dict[str, str]:
	if which == "frozen":
		return {arm: (FROZEN_DIR / CONTEXT_FILES[arm]).read_text() for arm in arms}
	from nakhoda.bench import fixture

	return {arm: text for arm, text in fixture.contexts().items() if arm in arms}


def _ordered(which: str) -> frozenset[str]:
	if which == "frozen":
		return grading.ORDERED
	return frozenset(q["id"] for q in _questions(which) if q.get("ordered"))


def _csv(value: str) -> tuple[str, ...]:
	return tuple(v.strip() for v in value.split(",") if v.strip())


def cmd_plan(args) -> int:
	run = Path(args.run)
	run.mkdir(parents=True, exist_ok=True)
	contexts = _contexts(args.set, args.arms)
	rows = driver.plan(_questions(args.set), contexts, targets=args.targets, tiers=args.tiers)
	driver.write_jsonl(run / "prompts.jsonl", rows)
	print(f"{len(rows)} prompts -> {run / 'prompts.jsonl'}")
	print(f"  set {args.set}  arms {list(contexts)}  targets {list(args.targets)}  tiers {list(args.tiers)}")
	return 0


def cmd_run(args) -> int:
	from nakhoda.bench import models

	run = Path(args.run)
	prompts = driver.read_jsonl(run / "prompts.jsonl")
	if args.models == "replay":
		source = Path(args.source or run / "completions.jsonl")
		generate = models.replay(source)
	else:
		generate = models.openai_compatible()

	rows = models.run(prompts, generate, workers=args.workers)
	driver.write_jsonl(run / "completions.jsonl", rows)
	failed = sum(1 for r in rows if r["err"])
	print(f"{len(rows)} completions -> {run / 'completions.jsonl'} ({failed} without an artifact)")
	return 0


def cmd_grade(args) -> int:
	import duckdb
	import ibis

	run = Path(args.run)
	fixture = Path(args.fixture or FIXTURES[args.set]) / "erp.duckdb"
	if not fixture.exists():
		sys.exit(f"no fixture at {fixture}: run {REBUILD[args.set]}")

	records = driver.read_jsonl(run / "completions.jsonl")
	con = duckdb.connect(str(fixture), read_only=True)
	ibis_con = ibis.duckdb.connect(str(fixture), read_only=True)
	gold = {q["id"]: con.execute(q["sql"]).df() for q in _questions(args.set)}

	graded = grading.grade(records, gold, con, ibis_con.table, ordered_ids=_ordered(args.set))
	(run / "graded.json").write_text(json.dumps(graded, indent=1))
	report(graded)
	return 0


def report(graded: list[dict]) -> None:
	"""Accuracy per cell, then the comparison each pair of cells supports."""
	sel = lambda **kw: [r for r in graded if all(r[k] == v for k, v in kw.items())]  # noqa: E731
	arms = sorted({r["arm"] for r in graded})
	targets = sorted({r["target"] for r in graded})
	tiers = [t for t in driver.TIERS if any(r["tier"] == t for r in graded)]

	for arm in arms:
		for target in targets:
			cells = sel(arm=arm, target=target)
			if not cells:
				continue
			print(f"\n=== {arm} / {target} ===")
			for tier in tiers:
				rows = sel(arm=arm, target=target, tier=tier)
				if not rows:
					print(f"  {tier:<10} {'-':>3}      not run")
					continue
				k = sum(r["status"] == "pass" for r in rows)
				print(f"  {tier:<10} {k:>3}/{len(rows):<4} {100 * k / len(rows):5.1f}%")
			k = sum(r["status"] == "pass" for r in cells)
			lo, hi = grading.wilson(k, len(cells))
			print(
				f"  {'all':<10} {k:>3}/{len(cells):<4} {100 * k / len(cells):5.1f}%"
				f"   95% CI [{100 * lo:.1f}, {100 * hi:.1f}]"
			)
			by_status: dict[str, int] = {}
			for r in cells:
				if r["status"] != "pass":
					by_status[r["status"]] = by_status.get(r["status"], 0) + 1
			if by_status:
				print("  failures: " + ", ".join(f"{k} {v}" for k, v in sorted(by_status.items())))

	pairs = [(a, b) for a in arms for b in arms if a < b]
	for arm in arms:
		if len(targets) == 2:
			pairs.append((arm, arm))
	for left_arm, right_arm in pairs:
		if left_arm == right_arm:
			left, right = sel(arm=left_arm, target=targets[0]), sel(arm=left_arm, target=targets[1])
			label = f"{left_arm}: {targets[0]} vs {targets[1]}"
		else:
			left, right = sel(arm=left_arm, target=targets[0]), sel(arm=right_arm, target=targets[0])
			label = f"{targets[0]}: {left_arm} vs {right_arm}"
		if not left or not right:
			continue
		b, c, n = grading.paired(left, right)
		lk, rk = (sum(r["status"] == "pass" for r in x) for x in (left, right))
		print(f"\n=== {label} ===")
		if not n:
			print(f"  {lk}/{len(left)} vs {rk}/{len(right)}   no shared questions: not paired")
			continue
		print(
			f"  {lk}/{len(left)} vs {rk}/{len(right)}   {n} pairs, discordant {b}/{c}"
			f"   McNemar exact p = {grading.mcnemar_exact(b, c):.3g}"
		)


def main(argv: list[str] | None = None) -> int:
	parser = argparse.ArgumentParser(prog="nakhoda.bench")
	parser.add_argument("--run", default="/tmp/nakhoda-bench", help="run directory")
	parser.add_argument("--set", choices=tuple(FIXTURES), default="frozen", help="question set")
	sub = parser.add_subparsers(dest="cmd", required=True)

	p = sub.add_parser("plan")
	p.add_argument("--arms", type=_csv, default=("B_semantic",))
	p.add_argument("--targets", type=_csv, default=driver.TARGETS)
	p.add_argument("--tiers", type=_csv, default=driver.TIERS)
	p.set_defaults(fn=cmd_plan)

	p = sub.add_parser("run")
	p.add_argument("--models", choices=("openai", "replay"), default="openai")
	p.add_argument("--source", help="completions to replay from")
	p.add_argument("--workers", type=int, default=8)
	p.set_defaults(fn=cmd_run)

	p = sub.add_parser("grade")
	p.add_argument("--fixture", help="database to grade against; defaults to the set's")
	p.set_defaults(fn=cmd_grade)

	args = parser.parse_args(argv)
	return args.fn(args)


if __name__ == "__main__":
	raise SystemExit(main())
