import { expect, test } from "@playwright/test";
import { mockQueryBuilder } from "./fixtures/query.js";

/**
 * Phase 8 (`docs/plan/12-build-plan.md` §Phase 8, `nakhoda.tests.test_ml`,
 * `nakhoda.tests.test_no_ml_surface`): a forecast is an ordinary pipeline
 * step, not a dedicated feature. This spec proves that end to end in the
 * browser - the counterpart to the backend unit tests (`ml.py` in
 * isolation) and the source-tree gate (no ML-named component/route/badge).
 *
 * The mocked `nakhoda.api.run` response below is the exact shape a real
 * forecast produces (verified live against the `jkm` site: source ->
 * filter -> summarize -> forecast returned `columns: [posting_date, total,
 * forecast, forecast_lower, forecast_upper]`, `sql` holding only the
 * summarize prefix, `ml_operation` echoing the trailing step).
 */
const ML_PIPELINE = [
	{ type: "source", table: "tabSales Invoice" },
	{ type: "filter", where: { fn: "eq", args: [{ col: "docstatus" }, { lit: 1 }] } },
	{
		type: "summarize",
		by: [{ name: "posting_date", expr: { col: "posting_date" } }],
		measures: [{ name: "total", expr: { fn: "sum", args: [{ col: "grand_total" }] } }],
	},
	{ type: "forecast", column: "total", date_column: "posting_date", periods: 5, freq: "D" },
];

const FORECAST_SQL =
	"SELECT `posting_date`, SUM(`grand_total`) AS `total` FROM `tabSales Invoice` WHERE `docstatus` = 1 GROUP BY `posting_date`";

const FORECAST_RUN_RESPONSE = {
	columns: ["posting_date", "total", "forecast", "forecast_lower", "forecast_upper"],
	rows: [
		{ posting_date: "2026-08-07", total: 69442.6, forecast: null, forecast_lower: null, forecast_upper: null },
		{ posting_date: "2026-08-08", total: null, forecast: 483880.81, forecast_lower: -558157.99, forecast_upper: 1525919.61 },
	],
	row_count: 2,
	truncated: false,
	execution_time: 0.9,
	sql: FORECAST_SQL,
	ml_operation: { type: "forecast", column: "total", date_column: "posting_date", periods: 5, freq: "D" },
};

test.describe("ML operations are ordinary pipeline steps", () => {
	test("a forecast pipeline runs and renders through the same UI as any other step", async ({ page }) => {
		await mockQueryBuilder(page);
		await page.route("**/api/v2/method/nakhoda.api.run**", (route) =>
			route.fulfill({ json: { data: FORECAST_RUN_RESPONSE } }),
		);
		await page.goto("./queries/new");

		await page.locator("textarea").first().fill(JSON.stringify(ML_PIPELINE, null, 2));
		await page.locator("textarea").first().blur();

		// Every step - including `forecast` - renders as an identically
		// structured `.op` row: numbered rail, kind label, generic description.
		// No `.op` carries an ML-specific class, badge, or icon distinct from
		// its siblings.
		const steps = page.locator(".query-builder .op");
		await expect(steps).toHaveCount(4);
		await expect(steps.last()).toContainText("forecast");
		const stepClasses = await steps.evaluateAll((rows) => rows.map((r) => r.className));
		expect(new Set(stepClasses).size).toBe(1); // identical class list across every step, ML or not

		await page.getByRole("button", { name: "Run" }).click();

		// Only the SQL prefix compiles/renders - the forecast step itself
		// never becomes SQL (`compile_pipeline` refuses a trailing ML op).
		await expect(page.locator(".sql")).toBeVisible();
		await expect(page.locator(".sql")).toContainText("GROUP BY");
		await expect(page.locator(".sql")).not.toContainText("forecast");

		// The results panel renders the forecast rows through the exact same
		// generic JSON preview every other pipeline result uses.
		await expect(page.locator(".query-builder pre")).toContainText("forecast_lower");
		await expect(page.locator(".query-builder pre")).toContainText("483880");

		// No element anywhere on the page names itself a dedicated ML surface
		// (chart variant, badge, panel) via a data attribute or badge-style
		// class - the DOM-level counterpart to `nakhoda.tests.test_no_ml_
		// surface`'s source-tree check. Excludes bare `[class*="ml-"]`: that
		// substring also matches Tailwind's `ml-*` margin-left utilities on
		// unrelated elements, which would be a false positive, not a finding.
		const mlSurfaceHits = await page
			.locator('[data-ml], [data-testid*="ml-"], [class*="ml-badge"], [class*="ml-chart"], [class*="ml-panel"]')
			.count();
		expect(mlSurfaceHits).toBe(0);
	});
});
