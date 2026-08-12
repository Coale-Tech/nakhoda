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

Requires `duckdb`. Verified against `/Users/mac/ERPNext/nvumabaranda/env` (duckdb 1.4.5).

```sh
mkdir -p /tmp/semantic-bench
cp questions.py generated.json grade.py /tmp/semantic-bench/
python build.py     # ~6m40s — writes erp.duckdb + context_{a,b}.txt to /tmp/semantic-bench
cd /tmp/semantic-bench && python grade.py
```

`build.py` reads DocType JSON from hardcoded `ERP` / `FRP` paths at `build.py:11-12`
(`kimcov16` bench) and writes to `BENCH = /tmp/semantic-bench` (`:13`). Edit those three
lines to relocate.

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
3. **No `__main__` guard, no CLI.** Both scripts execute at module top level.
4. **Contamination cuts one way.** Frontier models score 95.0% on *raw* ERPNext DDL because
   they recognise `tabSales Invoice` from pretraining. The measured lift therefore
   **understates** the effect for custom DocTypes, which appear in no training corpus.
