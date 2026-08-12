# Copyright (c) 2026, Nakhoda and contributors
# For license information, please see license.txt
"""The benchmark harness: plan, run, grade.

`semantic_bench/` proved a claim once. This runs it again, on demand, against
new questions - the difference between a record and a harness.

Three stages, connected by files in a run directory, because the middle one is
the only one that needs a model and the outer two are the only ones that need a
database:

    plan   questions x arms x targets -> prompts.jsonl      needs the app
    run    prompts.jsonl              -> completions.jsonl  needs a model
    grade  completions.jsonl          -> graded.json        needs the fixture

The seam is not decoration. `semantic_bench`'s generation step was lost because
it ran inside an interactive session and never touched disk; a file between
stages is what makes that impossible here. It also lets the stages run in
different interpreters, which they must: the grammar spec is generated from the
live engine and needs ibis, while generation needs only text and network.

`prompts.jsonl` carries a SHA of each prompt, and `completions.jsonl` carries it
back. Replay is content-addressed, so a changed prompt cannot silently re-use an
old answer - it fails and asks to be regenerated.
"""
