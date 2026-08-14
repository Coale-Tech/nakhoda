import { test, expect } from "@playwright/test";
import { askQuestion, openInspector } from "./fixtures/agent.js";

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

test.fixme(
	"assumptions, ambiguity prompt and permission notice render with the answer",
	async ({ page }) => {
		/**
		 * Unrunnable against the shipped build, and not because of the test:
		 * `nakhoda.api.agent.ask` returns no assumption list, no ambiguity
		 * counterfactual and no permission-exclusion count, so `src/agent.js`
		 * deliberately leaves `assumptions` / `notice` unset rather than invent
		 * them client-side (see its docstring). `AssumptionsBlock.vue`,
		 * `AssumptionRow.vue`, `AmbiguityPrompt.vue` and `PermissionNotice.vue`
		 * exist and are wired into `Turn.vue`'s slots; nothing fills them.
		 *
		 * Unblocked by: `engine/permissions.py` reporting the rows it removed,
		 * and the generator emitting its assumption set - then this asserts the
		 * §1/§3 surfaces on real data.
		 */
		await askQuestion(page);
		const card = page.locator(".answer").first();
		await expect(card.locator(".assumption-list")).toBeVisible();
		await expect(card.locator(".ambiguity").getByRole("button")).toHaveCount(2);
		await expect(card.locator(".perm-note")).toContainText(/records?.*outside your/);
	},
);
