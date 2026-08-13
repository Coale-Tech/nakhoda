import { test, expect } from "@playwright/test";

/**
 * Phase 5 gate (`12-build-plan.md` §5): "every operation in the grammar is
 * inspectable and editable, and a user can correct one wrong step and
 * re-run without retyping the question." The composer is a sibling of the
 * inspector, never touched by the edit/save/re-run path - this asserts
 * that structurally, not just that the confirmation text appears.
 */
test("a wrong operation step is corrected and re-run without retyping the question", async ({ page }) => {
	await page.goto("./");
	const composer = page.locator(".composer-input");
	await expect(composer).toHaveText("");

	await page.getByRole("button", { name: /Inspect \d+ steps/ }).click();
	const inspector = page.locator(".inspector");
	await expect(inspector).toBeVisible();

	// Every editable op exposes an "Edit" affordance; the injected permission
	// filter (the last row) must not - it is not the user's step to change.
	const editableOps = inspector.locator(".op:has(.op-edit)");
	const opCount = await inspector.locator(".op").count();
	expect(await editableOps.count()).toBe(opCount - 1);

	const rerunButton = inspector.getByRole("button", { name: "Edit & re-run" });
	await expect(rerunButton).toBeDisabled(); // nothing edited yet

	// Correct the second step (`docstatus == 1`) in place.
	const secondOp = inspector.locator(".op").nth(1);
	const originalKind = (await secondOp.locator(".op-kind span").first().textContent()).trim();
	await secondOp.locator(".op-edit").click();
	const textarea = secondOp.locator(".op-edit-input");
	await textarea.fill("docstatus == 1\nand company == 'Nakhoda Inc'");
	await secondOp.getByRole("button", { name: "Save" }).click();

	// The corrected row - and only that row - is marked edited.
	await expect(secondOp.locator(".op-edited")).toBeVisible();
	await expect(secondOp.locator(".op-expr")).toContainText("Nakhoda Inc");
	const otherEdited = await inspector.locator(".op-edited").count();
	expect(otherEdited).toBe(1);
	expect((await secondOp.locator(".op-kind span").first().textContent()).trim()).toBe(originalKind);

	// Re-run fires without the composer ever receiving input.
	await expect(rerunButton).toBeEnabled();
	await rerunButton.click();
	await expect(inspector.locator(".rerun-hint")).toContainText("never retyped");
	await expect(composer).toHaveText("");
});
