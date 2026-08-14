import vue from "@vitejs/plugin-vue";
import path from "path";
import frappeui from "frappe-ui/vite";
import { defineConfig } from "vite";

// `frappeProxy` proxies /api,/app,/login,... to the bench during `yarn dev`;
// `jinjaBootData` injects the `{% for key in boot %}...{% endfor %}` block
// this app's `www/_nakhoda.py` feeds (`context.boot`), which is how the SPA
// gets `window.csrf_token` that frappe-ui's `useCall` sends back.
// `lucideIcons` (default, left on) resolves the `~icons/lucide/*` virtual
// imports frappe-ui components do internally - it is required now that this
// app renders real frappe-ui components rather than hand-rolled markup.
// `buildConfig` stays off: the `build` script in `package.json` (and its
// `www/_nakhoda.html` copy step) already owns `outDir`/`base`, and frappeui's
// own build-config plugin would fight it.
export default defineConfig({
	plugins: [
		frappeui({
			frappeProxy: true,
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
	optimizeDeps: {
		// frappe-ui ships unbuilt source whose `~icons/lucide/*` virtual imports
		// esbuild's prebundler cannot resolve; the frappeui plugin resolves them
		// at request time instead.
		exclude: ["frappe-ui"],
		// Excluding the package leaves its transitive CJS deps unconverted, so
		// name them explicitly for prebundling.
		include: ["feather-icons", "tippy.js", "engine.io-client", "socket.io-client", "debug"],
	},
	// `frappeProxy` writes `server.proxy`, and `vite preview` inherits it - which
	// sent `/assets/nakhoda/frontend/` (this app's own built output, and the
	// Playwright `baseURL`) to the bench instead of serving it. Preview serves
	// the build; only the API needs the bench.
	preview: {
		proxy: {
			"^/api": { target: "http://127.0.0.1:8000", ws: true },
		},
	},
	build: {
		outDir: "../nakhoda/public/frontend",
		emptyOutDir: true,
		sourcemap: true,
	},
});
