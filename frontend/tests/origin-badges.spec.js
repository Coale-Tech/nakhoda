import { test, expect } from "@playwright/test";

/**
 * Phase 5 gate (`12-build-plan.md` §5, gate index row "5 - badges are
 * distinguishable"): render every origin badge the build defines and
 * compare computed `background`, `color` and `box-shadow`; any two
 * identical triples fail. `LINK GRAPH` rendering identically to
 * `SEMANTIC MODEL` (both sharing `.o-model`) was a real defect in an
 * earlier draft - see the docstring in `OriginBadge.vue`.
 */
test("no two origin badges share a background/color/box-shadow triple", async ({ page }) => {
	await page.goto("./");
	await page.getByRole("button", { name: /Inspect \d+ steps/ }).click();
	await expect(page.locator(".inspector")).toBeVisible();

	const badges = page.locator(".op-origin");
	const count = await badges.count();
	expect(count).toBeGreaterThanOrEqual(4); // question, model, link, injected all present in the pipeline

	const triples = new Map(); // label -> "bg|color|shadow"
	for (let i = 0; i < count; i++) {
		const badge = badges.nth(i);
		const label = (await badge.textContent()).trim().toLowerCase();
		const style = await badge.evaluate((el) => {
			const s = getComputedStyle(el);
			return `${s.backgroundColor}|${s.color}|${s.boxShadow}`;
		});
		if (triples.has(label)) {
			expect(triples.get(label), `two badges labelled "${label}" render differently`).toBe(style);
			continue;
		}
		for (const [otherLabel, otherStyle] of triples) {
			if (otherLabel === label) continue;
			expect(style, `"${label}" and "${otherLabel}" origin badges render identically`).not.toBe(otherStyle);
		}
		triples.set(label, style);
	}

	// The four labels the build defines today (`14-frontend-design.md` §2).
	expect([...triples.keys()].sort()).toEqual(
		["from question", "injected", "link graph", "semantic model"].sort(),
	);
});
