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
 * Only fields the backend actually produces are populated. `chart`,
 * `assumptions` and `notice` are left unset - the agent does not compute an
 * auto-picked chart, an assumptions list, or a permission-exclusion count
 * today, and inventing them client-side would show a false explanation next
 * to a real answer. Per-operation `origin` in the inspector pipeline is
 * uniformly "model": `engine/permissions.py` inlines permission filters at
 * SQL-compile time, never as a synthetic step in `operations`, so every real
 * op did come from the semantic-model-grounded generator - there is no
 * "from question" / "link graph" / "injected" distinction to draw honestly
 * per step.
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

function buildTable(columns, rows) {
	const isNumericColumn = columns.map((c) => rows.length > 0 && rows.every((r) => typeof r[c] === "number"));
	return {
		columns: columns.map((c, i) => ({ label: c, align: isNumericColumn[i] ? "num" : undefined })),
		rows: rows.map((r) => ({
			cells: columns.map((c) => ({
				text: r[c] === null || r[c] === undefined ? "\u2014" : String(r[c]),
			})),
		})),
	};
}

function buildInspector(run, ops) {
	if (!run.sql) return undefined;
	return {
		pipeline: ops.map((op) => ({
			kind: op.type,
			origin: "model",
			expr: describeOp(op),
			editable: false,
		})),
		sql: { html: `<span>${escapeHtml(run.sql)}</span>`, plain: run.sql },
		sqlNote: `Compiled from ${plural(ops.length, "operation")}.`,
		scope: [
			{ label: "Tier", value: run.tier_reason ? `${run.tier} \u2014 ${run.tier_reason}` : run.tier || "\u2014" },
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
		table: buildTable(columns, rows),
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
		inspector: isVerified ? undefined : buildInspector(run, ops),
	};

	return {
		id,
		kind: isVerified ? "verified" : "generated",
		question,
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
		url: computed(() => `/api/v2/document/Nakhoda Agent Run/${encodeURIComponent(runName.value)}`),
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
