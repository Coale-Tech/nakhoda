import { expect } from "@playwright/test";

/**
 * One deterministic answer, served by intercepting the two requests
 * `src/agent.js` makes: `nakhoda.api.agent.ask` and the `Nakhoda Agent Run`
 * audit record it wrote. Phase 5's gates were written against a screen with
 * demo data compiled into it; Phase 6 replaced that with live wiring, so the
 * gates now need a stand-in for the backend. Mocking the transport (not the
 * components, not the turn builder) keeps every assertion below a statement
 * about the shipped build: real `agent.js` mapping, real components, real
 * tokens - only the two HTTP responses are fixed.
 *
 * The payload shape is the contract in `nakhoda/agent/manager.py:ask` plus
 * the fields `nakhoda/nakhoda/doctype/nakhoda_agent_run` persists.
 */
export const RUN_NAME = "NAK-RUN-0001";

export const SQL =
	"SELECT territory, SUM(grand_total) AS total FROM `tabSales Invoice` " +
	"WHERE docstatus = 1 AND territory IN ('Kenya','Tanzania','Uganda') GROUP BY territory";

export const OPERATIONS = [
	{ type: "source", doctype: "Sales Invoice" },
	{ type: "filter", expr: "docstatus == 1" },
	{ type: "summarize", measure: "grand_total", by: "territory" },
];

export const ASK_RESPONSE = {
	columns: ["Territory", "Invoices", "Total"],
	rows: [
		{ Territory: "Kenya", Invoices: 412, Total: 12400000 },
		{ Territory: "Tanzania", Invoices: 208, Total: 6100000 },
		{ Territory: "Uganda", Invoices: 96, Total: 2950000 },
	],
	row_count: 3,
	truncated: false,
	execution_time: 0.412,
	sql: SQL,
	agent_run: RUN_NAME,
};

/** Two columns (label, measure), few enough rows - `nakhoda.agent.charts.pick`'s
 * eligibility shape, so `mockAgent(page, { ask: CHART_ASK_RESPONSE })` renders
 * the `Chart.vue` branch instead of the table one. */
export const CHART_ASK_RESPONSE = {
	columns: ["Territory", "Total"],
	rows: [
		{ Territory: "Kenya", Total: 12400000 },
		{ Territory: "Tanzania", Total: 6100000 },
		{ Territory: "Uganda", Total: 2950000 },
	],
	row_count: 3,
	truncated: false,
	execution_time: 0.412,
	sql: SQL,
	agent_run: RUN_NAME,
	chart: {
		series: [
			{ label: "Kenya", value: 12400000 },
			{ label: "Tanzania", value: 6100000 },
			{ label: "Uganda", value: 2950000 },
		],
	},
};

/** Same shape as `ASK_RESPONSE`, plus `notice` - `nakhoda.engine.pipeline.notice`'s
 * real return shape when a row-level permission excluded rows from the
 * query, so `mockAgent(page, { ask: NOTICE_ASK_RESPONSE })` renders the
 * `PermissionNotice.vue` branch. */
export const NOTICE_ASK_RESPONSE = {
	...ASK_RESPONSE,
	notice: { excluded_count: 47, excluded_amount: "1820000", reason: "territory permissions" },
};

/** Same shape as `ASK_RESPONSE`, plus `injected` - `nakhoda.engine.pipeline.injected`'s
 * real return shape when a row-level permission filter was compiled into the
 * query, so `mockAgent(page, { ask: INJECTED_ASK_RESPONSE })` renders an
 * `origin="injected"` row in the inspector pipeline. */
export const INJECTED_ASK_RESPONSE = {
	...ASK_RESPONSE,
	injected: [{ table: "tabSales Invoice", reason: "territory permissions" }],
};

/** Same shape as `ASK_RESPONSE`, plus `assumptions` - `driver._valid_assumptions`'s
 * real return shape (`nakhoda/bench/driver.py`) once `manager.ask()` validates
 * the model's own `ops_annotated` envelope, so `mockAgent(page, { ask:
 * ASSUMPTIONS_ASK_RESPONSE })` renders `AssumptionsBlock.vue`'s two rows plus
 * the single `AmbiguityPrompt.vue` its `needs_you` entry earns. */
export const ASSUMPTIONS_ASK_RESPONSE = {
	...ASK_RESPONSE,
	assumptions: [
		{ tag: "period", state: "applied", text: "Assumed this fiscal year." },
		{
			tag: "returns",
			state: "needs_you",
			text: "Assumed returns are netted against revenue.",
			counterfactual: "Excluding returns would give \u20b94.34 Cr instead.",
			alt_label: "Exclude returns",
			keep_label: "Keep netted",
		},
	],
};

export const RUN_RESPONSE = {
	name: RUN_NAME,
	source: "generated",
	tier: "standard",
	tier_reason: "grouped aggregate",
	model: "anthropic/claude-3-5-haiku",
	escalated: 0,
	degraded: 0,
	operations: JSON.stringify(OPERATIONS),
	sql: SQL,
	execution_time: 0.412,
};

/** Route both agent endpoints. Call before `page.goto`. */
export async function mockAgent(page, { ask = {}, run = {} } = {}) {
	await page.route("**/api/v2/method/nakhoda.api.agent.ask**", (route) =>
		route.fulfill({ json: { data: { ...ASK_RESPONSE, ...ask } } }),
	);
	await page.route("**/api/v2/document/Nakhoda*Agent*Run/**", (route) =>
		route.fulfill({ json: { data: { ...RUN_RESPONSE, ...run } } }),
	);
}

/** An `ask()` payload with more rows than the answer table renders
 * (`agent.js:PREVIEW_ROWS` = 100). Shaped like the live payload that exposed
 * the need for the cap: a question the pipeline answered with a bare `source`
 * operation, so the whole table came back. */
export function bigAnswer(rowCount = 250) {
	return {
		columns: ["Invoice", "Customer", "Total"],
		rows: Array.from({ length: rowCount }, (_, i) => ({
			Invoice: `SINV-${String(i + 1).padStart(5, "0")}`,
			Customer: `Customer ${i + 1}`,
			Total: (i + 1) * 1000,
		})),
		row_count: rowCount,
		truncated: false,
		execution_time: 0.9,
		sql: SQL,
		agent_run: RUN_NAME,
	};
}

/** Mocked answer on screen, asked the way a user asks it. `ask` overrides the
 * default payload for tests that need a different result shape. */
export async function askQuestion(page, question = "Revenue by territory this quarter", ask = {}) {
	await mockAgent(page, { ask });
	await page.goto("./");
	await page.locator("textarea.composer-input").fill(question);
	// The workbench sidebar also has an "Ask" navigation button; scope the click to the
	// main composer area so the selector is not ambiguous.
	await page.locator("main").getByRole("button", { name: /^Ask/ }).click();
	await expect(page.locator(".answer").first()).toBeVisible();
	await expect(page.locator('.answer [data-slot="list-row"]').first()).toBeVisible();
}

/** Mocked chart-eligible answer on screen - same flow as `askQuestion`, but
 * `ask.chart` makes `Turn.vue` render the `Chart.vue` branch instead of the
 * table one. */
export async function askChartQuestion(page, question = "Revenue by territory this quarter") {
	await mockAgent(page, { ask: CHART_ASK_RESPONSE });
	await page.goto("./");
	await page.locator("textarea.composer-input").fill(question);
	await page.locator("main").getByRole("button", { name: /^Ask/ }).click();
	await expect(page.locator(".answer").first()).toBeVisible();
	await expect(page.locator(".answer .chart").first()).toBeVisible();
}

/** Mocked answer-with-permission-notice on screen - same flow as `askQuestion`,
 * but `ask.notice` makes `Turn.vue` render the `PermissionNotice.vue` branch. */
export async function askNoticeQuestion(page, question = "Revenue by territory this quarter") {
	await mockAgent(page, { ask: NOTICE_ASK_RESPONSE });
	await page.goto("./");
	await page.locator("textarea.composer-input").fill(question);
	await page.locator("main").getByRole("button", { name: /^Ask/ }).click();
	await expect(page.locator(".answer").first()).toBeVisible();
	await expect(page.locator(".answer .perm-note").first()).toBeVisible();
}

/** Mocked answer with an injected-permission pipeline row - same flow as
 * `askQuestion`, but `ask.injected` makes the inspector (once opened) render
 * a read-only `origin="injected"` row alongside the model-authored ones. */
export async function askInjectedQuestion(page, question = "Revenue by territory this quarter") {
	await mockAgent(page, { ask: INJECTED_ASK_RESPONSE });
	await page.goto("./");
	await page.locator("textarea.composer-input").fill(question);
	await page.locator("main").getByRole("button", { name: /^Ask/ }).click();
	await expect(page.locator(".answer").first()).toBeVisible();
	await expect(page.locator('.answer [data-slot="list-row"]').first()).toBeVisible();
}

/** Mocked answer with the model's own assumptions - same flow as
 * `askQuestion`, but `ask.assumptions` makes `Turn.vue` render
 * `AssumptionsBlock.vue` (two rows) and the `AmbiguityPrompt.vue` its
 * `needs_you` row's counterfactual earns. */
export async function askAssumptionsQuestion(page, question = "Revenue by territory this quarter") {
	await mockAgent(page, { ask: ASSUMPTIONS_ASK_RESPONSE });
	await page.goto("./");
	await page.locator("textarea.composer-input").fill(question);
	await page.locator("main").getByRole("button", { name: /^Ask/ }).click();
	await expect(page.locator(".answer").first()).toBeVisible();
	await expect(page.locator(".answer .assumption-list").first()).toBeVisible();
}

/** Open the single reused inspector on the first answer. */
export async function openInspector(page) {
	await page.getByRole("button", { name: /Inspect \d+ steps/ }).click();
	const inspector = page.locator(".inspector");
	await expect(inspector).toBeVisible();
	await expect(inspector.locator(".sql")).toBeVisible();
	return inspector;
}
