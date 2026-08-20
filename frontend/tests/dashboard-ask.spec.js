import { expect, test } from "@playwright/test";
import { mockBoot } from "./fixtures/data_store.js";
import {
	CHART_RUN,
	DASHBOARD,
	PATCH_TURN,
	THREAD_TURN,
	VERSION,
	mockDashboard,
} from "./fixtures/dashboards.js";

/**
 * The agentic dashboard surfaces (`docs/plan/16-agentic-dashboards.md` §3):
 * panels that fetch their own rows, the Ask panel that spends a loop turn, the
 * `chart://` citation a report re-executes on read, and the approval screen a
 * patch has to pass through.
 *
 * Four properties here are claims this build makes and cannot check any other
 * way - the Python gates prove the *endpoints* behave, and prove nothing about
 * whether the browser ever reaches them:
 *
 * - **Every panel is its own execution.** The grid must issue one `panel_data`
 *   per panel, keyed on `i`; the shipped defect was a grid keyed on
 *   `panel.id` - a field that never existed - so Vue reused one DOM node for
 *   all of them (§2 defect 3).
 * - **Nothing is applied until approved.** A proposal on screen must have made
 *   zero `apply_dashboard_patch` requests. That is a statement about a request
 *   that must *not* exist, so only a counting fixture can make it.
 * - **Approval links the turn.** `apply_dashboard_patch` must carry
 *   `thread_turn`, or the audit trail from a change back to the sentence that
 *   proposed it is broken (`api/dashboards.py`).
 * - **A citation degrades in place.** A `chart://` run the reader may not read
 *   must leave the prose around it intact - the reason a report cites a run
 *   instead of embedding a snapshot.
 */

const QUESTION = "Which account moved most this quarter?";

async function openDashboard(page) {
	await mockBoot(page);
	await page.goto(`./dashboards/${encodeURIComponent(DASHBOARD)}`);
	// The metric strip is the first thing `get_dashboard_data` fills, so this is
	// the point at which the page - and its Ask toggle - is really on screen.
	await expect(page.getByText("Net Movement", { exact: true }).first()).toBeVisible();
}

/** The header toggle, scoped to the header: the composer's own submit button
 *  carries the same label, and both are on screen once the panel is open. */
function toggle(page) {
	return page.locator("header").getByRole("button", { name: "Ask", exact: true });
}

async function openPanel(page) {
	await toggle(page).click();
	const panel = page.locator("aside.dashboard-ask");
	await expect(panel).toBeVisible();
	return panel;
}

async function ask(page, panel, question = QUESTION) {
	await panel.getByPlaceholder("Ask about this dashboard…").fill(question);
	await panel.getByRole("button", { name: "Ask", exact: true }).click();
	await expect(panel.getByText(question)).toBeVisible();
}

test.describe("dashboard: panels", () => {
	test("each panel fetches and draws its own rows", async ({ page }) => {
		const calls = await mockDashboard(page);
		await openDashboard(page);

		// Two panels, two identities, two executions - not one node reused.
		await expect(page.locator("[data-panel]")).toHaveCount(2);
		await expect(page.locator('[data-panel="panel_1"]')).toBeVisible();
		await expect(page.locator('[data-panel="panel_2"]')).toBeVisible();
		await expect.poll(() => calls.panel).toBe(2);

		// Vega renders to canvas; a drawn chart is the only proof the rows
		// survived the semantic-type handoff into `flint-chart`.
		await expect(page.locator('[data-panel="panel_1"] canvas')).toBeVisible();
	});
});

test.describe("dashboard: ask", () => {
	test("a turn shows what it did before what it concluded", async ({ page }) => {
		const calls = await mockDashboard(page);
		await openDashboard(page);
		const panel = await openPanel(page);

		await expect(panel.getByText("Ask about this dashboard", { exact: true })).toBeVisible();
		await ask(page, panel);

		await expect.poll(() => calls.converse).toBe(1);
		// The loop's own step records, in order, above the report they produced.
		const steps = panel.locator("ol li");
		await expect(steps).toHaveCount(2);
		await expect(steps.first()).toContainText("Movement by account this quarter — 3 rows");
		await expect(steps.nth(1)).toContainText("Wrote a report");
		await expect(panel.locator(".report-prose").first()).toContainText(
			"Sales leads on movement",
		);
	});

	test("a chart:// citation is re-executed under the reader", async ({ page }) => {
		const calls = await mockDashboard(page);
		await openDashboard(page);
		const panel = await openPanel(page);
		await ask(page, panel);

		const cited = panel.locator(`.report-chart[data-agent-run="${CHART_RUN}"]`);
		await expect(cited).toBeVisible();
		await expect(cited.locator("canvas")).toBeVisible();
		// One request, made on read - not a snapshot the report was carrying.
		await expect.poll(() => calls.chart).toBe(1);
		// The prose on both sides of the citation is still there.
		await expect(panel.locator(".report-prose")).toHaveCount(2);
	});

	test("a citation the reader may not read leaves the prose standing", async ({ page }) => {
		await mockDashboard(page, { chartFails: true });
		await openDashboard(page);
		const panel = await openPanel(page);
		await ask(page, panel);

		const cited = panel.locator(`.report-chart[data-agent-run="${CHART_RUN}"]`);
		await expect(cited).toContainText("Not permitted");
		await expect(panel.locator(".report-prose").first()).toContainText(
			"Sales leads on movement",
		);
		await expect(panel.locator(".report-prose").nth(1)).toContainText(
			"Payroll is the smallest",
		);
	});
});

test.describe("dashboard: patch approval", () => {
	test("a proposal changes nothing until it is approved, and links its turn", async ({
		page,
	}) => {
		const calls = await mockDashboard(page, { turn: PATCH_TURN });
		await openDashboard(page);
		const panel = await openPanel(page);
		await ask(page, panel, "Filter accounts to Sales");

		const patch = panel.locator(".patch");
		await expect(patch).toContainText("Proposed change");
		await expect(patch).toContainText("Changed");
		await expect(patch).toContainText("Movement by Account");
		await expect(patch).toContainText("filters");
		// On screen, itemised, and not applied.
		expect(calls.apply).toBe(0);

		await patch.getByRole("button", { name: "Apply", exact: true }).click();
		await expect(patch).toContainText("Applied to this dashboard");
		await expect(patch).toContainText(VERSION);
		expect(calls.apply).toBe(1);
		// The audit link back to the sentence that proposed the change.
		expect(calls.appliedTurn).toBe(THREAD_TURN);

		await patch.getByRole("button", { name: "Undo", exact: true }).click();
		await expect(patch).toContainText("Proposed change");
		await expect.poll(() => calls.revert).toBe(1);
	});
});
