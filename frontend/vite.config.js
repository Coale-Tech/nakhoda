import vue from "@vitejs/plugin-vue";
import path from "path";
import frappeui from "frappe-ui/vite";
import { defineConfig } from "vite";

// `frappeProxy` proxies /api,/app,/login,... to the bench during `yarn dev`;
// `jinjaBootData` injects the `{% for key in boot %}...{% endfor %}` block
// this app's `www/_nakhoda.py` feeds (`context.boot`), which is how the SPA
// gets `window.csrf_token` for `src/callApi.js`'s `call()`. `buildConfig`
// stays off: the `build` script below (and the `www/_nakhoda.html` copy
// step in `package.json`) already owns `outDir`/`base`, and frappeui's own
// build config plugin would fight it. `frappe-ui`'s Vue component barrel
// (its default export) is never imported at runtime - see `callApi.js` -
// so its own internal dependencies (icons, vue-router, ...) never enter
// this bundle.
export default defineConfig({
	plugins: [
		frappeui({
			frappeProxy: true,
			lucideIcons: false,
			jinjaBootData: true,
			buildConfig: false,
		}),
		vue(),
	],
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
