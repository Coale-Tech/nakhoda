import frappeUIPreset from "frappe-ui/tailwind";

/**
 * The frappe-ui preset owns every design token this app uses - the semantic
 * `ink-*`/`surface-*`/`outline-*` colour ramps, the `text-*`/`text-p-*` type
 * scales, radii, elevations and the `lucide-*` icon classes. It replaces the
 * hand-copied espresso variables this frontend shipped before
 * (`src/assets/tokens.css`), so there is exactly one source for a colour and
 * dark mode flips with `[data-theme="dark"]` for free.
 *
 * `content` must list frappe-ui's own source: Tailwind v3 reads `content`
 * only from the top-level config and silently ignores a preset's, so without
 * these globs every class used *inside* a frappe-ui component is purged.
 *
 * `spacing['7.5']` is the one addition. Insights' sidebar rows and inline
 * editors are `h-7.5` (30px) - a step Tailwind's default scale does not define
 * above 3.5, and one the frappe-ui preset's own gap-filling skips because it
 * only walks whole integers (`tailwind/preset.js`). Without it `h-7.5` compiles
 * to nothing and every ported row silently collapses to its content height, so
 * the class has to exist for the geometry to be real rather than approximate.
 *
 * @type {import('tailwindcss').Config}
 */
export default {
	presets: [frappeUIPreset],
	theme: {
		extend: {
			spacing: { 7.5: "1.875rem" },
		},
	},
	content: [
		"./index.html",
		"./src/**/*.{vue,js,ts,jsx,tsx}",
		"./node_modules/frappe-ui/src/**/*.{vue,js,ts,jsx,tsx}",
		"./node_modules/frappe-ui/frappe/**/*.{vue,js,ts,jsx,tsx}",
	],
};
