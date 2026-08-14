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
 * @type {import('tailwindcss').Config}
 */
export default {
	presets: [frappeUIPreset],
	content: [
		"./index.html",
		"./src/**/*.{vue,js,ts,jsx,tsx}",
		"./node_modules/frappe-ui/src/**/*.{vue,js,ts,jsx,tsx}",
		"./node_modules/frappe-ui/frappe/**/*.{vue,js,ts,jsx,tsx}",
	],
};
