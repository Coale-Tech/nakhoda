import { test, expect } from "@playwright/test";

/**
 * Phase 5 gate (`12-build-plan.md` §5): "provenance is rendered, not just
 * logged... An answer must show its assumptions, the rows its permissions
 * removed, and the realised SQL before execution." `14-frontend-design.md`
 * §0 contrasts this with every competitor's chat bubble, which "hides the
 * SQL behind a disclosure triangle" - an unlabelled expand affordance over
 * unknown content. Nakhoda's answer card differs in kind, not degree: the
 * assumption taxonomy, ambiguity prompt, permission notice and receipt are
 * unconditional - present the instant the answer renders, no interaction
 * required - and the realised SQL sits one *labelled* action away
 * ("Inspect 5 steps", not a triangle), naming exactly what it opens.
 */
test("assumptions, permission notice and receipt render unconditionally with the answer", async ({ page }) => {
	await page.goto("./");

	const card = page.locator(".answer").first();
	await expect(card.locator(".assumption-list")).toBeVisible();

	// Assumption rows are visible without expanding anything.
	const rows = card.locator(".assumption");
	const rowCount = await rows.count();
	expect(rowCount).toBeGreaterThan(0);
	for (let i = 0; i < rowCount; i++) {
		await expect(rows.nth(i)).toBeVisible();
	}

	// The ambiguity prompt surfaces the unstated choice as a decision (two
	// buttons), not a footnote - both actions must be immediately clickable.
	const ambiguity = card.locator(".ambiguity");
	await expect(ambiguity).toBeVisible();
	await expect(ambiguity.getByRole("button")).toHaveCount(2);

	// The permission notice - rows removed - is on the card, not the inspector.
	await expect(card.locator(".perm-note")).toBeVisible();
	await expect(card.locator(".perm-note")).toContainText(/records?.*outside your/);

	// The receipt (operations, tables, query time, tokens, cost) is visible
	// with the answer, before any "Inspect" click.
	const receipt = card.locator(".receipt");
	await expect(receipt).toBeVisible();
	await expect(receipt).toContainText("operations");
	await expect(receipt).toContainText("tokens");
});

test("the realised SQL is one labelled action away, not an unlabelled disclosure triangle", async ({ page }) => {
	await page.goto("./");

	// Before interaction: the inspector (and its SQL block) exists but is
	// hidden via the `hidden` attribute - Inspector is a single persistent
	// instance reused across turns (`Inspector.vue`), not re-mounted per
	// click, so DOM presence isn't the contract; visibility is.
	await expect(page.locator(".sql")).not.toBeVisible();

	const inspectButton = page.getByRole("button", { name: /Inspect \d+ steps/ });
	await expect(inspectButton).toBeVisible();
	// A labelled action, not a bare glyph: it names what it opens.
	expect(await inspectButton.textContent()).toMatch(/Inspect \d+ steps/);

	await inspectButton.click();
	const sql = page.locator(".sql");
	await expect(sql).toBeVisible();
	await expect(sql).toContainText("not executed yet");
	await expect(sql).toContainText("SELECT");

	// The injected permission filter is highlighted inline in the SQL itself,
	// not summarised away - `apply_row_permissions` made visible (§3.2).
	await expect(page.locator(".sql .inj")).toBeVisible();
	await expect(page.locator(".sql .inj")).toContainText("territory IN");
});
