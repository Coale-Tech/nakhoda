import { computed, ref } from "vue";
import { useCall } from "frappe-ui";

/**
 * Live wiring for the Ask composer against `nakhoda.api.agent.ask`
 * (`nakhoda/agent/manager.py:ask`). Maps its return contract - either
 * `{columns, rows, row_count, truncated, execution_time, sql, agent_run}`
 * or `{error, agent_run}`, `ask()` never raises to its caller - plus the
 * `Nakhoda Agent Run` audit record it wrote (fetched separately: `ask()`'s
 * own return carries no `source`/`tier`/`model`, only the log doc does)
 * into the turn shape `Turn.vue` renders.
 *
 * Both requests go through frappe-ui's `useCall`, which is why this file is a
 * composable rather than a plain async function: `useCall` owns the request
 * lifecycle (loading, error, abort) and sends `X-Frappe-CSRF-Token` /
 * `X-Frappe-Site-Name` itself from `window.csrf_token` - the boot value
 * `www/_nakhoda.py` injects. It replaces this app's former hand-ported
 * `src/callApi.js`, and it speaks the **v2** API (`/api/v2/method/...`,
 * `/api/v2/document/...`) because `useCall` unwraps the v2 `{data: ...}`
 * envelope, not v1's `{message: ...}`. Errors never throw: they land on
 * `.error` as a `FrappeResponseError`.
 *
 * Only fields the backend actually produces are populated. `chart` is left
 * unset - the agent does not compute an auto-picked chart today, and
 * inventing one client-side would show a false explanation next to a real
 * answer. `notice` is populated: `nakhoda.engine.pipeline.notice` (backend)
 * reports it whenever a row-level permission actually excluded something
 * from this exact query, `undefined` otherwise - both a verified and a
 * generated answer can carry one. `injected` is populated the same way,
 * from `nakhoda.engine.pipeline.injected`: one read-only row per table an
 * active permission filter touched, appended to the inspector pipeline
 * with `origin: "injected"` and `editable: false` - never a step in
 * `operations` itself, since `engine/permissions.py` applies the filter at
 * the resolver boundary, not as something a caller could edit or replay.
 * Every *compiled* operation still carries `origin: "model"`: the stored
 * pipeline does not distinguish a step lifted from the question from one
 * the model chose, so there is no "from question" / "link graph"
 * distinction to draw honestly per step yet.
 *
 * `assumptions` is mapped from `ask.assumptions` - `driver._valid_assumptions`
 * (backend) already dropped anything malformed, so this file only reshapes
 * a validated flat list into what `AssumptionsBlock.vue` renders: counts by
 * `state`, one row per entry, and at most one `ambiguity` prompt (the
 * component renders a single counterfactual, so the *first* `needs_you`
 * entry that carries one wins - matching `AmbiguityPrompt.vue`'s one-slot
 * design). `undefined` when the model reported none, verified or generated -
 * a verified answer is never asked for assumptions (`ops_annotated` is a
 * generation-only prompt target, `driver.py`), so `run.source === "verified"`
 * always yields `undefined` here too.
 */

let seq = 0;
function turnId() {
	seq += 1;
	return `t${Date.now()}-${seq}`;
}

function plural(n, word) {
	const count = n ?? 0;
	return `${count} ${word}${count === 1 ? "" : "s"}`;
}

function formatMs(seconds) {
	return `${Math.round((seconds || 0) * 1000)}ms`;
}

function escapeHtml(value) {
	return String(value).replace(
		/[&<>"']/g,
		(c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c],
	);
}

function parseOps(operationsJson) {
	try {
		const ops = JSON.parse(operationsJson || "[]");
		return Array.isArray(ops) ? ops : [];
	} catch {
		return [];
	}
}

function describeOp(op) {
	const { type, ...rest } = op;
	return Object.entries(rest)
		.map(([k, v]) => `${k}: ${JSON.stringify(v)}`)
		.join(", ");
}

/**
 * Rows the answer table renders. `ask()` is capped at 100,000 rows server-side
 * (`engine/operations.py`), and a question the pipeline answers with a bare
 * `source` operation really does come back whole: "How many sales invoices are
 * there?" on this bench returned 3,730 rows x 249 columns, and rendering all
 * 928,270 cells wedged the browser's main thread hard enough to kill the tab.
 *
 * 100 is not a new number: it is `api/data_sources.py:PREVIEW_ROWS`, the bound
 * this app already puts on a table preview. Nothing is hidden by applying it
 * here - the metric above the table reads the payload's own `row_count` and
 * says `truncated` when the engine capped, so the true size is on screen
 * either way, and `total` lets the table say which slice it is showing.
 */
const PREVIEW_ROWS = 100;

/**
 * `displayNames` is `nakhoda.agent.charts.semantics`' second return value -
 * Frappe's own field labels, keyed by column. A `summarize` result names its
 * columns after the expression that produced them (`grand_total`), and the
 * DocType already knows that column is called "Grand Total"; heading the table
 * with the raw name asks the reader to translate. Absent for any column the
 * semantic layer could not resolve, and absent falls back to the raw name
 * rather than guessing a prettier one.
 */
function buildTable(columns, rows, displayNames = {}) {
	const shown = rows.slice(0, PREVIEW_ROWS);
	// Numeric alignment is decided from the rendered slice: it is what a reader
	// can see line up, and scanning 100 rows costs nothing on the main thread.
	const isNumericColumn = columns.map(
		(c) => shown.length > 0 && shown.every((r) => typeof r[c] === "number"),
	);
	return {
		columns: columns.map((c, i) => ({
			label: displayNames[c] || c,
			align: isNumericColumn[i] ? "num" : undefined,
		})),
		rows: shown.map((r) => ({
			cells: columns.map((c) => ({
				text: r[c] === null || r[c] === undefined ? "\u2014" : String(r[c]),
			})),
		})),
		total: rows.length,
	};
}

function buildAssumptions(list) {
	if (!Array.isArray(list) || list.length === 0) return undefined;
	const needsYou = list.filter((a) => a.state === "needs_you");
	const withCounterfactual = needsYou.find((a) => a.counterfactual);
	return {
		applied: list.length - needsYou.length,
		needsYou: needsYou.length,
		rows: list.map((a) => ({ tag: a.tag, state: a.state, html: escapeHtml(a.text) })),
		ambiguity: withCounterfactual
			? {
					counterfactual: escapeHtml(withCounterfactual.counterfactual),
					altLabel: withCounterfactual.alt_label,
					keepLabel: withCounterfactual.keep_label,
				}
			: undefined,
	};
}

function buildInspector(run, ops, injected) {
	if (!run.sql) return undefined;
	return {
		pipeline: [
			...ops.map((op) => ({
				kind: op.type,
				origin: "model",
				expr: describeOp(op),
				editable: false,
			})),
			// Read-only rows for whatever `nakhoda.engine.pipeline.injected`
			// reported - never editable, since the filter was applied at the
			// resolver boundary, not chosen as a step in `operations`.
			...(injected || []).map((entry) => ({
				kind: "permission",
				origin: "injected",
				expr: `${entry.table.replace(/^tab/, "")}: ${entry.reason}`,
				editable: false,
			})),
		],
		sql: { html: `<span>${escapeHtml(run.sql)}</span>`, plain: run.sql },
		sqlNote: `Compiled from ${plural(ops.length, "operation")}.`,
		scope: [
			{
				label: "Tier",
				value: run.tier_reason
					? `${run.tier} \u2014 ${run.tier_reason}`
					: run.tier || "\u2014",
			},
			{ label: "Model", value: run.model || "\u2014", mono: true },
			{ label: "Escalated", value: run.escalated ? run.escalation_reason || "yes" : "no" },
			{ label: "Degraded", value: run.degraded ? run.degradation_reason || "yes" : "no" },
			{ label: "Execution time", value: formatMs(run.execution_time) },
			{ label: "Agent run", value: run.name, mono: true },
		],
	};
}

/** Map one successful `ask()` payload + its audit record into a turn. */
function buildTurn(id, question, ask, run) {
	const isVerified = run.source === "verified";
	const columns = ask.columns || [];
	const rows = ask.rows || [];
	const ops = parseOps(run.operations);
	const rowCount = ask.row_count ?? rows.length;
	// `nakhoda.agent.charts.pick` (backend) decides eligibility from the
	// result shape; `chart` and `table` are mutually exclusive here so the
	// two never render together, matching `Turn.vue`'s own doc comment.
	const chart = ask.chart;
	const notice = ask.notice;
	const injected = ask.injected;
	const assumptions = buildAssumptions(ask.assumptions);

	const answer = {
		icon: isVerified ? "verified" : "sparkle",
		label: isVerified ? "Verified" : "Generated",
		title: isVerified
			? "Matched verified query"
			: `${run.tier || "generated"} tier${run.model ? ` \u00b7 ${run.model}` : ""}`,
		stepCount: ops.length,
		operations: ops,
		metric: {
			value: String(rowCount),
			caption: `${plural(columns.length, "column")} \u00b7 ${formatMs(ask.execution_time)}${
				ask.truncated ? " \u00b7 truncated" : ""
			}`,
		},
		chart: chart ? { series: chart.series } : undefined,
		table: chart ? undefined : buildTable(columns, rows, ask.field_display_names || {}),
		notice: notice
			? {
					excludedCount: notice.excluded_count,
					excludedAmount: notice.excluded_amount,
					reason: notice.reason,
				}
			: undefined,
		assumptions,
		receipt: {
			segments: isVerified
				? [
						{ html: "Verified query" },
						{ html: `<b>${plural(rowCount, "row")}</b>` },
						{ html: `<b>${formatMs(ask.execution_time)}</b>` },
						{ html: `<code class="font-mono">${escapeHtml(ask.agent_run)}</code>` },
					]
				: [
						{ html: `<b>${run.tier || "?"}</b> tier` },
						{ html: run.model ? `<b>${escapeHtml(run.model)}</b>` : "no model" },
						{ html: `<b>${plural(ops.length, "operation")}</b>` },
						{ html: `<b>${formatMs(ask.execution_time)}</b>` },
						{ html: `<code class="font-mono">${escapeHtml(ask.agent_run)}</code>` },
					],
		},
		inspector: isVerified ? undefined : buildInspector(run, ops, injected),
	};

	return {
		id,
		kind: isVerified ? "verified" : "generated",
		question,
		// The audit row's name, hoisted out of the receipt HTML it was only ever
		// rendered into: `save_answer` reads the pipeline from this row rather
		// than from the browser (`api/workbooks.py:save_answer`), so saving an
		// answer means naming the run that produced it.
		agentRun: ask.agent_run,
		trace: {
			summary: isVerified
				? `Matched a verified query \u00b7 ${plural(rowCount, "row")}`
				: `${run.escalated ? "Escalated to" : "Generated with"} ${run.tier || "?"} tier${
						run.model ? ` \u00b7 ${run.model}` : ""
					}`,
			ticks: isVerified ? 0 : ops.length,
			seconds: Number((ask.execution_time || 0).toFixed(1)),
		},
		answer,
	};
}

export function useAsk() {
	// Write-style call: `immediate: false` + `submit(params)` is `useCall`'s
	// canonical shape for anything triggered by a user action.
	const askCall = useCall({
		url: "/api/v2/method/nakhoda.api.agent.ask",
		method: "POST",
		immediate: false,
	});

	// The audit record, read by name once `ask` has returned one. The URL is a
	// computed so `submit()` picks up the name set immediately before it.
	const runName = ref("");
	const runCall = useCall({
		url: computed(
			() => `/api/v2/document/Nakhoda Agent Run/${encodeURIComponent(runName.value)}`,
		),
		immediate: false,
	});

	/** `{}` on any failure, so the turn still renders from `ask`'s own fields. */
	async function fetchRun(name) {
		if (!name) return {};
		runName.value = name;
		const run = await runCall.submit();
		return runCall.error ? {} : run || {};
	}

	async function ask(question) {
		const id = turnId();
		const result = await askCall.submit({ question });
		if (askCall.error) {
			return { id, question, error: askCall.error.message || "Request failed" };
		}
		if (!result) {
			return { id, question, error: "Request failed" };
		}
		if (result.error) {
			return { id, question, error: result.error, agentRun: result.agent_run };
		}
		return buildTurn(id, question, result, await fetchRun(result.agent_run));
	}

	return {
		ask,
		// One flag for the composer: the answer is not on screen until the audit
		// record behind it has been read too.
		pending: computed(() => askCall.loading || runCall.loading),
	};
}

/**
 * The dashboard loop (`nakhoda.api.agent.converse` -> `agent/thread.py`).
 *
 * Deliberately not folded into `useAsk`: `ask()` returns one result and its
 * audit row, while a turn here returns *what the agent did* - a step list, and
 * then exactly one of a report, a patch proposal, or a sentence. Mapping both
 * into one turn shape would mean a component branching on which fields are
 * absent, which is how the two surfaces start lying about each other.
 *
 * No second fetch. `converse` returns the steps it took, so unlike `ask` there
 * is nothing on the persisted row (`Nakhoda Thread Turn`) that the answer
 * needs and the response lacks; `get_thread_turn` exists for reading a turn
 * back later, not for rendering the one just returned.
 */
export function useConverse() {
	const call = useCall({
		url: "/api/v2/method/nakhoda.api.agent.converse",
		method: "POST",
		immediate: false,
	});

	async function converse(question, { dashboard = null, space = null } = {}) {
		const id = turnId();
		const result = await call.submit({ question, dashboard, space });
		if (call.error) {
			return { id, question, error: call.error.message || "Request failed" };
		}
		if (!result) {
			return { id, question, error: "Request failed" };
		}
		return {
			id,
			question,
			threadTurn: result.thread_turn,
			// `steps` is always present, including on a failed turn: the work
			// the loop did before it gave up is the only account of why.
			steps: result.steps || [],
			report: result.report,
			patch: result.patch,
			error: result.error,
		};
	}

	return { converse, pending: computed(() => call.loading) };
}
