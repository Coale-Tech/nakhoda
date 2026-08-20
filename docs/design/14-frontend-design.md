# Nakhoda — frontend design

Design record · 2026-08-11 · mockup in `mockup/index.html` (open in a browser)

Seven screens, light + dark, built on the real Espresso token set. Every colour, radius,
type size and weight in `mockup/tokens.css` is copied verbatim from
`kimcov16/apps/frappe/frappe/public/scss/espresso/*.scss` — no hand-tuned values, so the
mockup is a faithful preview of what frappe-ui would render.

---

## 0. The one design decision

Every competitor — Genie, Metabase AI, changAI, Fabric Data Agent — renders **a chat
bubble with the SQL hidden behind a disclosure triangle**. The answer arrives naked: a
number with no account of how it was reached.

Nakhoda renders **an answer with its provenance attached**. Same question, same number,
but the card also carries:

1. what the agent assumed, itemised and individually correctable,
2. which filters were injected rather than generated,
3. how many rows your permissions removed from the total,
4. what it cost.

This is not decoration. §6.2's non-negotiables (agent emits Operation JSON, never raw
SQL; dry-run before execute; log every turn; run as `frappe.session.user`) are all
*invisible* if the UI does not surface them. A trust guarantee nobody can see is not a
feature. **The provenance strip is what the architecture looks like from the outside.**

---

## 1. The assumption taxonomy is measured, not invented

The assumption rows in the answer card are typed by the **seven trap classes from
`semantic-bench`** (§6.0) — the same taxonomy that produced 78.3% → 95.8%:

| Tag | What the UI states | Measured lift |
|---|---|---|
| `join` | which Link path reached the dimension | +33.3 pp |
| `grain` | invoice grain vs child-table fan-out | +23.8 pp |
| `docstatus` | drafts and cancelled excluded | +20.8 pp |
| `returns` | credit notes in or out | +16.7 pp |
| `display` | code vs display name | +16.7 pp |
| `currency` | `base_` column, so rows are comparable | +11.1 pp |
| `domain` | value came from the Select domain | +6.7 pp |

Two visual states, and the distinction carries the product's honesty:

- **applied** (grey tag) — the semantic model settled it. Factual, low salience.
- **needs you** (amber tag + inline prompt) — *the question was ambiguous*, the agent
  picked a side, and it says so with the counterfactual: “Netting returns off would give
  ₹4.34 Cr.”

That amber state is the direct UI consequence of a bench finding: the questions where
models diverged were the ones whose wording left returns treatment unstated. A product
that silently picks one reading is wrong half the time and never tells you. Surfacing the
fork costs one row of UI and converts the single largest residual error class into a
one-click decision.

Colour carries meaning only where attention is required. Nothing is coloured decoratively.

---

## 2. Screens

| Screen | Carries |
|---|---|
| **Ask** | The answer card. Two paths shown side by side: *generated* (blue chip, assumptions, ambiguity prompt, token cost) and *verified* (green chip, no ambiguity, 0 tokens, 0.1s) |
| **Inspect** (right pane) | Operation pipeline with per-step origin badges; realised dry-run SQL with the injected permission filter highlighted; cost and scope |
| **Semantic Model** | Coverage of the auto-derivation; per-entity grain warnings; the derived `status` domain shown verbatim |
| **Verified Queries** | The trust library — owner, usage count, approval state |
| **Accuracy** | The benchmark gate, by trap class, raw DDL vs with model |
| **Plugins** | Registered MCP servers, transport named per server |

### Why the inspector is a pane, not a modal

Phase 5's gate: *a user can correct one wrong step and re-run without retyping the
question.* A modal forces you to close the answer to see the reasoning, which is exactly
the comparison you need to make. The pane keeps answer and pipeline on screen together.

### Why each operation shows its origin

`FROM QUESTION` / `SEMANTIC MODEL` / `LINK GRAPH` / `INJECTED`. When an answer is wrong,
the first question is always *which layer got it wrong* — the model, the question, or the
schema. The badge answers it before you read the expression.

### The highlighted SQL line

The permission filter is rendered in green, inline, with the note that it was **injected,
not generated**. This is the visual form of `apply_row_permissions` (§3.2). It is also the
answer to issue #919: a user can see the constraint exists.

---

## 3. Three elements no competitor ships

**The permission notice.** *“232 invoices (₹39.2 L) in Germany and Kenya are outside your
territory permissions and are not in this total.”* Every BI tool silently truncates to your
permissions and shows a number that looks complete. Stating the gap is more honest and
strictly more useful — the reader knows whether to ask someone with wider scope. Costs one
row; needs the row-level bridge to exist, which it does.

**The receipt.** `5 operations · 2 tables · 0.4s · 1,204 tokens · $0.0031`. Token cost is
normally hidden from the person spending it. On a self-hosted product the cost line is an
argument in its own right: the verified path shows **0 tokens**, which is the cheapest
possible demonstration that verified queries are worth curating.

**The patch diff.** The Dashboards screen answers *"how does the chat change a
dashboard?"* — the question every AI BI tool ducks. The agent emits a `DashboardPatch`:
`add_chart`, `set_filter`, `remove_item`, each a member of a closed grammar over
`items[]`, dry-run compiled and shown as a diff before it runs. Cards carry their state
in the layout — `will change` (amber rail), `added by patch` (green rail, hatched
forecast bar), `removed by patch` (struck title). An adversarial prompt asking for a
write or a `DROP` fails validation because **the grammar has no op for it**, not because
a filter caught the string. This is `00-REPORT.md` §10 (`DashboardPatch`) and doc 15
Move 3 rendered; the same inspector serves it, retitled.

The screen also carries Move 1 by *omission*. `forecast` appears as step 5 of the
operation pipeline, badged `FROM QUESTION` exactly like `summarize` — no ML surface, no
ML badge, no separate renderer. The 147 `api/ml` endpoints collapse into four members of
the operation union, and the permission filter at step 4 applies to the forecast for
free. A dedicated ML screen would be drawing the architecture the design exists to
delete.

---

## 4. Conformance

Audited against `frappe/public/scss/espresso/*.scss` on 2026-08-12. The counts below
are measured, not asserted — an earlier draft of this section claimed every value was
copied verbatim, and that was false in four places.

- **Colour: 48 of 49 light values verbatim.** Every `--ink-*`, `--surface-*` and
  `--outline-*` in light mode is the shipped espresso value (`--surface-cards` is the
  exception; espresso defines it only for dark). No raw `--gray-*`, and no colour hex
  anywhere outside `tokens.css`.
- **Dark mode diverges deliberately — 15 of 52 values.** The whole `--ink-gray-*` ramp
  is lifted roughly one step (`gray-6` #999999 → #c4c4c4, `gray-8` #d4d4d4 → #e2e2e2,
  and so on). This is a contrast decision, not an oversight: espresso's shipped dark
  ink sits too close to its own dark surfaces for screens this metadata-dense. Dark
  mode therefore does **not** "work with no additional rules" — that claim is withdrawn.
- **Three chromatic text tokens are new**, and they are the only invented colours:
  `--ink-blue-text` #006fcb, `--ink-green-text` #237f53, `--ink-amber-text` #ab5d05.
  Espresso's light ramp contains no chromatic value that clears WCAG AA on white —
  `blue-3` is 4.28:1, `green-3` 4.06, `amber-3` 3.16 — so every coloured label,
  provenance badge and SQL token in the mockup failed by standard. Each new value is
  the minimum HSL-lightness darkening of its espresso parent that clears 4.5:1 against
  *every* surface it lands on (white, `gray-1`, and the `-1`/`-2` tints behind chips,
  where 4.53 is the binding case). Hue and saturation are byte-identical to the parent.
  Text only — backgrounds, borders and fills stay on the shipped `-2`/`-3` values.
- **Four shadows are custom, none verbatim.** Espresso's are tuned for its own
  elevation model; these are flatter and single-layered.
- **Type: 9 of 11 verbatim.** `--text-5xl` is 32px against espresso's 28px, and the
  font stack is shortened to five families. Base 14px, `--weight-regular` 420, all
  four weights verbatim. Tabular numerals on every figure so columns align.
- **Shape: 8 of 8 radii verbatim.** Cards `--border-radius-lg`, controls
  `--border-radius`, chips `--border-radius-full`, `--shadow-sm` on cards only.
- Icons: 16px line icons at 1.7–2.0 stroke, matching the espresso `es-line-*` weight.
- **Accessibility: 0 WCAG AA text failures** across 7 screens × 2 themes. Before the
  two token roles above (`--text-secondary` / `--text-tertiary`, both pinned to
  `gray-6` because espresso's light ramp jumps 4.17 → 7.81 with nothing between) the
  count was 87 in light and 17 in dark.
- **Charts: 0px label drift, ≤1.4% bar error** on all seven screens. Both were real
  defects, found only by measuring the rendered DOM. Bars were `display:flex`, so
  `height:N%` resolved against the column *including* the value label and the tallest
  bar silently rescaled the series (11.4% error); they are now `grid` with the plot
  track at `1fr`. Axis labels were `flex:1` while card bars were pinned to a fixed
  width, so the last label sat 99px right of the bar it named, and `current` overlapped
  `1–30` by 4px; the axis now mirrors the bar track exactly, sized by the widest label.
- **Origin badges: four layers, four appearances.** `LINK GRAPH` was rendering
  identically to `SEMANTIC MODEL` — both `.o-model` — which defeats the badge's whole
  job of naming which layer produced a step. Separated by fill vs outline rather than a
  fourth hue, since §1 reserves colour for attention and provenance is not attention.

The mockup is hand-written CSS so it opens without a build step; the class names
deliberately mirror the component boundaries. That translation has since happened —
see §6 for what the shipped frontend actually renders, which of the claims above
survived contact with the real component library, and which of §5's limits are still
in force.

---

## 5. What the mockup does not claim

- The numbers on **Verified Queries**, **Workbook** and **Plugins** are illustrative,
  though shaped to the real seeded dataset (4,200 invoices, ₹4.61 Cr, the territory set
  from `semantic-bench/build.py`).
- Every figure on **Ask** and **Dashboards** is computed from that seeded DuckDB, not
  invented: ₹62.4 L over 480 permitted invoices, the four-territory bar series, the
  ₹1.60 Cr / 1,034-invoice receivables book, its five ageing buckets, the Apr–Jul
  collections actuals and their trailing-3 forecast, and the 508 invoices (₹82.2 L)
  in Germany and Kenya that permissions exclude. An earlier draft carried a `₹74.61 Cr`
  headline and a `₹2.28 Cr` verified card, both stale; the permission notice claimed
  318 invoices when the real exclusion at that scope is 232.
- Everything on **Accuracy** and **Semantic Model** is a real measurement, and each is
  now reproducible from a named source:
  - Accuracy headline, trap table and gate — `semantic-bench/graded.json`, 40 questions
    × 3 model tiers. All 8 trap rows verified row-for-row. The gate is `≥90.6%`, arm B's
    Wilson 95% lower bound (§6.0), **not** Databricks' 80% — that figure sits inside
    arm A's own CI [70.1, 84.8] and was retired on 2026-08-12.
  - `5.0% described` — a scan of all 528 installed ERPNext DocTypes, 10,413 fields,
    520 with a `description`. Reproduces exactly. The card now states that scope, since
    the screen itself is headed "41 DocTypes" and the figure is ERPNext-wide.
  - `80.6% derived` — 5,862 of 7,277 real fields, where *real* excludes layout
    scaffolding and buttons (the same definition behind `155 real` on the Sales Invoice
    row) and *derived* means the `fieldtype` alone yields schema semantics: a join
    target, a value domain, a grain, a time dimension, or a unit-bearing measure. A
    label without a type gives a name, not semantics, and is excluded — that is the
    19.4% a human still owns, which is the screen's actual argument.
  - Every DocType figure on **Semantic Model** — field, Link, Select and time-dimension
    counts, and the full 13-value `status` domain — is read from the installed
    `*.json` and verified against it.
- **A prior draft of this section warranted a `89% derived` figure as measured.** It was
  not: it appears in no dossier, and no definition of "derivable" reproduces it (labelled
  82.3%, labelled-or-typed 82.4%, typed-over-real 92.3%). It has been replaced by the
  measured 80.6% above, and the mockup now carries the definition on the screen so the
  number cannot come loose from its method again.
- No interaction is wired beyond screen switching, theme, and the inspector. It is a
  design artifact, not a prototype.
- Layout is desktop-only by design: two fixed rails (236px sidebar, 452px inspector)
  set a 688px floor, there are no media queries and no viewport meta. Below ~1024px it
  overflows horizontally. Contrast, unlike layout, **is** claimed — see §4.

---

## 6. The shipped frontend · 2026-08-14

`frontend/` is a Vite + Vue 3 SPA served by `nakhoda/www/_nakhoda.py` at `/nakhoda`.
Two screens are now wired end-to-end — **Ask** (`src/pages/AskPage.vue`) and the
**Query Builder** (`src/pages/QueryBuilderPage.vue`) — plus the **Queries**
list (`src/pages/QueriesPage.vue`). The remaining workbench screens were shells
*as of this section's date*; §8 and §9 record when each was wired, and none
remain.

It is built from **frappe-ui** components and the library's own Tailwind preset, per
`coale_v16/apps/frappe-ui/skills/frappe-ui/` (`SKILL.md`, `COMPONENTS.md`, `TOKENS.md`,
`DESIGN.md`, `SETUP.md`). That replaced this repo's hand-rolled layer wholesale:

- **No design token is declared here any more.** `src/assets/tokens.css`,
  `src/assets/base.css` and the vendored `InterVariable.woff2` are deleted;
  `src/style.css` imports `frappe-ui/style.css` (the preset's `@tailwind` layers +
  the Inter `@font-face`) and `frappe-ui/list-style.css`. Every colour, radius,
  shadow and type value now comes from the published preset, so §4's "48 of 49
  verbatim" accounting is moot — the values *are* the shipped ones, and the three
  invented text tokens are gone (secondary → `text-ink-gray-6`, tertiary →
  `text-ink-gray-5`, chart/metric accents → `text-ink-{green,amber,blue}-*`).
- **No hand-rolled control survives.** `Button`, `Badge`, `Textarea`, `Alert`,
  `KeyboardShortcut`, `Tooltip`; the app frame is `DesktopShell` + `PageHeader` +
  `ScrollArea`; the result table is the `frappe-ui/list` family in table mode
  (`List` + `ListHeader`/`ListHeaderCell` + `ListRows`/`ListRow`/`ListCell`), which
  owns row height, dividers, hover surface and the column tracks. `src/components/
  Icon.vue` + `IconSprite.vue` (the mockup's `<use href="#i-*">` sprite) are deleted:
  icons are the preset's `lucide-*` classes.
- **Data fetching is `useCall`**, not the former hand-written `src/callApi.js`
  (deleted). CSRF still arrives through `jinjaBootData` → `window.csrf_token`, which
  `useCall` sends as `X-Frappe-CSRF-Token`.
- `FrappeUIProvider` wraps the router view so imperative `dialog`/`toast` have a
  portal; `app.use(FrappeUI, { socketio: false })` — nothing here subscribes to
  realtime, and the default opens a socket that retries forever.

### Build pitfalls this migration actually hit

All four are in `SETUP.md`'s checklist; each cost a build:

1. **Tailwind must be v3** with `frappeUIPreset` in `tailwind.config.js` and a
   `postcss.config.js` — v4 silently ignores the preset's shape.
2. **`frappe-ui/list-style.css` is a separate entry.** The family's structural CSS
   (`[data-slot="list-row"] { display: grid }`, the `--list-columns` tracks) is
   imported by the barrel, but that import does not survive this build, so the first
   migrated table rendered every cell stacked while still *looking* like a table.
   `tests/table-geometry.spec.js` now measures `grid-template-columns` and the cell
   boxes so it cannot regress silently.
3. **`optimizeDeps.exclude: ["frappe-ui"]`** (it ships unbuilt source with virtual
   `~icons/lucide/*` imports) plus an explicit `include` for its CJS transitives.
4. **A router must exist** — `Button` injects `Symbol(router)` and warns on every
   render without one. `src/router.js` has routes for Ask, Dashboards, Workbooks,
   Queries, Settings, Data Sources and Data Store; it detects the preview mount path
   (`/assets/nakhoda/frontend/`) at runtime so client-side pushes stay inside the
   Vite preview server, while production keeps the `/nakhoda` base.

### Query builder

- `src/composables/useQuery.js` wraps `useCall` for query CRUD
  (`nakhoda.api.query.*`) and execution (`nakhoda.api.run` / `execute`).
- `src/components/QueryBuilder.vue` displays the engine-format pipeline as
  operation cards, exposes a JSON editor, and runs the pipeline through
  `nakhoda.api.run`. Saving creates or updates a `Nakhoda Query` document and
  navigates to the persisted URL.
- `src/pages/AskPage.vue` adds an **Open in builder** action on generated answers
  that passes the engine pipeline via history state; `agent.js` now keeps the
  raw operations on the turn so the builder can reload them verbatim.
- `tests/query-builder.spec.js` covers the Ask → builder handoff, running a
  pipeline, saving, and the query list; `tests/fixtures/query.js` mocks the
  query endpoints.

### Which gates are measured, and which are recorded as unmet

`frontend/tests/` runs against the **built** app (`vite preview`), never a snapshot.
Phase 5's gates were written against the mockup's compiled-in demo data; live wiring
removed that data, so the suite now drives a real question through a fixture that
mocks only the two HTTP responses (`tests/fixtures/agent.js`) — real `agent.js`
mapping, real components, real tokens.

| Gate | Status |
| --- | --- |
| 0 WCAG AA text failures, light + dark, answer + inspector | **measured** — `contrast.spec.js`, 5 tests |
| Result-table geometry: real grid, equal tracks, aligned numerics | **measured** — `table-geometry.spec.js` |
| Receipt renders unconditionally; SQL one *labelled* action away | **measured** — `provenance.spec.js` |
| Origin badge on every operation, none fabricated | **measured** — `origin-badges.spec.js` |
| No Edit affordance while re-run is unwired | **measured** — `correction.spec.js` |
| Query builder: Ask → builder handoff, run, save, list | **measured** — `query-builder.spec.js`, 4 tests |
| Bar height ∝ value ±2%, 0px axis drift | **measured** — `nakhoda.agent.charts.pick` infers a chart from a two-column, few-row grouped result and `agent.js` maps it onto `turn.answer.chart`; `chart-geometry.spec.js`, 2 tests |
| Correct one step and re-run without retyping | **partially met** — the inspector still sets `editable: false` because the inline "Edit & re-run" path is unwired, but a generated pipeline can now be opened in the builder, edited as JSON, and run/saved. The remaining work is typed per-step controls and a round-trip back to Ask. |
| Four origin appearances, pairwise distinct | **partially met** — `nakhoda.engine.permissions.injected()` (backend) now reports which tables a row-level filter touched; `agent.js:buildInspector` appends a read-only `origin: "injected"` row per entry, distinct from `model` and covered by `origin-badges.spec.js`'s new "injected origin badge" test. `from question` and `link graph` remain unmet — a compiled pipeline still doesn't record whether an operation was lifted from the question or picked by the model, so those two never render in the same screen as the other two (`test.fixme`d). |
| Permission notice: excluded rows and amount | **measured** — `nakhoda.engine.pipeline.notice()` (backend) counts the raw rows a row-level permission removed from the exact query, plus a sum when the pipeline names one unambiguous measure; `permissions.excluded()`/`excluded_resolver()` covered by `tests/test_permissions.py` against the same DuckDB fixture as Gate B (19 tests), the endpoint wiring by `provenance.spec.js`'s "permission notice renders" test |
| Assumptions, ambiguity counterfactual | **measured** — `driver.py`'s `ops_annotated` prompt target asks the model for `{"ops": [...], "assumptions": [...]}` and `_valid_assumptions()` drops anything malformed before `manager.ask()` ever sees it; the response and the `Nakhoda Agent Run` record both carry the validated list (`test_agent.py::Agent`, 3 tests, live). `agent.js`'s `buildAssumptions` reshapes it into what `AssumptionsBlock.vue`/`AssumptionRow.vue`/`AmbiguityPrompt.vue` render — counts by state, one row per entry, and the first `needs_you` entry with a counterfactual fills the single ambiguity slot the component design allows. `provenance.spec.js`'s "assumptions and the ambiguity prompt render with the answer" test, no longer `test.fixme`. |

The remaining unmet work is the honest state of what is left of §0's central claim:
provenance now covers operations, realised SQL, tier, model, cost, run id, the rows
permissions removed, which tables a permission filter touched, *and* the assumptions
and ambiguity counterfactual the model itself reports — only the `from question`/
`link graph` origin split remains open. A compiled pipeline still doesn't record
whether an operation was lifted from the question or picked by the model, so those two
badges never render in the same screen as `SEMANTIC MODEL`/`INJECTED` (`test.fixme`d in
`origin-badges.spec.js`); closing it needs the engine to tag each operation at compile
time, not something the frontend can derive after the fact.

---

## 7. Strategic pivot · full BI workbench · 2026-08-14

The Ask-only frontend above is being expanded to match the surface area of the
incumbent (`nvumabaranda/apps/insights/frontend`). The seven-screen mockup in
`mockup/index.html` is no longer a design artifact; it is the specification. The
current Ask implementation survives as one route inside a larger workbench.

**Why the pivot.** A chat-only shell competes badly against a complete product: users
compare Nakhoda to dashboards, workbooks, and query builders they already have, and the
semantic-layer argument never gets a hearing if the screen does not look like the
category. Metabase already ships Data Studio, Python transforms, documents, MCP and an
Agent API (§5.5) — the differentiator is not the visual surface, it is that Nakhoda's
semantic layer is generated from the application schema. The workbench is the shell
that exposes the generator.

**What changes in the target.**

- A persistent left sidebar: Dashboards, Workbooks, Queries, Ask, Data Sources, Data
  Store, Settings. The sidebar is the primary navigation; Ask is one entry, not the whole
  app. **Shipped 2026-08-15 with two changes to that list** (`components/AppSidebar.vue`):
  the entries are grouped under uppercase labels — *Workbench* (Ask, Dashboards,
  Workbooks, Queries) and *Data* (Data Sources, Data Store) — and Ask leads the first
  group rather than following Queries, because Ask is also the index route (`/`,
  `router.js:37`), so a first-run session lands on the answer card that carries §0's
  argument instead of on an empty dashboard list. Settings is not in either group: it sits
  below a divider with the collapse toggle, and opens a dialog rather than navigating
  (§10's tab lives inside it). Data Store is the one conditional entry, hidden when the
  store is off while its route stays registered, mirroring Insights.
- Pinia stores for dashboards, workbooks, queries, and session state. Local refs in
  `AskPage.vue` are not enough once workbooks and dashboards hold cross-component state.
- A visual query builder that edits the same Operation JSON the agent emits. The
  inspector becomes an editor; generated pipelines can be opened, corrected, and saved
  as workbook queries without retyping the question.
- A chart builder with typed config (dimensions, measures, display options, chart type).
- A workbook container for named collections of queries, charts, and dashboards, with
  sharing, versioning, and export.
- A dashboard grid with filters and widget chrome, reusing the same chart components and
  operation grammar.
- Settings, users, and teams pages that are currently framework-shaped in Insights and
  will be rebuilt with frappe-ui here.

**What does not change.**

- The design system stays `frappe-ui` + the Tailwind preset; no hand-rolled tokens return.
- The operation grammar stays closed: the builder surfaces the same ~25 functions the
  agent is allowed to emit, not an open expression language.
- No in-process Python execution; the only sanctioned code path is an out-of-process
  notebook kernel (Phase 7).
- The agent remains the fastest path to a correct answer. The visual builder must not
  become the primary way to build a query; it is the correction and refinement surface.

**Migration from the current Ask implementation.**

- `App.vue` loses its minimal wrapper and gains the `AppSidebar` + `PageHeader` shell.
- `AskPage.vue` keeps the composer, turn list, and answer card; the "Inspect" button
  now routes to or opens the query builder with the generated pipeline loaded.
- `src/agent.js` and `useAsk` stay unchanged; they already produce the right Operation JSON
  and audit record. The query builder becomes a second consumer of `useCall` and the
  engine endpoints.
- The inspector component is promoted from a read-only slide-out into the operation
  editor's step rail.
- New test fixture scope: the existing `tests/fixtures/agent.js` remains the Ask fixture;
  add fixtures for workbooks, dashboards, and queries that mock the DocType CRUD endpoints.

**Status of this section.** Every screen this section names is now implemented
and covered by the regression suite: Ask, the query builder, the queries list,
Data Sources and Data Store (§8), and Workbooks, Dashboards and Settings (§9).
No shells remain.

**Preview caveat.** `yarn serve` uses Vite preview with `base=/assets/nakhoda/frontend/`,
so the SPA mounts at `/assets/nakhoda/frontend/` during preview. `src/router.js` detects
this at runtime (`window.location.pathname` starts with the asset base) and uses the
asset base as the Vue Router history base; otherwise it uses `/nakhoda` for the Frappe
www route. Client-side navigation therefore emits `/assets/nakhoda/frontend/*` URLs in
preview and `/nakhoda/*` URLs in production, so hard refreshes on subpaths work in both
environments.

---

## 8. Data Sources & Data Store, redesigned to exceed Insights · 2026-08-15

Both screens moved from shell to fully wired, then were rebuilt a second time
against Insights' actual data-source stack rather than a summary of it. The
surface is now four routed pages, four dialogs, one settings tab, three backend
modules (`nakhoda/api/data_store.py`, `nakhoda/api/data_sources.py`,
`nakhoda/api/files.py`, 19 whitelisted endpoints between them), one new DocType
(`Nakhoda Table Import Log`) and a third `source_type` on `Nakhoda Data Source`
(`External Database`), verified end-to-end against a live `jkm` site and in a
real browser (`tests/data-store.spec.js` 15 tests,
`tests/data-sources.spec.js` 18 tests, `nakhoda/tests/test_data_store.py` 23,
`nakhoda/tests/test_data_sources.py` 30).

### The refusal this section used to record, and why it was reversed

An earlier revision of this section argued that Nakhoda *deliberately* had no
external-database connection form: `source_type` was a closed two-value Select
(`Site Database` / `DuckDB Warehouse`), both rows backend-created on demand, and
`data-sources.spec.js` pinned "no external-database connection form" as
regression-tested product behaviour. The stated reason was the boundary
`connectors/__init__.py`'s docstring names - a second, arbitrary outbound
connection the permission layer never checked, which is what made Insights' ML
surface (`api/ml/*`, #919) expensive to secure.

That refusal is withdrawn: `connectors/BACKENDS` already implemented MariaDB,
PostgreSQL and ClickHouse for the *engine*, so the capability existed and only
the way to configure it was missing. A closed Select did not remove the risk, it
removed the audit trail - the same connection could be inserted from the Desk or
a script with no form, no probe and no owner. `source_type` is now a three-value
Select (`External Database` added), and the risk the old paragraph named is
carried by guards instead of by absence:

- **Creation is permissioned and typed.** `create_data_source` requires `create`
  on the DocType, `validate` refuses a `database_type` outside `BACKENDS`, and
  `before_insert` refuses a second row claiming to be the site database or the
  warehouse - those two stay backend-owned.
- **Credentials never round-trip.** `password` lives in Frappe's password store;
  `get_data_source` omits it, so an edit form opens with the box empty and
  `test_connection` fills the stored secret in server-side. A form that omits
  `password` is not asking for it to be cleared.
- **Reads are guarded by the right thing, and say which.** A site-database
  preview runs through `engine.pipeline.run` behind `for_connector`, so it is
  already row- and column-filtered. An external table has no `tabDocPerm` row to
  filter by, so `get_source_table` reads it through the backend's own
  parameterised `table()` catalogue call and claims no row filter - what guards
  it is `read` on the source row, and the docstring says so rather than implying
  a filter that cannot exist. An uploaded CSV takes the same path for the same
  reason. `test_data_sources.py` asserts a reader cannot reconfigure a source,
  cannot import a file, and that a site-database preview is refused - not
  silently emptied - for a DocType the viewer may not read.

### What each screen renders

- **Data Store** (`DataStorePage.vue`) - every DocType the current user can
  read, joined against its `Nakhoda Table` sync row
  (`nakhoda.api.data_store.list_tables`). Unimported DocTypes still appear
  with `sync_state: "Never"`, matching Insights' `DataStoreList` convention
  of showing the full pickable set, not only what has already landed. A
  debounced search box filters by label. `Import`/`Re-sync` opens
  `ImportTableDialog.vue` for a per-table row limit, then **enqueues** -
  see the enqueue section below. The button is admin-only (`create` on
  `Nakhoda Table`), the same split Insights draws with `session.user.is_admin`.
- **Data Sources** (`DataSourcesPage.vue`) - every `Nakhoda Data Source` row:
  the site database, the DuckDB warehouse, and any external database somebody
  connected through the New Source dialog, with `Test Connection`,
  `Set Default`, `Edit Connection` and `Delete` actions, using
  `frappe-ui/list`'s real `List`/`ListRow`/`ListCell` family exactly as the
  Query Builder and Queries list already do, so there is one table
  component in this app, not a bespoke one per screen. Chrome follows
  Insights' `DataSourceList.vue`: `h-12` header, a "Search by Title" box
  above the list (client-side over the loaded rows, as Insights' own
  `filteredDataSources` computed is), then the list. The column set is
  Insights' own, in Insights' order - `Title`, `Status`, `Owner`, `Created`,
  `Modified` - plus one cell of row actions Insights' list has no equivalent
  for (`Set Default`, `Test Connection`), because a `Nakhoda Data Source`
  answers a probe where an Insights source is edited in a detail page. An
  earlier revision of this screen substituted `Tables` and `Last Checked`
  for the last three columns on the argument that nothing here is
  user-created; that was wrong on this app's own data - `create_data_source`
  writes external rows from the New Source dialog, so `owner`, `creation`
  and `modified` differ per row and per install. `Last Checked` did not
  disappear, it moved into the `Status` cell's tooltip, where the badge that
  reports reachability also says when reachability was last established.
  `Owner` renders a frappe-ui `Avatar` plus the owner's full name, resolved
  by `_owner_names` in one `User` read per list call rather than one round
  trip per row (`api/data_sources.py:list_data_sources`). Timestamps render
  relative with the exact stamp on hover (`composables/useTimestamp.js`, the
  same `formatTimeAgo` convention as Insights' `useTimeAgo` in
  `src2/data_source/data_source.ts`): an 11rem cell truncates a Frappe stamp
  to `2026-08-15 16:24:50.78…`, cutting away the part a reader scanning for a
  stale write is actually looking for. On the Data Store list the same cell
  falls back to `—` rather than `Never`, because that row's state badge
  already says `Never`.
- **A source's tables** (`DataSourceTablesPage.vue`, `/data-sources/:name`) -
  ported from Insights' `DataSourceTableList.vue`. The two `source_type`
  values answer differently and that asymmetry is the screen: the site
  database lists every DocType the viewer may read, the warehouse lists only
  what somebody deliberately imported, because a DuckDB table nobody asked
  for does not exist.
- **One table's preview** (`DataSourceTablePage.vue`, `/data-sources/:name/:table`) -
  ported from Insights' `DataSourceTable.vue`, rendered through this app's
  own `DataTable.vue` rather than a second grid component. The rows arrive
  already row- and column-filtered: the endpoint runs them through
  `engine.pipeline.run` behind `for_user`, so a viewer's preview is their
  own slice, not a redacted view of everyone's.
- **Settings › Data Store** (`settings/DataStoreSettings.vue`) - Insights'
  three controls in Insights' order: `Enable`, `Row Limit`, `Memory Limit`.
  `Enable` is a `Toggle` pill switch (`components/Toggle.vue`, wrapping
  frappe-ui's `Switch`) - and so is `Enable AI` on the AI Provider tab, and
  `Fail On Unreadable Columns` on Permissions. One switch shape for every boolean
  in this dialog. Insights is not consistent here: its Data Store and
  Permissions tabs render `<Toggle>` while `AISettings.vue:356` renders a
  `FormControl type="checkbox"` with an `On`/`Off` label, and an earlier
  revision of this app copied that split faithfully - two different controls
  for the same kind of decision, one dialog apart. Copying a house style
  includes not copying its accidents. `tests/settings.spec.js` asserts the
  shape by role (`getByRole("switch")` with `aria-checked`), so a control that
  silently reverts to a checkbox fails rather than merely looks wrong.
  Two earlier mistakes are fixed here and
  regression-tested in `tests/settings.spec.js` ("settings: Data Store"):
  the tab previously omitted the switch entirely (this doc claimed the
  warehouse "is not optional", which stopped being true once
  `data_store.py` grew a gate), and it then hid both caps behind
  `v-if="enable_data_store"`, so an install that had never written the field
  saw one Off control and nothing else - the caps unreachable exactly when
  someone was about to turn the store on.
  `patches/v1_0/data_store_setting_defaults.py` settles all three fields on
  upgrade, and the two rules differ because the values do. The Check is
  written only when its row is *missing*: the backend reads "no row" as on
  (`setting_enabled`), the document API casts it to `0`, and without the patch
  the switch renders off over a store that imports - but a row saying `0` is
  an admin's explicit off and must survive every later `migrate`. The two Int
  caps are written when missing *or* zero, because zero is not a value either
  can hold: a zero row limit imports nothing and a zero memory limit makes
  DuckDB refuse to start, which is why both readers already override it.
  `NakhodaSettings.validate` closes the same hole from the other side -
  clearing a cap box posts `0`, and the coercion turns that into "use the
  default" rather than into a number the page shows and the worker ignores.
  `DEFAULT_ROW_LIMIT` / `DEFAULT_MEMORY_MB` live on the doctype controller so
  the form, the patch and `api/data_store.py` cannot drift.

### The structural change: importing enqueues, it does not copy inline

The first pass copied a table inside the HTTP request. That is fine for
`Currency` and wrong for `Sales Invoice`: a wide ERPNext DocType takes
minutes, and the default 300s gunicorn timeout kills the worker mid-copy,
leaving the row `Syncing` forever with no record of why. Insights does not
do this either - `insights_data_source_v3/data_warehouse.py:85-126` (read on
this bench) enqueues, and this port now matches that shape:

- `import_table` writes a `Nakhoda Table Import Log` row, flips the table to
  `Syncing`, **then** enqueues. Ordering is the contract - a fast worker must
  never load a row still carrying the previous run's state - and
  `test_queueing_opens_a_log_and_marks_the_row_before_handing_over` pins it.
- Concurrency is refused, not queued twice: two writers of one DuckDB table
  is a corrupted table. The guard is `is_job_enqueued(job_id)` **or** an open
  log, because RQ forgets a job the moment its worker picks it up - so
  mid-import the registry looks empty and only the log still says busy.
- `run_import` never raises to the worker; a traceback is not something the
  Data Store page can render. Failures land on the row (`sync_error`) and in
  the log (`output`), which is what the page shows.
- `expire_stale_imports` (hourly) retires logs whose worker never came back.
  Without it a killed worker leaves the table `Syncing` forever and its own
  duplicate guard then blocks every retry - the failure mode that makes a
  table permanently unimportable.
- `sync_stored_tables` (daily) re-copies **only** tables already imported. A
  cron that widened the warehouse would be importing data nobody asked to
  materialise.
- The client polls (`useDataStore.js`) instead of blocking, so a finished
  import lands on screen without a reload, and the poll stops the moment
  nothing is in flight.

Row caps are two-level, ported from Insights' `row_limit`/`memory_limit`
pair: `Nakhoda Settings.max_records_to_sync` site-wide,
`Nakhoda Table.row_limit` per table when an admin types one into the import
dialog. Both are `Int`, so an untouched Single reads `0` - which as a row cap
means "import nothing", not "no cap". Every reader falls back to the shipped
default rather than trusting an unwritten zero.

### Eight real bugs found only by driving both screens against a live site

A static comparison against Insights' components was not enough to call this
"done". The first five surfaced only when the actual import flow ran against
real data in a real browser; the sixth only once the backend had python tests
of its own; the last two only once a real Administrator session drove the
built bundle against this site's 1,103 tables:

1. **`Meta.get_label(fieldname)` missing an argument.** `nakhoda_table.py`'s
   `validate()` called the framework method with no `fieldname`, which
   raised `TypeError` on every `Nakhoda Table` save - the very first import
   ever attempted. Fixed to pass `self.document_type` explicitly, since a
   DocType has no separate display label distinct from its own name.
2. **DuckDB refuses NULL-typed columns on `create_table`.** Wide ERPNext
   DocTypes (e.g. `Sales Invoice`) commonly have optional columns that are
   entirely NULL within the capped row window; `ibis`'s pandas-frame type
   inference then raises `IbisTypeError`. Fixed by passing the *source*
   ibis schema (typed from MySQL's own DDL, never NULL) to `create_table`
   instead of letting it infer from the fetched frame.
3. **A shared `useCall` instance let a stale request clobber a fresh one.**
   `useDataStore.js`'s `list()` reused one `useCall` instance across every
   invocation; typing in the search box while the initial unfiltered load
   was still in flight let the older response's (wrong) result land last.
   Fixed with a request-epoch guard - each `list()` call drops its own
   result once a later call has superseded it - the same class of bug
   `frappe-ui`'s vendored `useCall.ts` does not guard against on its own.
4. **A single global `importing` boolean spun every row's button at once.**
   `DataStorePage.vue` originally read one shared flag; fixed to track
   `importingDoctype` so only the row actually being imported shows the
   spinner, and every other row is merely disabled (not spinning) for the
   duration - `data-store.spec.js`'s per-row isolation test pins this.
5. **`importTable`'s post-import refresh reset an active search filter.**
   `list()` was called with no argument after a successful import, silently
   returning the user to the unfiltered full table list mid-task. Fixed to
   re-list with `lastSearchTerm`, and `data-store.spec.js` covers exactly
   this sequence (filter → import → filter still applied).
6. **`default_source()` could return a row that was not the default.**
   Found by the second pass's python tests, not by the browser. Deleting the
   default `Nakhoda Data Source` row is allowed, so "no row carries the flag"
   is reachable; the fallback branch then elected the surviving row and
   returned it *without writing the flag back*. The engine used it while the
   Data Sources page drew no `Default` badge on anything and
   `list_data_sources`' `is_default desc` sort had nothing to sort by. Fixed
   to promote the row it elects, so the invariant is now: if any source row
   exists, exactly one is default.
7. **The Data Sources page never finished loading.** `list_data_sources`
   took 44s cold and 13s warm, so the page sat on a spinner until Playwright
   gave up - a defect no mocked test could see, because the mock answers
   instantly. The cost was in the shared table list it counts:
   `api/query.list_sources` ran `frappe.db.exists` + `has_permission` +
   `get_meta` **per DocType**, and each `get_meta` builds a DocType's meta
   from the database on a cold cache. Rewritten as set math - one cached
   `frappe.db.get_tables()` sweep, one `DocType` read for names and
   `istable`, one role-permission pass (`get_doctypes_with_read`, with
   Administrator short-circuited exactly as `has_permission` does) - which is
   `0.21s` warm. The narrowing this accepts is deliberate and documented at
   the call site: a DocType reachable *only* because one document was shared
   with the user no longer appears in a table picker, and every read path
   still asks `has_permission` for the specific DocType.
8. **The settings page rendered `0` over a worker using the defaults, and
   the test suite kept putting it back.** Two halves. The rows: three fields
   the Single predated, so `Enable` had no row at all and both caps said `0`
   (`patches/v1_0/data_store_setting_defaults.py`, `NakhodaSettings.validate`
   - see the Settings entry above). The tests: `test_data_store.py` wrote
   `max_records_to_sync` / `max_memory_usage` directly and never restored
   them, and a sibling test's cleanup `commit()` made those writes permanent
   - so every suite run left the site claiming a zero row cap. Both cap
   writes now go through `set_cap`, which snapshots the raw `tabSingles` row
   once per test and restores it as a *deletion* when there was none;
   `set_single_value(..., None)` would store `NULL`, which the page reads
   back as `0`.

### The whitelisted surface

`nakhoda/api/data_store.py` — *movement*: what may be copied, who may copy
it, and what happens to a copy that never comes back.

| Endpoint | Reachable by | Does |
|---|---|---|
| `list_tables(search_term, limit)` | any reader | Every readable DocType joined against its `Nakhoda Table` row |
| `import_table(doctype, row_limit)` | `create` on `Nakhoda Table` **and** `read` on the DocType | Opens a log, marks the row, enqueues |

`run_import` / `sync_stored_tables` / `expire_stale_imports` are worker and
scheduler entry points, deliberately **not** whitelisted: nothing about them
is safe to hand a caller who can choose the arguments.

`nakhoda/api/data_sources.py` — *description*: what sources exist, what each
exposes, and a bounded preview of any one of them.

| Endpoint | Reachable by | Does |
|---|---|---|
| `list_data_sources()` | any reader | The two rows, default first, with per-type table counts |
| `get_data_source(name)` | any reader | Header fields for the drill-down |
| `list_source_tables(name, search_term, limit)` | any reader | Site DB → readable DocTypes; warehouse → imported tables only |
| `get_source_table(name, table)` | `read` on that DocType | `PREVIEW_ROWS` through `for_user`, refused (not emptied) without permission |
| `test_data_source(name)` | `write` | Records reachability on the row rather than raising |
| `set_default_data_source(name)` | `write` | Exclusivity already lives in `NakhodaDataSource.validate` |

Neither module has a create endpoint, and there is no `update_table_links`:
`source_type` is a closed Select and both rows are backend-created.
`test_there_is_no_endpoint_that_creates_an_external_source` asserts the exact
set above, so adding a seventh endpoint to `data_sources.py` fails a test
until someone states the intent.

### Verification

- **Backend, live site:** `nakhoda/tests/test_data_store.py` (16 tests) and
  `nakhoda/tests/test_data_sources.py` (14 tests) run against `jkm`, all
  green. They cover the enqueue ordering contract, the double-click refusal
  (including the RQ-forgets-the-job window), the stale-import sweep and its
  cutoff, the two-level row cap and its unwritten-zero fallback, both
  permission gates, per-source-type table listing, and a preview's
  row-filtering by caller. One test moves real data end to end: MariaDB read
  → DuckDB write → row committed, capped at 5 rows and dropped afterward.
- **Frontend:** full Playwright suite green — 55 passed, 2 skipped, 0
  failed. `tests/data-store.spec.js` (8) and `tests/data-sources.spec.js`
  (8) cover listing, search, the row-limit dialog, the queued→`Syncing`→
  `Synced` poll transition, failure reporting, refusal-is-not-an-error, the
  filter-preserving post-import refresh, the non-admin's missing import
  affordance, both drill-down levels, and a preview the viewer may not read.
  All against mocked endpoints, so the suite runs without a live site.
- **Lint:** `ruff check nakhoda` clean.
- Every row these tests create is deleted afterward, so the site returns to
  its pre-run state.

---

## 9. Workbooks, and an answer that becomes one · 2026-08-15

Workbooks were the last shell. The screen matters less than the thing it makes
possible: a chat answer that lands somewhere durable. Insights' workbook is a
container the analyst fills by hand; here the interesting path starts at Ask,
which is why the save action ships in the same section as the container.

### The container

`Nakhoda Workbook` owns its contents by `Link`, not by child table — queries,
charts, dashboards and folders are separate documents pointing back. Frappe
then enforces the ownership Insights enforces in application code: deleting a
workbook deletes its rows, and nothing leaves a `Nakhoda Dashboard Chart`
orphaned in its own table. Three consequences the tests pin:

- **Undelete rebuilds the tree.** `Deleted Document` snapshots a document's
  children only if the tree is inside it, so `on_trash` writes the snapshot
  before anything is destroyed. `restore_deleted` is a module function, not a
  method (`frappe/core/doctype/deleted_document/deleted_document.py:41`), and
  the restored workbook lands under a **new** autoincrement id — the same
  property Insights has, and the reason no test asserts the old name.
- **A copy is a separate workbook.** `duplicate()` remaps every query
  reference inside `operations` JSON and every chart id inside a dashboard's
  `items` JSON, so the copy reads its own queries. Without the remap the
  duplicate silently reads the original's rows, which is the bug a naive copy
  always ships.
- **Import brings the query with it.** `import_chart` refuses a chart whose
  query lives in another workbook (`nakhoda_chart.py:validate_query_workbook`)
  and therefore copies the query too; `import_query` copies its upstream
  closure. A chart that renders a query the viewer cannot open is a dangling
  reference, not a feature.

`Nakhoda Workbook` is autoincrement-named, so `workbook` is an `int` on an
in-memory document and a varchar on the row. Every comparison in this slice
coerces both sides with `str()`; two of the original test failures were exactly
this mismatch, and they are the reason the coercion is not left implicit.

### Who may read a workbook

`nakhoda/permissions.py` decides which *rows* a caller sees, so the workbook
family needs its own resolver: DocType permissions cannot express "private
until its owner shares it", and Frappe's role permissions have no per-row
notion beyond `owner`. The resolver is registered in `hooks.py` under
`permission_query_conditions` and `has_permission` for all five DocTypes, and
narrows in exactly the direction Frappe intends — hooks are consulted only
after role permissions already allow, so a hook can refuse but never grant.

Reading is `owner` ∪ `DocShare` ∪ organisation-wide; writing is `owner` ∪
`DocShare(write)`. The list endpoint joins `DocShare` and `View Log` in two
batched queries rather than per row, and `get_workbooks` resolves `owner_name`
in one `User` lookup — the same convention `api/data_sources.py` uses, so the
Owner column shows a person rather than a login.

### An answer becoming a workbook

`manager.py` runs one completion per question — there is deliberately no
tool-calling loop (§12-build-plan Phase 4), so "let the agent create a
workbook" would have meant a new architecture. The save is a user action
instead, which is also the honest shape: the analyst decides what is worth
keeping.

`save_answer(agent_run, workbook=None, title=None)` re-reads the audit row and
saves *its* pipeline, never a pipeline the browser posts back. Re-running the
question server-side would double the cost of a save and could return
different rows; trusting the client with the pipeline would let a viewer store
operations the engine never approved for them. Two calls of the same shape —
`workbook` names an existing one, omitting it creates one — because "save this
answer" and "build me a workbook from this answer" are the same intent with a
different target.

The chart travels as its rendered spec (`agent/charts.py:pick` output), not as
a re-derivation: re-deriving server-side would let the saved chart differ from
the one the analyst was looking at. Titles clamp to `TITLE_MAX = 140` (the
`Data` field cap) through `_clamp_title`, which a test caught before a long
question could fail an insert.

### What a saved artifact remembers

`12-build-plan.md` §4 requires the workbook family to record "the semantic-model
version and prompt that produced it", and the first cut of this slice did not —
a query saved from Ask carried its pipeline and nothing about its origin, so
opening it six months later told you what it computed and never what was asked.
`Nakhoda Query.agent_run` closes the half that is reachable today: a `Link` to
the `Nakhoda Agent Run`, which already carries the question, the source
(verified or generated), the tier and the model. A Link rather than three copied
fields, because Frappe then refuses to delete a run an artifact cites — the
account survives as long as the thing it explains.

The link deliberately does **not** travel with a copy (`EXPORT_FIELDS`): the
copy was produced by a copy, and on a cross-site import the named run does not
exist, so carrying it would fail the insert. Three tests hold that shape — set
on save, undeletable while cited, absent on a duplicate.

The semantic-model half was unmet when this slice shipped because the DocType was
not on disk. It is now (§10), and the requirement is still unmet — for a better
reason: `Nakhoda Semantic Model.source_checksum` is per document, and a pipeline
reads a set of them, so there is no single version for an artifact to cite. What
to cite instead is now an open decision with a shape (`12-build-plan.md` §8.3),
not a missing table.

### The builder's own affordances

Ported from `src2/workbook/`: a sidebar holding the workbook's three
collections, and the actions Insights keeps in its navbar.

- **Folders group, they do not parent.** `move_item_to_folder` takes a folder
  document *name* and stores its `title` (`api/workbooks.py`), so
  `WorkbookSidebarSection.vue` renders folders as labels over a flat list. A
  folder with nothing in it still appears, because the folder list drives the
  groups rather than the items' own labels. Three defects the port had to fix
  before it was honest: the drag payload sent the folder *title* as its id, a
  `dragover` on the section root shadowed every folder's drop target, and
  dashboards were offered a reorder the server refuses — `Nakhoda Dashboard`
  has neither `folder` nor `sort_order`, so an `organizable` prop now gates the
  affordance instead of the UI promising what the DocType cannot store.
- **Manage Access is a search, not a client filter.** `list_shareable_users` is
  gated on `share` for *this* workbook and returns the candidates, so the
  dialog never enumerates the user table. An empty result says so in words: a
  search that answers with silence cannot be told from a broken picker, which
  is the one thing a permission dialog must never be ambiguous about.
- **Each action is dropped, not disabled, when it cannot apply.** A reader sees
  no Delete and no Share; `Open in Desk` appears only when
  `boot.has_desk_access`, which the boot payload now carries from
  `User.has_desk_access()` (`frappe/core/doctype/user/user.py:415`) rather than
  from `is_admin` — a Website User following that link gets a 403, and an
  offered link that 403s is worse than a missing one.
- **Cmd+S saves the open query**, matching Insights
  (`src2/workbook/workbook.ts:49`). Bound on the window rather than a textarea,
  and inert unless the query tab is holding unsaved changes.

### Why a Queries page still exists

Insights has no global Queries entry, and the reason is a schema fact rather
than taste: `insights_query_v3.workbook` is `reqd`, so every query is inside a
workbook and the workbook sidebar is the only list that could exist.
`Nakhoda Query.workbook` is optional — the standalone builder can save a query
that belongs to no container — so the page stays, narrowed to exactly those
rows. Asking the question surfaced two defects in the endpoint behind it:

- `list_queries` used `frappe.get_all`, which documents itself as **not**
  checking permissions (`frappe/__init__.py:1383`), so it never reached
  `permissions.get_permission_query_conditions` and listed every other user's
  queries. A title that refuses when clicked is worse than a short list; it is
  `get_list` now.
- It had no `workbook` filter, so every workbook-owned query was listed twice —
  once in its workbook, once here. The filter is `workbook is not set`.

Verified live rather than by inspection: with one filed and one unfiled query
on `jkm`, `/queries` renders only the unfiled one, and the filed one is a row
in its workbook's Queries section.

### Verification

- **Backend, live site:** `nakhoda/tests/test_workbooks.py` (55 tests) green
  against `jkm` — the ownership-by-`Link` guarantees, undelete under a new id,
  duplicate's reference remapping, both import paths, the read/write boundary
  for owner, sharee and outsider, artifact origin, and the save-answer contract
  including the refusal to save a run the caller may not read. `test_api.py` (9)
  additionally proves the endpoint layer is bounded by the caller's own
  permissions and that two callers with different permissions never share a
  cache entry. `test_query.py` (11) pins the list scoping above: a second user's
  query is absent, and a query inside a workbook is not listed twice.
- **Frontend:** full Playwright suite green — **88 passed, 2 skipped, 0
  failed**. `tests/workbooks.spec.js` (17) covers the list's access/views/owner
  columns, title search, the builder's collections and their folders, an unsaved
  draft query, a reader's missing write affordances, the save dialog (existing
  vs new workbook, that it posts the run id and never the pipeline, and that a
  chart answer carries its spec), and the four affordances above: who holds the
  workbook and how the org sees it, the picker's server-named candidates, a
  search matching nobody saying so, a workbook nobody may share offering no
  dialog, Cmd+S saving the open query, and delete returning to the list.
- **Live, real browser:** against `jkm` on port 8052 with an Administrator
  session — created a workbook (`create_workbook` → 586), asked a question
  through the verified path (`ask` → 1,250 customers), saved it (`save_answer`
  → a query under 586), and confirmed the builder then reads `1 query · 0
  charts · 0 dashboards`. The pluralisation in that line is a real fix this
  section shipped: the first live run showed `1 queries`, which no mocked spec
  would have caught. The saved query's `agent_run` resolved to the run carrying
  that exact question with `source: verified`, and deleting the run was refused
  with `LinkExistsError`. Every row created this way was deleted afterwards,
  including the `Deleted Document` snapshot, so the site is back to its
  pre-run state.
  A second live pass exercised the new affordances against real endpoints: the
  actions menu offered Duplicate, Export, Delete and `Open in Desk` with the
  boot flag present, Manage Access round-tripped
  (`list_shareable_users` → `update_share_permissions` → `get_share_permissions`
  reading the grant back) after seeding a second user, and a search for a name
  nobody holds rendered the no-match line rather than an empty panel. The
  `/queries` narrowing was checked the same way, with a filed and an unfiled
  query on the site. Every seeded row — workbooks, queries, users, shares and
  the `Deleted Document` snapshots — was removed afterwards; the site holds one
  pre-existing unfiled query and two pre-existing workbooks, as it did before.
- **Whole backend:** 389 tests, **0 errors**, 6 failures — all six the
  pre-existing accuracy gates below, none in the workbook or query family. An
  earlier run of this suite showed 25 extra errors, all of them permission
  assertions: that was live browser probing writing to the same site *during*
  the run, reproduced deliberately with a concurrent writer and cleaned up. The
  quiet-site number is the one recorded here.
- **Lint:** `ruff check nakhoda` clean.

### The chrome a workbook actually has · 2026-08-15

The first cut of §9 put the builder *inside* the workbench shell. Measured
against Insights in a live browser at 1440×900, that was wrong in every
dimension, so this pass rebuilt the chrome rather than adjusting it.

- **A workbook is a focused surface, not a page in a shell.** Insights renders
  navbar + workbook sidebar and nothing else (`src2/workbook/Workbook.vue`),
  dropping its app sidebar entirely. Both workbook routes are now
  `meta.chromeless` and `App.vue` hides `AppSidebar` for them. The shell was
  spending 224px of a 1440px window on links you are not using while pushing
  the builder's own sidebar off centre.
- **The title lives in the navbar, centred, and is the rename control.**
  `WorkbookNavbar.vue` + a ported `ContentEditable.vue`: `rename` fires on Enter
  or blur and the page turns that into one server call. This replaced a `h-12`
  crumbs header *plus* an inline title input — two chromes for one workbook.
  Read-only is Insights' shield glyph with a tooltip; ours adds `role="img"` and
  an accessible name, which the original lacks.
- **Rows are links.** Every sidebar item and the chart body's "reads" reference
  are `router-link`s over `itemRoute()`, as in Insights. A `button` that calls
  `router.push` cannot be cmd-clicked or opened in a new tab, and a workbook's
  items are exactly the things an analyst wants in two tabs. The Playwright
  locators moved from `getByRole("button")` to `getByRole("link")` to match the
  real DOM.
- **`h-7.5` had to be made to exist.** Insights' rows and inline editors are
  30px. Tailwind's default scale stops defining fractional steps above `3.5`,
  and the frappe-ui preset's gap-filling walks whole integers only, so `h-7.5`
  compiled to *nothing* and every ported row silently collapsed to its content
  height. `tailwind.config.js` now extends `spacing['7.5']`; the built CSS
  carries `.h-7\.5{height:1.875rem}`, byte-identical to Insights'.
- **Copy JSON, not just Export.** Insights' `workbook.ts:281` copies the export
  tree to the clipboard and its list pastes one back. Both exist here now, over
  the same `import_workbook`/`import_query`/`import_chart` endpoints the file
  download already used.
- **The list's columns are Insights' columns.** Title / Access / Views / Owner /
  Modified at 4 / 2 / 1.5 / 2 / 2, with the three access states carrying their
  own glyph — Everyone (building), Private (lock), a named sharee (shield). The
  old cell showed *nothing* for an unshared workbook, which reads as data that
  failed to load. Naming a single sharee needed a backend change:
  `get_workbooks` now resolves sharees through the `_full_names` batch it
  already ran for owners, so the cell shows a person rather than the only login
  printed anywhere on the page.

**Measured, not eyeballed.** Both apps driven live on port 8052 at 1440×900,
reading computed geometry:

| | Insights | Nakhoda |
|---|---|---|
| navbar | 1440×44 at (0,0) | 1440×44 at (0,0) |
| workbook sidebar | 272×856 at (0,44) | 272×856 at (0,44) |
| sidebar row | `<a>`, 30px | `<a>`, 30px |
| section wrappers | `px-3.5 pt-3` — 83/88/88px | `px-3.5 pt-3` — 83/88/88px |
| app sidebar present | no | no |

Suites after the rebuild: **88 passed / 2 skipped / 0 failed** frontend,
`test_workbooks.py` **55 green** (the new one asserts the sharee's name lands on
the row), `ruff check nakhoda` clean.

### Known-failing, not from this slice

`test_bench.py` (3) fails on an accuracy gate: `bench_baseline.jsonl` is 240
recorded completions keyed by prompt hash, and the ops grammar those prompts
were recorded against has since changed, so 120 of them replay as
`no_artifact`. Verified committed-state, not this session's: a throwaway
worktree at `HEAD` produces an identical grammar sha (`4c358cb0eeae`) and an
identical 40/80 key overlap. Re-earning it costs 240 real completions across
three models, which is why it stays a declared known-failing gate rather than
something quietly re-keyed.

`test_retrieval.py` was in this list at 3 failures and no longer is: the
retrieval gate now holds at **11 green**, 8 on the derived layer and 3 on the
curated one (§10).

## 10. The semantic layer as a surface · 2026-08-16

Phase 1's other half is the only screen in this app whose *input* is a person
rather than the site. Everything else here renders what the bench already knows;
this one is where somebody writes down what the schema never says, and retrieval
reads it on the next question. The plan records the measurement
(`12-build-plan.md` §Phase 1: 37/40 → **40/40**, boundary `CURATED=0.75`,
shipped 3.0); this section records the surface.

### What the tab shows, and why each part is there

| Element | Reads | Why it is on screen |
|---|---|---|
| Coverage strip — Documents Used / Modelled / Written By Hand / With Synonyms | `api/semantic.coverage` | Four counts, not a percentage: "428 / 439 modelled" is a fact, "97%" is a claim about what the missing 11 were worth. On this site: 439 / 428 / 0 / 0 at install. |
| List — Document, One Row Is, Rows, Charts, Synonyms, Derived | `api/semantic.list_models` | Ordered by reporting count, the same site-derived prior retrieval ranks with, so the first screen holds the documents whose description is worth writing. |
| `Written` / `Generated` badge | row `curated` | The one bit a curator scans for. Derived in the controller from the checksum, never sent by the client. |
| Editor — Description, Synonyms, per-column Synonyms | `get_model` / `save_model` | Description and synonyms are the two fields retrieval weights; the column grid is where a name like `base_outstanding_amount` gets the word the business uses. |
| Rows / Charts / Never Filled / Schema Cost | the same row | What this document costs the model and how much of it is empty — the reason a curator picks this document over another. |
| Regenerate ▾ — Refresh described / Seed every used document | `api/semantic.regenerate` | Enqueued, never inline: seeding this site is 439 documents in 31s, which is not a thing to hold an HTTP worker open for. The notice says *queued*, not *done*. |

Against §2's promise for this screen — "coverage of the auto-derivation;
per-entity grain warnings; the derived `status` domain shown verbatim" — all
three landed, with the middle one narrowed by what the site can actually assert:
the grain warning is a child table whose `parent_doctypes` came back empty,
flagged on the row and again in the editor, because that is the one grain fact
that makes a document unjoinable rather than merely odd. `Never Filled` carries
the other half of the same warning class. The `status` domain is verbatim in the
editor's read-only column grid, unrendered and untranslated, since a curator
correcting a synonym needs to see the value the database holds.

### Driving it against the live bench found a defect no fixture would have

With the tab open on `jkm` as Administrator, every row's Derived column read
**"in 2 hours"** — a document generated 45 minutes earlier, dated into the
future. The cause is not this tab: Frappe writes naive timestamps in the
*site's* zone (`System Settings.time_zone`, `utils/data.py:388` — `Asia/Kolkata`
here), `new Date("2026-08-16 20:55:54")` resolves them in the *browser's*
(`Africa/Nairobi`), and the 2½-hour difference lands every fresh row in the
future. Data Sources' "Last checked" and the Data Store's "Last synced" read the
same helper and were wrong the same way, unnoticed, since they shipped.

The fix is one boot key and one conversion: `www/_nakhoda.py` sends `time_zone`
(from the cached `System Settings`, so no query), and `useTimestamp.js` walks the
naive string back through that zone's offset at that instant — twice, because the
offset is itself a function of the instant across a DST boundary. A page that
never received the key falls back to browser-local, which is exactly the old
behaviour and correct wherever the two zones agree.

It is a fixture-proof bug, which is why the tests now pin both clocks:
`playwright.config.js` sets `timezoneId: "Africa/Nairobi"` and the fixtures write
timestamps in `SITE_TIME_ZONE = "Asia/Kolkata"`, so "Last checked 2 hours ago"
can only pass if the conversion happens. Before the fix that assertion read "in
30 minutes"; a suite that generated its own timestamps in browser-local terms —
as this one did — could never have caught it.

### Verification

Driven end-to-end in a real browser against a real site (`127.0.0.1:8000`,
minted Administrator session), not a mock:

| Path | Observed |
|---|---|
| Tab renders live | 439 / 428 / 0 / 0, 428 rows, `Sales Invoice` first at 30 charts, `GL Entry` 71,024 rows |
| Write a synonym | badge `Generated` → `Written by hand`, Save re-disabled, coverage strip 0 → 1 on both counts **without a reload** |
| Persisted | `Nakhoda Semantic Model.Sales Invoice` = `revenue, turnover, sold, billings`, `curated: 1`, and `curation.synonyms()` returns it (cache invalidated by the controller's `on_update`) |
| Retrieval reads it | for "Which item sold the most units, excluding returns?" `Sales Invoice` ranks **first**; its curated terms are `['bill', 'revenu', 'sold', 'turnover']`, and `sold` appears nowhere in its schema |
| Clear it again | badge back to `Generated`, `curated: 0`, site left at 0 curated rows |
| Regenerate | notice "Queued: re-deriving every described document."; worker log shows `nakhoda.api.semantic.run_regenerate` (`jkm||nakhoda-semantic-sync`) **completed in 33.9s**, all 428 rows preserved |

Suites: `semantic.spec.js` **13 green**, the four settings/data specs **59
green** together (two new ones on the timezone path), `test_curation.py` **14
green**, `test_retrieval.py` **11 green** (8 derived + 3 curated), full backend
**408 tests, 3 known failures** — all three `test_bench.py`, above. `ruff
format` / `ruff check nakhoda` clean.

## 11. Ask inside a workbook · 2026-08-16

Ask is the app's index route and the surface every product argument rests on
(§0), so "can it live inside a workbook?" is a question about where the
*conversation* lives, not about moving a component.

### Why a panel, and why not a fourth item type

Three shapes were available. **A conversation as a fourth `itemType`** was
rejected: `itemType` is a closed enum (`query | chart | dashboard`,
`router.js`), `Nakhoda Agent Run` is per-turn with no workbook link, and a
persisted in-workbook thread is the first step toward "let the agent create a
workbook" — a different architecture, worth arriving at deliberately rather
than as a side effect of moving a composer. **A sidebar rail** was rejected on
geometry the chrome work already measured (§9): the workbook sidebar is the
only list that could exist, and the builder spends 224px of a 1440px window on
chrome as it is. What ships is **a right-hand panel in the builder**
(`components/AskPanel.vue`, 452px, `border-l`), toggled from the navbar, in the
space the inspector already occupies on Ask.

Nothing server-side was added: `api/workbooks.py:save_answer` already takes a
workbook name and reads the pipeline from the `Nakhoda Agent Run` row rather
than from the browser, so a workbook-scoped save inherits that guarantee
unchanged.

### The store exists because saving navigates

§7 predicted this ("local refs in `AskPage.vue` are not enough once workbooks
and dashboards hold cross-component state") and the save path is where the
prediction lands: keeping an answer navigates to the query it just created, so
a thread living in the component that navigated away dies one keystroke after
the user asked to keep it. `stores/ask.js` holds one thread **per scope** —
`"ask"` for the route, `workbook:<name>` for each workbook — so two workbooks
are two conversations and neither inherits the other's history.

It is **memory-only, deliberately**. Turns hold result rows already filtered by
the asker's permissions; `localStorage` is readable by every script on the
origin and survives logout, so persisting a thread would park
permission-filtered rows outside the permission system. The panel's *open* flag
is a preference and is persisted (`nakhoda:workbookAskOpen`); the answer is not.

Two pieces were extracted rather than copied, since a second copy of either is
a place for the two surfaces to drift: `composables/useSaveAnswer.js` (the
write) and `components/AskComposer.vue` (textarea + submit guard).

### Two accessible-name collisions the DOM decided

The navbar toggle and the panel's submit button are both labelled "Ask", and
frappe-ui derives a Button's accessible name from its visible label
(`Button.vue:288`) — an `aria-label` override is dead code there. Fixed at the
source instead: `WorkbookNavbar.vue` is now a `<header>` (the element
`AskPage.vue` already uses), so the two are told apart by the region they sit
in. It is not a `banner` landmark — `App.vue` renders routes inside `main`, and
a `header` inside `main` carries no landmark role — so the spec scopes to
`locator("header")`, not `getByRole("banner")`.

### The live bench found a defect that wedged the browser

Asked "How many sales invoices are there?" against `jkm`, the panel worked and
the tab **died** — three times, before the cause was measured rather than
guessed. The pipeline answered that question with a bare `source` operation, so
`ask()` returned the whole table: 3,730 rows × 264 columns. `DataTable.vue`
rendered every one — 984,720 `ListCell` components — and wedged the main thread
past recovery.

The guard belongs at the shaping boundary, because the frontend has to survive
whatever shape the pipeline emits: `agent.js:buildTable` now renders
`PREVIEW_ROWS = 100`. That is not a new number — it is
`api/data_sources.py:PREVIEW_ROWS`, the bound this app already puts on a table
preview. Nothing is hidden: the metric above the table reads the payload's own
`row_count`, and the table states the slice ("Showing the first 100 of 3730
rows."), because a table showing 100 of 3,730 rows without saying so is a wrong
answer rather than a shortened one.

No fixture would have caught it — every answer mock in the suite is three rows.
`table-geometry.spec.js` now drives a 250-row payload and asserts the rendered
count is 100, the footer names both numbers, and the metric still reads 250.

### Verification

Driven end-to-end in a real browser against a real site (`127.0.0.1:8000`,
minted Administrator session), not a mock:

| Path | Observed |
|---|---|
| Toggle in the navbar | panel 452px, flush right at a 1440px viewport; open flag survived a reload |
| Ask a live question | `Nakhoda Agent Run oag3pv7s8b` / `095amlrbji`, `status: ok`, `source: verified`, 2.4s — the real agent, not a fixture |
| The render cap | 100 rows / 26,400 cells (was 3,730 / 984,720); footer "Showing the first 100 of 3730 rows."; metric still `3730 · 264 columns` |
| Page stays alive | `evaluate` returns promptly where the same question previously killed the tab worker |
| Save to this workbook | `Nakhoda Query 0qm0j18d95` created in workbook `1575`, titled with the question, `agent_run` linked, `data_source: Site Database` |
| The app followed | navigated to `/nakhoda/workbooks/1575/query/0qm0j18d95`; sidebar lists it; the panel stayed open with its answer intact |

Suites: `workbook-ask.spec.js` **6 green**, `table-geometry.spec.js` **2
green**, full frontend **110 passed / 2 skipped / 0 failed**.
