/**
 * Mocks for one dashboard's live surfaces: `nakhoda.api.dashboards.panel_data`
 * (one panel's rows), `nakhoda.api.agent.converse` (a loop turn),
 * `nakhoda.api.agent.run_chart` (a `chart://` citation re-executed on read),
 * and the two patch endpoints the approval screen presses.
 *
 * Same discipline as `fixtures/agent.js`: the transport is fixed, nothing else
 * is. Real `agent.js` mapping, real components, real Espresso tokens, real
 * `flint-chart` picking the chart type - only the HTTP responses are stand-ins,
 * shaped exactly as `api/dashboards.py:panel_data` and `agent/thread.py:converse`
 * return them.
 *
 * The counters are the point of several assertions: "nothing is applied until
 * approved" is a claim about a request that must *not* have been made, and only
 * a fixture that counts can prove it.
 */

export const DASHBOARD = "Financial Analytics";
export const CHART_RUN = "NAK-RUN-0042";
export const VERSION = "NAK-DBV-0007";
export const THREAD_TURN = "NAK-TURN-0001";

/** `get_dashboard_data` with panels - `templates.js`'s copy ships none, and a
 * dashboard with no panels cannot exercise the grid or a patch that names one. */
export const PANELLED_DASHBOARD = {
	name: DASHBOARD,
	key: "financial",
	title: "Financial Analytics",
	icon: "dollar-sign",
	color: "#10B981",
	metrics: [
		{
			label: "Net Movement",
			value: 28138168.84,
			format: "Currency",
			target: null,
			direction: null,
		},
	],
	panels: [
		{
			i: "panel_1",
			type: "chart",
			chart_type: "bar",
			title: "Movement by Account",
			removed: false,
		},
		{
			i: "panel_2",
			type: "chart",
			chart_type: "line",
			title: "Net Movement Over Time",
			removed: false,
		},
	],
	metrics_available: true,
	reason: null,
};

/** `panel_data`'s shape: flint's input exactly - columns, rows, and the
 * semantic types Frappe's fieldtypes resolved to (`agent/charts.py:semantics`). */
export const PANEL_DATA = {
	columns: ["account", "total"],
	rows: [
		{ account: "Sales", total: 12400000.03 },
		{ account: "Purchases", total: 6100000.03 },
		{ account: "Payroll", total: 2950000.03 },
	],
	row_count: 3,
	chart_type: "bar",
	title: "Movement by Account",
	semantic_types: { account: "Name", total: "Amount" },
	field_display_names: { account: "Account", total: "Total" },
	execution_time: 0.041,
};

/** A turn that ends in a written report citing one run. The bare `chart://`
 * line is the shape `agent/thread.py`'s action menu asks for. */
export const REPORT_TURN = {
	thread_turn: THREAD_TURN,
	status: "ok",
	steps: [
		{ action: "ask_data", question: "Movement by account this quarter", row_count: 3 },
		{ action: "write_report" },
	],
	step_count: 2,
	report: [
		"Sales leads on movement, at **KES 12.4M**.",
		"",
		`chart://${CHART_RUN}`,
		"",
		"Payroll is the smallest of the three.",
	].join("\n"),
	patch: null,
	error: null,
};

/** A turn that ends in a proposal. `diff` is `engine/dashboard.py:apply_patch`'s
 * own return shape, including the `state` values `PatchApproval.vue` badges. */
export const PATCH_TURN = {
	thread_turn: THREAD_TURN,
	status: "ok",
	steps: [
		{ action: "ask_data", question: "Movement by account", row_count: 3 },
		{ action: "propose_patch" },
	],
	step_count: 2,
	report: null,
	patch: {
		ops: [
			{ op: "set_filter", i: "panel_1", column: "account", operator: "=", value: "Sales" },
		],
		diff: [
			{ i: "panel_1", title: "Movement by Account", state: "will_change", field: "filters" },
		],
	},
	error: null,
};

/**
 * Route every endpoint the dashboard page and its Ask panel call.
 *
 * `turn` is what `converse` returns; `chartFails` serves `run_chart` a 403 so
 * the "a citation the reader may not read degrades in place" branch renders.
 * Returns the counters, live.
 */
export async function mockDashboard(page, { turn = REPORT_TURN, chartFails = false } = {}) {
	const calls = { converse: 0, panel: 0, chart: 0, apply: 0, revert: 0, appliedTurn: null };

	await page.route("**/api/v2/method/nakhoda.api.templates.list_dashboards**", (route) =>
		route.fulfill({
			json: { data: [{ ...PANELLED_DASHBOARD, modified: "2026-08-20 10:00:00" }] },
		}),
	);

	await page.route("**/api/v2/method/nakhoda.api.templates.get_dashboard_data**", (route) =>
		route.fulfill({ json: { data: PANELLED_DASHBOARD } }),
	);

	await page.route("**/api/v2/method/nakhoda.api.dashboards.panel_data**", (route) => {
		calls.panel += 1;
		const id = new URL(route.request().url()).searchParams.get("panel_id");
		return route.fulfill({ json: { data: { ...PANEL_DATA, title: `Panel ${id}` } } });
	});

	await page.route("**/api/v2/method/nakhoda.api.agent.converse**", (route) => {
		calls.converse += 1;
		return route.fulfill({ json: { data: turn } });
	});

	await page.route("**/api/v2/method/nakhoda.api.agent.run_chart**", (route) => {
		calls.chart += 1;
		if (chartFails) {
			return route.fulfill({
				status: 403,
				json: {
					errors: [
						{ type: "PermissionError", message: "Not permitted", title: "Message" },
					],
				},
			});
		}
		return route.fulfill({ json: { data: { ...PANEL_DATA, title: "Movement by Account" } } });
	});

	await page.route(
		"**/api/v2/method/nakhoda.api.dashboards.apply_dashboard_patch**",
		(route) => {
			calls.apply += 1;
			calls.appliedTurn = route.request().postDataJSON()?.thread_turn ?? null;
			return route.fulfill({
				json: { data: { diff: PATCH_TURN.patch.diff, version: VERSION } },
			});
		},
	);

	await page.route(
		"**/api/v2/method/nakhoda.api.dashboards.revert_dashboard_patch**",
		(route) => {
			calls.revert += 1;
			return route.fulfill({ json: { data: null } });
		},
	);

	return calls;
}
