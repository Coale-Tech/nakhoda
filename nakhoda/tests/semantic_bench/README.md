# semantic-bench

The paired A/B behind `00-REPORT.md` §0 finding 2 and §6.0: does a semantic layer
mechanically derived from DocType metadata improve NL2SQL over raw DDL?

40 questions x 2 contexts x 3 model tiers = 240 single-shot runs.
**78.3% -> 95.8% (+17.5 pp), McNemar exact p = 1.9e-05.**

## Files

| File | Role |
|---|---|
| `build.py` | Builds `/tmp/semantic-bench/erp.duckdb` from **real** ERPNext DocType JSON, plus the two competing context files. Seeded (`random.seed(7)`) — deterministic |
| `questions.py` | The 40 gold questions + gold SQL, each tagged with a semantic **trap** class |
| `context_a.txt` | Arm A — DDL only, what a warehouse sees after ingestion (14,441 chars) |
| `context_b.txt` | Arm B — the DocType-derived semantic layer (29,717 chars) |
| `generated.json` | The 240 model generations, archived |
| `grade.py` | Execution-accuracy grading with NULL / ordering / column-shape guards |
| `graded.json` | Per-run pass/fail with failure detail |

## Reproducing

Requires `duckdb`, and an **ERPNext v16.29.0** checkout - the DocTypes the contexts
were derived from. That version is a pin, not a detail: ERPNext v15 moves 22 fields
across these eight DocTypes, so a rebuild on another release produces a different
`context_b.txt` and measures the release rather than the layer.

```sh
python -m nakhoda.tests.semantic_bench.build     # ~6m40s -> $SEMANTIC_BENCH_OUT
python -m nakhoda.tests.semantic_bench.grade
```

Both resolve `apps/erpnext` and `apps/frappe` from the bench this app is installed
in, and write to `/tmp/semantic-bench`. Override with `SEMANTIC_BENCH_ERPNEXT`,
`SEMANTIC_BENCH_FRAPPE`, `SEMANTIC_BENCH_OUT`.

Three changes were made when this was vendored, and no others: paths resolved
instead of hardcoded to one workstation, an import guard so that test discovery
cannot trigger a six-minute destructive rebuild, and `grade.py` reading
`questions.py` from beside itself. The scripts are excluded from `ruff` - their
value is that they reproduce byte-identical, which reformatting would trade away.

**Audited 2026-08-12.** Fixture rebuilt from scratch: `context_a.txt` and `context_b.txt`
came out md5-identical to the committed copies, and re-grading `generated.json` against the
fresh database reproduced every published figure exactly — combined 78.3% -> 95.8%, all
three per-model rows, all eight trap rows, and the failure-mode split (A_raw 94 pass /
26 wrong_values; B_semantic 115 pass / 1 error / 4 wrong_values).

## Known gaps

1. **The generation step is not on disk.** `generated.json` is archived output; the driver
   that called the models was never written to a file. You can re-grade, you cannot
   re-generate. Any productisation (`12-build-plan.md` Phase 2) has to write that driver.
2. **40 questions, not the >=200 the literature recommends** (`10-eval-methodology.md` §4).
   The headline delta clears significance anyway; the per-trap cells (n = 2-8) are
   indicative only.
3. **One phantom column in Arm B.** `context_b.txt` lists `image_view VARCHAR` on
   Sales Invoice Item. It is an `Image` field - a widget that re-renders another
   column - and has no column of its own; the harness' own Arm A DDL omits it.
   The 95.8% was therefore scored against a schema advertising one column that did
   not exist. `nakhoda/semantic/model.py` filters on Frappe's `data_fieldtypes`
   allow-list and drops it, which is the single line by which the shipped generator
   differs from this artifact - asserted in `test_semantic.py`, not tolerated.
4. **Scripts, not modules.** Both run at import, so both now refuse to be imported.
   Neither has a CLI beyond the env vars above.
5. **Contamination cuts one way.** Frontier models score 95.0% on *raw* ERPNext DDL because
   they recognise `tabSales Invoice` from pretraining. The measured lift therefore
   **understates** the effect for custom DocTypes, which appear in no training corpus.
