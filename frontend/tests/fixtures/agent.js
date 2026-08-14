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

/** Mocked answer on screen, asked the way a user asks it. */
export async function askQuestion(page, question = "Revenue by territory this quarter") {
	await mockAgent(page);
	await page.goto("./");
	await page.locator("textarea.composer-input").fill(question);
	// The workbench sidebar also has an "Ask" navigation button; scope the click to the
	// main composer area so the selector is not ambiguous.
	await page.locator("main").getByRole("button", { name: /^Ask/ }).click();
	await expect(page.locator(".answer").first()).toBeVisible();
	await expect(page.locator('.answer [data-slot="list-row"]').first()).toBeVisible();
}

/** Open the single reused inspector on the first answer. */
export async function openInspector(page) {
	await page.getByRole("button", { name: /Inspect \d+ steps/ }).click();
	const inspector = page.locator(".inspector");
	await expect(inspector).toBeVisible();
	await expect(inspector.locator(".sql")).toBeVisible();
	return inspector;
}
