import { expect, test } from "@playwright/test";
import { frappeError, mockBoot } from "./fixtures/data_store.js";
import { COVERAGE, mockSemantic, ORPHAN_CHILD, SALES_INVOICE } from "./fixtures/semantic.js";
import { mockSettings } from "./fixtures/settings.js";

/**
 * The Semantic Model tab: the surface where a person tells this site what its
 * own words mean, and the only settings tab whose edits change an *answer*.
 *
 * The design contract (`docs/design/14-frontend-design.md` §2) asks for three
 * things this file grades, because each one is a measurement the tab is
 * claiming rather than a layout choice:
 *
 * 1. **Coverage of the auto-derivation.** Four counts, from the backend, and
 *    the two a save moves (`curated`, `with_synonyms`) are patched locally
 *    rather than re-fetched - `coverage()` costs a `row_counts()` scan. A
 *    strip that showed a stale number after a save would be worse than one
 *    that showed none.
 * 2. **Per-entity grain warnings.** A child table with no reachable parent is
 *    dropped from the index by retrieval, so describing it changes nothing.
 *    The tab has to say so on the row *and* in the editor.
 * 3. **The derived domain, verbatim.** `link: tabCustomer.name` is exactly the
 *    string the model is handed; a paraphrase here would describe a schema the
 *    model never sees.
 *
 * Plus the one property that is not about display: a stale form must fail
 * loudly. The backend refuses a payload naming a column the document no longer
 * has (`api/semantic.py:save_model`), and this tab is the client that can hold
 * such a payload open for an hour.
 */
async function openSemanticTab(page, options) {
	await mockBoot(page, { isAdmin: true });
	await mockSettings(page);
	await mockSemantic(page, options);
	await page.goto("./");
	await page.getByRole("button", { name: "Settings" }).click();
	await page.getByRole("button", { name: "Semantic Model" }).click();
	await expect(page.getByRole("heading", { name: "Semantic Model" })).toBeVisible();
	return page;
}

/** The editor dialog for one document, opened by clicking its row. */
async function openDocument(page, name) {
	await page.getByText(name, { exact: true }).first().click();
	await expect(page.getByRole("heading", { name })).toBeVisible();
	return page;
}

test.describe("settings: Semantic Model", () => {
	test("the coverage strip reports the backend's counts", async ({ page }) => {
		await openSemanticTab(page);

		// Anchored on the card's own label, not a substring: the header's filter
		// checkbox reads "Written by hand only", which `hasText` would match too.
		const card = (label) => page.getByText(label, { exact: true }).locator("..");
		await expect(card("Documents Used")).toContainText(String(COVERAGE.used));
		await expect(card("Modelled")).toContainText(String(COVERAGE.modelled));
		await expect(card("Written By Hand")).toContainText(String(COVERAGE.curated));
		await expect(card("With Synonyms")).toContainText(String(COVERAGE.with_synonyms));
	});

	test("a curated document is badged and a generated one is not", async ({ page }) => {
		await openSemanticTab(page);

		const invoice = page.getByRole("row").filter({ hasText: SALES_INVOICE.doctype_name });
		await expect(invoice.getByText("Written")).toBeVisible();

		const child = page.getByRole("row").filter({ hasText: ORPHAN_CHILD.doctype_name });
		await expect(child.getByText("Written")).toHaveCount(0);
	});

	test("a child table with no parent is flagged on the row and in the editor", async ({ page }) => {
		await openSemanticTab(page);

		const child = page.getByRole("row").filter({ hasText: ORPHAN_CHILD.doctype_name });
		await expect(child.getByText("No parent")).toBeVisible();

		await openDocument(page, ORPHAN_CHILD.doctype_name);
		await expect(page.getByText("retrieval drops it")).toBeVisible();
	});

	test("search filters by document and by the synonyms a person wrote", async ({ page }) => {
		await openSemanticTab(page);

		const search = page.getByPlaceholder("Search documents");
		await search.fill("Payment");
		await expect(page.getByText(SALES_INVOICE.doctype_name, { exact: true })).toHaveCount(0);

		// Synonyms are searchable because they are what a curator remembers writing,
		// not the DocType name they wrote them on.
		await search.fill("turnover");
		await expect(page.getByText(SALES_INVOICE.doctype_name, { exact: true }).first()).toBeVisible();
		await expect(page.getByText(ORPHAN_CHILD.doctype_name, { exact: true })).toHaveCount(0);
	});

	test("the hand-written filter keeps only curated rows", async ({ page }) => {
		await openSemanticTab(page);

		await page.getByText("Written by hand only").click();
		await expect(page.getByText(SALES_INVOICE.doctype_name, { exact: true }).first()).toBeVisible();
		await expect(page.getByText(ORPHAN_CHILD.doctype_name, { exact: true })).toHaveCount(0);
	});

	test("the editor shows the column domain verbatim and the generated fields read-only", async ({ page }) => {
		await openSemanticTab(page);
		await openDocument(page, SALES_INVOICE.doctype_name);

		await expect(page.getByTitle("link: tabCustomer.name")).toBeVisible();
		await expect(page.getByText("2,624")).toBeVisible();
		// A column no row on this site fills is flagged, because retrieval prunes it
		// and a curator naming it would be naming something the model never sees.
		await expect(page.getByTitle("No row on this site has a value here - retrieval prunes it")).toBeVisible();
	});

	test("Save is disabled until something is edited, then persists and settles", async ({ page }) => {
		await openSemanticTab(page);
		await openDocument(page, ORPHAN_CHILD.doctype_name);

		const save = page.getByRole("button", { name: "Save" });
		await expect(save).toBeDisabled();

		await page.getByPlaceholder("revenue, turnover, topline, billings").fill("reconciliation, matching");
		await expect(save).toBeEnabled();

		await save.click();
		await expect(save).toBeDisabled();
		// The row and the strip are patched in place rather than re-fetched.
		await expect(page.getByText("Written by hand").first()).toBeVisible();
	});

	test("a saved synonym reaches the list without a reload", async ({ page }) => {
		await openSemanticTab(page);
		await openDocument(page, ORPHAN_CHILD.doctype_name);

		await page.getByPlaceholder("revenue, turnover, topline, billings").fill("matching");
		await page.getByRole("button", { name: "Save" }).click();
		await page.getByRole("button", { name: "Close" }).click();

		const child = page.getByRole("row").filter({ hasText: ORPHAN_CHILD.doctype_name });
		await expect(child).toContainText("matching");
		await expect(child.getByText("Written")).toBeVisible();
	});

	test("a column synonym is written for the column it was typed on", async ({ page }) => {
		await openSemanticTab(page);
		await openDocument(page, SALES_INVOICE.doctype_name);

		const request = page.waitForRequest((r) => r.url().includes("semantic.save_model"));
		await page.getByPlaceholder("—").first().fill("buyer");
		await page.getByRole("button", { name: "Save" }).click();

		const sent = JSON.parse((await request).postDataJSON().field_synonyms);
		expect(Object.keys(sent)).toEqual(["customer"]);
		expect(sent.customer).toBe("buyer");
	});

	test("a rejected save reports the backend's own message and keeps the editor open", async ({ page }) => {
		await openSemanticTab(page);
		await page.route("**/api/v2/method/nakhoda.api.semantic.save_model**", (route) =>
			route.fulfill(frappeError("ValidationError", "Sales Invoice has no column po_no")),
		);
		await openDocument(page, SALES_INVOICE.doctype_name);

		await page.getByPlaceholder("revenue, turnover, topline, billings").fill("stale client");
		await page.getByRole("button", { name: "Save" }).click();

		await expect(page.getByText("Sales Invoice has no column po_no")).toBeVisible();
		await expect(page.getByRole("heading", { name: SALES_INVOICE.doctype_name })).toBeVisible();
	});

	test("Regenerate offers both passes and reports what was queued", async ({ page }) => {
		await openSemanticTab(page);

		await page.getByRole("button", { name: "Regenerate" }).click();
		await expect(page.getByText("Refresh described documents")).toBeVisible();
		await page.getByText("Seed every used document").click();

		await expect(page.getByText(`${COVERAGE.used}`).first()).toBeVisible();
	});

	test("a pass already running says so instead of claiming a new one", async ({ page }) => {
		await openSemanticTab(page, { queued: { queued: false, reason: "in_progress" } });

		await page.getByRole("button", { name: "Regenerate" }).click();
		await page.getByText("Refresh described documents").click();

		await expect(page.getByText(/already running/i)).toBeVisible();
	});

	test("an empty site says how to seed itself rather than showing an empty table", async ({ page }) => {
		await openSemanticTab(page, {
			docs: [],
			coverage: { ...COVERAGE, modelled: 0, curated: 0, with_synonyms: 0 },
		});

		await expect(page.getByText(/Regenerate/).last()).toBeVisible();
		await expect(page.getByText("Nothing modelled yet.")).toBeVisible();
	});
});
