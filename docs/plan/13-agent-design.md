# Agent design — Raven's three layers, VS Code's lessons, Nakhoda's openings

Research dossier · 2026-08-11 · for `00-REPORT.md` §6.2
Subject: `Raven 2.8.12` (`/Users/mac/ERPNext/kimcov16/apps/raven`), `openai-agents 0.18.3`,
and `microsoft/vscode-copilot-chat`. Compared against `frappe/insights` @ `ea62bf6`.

---

## 0. Provenance

This file separates what I verified by reading source on this workstation from what a
subagent reported. **Six research agents were dispatched; four fabricated their file
writes** — `13a`, `13b`, `13c` and `13f` were reported as written and do not exist on
disk. Their findings survive only where I re-derived them myself, and every Raven line
number below is from my own read, because subagent line numbers drifted by up to 50
lines against the real files.

| Claim class | How grounded |
|---|---|
| Every `raven/…:line` and `insights/…:line` cite below | Read directly by me |
| `agents 0.18.3` MCP classes | Executed against the installed venv |
| `maxToolCallIterations: 15` | Fetched from the live repo (`defaultIntentRequestHandler.ts:92`) |
| Remaining VS Code detail | `13d-vscode-manager.md`, `13e-vscode-tools.md` (agent-written, 44 and 38 source refs, spot-checked once) |

---

## 1. Manager

Raven's manager is `RavenAgentManager` (`ai/agents_integration.py:43`). It is the live
path for **both** providers — `ai.py:501` comments "Use Agents SDK for both OpenAI and
Local LLM" before calling `handle_ai_request_sync`. The older Assistants-API engine in
`ai/handler.py` is legacy fallback.

| Property | Raven | Cite |
|---|---|---|
| Loop | `Runner.run(agent, full_input, max_turns=5)` | `agents_integration.py:519` |
| Concurrency | async, wrapped `loop.run_until_complete` in a web request | `:786-790` |
| Agent shape | `Agent(name, instructions, model, tools, model_settings)` | `:445-451` |
| Handoffs / sub-agents | **none** — no `handoffs=`, no agents-as-tools | `:445-451` |
| `output_type` | **not set** — free prose only | `:445-451` |
| Guardrails | none: no moderation, no cost cap, no rate limit | grep, `not found` |
| Providers | 2 — OpenAI (`use_responses=True`), Local LLM (`False`) | `:72-90` |

Four things are wrong here in ways that matter to an analytics agent.

**`max_turns=5` is below the floor for analytics.** A grounded NL2SQL turn is
`get_schema → run_query → (error) → repair → run_query → chart` — six calls before a
first answer. Raven aborts at five. VS Code's comparable cap is **15**, and it is
user-extendable when hit (`defaultIntentRequestHandler.ts:92`, verified). A flat
integer is the wrong control anyway: budget by phase (schema 1, generate 1, repair ≤2,
render 1), so a repair loop cannot consume the whole allowance.

**No `output_type` means the SQL is parsed out of prose.** The Agents SDK supports a
typed result. For NL2SQL the return should be a struct — `sql`, `dialect`,
`tables_used`, `assumptions`, `confidence` — not a paragraph the frontend regexes. This
is close to free and it is the difference between a chat toy and an inspectable tool.

**Tool descriptions are hand-injected into the system prompt** (`:398-429`), even though
the SDK already transmits schemas via the API's `tools` parameter. The block duplicates
every tool name and description in prose, then appends behavioural patches like `Do not
use XML tags like <tool_call>` — a workaround for weak local models leaking raw tool
syntax. It burns tokens on every turn and it degrades exactly when the context is
tightest. This is the precise problem `@vscode/prompt-tsx` exists to solve (§4).

**`ModelSettings(temperature=…, top_p=…)`** (`:432`) sets both samplers from bot fields
whose defaults are 1. For SQL generation you want temperature 0; and reasoning models
reject `temperature` outright, which makes the `reasoning_effort` branch at `:435-436`
self-contradictory.

Also dead: `_create_crud_tools` (`:179-281`, ~100 LOC) is defined and never called —
`_setup_tools` uses `create_raven_tools` instead.

### 1.1 Security finding — the AI rewrite lost the sandbox

Raven renders bot instructions as a Jinja template when `dynamic_instructions` is set.
There are two implementations:

| Path | Call | Sandboxed |
|---|---|---|
| Legacy (`handler.py:391`) | `frappe.render_template(bot.instruction, vars)` | **yes** |
| Live (`agents_integration.py:389-391`) | `jinja2.Template(instructions)` | **no** |

Frappe's own renderer builds a `FrappeSandboxedEnvironment(SandboxedEnvironment)` with an
`UNSAFE_ATTRIBUTES` denylist (`frappe/utils/jinja.py:58-66`) and refuses templates
containing `.__` (`jinja.py:137-138`). The live Agents-SDK path imports raw `jinja2` and
gets none of it, so bot instructions are a server-side template injection sink.

Reachability: `Raven Bot` is writable by **`Raven Admin`**, not only `System Manager`
(`raven_bot.json` permissions). A delegated chat administrator should not imply code
execution on the bench.

This is the *same shape* as `00-REPORT.md` §2.3 in Insights: the framework ships a
sandbox, and the AI feature routes around it. Two independent instances in two Frappe AI
apps is a pattern, not a coincidence, and it is the strongest available argument for
Nakhoda's "no in-process execution" invariant. **Report upstream to `frappe/raven`;
the fix is one line — use `frappe.render_template`, which the same repo already uses
correctly a file away.**

---

## 2. Tools

17 built-in function types, declared as an enum on the `Raven AI Function` DocType, all
DocType-shaped: get/create/update/delete/submit/cancel document, get list, get value,
get report result, attach file, plus user-defined custom functions.

**The important property is where permissions come from.** Raven does not implement
permission checking in the tool layer. It gets it for free because every tool bottoms out
in the Document ORM — `doc.check_permission()` and `doc.apply_fieldlevel_read_permissions()`
(`ai/sdk_tools.py:732-733`), and `doc.insert()/save()/delete()` self-check on write.

**That inheritance does not survive the jump to analytics.** An aggregate over 400k
invoices has no `doc` to check. This is the single most important architectural fact in
this dossier: Nakhoda cannot copy Raven's permission model, because Raven's permission
model is "call the ORM".

Insights already solved it, and solved it well — see §3 below. That is a *rebuild
obligation*, not an opportunity.

Three defects worth not inheriting:

- **Tool results are unbounded.** `json.dumps(result, default=str)` (`sdk_tools.py:187`)
  with no size cap, no row limit, no truncation marker anywhere in the file. A 10,000-row
  answer goes straight into the context window. VS Code caps tool results against
  `maxResultTokens` and appends a truncation marker (`13e` §5).
- **`strict_json_schema=False`** (`sdk_tools.py:210`), disabled with the comment "allow
  more flexible schemas". Strict mode is what stops a model inventing parameters.
- **No confirmation step.** Mutating tools execute immediately; there is no
  `prepareInvocation`-style gate. Raven ships delete and cancel tools.

Schema generation from the DocType covers `string / integer / number / float / boolean`
with newline-split enums for strings, and does **not** support nested objects or arrays —
so Frappe's structurally interesting fieldtypes (`Table`, `Link`, `Select`) have no
faithful JSON-Schema representation.

### 2.1 The plugin ceiling is self-inflicted

Raven imports `HostedMCPTool` — OpenAI's server-side MCP — and then strips it, together
with every other hosted tool, whenever the provider is Local LLM
(`agents_integration.py:349-376`). Net effect: **Raven has no plugin story on-prem.**

But the SDK it already depends on ships client-side MCP. Verified by executing against
the installed venv (`agents 0.18.3`):

```
agents/mcp/server.py:1110  class MCPServerStdio
agents/mcp/server.py:1235  class MCPServerSse
agents/mcp/server.py:1375  class MCPServerStreamableHttp
```

Three transports, all client-side, all provider-independent. Raven's air-gap limitation
is an import choice, not a platform constraint. **This directly rescues Nakhoda's Phase 6**
(`12-build-plan.md`), which is aimed at exactly the customers who cannot call OpenAI.

*Measured against `agents 0.18.3` as installed. Do not read the middle line as a
recommendation:* MCP `2026-07-28` deprecates legacy HTTP+SSE on a 12-month offramp, so new
work takes Stdio + Streamable HTTP only. The stateless core also makes self-hosting easier
— no session affinity — which strengthens this row rather than weakening it. See
`12-build-plan.md` Phase 6 for the version floor (`openai-agents >= 0.20.0`, `mcp >= 2.0.0`).

---

## 3. Transcript

Storage is provider-independent on the live path, which is the good news: the Agents-SDK
route sets no `openai_thread_id` and rebuilds history from Frappe rows each turn. Nothing
is stranded in a vendor's thread store.

Everything else is thin.

**A verified bug.** History is fetched as:

```python
messages = frappe.get_all("Raven Message",
    filters={"channel_id": channel.name},
    order_by="creation asc",
    limit=20,  # Limit to last 20 messages for context
)
```
`ai.py:461-476`

`order_by="creation asc"` with `limit=20` returns the **oldest** twenty messages in the
channel, not the last twenty. Under 20 messages the behaviour is correct; past that, the
agent is permanently pinned to the opening of the conversation and never sees recent
turns — while the comment, and every reader, assumes a sliding window. The adjacent
`messages[:-1]  # Exclude the current message` is wrong for the same reason. Fix is
`desc` + reverse. Report upstream alongside §1.1.

**No summarisation, no token budget, no windowing** beyond that integer.

**Tool calls are never persisted.** They stream to the UI as ephemeral `ai_event`
payloads and are dropped; reasoning blocks are stripped before storage. For a chat app
that is defensible. For an analytics agent it is disqualifying: **the SQL is the
artifact.** An answer whose query cannot be reopened is not auditable, not re-runnable,
and not verifiable — which is the entire trust proposition in §6.7 of the main report.

Artifacts exist only as `File` DocType links on a message. There is no durable, re-openable
query or chart object.

---

## 4. What VS Code does differently

From `13d-vscode-manager.md` and `13e-vscode-tools.md`. The four that transfer:

**Priority-based pruning instead of a message count.** `@vscode/prompt-tsx` assigns each
prompt element a `priority`, with `flexGrow`/`flexReserve` for proportional allocation,
and prunes lowest-priority content first when the budget is exceeded. History is
sacrificed before user intent. Raven's `limit=20` is the degenerate version of this: a
fixed count that discards by position rather than by value.

**Summarise on budget overflow, not eagerly.** Compaction triggers on
`BudgetExceededError` and requests a structured multi-section summary rather than free
prose. For Nakhoda the analogue is obvious and better: summarise the *transcript*, but
never the semantic layer or the current SQL.

**Two-phase tool invocation.** `prepareInvocation` returns `confirmationMessages` and an
`invocationMessage` before `invoke` runs, so a destructive tool renders its intent — in
markdown, with code blocks — and waits. This is the natural home for "here is the SQL I
am about to run".

**`modelDescription` vs `userDescription`.** Two descriptions per tool: one written for
the model, one for the human. Raven has one string doing both jobs, which is why its
system prompt is padded with prose that exists to correct model behaviour.

The 128-tool wall and virtual-tool grouping are real but not Nakhoda's problem — a
focused analytics agent should expose well under 20 tools. Deliberately not copying it.

---

## 5. Openings for Nakhoda

Ranked by leverage, with the invariant or cost each one touches.

| # | Opening | Grounded in | Cost |
|---|---|---|---|
| 1 | **Typed `output_type` envelope** — `{sql, dialect, tables_used, assumptions, confidence}` instead of prose | Raven sets none (`:445-451`) | hours |
| 2 | **Persist every tool call as a first-class row** — the SQL *is* the artifact | Raven drops them (§3) | small |
| 3 | **Client-side MCP** (`MCPServerStdio` + `MCPServerStreamableHttp`) → plugins work air-gapped | verified in `agents 0.18.3`; SSE deprecated by MCP `2026-07-28` | small; unblocks Phase 6 |
| 4 | **Bounded tool results** — return a handle + `head(n)` + row count, never the full set | Raven unbounded (`:187`) | small; hard requirement |
| 5 | **Phase-budgeted turns**, not a flat `max_turns` | Raven 5, VS Code 15 | small |
| 6 | **Two-phase invocation showing the SQL before it runs** | VS Code `prepareInvocation` | medium; this *is* the trust surface |
| 7 | **Priority-pruned context** — semantic layer pinned, transcript prunable | prompt-tsx | medium |
| 8 | **`strict_json_schema=True`** from day one | Raven disables it (`:210`) | trivial |

Openings 1–5 and 8 are cheap, and together they are most of the distance between a chat
box and an inspectable analyst.

### 5.1 The correction that matters most

I began this research expecting to find that row-level security on a DuckDB warehouse was
an unsolved opportunity. **It is not.** Insights ships it, and the implementation is the
strongest code in the app:

```python
from_warehouse = isinstance(t.get_backend(), DuckDBBackend)
if from_warehouse:
    # permission query must run against the live site-db (a different backend)
    db = InsightsDataSourcev3.get_doc(data_source)._get_ibis_backend()
    names_expr = ibis.memtable(db.sql(permission_query).select("name"))
else:
    names_expr = t.sql(permission_query).select("name")
return t.semi_join(names_expr, "name")
```
`insights_table_v3.py:356-367`

It applies column permissions via `get_permitted_fields` as an explicit projection
(`:336-347`), applies row permissions as a semi-join, **fails closed** when no permission
query is returned (`:327-328`), handles child tables by unioning across permitted parents,
and correctly notices that the warehouse and the permission source are different backends.

Two consequences for the plan:

1. **This is a rebuild obligation at parity, not a differentiator.** `00-REPORT.md` §6.9
   lists permissions under "rebuild lean". That is wrong — this is the one subsystem where
   lean means insecure. Budget it as the most expensive non-AI component.
2. **The one genuine improvement available** is the `memtable` materialisation on line
   361: a user permitted to see 400k of 1M invoices pulls 400k primary keys into memory on
   every query. Ingesting the permission-determining columns into the warehouse and
   evaluating the filter there would remove the cross-backend round trip. That is a real,
   narrow, honest opportunity — not a new capability.

And it sharpens §3.2 of the main report. The `#919` behaviour has an exact line:

```python
if not _has_where_clause(permission_query):
    return t
```
`insights_table_v3.py:330-331`

Correct when a doctype is genuinely unrestricted; wrong when User Permissions should have
produced a restriction and silently did not. The bug is upstream of this line, but this is
where it becomes invisible.

---

## 6. To report upstream

Both in `frappe/raven`, both on the live path, neither an exploit worth publishing in
detail:

1. **Unsandboxed Jinja in bot instructions** — `agents_integration.py:389-391` should call
   `frappe.render_template`, as `handler.py:391` already does. Writable by `Raven Admin`.
2. **Inverted history window** — `ai.py:474-475`, `order_by="creation asc"` with `limit=20`
   returns the oldest messages, not the newest.

---

## 7. Corrections to subagent output

- Four of six agents reported writing files that do not exist (`13a`, `13b`, `13c`, `13f`).
  Their findings are used here only where independently re-derived.
- Subagent line numbers for `agents_integration.py` drifted ~50 lines high
  (`create_agent` reported at 430, actually 378; jinja at 443, actually 389). All cites
  above are mine.
- `RavenTools` reported the permission risk as "NONE — respects Frappe role model". True
  for DocType CRUD, misleading as a general claim: the guarantee comes from the ORM and
  does not extend to aggregate queries, which is Nakhoda's entire workload.
- `AgentUXPatterns` reported "Raven has NO trust surface (silent SQL execution)". Raven
  does not generate SQL at all; its tools are DocType operations. The absence of a
  confirmation step is real (§2); the SQL framing is not.
