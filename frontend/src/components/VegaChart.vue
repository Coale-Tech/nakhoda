<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from "vue";

/**
 * The Vega runtime and flint together are ~1.5 MB minified - more than the
 * rest of the app put together - so they are imported dynamically rather than
 * at module scope. Vite splits them into their own chunk, which is fetched the
 * first time a chart actually renders and never on a route that has none.
 */
let engine = null;

async function load() {
	if (!engine) {
		const [flint, vega] = await Promise.all([
			import("flint-chart/vegalite"),
			import("vega-embed"),
		]);
		engine = { ...flint, embed: vega.default };
	}
	return engine;
}

/**
 * Everything `Chart.vue` cannot express - line, area, scatter, pie, heatmap,
 * stacked and grouped bar - compiled by `flint-chart` and rendered by Vega.
 *
 * `Chart.vue` deliberately survives beside this. `tests/chart-geometry.spec.js`
 * measures bar height against `data-value` on rendered DOM and caught two real
 * invisible defects doing it; Vega draws to canvas, where those assertions
 * cannot run at all. So bars stay with the component that has a passing
 * geometry gate, and this one takes the shapes that gate never covered.
 *
 * The division of labour is what flint buys: `agent/charts.py:semantics()`
 * resolves *meaning* server-side, where Frappe already knows a column is a
 * `Currency` and that its axis reads "Grand Total", and flint turns meaning
 * into geometry here. Nothing in this file decides what a column means.
 *
 * Theming is Espresso, read at render time from the live CSS custom properties
 * rather than hardcoded: `docs/design/mockup/tokens.css` flips every one of
 * them under `[data-theme="dark"]`, and a chart that baked its palette in
 * would be the one element on the page that ignored the theme. Vega cannot
 * resolve `var(--ink-gray-9)` itself, so the values are computed once per
 * render and handed over as a flint `ThemeSpec`.
 */
const props = defineProps({
	columns: { type: Array, default: () => [] },
	rows: { type: Array, default: () => [] },
	chartType: { type: String, default: "" },
	title: { type: String, default: "" },
	subtitle: { type: String, default: "" },
	semanticTypes: { type: Object, default: () => ({}) },
	fieldDisplayNames: { type: Object, default: () => ({}) },
	width: { type: Number, default: 420 },
	height: { type: Number, default: 260 },
});

/**
 * Nakhoda's own `chart_type` vocabulary - what a `Nakhoda Intelligence
 * Template` panel stores, and what `engine/dashboard.py:add_chart` accepts -
 * to flint's template names. An unmapped value falls through to flint's
 * recommendation rather than failing: a panel authored with a type this build
 * does not know still draws something honest.
 */
const TEMPLATES = {
	bar: "Bar Chart",
	stacked_bar: "Stacked Bar Chart",
	grouped_bar: "Grouped Bar Chart",
	line: "Line Chart",
	area: "Area Chart",
	scatter: "Scatter Plot",
	pie: "Pie Chart",
	donut: "Donut Chart",
	heatmap: "Heatmap",
	histogram: "Histogram",
};

const el = ref(null);
const error = ref("");
let view = null;

function token(styles, name, fallback) {
	return styles.getPropertyValue(name).trim() || fallback;
}

/**
 * The Espresso palette as a flint `ThemeSpec`, extending `swiss` - the shipped
 * house whose structural restraint (thin rules, no frame, quiet grid) is
 * closest to Espresso's, so the fields stated here are the ones that differ
 * rather than a whole design language restated.
 *
 * The categorical set is Espresso's own accent order (`gray-7`, `blue-3`,
 * `green-3`, `amber-3`, `red-5`), which is the order the rest of the UI
 * already uses for series-like things.
 */
function theme() {
	const styles = getComputedStyle(document.documentElement);
	return {
		extends: "swiss",
		ink: {
			surface: { canvas: token(styles, "--surface-white", "#ffffff") },
			text: {
				primary: token(styles, "--ink-gray-9", "#171717"),
				secondary: token(styles, "--ink-gray-6", "#525252"),
				muted: token(styles, "--ink-gray-5", "#7c7c7c"),
			},
			structure: {
				axis: token(styles, "--outline-gray-3", "#c7c7c7"),
				grid: token(styles, "--outline-gray-2", "#e2e2e2"),
			},
			series: {
				single: token(styles, "--surface-gray-7", "#171717"),
				categorical: [
					token(styles, "--surface-gray-7", "#171717"),
					token(styles, "--surface-blue-3", "#007be0"),
					token(styles, "--surface-green-3", "#278f5e"),
					token(styles, "--surface-amber-3", "#db7706"),
					token(styles, "--surface-red-5", "#cc2929"),
				],
			},
		},
		type: {
			headline: { font: token(styles, "--font-stack", "Inter, sans-serif") },
			axisLabel: { font: token(styles, "--font-stack", "Inter, sans-serif") },
		},
		marks: { cornerRadius: 2 },
	};
}

/**
 * `{chartType, encodings}` for this data. A panel that names a type keeps it
 * and only its channels are filled; a panel that names none - or names one
 * whose required channels this result cannot fill - takes flint's own ranked
 * first choice, which is the same recommender the gallery uses.
 */
function chart(flint) {
	const wanted = TEMPLATES[String(props.chartType || "").toLowerCase()];
	if (wanted) {
		const encodings = flint.vlRecommendEncodings(wanted, props.rows, props.semanticTypes);
		if (encodings && Object.keys(encodings).length) return { chartType: wanted, encodings };
	}
	const ranked = flint.vlRecommendCharts(props.rows, props.semanticTypes, { max: 1 });
	return ranked.length ? ranked[0] : null;
}

async function render() {
	error.value = "";
	if (view) {
		view.finalize();
		view = null;
	}
	if (!el.value || !props.rows.length) return;

	try {
		const flint = await load();
		const picked = chart(flint);
		if (!picked) {
			error.value = "No chart fits this result";
			return;
		}
		const spec = flint.assembleVegaLite({
			data: { values: props.rows },
			semantic_types: props.semanticTypes,
			field_display_names: props.fieldDisplayNames,
			theme_spec: theme(),
			options: { addTooltips: true },
			chart_spec: {
				chartType: picked.chartType,
				encodings: picked.encodings,
				title: props.title || undefined,
				subtitle: props.subtitle || undefined,
				baseSize: { width: props.width, height: props.height },
			},
		});
		const result = await flint.embed(el.value, spec, { actions: false, renderer: "canvas" });
		view = result.view;
	} catch (e) {
		// A chart that cannot be drawn says so in place. Throwing here would
		// take the whole dashboard grid down with one bad panel.
		error.value = e?.message || String(e);
	}
}

onMounted(render);
onBeforeUnmount(() => view?.finalize());
watch(
	() => [props.rows, props.chartType, props.semanticTypes, props.title],
	render,
	{ deep: true },
);
</script>

<template>
	<div class="vega-chart">
		<div v-if="error" class="p-3 text-p-sm text-ink-gray-5">{{ error }}</div>
		<div v-show="!error" ref="el" />
	</div>
</template>
