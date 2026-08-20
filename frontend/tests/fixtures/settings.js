/**
 * Mocks for `useSettings.js` - GET returns a fixed row, PUT echoes back
 * whatever body it was sent (mirroring `mockQueryBuilder`'s pattern for
 * `Nakhoda*Query` documents) so a save round-trips through the same
 * component code a real PUT would exercise.
 *
 * The AI fields mirror `nakhoda_settings.json`'s defaults, so the AI Provider
 * tab renders the same state a fresh install would show.
 */
export const SETTINGS_ROW = {
	name: "Nakhoda Settings",
	max_rows: 100000,
	cache_ttl: 3600,
	strict_columns: 0,
	// -- Data Store tab -----------------------------------------------------
	enable_data_store: 1,
	max_records_to_sync: 1000000,
	max_memory_usage: 512,
	// -- AI Provider tab ----------------------------------------------------
	enable_ai: 1,
	ai_provider: "openrouter",
	openrouter_api_key: "",
	ai_model: "nvidia/nemotron-3-super-120b-a12b:free",
	ai_model_fallback: "nvidia/nemotron-3-ultra-550b-a55b:free",
	openai_auth_mode: "API Key",
	openai_api_key: "",
	openai_base_url: "",
	openai_model: "gpt-5.6-terra",
	nvidia_api_key: "",
	nvidia_model: "nvidia/nemotron-3-super-120b-a12b",
	ollama_base_url: "http://localhost:11434",
	ollama_api_key: "",
	ollama_model: "llama3.1",
	moonshot_auth_mode: "API Key",
	moonshot_api_key: "",
	moonshot_model: "kimi-k3",
	quota_reset_schedule: "Daily",
	daily_ai_quota: 100,
	ai_quota_used: 12,
	last_ai_answer: "2026-08-15 09:30:00",
	chatgpt_oauth_account_label: "",
	kimi_oauth_account_label: "",
};

/** What `nakhoda.api.ai.status` reports for `SETTINGS_ROW`. */
export const AI_STATUS = {
	enabled: true,
	configured: false,
	provider: "openrouter",
	provider_label: "OpenRouter",
	base_url: "https://openrouter.ai/api/v1",
	model: SETTINGS_ROW.ai_model,
	fallback_model: SETTINGS_ROW.ai_model_fallback,
	quota_used: SETTINGS_ROW.ai_quota_used,
	daily_quota: SETTINGS_ROW.daily_ai_quota,
	unlimited: false,
	reset_schedule: "Daily",
	window_start: "2026-08-15 00:00:00",
	last_answer: SETTINGS_ROW.last_ai_answer,
};

/**
 * Mock the Nakhoda Settings document endpoint. Call before `page.goto`.
 *
 * `overrides` exist because two surfaces read one switch: boot carries
 * `data_store_enabled` for the nav gate, and this document carries
 * `enable_data_store` for the Settings tab - and `useSettings`'s GET writes
 * through to the session store, so a fixture that let the two disagree would
 * have the later read silently undo `mockBoot`'s gate.
 */
export async function mockSettings(page, overrides = {}) {
	const row = { ...SETTINGS_ROW, ...overrides };
	await page.route("**/document/Nakhoda*Settings**", async (route) => {
		if (route.request().method() === "GET") {
			return route.fulfill({ json: { data: row } });
		}
		if (route.request().method() === "PUT") {
			const body = route.request().postDataJSON();
			return route.fulfill({ json: { data: { ...row, ...body } } });
		}
		return route.continue();
	});
}

/**
 * Mock the AI Provider tab's live-state calls: the status strip, the device
 * -login status probes, and `Test`. `testResult` overrides what a probe
 * reports, so a test can drive the success and failure branches.
 */
export async function mockAIStatus(page, { status = AI_STATUS, testResult } = {}) {
	await page.route("**/api/method/nakhoda.api.ai.status**", (route) =>
		route.fulfill({ json: { message: status } }),
	);
	await page.route("**/api/method/nakhoda.api.ai.test_connection**", (route) =>
		route.fulfill({
			json: { message: testResult || { success: true, message: "Connected" } },
		}),
	);
	await page.route("**/api/method/nakhoda.agent.*_subscription_auth.*", (route) =>
		route.fulfill({
			json: { message: { connected: false, account_label: "", expired: false } },
		}),
	);
}
