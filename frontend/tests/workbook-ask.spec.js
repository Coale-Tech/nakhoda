import { expect, test } from "@playwright/test";
import { mockBoot } from "./fixtures/data_store.js";
import { mockAgent } from "./fixtures/agent.js";
import { mockWorkbooks, mockSaveAnswer } from "./fixtures/workbooks.js";
import { mockQueryBuilder } from "./fixtures/query.js";

/**
 * Ask, inside a workbook (`components/AskPanel.vue`).
 *
 * The panel is the surface `14-frontend-design.md` §9 was missing: a workbook
 * could hold a saved answer but was not a place to ask for one. Two properties
 * are worth a test rather than an eyeball:
 *
 * - **The save has no target to choose.** `save_answer` must be posted with
 *   `workbook`, never `title` - a panel that created a *second* workbook from
 *   inside one would be the worst possible outcome of pressing Save here.
 * - **The conversation survives the save.** Saving navigates to the query it
 *   created, and the answer that produced it has to still be there afterwards.
 *   That is the whole reason `stores/ask.js` exists, and it is invisible to any
 *   test that never navigates.
 */

const WORKBOOK = "wb-sales";

async function openWorkbook(page, { name = WORKBOOK, tree } = {}) {
	await mockBoot(page);
	await mockWorkbooks(page, tree ? { tree } : {});
	await mockQueryBuilder(page);
	await mockAgent(page);
	await mockSaveAnswer(page, { workbook: WORKBOOK, query: "q-invoices", chart: null });
	await page.goto(`./workbooks/${name}`);
	// The workbook redirects to its first query, so this is the point at which
	// the shell - and its navbar - is really on screen.
	await expect(page.getByText("Revenue by territory").first()).toBeVisible();
}

/**
 * The navbar toggle, scoped to the navbar element. The panel it opens has its own
 * "Ask" button (submit), and frappe-ui takes a Button's accessible name from its
 * visible label (`Button.vue:288`), so the two are separated by where they are.
 *
 * `locator("header")` rather than `getByRole("banner")`: `App.vue` renders routes
 * inside `main`, and a `header` inside `main` carries no landmark role.
 */
function toggle(page) {
	return page.locator("header").getByRole("button", { name: "Ask", exact: true });
}

async function openPanel(page) {
	await toggle(page).click();
	const panel = page.locator(".ask-panel");
	await expect(panel).toBeVisible();
	return panel;
}

async function askInPanel(page, panel, question = "Revenue by territory this quarter") {
	await panel.locator("textarea.composer-input").fill(question);
	await panel.getByRole("button", { name: /^Ask/ }).click();
	await expect(panel.locator(".answer").first()).toBeVisible();
	return panel.locator(".answer").first();
}

test.describe("workbook: ask panel", () => {
	test("the panel is closed until asked for, and the toggle says which", async ({ page }) => {
		await openWorkbook(page);
		await expect(page.locator(".ask-panel")).toHaveCount(0);
		await expect(toggle(page)).toHaveAttribute("aria-pressed", "false");

		await openPanel(page);
		await expect(toggle(page)).toHaveAttribute("aria-pressed", "true");

		// Closing from inside the panel, not only from the navbar: the close
		// button is where a reader's hand already is.
		await page.locator(".ask-panel").getByRole("button", { name: "Close Ask" }).click();
		await expect(page.locator(".ask-panel")).toHaveCount(0);
	});

	test("an answer arrives in the panel with its rows", async ({ page }) => {
		await openWorkbook(page);
		const panel = await openPanel(page);
		const answer = await askInPanel(page, panel);
		await expect(answer.locator('[data-slot="list-row"]').first()).toBeVisible();
		// The builder is still on the left: the panel is beside the workbook,
		// not a screen that replaced it.
		await expect(page.getByText("Revenue by territory").first()).toBeVisible();
	});

	test("saving posts this workbook and opens the query the server named", async ({ page }) => {
		await openWorkbook(page);
		const panel = await openPanel(page);
		await askInPanel(page, panel);

		const [request] = await Promise.all([
			page.waitForRequest("**/api/v2/method/nakhoda.api.workbooks.save_answer**"),
			panel.getByRole("button", { name: "Save to this workbook" }).click(),
		]);
		const body = request.postDataJSON() || {};
		expect(body.workbook).toBe(WORKBOOK);
		// A `title` here would create a second workbook from inside one.
		expect(body.title).toBeUndefined();
		expect(body.agent_run).toBeTruthy();

		// `q-invoices` is what the mocked save returned; the workbook had opened
		// on `q-revenue`, so landing here is the navigation under test.
		await expect(page).toHaveURL(/\/workbooks\/wb-sales\/query\/q-invoices$/);
		await expect(page.getByText("Invoice list").first()).toBeVisible();
	});

	test("the conversation survives the save it triggered", async ({ page }) => {
		await openWorkbook(page);
		const panel = await openPanel(page);
		await askInPanel(page, panel, "Revenue by territory this quarter");

		await panel.getByRole("button", { name: "Save to this workbook" }).click();
		await expect(page).toHaveURL(/\/query\/q-invoices$/);

		// Same panel, same thread - the question and its answer are still there
		// after the route changed under them.
		await expect(page.locator(".ask-panel .answer").first()).toBeVisible();
		await expect(page.locator(".ask-panel")).toContainText("Revenue by territory this quarter");
	});

	test("each workbook keeps its own thread", async ({ page }) => {
		await openWorkbook(page);
		let panel = await openPanel(page);
		await askInPanel(page, panel, "Revenue by territory this quarter");

		// A different workbook, same fixture tree. The thread is keyed by the
		// route's workbook name, so this one has never been asked anything.
		await page.goto("./workbooks/wb-other");
		await expect(page.getByText("Revenue by territory").first()).toBeVisible();
		panel = page.locator(".ask-panel");
		// The toggle is a persisted preference, so the panel is already open.
		await expect(panel).toBeVisible();
		await expect(panel).toContainText("Ask about your data");
		await expect(panel.locator(".answer")).toHaveCount(0);
	});

	test("a reader can ask but is offered no save", async ({ page }) => {
		await mockBoot(page);
		await mockWorkbooks(page);
		await mockQueryBuilder(page);
		await mockAgent(page);
		await page.goto("./workbooks/wb-sales");
		await expect(page.getByText("Revenue by territory").first()).toBeVisible();

		// Re-route the tree as a reader's copy, then reload: `read_only` is read
		// per load (`api/workbooks.py` `as_dict`), never toggled client-side.
		await page.unroute("**/api/v2/document/Nakhoda%20Workbook/**");
		const { WORKBOOK_TREE } = await import("./fixtures/workbooks.js");
		await page.route("**/api/v2/document/Nakhoda%20Workbook/**", (route) =>
			route.fulfill({ json: { data: { ...WORKBOOK_TREE, read_only: 1, can_share: 0 } } }),
		);
		await page.reload();
		await expect(page.getByText("Revenue by territory").first()).toBeVisible();

		const panel = page.locator(".ask-panel");
		if (!(await panel.count())) await openPanel(page);
		const answer = await askInPanel(page, page.locator(".ask-panel"));
		await expect(answer).toBeVisible();
		await expect(page.getByRole("button", { name: "Save to this workbook" })).toHaveCount(0);
	});
});
