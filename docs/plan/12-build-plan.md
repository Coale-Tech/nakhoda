# Nakhoda — build plan

Execution plan · 2026-08-11, rev. 2026-08-12 · derived from `00-REPORT.md` rev. 5
Evidence for every number here: `00-REPORT.md` §6.0 (accuracy), §6.6 (substrate), §6.9
(boundary). Naming: `11-naming.md`. Benchmark artifacts: `semantic-bench/`.
ML and dashboard phases: `15-ml-dashboards.md`. **UI phases (5, 8, 10) are specified by
`14-frontend-design.md` and its working mockup at `mockup/index.html`** — seven screens,
light + dark, on the real Espresso token set. Where a gate below says "matches the
design record", that mockup is the artifact it must match.

---

## 0. Scope contract

**Nakhoda is a standalone Frappe app: an AI-native analytics platform for Frappe/ERPNext.**

| It is | It is not |
|---|---|
| An independent app installed with `bench install-app nakhoda` | A fork of `frappe/insights` |
| A competitor to Insights | A plugin, extension or dependent of Insights |
| Semantic-layer-first, agent-second, UI-third | A chat box bolted to a schema |
| Built on `frappe` (MIT) + ibis/DuckDB/sqlglot (Apache-2/MIT) | Dependent on any AGPL code — Nakhoda *is* AGPL-3.0 (§7), but inherits it from nothing |
| A clean-room build — read Insights, copy none of it | An Insights importer or migration path (§8) |

The one-sentence claim it must earn: **the only BI tool that already knows what your
data means, because the application defined it.**

---

## 1. Ground truth — the incumbent, measured

Insights at `ea62bf6`, measured on this workstation:

| Surface | Size |
|---|---|
| Backend Python (excl. tests) | 13,870 LOC |
| Frontend `src2/` | 30,213 LOC (21,249 Vue + 8,964 TS) |
| DocType JSONs | 21 |
| Whitelisted endpoints | 91 |
| Licence | **AGPL-3.0** |

Largest backend files: `ibis/functions.py` 1,453 · `ibis_utils.py` 1,175 ·
`data_warehouse.py` 1,045 · `connectors/` 549.
Largest frontend blocks: `query/` 9,176 · `charts/` 6,732 · `components/` 3,256 ·
`workbook/` 2,502 · `dashboard/` 2,401.

**Read it. Copy none of it.** AGPL applies to code, not to architecture. The Operation
JSON grammar in `frontend/src2/types/query.types.ts` is the single most valuable thing
to study before writing Nakhoda's own.

---

## 2. Reuse / rebuild / refuse

**Reuse (all permissive, verified):** `frappe` MIT · `ibis-framework` 11 Apache-2.0 ·
`duckdb` 1.4 MIT · `sqlglot` MIT · `pandas` BSD-3 · `frappe-ui`.
§6.6 measured that the dataframe library is **not** the bottleneck — serialisation
dominates by ~20:1. Do not shop for a faster engine; ship the boring one.

**Rebuild (~4–5k LOC backend, ~8–10k frontend for a defensible v1):** operation compiler,
site-DB connector, DuckDB warehouse sync, semantic-model generator, agent loop, result
cache, inspector UI, chart renderers.

**Refuse — the three that make this worth doing:**

1. **No in-process code execution.** No `code` operation, no `safe_exec` pandas shim, no
   Python cell in a web worker. §2.3's bypass class cannot exist in code never written.
   Any Python, ever, runs out-of-process (phase 7) or not at all.
2. **No 90-function expression language.** Ship ~25. Every admitted function is
   generation surface the model can get wrong.
3. **No drag-and-drop pipeline builder.** Build the *correction* surface, not the
   *construction* surface.

These are the product thesis, not cost-cutting. Erode them and Nakhoda is Insights with
a chat box — a race §5.5 says Metabase already won.

---

## 3. Repo layout

```
apps/nakhoda/
  nakhoda/
    semantic/          # generator over frappe.get_meta(); retrieval/pruning
    engine/            # operation grammar → ibis → SQL; permission filter injection
    warehouse/         # DuckDB sync, incremental import
    connectors/        # site_db first; postgres/mysql after
    agent/             # Raven-pattern manager, tools, transcript
    doctype/           # see §4
    api/               # whitelisted endpoints
  frontend/            # Vue 3 + Vite + frappe-ui
    src/
      inspector/       # operation step viewer + editor  ← replaces Insights' query/
                       #   ONE component, retitled per surface: "Inspect answer" on Ask,
                       #   "Review patch" on Dashboards. Two inspectors = the design lost
      charts/          # renderers only; config is generated
      chat/
      workbook/
      dashboard/       # grid + patch diff review (Phase 10)
  pyproject.toml
  license.txt
```

```toml
dependencies = [
  "ibis-framework[duckdb,mysql,postgres]~=11.0.0",
  "duckdb~=1.4.3",
  "sqlglot<28.0.0",
  "pandas~=2.3.3",
]
[tool.bench.frappe-dependencies]
frappe = ">=15.0.0"     # note: NOT insights
```

```bash
bench new-app nakhoda
bench --site <site> install-app nakhoda
```

---

## 4. Data model

18 DocTypes. Introduced by the phase that needs them. The table previously stopped at
Phase 5 and undercounted at "~13"; phases 6, 9 and 10 each need storage.

| DocType | Phase | Purpose |
|---|---|---|
| `Nakhoda Settings` | 0 | Single. Model provider, token budget, row caps, permission defaults |
| `Nakhoda Data Source` | 0 | Connection config; site DB is the default source |
| `Nakhoda Table` | 0 | Synced table metadata + warehouse state |
| `Nakhoda Query` | 0 | Operations JSON + cache key. The unit of execution |
| `Nakhoda Semantic Model` | 1 | Generated from `get_meta()`, hand-correctable. Versioned |
| `Nakhoda Semantic Field` | 1 | Child. Label, type, enum domain, join target, grain, synonyms |
| `Nakhoda Metric` | 1 | Certified measure: definition, owner, grain. **Hand-authored — the metadata cannot supply this** |
| `Nakhoda Benchmark Set` | 2 | Question + gold result |
| `Nakhoda Benchmark Question` | 2 | Child |
| `Nakhoda Verified Query` | 3 | Trusted asset; preferred over generation, labelled in output |
| `Nakhoda Space` | 4 | Agent scope: sources + instructions + verified queries + MCP servers |
| `Nakhoda Agent Run` | 4 | Audit: prompt, tools called, operations, SQL, rows, tokens, cost |
| `Nakhoda Workbook` | 5 | Artifact container. **Must record the semantic-model version and prompt that produced it** |
| `Nakhoda Chart` / `Dashboard` | 5 | Presentation |
| `Nakhoda MCP Server` | 6 | Child of Space. Transport, URL/command, `cacheScope`, egress policy — Gate B fails without a per-server cache-scope field |
| `Nakhoda Intelligence Template` | 9 | A domain dashboard as a declarative record. The six shipped domains are six fixtures; a seventh is one more and zero Python |
| `Nakhoda Dashboard Version` | 10 | Applied patch + prior `items[]`. Revert is restoring a row, not replaying an inverse patch |

---

## 5. Phases and acceptance gates

Every gate is a command that passes or fails. No phase closes on judgement.

Phases 0–7 are the Nakhoda build. **Phases 8–10 (intelligence dashboards) depend only on
Phase 5** and may run in parallel with 6–7; they are numbered last because they are a second
product surface, not a prerequisite for the first.

### Before Phase 0 — the live leak (different codebase, do today)

Not Nakhoda work, listed here because it is the most urgent thing in this directory.
`/Users/mac/ERPNext/jkm/apps/insights` is a separate Insights fork on this workstation,
deployed and leaking now: `analytics/ml_engine.py` (4 whitelisted endpoints) and
`api/dashboard_chat.py` (13) carry **zero** `has_permission` calls between them, and
`get_dashboard(dashboard_type, filters)` (`ml_engine.py:629`) takes the company to query as
client-supplied JSON. Below that, `insights/ml/` contains **zero** references to
`get_permission_query_conditions` / `apply_row_permissions` / `apply_user_permissions` /
`build_match_conditions`. Full analysis: `15-ml-dashboards.md` §3.1.

*a.* Add `frappe.has_permission(..., throw=True)` to the 17 ungated endpoints, and stop
trusting `filters["company"]` — derive it from the user, or validate it against their
permitted companies.
*b.* Inject permissions at `api/ml/ibis_source.py:65-71`. The fork's own SQL→ibis refactor
(`1d7dffe` → `1815f8c`, 2026-08-11) created a single choke point that did not exist a day
earlier: `t(doctype)` returns a bare ibis table and 43 files import it. Upstream's
`apply_user_permissions` / `apply_column_permissions` / `apply_row_permissions` take
`t: Table` — the exact type it returns (`nvumabaranda/…/insights_table_v3.py:299, 336, 350`)
— so they are drop-in. Its only current scoping is an optional `company_filter` (`:74-83`)
fed by `default_company()` (`:86-90`), which falls back to `Global Defaults.default_company`:
a site-wide value, not a permission boundary.
*c.* Default `apply_user_permissions` to on. It ships as `0`.

> **Gate A:** an authenticated user with no ERPNext roles calling
> `ml_engine.get_dashboard("financial", '{"company":"X"}')` receives a `PermissionError`,
> not a P&L.
>
> **Gate B:** two users with different User Permissions get different totals from the same
> endpoint — `#919` reproduced against `api/ml/*` and proven fixed.
>
> **Gate C:** on a table with 1M permitted rows the compiled SQL contains a subquery, not a
> literal `IN` list. The fork materialises every permitted primary key into Python and then
> into the SQL text (`jkm/…/insights_table_v3.py:108-145`). Check the SQL, not the result.

### Phase 0 — Engine
Scaffold; site-DB connector; operation compiler → ibis → DuckDB; permission-filter
injection; result cache.

> **Gate A:** each of the 40 gold queries in `semantic-bench/questions.py` returns results
> **row-for-row identical** to the same query run directly against DuckDB. Reuse
> `semantic-bench/build.py` to seed the fixture — it already builds an authentic
> 529-DocType ERPNext schema.
>
> *Expressibility is already settled and is no longer part of this gate.* Static analysis
> of the gold SQL (2026-08-12) puts all 40 inside the structured operations, needing only
> **7**: `source`, `select`/`rename`, `filter`, `order_by`, `summarize`, `join`, `limit`.
> Zero CTEs, subqueries, window functions or unions. Ship those 7; hold 14 as the ceiling;
> `custom_operation`, `sql` and `code` are a standing refusal, not a later decision —
> they are how a grammar stops being closed. See `00-REPORT.md` §6.2.
>
> **Gate B — permissions, and it is not optional.** Two users with different User
> Permissions run the *same* aggregate against the warehouse and get different,
> correct numbers; a user with no read access gets zero rows, not an error and not
> everything. Test row-level, column-level (permlevel), and child-table grain
> separately. `insights_table_v3.py:299-367` is worth reading for the *shape* of the
> problem — ibis `semi_join` for rows, a `get_permitted_fields` projection for columns —
> but write your own against `frappe.permissions` directly, per §1. It must **fail
> closed** when no permission query comes back. Insights' own gap here is
> issue #919; do not reproduce it. This is the most expensive non-AI work in the plan
> and it belongs in phase 0, because retrofitting security after the engine exists is
> how #919 happened.

### Phase 1 — Semantic layer  ← *the differentiator*
Generator over `frappe.get_meta()`; enum value domains; Link-derived join graph;
child-table grain; `.po` catalogues as the synonym source. **Retrieval/pruning ships
here, not later.**

> **Gate A:** generator output on a live ERPNext site is structurally equivalent to
> `semantic-bench/context_b.txt`, produced with zero hand-editing.
> **Gate B (scale):** all 529 DocTypes render to 91,735 tokens (~$0.115/question) — so
> retrieval must select the right table set for **≥90%** of the 40 benchmark questions
> while staying under a fixed per-question token budget. This gate exists because §7
> risk 5 locates the residual risk here.

### Phase 2 — Eval harness
`Nakhoda Benchmark Set`; re-implement §6.0's paired protocol in-app; wire to CI.
Seeded from `semantic-bench/`, which reproduced exactly on a from-scratch rebuild
(`10-eval-methodology.md` §7). Three steps, in dependency order:

> **2a. Generation driver.** `semantic-bench` can only re-grade frozen output — the code
> that called the models was never written to disk. This is a *hard* prerequisite for 2b:
> you cannot add question 41 without a way to generate an answer for it. Hours of work.
>
> Make it emit **two targets** for the same 40 questions against arm B: SQL and
> Operation JSON. §6.0 measured SQL, but §6.2 forbids the agent from emitting SQL — so
> the product's actual generation target is currently unmeasured
> (`10-eval-methodology.md` §9). One extra arm closes it: same questions, same gold, same
> execution-accuracy metric. If Operation JSON tracks SQL within noise the non-negotiable
> is free; if it does not, that delta is the price of inspectability and Phase 4 should
> know it before committing.
>
> **2b. Question count to ≥200** across ≥3 ERPNext modules. The real work, and the one
> limitation §6 self-reports. Until it lands, 95.8% is an internal signal, not a number
> to quote.
>
> **2c. CI wiring**, failing on regression.

> **Gate:** in-app accuracy **≥90.6%** — the Wilson 95% lower bound of what the offline
> prototype achieved (115/120). **Not ≥80%.** Databricks' published pre-UAT bar is the
> wrong instrument here: raw-DDL arm A scored 78.3%, CI [70.1, 84.8], so an 80% result is
> statistically indistinguishable from having *no semantic layer at all*. A gate the
> null hypothesis can pass is not a gate. Ship nothing AI-facing before this passes.
> Expect to find gold-SQL defects: three were found and fixed during §6.0, and
> [arXiv:2601.08778](https://arxiv.org/abs/2601.08778) documents 52.8%/62.8% annotation
> error rates in the public benchmarks.

### Phase 3 — Verified queries
`Nakhoda Verified Query` + approval workflow.

> **Gate A — the asset is governed.** An unapproved query is not servable, approval is
> enforced by Frappe permissions rather than by hiding a button, and an answer sourced
> from a verified query is labelled as one. Runs with no agent present — this is the
> half that survives the no-AI fallback at the end of this section.
>
> **Gate B — the agent prefers it.** Given a question a verified query already answers,
> the agent serves that query instead of generating SQL. Cannot be tested before Phase 4
> exists, so it is checked when Phase 4's gate runs; it is stated here because it is the
> reason Phase 3 exists at all.

### Phase 4 — Agent
Raven-pattern manager; tools over Nakhoda's own API; stream over
`frappe.publish_realtime`; emit Operation JSON.

> **Gate:** **≥95%** on the benchmark using the *cheap* model tier. §6.0 measured 95.0%
> for a small model with the layer, beating a frontier model without it (87.5%). If you
> need a frontier model to pass, the semantic layer is under-built — fix phase 1, not
> the prompt. Plus: zero raw SQL emitted by the model, and every run written to
> `Nakhoda Agent Run`.

**Model selection — adopted from `jkm/apps/insights` (`ai/` + `ai_reasoning/`).** The
gate above already says "cheap model tier"; this is what a tier is. The fork's design is
right and its implementation never ran — take the former, per invariant 11 write the
latter fresh.

*Adopt, four ideas:*

1. **Tiers are named, models are data.** `FAST` / `BALANCED` / `PREMIUM` as an enum whose
   values are the only place a model id appears, so a catalog refresh is a one-line
   change. The fork learned this the hard way — its `llama-3.1` and `claude-3.5` ids were
   **delisted upstream** and the tier names survived it. `config/settings.py` keys quota
   percentages by tier name for the same reason. Model ids rot on a timescale shorter
   than this roadmap; nothing else in Nakhoda may name one.
2. **Free-first allocation.** One daily budget, split **70 / 25 / 5** across the tiers,
   with `FAST` and `BALANCED` both on `:free` models and only 5% on paid. The default
   path costs zero, which is what makes the §6.7 BYOM position credible rather than
   aspirational.
3. **Degrade, never fail into the UI.** Quota exhausted → next tier. Model errors → next
   model. Three consecutive rate-limits → one plain-language message. Every terminal
   state returns a value carrying `error`; nothing raises at the user.
4. **Providers behind one ABC, lazily and independently registered.** The fork ships
   seven — `openrouter`, `ollama`, `ollama_cloud`, `openai`, `nvidia`, `moonshot`, plus
   Kimi/Codex auth — each `ImportError`-guarded so a missing SDK degrades one provider
   instead of the factory. Local Ollama discovers its catalog at runtime from
   `/api/tags`, so the model list is whatever the operator actually pulled. **BYOM is a
   peer, not a fallback** — that was §8's model-provider question, now closed.

*Two hard-won fixes to carry as requirements, not code* — both are comments in the fork
recording a bug that had already shipped:

- Pass the **requested** provider name through the factory; never let it fall back to the
  **saved** setting. Otherwise "test connection before saving" probes the wrong host.
- A loopback URL is meaningless for a cloud provider. `ollama_base_url` ships a localhost
  default which would otherwise shadow the cloud endpoint and make discovery probe the
  local daemon, so the cloud catalog never appears.

*Do not adopt — three defects, all in the router, none in the provider layer:*

- **It has never executed.** Six call sites in `processing/task_processors.py` call
  `route_task`; the class defines `route_request`. Its `_execute_request` calls
  `client.query(...)`; no provider defines `query`. Broken at both boundaries
  independently, so the tier logic below the entry point is unproven — it is a design
  document, and adopting it means writing and testing it for the first time.
- **The cost routing is inverted.** `_select_model` sends `parse|extract|classify|`
  `summarize|translate` to **PREMIUM** — the paid tier holding 5% of quota — and
  `forecast|predict|regression|clustering` to the free `BALANCED`. Any question
  containing "summarize" bills the expensive tier, and because the simple test runs
  *after* the complex one, "summarize the forecast" does too. Cheapest-capable wins;
  escalation is earned.
- **Quota is global.** `TaskRequest.user_id` exists and is never used for accounting, so
  one user drains the org's budget. Nakhoda already scopes everything else per user.

*One replacement, and it is the Nakhoda-specific part.* The fork picks a tier by keyword-
matching raw user text (`analyze_query_complexity`, plus a second overlapping keyword
pass in `_select_model`). Nakhoda does not have to guess: complexity is **structurally
known before any model is called** — whether a `Nakhoda Verified Query` matched (Phase 3:
zero tokens, no routing at all), how many tables the semantic layer says the question
spans, whether it needs a join, a window, or a grain change. Route on that vector, and
**escalate a tier only on a validation failure**, never on a string. Two payoffs: it is
deterministic, and unlike a keyword hit it is a reason that can be written to
`Nakhoda Agent Run` alongside prompt, tools, operations, SQL, rows, tokens and cost
(invariant 8). A router that cannot explain its own choice cannot be audited.

> **Gate — the tier is load-bearing and the ladder is visible.** Run the benchmark with
> `PREMIUM` disabled entirely: ≥95% must still hold, or the semantic layer is
> under-built (fix phase 1). Then assert every `Nakhoda Agent Run` row records the tier
> used *and* the structural reason it was chosen, and that no row shows an escalation
> without a preceding validation failure.

### Phase 5 — Correction UI  ← *specified by `14-frontend-design.md`*
Operation inspector; chart renderers; workbook artifact; **the approval component** that
phases 6 and 10 both consume. The Ask screen in the mockup is the spec, not an
illustration: the answer card carries the assumption taxonomy (`applied` grey vs
`needs you` amber + inline prompt), the permission notice, the receipt line, and an
inspector whose every step is badged with the layer that produced it.

Approval lives here rather than in either consumer because the plan previously had a
cycle: Phase 6 Gate C said Phase 10 builds the component, Phase 10 said it reuses
Phase 6's. Neither could go first. It is an inspector-family concern, so it ships with
the inspector — which makes this section's opening claim, that phases 8–10 depend only
on Phase 5, actually true.

**Four origin badges, four appearances:** `FROM QUESTION`, `SEMANTIC MODEL`, `LINK GRAPH`,
`INJECTED`. The badge exists to say which layer to go fix, so no two may render alike —
a draft of the mockup had `LINK GRAPH` and `SEMANTIC MODEL` sharing one style, which
silently voids the whole mechanism. Separate by fill vs outline, not by adding a hue:
colour is reserved for attention, and provenance is not attention.

> **Gate:** every operation in the grammar is inspectable and editable, and a user can
> correct one wrong step and re-run **without retyping the question**. Without this the
> §6.2 non-negotiables are unenforceable.

> **Gate — provenance is rendered, not just logged.** Invariant 8 logs the turn;
> this gate requires it on screen. An answer must show its assumptions, the rows its
> permissions removed, and the realised SQL *before* execution. Verify by asking a
> question whose answer depends on an unstated choice (returns netted or not) and
> confirming the UI surfaces the choice as a decision, not a footnote.

> **Gate — charts do not lie, measured in the DOM.** Bar height must be proportional to
> value within 2%, and every axis label must sit under the bar it names (0px drift).
> Both were real defects in the mockup, invisible to the eye and found only by measuring
> rendered geometry: `display:flex` bars resolved `height:N%` against the column
> *including* the value label, so the tallest bar silently rescaled the series by 11.4%;
> and `flex:1` axis labels against fixed-width bars put the last label 99px from its bar.
> Put both assertions in CI against the real renderer, not a snapshot.

> **Gate — the badges are distinguishable, asserted not eyeballed.** Render every origin
> badge the build defines — four here, five once Phase 6 adds `PLUGIN` — and compare
> computed `background`, `color` and `box-shadow`; any two identical triples fail.
> `PLUGIN` is the one that may take a hue: a third-party prompt inside trusted chrome
> *is* attention, which is exactly what Gate C is about. Plus `0` WCAG AA text failures
> across every screen × light and dark, measured on the rendered DOM. The mockup passes
> both today, and got there by failing them: 87 light and 17 dark contrast failures
> before two text token roles were defined, because Espresso's light ink ramp jumps
> 4.17 → 7.81 with nothing between.

### Phase 6 — Plugins
MCP server registration per space, over the SDK's **client-side** transports —
`MCPServerStdio` for local, `MCPServerStreamableHttp` for remote (`agents/mcp/server.py:1110,
1375`). **Not `MCPServerSse`:** legacy HTTP+SSE is deprecated as of MCP `2026-07-28`, on a
12-month offramp. **Never `HostedMCPTool`:** it is OpenAI-only, and Raven's own provider
filter strips it for local models (`agents_integration.py:349-376`), which is why Raven has
no plugin story on-prem.

**Version floor — build against the stateless spec, not the one on this bench.** MCP
`2026-07-28` ships only in `mcp 2.0.0`; the entire 1.x line including `1.29.0` still reports
`LATEST_PROTOCOL_VERSION = "2025-11-25"`. This bench has `mcp 1.26.0` under `openai-agents
0.18.3`, pinned `mcp<2`. Require `openai-agents >= 0.20.0` (pin widened to `mcp<3`,
released 11 Aug 2026) + `mcp >= 2.0.0`. Note `mcp 2.0.0` restructured the package —
`mcp/types.py` became `mcp/types/`, and `client/caching.py`, `client/subscriptions.py`,
`server/_streamable_http_modern.py` are new — so this is a migration, not a bump.

> **Gate A — data reachability.** A third-party MCP server registered on a `Nakhoda Space`
> is callable by the agent, its tools appear in the transcript, and it runs under the
> *asker's* permissions — verified by registering one server and confirming a restricted
> user cannot reach data through it that they cannot reach directly. A plugin system that
> escalates privilege is worse than no plugin system. Re-run the whole check against a
> **local model** with no network egress; if plugins only work on OpenAI, the phase failed.

> **Gate B — catalog reachability.** `2026-07-28` makes `tools/list` cacheable with `ttlMs`
> and `cacheScope`, where `cacheScope` states whether a catalog may be shared across users.
> The Agents SDK exposes only `cache_tools_list: bool`, cached per server object with a
> manual dirty flag and **no user scoping** (`agents/mcp/server.py:846`) — still true in
> `0.20.0`. Register a plugin that returns a per-user tool catalog; user A's tools must not
> appear for user B. Honour `cacheScope` or disable the cache. This is `#919`'s bug class —
> a permission boundary lost inside a cache — arriving through the plugin door.

> **Gate C — approval provenance.** MRTR replaces server-initiated elicitation: a tool
> returns `resultType: "input_required"` and the client retries with `inputResponses`. That
> is the **Phase 5 approval component** — reuse it, but a plugin prompt MUST be visually
> attributed. Add a `PLUGIN` origin badge alongside the
> inspector's `FROM QUESTION` / `SEMANTIC MODEL` / `LINK GRAPH` / `INJECTED`. Verify a
> plugin cannot render a prompt indistinguishable from Nakhoda's own. Unattributed, this
> teaches users to reflex-approve third-party requests inside trusted chrome.

### Phase 7 — Notebooks
Out-of-process kernel (marimo or a container/seccomp subprocess) or nothing. Difficulty
4/5. Do last, or never.

> **Gate:** the §2.3 exploit — reading an arbitrary file off disk via an unguarded
> `pandas.read_csv` — is attempted against the kernel and **fails**. Reuse the exact
> probe that broke Insights' shim. If it succeeds, the kernel is not out-of-process
> enough, and invariant 1 in §6 says ship nothing.

### Phase 8 — ML as operations
Add `forecast` / `detect_anomalies` / `segment` / `score` to the operation union.
Reimplement `sales_forecasting`, `gl_anomaly` and `customer_segmentation` first — the
three with the most production mileage in the jkm fork, so their *behaviour* is the
best-evidenced. **Do not port the code.** That fork inherits Insights' AGPL-3.0
(`jkm/apps/insights/license.txt`, verified), so lifting it would decide §7's licence
question by accident. Read it for the method — which estimator, which parameters, what
it does with sparse series — and write Nakhoda's own against `statsmodels`/`scikit-learn`
directly; the modelling is generic, only the wrapper is theirs. Compute in the
already-forked web worker; **never** re-enqueue onto RQ (`15-ml-dashboards.md` §6.1 —
`fork()` corrupts numpy/OpenBLAS thread state and it is not fixable at runtime; the fork
proved this across eight execution models in ten hours on 2026-08-11).

> **Gate:** a forecast renders in a stock chart with no `ml_predictions` branch anywhere in
> the render path, and respects the caller's row permissions. An ML result that cannot be
> filtered, joined and cached like any other operation has not been integrated, only attached.

> **Gate — no ML surface exists.** The design consequence of this phase is a *subtraction*,
> and it is checkable: grep the frontend for an ML route, an ML nav item, an ML chart
> component or an ML-specific origin badge, and find zero. In the mockup's Dashboards
> screen `forecast` is step 5 of an ordinary pipeline badged `FROM QUESTION`, identical
> to `summarize`, inheriting the permission filter at step 4 for free. If a reviewer can
> point at "the ML part of the UI", the 147 `api/ml` endpoints were moved, not deleted.

### Phase 9 — `Intelligence Template` DocType
A domain dashboard becomes a declarative record, not an `if/elif` chain.

> **Gate:** a seventh domain is added by writing one fixture and **zero Python**. The fork's
> hardcoded equivalents (`DASHBOARD_TYPES`, `_calculate_kpis`, `_prepare_charts`) must have no
> counterpart in Nakhoda — if you find yourself writing one, this phase has failed.

### Phase 10 — `DashboardPatch`  ← *specified by `14-frontend-design.md` §3*
The chat refines by emitting a validated patch over `items[]`, not prose. Schema, validator,
dry-run, diff preview, approval, versioning. This is invariant 1 applied to a second surface,
and it reuses the Phase 5 inspector and approval component. No dependency on Phase 6.

The mockup's Dashboards screen is the spec. Three ops — `add_chart`, `set_filter`,
`remove_item` — with state carried in the layout itself: amber rail `will change`, green
rail `added by patch`, struck title `removed by patch`. The removed card **stays on the
page** showing what left and why; a patch that silently deletes a chart is a patch nobody
will approve twice. The inspector is the Phase 5 component retitled "Review patch", not a
second one.

> **Gate:** "split revenue by territory and add last year" produces a correct patch, previews
> a diff, applies on approval, and reverts cleanly. An adversarial prompt attempting a write
> or a `DROP` fails validation **because the grammar has no op for it** — not because a filter
> caught it.

> **Gate — every touched item is named in the diff.** Mechanical, not aesthetic: for each
> op in the patch, assert the preview renders the target item's title, its state
> (`will change` / `added` / `removed`), and the field that changes — and that removed
> items remain on the page rather than vanishing. Revert restores the prior
> `Nakhoda Dashboard Version` row with layout intact. Both assertions run in CI.

### Gate index

Every gate is a command that passes or fails; no phase closes on judgement. Four of them
assert on the *rendered* DOM or on the file tree rather than on behaviour, because the
defects they catch are invisible to review: the mockup's own bars silently rescaled the
series by 11.4% and its axis labels sat 99px from the bar they named, and both survived
repeated eyeballing. A gate a careless reviewer can nod through is not a gate.

| Phase | Gate | Asserts | Runs as |
|---|---|---|---|
| **all** | — | no normalised 8-line shingle from either AGPL tree appears in `nakhoda/` (invariant 11) | CI |
| pre-0 | A | roleless user calling `ml_engine.get_dashboard` gets `PermissionError`, not a P&L | CI |
| pre-0 | B | two users with different User Permissions get different totals — `#919` reproduced, then fixed | CI |
| pre-0 | C | at 1M permitted rows the compiled SQL contains a subquery, not a literal `IN` list | CI (SQL text) |
| 0 | A | 40 gold queries return results identical to DuckDB, row for row | CI |
| 0 | B | row, column (permlevel) and child-table grain each filter separately, and fail closed | CI |
| 1 | A | generator output ≡ `context_b.txt`, produced with zero hand-editing | CI |
| 1 | B | retrieval picks the right table set for ≥90% of the 40 questions under a fixed token budget | CI |
| 2 | — | in-app accuracy ≥90.6%, the Wilson lower bound of the offline 115/120 | CI |
| 3 | A | unapproved queries unservable; approval enforced by Frappe permissions; answers labelled | CI |
| 3 | B | agent serves a verified query instead of generating one — checked when Phase 4's gate runs | CI |
| 4 | — | ≥95% on the *cheap* model tier; zero raw SQL emitted; every run logged | CI |
| 4 | — | ≥95% holds with `PREMIUM` disabled; every run records its tier and the structural reason | CI |
| 5 | — | every operation inspectable and editable; correct one step and re-run without retyping | e2e |
| 5 | — | provenance rendered before execution: assumptions, rows removed, realised SQL | e2e |
| 5 | — | charts do not lie: bar height ∝ value within 2%, 0px axis-label drift | CI (DOM) |
| 5 | — | no two origin badges share a `background`/`color`/`box-shadow` triple; 0 WCAG AA text failures | CI (DOM) |
| 6 | A | plugin runs under the *asker's* permissions — re-run against a local model with no egress | e2e |
| 6 | B | user A's tool catalog never appears for user B (`cacheScope` honoured or cache off) | e2e |
| 6 | C | a plugin cannot render a prompt indistinguishable from Nakhoda's own | CI (DOM) |
| 7 | — | the §2.3 `pandas.read_csv` arbitrary-file read is attempted against the kernel and fails | probe |
| 8 | — | a forecast renders in a stock chart with no `ml_predictions` branch in the render path | CI |
| 8 | — | no ML route, nav item, chart component or origin badge exists anywhere in the frontend | CI (grep) |
| 9 | — | a seventh domain costs one fixture and zero Python | CI |
| 10 | — | patch previews as a diff, applies on approval, reverts cleanly; a `DROP` fails validation | CI |
| 10 | — | every touched item named with its state; removed items stay on the page as `removed` | CI |

### The no-AI fallback — what survives if the agent is cancelled

The sequence is ordered so that cancelling the AI leaves a product, not a half-built one.
That is the test of a good sequence, and it is worth stating precisely because the
one-line version of this claim was wrong in two ways.

**What survives.** Phase 0 gives a permission-correct operation engine — the compiler,
the row/column/grain filter injection, the result cache. Phase 1 gives the semantic
layer, auto-derived from `frappe.get_meta()`. Phase 3 gives a curated library of
approved queries, governed by Frappe permissions. That combination is a BI tool with a
governed semantic layer, which is what Lightdash sells (`00-REPORT.md` §5.5) — except
Lightdash makes you author the layer as dbt YAML, Metabase as a Data Studio dataset and
WrenAI as MDL (§8). Nakhoda derives it. **The differentiator is the phase that does
not need an LLM**, which is the whole reason the fallback is worth having.

**Correction 1 — "building", not "shipping".** The report says these phases are worth
*building* if the AI is cancelled (`00-REPORT.md` §6.4); an earlier revision of this plan
tightened that to *shipping*, which overstates it. Phases 0, 1 and 3 have no user
interface: the operation editor and chart renderers are Phase 5. A no-AI product is
**0 + 1 + 3 + the non-agent half of 5** — the inspector as a query builder, the chart
renderers, the workbook. What Phase 5 loses without an agent is the assumption taxonomy,
the receipt and the `FROM QUESTION` badge, because there is no question. Everything else
in that phase is ordinary BI and would have to be built anyway.

**Correction 2 — Phase 3's gate is agent-shaped.** "The agent demonstrably prefers a
verified query over generating one" cannot be run without Phase 4, so as written Phase 3
does not close in a no-AI world. Split it. The AI-independent half — the query is a
governed asset, approval is enforced by Frappe permissions rather than a hidden button,
and the answer is labelled — is testable on its own and is the half that survives. The
preference behaviour is really a Phase 4 acceptance criterion filed under the wrong
phase.

**Phase 2 is deliberately absent** from the fallback: the eval harness exists to measure
the agent. Keep Phase 0 Gate A in CI regardless — row-for-row equality against DuckDB is
an engine test, not an AI test, and it is the only thing standing between a governed
semantic layer and a governed semantic layer that returns wrong numbers.

---

## 6. Invariants

Hold these at every phase; they are what the report's evidence actually supports.

1. The agent emits **Operation JSON, never raw SQL** — structured operations only, and
   never `custom_operation`, `sql` or `code`. A grammar with an escape hatch is not a
   closed grammar, and the agent will find the hatch. Coverage measured: 40/40 questions
   in 7 operations (`00-REPORT.md` §6.2).
2. The agent runs as `frappe.session.user`. **Never elevate.** Row-level scoping is
   structural, not prompted.
3. **Dry-run before execute** — expand to realised SQL with injected permission filters
   and show it before touching the database (WrenAI's `dry-plan`, §5.5).
4. Precedence ladder: org settings > role permissions > space instructions > user
   prompt, higher always wins (Fabric's model, §5.3).
5. Space instructions stay **≤20 lines** — Databricks states longer degrades quality.
6. Ground every literal via `get_distinct_column_values()`. String hallucination is the
   #1 NL2SQL failure mode.
7. The semantic model must stay **generated**. The moment it requires hand-maintenance
   you have inherited Airbnb Minerva's problem (§7 risk 3) and lost the edge. Hand-author
   **measures only** — the metadata cannot supply them (only 5.0% of ERPNext's 10,413
   fields carry a description).
8. Log prompt, tools, operations, SQL, rows, tokens, cost on every turn.
9. **Render the provenance, not only the log.** Invariant 8 makes a turn auditable after
   the fact; this one makes it legible during. Every answer ships with its assumptions,
   the rows permissions removed, and the realised SQL — visible by default, not behind a
   disclosure triangle. This is the product's single differentiating decision
   (`14-frontend-design.md` §0): every competitor renders a chat bubble and hides the
   SQL, so the answer arrives with no account of how it was reached. Losing this makes
   Nakhoda one more of them.
10. **Numbers on screen are computed, never illustrative.** Applies to demos, docs and
   design artifacts as much as to the app. Every figure in the mockup is derived from
   the seeded DuckDB and re-derivable; earlier drafts carried a stale headline and a
   permission count off by 86 invoices, and both survived review by looking plausible.
11. **No AGPL line enters the tree, and CI proves it.** AGPL-3.0 → AGPL-3.0 copying is
   *legal* (§7), which is exactly why this needs to be mechanical rather than assumed:
   the rule now protects two things the licence decision does not. First, **dual-licensing
   optionality** — copied lines are Frappe's copyright, cannot be relicensed by you, and
   kill the FAC revenue model silently (§7). Second, **the §2 refusals** — the files worth
   copying are the ones carrying the surface Nakhoda exists to reject: `ibis_utils.py`
   brings the `code`/`sql`/`custom_operation` operations, `functions.py` brings the
   90-function expression language. Copying is how the grammar reopens by accident.
   Prototyped and measured on this workstation, 2026-08-12:

   > Strip comments, collapse whitespace, drop lines ≤12 chars, drop `import`/`from`
   > lines and any line with no operator or keyword. Cut what remains into overlapping
   > 8-line windows, hash each with blake2b-64, and fail the build on any collision
   > between `nakhoda/` and the union of the two AGPL trees.

   **40,641 shingles from both trees, built in 2.3s** — cache it and each CI run only
   hashes the diff. Validated both ways: it flags **2,295 windows the `jkm` fork
   inherited verbatim from upstream (8.8% of the fork)**, and produces **zero false
   positives across 9,067 shingles of MIT `frappe/utils`**. The import-block and
   bare-identifier filters are load-bearing — without them two files importing the same
   `frappe.utils` date helpers alphabetically collide, which is the one false positive
   the first draft produced. Architecture, grammars and failure modes are free to
   travel; lines are not.

---

## 7. Licence — decided: AGPL-3.0

Frappe's MIT left the choice free; the choice is **AGPL-3.0**. The reason is ecosystem
fit and optionality, not protection — see the limits below before relying on it.

Measured on this workstation: `frappe` is MIT, but every app-layer product around it is
copyleft — `erpnext` **GPL-3.0**, `hrms` **GPL-3.0**, `insights` **AGPL-3.0**, FAC
**AGPL-3.0**. AGPL is the default expectation for a Frappe app, not a statement. MIT
would be the anomaly, and a costly one: Frappe Cloud already bundles Insights from
$5/mo, so an MIT Nakhoda is a donation to the incumbent's distribution channel. Frappe
distributing a third-party AGPL AI tool is settled precedent — FAC sits on the Frappe
Cloud Marketplace under AGPL-3.0 (`05-community.md` §10.5). Customer FUD is largely
pre-absorbed too: ERPNext shops have run GPL-3.0 in-process for a decade.

**What AGPL does not buy you — two corrections to the obvious reading.**

1. **It is no defence against §8.3, the risk that actually threatens Nakhoda.** Insights
   is AGPL-3.0, so Nakhoda's AGPL-3.0 code is copy-compatible *into it*. Frappe can
   absorb the semantic layer wholesale, comply by staying AGPL, and ship it in the app
   that already has the distribution. AGPL defends against *proprietary* capture; the
   dangerous predator here is copyleft and first-party. Only source-available (BSL/SSPL)
   answers this, and that trade forfeits the ERPNext install base the whole thesis rests
   on — rejected, but rejected knowingly. **The moat is Phase 1 shipping first, not law.**
2. **"Hostile to cloud resellers" overstates it.** Metabase's moat is *open-core* —
   AGPL core plus a proprietary `/enterprise` — not AGPL alone. Copyleft deters nobody
   when the source is already public and compliance means linking to the repo. Frappe
   Cloud would host Nakhoda on exactly the terms it hosts Insights.

**The revenue model this enables, and the two things that foreclose it.** FAC's model is
the verified template: AGPL-3.0 + sponsors + a named services partner + **an explicit
dual-licensing offer**. Given correction 2, this — not reseller deterrence — is the real
reason to prefer AGPL over MIT: copyleft is worth little as a wall and a great deal as a
negotiating position with anyone who wants to embed Nakhoda in something closed. But you
can only relicense code whose copyright you hold, so it dies quietly in two ways:

1. **Copying AGPL code you don't own.** Frappe Technologies' lines in your tree cannot
   be relicensed by you, and Frappe has no reason to grant an exception. A dozen copied
   lines from `ibis_utils.py` are enough. This is now the real reason for invariant 11 —
   not licence *choice*, which is settled, but licence *optionality*, which is not.
2. **Outside contributors without a CLA.** Same defect, arriving socially instead of by
   copy-paste. Retrofitting a CLA after contributors exist is the "worse problem" this
   section used to warn about, and it is now the only part of the licence question still
   live: **decide the CLA before the first public commit, not the licence.**

**Recommended: adopt the CLA.** AGPL alone leaves exactly one future. AGPL + CLA leaves
three and closes none — stay pure OSS, dual-license (FAC), or go open-core (Metabase's
*actual* moat, per correction 2, and the only one of the three that answers a funded
competitor). Cost is one `CLA.md` and `cla-assistant.io` wired to an Apache-ICLA
derivative. Cost of skipping it is permanent and invisible until the first outside PR
merges. The CLA backlashes people cite — HashiCorp, Elastic, Redis — were all
*relicensing after the fact*, breaking an implied promise; declared intent from commit
one reads differently, which is why FAC states its dual-licensing offer openly and takes
no flak for it. Say it in `CONTRIBUTING.md` on day one. Declining the CLA is defensible;
only the accident is not.

**One architectural consequence.** AGPL reaches a derivative work, and a plugin that
imports Nakhoda's Python in-process is arguably one. Phase 6 already puts every plugin
out-of-process behind MCP (`MCPServerStdio` / `MCPServerStreamableHttp`) for tenancy and
trust reasons; that boundary is now also the licence boundary, and it means a customer
can write a proprietary plugin without the question arising. Do not add an in-process
plugin hook later without re-opening this paragraph.

---

## 8. Open decisions

Things this research cannot settle for you:

1. **CLA or AGPL-only, forever.** The licence is settled (§7: AGPL-3.0); what it leaves
   open is whether you keep the right to dual-license later. That requires holding all
   the copyright, so it needs a CLA (or DCO + assignment) adopted *with* `LICENSE`, not
   after contributors arrive. Choosing "no CLA" is legitimate — it is friction that
   costs early contributors — but choose it deliberately.
2. **How hard to court the maintainer.** `00-REPORT.md` §7 risk 4: Frappe could add a
   `get_meta()` semantic layer to Insights for ~1,500 LOC on top of the 44,000 it
   already has. The window is real (zero AI code in framework v16 or Insights v3) but it
   is a window.

### Closed — model provider and tiering

Previously "BYOM self-hosted is the §6.7 positioning win but adds support surface."
**Decided: BYOM is a peer provider, not a fallback, and the default path is free.**
Adopted from the design already built in `jkm/apps/insights` — three named tiers with
model ids as data, a 70/25/5 daily budget with the top two tiers on `:free` models, an
ABC over seven providers including local Ollama, and degradation that never raises at
the user. Full adoption notes, the two shipped bug-fixes worth carrying, the three
defects to leave behind, and the one replacement (route on the semantic layer's
structural signal, not on keywords in user text) are in Phase 4.

The support-surface worry resolves the other way once tiers exist: seven providers
behind one interface is *less* surface than one blessed provider plus a stream of
"can I use X" requests, because adding X becomes a class, not a negotiation. And it
makes the §6.7 claim testable rather than rhetorical — Phase 4's second gate runs the
whole benchmark with the paid tier switched off.

### Closed — no Insights importer

Previously listed here as an open question. **Decided: Nakhoda ships no migration path
from Insights**, and the reason is grammar, not law. Reading a file format is legally
fine; the problem is what round-tripping one costs. Insights has 17 operation types and
90 expression functions. §2 refuses the `code` operation outright and caps the function
list at ~25 — those refusals *are* the product thesis. An importer therefore has two
outcomes and both are bad: it is lossy at exactly the workbooks people care about
(anything using a `code` op or one of the ~65 functions Nakhoda declines to ship), or it
forces the grammar back open to stay faithful. The second is Insights with a chat box,
which §5.5 says Metabase already won.

It also inverts the target. An importer optimises for users who already chose the
incumbent and want their old artifacts preserved; Nakhoda's claim is that the artifacts
shouldn't have been hand-built in the first place, because the semantic layer derives
them. The migration story is **re-ask the question**, and Phase 1 is what makes that
cheaper than porting a workbook.

---

## 9. First week

1. Register `github.com/nakhodahq` and PyPI `nakhoda` (`11-naming.md` §4).
2. `bench new-app nakhoda`; commit the layout in §3, a verbatim AGPL-3.0 `LICENSE`, and
   the `license = "AGPL-3.0"` classifier in `pyproject.toml`. Settle §8.1 in the same
   commit — a `CLA.md` and a bot, or a line in `CONTRIBUTING.md` recording that Nakhoda
   is AGPL-only by choice. Either is fine; leaving it blank is how the default gets
   picked for you.
3. Copy `semantic-bench/build.py`, `questions.py`, `grade.py` into `nakhoda/tests/` —
   the benchmark exists already; make it the app's CI from commit one. Add invariant 11's
   shingle check in the same commit: it is ~30 lines, and it is worthless retrofitted —
   its whole job is to fail on the first copied file, not to audit a finished tree.
4. Write the phase-1 generator against `frappe.get_meta()` before writing the engine.
   It is the only part that is genuinely differentiated, and it is the part that tells
   you whether the whole thesis holds on *your* customers' custom DocTypes.
5. Commit `mockup/` and `14-frontend-design.md` into `nakhoda/docs/design/`. It is the
   spec for phases 5, 8 and 10, it opens in a browser with no build step, and left
   outside the repo it will rot into a screenshot nobody trusts. Port its `tokens.css`
   to a frappe-ui `@theme` extension at Phase 5 — **6 additions and 22 overrides**,
   measured by diffing against the shipped `.scss` on 2026-08-12 (light: 69 verbatim /
   7 divergent; dark: 37 / 15). The additions are two grayscale text roles, three
   chromatic text colours and `--font-mono`, and they are non-negotiable: without them
   the mockup fails WCAG AA 87 times in light. The 22 overrides are a decision to make,
   not a value to copy — 15 are the dark `--ink-gray-*` ramp lifted one step for
   metadata-dense screens, 4 are flatter shadows, and the rest are `--text-5xl`,
   `--font-stack` and `--surface-cards`. Take the additions; re-derive the overrides
   against espresso's dark ink before adopting them wholesale.
