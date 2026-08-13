<script setup>
import { computed } from "vue";

/**
 * The bar chart `14-frontend-design.md` §4 measured two real defects in:
 *
 * - `display:flex` bars resolved `height:N%` against the column *including*
 *   the value label, so the tallest bar was shrunk to fit label + gap and
 *   the whole series silently rescaled (11.4% error). Fixed by `.bar-col`
 *   being `grid-template-rows: auto 1fr` - the label takes the `auto` row,
 *   the bar owns the `1fr` plot track, and `height:N%` resolves against
 *   that track alone.
 * - `flex:1` axis labels against fixed-width `.compact` bars put the last
 *   label 99px from the bar it named. Fixed by the axis using the exact
 *   same track geometry as `.bars` - `flex:1` here, `flex:0 0 44px` there.
 *
 * `height` is computed here from `series[].value`, not hand-authored per
 * bar, so `test_chart_geometry.spec.js` is asserting this component's own
 * arithmetic against its own rendered DOM - a hand-typed `height:92%` next
 * to a hand-typed value is exactly how the flex defect above shipped once
 * already.
 */
const props = defineProps({
	series: { type: Array, required: true }, // [{ label?, value, muted?, forecast? }]
	showValues: { type: Boolean, default: true },
	showAxis: { type: Boolean, default: true },
	compact: { type: Boolean, default: false },
	height: { type: Number, default: 132 },
});

const max = computed(() => Math.max(...props.series.map((s) => s.value), 1));

function pct(value) {
	return (value / max.value) * 100;
}
</script>

<template>
	<div class="chart">
		<div class="bars" :class="{ compact }" :style="{ height: `${height}px` }">
			<div v-for="(s, i) in series" :key="i" class="bar-col" :class="{ compact }">
				<span v-if="showValues" class="bar-val num">{{ s.value }}</span>
				<div
					class="bar"
					:class="{ muted: s.muted, forecast: s.forecast }"
					:style="{ height: `${pct(s.value)}%` }"
					:data-value="s.value"
				/>
			</div>
		</div>
		<div v-if="showAxis" class="axis" :class="{ compact }">
			<div v-for="(s, i) in series" :key="i" class="bar-label">{{ s.label }}</div>
		</div>
	</div>
</template>

<style scoped>
.chart {
	margin: 18px 0 4px;
}
.bars {
	display: flex;
	align-items: flex-end;
	gap: 10px;
}
.bar-col {
	flex: 1;
	display: grid;
	grid-template-rows: auto 1fr;
	justify-items: center;
	align-items: end;
	height: 100%;
}
.bar-val {
	margin-bottom: 6px;
	font-size: var(--text-xs);
	color: var(--text-secondary);
}
.bar {
	grid-row: 2;
	width: 100%;
	max-width: 44px;
	border-radius: var(--border-radius-tiny) var(--border-radius-tiny) 2px 2px;
	background: var(--surface-gray-7);
	position: relative;
}
.bar.muted {
	background: var(--surface-gray-4);
}
.bar.forecast {
	background: repeating-linear-gradient(135deg, var(--surface-gray-7) 0 3px, var(--surface-gray-4) 3px 6px);
}
.axis {
	border-top: 1px solid var(--outline-gray-2);
	margin-top: 8px;
	padding-top: 7px;
	display: flex;
	gap: 10px;
}
.axis > div {
	flex: 1;
	min-width: 0;
	text-align: center;
	font-size: var(--text-tiny);
	color: var(--text-tertiary);
}
/* Compact charts (inside cards) pack left at a fixed track width - the axis
   must use the same geometry or labels drift, per the docstring above. */
.bars.compact,
.axis.compact {
	gap: 12px;
	justify-content: flex-start;
}
.bar-col.compact,
.axis.compact > div {
	flex: 0 0 44px;
	min-width: 0;
}
</style>
