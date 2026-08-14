import { expect } from "@playwright/test";

/**
 * Mocks for the query builder endpoints. The builder is the first workbench
 * screen that is fully wired to the backend; these fixtures let the test suite
 * exercise that wiring without a live Frappe site.
 */
export const SQL =
	"SELECT territory, SUM(grand_total) AS total FROM `tabSales Invoice` " +
	"WHERE docstatus = 1 GROUP BY territory";

export const OPERATIONS = [
	{ type: "source", table: "tabSales Invoice" },
	{
		type: "summarize",
		by: [{ name: "territory", expr: { col: "territory" } }],
		measures: [{ name: "total", expr: { fn: "sum", args: [{ col: "grand_total" }] } }],
	},
];

export const RUN_RESPONSE = {
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
	ml_operation: null,
};

export const SAVE_RESPONSE = {
	name: "NKQ-00001",
	title: "From Ask",
	data_source: "site",
	operations: OPERATIONS,
};

export const LIST_RESPONSE = [
	{ name: "NKQ-00001", title: "Revenue by territory", data_source: "site", modified: "2026-08-14 10:00:00" },
];

export const SOURCES_RESPONSE = [
	{ name: "Sales Invoice", label: "Sales Invoice", table: "tabSales Invoice", is_child: false },
	{ name: "Customer", label: "Customer", table: "tabCustomer", is_child: false },
];

export const SCHEMA_RESPONSE = {
	doctype: "Sales Invoice",
	table: "tabSales Invoice",
	flags: ["SUBMITTABLE"],
	columns: [
		{ name: "name", type: "VARCHAR", notes: ["primary key"] },
		{ name: "docstatus", type: "TINYINT", notes: ["0=Draft 1=Submitted 2=Cancelled"] },
		{ name: "territory", type: "VARCHAR", notes: [] },
		{ name: "grand_total", type: "DECIMAL(18,6)", notes: [] },
	],
};

/** Mock query builder endpoints. Call before `page.goto`. */
export async function mockQueryBuilder(page) {
	await page.route("**/api/v2/method/nakhoda.api.run**", (route) =>
		route.fulfill({ json: { data: RUN_RESPONSE } }),
	);
	await page.route("**/api/v2/method/nakhoda.api.query.save_query**", (route) =>
		route.fulfill({ json: { data: SAVE_RESPONSE } }),
	);
	await page.route("**/api/v2/method/nakhoda.api.query.list_queries**", (route) =>
		route.fulfill({ json: { data: LIST_RESPONSE } }),
	);
	await page.route("**/api/v2/method/nakhoda.api.query.list_sources**", (route) =>
		route.fulfill({ json: { data: SOURCES_RESPONSE } }),
	);
	await page.route("**/api/v2/method/nakhoda.api.query.get_schema**", (route) =>
		route.fulfill({ json: { data: SCHEMA_RESPONSE } }),
	);
	await page.route("**/api/v2/document/Nakhoda*Query/**", (route) =>
		route.fulfill({ json: { data: { ...SAVE_RESPONSE, operations: OPERATIONS } } }),
	);
}

/** Run the current pipeline in the query builder and wait for the SQL preview. */
export async function runQuery(page) {
	await page.getByRole("button", { name: "Run" }).click();
	await expect(page.locator(".sql")).toBeVisible();
	await expect(page.locator(".query-builder pre")).toContainText("Kenya");
}

/** Save the current query and return the persisted name in the URL. */
export async function saveQuery(page) {
	await page.getByRole("button", { name: "Save" }).click();
	await expect(page).toHaveURL(/queries\/NKQ-00001/);
}
