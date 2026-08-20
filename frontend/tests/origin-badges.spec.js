import { test, expect } from "@playwright/test";
import { askQuestion, askInjectedQuestion, openInspector } from "./fixtures/agent.js";

/**
 * Phase 5 gate (`12-build-plan.md` §5, gate index row "5 - badges are
 * distinguishable"): render every origin badge the build defines and
 * compare computed `background`, `color` and `box-shadow`; any two
 * identical triples fail. `LINK GRAPH` rendering identically to
 * `SEMANTIC MODEL` was a real defect in an earlier draft - see the
 * docstring in `OriginBadge.vue`.
 *
 * Two origins ship. `src/agent.js:buildInspector` stamps every operation
 * `origin: "model"`, because the pipeline the audit record stores does not
 * distinguish a step lifted from the question from one the model chose.
 * `engine/permissions.py`'s `injected()` now reports which tables a
 * row-level filter touched, so `buildInspector` appends a read-only
 * `origin: "injected"` row per entry whenever `ask.injected` is non-empty.
 * `from question` and `link graph` remain unmet.
 */
test("every operation carries an origin badge, and none is fabricated", async ({ page }) => {
	await askQuestion(page);
	const inspector = await openInspector(page);

	const ops = inspector.locator(".op");
	const badges = inspector.locator(".op-origin");
	await expect(badges).toHaveCount(await ops.count());

	// All four appearances exist in `OriginBadge.vue`; only the one the run
	// actually reports is rendered. A second label appearing here means
	// either the engine got richer (update this test) or the frontend started
	// inventing provenance (fix the frontend).
	const labels = new Set((await badges.allTextContents()).map((t) => t.trim().toLowerCase()));
	expect([...labels]).toEqual(["semantic model"]);
});

test("a permission filter compiled into the query renders an injected origin badge", async ({ page }) => {
	await askInjectedQuestion(page);
	const inspector = await openInspector(page);

	const ops = inspector.locator(".op");
	const badges = inspector.locator(".op-origin");
	await expect(badges).toHaveCount(await ops.count());

	const labels = (await badges.allTextContents()).map((t) => t.trim().toLowerCase());
	expect(labels).toContain("semantic model");
	expect(labels).toContain("injected");
});

test.fixme("no two origin badges share a background/color/box-shadow triple", async ({ page }) => {
	/**
	 * Unblocked by the engine reporting per-operation provenance: a
	 * `from question` / `link graph` distinction in the stored pipeline.
	 * `injected` now ships (see the test above) but only ever appears
	 * alongside `model` rows, never all four together, since a compiled
	 * pipeline still doesn't record whether an operation was lifted from
	 * the question or picked by the model. Once that distinction exists,
	 * all four appearances render in one screen and this measures them
	 * pairwise, as it did against the mockup.
	 */
	await askQuestion(page);
	const inspector = await openInspector(page);
	const badges = inspector.locator(".op-origin");
	const count = await badges.count();
	expect(count).toBeGreaterThanOrEqual(4);

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
			expect(style, `"${label}" and "${otherLabel}" origin badges render identically`).not.toBe(otherStyle);
		}
		triples.set(label, style);
	}
	expect([...triples.keys()].sort()).toEqual(["from question", "injected", "link graph", "semantic model"].sort());
});
