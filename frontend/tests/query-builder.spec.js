import { expect, test } from "@playwright/test";
import { askQuestion } from "./fixtures/agent.js";
import { mockQueryBuilder, runQuery, saveQuery, OPERATIONS } from "./fixtures/query.js";

test.describe("query builder", () => {
	test("a generated pipeline from Ask opens in the builder", async ({ page }) => {
		await mockQueryBuilder(page);
		await askQuestion(page);
		await page.getByRole("button", { name: "Open in builder" }).click();
		await expect(page).toHaveURL(/queries\/from-ask/);
		await expect(page.locator(".query-builder .op")).toHaveCount(2);
		await expect(page.locator(".query-builder")).toContainText("tabSales Invoice");
	});

	test("a pipeline can be run and shows SQL + results", async ({ page }) => {
		await mockQueryBuilder(page);
		await page.goto("./queries/new");
		await page.locator("textarea").fill(JSON.stringify(OPERATIONS, null, 2));
		await page.locator("textarea").blur();
		await runQuery(page);
		await expect(page.locator(".sql")).toContainText("SELECT");
		await expect(page.locator(".query-builder pre")).toContainText("12400000");
	});

	test("saving a new query navigates to the persisted document", async ({ page }) => {
		await mockQueryBuilder(page);
		await page.goto("./queries/new");
		await page.locator("textarea").fill(JSON.stringify(OPERATIONS, null, 2));
		await page.locator("textarea").blur();
		await runQuery(page);
		await saveQuery(page);
		await expect(page.locator("main .text-base-semibold")).toContainText("NKQ-00001");
	});

	test("the source selector discovers DocTypes and sets the first operation", async ({ page }) => {
		await mockQueryBuilder(page);
		await page.goto("./queries/new");

		const source = page.locator(".query-builder .source-combobox").first();
		await expect(source).toBeVisible();
		await source.click();
		await page.getByRole("option", { name: "Customer" }).click();

		// Pipeline JSON should now start with a source step pointing at the selected table.
		await expect(page.locator(".query-builder textarea")).toHaveValue(/"type": "source"/);
		await expect(page.locator(".query-builder textarea")).toHaveValue(/"table": "tabCustomer"/);
	});

	test("the queries list loads saved queries", async ({ page }) => {
		await mockQueryBuilder(page);
		await page.goto("./queries");
		await expect(page.locator('[data-slot="list-row"]')).toHaveCount(1);
		await expect(page.locator('[data-slot="list-row"]')).toContainText("Revenue by territory");
	});
});
