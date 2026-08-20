/**
 * Workbook fixtures.
 *
 * Shapes are copied from what the endpoints actually return, not invented:
 * `get_workbooks` (`api/workbooks.py:71`) yields the list row with `views` and
 * `shared_with`, and the document GET yields the tree that
 * `Nakhoda Workbook.as_dict` builds - queries/charts/dashboards/folders plus
 * `read_only`. A mock that guessed those keys would let a page ship reading
 * fields the server never sends.
 */

export const WORKBOOK_ROWS = [
	{
		name: "wb-sales",
		title: "Sales Review",
		owner: "Administrator",
		owner_name: "Administrator",
		creation: "2026-08-01 09:00:00",
		modified: "2026-08-14 16:20:00",
		views: 12,
		shared_with: ["reader@example.com"],
		shared_with_names: ["Reader User"],
		shared_with_organization: 0,
	},
	{
		name: "wb-ops",
		title: "Ops Weekly",
		owner: "reader@example.com",
		owner_name: "Reader User",
		creation: "2026-07-20 11:00:00",
		modified: "2026-08-10 08:05:00",
		views: 3,
		shared_with: [],
		shared_with_names: [],
		shared_with_organization: 1,
	},
];

export const WORKBOOK_TREE = {
	name: "wb-sales",
	title: "Sales Review",
	owner: "Administrator",
	read_only: 0,
	// `as_dict` answers "would Manage Access open or 403" per load, because
	// `update_share_permissions` grants read and write but never `share`.
	can_share: 1,
	queries: [
		{
			name: "q-revenue",
			title: "Revenue by territory",
			data_source: "Site Database",
			folder: "Drafts",
			sort_order: 0,
			operations: JSON.stringify([
				{ type: "source", table: "tabSales Invoice" },
				{ type: "summarize", by: ["territory"], measures: [{ name: "total", expr: { fn: "sum", args: ["base_grand_total"] } }] },
			]),
		},
		{
			name: "q-invoices",
			title: "Invoice list",
			data_source: "Site Database",
			folder: null,
			sort_order: 1,
			operations: JSON.stringify([{ type: "source", table: "tabSales Invoice" }]),
		},
	],
	charts: [
		{
			name: "c-revenue",
			title: "Revenue bars",
			query: "q-revenue",
			chart_type: "Bar",
			folder: null,
			sort_order: 0,
			is_public: 0,
			config: JSON.stringify({
				series: [
					{ label: "Germany", value: 4200 },
					{ label: "Kenya", value: 3100 },
					{ label: "Japan", value: 1800 },
				],
			}),
		},
	],
	dashboards: [
		{
			name: "d-weekly",
			title: "Weekly board",
			folder: null,
			sort_order: 0,
			is_public: 0,
			vertical_compact_layout: 1,
			items: JSON.stringify([{ i: "0", type: "chart", chart: "c-revenue", x: 0, y: 0, w: 6, h: 8 }]),
		},
	],
	folders: [{ name: "f-drafts", title: "Drafts", type: "query", sort_order: 0, is_expanded: 1 }],
};

/**
 * Route the workbook list and one workbook's tree.
 *
 * `overrides.tree` replaces the document response wholesale so a test can send
 * a reader's copy (`read_only: 1`) without restating the tree.
 */
export async function mockWorkbooks(page, overrides = {}) {
	const rows = overrides.rows ?? WORKBOOK_ROWS;
	const tree = overrides.tree ?? WORKBOOK_TREE;

	await page.route("**/api/v2/method/nakhoda.api.workbooks.get_workbooks**", (route) =>
		route.fulfill({ json: { data: rows } }),
	);
	await page.route("**/api/v2/document/Nakhoda%20Workbook/**", async (route) => {
		const method = route.request().method();
		if (method === "GET") return route.fulfill({ json: { data: tree } });
		// PUT (rename) and doc-method POSTs land here; echoing the tree keeps the
		// page's post-write refetch honest.
		return route.fulfill({ json: { data: tree } });
	});
	await page.route("**/api/v2/method/nakhoda.api.workbooks.create_workbook**", (route) =>
		route.fulfill({ json: { data: "wb-new" } }),
	);
	await page.route("**/api/v2/method/nakhoda.api.workbooks.add_chart**", (route) =>
		route.fulfill({ json: { data: "c-new" } }),
	);
	await page.route("**/api/v2/method/nakhoda.api.workbooks.add_dashboard**", (route) =>
		route.fulfill({ json: { data: "d-new" } }),
	);
	await page.route("**/api/v2/method/nakhoda.api.workbooks.toggle_folder_expanded**", (route) =>
		route.fulfill({ json: { data: null } }),
	);
	// Share surface. Shapes from `get_share_permissions` (`api/workbooks.py:208`)
	// and `list_shareable_users` (`:275`) - the dialog reads `full_name` and
	// `write`, so a fixture that shortened either would let it ship broken.
	await page.route("**/api/v2/method/nakhoda.api.workbooks.get_share_permissions**", (route) =>
		route.fulfill({
			json: {
				data: {
					user_permissions: [
						{ user: "reader@example.com", full_name: "Reader User", read: 1, write: 0 },
					],
					organization_access: "view",
				},
			},
		}),
	);
	// `candidates: []` is how a test says "the server named nobody" - the shape
	// the dialog has to answer with words rather than silence.
	await page.route("**/api/v2/method/nakhoda.api.workbooks.list_shareable_users**", (route) =>
		route.fulfill({
			json: {
				data: overrides.candidates ?? [
					{ user: "editor@example.com", full_name: "Editor User", user_image: "" },
					{ user: "reader@example.com", full_name: "Reader User", user_image: "" },
				],
			},
		}),
	);
	await page.route("**/api/v2/method/nakhoda.api.workbooks.update_share_permissions**", (route) =>
		route.fulfill({ json: { data: null } }),
	);
	await page.route("**/api/v2/method/nakhoda.api.query.save_query**", (route) =>
		route.fulfill({
			json: { data: { name: "q-new", title: "Untitled Query", data_source: "Site Database", workbook: "wb-sales", operations: [] } },
		}),
	);
}

/** The save-answer endpoint the Ask page's dialog posts to. */
export async function mockSaveAnswer(page, result = { workbook: "wb-sales", query: "q-saved", chart: null }) {
	await page.route("**/api/v2/method/nakhoda.api.workbooks.save_answer**", (route) =>
		route.fulfill({ json: { data: result } }),
	);
}
