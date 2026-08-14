import { test, expect } from "@playwright/test";
import { askQuestion, openInspector } from "./fixtures/agent.js";

/**
 * Phase 5 gate (`12-build-plan.md` §5): "every operation in the grammar is
 * inspectable and editable, and a user can correct one wrong step and
 * re-run without retyping the question."
 *
 * Inspectable ships. Editable does not: `src/agent.js:buildInspector` sets
 * `editable: false` on every operation, because `nakhoda.api.agent.ask`
 * takes a question - there is no endpoint that accepts an edited operation
 * list, so an Edit affordance would collect a correction and silently drop
 * it. The gate below is therefore split: what ships is asserted, and the
 * unmet half is recorded as such rather than dressed up.
 */
test("no operation offers an Edit affordance while re-run is unwired", async ({ page }) => {
	await askQuestion(page);
	const inspector = await openInspector(page);

	const ops = inspector.locator(".op");
	await expect(ops).toHaveCount(3);
	// Inspectable: every step is on screen with its kind and expression.
	await expect(ops.first().locator(".op-expr")).toBeVisible();

	// Not editable, and honestly so: no Edit button, no edit textarea, no
	// "Edit & re-run" action. This assertion exists to fail the moment one of
	// them is re-enabled without an engine that accepts edited operations -
	// the failure mode being a control that looks like it corrects the answer
	// above it and does nothing.
	await expect(inspector.locator(".op-edit")).toHaveCount(0);
	await expect(inspector.locator(".op-edit-input")).toHaveCount(0);
	await expect(inspector.getByRole("button", { name: /Edit & re-run/ })).toHaveCount(0);
});

test("the composer is never touched by the inspector path", async ({ page }) => {
	await askQuestion(page, "Revenue by territory this quarter");
	const composer = page.locator("textarea.composer-input");
	// Submitting clears it; opening and closing the inspector must not refill
	// it - the correction path is a sibling of the composer, not a detour
	// through it (`14-frontend-design.md` §2).
	await expect(composer).toHaveValue("");
	const inspector = await openInspector(page);
	await inspector.getByRole("button", { name: "Close" }).click();
	await expect(inspector).toHaveCount(0);
	await expect(composer).toHaveValue("");
});

test.fixme("a wrong operation step is corrected and re-run without retyping the question", async ({ page }) => {
	/**
	 * Unblocked by an engine entry point that takes an operation list:
	 * `nakhoda/agent/manager.py` exposes `ask(question)` only, and
	 * `nakhoda/api/agent.py` whitelists just that. Once a `rerun(operations)`
	 * surface exists, flip `editable` in `buildInspector` and this runs:
	 * every non-injected step gets an Edit affordance, saving marks that row
	 * edited, and re-run fires with the composer still empty.
	 */
	await askQuestion(page);
	const inspector = await openInspector(page);
	const secondOp = inspector.locator(".op").nth(1);
	await secondOp.locator(".op-edit").click();
	await secondOp.locator(".op-edit-input").fill("docstatus == 1\nand company == 'Nakhoda Inc'");
	await secondOp.getByRole("button", { name: "Save" }).click();
	await expect(secondOp.locator(".op-expr")).toContainText("Nakhoda Inc");
	await expect(inspector.locator(".op-edited")).toHaveCount(1);
	await inspector.getByRole("button", { name: "Edit & re-run" }).click();
	await expect(page.locator("textarea.composer-input")).toHaveValue("");
});
