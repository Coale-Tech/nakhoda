# Naming decision — Nakhoda

Decision record · 2026-08-11 · status: **decided**
Product: a standalone AI-native analytics app for Frappe/ERPNext. Main report:
`00-REPORT.md` (§6 is the proposal, §6.9 the app boundary). Execution: `12-build-plan.md`.

---

## Decision

**Nakhoda.**

| Surface | Value | State (checked 2026-08-11) |
|---|---|---|
| Primary domain | `nakhoda.io` | free |
| Docs domain | `nakhoda.dev` | free |
| PyPI | `nakhoda` | free |
| npm | `nakhoda` | free |
| GitHub org | `nakhodahq` | free |
| Frappe app module | `nakhoda` | valid Python identifier, no bench collision |

Rejected: `DhowData`, `DataDhow`, bare `Dhow`, `Dhowline`, `Lateen`, `Kaskazi`,
`Sambuk`, `Zaruk`, `Kusi`, `Baghlah`, `Ghanjah`, `Jalbut`.

---

## 1. Why every Dhow candidate is dead

`dhowdata.com` is a **live business-intelligence vendor**. Fetched 2026-08-11, HTTP 200:

> "Modern Big Data BI Software — Dhow Software … Dhow is a BI software provider that
> enables businesses to create detailed reports, analyze data, and make data-driven
> decisions. Through product like **DhowBI**, Dhow helps organizations optimize their
> data collection, reporting, and analysis processes."

Contact number on the page begins `+971` — **UAE**. Same word, same product category,
same region as the strongest ERPNext market.

`DataDhow` does not escape it. It is the transposition of an operating competitor's
domain, in that competitor's category. `DhowBI` is literally their product name.

The rest of the namespace, same day:

| Holder | What | How verified |
|---|---|---|
| `dhowdata.com` | "Dhow Software", product **DhowBI** | HTTP fetch, quoted above |
| PyPI `dhow` | *"A lightweight Python toolkit for building and sharing data workflows"* v0.1.0 | PyPI JSON API |
| npm `dhow` | published package, last modified 2023-06-29 | npm registry API |
| `github.com/dhow` | user account, 7 repos, created 2013-02-17 | GitHub API |
| `kartiknair/dhow` | JSX static-site generator, 80★ | GitHub search API |
| `dhow.com`, `dhow.dev`, `dhow.ai` | all registered | RDAP |
| Dhow Information Systems / "DhowSoft" | Kuwait software vendor, independent entity since 2004 | web search — **not independently verified** |
| Dhow Capital | Kuwait VC, founded 2016 | web search — **not independently verified** |
| `dhow.app` | values-aligned private-market investing | web search — **not independently verified** |

Two of those are direct-category collisions in enterprise data software (`dhowdata.com`,
PyPI `dhow`). The word's cultural resonance across the Indian Ocean trade world is
exactly why every trading house from Mombasa to Kuwait City already uses it.

Secondary defect: **"DhowData" spoken aloud is "Dow Data"** — unspellable from audio and
adjacent to Dow Jones in a data-analytics context.

---

## 2. Why Nakhoda

Keep the dhow. Drop the word. Name the **captain**, not the boat.

**Etymology** (Wiktionary, `en.wiktionary.org/wiki/nakhoda`): English *nakhoda* /
*nacodah*, from Persian **نَاخُدَا** (*nāxodā*), from Classical Persian **نَاوْخُدَا**
(*nāwxudā*) — **nāw** "ship" + **xudā** "lord, master". Borrowed onward into Malay and
Indonesian. The English sense recorded there: *"A travelling merchant in parts of
South-East Asia, in charge of a vessel."*

Four reasons it fits this product specifically:

1. **The metaphor is the thesis.** A nakhoda crossed the monsoon on memorised stars and
   inherited timing, not instruments. §6.0 measured that the entire advantage comes from
   *meaning that was never lost* — DocType metadata Frappe already declares. Naming the
   vessel names infrastructure; naming the navigator names the value.
2. **Merchant *and* navigator.** Someone who knows both the cargo and the route. That is
   precisely an AI analyst embedded in an ERP, not a generic warehouse query tool.
3. **It travels the actual market.** Persian → Arabic → Urdu → Gujarati → Swahili →
   Malay/Indonesian. That is the India ↔ Gulf ↔ East Africa ↔ SEA triangle where
   ERPNext sells.
4. **House style.** Apps on this workstation's benches: `insights`, `raven`, `crm`,
   `hrms`, `mint`, `posnext`, `webshop`, `payments`, `themes`, and `mkaguzi` — Swahili
   for *auditor*. Short evocative nouns, non-English ones already present. **Zero** apps
   named `*data`. `nakhoda` reads native to the ecosystem; `dhowdata` reads like a
   third-party bolt-on.

### Cultural check

Persian permits a mis-parse: نا (*nā-*, negation) + خدا (*khodā*, God) → "godless". This
is a known wordplay, not the ordinary reading. Countervailing evidence: **Nakhoda
Masjid**, completed 1926, is the principal mosque of Kolkata (Wikipedia, verified
2026-08-11). A community does not name its principal mosque with a slur. Treat the pun
as trivia, not a risk.

---

## 3. Measured availability

RDAP for domains; registry APIs for PyPI/npm/GitHub. All checked 2026-08-11.

| Name | .com | .io | .dev | .ai | PyPI | npm | GitHub |
|---|---|---|---|---|---|---|---|
| **nakhoda** | taken | **free** | **free** | taken | **free** | **free** | user taken → `nakhodahq` free |
| lateen | taken | free | free | taken | free | free | taken → `lateenhq` free |
| kaskazi | taken | free | free | taken | free | free | taken → `kaskazihq` free |
| zaruk | — | free | free | — | free | free | taken |
| sambuk | taken | free | free | free | free | free | taken |
| baghlah | — | free | free | — | free | free | **free** |
| ghanjah | — | free | free | — | free | free | **free** |
| jalbut | — | free | free | — | free | free | **free** |
| dhow | taken | free | taken | taken | **taken** | **taken** | **taken** |
| dhowdata | **taken (BI vendor)** | free | free | free | free | free | free |
| datadhow | free | free | free | free | free | free | free |

`.com` and `.ai` being taken for `nakhoda` is acceptable: Frappe itself is `frappe.io`,
and `.io` is the ecosystem's default.

### Honest costs of Nakhoda

- Three syllables; spelling not derivable from sound. Wiktionary lists *nakoda*,
  *nakhuda*, *nachoda* as variants. Budget for typo-domains later, not now.
- `github.com/nakhoda` is an occupied personal account — the org needs a suffix.
- Needs a one-line gloss in the README forever. Every good name does.

### Runners-up, and why not

- **Lateen** — the sail that let dhows sail *against* the wind; strong metaphor, short,
  English-readable. Lost on "reads as Latin / la-teen" and a taken `.ai`.
- **Kaskazi** — Swahili for the NE monsoon that carried dhows to Africa. Distinctive,
  precedent in-ecosystem (`mkaguzi`), but opaque without a paragraph of explanation.
- **Baghlah / Ghanjah / Jalbut** — completely clean across every registry checked,
  including the GitHub org. Rejected anyway: unpronounceable to the target buyer and no
  resonance outside maritime history. A clean namespace is not worth an unsayable name.

---

## 4. Registration order

Gate on the two that actually block distribution — `bench get-app` and `pip` resolve
against GitHub and PyPI:

1. `github.com/nakhodahq` (org)
2. PyPI `nakhoda`
3. `nakhoda.io`, `nakhoda.dev`
4. npm `nakhoda` (frontend package; cheap insurance)

Do not register anything under Dhow.

---

## Verification notes

Directly verified by tool call on 2026-08-11: `dhowdata.com` content and HTTP status;
PyPI/npm/GitHub registry state for every name in the table; RDAP domain status; the
Wiktionary etymology; the Nakhoda Masjid entry; the bench app-name list (`~/ERPNext/*/apps/`).

Reported by web search and **not** independently verified: Dhow Information Systems,
Dhow Capital, `dhow.app`. No trademark-registry search was performed — do that before
any commercial launch; this record covers namespace collision only, not trademark law.
