import vue from "@vitejs/plugin-vue";
import path from "path";
import { defineConfig } from "vite";

// No frappe-ui proxy/jinja plugin here on purpose: Phase 5 ships the Ask
// screen's rendering surface (inspector, chart, badges, answer card) against
// demo data shaped exactly like `nakhoda.agent.manager.ask()`'s real return
// contract (see `src/demo/`). Wiring the composer to the live `/api/method/
// nakhoda.api.agent.ask` endpoint is Phase 8's job, not this one's - the four
// gates in `14-frontend-design.md` are about what renders, not about calling
// a real site.
export default defineConfig({
	plugins: [vue()],
	server: {
		port: 5177,
		strictPort: true,
	},
	resolve: {
		alias: {
			"@": path.resolve(__dirname, "src"),
		},
	},
	build: {
		outDir: "../nakhoda/public/frontend",
		emptyOutDir: true,
		sourcemap: true,
	},
});
