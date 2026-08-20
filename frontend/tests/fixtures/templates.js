/**
 * Mocks for the workbook-template mechanism (`nakhoda.api.templates`):
 * `get_intelligence_templates` (gallery list), `create_intelligence_template`
 * (instantiate), `list_dashboards` (Dashboards page), and
 * `get_dashboard_data` (the instantiated dashboard's computed metrics),
 * mirroring `fixtures/query.js`'s pattern for the query builder endpoints.
 */
export const TEMPLATES_LIST = [
	{
		name: "nakhoda/sales",
		title: "Sales Intelligence",
		description: "Revenue, pipeline and territory performance.",
		module: "Nakhoda",
		app: "nakhoda",
		app_title: "Nakhoda",
		version: 1,
		has_data: true,
		preview_image: null,
		imported_name: null,
		imported_version: null,
		update_available: false,
		customized: false,
	},
	{
		name: "nakhoda/financial",
		title: "Financial Analytics",
		description: "Margins, AR/AP and cash position.",
		module: "Nakhoda",
		app: "nakhoda",
		app_title: "Nakhoda",
		version: 1,
		has_data: true,
		preview_image: null,
		imported_name: "Financial Analytics",
		imported_version: 1,
		update_available: false,
		customized: false,
	},
];

export const CREATE_RESPONSE = { name: "Sales Intelligence" };

export const DASHBOARDS_LIST = [
	{
		name: "Financial Analytics",
		title: "Financial Analytics",
		icon: "dollar-sign",
		color: "#10B981",
		modified: "2026-08-14 10:00:00",
	},
];

export const DASHBOARD_DATA = {
	name: "Sales Intelligence",
	key: "sales",
	title: "Sales Intelligence",
	icon: "trending-up",
	color: "#3B82F6",
	metrics: [{ label: "Total Revenue", value: 12400000, format: "Currency", target: null, direction: null }],
	panels: [],
	metrics_available: true,
	reason: null,
};

/** Mock the template gallery + dashboard endpoints. Call before `page.goto`. */
export async function mockTemplates(page) {
	await page.route("**/api/v2/method/nakhoda.api.templates.get_intelligence_templates**", (route) =>
		route.fulfill({ json: { data: TEMPLATES_LIST } }),
	);
	await page.route("**/api/v2/method/nakhoda.api.templates.create_intelligence_template**", (route) =>
		route.fulfill({ json: { data: CREATE_RESPONSE } }),
	);
	await page.route("**/api/v2/method/nakhoda.api.templates.list_dashboards**", (route) =>
		route.fulfill({ json: { data: DASHBOARDS_LIST } }),
	);
	await page.route("**/api/v2/method/nakhoda.api.templates.get_dashboard_data**", (route) =>
		route.fulfill({ json: { data: DASHBOARD_DATA } }),
	);
}
