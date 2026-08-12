"""Invariant 11 - no copyleft line enters the tree, and CI proves it.

AGPL -> AGPL copying is *legal*. That is exactly why this has to be mechanical
rather than assumed: the rule protects two things the licence does not.

1. Dual-licensing optionality. Copied lines are someone else's copyright, cannot be
   relicensed by us, and kill the revenue model silently - no error, no warning.
2. The build plan's refusals. The files most worth copying are the ones carrying the
   surface Nakhoda exists to reject: Insights' `ibis_utils.py` brings the
   `code`/`sql`/`custom_operation` operations, `functions.py` brings the 90-function
   expression language. Copying is how a closed grammar reopens by accident.

Method, measured on this workstation 2026-08-12:

    Strip comments, collapse whitespace, drop lines <= 12 chars, drop import/from
    lines and any line with no operator or keyword. Cut what remains into
    overlapping 8-line windows, hash each with blake2b-64, and fail the build on
    any collision between nakhoda/ and the union of the copyleft trees.

Every filter is load-bearing. Without the import-block and bare-identifier filters,
two files importing the same `frappe.utils` date helpers alphabetically collide -
the one false positive the first draft produced.

Validated both ways on this workstation, 2026-08-11:

    detection      6,333 windows (13.2%) of the jkm Insights fork matched upstream,
                   attributed to the file and line they came from
    false positives  0 across 7,656 windows of MIT frappe/utils

The build plan measured 2,295 windows / 8.8% over `.py`/`.ts`/`.js`. Adding `.vue`
raises detection to 13.2% at no false-positive cost, and it closes the larger hole:
Insights is 30,213 lines of frontend against 13,870 of backend, so a Python-only
gate leaves the two-thirds of the tree most worth copying unguarded.

Run it:

    python -m nakhoda.tests.clean_room                 # the gate
    python -m nakhoda.tests.clean_room --stats         # corpus only, no verdict
    python -m nakhoda.tests.clean_room --audit PATH    # point it at any tree
    NAKHODA_COPYLEFT_ROOTS=/a:/b python -m nakhoda.tests.clean_room
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

SHINGLE = 8
MIN_LINE = 12
EXTS = {".py", ".ts", ".js", ".vue"}
PRUNE = {
	".git",
	"__pycache__",
	"node_modules",
	"dist",
	"build",
	".venv",
	"env",
	"sites",
	"assets",
	".yarn",
	"locale",
}

# A line survives only if it has an operator or opens a block. Bare identifiers,
# lone decorators and closing brackets carry no authorship and collide freely.
STMT = re.compile(r"[=(){}\[\]]|^(?:return|if|for|while|with|raise|yield|await|def|class)\b")
IMPORT = re.compile(r"^(?:import|from|export|require)\b")
# Drop comments while preserving quoted strings that happen to contain # or //.
COMMENT = re.compile(r"""("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')|#.*|//.*""")
BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)

CACHE = Path(os.environ.get("NAKHODA_CACHE", Path.home() / ".cache" / "nakhoda"))


def normalise(text: str) -> list[str]:
	"""Source text -> the lines that carry authorship."""
	out = []
	for raw in BLOCK_COMMENT.sub(" ", text).split("\n"):
		line = re.sub(r"\s+", " ", COMMENT.sub(lambda m: m.group(1) or "", raw)).strip()
		if len(line) <= MIN_LINE or IMPORT.match(line) or not STMT.search(line):
			continue
		out.append(line)
	return out


def shingle_file(path: Path) -> dict[str, int]:
	"""blake2b-64 of every 8-line window -> the line number it starts at."""
	try:
		lines = normalise(path.read_text(encoding="utf-8", errors="ignore"))
	except OSError:
		return {}
	out = {}
	for i in range(len(lines) - SHINGLE + 1):
		window = "\n".join(lines[i : i + SHINGLE]).encode()
		out.setdefault(hashlib.blake2b(window, digest_size=8).hexdigest(), i + 1)
	return out


def walk(root: Path):
	for path in root.rglob("*"):
		if path.suffix in EXTS and path.is_file() and not PRUNE & set(path.parts):
			yield path


def tree_key(root: Path) -> str:
	"""Content identity for a tree.

	A clean git checkout answers this in microseconds and answers it exactly, which
	matters because a workstation accumulates a dozen checkouts of the same app: keyed
	by commit, the duplicates collapse into one cache entry instead of one walk each.
	Anything dirty or unversioned falls back to walking for file count and newest mtime.
	"""
	git = subprocess.run(
		["git", "-C", str(root), "status", "--porcelain=v1", "-uno", "--no-renames"],
		capture_output=True,
		text=True,
	)
	if git.returncode == 0 and not git.stdout.strip():
		head = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True)
		if head.returncode == 0:
			return f"git:{head.stdout.strip()}"

	newest, count = 0.0, 0
	for path in walk(root):
		count += 1
		newest = max(newest, path.stat().st_mtime)
	return f"walk:{root}|{count}|{newest:.0f}"


def corpus_shingles(roots: list[Path], use_cache: bool = True) -> dict[str, tuple[str, int]]:
	"""Union of every copyleft window -> (file, line). Cached per distinct tree."""
	CACHE.mkdir(parents=True, exist_ok=True)
	merged: dict[str, tuple[str, int]] = {}
	seen: set[str] = set()
	for root in roots:
		key = hashlib.blake2b(tree_key(root).encode(), digest_size=8).hexdigest()
		if key in seen:
			continue
		seen.add(key)
		cached = CACHE / f"corpus-{key}.json"
		if use_cache and cached.exists():
			merged.update({h: tuple(v) for h, v in json.loads(cached.read_text()).items()})
			continue
		tree: dict[str, tuple[str, int]] = {}
		for path in walk(root):
			rel = str(path.relative_to(root.parent))
			for h, line in shingle_file(path).items():
				tree.setdefault(h, (rel, line))
		cached.write_text(json.dumps(tree))
		merged.update(tree)
	return merged


def discover_roots() -> list[Path]:
	"""Copyleft trees to guard against.

	Override with NAKHODA_COPYLEFT_ROOTS (colon-separated). The default is every
	Insights checkout on the machine, in this bench and its siblings: Insights is
	the tree whose lines carry the surface we refuse, and the only one where an
	idiom match is genuinely suspicious. ERPNext and HRMS are GPL too but are
	*meant* to be echoed - we call the same framework the same way - so folding
	them in would report the convention, not a copy. Add them explicitly if you
	want the stricter run; the gate reports whatever corpus it used.
	"""
	if env := os.environ.get("NAKHODA_COPYLEFT_ROOTS"):
		return [Path(p) for p in env.split(":") if Path(p).is_dir()]

	app = Path(__file__).resolve().parents[2]
	benches = app.parents[2]
	found = {
		d.resolve() for d in benches.glob("*/apps/insights") if d.is_dir() and d.resolve() != app.resolve()
	}
	return sorted(found)


def check(app_root: Path, roots: list[Path], use_cache: bool = True):
	corpus = corpus_shingles(roots, use_cache)
	hits, windows = [], 0
	for path in walk(app_root):
		if path.resolve() == Path(__file__).resolve():
			continue
		own = shingle_file(path)
		windows += len(own)
		for h, line in own.items():
			if h in corpus:
				src, src_line = corpus[h]
				hits.append((str(path.relative_to(app_root)), line, src, src_line))
	return corpus, sorted(hits), windows


def main(argv: list[str]) -> int:
	app_root = Path(__file__).resolve().parents[2]
	if "--audit" in argv:
		app_root = Path(argv[argv.index("--audit") + 1]).resolve()
	roots = [r for r in discover_roots() if r != app_root]
	if not roots:
		print("clean-room: no copyleft corpus found.", file=sys.stderr)
		print("Set NAKHODA_COPYLEFT_ROOTS to the trees to guard against.", file=sys.stderr)
		return 2

	t0 = time.time()
	corpus, hits, windows = check(app_root, roots, use_cache="--no-cache" not in argv)
	elapsed = time.time() - t0

	print(f"clean-room: {len(corpus):,} windows from {len(roots)} tree(s) in {elapsed:.1f}s")
	print(f"  checked {windows:,} windows in {app_root}")
	for root in roots:
		print(f"  corpus  {root}")

	if "--stats" in argv:
		return 0
	if not hits:
		print(f"  OK      no copied window in {app_root.name}/")
		return 0

	pct = f" — {len(hits) / windows:.1%} of the tree" if windows else ""
	print(f"\n  FAIL    {len(hits)} copied window(s){pct}:\n", file=sys.stderr)
	for rel, line, src, src_line in hits:
		print(f"    {rel}:{line}  <-  {src}:{src_line}", file=sys.stderr)
	print(
		"\n  Read it, copy none of it. Architecture travels; lines do not.\n"
		"  See CONTRIBUTING.md, clean-room section.",
		file=sys.stderr,
	)
	return 1


if __name__ == "__main__":
	raise SystemExit(main(sys.argv[1:]))
