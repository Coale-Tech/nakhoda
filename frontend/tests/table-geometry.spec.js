import { test, expect } from "@playwright/test";
import { askQuestion } from "./fixtures/agent.js";

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
test("the result table is a real grid with equal tracks and right-aligned numbers", async ({ page }) => {
	await askQuestion(page);

	const row = page.locator('.answer [data-slot="list-row"]').first();
	const header = page.locator('.answer [data-slot="list-header"]');

	const geometry = await row.evaluate((el) => {
		const s = getComputedStyle(el);
		return { display: s.display, tracks: s.gridTemplateColumns, height: el.getBoundingClientRect().height };
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
	const headerX = await header.locator('[data-slot="list-header-cell"]').evaluateAll((els) =>
		els.map((e) => Math.round(e.getBoundingClientRect().x)),
	);
	const cellX = await row.locator('[data-slot="list-cell"]').evaluateAll((els) =>
		els.map((e) => Math.round(e.getBoundingClientRect().x)),
	);
	expect(headerX).toHaveLength(3);
	expect(cellX).toHaveLength(3);
	for (let i = 0; i < 3; i++) expect(Math.abs(headerX[i] - cellX[i])).toBeLessThanOrEqual(12);

	// Numeric columns right-align on a shared edge across every row, so
	// digits line up - `DESIGN.md` "Alignment over flow" plus `tabular-nums`.
	const rightEdges = await page
		.locator('.answer [data-slot="list-row"]')
		.evaluateAll((rows) =>
			rows.map((r) => {
				const cells = r.querySelectorAll('[data-slot="list-cell"]');
				const last = cells[cells.length - 1].getBoundingClientRect();
				return Math.round(last.x + last.width);
			}),
		);
	expect(rightEdges.length).toBeGreaterThan(1);
	for (const edge of rightEdges) expect(edge).toBe(rightEdges[0]);
});
