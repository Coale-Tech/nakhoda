import { expect, test } from "@playwright/test";
import { mockBoot, mockDataStore, openDataStore } from "./fixtures/data_store.js";
import { mockSettings } from "./fixtures/settings.js";

/** Scope assertions to one table's row so a shared status word (e.g. "Synced",
 * which also appears in the intro paragraph and the "Last Synced" column
 * header) can't match the wrong element. */
function row(page, tableName) {
	return page.locator("[data-slot='list-row']").filter({ hasText: tableName });
}

async function open(page, storeOptions = {}, bootOptions = {}) {
	await mockBoot(page, bootOptions);
	// One switch, two readers: the settings document must say what boot said,
	// or `useSettings`'s write-through flips the gate back mid-test.
	await mockSettings(page, { enable_data_store: bootOptions.dataStoreEnabled === false ? 0 : 1 });
	await mockDataStore(page, storeOptions);
	await openDataStore(page);
}

test.describe("data store", () => {
	test("lists every readable DocType, imported and not", async ({ page }) => {
		await open(page);

		const invoiceRow = row(page, "tabSales Invoice");
		const customerRow = row(page, "tabCustomer");
		// Never-imported row shows "Never" and an "Import" action; the already
		// synced row shows its row count and a "Re-sync" action.
		await expect(invoiceRow.getByRole("button", { name: "Import" })).toBeVisible();
		await expect(customerRow.getByRole("button", { name: "Re-sync" })).toBeVisible();
		await expect(customerRow.getByText("480")).toBeVisible();
	});

	test("search filters the table list by label", async ({ page }) => {
		await open(page);
		await expect(row(page, "tabCustomer")).toBeVisible();

		await page.getByPlaceholder("Search tables").fill("Sales");
		await expect(row(page, "tabSales Invoice")).toBeVisible();
		await expect(row(page, "tabCustomer")).toHaveCount(0);
	});

	test("import asks for a row limit before queueing anything", async ({ page }) => {
		await open(page);

		await row(page, "tabSales Invoice").getByRole("button", { name: "Import" }).click();
		// The dialog is the confirmation step: nothing is queued until it is,
		// and the site-wide cap shows as the placeholder rather than as a
		// pre-filled value a blank submit would then persist per-table.
		const limit = page.getByLabel("Row Limit");
		await expect(limit).toBeVisible();
		await expect(limit).toHaveAttribute("placeholder", "1000000");
		await expect(limit).toHaveValue("");
		await expect(row(page, "tabSales Invoice").getByText("Syncing")).toHaveCount(0);
	});

	test("a queued import shows Syncing, then Synced once the poll catches up", async ({ page }) => {
		// `syncAfter: 2` keeps the row "Syncing" past the post-import refresh, so
		// reaching "Synced" proves the poll ran rather than the single refetch.
		await open(page, { syncAfter: 2 });

		const invoiceRow = row(page, "tabSales Invoice");
		await invoiceRow.getByRole("button", { name: "Import" }).click();
		await page.getByRole("button", { name: "Import", exact: true }).last().click();

		await expect(invoiceRow.getByText("Syncing")).toBeVisible();
		// While anything is in flight the header says so, and that row's own
		// action is disabled - re-queueing a table mid-import is the one thing
		// the endpoint refuses.
		await expect(page.getByText("Importing…")).toBeVisible();
		await expect(invoiceRow.getByRole("button", { name: "Re-sync" })).toBeDisabled();

		await expect(invoiceRow.getByText("Synced", { exact: true })).toBeVisible();
		await expect(page.getByText("Importing…")).toHaveCount(0);
	});

	test("a failed import surfaces the Failed state and its reason", async ({ page }) => {
		await open(page, { failImport: true });

		const invoiceRow = row(page, "tabSales Invoice");
		await invoiceRow.getByRole("button", { name: "Import" }).click();
		await page.getByRole("button", { name: "Import", exact: true }).last().click();
		await expect(invoiceRow.getByText("Failed")).toBeVisible();
		// A state badge alone would say "Failed" without ever saying why.
		await expect(invoiceRow.getByText("connection refused")).toBeVisible();
	});

	test("a refused queue reports the table is already importing, not an error", async ({ page }) => {
		await open(page, { alreadyQueued: true });

		await row(page, "tabSales Invoice").getByRole("button", { name: "Import" }).click();
		await page.getByRole("button", { name: "Import", exact: true }).last().click();
		await expect(page.getByText("is already importing")).toBeVisible();
	});

	test("search term survives an import's post-import refresh", async ({ page }) => {
		await open(page);

		await page.getByPlaceholder("Search tables").fill("Sales");
		const invoiceRow = row(page, "tabSales Invoice");
		await expect(invoiceRow).toBeVisible();
		await invoiceRow.getByRole("button", { name: "Import" }).click();
		await page.getByRole("button", { name: "Import", exact: true }).last().click();
		await expect(invoiceRow.getByText("Synced", { exact: true })).toBeVisible();
		// The list refresh after import must keep filtering on "Sales", not
		// silently reset to the unfiltered full list.
		await expect(row(page, "tabCustomer")).toHaveCount(0);
	});

	test("a non-admin sees the warehouse but no import affordance", async ({ page }) => {
		await open(page, {}, { isAdmin: false });

		// The endpoint gates on create-on-`Nakhoda Table` anyway; hiding the
		// button keeps the page from offering something the server refuses.
		await expect(row(page, "tabCustomer").getByText("480")).toBeVisible();
		await expect(page.getByRole("button", { name: "Import" })).toHaveCount(0);
		await expect(page.getByRole("button", { name: "Re-sync" })).toHaveCount(0);
	});

	test("with the store switched off the page says so and withdraws Import", async ({ page }) => {
		await open(page, {}, { dataStoreEnabled: false });

		// Listing is not gated - the warehouse stays readable, and tables
		// already imported stay queryable. Only movement stops.
		await expect(row(page, "tabCustomer").getByText("480")).toBeVisible();
		await expect(page.getByText("The Data Store is switched off in Settings")).toBeVisible();
		await expect(page.getByRole("button", { name: "Import" })).toHaveCount(0);
		await expect(page.getByRole("button", { name: "Re-sync" })).toHaveCount(0);
	});

	test("the sidebar drops the Data Store entry when the store is off, but the route still lands", async ({
		page,
	}) => {
		await open(page, {}, { dataStoreEnabled: false });

		// Insights hides its single Data Store entry the same way
		// (`src2/components/AppSidebar.vue`), and the route stays registered: a
		// bookmark from before the switch was flipped still resolves. Scoped to
		// the nav landmark because the page's own breadcrumb carries this name
		// too - and it is the one that must survive.
		const sidebar = page.getByRole("navigation", { name: "Main" });
		await expect(sidebar.getByRole("link", { name: "Data Store", exact: true })).toHaveCount(0);
		await expect(sidebar.getByRole("link", { name: "Data Sources", exact: true })).toBeVisible();
		await expect(page.locator("header").getByRole("link", { name: "Data Store" })).toBeVisible();
	});

	test("with the store on, the sidebar carries the entry", async ({ page }) => {
		await open(page);

		const entry = page
			.getByRole("navigation", { name: "Main" })
			.getByRole("link", { name: "Data Store", exact: true });
		await expect(entry).toBeVisible();
		// Navigation, not an action: the entry carries a real href, so it can be
		// opened in a new tab and reads as a link to a screen reader.
		await expect(entry).toHaveAttribute("href", /data-store/);
		await expect(entry).toHaveAttribute("aria-current", "page");
	});
});
