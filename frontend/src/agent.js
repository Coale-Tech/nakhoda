import { call } from "./callApi.js";

/**
 * Live wiring for the Ask composer against `nakhoda.api.agent.ask`
 * (`nakhoda/agent/manager.py:ask`). Maps its return contract - either
 * `{columns, rows, row_count, truncated, execution_time, sql, agent_run}`
 * or `{error, agent_run}`, `ask()` never raises to its caller - plus the
 * `Nakhoda Agent Run` audit record it wrote (fetched separately: `ask()`'s
 * own return carries no `source`/`tier`/`model`, only the log doc does)
 * into the turn shape `Turn.vue` renders.
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
	return String(value).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
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

/** Fetch the audit record `ask()` wrote; `{}` on any failure so the turn
 * still renders from `ask`'s own fields alone. */
async function fetchRun(name) {
	if (!name) return {};
	try {
		return await call("frappe.client.get", { doctype: "Nakhoda Agent Run", name });
	} catch {
		return {};
	}
}

export async function askQuestion(question) {
	const id = turnId();
	let ask;
	try {
		ask = await call("nakhoda.api.agent.ask", { question });
	} catch (e) {
		return { id, question, error: e.messages?.[0] || e.message || "Request failed" };
	}
	if (ask.error) {
		return { id, question, error: ask.error, agentRun: ask.agent_run };
	}

	const run = await fetchRun(ask.agent_run);
	const isVerified = run.source === "verified";
	const columns = ask.columns || [];
	const rows = ask.rows || [];
	const ops = parseOps(run.operations);
	const rowCount = ask.row_count ?? rows.length;

	const answer = {
		icon: isVerified ? "verified" : "sparkle",
		label: isVerified ? "Verified" : "Generated",
		title: isVerified ? "Matched verified query" : `${run.tier || "generated"} tier${run.model ? ` \u00b7 ${run.model}` : ""}`,
		stepCount: ops.length,
		metric: {
			value: String(rowCount),
			caption: `${plural(columns.length, "column")} \u00b7 ${formatMs(ask.execution_time)}${ask.truncated ? " \u00b7 truncated" : ""}`,
		},
		table: buildTable(columns, rows),
		receipt: {
			segments: isVerified
				? [
						{ html: "Verified query" },
						{ html: `<b>${plural(rowCount, "row")}</b>` },
						{ html: `<b>${formatMs(ask.execution_time)}</b>` },
						{ html: `<code class="mono">${escapeHtml(ask.agent_run)}</code>` },
					]
				: [
						{ html: `<b>${run.tier || "?"}</b> tier` },
						{ html: run.model ? `<b>${escapeHtml(run.model)}</b>` : "no model" },
						{ html: `<b>${plural(ops.length, "operation")}</b>` },
						{ html: `<b>${formatMs(ask.execution_time)}</b>` },
						{ html: `<code class="mono">${escapeHtml(ask.agent_run)}</code>` },
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
				: `${run.escalated ? "Escalated to" : "Generated with"} ${run.tier || "?"} tier${run.model ? ` \u00b7 ${run.model}` : ""}`,
			ticks: isVerified ? 0 : ops.length,
			seconds: Number((ask.execution_time || 0).toFixed(1)),
		},
		answer,
	};
}
