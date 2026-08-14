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
list (`src/pages/QueriesPage.vue`). The remaining workbench screens are shells.

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
| Bar height ∝ value ±2%, 0px axis drift | **unmet** — `ask()` returns no chart; `Chart.vue` keeps the fixed arithmetic, the gate is `test.fixme` |
| Correct one step and re-run without retyping | **partially met** — the inspector still sets `editable: false` because the inline "Edit & re-run" path is unwired, but a generated pipeline can now be opened in the builder, edited as JSON, and run/saved. The remaining work is typed per-step controls and a round-trip back to Ask. |
| Four origin appearances, pairwise distinct | **unmet** — the audit record reports one origin (`model`); permission filters are inlined at SQL-compile time, never as an `injected` operation |
| Assumptions, ambiguity counterfactual, permission notice | **unmet** — `ask()` returns none of them; the four components exist and are slotted, nothing fills them |

The unmet rows are the honest state of §0's central claim: provenance *is* attached
(operations, realised SQL, tier, model, cost, run id), but the assumption and
permission-exclusion halves of the answer card are still engine work, and the
frontend does not fabricate them client-side.

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
  app.
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

**Status of this section.** Ask, the query builder, and the queries list are now
implemented and covered by the regression suite. The remaining workbench screens
(Dashboards, Workbooks, Data Sources, Data Store, Settings) are still shells.

**Preview caveat.** `yarn serve` uses Vite preview with `base=/assets/nakhoda/frontend/`,
so the SPA mounts at `/assets/nakhoda/frontend/` during preview. `src/router.js` detects
this at runtime (`window.location.pathname` starts with the asset base) and uses the
asset base as the Vue Router history base; otherwise it uses `/nakhoda` for the Frappe
www route. Client-side navigation therefore emits `/assets/nakhoda/frontend/*` URLs in
preview and `/nakhoda/*` URLs in production, so hard refreshes on subpaths work in both
environments.
