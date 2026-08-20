import { expect, test } from "@playwright/test";
import { mockTemplates, TEMPLATES_LIST, DASHBOARDS_LIST } from "./fixtures/templates.js";

test.describe("workbook template gallery", () => {
	test("the dashboards list shows already-instantiated dashboards", async ({ page }) => {
		await mockTemplates(page);
		await page.goto("./dashboards");
		await expect(page.getByText(DASHBOARDS_LIST[0].title)).toBeVisible();
	});

	test("New from Template opens the gallery with both templates", async ({ page }) => {
		await mockTemplates(page);
		await page.goto("./dashboards");
		await page.getByRole("button", { name: "New from Template" }).click();
		await expect(page.getByRole("heading", { name: "New from template" })).toBeVisible();
		for (const template of TEMPLATES_LIST) {
			await expect(page.getByRole("dialog").getByText(template.title)).toBeVisible();
		}
	});

	test("an unimported template shows Add; an imported one with no update shows Open", async ({ page }) => {
		await mockTemplates(page);
		await page.goto("./dashboards");
		await page.getByRole("button", { name: "New from Template" }).click();

		const salesCard = page.locator(".grid.flex-1 > div", { hasText: "Sales Intelligence" });
		await expect(salesCard.getByRole("button", { name: "Add" })).toBeVisible();

		const financialCard = page.locator(".grid.flex-1 > div", { hasText: "Financial Analytics" });
		await expect(financialCard.getByRole("button", { name: "Open" })).toBeVisible();
	});

	test("instantiating a template creates it and navigates to the live dashboard", async ({ page }) => {
		await mockTemplates(page);
		await page.goto("./dashboards");
		await page.getByRole("button", { name: "New from Template" }).click();

		let createCalled = false;
		await page.route("**/api/v2/method/nakhoda.api.templates.create_intelligence_template**", (route) => {
			createCalled = true;
			return route.fulfill({ json: { data: { name: "Sales Intelligence" } } });
		});

		await page.locator(".grid.flex-1 > div", { hasText: "Sales Intelligence" }).getByRole("button", { name: "Add" }).click();

		await expect(page).toHaveURL(/dashboards\/Sales(%20|\s)Intelligence/);
		await expect(page.locator("header").getByRole("link", { name: "Sales Intelligence" })).toBeVisible();
		expect(createCalled).toBe(true);
	});

	test("an instantiated dashboard renders its computed metric values", async ({ page }) => {
		await mockTemplates(page);
		await page.goto("./dashboards/Sales Intelligence");
		await expect(page.getByText("Total Revenue")).toBeVisible();
		await expect(page.getByText("$12,400,000.00")).toBeVisible();
		await expect(page.getByText("No panels on this dashboard yet.")).toBeVisible();
	});
});
