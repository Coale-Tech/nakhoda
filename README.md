<div align="center">

# Nakhoda

**The only BI tool that already knows what your data means, because the application defined it.**

An AI-native analytics platform for Frappe and ERPNext.

</div>

---

## The idea

Every text-to-SQL tool starts from the same handicap: a warehouse schema is a pile of
tables and column types, so the model has to *infer* what the business meant. Which
rows are real transactions and which are abandoned drafts. Which money column is
comparable across currencies. What a "customer" is when three tables mention one.

A Frappe application already answers all of that, in metadata it maintains anyway.
Every DocType declares its fields, labels, link targets, select domains, child-table
grain and submit semantics. Nakhoda reads that with `frappe.get_meta()` and derives a
semantic layer from it — no hand-authored YAML, no modelling project, no drift.

We measured the difference before writing the app. Same 40 questions, same models,
one variable — raw DDL versus the derived semantic layer:

| Context | Execution accuracy |
|---|---|
| Raw DDL, as a warehouse sees it | 78.3% |
| Derived from DocType metadata | **95.8%** |

+17.5 points, McNemar exact _p_ = 1.9e-05. The harness is in
[`nakhoda/tests/semantic_bench/`](nakhoda/tests/semantic_bench/) and reproduces from
scratch. A *small* model with the layer beat a frontier model without it, which is
the whole argument in one line: this is a metadata problem, not a model problem.

## What makes it different

**It shows its work.** Every answer arrives with its assumptions, the rows your
permissions removed, and the SQL that will run — visible before execution, not behind
a disclosure triangle. Competitors render a chat bubble and hide the query.

**The agent cannot write SQL.** It emits structured operations from a closed grammar,
which is what makes an answer inspectable, correctable and safe. Coverage was measured
before the constraint was adopted: all 40 benchmark questions need just 7 operations.

**Permissions are structural.** The agent runs as you, never elevated. Row filters are
injected into the compiled query, not requested in a prompt.

**Three things we refuse to build**, because each one quietly turns this back into a
query builder with a chat box:

- no in-process code execution — no `code` operation, no Python cell, ever
- no 90-function expression language — every admitted function is surface a model can
  get wrong
- no drag-and-drop pipeline builder — we build the *correction* surface, not the
  *construction* surface

## Status

Early. Phase 0 of the plan in [`docs/plan/`](docs/plan/), which is public because the
research behind it is worth more than the head start it gives away. Every phase closes
on a gate that is a command, not a judgement call.

## Licence

AGPL-3.0. Contributions require signing the [CLA](CLA.md) — see
[`CONTRIBUTING.md`](CONTRIBUTING.md) for why, and for the clean-room rule CI enforces
on every commit.
