# NL2SQL evaluation methodology

Methodology dossier · 2026-08-11
· Source: `SemanticLayerEvalScout` (50+ arXiv papers, 2018–2026), **spot-verified by
Main where cited in `00-REPORT.md`**

> **Provenance warning.** The scout reported these findings but did **not** write this
> file despite claiming to; this file was reconstructed by Main from its returned
> summary. Rows marked **[VERIFIED]** were checked by Main directly against the arXiv
> API. Everything else is **scout-reported and unverified** — treat as a reading list,
> not as evidence. One scout figure was found wrong on verification (see Corrections).

---

## Corrections applied

| Scout claim | Actual | Source |
|---|---|---|
| annotation errors "52.8–66.1%" | **52.8%** (BIRD Mini-Dev), **62.8%** (Spider 2.0-Snow) | [arXiv:2601.08778](https://arxiv.org/abs/2601.08778) **[VERIFIED]** |

---

## 1. Metric choice

**Execution Accuracy (EX)** — compare result sets after running both queries. This is
what `semantic-bench/grade.py` implements. Alternatives and why they were rejected:

| Metric | What it does | Why not |
|---|---|---|
| Exact Match (EM) | string/AST equality against gold SQL | punishes correct queries written differently; useless across dialects |
| VES / R-VES | EX weighted by runtime | measures the engine, not the semantics |
| **EX** | result-set equality | **chosen** — the only one that tracks "did the user get the right answer" |

EX has three documented failure modes, all of which bit during this research:

1. **NULL / NaN comparison** — `NULL != NULL`, and pandas `NaN != NaN`. Both arms of a
   comparison must normalise. (`grade.py:scal()` coerces `pd.NaT`/`NaN`/`Decimal`/
   `datetime` to a canonical form.)
2. **Non-deterministic ordering** — a query without `ORDER BY` may return rows in any
   order. Order must be enforced *only* where the question demands a ranking; grading
   unordered results as ordered manufactures false failures. This produced a spurious
   "failure" class in the first run of the dataframe benchmark.
3. **Column-count mismatch** — a model returning extra descriptive columns is usually
   *more* useful, not wrong. Gold columns should be required as a **subset** of
   predicted columns, matched column-wise by value sequence. Grading on exact shape
   produced 8 false failures in the semantic benchmark's first pass.

## 2. Ablation evidence — what actually moves accuracy

Scout-reported, unverified unless marked:

| Intervention | Reported effect | Source |
|---|---|---|
| Schema linking (RAT-SQL) | **+14.76 pp** | arXiv:1911.04942 |
| External knowledge / business context (BIRD) | **~20 pp** gap | arXiv:2305.03111 |
| Synthetic column descriptions | +5–8 pp | arXiv:2408.04691 |
| Schema routing | +4.43 – 11.22 pp | arXiv:2312.03463 |
| Value sampling (naive) | **−7 pp** | DeepVIS |
| Hand-authored 4 KB semantics doc | **+17 – 23 pp** | [arXiv:2604.25149](https://arxiv.org/abs/2604.25149) **[VERIFIED]** |
| Semantic-layer-mediated agent (Spider2-snow) | **94.15%** EX, rank 3 | [arXiv:2606.31041](https://arxiv.org/abs/2606.31041) **[VERIFIED]** |
| SOTA agents on real enterprise warehouses | **10.8%** EX (GPT-5.2) | [arXiv:2409.02038](https://arxiv.org/abs/2409.02038) **[VERIFIED]** |

Every intervention above the line is a *context* intervention. None is a model
intervention. This is the corpus behind `00-REPORT.md` §0 finding 2, and
`00-REPORT.md` §6.0 measures the same effect independently on ERPNext.

## 3. Schema-size effects

- Spider 2.0 databases average **755 columns**; naive schema routing shows a **27.6%**
  schema-linking error rate.
- ERPNext is in the same regime: **529** DocTypes in stock `erpnext` alone (measured by
  Main, not scout-reported), Sales Invoice carrying **233 declared fields / 155 real
  columns**, rendering to **91,735 tokens** for the full app.
- Implication, confirmed independently by changAI shipping a fine-tuned retriever
  (`00-REPORT.md` §5.7): **retrieval is mandatory, not optional**, above ~10 tables.

## 4. Golden question set design

Scout recommendation vs what this research actually did:

| | Recommended | `semantic-bench` | Gap |
|---|---|---|---|
| Question count | 200 minimum | **40** | underpowered for small deltas; the measured +17.5 pp clears McNemar at p=1.9e-05 anyway, but per-trap cells (n=2–8) are indicative only |
| Stratification | by difficulty (easy/medium/hard/extra) | by **semantic trap** (docstatus, grain, join, currency, returns, domain, display, none) | deliberate — difficulty is a property of the question, trap is a property of the *schema semantics*, which is the variable under test |
| Curation | manual verification | manual, plus 3 gold defects found and fixed mid-run | — |
| Control group | — | 5 "none" questions answerable from column names alone; 100% in both arms | added by Main to rule out a prompt-length effect |

## 5. Known pitfalls

- **Benchmark contamination** (SPENCE, arXiv:2604.17771) — public benchmarks leak into
  pretraining. Directly observed here: frontier models scored 95.0% on *raw* ERPNext
  DDL, recognising `tabSales Invoice` from pretraining. This is why a semantic-layer
  benchmark on stock ERPNext **understates** the effect for custom DocTypes, which
  appear in no training corpus.
- **Annotation errors** — 52.8% (BIRD Mini-Dev) and 62.8% (Spider 2.0-Snow) of
  gold answers are wrong **[VERIFIED]**; correcting them moves leaderboard rank by up
  to ±9 positions and breaks rank correlation with the uncorrected set
  (Spearman 0.85 → 0.32). Encountered first-hand at small scale: 3 of 40 gold answers
  in `semantic-bench` were defective on first pass.
- **Duplicate rows** — strict comparison needs bipartite matching, not set equality.
- **Statistical testing** — paired designs need **McNemar's exact test** on discordant
  pairs, not two independent binomial CIs. `semantic-bench` reports both.

## 6. Recommended protocol (and what this research ran)

| Step | Recommended | Ran |
|---|---|---|
| Metric | Execution Accuracy + 95% binomial CI | ✅ EX + Wilson CI |
| Design | paired, single-shot | ✅ 40 q × 2 contexts × 3 model tiers = 240 |
| Significance | p < 0.05 | ✅ McNemar exact, p = 1.9e-05 |
| Question count | ≥ 200 | ❌ 40 — the main power limitation |
| Gold verification | expert review | ✅ manual + 3 defects corrected |
| NULL/order/shape guards | all three | ✅ all three |

**Honest summary:** the design is sound and the headline delta is large enough to
survive the sample size, but the question count is 20% of what the literature
recommends. Anyone productising this should extend to ≥200 questions across ≥3 ERPNext
modules before quoting the number externally.

---

## 7. Reproduction audit — 2026-08-12

Both harnesses were re-run from scratch to test whether they are a *foundation*
(`12-build-plan.md` Phase 0 Gate A reuses `semantic-bench/build.py`, Phase 2 productises
the harness) or a one-off. Runbooks now live in `semantic-bench/README.md` and
`dfbench/README.md`.

| Check | `semantic-bench` | `dfbench` |
|---|---|---|
| Fixture rebuilds from source | ✅ 6m39s, exit 0 | n/a (generates its own) |
| Deterministic | ✅ `context_{a,b}.txt` md5-identical to committed | seeded, unverified |
| Grading reproduces published figures | ✅ **exactly** — all 3 model rows, all 8 trap rows, both failure-mode splits | ❌ cannot run |
| Runtime available today | ✅ any bench venv with duckdb | ❌ **no interpreter on this box has polars + duckdb together** |
| Generation step on disk | ❌ archived output only, no driver | ❌ same |
| Entry point / CLI | ❌ flat scripts, hardcoded `/tmp` + bench paths | ❌ same |

**Verdict.** `semantic-bench` is a genuine, reproducible artifact: the §6.0 headline
survives a from-scratch rebuild with zero drift, which is the strongest form the claim can
take. `dfbench` is a *record of a run*, not a live harness — no interpreter on this box
carries its four dependencies together. Its version pins do survive in §6.6's
verification note, so it is reconstructible from a fresh venv; it is simply not live.

Neither is yet a harness in the Phase 2 sense. What to do about that is §8.

---

## 8. Decision — 2026-08-12

**Promote `semantic-bench`. Retire `dfbench`. Driver before questions.**

**`semantic-bench` is the foundation.** It reproduced exactly from a scratch rebuild, and
it is the only artifact in this directory that makes §0 finding 2 a measurement rather
than a citation. It becomes the Phase 2 seed. Sequencing is forced by a dependency, not a
preference: the generation driver (2a) must exist before the question count can grow (2b),
because there is no way to produce an answer for question 41 without it. Doing 2b first is
not slower — it is impossible.

**`dfbench` is retired as a live harness.** Its question is answered and the answer was
"you asked the wrong question": the dataframe library is irrelevant (12/12 both, verbosity
within 3%) and the cost is in the wire format (564x, JSON records vs Arrow IPC). A
benchmark whose finding has already hardened into a design decision has no ongoing job.
The finding graduates into a Phase 0 build requirement — Arrow IPC transport, never
`to_dict(records)` — and its future home is a perf test in the app's CI, not a research
artifact. Do not spend the environment work to resurrect it. `bench.out` stands as
evidence of a run.

**Corrected Phase 2 gate.** It read "≥80%, Databricks' published pre-UAT bar". That is
below the raw-DDL baseline's upper confidence bound (arm A: 78.3%, CI [70.1, 84.8]) — an
in-app implementation could score exactly 80%, pass the gate, and be statistically
indistinguishable from shipping *no semantic layer at all*. A gate the null hypothesis can
clear is not a gate. Replaced with **≥90.6%**, the Wilson 95% lower bound of the offline
prototype (115/120). Borrowed industry thresholds are not portable across baselines.

**What the benchmark licenses, and what it does not.** It shows the *mechanism*: a
DocType-derived semantic layer fixes join, grain, docstatus and currency errors, verified
against a clean control (5 questions answerable from column names alone, 100% in both
arms, ruling out a prompt-length effect). It does **not** license a competitive claim. No
serious competitor ships raw DDL to a model, so +17.5 pp is not a delta over Databricks or
Metabase — it is the cost those products pay to hand-build what Frappe already has in
`frappe.get_meta()`. The defensible sentence is "the layer is free here and expensive
there", never "we are 17.5 points better".

**Confidence.** Build Phase 1 on this evidence — $p = 1.9\times10^{-5}$ is not marginal
and the trap breakdown shows a mechanism, not a coincidence. Do not market on it until 2b
lands. Direction: trustworthy. Number: not yet portable.

---

## 9. The generation-target gap — construct validity

**The benchmark measures a generation target the product has explicitly rejected.** Both
arms of §6.0 had models emit **SQL**, graded by execution accuracy against DuckDB. But
`00-REPORT.md` §6.2's first non-negotiable is that the agent emits **Operation JSON,
never raw SQL**. Nothing in this document measured Operation JSON generation. That gap
went unstated until 2026-08-12 and is recorded here rather than quietly closed.

Three parts, with different levels of risk.

**1. Grammar coverage — measured, low risk.** All 40 gold queries are expressible in the
structured operations, and need only **7**: `source` (40), `select`/`rename` (37),
`filter` (35), `order_by` (17), `summarize` (14), `join` (9), `limit` (6). Static
analysis of the gold SQL finds zero CTEs, zero subqueries, zero window functions and zero
unions; `filter_group`, `union`, `pivot_wider`, `remove` and `cast` go unexercised. The
closed grammar loses nothing here. The questions were not written adversarially against
the grammar and cover one module, so this bounds the *benchmark*, not the product.

**2. Grading transfers by construction — no risk.** Execution accuracy compares
*result sets*, not artifacts. A harness that grades Operation JSON → compiled SQL →
rows uses the identical metric, guards and gold data. Phase 2 inherits the protocol
unchanged; only the thing being generated differs.

**3. Model competence in an unfamiliar grammar — unmeasured, real risk.** Models have
enormous pretraining exposure to SQL and **zero** exposure to Nakhoda's Operation JSON.
Closed grammar plus `strict_json_schema=True` plus a validate-and-repair loop kills
*syntactic* failure, but says nothing about *semantic* failure inside a grammar the model
has never seen — picking `summarize` where a chart-level aggregation was meant is a grain
error that validates cleanly and answers the wrong question. The magnitude is unknown and
cannot be inferred from the SQL result.

**Direction of bias.** This is the second unquantified bias in the corpus and it points
*opposite* to the first:

| Bias | Effect on the 95.8% | Why |
|---|---|---|
| Schema contamination (§4) | **understates** the layer's value | models recognise `tabSales Invoice`; custom DocTypes appear in no training corpus |
| Generation-target familiarity (§9) | **overstates** in-product accuracy | SQL is pretrained, Operation JSON is not |

They do not cancel — they are different magnitudes on different axes, and neither is
measured. Treat 95.8% as an upper bound on the SQL path and an unknown on the product
path.

**Cheapest resolution.** Phase 2a's generation driver should emit **both** targets for the
same 40 questions against arm B, and report the delta. One extra arm, no new questions, no
new gold data — it reuses everything. If Operation JSON tracks SQL within noise, §6.2's
first non-negotiable is free and the matter is closed. If it does not, the gap is the
price of inspectability, and that price should be known before Phase 4 commits to it.

---

## 10. Resolution — 2026-08-12

**Measured. Operation JSON tracks SQL exactly, and §6.2's first non-negotiable is
free.** Phase 2a's driver (`nakhoda/bench/`) ran both targets over the same 40
questions, arm B, three model tiers — 240 single-shot generations, graded by the
reimplemented grader that reproduces §6.0 figure for figure.

| Target | smol | default | slow | all | 95% CI |
|---|---|---|---|---|---|
| SQL | 33/40 | 40/40 | 39/40 | **112/120 (93.3%)** | [87.4, 96.6] |
| Operation JSON | 33/40 | 40/40 | 39/40 | **112/120 (93.3%)** | [87.4, 96.6] |

McNemar exact **p = 1.00** (discordant 5/5 — the same accuracy on different
questions, not the same answers). Against the frozen arm B of §6.0, the SQL run is
112/120 vs 115/120, **p = 0.453**: the driver reproduces the original within noise,
which is what licenses comparing anything to it.

**Risk 3 was real, and it was not model competence.** The first measurement put
Operation JSON at 98/120 (81.7%), −11.7 pp, p = 0.0043 — apparently the price of
inspectability, exactly as feared. It was not. Fifteen of the twenty-two failures
were one error:

```
OperationError: operations[1]: ['docstatus'] already in scope.
Name the joined column something else - this pipeline does not merge namespaces.
```

`join` refuses a selection whose name already exists on the left, by design — it is
the rule that makes a pipeline readable without knowing either schema. The prompt
never said so. Stating it, along with `date_trunc`'s argument order and its literal
unit domain (fixed in the engine's own function registry, which the prompt renders),
moved the arm from 98 to 112 and closed the gap entirely.

So the cost of a grammar with zero pretraining exposure is paid in **prompt
specification**, not in accuracy — provided every constraint the engine enforces is
one the prompt states. The failure is mechanical, loud, and fixable once; a wrong
answer in fluent SQL is none of those. `test_bench.py` now pins each stated rule to a
pipeline the engine must reject, because the inverse defect — a rule the prompt
invents and the engine does not have — costs accuracy forever and no measurement
would reveal it.

**What this does not cover.** Single-shot, no validate-and-repair loop, so it is a
floor for the product rather than a description of it: three of the four remaining
`ops` errors are the kind a repair loop is built to catch. The sample is still 40
questions over one module (§6 row 4), and the two biases in the table above are still
unquantified. The claim is narrow and it is the one that was missing: **the product's
generation target is no worse than the benchmark's.**
