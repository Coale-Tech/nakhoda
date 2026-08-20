import { test, expect } from "@playwright/test";
import { askQuestion, askNoticeQuestion, askAssumptionsQuestion, openInspector } from "./fixtures/agent.js";

/**
 * Phase 5 gate (`12-build-plan.md` §5): "provenance is rendered, not just
 * logged... An answer must show its assumptions, the rows its permissions
 * removed, and the realised SQL before execution." `14-frontend-design.md`
 * §0 contrasts this with every competitor's chat bubble, which "hides the
 * SQL behind a disclosure triangle" - an unlabelled expand affordance over
 * unknown content. Nakhoda's answer card differs in kind, not degree: the
 * provenance strip is unconditional, and the realised SQL sits one
 * *labelled* action away ("Inspect 3 steps", not a triangle).
 */
test("the receipt renders unconditionally with the answer", async ({ page }) => {
	await askQuestion(page);
	const card = page.locator(".answer").first();

	// The receipt - tier, model, operation count, query time, run id - is
	// visible with the answer, before any "Inspect" click.
	const receipt = card.locator(".receipt");
	await expect(receipt).toBeVisible();
	await expect(receipt).toContainText("operations");
	await expect(receipt).toContainText("standard");
	await expect(receipt).toContainText("NAK-RUN-0001");
});

test("the realised SQL is one labelled action away, not an unlabelled disclosure triangle", async ({ page }) => {
	await askQuestion(page);

	// Before interaction the inspector is not mounted at all (`AskPage.vue`
	// mounts it per inspected turn), so its SQL block cannot be on screen.
	await expect(page.locator(".sql")).toHaveCount(0);

	const inspectButton = page.getByRole("button", { name: /Inspect \d+ steps/ });
	await expect(inspectButton).toBeVisible();
	// A labelled action, not a bare glyph: it names what it opens.
	expect(await inspectButton.textContent()).toMatch(/Inspect \d+ steps/);

	const inspector = await openInspector(page);
	await expect(inspector.locator(".sql")).toContainText("SELECT");
	// Every operation the run recorded is listed, numbered, with its origin.
	await expect(inspector.locator(".op")).toHaveCount(3);
	await expect(inspector.locator(".op-origin").first()).toBeVisible();
	// Cost and scope, read off the audit record rather than recomputed here.
	await expect(inspector.locator(".kv")).toHaveCount(6);
	await expect(inspector).toContainText("412ms");
});

test("the permission notice renders with the answer when rows were excluded", async ({ page }) => {
	/**
	 * `nakhoda.engine.pipeline.notice` (backend) reports the rows and, when
	 * the pipeline names one clear sum measure, the amount a row-level
	 * permission removed from this exact query - `14-frontend-design.md` §3's
	 * answer to Insights issue #919. `src/agent.js` maps it straight through
	 * to `PermissionNotice.vue`; nothing here fabricates it.
	 */
	await askNoticeQuestion(page);
	const card = page.locator(".answer").first();
	await expect(card.locator(".perm-note")).toContainText(/records? \(.*\) are outside your territory permissions/);
});

test("assumptions and the ambiguity prompt render with the answer", async ({ page }) => {
	/**
	 * `manager.ask()` validates the model's `ops_annotated` envelope through
	 * `driver._valid_assumptions` and threads the result onto the response
	 * (`nakhoda/agent/manager.py`); `src/agent.js`'s `buildAssumptions` reshapes
	 * the flat list into what `AssumptionsBlock.vue`/`AssumptionRow.vue` render,
	 * and the first `needs_you` entry carrying a counterfactual earns the one
	 * `AmbiguityPrompt.vue` slot the component design allows (§1: two visual
	 * states, "applied" grey vs "needs you" amber + inline prompt).
	 */
	await askAssumptionsQuestion(page);
	const card = page.locator(".answer").first();
	await expect(card.locator(".assumption-list")).toBeVisible();
	await expect(card.locator(".assumption-list .assumption")).toHaveCount(2);
	await expect(card.locator(".ambiguity").getByRole("button")).toHaveCount(2);
});
