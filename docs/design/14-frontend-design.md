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

In a real build these become frappe-ui components (`Button`, `Badge`, `ListView`,
`Dialog`) with Tailwind token classes (`text-ink-gray-8`, `bg-surface-gray-1`,
`border-outline-gray-2`). The mockup is hand-written CSS so it opens without a build step;
the class names deliberately mirror the component boundaries. The three text tokens
would land as a small `@theme` extension, not as overrides of espresso's own scale.

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
