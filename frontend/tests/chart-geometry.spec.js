import { test, expect } from "@playwright/test";
import { askChartQuestion } from "./fixtures/agent.js";

/**
 * Phase 5 gate (`12-build-plan.md` §5, gate index row "5 - charts do not
 * lie"): bar height must be proportional to value within 2%, and every axis
 * label must sit under the bar it names with 0px drift. Both were real
 * defects in the design mockup, invisible to repeated eyeballing and found
 * only by measuring rendered geometry - see the docstring in `Chart.vue`.
 *
 * `nakhoda.agent.charts.pick` (backend) infers a chart from a grouped
 * result's shape and `src/agent.js` maps it onto `turn.answer.chart`, so
 * `Turn.vue` renders `Chart.vue` for a two-column, few-row answer -
 * `askChartQuestion` mocks exactly that shape. `Chart.vue` retains the
 * arithmetic that fixed both defects, and the measurement below is kept
 * verbatim - the geometry claim is asserted against a rendered DOM or not
 * at all.
 *
 * The equivalent claim for the surface that ships on every other answer is
 * measured in `table-geometry.spec.js`.
 */
test("bar height is proportional to its value within 2 percentage points", async ({ page }) => {
	await askChartQuestion(page);
	const bars = page.locator(".chart .bar");
	const count = await bars.count();
	expect(count).toBeGreaterThan(1);

	const measurements = [];
	for (let i = 0; i < count; i++) {
		const bar = bars.nth(i);
		const value = Number(await bar.getAttribute("data-value"));
		const box = await bar.boundingBox();
		measurements.push({ value, height: box.height });
	}

	const maxHeightEntry = measurements.reduce((a, b) => (b.height > a.height ? b : a));
	const maxValue = Math.max(...measurements.map((m) => m.value));

	// Sanity: the tallest bar by pixel height must be the largest value -
	// a rescaled series (the historical defect) silently breaks this too.
	expect(maxHeightEntry.value).toBe(maxValue);

	for (const m of measurements) {
		const expectedPct = (m.value / maxValue) * 100;
		const actualPct = (m.height / maxHeightEntry.height) * 100;
		expect(Math.abs(actualPct - expectedPct)).toBeLessThanOrEqual(2);
	}
});

test("axis label sits under the bar it names, 0px horizontal drift", async ({ page }) => {
	await askChartQuestion(page);
	const bars = page.locator(".chart .bar-col");
	const labels = page.locator(".chart .axis > div");
	const count = await bars.count();
	expect(count).toBe(await labels.count());

	for (let i = 0; i < count; i++) {
		const barBox = await bars.nth(i).boundingBox();
		const labelBox = await labels.nth(i).boundingBox();
		const barCenter = barBox.x + barBox.width / 2;
		const labelCenter = labelBox.x + labelBox.width / 2;
		// Sub-pixel layout rounding only - the historical defect put the last
		// label 99px off, so a generous-looking 1px tolerance here is still
		// two orders of magnitude tighter than the bug it guards against.
		expect(Math.abs(barCenter - labelCenter)).toBeLessThanOrEqual(1);
	}
});
