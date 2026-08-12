# Contributing to Nakhoda

## Licence — AGPL-3.0, by choice

Nakhoda is AGPL-3.0. Frappe is MIT, so this was a free choice, not an inherited
obligation. It was made for ecosystem fit and **optionality**, not protection:

- Every app-layer product around Frappe is already copyleft — `erpnext` GPL-3.0,
  `hrms` GPL-3.0, `insights` AGPL-3.0. AGPL is the default expectation for a Frappe
  app. MIT would be the anomaly, and an expensive one, since Frappe Cloud already
  bundles a BI tool from $5/mo.
- Copyleft is worth little as a wall — the source is public and compliance means
  linking to this repo — and a great deal as a negotiating position with anyone who
  wants to embed Nakhoda in something closed.

Be clear about what AGPL does **not** buy: it is no defence against the incumbent
absorbing Nakhoda's ideas, because AGPL code is copy-compatible into other AGPL code.
The moat is shipping the semantic layer first, not the licence.

## The CLA — required, and here is why

**Every contributor signs [`CLA.md`](CLA.md) before their first merge.** This is
stated on day one rather than retrofitted, which is the whole point.

You can only relicense code whose copyright you hold. The right to dual-license
later — to fund the project the way Frappe Assistant Core does, or to go open-core
if a funded competitor appears — dies quietly the moment a single unassigned
contribution lands. AGPL alone leaves exactly one future. AGPL + CLA leaves three
and closes none: stay pure OSS, dual-license, or open-core.

The CLA backlashes people cite — HashiCorp, Elastic, Redis — were all **relicensing
after the fact**, breaking an implied promise. Declared intent from commit one reads
differently. Nothing here revokes your rights: the CLA grants Nakhoda a licence
alongside your own, it does not take your copyright away, and every line stays
AGPL-3.0 in this repo forever.

Sign by opening a PR; the bot will prompt you once.

## Clean room — read Insights, copy none of it

Frappe Insights is AGPL-3.0. Copying it would be *legal* — AGPL to AGPL — and that is
exactly the trap: it is a licence-optionality failure, not a compliance failure. A
dozen lines you do not own means the dual-licence option above is gone, silently,
with no error message.

So the rule is mechanical rather than aspirational:

- Study its architecture freely. Architecture is not copyrightable, and
  `frontend/src2/types/query.types.ts` is the most valuable thing to read before
  writing our own operation grammar.
- Never paste. Never "adapt". Never keep a file open in a second window while typing.
- CI enforces this. `tests/test_clean_room.py` shingles every source file against the
  AGPL trees on the machine and fails the build on any match. It runs on every commit
  because its job is to catch the *first* copied file, not to audit a finished tree.

## No in-process plugin hook

AGPL reaches a derivative work, and a plugin importing Nakhoda's Python in-process is
arguably one. Every plugin runs out-of-process behind MCP (`MCPServerStdio` /
`MCPServerStreamableHttp`) — a boundary chosen for tenancy and trust, which now also
carries the licence, and which lets a customer write a proprietary plugin without the
question arising.

Do not add an in-process plugin hook without reopening this section.

## Working here

- Bench commands run from the bench root, not the app directory.
- Run the bench's pre-commit hooks before committing.
- `CONTEXT.md` is the glossary. Use its terms in code, commits and issues.
- Gates in `docs/plan/` are commands that pass or fail. No phase closes on judgement.
