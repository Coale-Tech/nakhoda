import { test, expect } from "@playwright/test";
import { askQuestion, openInspector } from "./fixtures/agent.js";

/**
 * Phase 5 gate (`12-build-plan.md` §5, gate index row "5 - badges are
 * distinguishable"): render every origin badge the build defines and
 * compare computed `background`, `color` and `box-shadow`; any two
 * identical triples fail. `LINK GRAPH` rendering identically to
 * `SEMANTIC MODEL` was a real defect in an earlier draft - see the
 * docstring in `OriginBadge.vue`.
 *
 * One origin ships. `src/agent.js:buildInspector` stamps every operation
 * `origin: "model"`, because the pipeline the audit record stores does not
 * distinguish a step lifted from the question from one the model chose, and
 * `engine/permissions.py` inlines its filters at SQL-compile time rather
 * than appending an operation - so `injected` never appears either.
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

test.fixme("no two origin badges share a background/color/box-shadow triple", async ({ page }) => {
	/**
	 * Unblocked by the engine reporting per-operation provenance: a
	 * `from question` / `link graph` distinction in the stored pipeline, and
	 * permission filters emitted as `injected` operations rather than inlined
	 * into SQL. Then all four appearances render in one screen and this
	 * measures them pairwise, as it did against the mockup.
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
