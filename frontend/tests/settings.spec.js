import { expect, test } from "@playwright/test";
import { mockAIStatus, mockSettings, SETTINGS_ROW } from "./fixtures/settings.js";

/**
 * Settings is a dialog opened from `AppSidebar.vue`'s footer link, not a
 * routed page - mirrors Insights, whose own settings screen has no URL of
 * its own either. Every test opens it the same way: land on any page, click
 * the "Settings" trigger, wait for its General tab (the default active tab).
 */
async function openSettings(page) {
	await page.goto("./");
	await page.getByRole("button", { name: "Settings" }).click();
	await expect(page.getByText("Max Rows Returned")).toBeVisible();
}

/** The AI Provider tab, with its live-state calls mocked. */
async function openAITab(page, options) {
	await mockSettings(page);
	await mockAIStatus(page, options);
	await openSettings(page);
	await page.getByRole("button", { name: "AI Provider" }).click();
	await expect(page.getByRole("heading", { name: "AI Provider" })).toBeVisible();
}

test.describe("settings", () => {
	test("loads current limits and permission fields", async ({ page }) => {
		await mockSettings(page);
		await openSettings(page);
		const maxRows = page.locator("input[type='number']").first();
		await expect(maxRows).toHaveValue(String(SETTINGS_ROW.max_rows));
	});

	test("editing a field enables Save, saving persists it and disables Save again", async ({ page }) => {
		await mockSettings(page);
		await openSettings(page);

		const saveButton = page.getByRole("button", { name: "Save" });
		await expect(saveButton).toBeDisabled();

		const maxRows = page.locator("input[type='number']").first();
		await maxRows.fill("250000");
		await maxRows.blur();
		await expect(saveButton).toBeEnabled();

		await saveButton.click();
		await expect(saveButton).toBeDisabled();
	});

	test("the Permissions tab switches without losing the General tab's state", async ({ page }) => {
		await mockSettings(page);
		await openSettings(page);

		const maxRows = page.locator("input[type='number']").first();
		await maxRows.fill("250000");
		await maxRows.blur();

		await page.getByRole("button", { name: "Permissions" }).click();
		await expect(page.getByText("Fail On Unreadable Columns")).toBeVisible();

		await page.getByRole("button", { name: "General" }).click();
		await expect(maxRows).toHaveValue("250000");
	});

	test("the old dead 'Model Provider' field stays gone", async ({ page }) => {
		await mockSettings(page);
		await openSettings(page);
		await expect(page.getByText("Model Provider")).toHaveCount(0);
	});
});

/**
 * The Data Store tab. Insights renders `Enable` as a pill switch and both
 * caps unconditionally (`src2/settings/DataStoreSettings.vue`); this port
 * previously rendered a labelled checkbox and hid the caps behind the
 * switch, so an install that had never written the field showed one Off
 * control and nothing else. These grade both halves of that.
 */
test.describe("settings: Data Store", () => {
	async function openDataStoreTab(page) {
		await mockSettings(page);
		await openSettings(page);
		await page.getByRole("button", { name: "Data Store" }).click();
		await expect(page.getByRole("heading", { name: "Data Store" })).toBeVisible();
	}

	test("Enable is a switch reflecting the saved value, with both caps on screen", async ({ page }) => {
		await openDataStoreTab(page);

		await expect(page.getByRole("switch")).toHaveAttribute("aria-checked", "true");
		await expect(page.getByText("Row Limit", { exact: true })).toBeVisible();
		await expect(page.getByText("Memory Limit", { exact: true })).toBeVisible();
	});

	test("the caps stay reachable with the store disabled", async ({ page }) => {
		await openDataStoreTab(page);

		await page.getByRole("switch").click();
		await expect(page.getByRole("switch")).toHaveAttribute("aria-checked", "false");
		await expect(page.getByText("Row Limit", { exact: true })).toBeVisible();
		await expect(page.getByText("Memory Limit", { exact: true })).toBeVisible();
	});

	test("flipping Enable saves, and flipping back to the saved value is not dirty", async ({ page }) => {
		await openDataStoreTab(page);

		const saveButton = page.getByRole("button", { name: "Save" });
		await expect(saveButton).toBeDisabled();

		// A `Check` field round-trips as 0/1 and the switch's model is a
		// boolean: without `useSettings.js` normalising it, `false !== 0`
		// would leave Save enabled here forever.
		await page.getByRole("switch").click();
		await expect(saveButton).toBeEnabled();
		await page.getByRole("switch").click();
		await expect(saveButton).toBeDisabled();

		await page.getByRole("switch").click();
		await saveButton.click();
		await expect(saveButton).toBeDisabled();
		await expect(page.getByRole("switch")).toHaveAttribute("aria-checked", "false");
	});
});

/**
 * The AI Provider tab is a port of Insights' AI Analytics page: one card per
 * provider, and only the selected provider's own credential/model block on
 * screen. These grade that contract - a control that belongs to a provider
 * nobody selected must not be reachable, because every provider stores its
 * credential in a different field (`nakhoda_settings.json`).
 */
test.describe("settings: AI Provider", () => {
	test("shows the saved provider selected, with its own config block", async ({ page }) => {
		await openAITab(page);

		await expect(page.locator("input[type='radio'][value='openrouter']")).toBeChecked();
		await expect(page.getByRole("heading", { name: "OpenRouter Settings" })).toBeVisible();
		await expect(page.getByRole("heading", { name: "NVIDIA NIM Settings" })).toHaveCount(0);
	});

	test("switching provider swaps which credential block is on screen", async ({ page }) => {
		await openAITab(page);

		await page.locator("input[type='radio'][value='nvidia']").check();
		await expect(page.getByRole("heading", { name: "NVIDIA NIM Settings" })).toBeVisible();
		await expect(page.getByRole("heading", { name: "OpenRouter Settings" })).toHaveCount(0);
		await expect(page.getByPlaceholder("nvapi-...")).toBeVisible();
		await expect(page.getByPlaceholder("sk-or-v1-...")).toHaveCount(0);
	});

	test("editing a model enables Save, and saving disables it again", async ({ page }) => {
		await openAITab(page);

		const saveButton = page.getByRole("button", { name: "Save" });
		await expect(saveButton).toBeDisabled();

		await page.locator("select").first().selectOption("google/gemma-4-31b-it:free");
		await expect(saveButton).toBeEnabled();

		await saveButton.click();
		await expect(saveButton).toBeDisabled();
	});

	test("Test refuses to probe before a key is entered, then reports the result", async ({ page }) => {
		await openAITab(page);

		await page.getByRole("button", { name: "Test" }).click();
		await expect(page.getByText("API key required")).toBeVisible();

		await page.getByPlaceholder("sk-or-v1-...").fill("sk-or-v1-testkey");
		await page.getByRole("button", { name: "Test" }).click();
		await expect(page.getByText("Connected").first()).toBeVisible();
	});

	test("a failed probe reports the backend's own error", async ({ page }) => {
		await openAITab(page, {
			testResult: { success: false, error: "The endpoint rejected this credential (HTTP 401)." },
		});

		await page.getByPlaceholder("sk-or-v1-...").fill("sk-or-v1-badkey");
		await page.getByRole("button", { name: "Test" }).click();
		await expect(page.getByText("The endpoint rejected this credential (HTTP 401).")).toBeVisible();
	});

	test("the usage strip reports what the status endpoint says, not the form", async ({ page }) => {
		await openAITab(page);

		// `ai_quota_used` (12) is the *server's* count, not `daily_ai_quota`
		// (100) which the form owns - the strip must show the former over the
		// latter, so scope to the card rather than matching a bare "12"
		// anywhere on a page full of model ids.
		const quotaCard = page.locator("div").filter({ hasText: "Quota This Window" }).last();
		await expect(quotaCard).toContainText("12");
		await expect(quotaCard).toContainText("/ 100");

		const lastAnswer = page.locator("div").filter({ hasText: "Last Answer" }).last();
		await expect(lastAnswer).not.toContainText("Never");
	});

	test("ChatGPT Subscription mode replaces the API key box with a device login", async ({ page }) => {
		await openAITab(page);

		await page.locator("input[type='radio'][value='openai']").check();
		await expect(page.getByPlaceholder("sk-...").first()).toBeVisible();

		await page.getByRole("combobox").first().selectOption("ChatGPT Subscription");
		await expect(page.getByRole("button", { name: "Connect ChatGPT" })).toBeVisible();
		await expect(page.getByPlaceholder("sk-...")).toHaveCount(0);
	});

	test("turning AI off hides every provider control", async ({ page }) => {
		await openAITab(page);

		// The Enable control is the shared pill switch (`role="switch"`), not a
		// checkbox - `uncheck()` only drives real checkbox/radio inputs.
		await page.getByRole("switch").first().click();
		await expect(page.getByRole("switch").first()).toHaveAttribute("aria-checked", "false");
		await expect(page.getByRole("heading", { name: "OpenRouter Settings" })).toHaveCount(0);
		await expect(page.locator("input[type='radio'][value='openrouter']")).toHaveCount(0);
		// The switch itself, and Save, must survive - otherwise the change
		// could never be persisted.
		await expect(page.getByRole("button", { name: "Save" })).toBeEnabled();
	});
});
