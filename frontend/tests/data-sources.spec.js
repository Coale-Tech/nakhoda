import { expect, test } from "@playwright/test";
import { SOURCES_ROWS, mockBoot, mockDataSources, mockUploads, openDataSources } from "./fixtures/data_store.js";

/**
 * `ListHeaderCell` also renders the literal column header text "Default",
 * so every assertion below scopes to a specific `[data-slot="list-row"]`
 * rather than searching the whole page for that word - a page-wide
 * `getByText("Default")` always has (at least) the header as a second match.
 */
function row(page, name) {
	return page.locator("[data-slot='list-row']").filter({ hasText: name });
}

async function open(page, sourceOptions = {}, bootOptions = {}, uploadOptions = null) {
	await mockBoot(page, bootOptions);
	await mockDataSources(page, sourceOptions);
	if (uploadOptions) await mockUploads(page, uploadOptions);
	await openDataSources(page);
}

/** Open New Data Source › one type, from the list header. */
async function pickType(page, label) {
	await page.getByRole("button", { name: "New Data Source" }).click();
	await page.getByText(label, { exact: true }).click();
}

test.describe("data sources", () => {
	test("lists configured sources with their default and status", async ({ page }) => {
		await open(page);

		const siteDb = row(page, "Site Database");
		const warehouse = row(page, "DuckDB Warehouse");
		await expect(siteDb.getByText("Default", { exact: true })).toBeVisible();
		await expect(warehouse.getByRole("button", { name: "Set Default" })).toBeVisible();
		await expect(siteDb.getByText("Reachable")).toBeVisible();
		await expect(warehouse.getByText("Untested")).toBeVisible();
	});

	test("says who configured each source and when it last changed", async ({ page }) => {
		await open(page);

		// Insights' Owner / Created / Modified columns. The owner is read per row,
		// not printed from the session, so a row somebody else owns says their
		// name - the whole point of the column on a shared install.
		const replica = row(page, "Reporting Replica");
		await expect(replica.getByText("Amina Analyst")).toBeVisible();
		await expect(row(page, "Site Database").getByText("Administrator")).toBeVisible();
		await expect(replica.getByTitle(SOURCES_ROWS[2].creation)).toBeVisible();
		await expect(replica.getByTitle(SOURCES_ROWS[2].modified)).toBeVisible();
	});

	test("the status badge carries when the connection last answered", async ({ page }) => {
		await open(page);

		// Relative and on the badge rather than in a column of its own: the
		// question the list answers is whether a source is reachable, and "when
		// did it say so" is the follow-up, which a tooltip can hold.
		await expect(row(page, "Site Database").getByTitle("Last checked 2 hours ago")).toBeVisible();
		// A source nobody has probed reads as Never, not as a blank tooltip.
		await expect(row(page, "DuckDB Warehouse").getByTitle("Last checked Never")).toBeVisible();
	});

	test("relative times read the site's timezone, not the reader's", async ({ page }) => {
		// The fixture writes `last_checked` the way the server does - a naive
		// string in the site's zone (`SITE_TIME_ZONE`), two and a half hours off
		// the browser's pinned one. Read as browser-local, a probe from two
		// hours ago renders in the *future* ("in 30 minutes"), which is how this
		// was found on a live `Asia/Kolkata` bench.
		await open(page, {}, { timeZone: "Asia/Kolkata" });
		await expect(row(page, "Site Database").getByTitle("Last checked 2 hours ago")).toBeVisible();
	});

	test("a boot payload without a timezone still renders a relative time", async ({ page }) => {
		// Older page renders never sent `time_zone`. The column falls back to
		// browser-local rather than blanking or printing the raw timestamp: with
		// the fixture writing site-zone strings, that lands 2.5 hours out, which
		// is the pre-fix behaviour and still a legible relative time.
		await open(page, {}, { timeZone: null });
		const badge = row(page, "Site Database").locator("[title^='Last checked ']");
		await expect(badge).toHaveAttribute("title", /Last checked (in|\d+ )/);
		await expect(badge).not.toHaveAttribute("title", "Last checked Never");
	});

	test("the search box filters by title, and says so when nothing matches", async ({ page }) => {
		await open(page);

		await page.getByPlaceholder("Search by Title").fill("duck");
		await expect(row(page, "DuckDB Warehouse")).toBeVisible();
		await expect(row(page, "Site Database")).toHaveCount(0);

		await page.getByPlaceholder("Search by Title").fill("postgres");
		await expect(page.getByText("No data source matches this search.")).toBeVisible();
	});

	test("testing a connection updates its status badge", async ({ page }) => {
		await open(page);

		const warehouse = row(page, "DuckDB Warehouse");
		await warehouse.getByRole("button", { name: "Test Connection" }).click();
		await expect(warehouse.getByText("Reachable")).toBeVisible();
	});

	test("setting a source as default moves the badge and removes the button from that row", async ({ page }) => {
		await open(page);

		const siteDb = row(page, "Site Database");
		const warehouse = row(page, "DuckDB Warehouse");
		await expect(siteDb.getByText("Default", { exact: true })).toBeVisible();
		await expect(warehouse.getByRole("button", { name: "Set Default" })).toBeVisible();

		await warehouse.getByRole("button", { name: "Set Default" }).click();

		await expect(warehouse.getByText("Default", { exact: true })).toBeVisible();
		await expect(siteDb.getByRole("button", { name: "Set Default" })).toBeVisible();
		// Exactly one row carries the badge at a time.
		await expect(siteDb.getByText("Default", { exact: true })).toHaveCount(0);
	});

	test("a new external database is added through pick-a-type then fill-its-form", async ({ page }) => {
		await open(page);

		await page.getByRole("button", { name: "New Data Source" }).click();
		// Every type Nakhoda can actually open, and nothing it cannot: the
		// dialog's options are the deployment's real capability list.
		for (const type of ["MariaDB", "PostgreSQL", "ClickHouse", "DuckDB", "Upload CSV or Excel"]) {
			await expect(page.getByText(type, { exact: true })).toBeVisible();
		}

		await page.getByText("PostgreSQL", { exact: true }).click();
		await expect(page.getByText("Connect to PostgreSQL")).toBeVisible();
		// Postgres is the one type carrying `schema`; the form is per-type, not
		// a shared superset with dead fields.
		await expect(page.getByPlaceholder("eg. schema1,schema2")).toBeVisible();

		await page.getByPlaceholder("My Database").fill("Analytics Replica");
		await page.getByPlaceholder("localhost").fill("db.internal");
		await page.getByPlaceholder("DB_1267891").fill("analytics");
		await page.getByPlaceholder("read_only_user").fill("reader");
		await page.getByPlaceholder("**********").fill("s3cret");

		// Save is refused until the credentials have answered once: an untested
		// row is a broken row for every other user of the site.
		await expect(page.getByRole("button", { name: "Add Data Source" })).toBeDisabled();
		await page.getByRole("button", { name: "Connect" }).click();
		await expect(page.getByRole("button", { name: "Connected" })).toBeVisible();

		await page.getByRole("button", { name: "Add Data Source" }).click();
		await expect(row(page, "Analytics Replica")).toBeVisible();
	});

	test("a connection that does not answer cannot be saved", async ({ page }) => {
		await open(page, { unreachable: true });

		await pickType(page, "MariaDB");
		await page.getByPlaceholder("My Database").fill("Dead Host");
		await page.getByPlaceholder("localhost").fill("nope.invalid");
		await page.getByPlaceholder("DB_1267891").fill("db");
		await page.getByPlaceholder("read_only_user").fill("reader");
		await page.getByPlaceholder("**********").fill("pw");

		await page.getByRole("button", { name: "Connect" }).click();
		await expect(page.getByRole("button", { name: "Failed, Retry?" })).toBeVisible();
		await expect(page.getByText("could not connect to server")).toBeVisible();
		await expect(page.getByRole("button", { name: "Add Data Source" })).toBeDisabled();
	});

	test("editing a host after a successful Connect withdraws the save", async ({ page }) => {
		await open(page);

		await pickType(page, "MariaDB");
		await page.getByPlaceholder("My Database").fill("Retyped");
		await page.getByPlaceholder("localhost").fill("db.internal");
		await page.getByPlaceholder("DB_1267891").fill("db");
		await page.getByPlaceholder("read_only_user").fill("reader");
		await page.getByPlaceholder("**********").fill("pw");
		await page.getByRole("button", { name: "Connect" }).click();
		await expect(page.getByRole("button", { name: "Connected" })).toBeVisible();

		// Insights keeps the green state here, which lets an untested host be
		// saved. The result is a row that fails for everyone else.
		await page.getByPlaceholder("localhost").fill("other.internal");
		await expect(page.getByRole("button", { name: "Connect", exact: true })).toBeVisible();
		await expect(page.getByRole("button", { name: "Add Data Source" })).toBeDisabled();
	});

	test("only an external source offers Edit Connection and Delete", async ({ page }) => {
		await open(page);

		// The site database and the warehouse are created by the backend from
		// `site_config.json`; there is no connection to re-point and no row to
		// delete, so they carry no menu at all.
		await expect(row(page, "Site Database").getByRole("button", { name: "More actions" })).toHaveCount(0);
		await expect(row(page, "DuckDB Warehouse").getByRole("button", { name: "More actions" })).toHaveCount(0);

		await row(page, "Reporting Replica").getByRole("button", { name: "More actions" }).click();
		await page.getByRole("menuitem", { name: "Edit Connection" }).click();
		// The form opens on the row's own type, pre-filled with the connection
		// the backend holds - not with the handful of fields the list shows.
		await expect(page.getByText("Edit PostgreSQL")).toBeVisible();
		await expect(page.getByPlaceholder("My Database")).toHaveValue("Reporting Replica");
		await expect(page.getByPlaceholder("localhost")).toHaveValue("db.internal");
		await expect(page.getByPlaceholder("read_only_user")).toHaveValue("reader");
		await expect(page.getByPlaceholder("DB_1267891")).toHaveValue("reporting");
	});

	test("an edit re-points a host without retyping the password", async ({ page }) => {
		await open(page);

		await row(page, "Reporting Replica").getByRole("button", { name: "More actions" }).click();
		await page.getByRole("menuitem", { name: "Edit Connection" }).click();

		// The stored secret is never sent to the browser, so the box is empty and
		// says what empty means. On an edit it is also optional: `test_connection`
		// fills it in from the row, because requiring it would mean
		// re-authenticating to move a port.
		await expect(page.getByPlaceholder("Unchanged")).toHaveValue("");
		await expect(page.getByText("Leave empty to keep the stored password.")).toBeVisible();
		await page.getByPlaceholder("localhost").fill("replica.internal");
		await page.getByRole("button", { name: "Connect" }).click();
		await expect(page.getByRole("button", { name: "Connected" })).toBeVisible();

		await page.getByRole("button", { name: "Save" }).click();
		await row(page, "Reporting Replica").getByRole("button", { name: "More actions" }).click();
		await page.getByRole("menuitem", { name: "Edit Connection" }).click();
		await expect(page.getByPlaceholder("localhost")).toHaveValue("replica.internal");
	});

	test("deleting an external source drops it from the list", async ({ page }) => {
		await open(page);

		await row(page, "Reporting Replica").getByRole("button", { name: "More actions" }).click();
		await page.getByRole("menuitem", { name: "Delete" }).click();
		// The confirm names the row, because the queries built on it break.
		await expect(page.getByText("Delete Reporting Replica?")).toBeVisible();
		await page.getByRole("button", { name: "Delete" }).last().click();

		await expect(row(page, "Reporting Replica")).toHaveCount(0);
		await expect(row(page, "Site Database")).toBeVisible();
	});

	test("a CSV is previewed before anything is written, then imported", async ({ page }) => {
		await open(page, {}, {}, {});

		await pickType(page, "Upload CSV or Excel");
		await expect(page.getByText("Select a CSV or Excel file to upload")).toBeVisible();

		await page.setInputFiles("input[type='file']", {
			name: "customers.csv",
			mimeType: "text/csv",
			buffer: Buffer.from("name,city\nAcme,Nairobi\nGlobex,Mombasa\n"),
		});

		// The parse is shown before the write: a misread delimiter is visible
		// here, when walking away still costs nothing.
		await expect(page.getByText("upload_customers")).toBeVisible();
		await expect(page.getByText("city", { exact: true })).toBeVisible();
		await expect(page.getByText("Nairobi")).toBeVisible();
		await expect(page.getByText("Showing 2 of 2 rows")).toBeVisible();

		await page.getByRole("button", { name: "Import", exact: true }).click();
		await expect(page.getByText("Imported customers")).toBeVisible();
	});

	test("a refused import is reported in the dialog, not swallowed", async ({ page }) => {
		await open(page, {}, {}, { importFails: true });

		await pickType(page, "Upload CSV or Excel");
		await page.setInputFiles("input[type='file']", {
			name: "customers.csv",
			mimeType: "text/csv",
			buffer: Buffer.from("name,city\nAcme,Nairobi\n"),
		});
		await expect(page.getByText("upload_customers")).toBeVisible();

		await page.getByRole("button", { name: "Import", exact: true }).click();
		await expect(page.getByText("The Data Store is turned off")).toBeVisible();
	});

	test("a non-admin can read the list but not reconfigure it", async ({ page }) => {
		await open(page, {}, { isAdmin: false });

		await expect(row(page, "Site Database").getByText("Reachable")).toBeVisible();
		await expect(page.getByRole("button", { name: "Test Connection" })).toHaveCount(0);
		await expect(page.getByRole("button", { name: "Set Default" })).toHaveCount(0);
		// Adding a source writes a `Nakhoda Data Source` row, which only the two
		// admin roles may create - so the whole two-step flow is absent, not
		// offered and then refused by the backend.
		await expect(page.getByRole("button", { name: "New Data Source" })).toHaveCount(0);
		await expect(page.getByRole("button", { name: "More actions" })).toHaveCount(0);
	});

	test("a source drills into its own tables, and the warehouse lists only imports", async ({ page }) => {
		await open(page);

		await row(page, "Site Database").click();
		// The site database exposes every readable DocType...
		await expect(page.locator("[data-slot='list-row']").filter({ hasText: "tabSales Invoice" })).toBeVisible();
		await expect(page.locator("[data-slot='list-row']").filter({ hasText: "tabCustomer" })).toBeVisible();

		await page.getByRole("link", { name: "Data Sources" }).first().click();
		await row(page, "DuckDB Warehouse").click();
		// ...the warehouse exposes only what somebody deliberately imported. A
		// DuckDB table nobody asked for does not exist, so it is absent rather
		// than listed as un-synced.
		await expect(page.locator("[data-slot='list-row']").filter({ hasText: "tabCustomer" })).toBeVisible();
		await expect(page.locator("[data-slot='list-row']").filter({ hasText: "tabSales Invoice" })).toHaveCount(0);
	});

	test("a table drills into a bounded preview with its real columns", async ({ page }) => {
		await open(page);

		await row(page, "Site Database").click();
		await page.locator("[data-slot='list-row']").filter({ hasText: "tabCustomer" }).click();

		await expect(page.getByText("tabCustomer").first()).toBeVisible();
		await expect(page.getByText("customer_name")).toBeVisible();
		await expect(page.getByText("Acme")).toBeVisible();
		// A null cell reads as an em dash rather than as an empty column.
		await expect(page.getByText("\u2014").first()).toBeVisible();
	});

	test("a preview the viewer may not read reports it instead of rendering an empty grid", async ({ page }) => {
		await open(page, { previewFails: true });

		await row(page, "Site Database").click();
		await page.locator("[data-slot='list-row']").filter({ hasText: "tabCustomer" }).click();
		await expect(page.getByText("Could not preview this table.")).toBeVisible();
	});
});
