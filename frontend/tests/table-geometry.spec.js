import { test, expect } from "@playwright/test";
import { askQuestion, bigAnswer } from "./fixtures/agent.js";

/**
 * The result table is the one data surface that ships, so it carries the
 * "measure the rendered DOM, don't eyeball it" gate (`12-build-plan.md` §5)
 * that `chart-geometry.spec.js` holds for charts.
 *
 * This is not hypothetical: migrating `DataTable.vue` onto `frappe-ui/list`
 * shipped a table whose every cell stacked vertically, because the family's
 * structural CSS (`[data-slot="list-row"] { display: grid }` and the
 * `--list-columns` tracks) lives in a separate entry - `frappe-ui/list-style.css`
 * - that this app's build did not pull in. The screen still looked like a
 * table at a glance: header row, right-shaded surface, plausible spacing.
 * Only measuring `grid-template-columns` and the cell boxes showed it.
 */
test("the result table is a real grid with equal tracks and right-aligned numbers", async ({
	page,
}) => {
	await askQuestion(page);

	const row = page.locator('.answer [data-slot="list-row"]').first();
	const header = page.locator('.answer [data-slot="list-header"]');

	const geometry = await row.evaluate((el) => {
		const s = getComputedStyle(el);
		return {
			display: s.display,
			tracks: s.gridTemplateColumns,
			height: el.getBoundingClientRect().height,
		};
	});
	// Grid, not stacked blocks: the defect above rendered `display: block`
	// with `grid-template-columns: none`.
	expect(geometry.display).toBe("grid");
	const tracks = geometry.tracks.split(" ").map(parseFloat);
	expect(tracks).toHaveLength(3);
	// Three `minmax(0, 1fr)` columns resolve equal, so a column that silently
	// collapses to its content width fails here.
	for (const t of tracks) expect(Math.abs(t - tracks[0])).toBeLessThanOrEqual(1);
	// `:row-height="36"` is honoured by the family, not by a hand-set class.
	expect(Math.round(geometry.height)).toBe(36);

	// Header cells sit over the columns they name: same left edges, in order.
	const headerX = await header
		.locator('[data-slot="list-header-cell"]')
		.evaluateAll((els) => els.map((e) => Math.round(e.getBoundingClientRect().x)));
	const cellX = await row
		.locator('[data-slot="list-cell"]')
		.evaluateAll((els) => els.map((e) => Math.round(e.getBoundingClientRect().x)));
	expect(headerX).toHaveLength(3);
	expect(cellX).toHaveLength(3);
	for (let i = 0; i < 3; i++) expect(Math.abs(headerX[i] - cellX[i])).toBeLessThanOrEqual(12);

	// Numeric columns right-align on a shared edge across every row, so
	// digits line up - `DESIGN.md` "Alignment over flow" plus `tabular-nums`.
	const rightEdges = await page.locator('.answer [data-slot="list-row"]').evaluateAll((rows) =>
		rows.map((r) => {
			const cells = r.querySelectorAll('[data-slot="list-cell"]');
			const last = cells[cells.length - 1].getBoundingClientRect();
			return Math.round(last.x + last.width);
		}),
	);
	expect(rightEdges.length).toBeGreaterThan(1);
	for (const edge of rightEdges) expect(edge).toBe(rightEdges[0]);
});

/**
 * A live regression, not a hypothetical: asked "How many sales invoices are
 * there?" on the `jkm` bench, the pipeline answered with a bare `source`
 * operation, so `ask()` returned all 3,730 invoices with all 249 columns.
 * `DataTable.vue` rendered every one - 928,270 `ListCell` components - and
 * wedged the main thread hard enough that the browser tab had to be killed
 * three times before the cause was measured rather than guessed.
 *
 * The cap belongs in `agent.js:buildTable`, at the shaping boundary, because
 * the frontend has to survive whatever shape the pipeline emits.
 */
test("a result larger than the render cap shows the first 100 rows and says so", async ({
	page,
}) => {
	await askQuestion(page, "Every invoice", bigAnswer(250));

	// Exactly the cap, not 250: the row count here is what the main thread pays.
	await expect(page.locator('.answer [data-slot="list-row"]')).toHaveCount(100);
	await expect(page.locator(".answer .table-wrap")).toContainText(
		"Showing the first 100 of 250 rows",
	);
	// Nothing is hidden by capping: the metric still reports the true size, so
	// the reader is never told the result was 100 rows.
	await expect(page.locator(".answer .metric")).toContainText("250");
});

/**
 * `agent/charts.py:semantics` resolves a column against the DocType it came
 * from and returns Frappe's own field label. Both dashboard surfaces already
 * consume that map; the Ask route was returning it and dropping it, heading
 * every table with the raw column name a `summarize` step happens to mint.
 *
 * Three columns, so `charts.pick` leaves this a table rather than a chart.
 */
test("a table is headed by the field labels the semantic layer resolved", async ({ page }) => {
	await askQuestion(page, "Revenue by territory this quarter", {
		columns: ["territory", "n", "grand_total"],
		rows: [
			{ territory: "Kenya", n: 412, grand_total: 12400000 },
			{ territory: "Tanzania", n: 208, grand_total: 6100000 },
		],
		row_count: 2,
		field_display_names: { territory: "Territory", grand_total: "Grand Total" },
	});

	const header = page.locator('.answer [data-slot="list-header"]');
	await expect(header).toContainText("Grand Total");
	// `n` has no label - the count is not a field on anything - so it stays
	// verbatim rather than being prettified into something invented.
	await expect(header).toContainText("n");
	await expect(header).not.toContainText("grand_total");
});
