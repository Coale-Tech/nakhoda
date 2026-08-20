import { expect, test } from "@playwright/test";
import { mockBoot } from "./fixtures/data_store.js";
import { WORKBOOK_TREE, mockSaveAnswer, mockWorkbooks } from "./fixtures/workbooks.js";
import { askQuestion, mockAgent } from "./fixtures/agent.js";

/**
 * The workbook container: a list, one open workbook's sidebar, and the write
 * that puts a chat answer into it.
 *
 * Item selection is asserted through the *URL*, not through which panel is
 * visible: `save_answer` returns `{workbook, query}` and Ask links straight at
 * that query, so a route that does not encode the open item silently breaks
 * that link while every panel still looks right.
 */

async function openList(page, overrides = {}) {
	await mockBoot(page);
	await mockWorkbooks(page, overrides);
	await page.goto("./workbooks");
	await expect(page.getByRole("button", { name: "New Workbook" })).toBeVisible();
}

async function openWorkbook(page, overrides = {}) {
	await mockBoot(page);
	await mockWorkbooks(page, overrides);
	await page.goto("./workbooks/wb-sales");
	// Rows are links, not buttons: an item's destination is a route, so it must
	// be openable in a new tab. Insights' sidebar rows are `router-link` too.
	await expect(page.getByRole("link", { name: "Revenue by territory" })).toBeVisible();
}

function sidebarSection(page, label) {
	return page.locator("aside section").filter({ hasText: label });
}

test.describe("workbook list", () => {
	test("lists workbooks with their owner, views and share state", async ({ page }) => {
		await openList(page);

		const sales = page.locator("[data-slot='list-row']").filter({ hasText: "Sales Review" });
		const ops = page.locator("[data-slot='list-row']").filter({ hasText: "Ops Weekly" });

		// Views and access are the two columns that only make sense on a shared
		// install - `get_workbooks` computes both per row. Access names a single
		// sharee and says `Everyone` for an org-wide grant, matching Insights:
		// one reader, eleven, and everybody are three different facts.
		await expect(sales.getByText("12")).toBeVisible();
		await expect(sales.getByText("Reader User")).toBeVisible();
		await expect(ops.getByText("Everyone")).toBeVisible();
		// The owner is read per row, not printed from the session, so a workbook
		// somebody else owns says their name.
		await expect(ops.getByText("Reader User")).toBeVisible();
	});

	test("creating a workbook opens the new one", async ({ page }) => {
		await openList(page);

		await page.getByRole("button", { name: "New Workbook" }).click();
		await expect(page).toHaveURL(/workbooks\/wb-new/);
	});

	test("filters the list by title", async ({ page }) => {
		await openList(page);

		await page.getByPlaceholder("Search by title").fill("Ops");
		await expect(page.locator("[data-slot='list-row']").filter({ hasText: "Ops Weekly" })).toBeVisible();
		await expect(page.locator("[data-slot='list-row']").filter({ hasText: "Sales Review" })).toHaveCount(0);
	});
});

test.describe("workbook builder", () => {
	test("sidebar carries all three collections and its folders", async ({ page }) => {
		await openWorkbook(page);

		// The folder is a grouping label, not a parent row: the query inside it
		// is listed under it, and the folder itself is a `Nakhoda Folder`.
		await expect(sidebarSection(page, "Queries").getByText("Drafts")).toBeVisible();
		await expect(sidebarSection(page, "Queries").getByRole("link", { name: "Invoice list" })).toBeVisible();
		await expect(sidebarSection(page, "Charts").getByRole("link", { name: "Revenue bars" })).toBeVisible();
		await expect(sidebarSection(page, "Dashboards").getByRole("link", { name: "Weekly board" })).toBeVisible();
	});

	test("opening an item puts it in the URL", async ({ page }) => {
		await openWorkbook(page);

		await page.getByRole("link", { name: "Revenue bars" }).click();
		await expect(page).toHaveURL(/workbooks\/wb-sales\/chart\/c-revenue/);
		// The chart says which query it reads - a chart whose query is a mystery
		// cannot be trusted, and `add_chart` guarantees the query is in here. The
		// sidebar carries the same title, so this scopes to the body's own link.
		await expect(
			page.getByRole("paragraph").getByRole("link", { name: "Revenue by territory" }),
		).toBeVisible();
	});

	test("a dashboard renders the charts its tiles name", async ({ page }) => {
		await openWorkbook(page);

		await page.getByRole("link", { name: "Weekly board" }).click();
		await expect(page).toHaveURL(/workbooks\/wb-sales\/dashboard\/d-weekly/);
		// The tile names a chart by `name`; the title shown is the chart's own.
		await expect(page.locator(".grid").getByText("Revenue bars")).toBeVisible();
	});

	test("a new query is an unsaved draft until it has a source", async ({ page }) => {
		await openWorkbook(page);

		await sidebarSection(page, "Queries").getByRole("button", { name: "Add Queries" }).click();
		await expect(page).toHaveURL(/workbooks\/wb-sales\/query\/new/);
		// `validate_pipeline` refuses a pipeline with no source, so Save is
		// unavailable rather than a click that throws.
		await expect(sidebarSection(page, "Queries").getByText("unsaved")).toBeVisible();
		await expect(page.getByRole("button", { name: "Save" })).toBeDisabled();
	});

	test("a reader gets no write affordances", async ({ page }) => {
		await openWorkbook(page, { tree: { ...WORKBOOK_TREE, read_only: 1 } });

		// Read-only is a shield in the navbar, as in Insights - asserted by its
		// accessible name, which is the only thing a reader without hover gets.
		await expect(page.getByRole("img", { name: "Read only" })).toBeVisible();
		await expect(sidebarSection(page, "Queries").getByRole("button", { name: "Add Queries" })).toHaveCount(0);
		await expect(page.getByRole("button", { name: "Save" })).toHaveCount(0);
	});

	test("manage access lists who holds the workbook and how the org sees it", async ({ page }) => {
		await openWorkbook(page);

		await page.getByRole("button", { name: "Share" }).click();

		const dialog = page.getByRole("dialog");
		await expect(dialog.getByText("Reader User")).toBeVisible();
		// Organisation access is one control with three states, not a checkbox:
		// `update_share_permissions` stores it as a single `everyone` row.
		await expect(dialog.getByText("Organization access")).toBeVisible();
	});

	test("the share picker offers candidates the server named", async ({ page }) => {
		await openWorkbook(page);
		await page.getByRole("button", { name: "Share" }).click();

		const dialog = page.getByRole("dialog");
		// A search, not a client filter over every user: `list_shareable_users`
		// is gated on `share` for *this* workbook and returns the candidates.
		await dialog.getByLabel("Search people").fill("Edit");
		await dialog.getByRole("button", { name: "Search" }).click();

		await expect(dialog.getByText("Editor User")).toBeVisible();
	});

	test("a search that matches nobody says so", async ({ page }) => {
		await openWorkbook(page, { candidates: [] });
		await page.getByRole("button", { name: "Share" }).click();

		const dialog = page.getByRole("dialog");
		await dialog.getByLabel("Search people").fill("Ghost");
		await dialog.getByRole("button", { name: "Search" }).click();

		// An empty result and an unrun search render identically unless the
		// dialog records that it asked: silence here reads as a broken picker.
		await expect(dialog.getByText(/Nobody matches “Ghost”/)).toBeVisible();
	});

	test("a workbook nobody may share offers no dialog", async ({ page }) => {
		await openWorkbook(page, { tree: { ...WORKBOOK_TREE, can_share: 0 } });

		// An editor added by someone else holds `write` without `share`: a button
		// that 403s on open is the failure this answers.
		await expect(page.getByRole("button", { name: "Share" })).toHaveCount(0);
	});

	test("deleting the workbook returns to the list", async ({ page }) => {
		await openWorkbook(page);
		const deletes = [];
		page.on("request", (r) => {
			if (r.method() === "DELETE") deletes.push(r.url());
		});

		await page.getByRole("button", { name: "Workbook actions" }).click();
		await page.getByRole("menuitem", { name: "Delete" }).click();
		await page.getByRole("dialog").getByRole("button", { name: "Delete" }).click();

		await expect(page).toHaveURL(/\/workbooks$/);
		expect(deletes.length).toBe(1);
	});

	test("cmd+s saves the open query instead of the page", async ({ page }) => {
		await openWorkbook(page);
		const saves = [];
		page.on("request", (r) => {
			if (r.url().includes("save_query")) saves.push(r.url());
		});

		await page.getByRole("link", { name: "Invoice list" }).click();
		await expect(page.getByRole("button", { name: "Save" })).toBeVisible();
		// Opening a saved query reads it; the write must come from the shortcut,
		// so a zero here is what makes the count below mean anything.
		expect(saves.length).toBe(0);

		await page.keyboard.press("ControlOrMeta+s");

		await expect.poll(() => saves.length).toBe(1);
	});
});

test.describe("saving an answer", () => {
	test("an answer offers to become a workbook", async ({ page }) => {
		await mockBoot(page);
		await mockWorkbooks(page);
		await mockSaveAnswer(page);
		await askQuestion(page);

		await page.getByRole("button", { name: "Save to workbook" }).click();
		// The existing-workbook branch is offered first when there are any: the
		// common case is filing into a board that already exists.
		await expect(page.getByRole("dialog").getByText("Sales Review")).toBeVisible();

		await page.getByRole("dialog").getByText("Sales Review").click();
		await page.getByRole("dialog").getByRole("button", { name: "Save" }).click();

		// The saved answer's own link, not a toast that vanishes.
		await page.getByRole("button", { name: "Open", exact: true }).click();
		await expect(page).toHaveURL(/workbooks\/wb-sales\/query\/q-saved/);
	});

	test("saving posts the run id, never the pipeline", async ({ page }) => {
		await mockBoot(page);
		await mockWorkbooks(page);

		let body = null;
		await page.route("**/api/v2/method/nakhoda.api.workbooks.save_answer**", (route) => {
			body = route.request().postDataJSON();
			return route.fulfill({ json: { data: { workbook: "wb-new", query: "q-saved" } } });
		});

		await askQuestion(page);
		await page.getByRole("button", { name: "Save to workbook" }).click();
		await page.getByRole("dialog").getByRole("button", { name: "New workbook" }).click();
		await page.getByRole("dialog").getByRole("button", { name: "Save" }).click();
		await expect(page.getByRole("button", { name: "Open", exact: true })).toBeVisible();

		// `save_answer` re-reads operations from the audit row, so a save cannot
		// store SQL nobody saw. If the client ever starts posting `operations`,
		// that guarantee is gone and this fails.
		expect(body.agent_run).toBeTruthy();
		expect(body.operations).toBeUndefined();
		expect(body.sql).toBeUndefined();
	});

	test("a chart answer carries its chart spec", async ({ page }) => {
		await mockBoot(page);
		await mockWorkbooks(page);

		let body = null;
		await page.route("**/api/v2/method/nakhoda.api.workbooks.save_answer**", (route) => {
			body = route.request().postDataJSON();
			return route.fulfill({ json: { data: { workbook: "wb-sales", query: "q-saved", chart: "c-saved" } } });
		});

		const { CHART_ASK_RESPONSE } = await import("./fixtures/agent.js");
		await mockAgent(page, { ask: CHART_ASK_RESPONSE });
		await page.goto("./");
		await page.locator("textarea.composer-input").fill("Revenue by territory");
		await page.locator("main").getByRole("button", { name: /^Ask/ }).click();
		await expect(page.locator(".answer .chart").first()).toBeVisible();

		await page.getByRole("button", { name: "Save to workbook" }).click();
		await page.getByRole("dialog").getByText("Sales Review").click();
		await page.getByRole("dialog").getByRole("button", { name: "Save" }).click();
		await expect(page.getByRole("button", { name: "Open", exact: true })).toBeVisible();

		// Presentation JSON travels because it is what was rendered; re-deriving
		// it server-side would let the saved chart differ from the answer.
		expect(body.chart).toBeTruthy();
	});
});
