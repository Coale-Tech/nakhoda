<script setup>
import { computed } from "vue";

/**
 * The bar chart `14-frontend-design.md` §4 measured two real defects in:
 *
 * - `display:flex` bars resolved `height:N%` against the column *including*
 *   the value label, so the tallest bar was shrunk to fit label + gap and
 *   the whole series silently rescaled (11.4% error). Fixed by `.bar-col`
 *   being `grid-rows-[auto_1fr]` - the label takes the `auto` row, the bar
 *   owns the `1fr` plot track (`row-start-2`), and `height:N%` resolves
 *   against that track alone.
 * - `flex:1` axis labels against fixed-width compact bars put the last
 *   label 99px from the bar it named. Fixed by the axis using the exact
 *   same track geometry as the bars - `flex-1` here, `flex-none w-11`
 *   there.
 *
 * `height` is computed here from `series[].value`, not hand-authored per
 * bar, so `chart-geometry.spec.js` is asserting this component's own
 * arithmetic against its own rendered DOM - a hand-typed `height:92%` next
 * to a hand-typed value is exactly how the flex defect above shipped once
 * already.
 *
 * The class names (`chart`, `bars`, `bar-col`, `bar`, `axis`) carry no
 * styling now that geometry is expressed in utilities; they are kept as the
 * structural hooks that spec addresses. The forecast hatch is the one
 * pattern with no utility equivalent, so it is an arbitrary value over the
 * `--surface-*` variables the frappe-ui preset emits - which still flip
 * under `[data-theme="dark"]`.
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
	<div class="chart mt-4 mb-1">
		<div
			class="bars flex items-end"
			:class="compact ? 'justify-start gap-3' : 'gap-2.5'"
			:style="{ height: `${height}px` }"
		>
			<div
				v-for="(s, i) in series"
				:key="i"
				class="bar-col grid h-full grid-rows-[auto_1fr] items-end justify-items-center"
				:class="compact ? 'w-11 min-w-0 flex-none' : 'flex-1'"
			>
				<span v-if="showValues" class="mb-1.5 text-xs tabular-nums text-ink-gray-6">{{ s.value }}</span>
				<div
					class="bar row-start-2 w-full max-w-11 rounded-t-sm"
					:class="
						s.forecast
							? 'bg-[repeating-linear-gradient(135deg,var(--surface-gray-7)_0_3px,var(--surface-gray-4)_3px_6px)]'
							: s.muted
								? 'bg-surface-gray-4'
								: 'bg-surface-gray-7'
					"
					:style="{ height: `${pct(s.value)}%` }"
					:data-value="s.value"
				/>
			</div>
		</div>
		<div
			v-if="showAxis"
			class="axis mt-2 flex border-t border-outline-gray-2 pt-2"
			:class="compact ? 'justify-start gap-3' : 'gap-2.5'"
		>
			<div
				v-for="(s, i) in series"
				:key="i"
				class="min-w-0 text-center text-2xs text-ink-gray-6"
				:class="compact ? 'w-11 flex-none' : 'flex-1'"
			>
				{{ s.label }}
			</div>
		</div>
	</div>
</template>
