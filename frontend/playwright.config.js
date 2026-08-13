import { defineConfig } from "@playwright/test";

/**
 * Phase 5's gates (`12-build-plan.md` §5, gate index) run against the
 * rendered DOM, not a snapshot - the two chart defects it references
 * (bar height rescaled 11.4%, axis labels 99px off) were invisible to
 * repeated eyeballing and found only by measuring computed geometry.
 * `webServer` builds once and serves the static output, matching what
 * ships - not the dev server's HMR runtime.
 */
export default defineConfig({
	testDir: "./tests",
	fullyParallel: true,
	forbidOnly: !!process.env.CI,
	retries: 0,
	reporter: [["list"]],
	use: {
		baseURL: "http://127.0.0.1:5178/assets/nakhoda/frontend/",
		trace: "retain-on-failure",
	},
	webServer: {
		command: "yarn build && yarn serve",
		url: "http://127.0.0.1:5178/assets/nakhoda/frontend/",
		reuseExistingServer: !process.env.CI,
		timeout: 60_000,
	},
});
