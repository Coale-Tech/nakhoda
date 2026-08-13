<script setup>
/**
 * The headline number + delta + caption from `.metric`/`.metric-value`/
 * `.metric-delta`/`.metric-caption` (`app.css` lines 190-203). `delta` is
 * signed text like `"-13.7%"`; a leading `-` flips the arrow and switches
 * the amber hue (`.metric-delta.down`) - same weight as positive, per the
 * mockup's comment: a decline is not rendered as an error.
 */
const props = defineProps({
	value: { type: String, required: true },
	delta: { type: String, default: "" },
	caption: { type: String, default: "" },
});
const isDown = props.delta.trim().startsWith("-");
</script>

<template>
	<div>
		<div class="metric">
			<div class="metric-value num">{{ value }}</div>
			<div v-if="delta" class="metric-delta" :class="{ down: isDown }">
				<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" :style="{ transform: isDown ? 'rotate(180deg)' : '' }">
					<use href="#i-up" />
				</svg>
				{{ delta.replace(/^-/, "") }}
			</div>
		</div>
		<div v-if="caption" class="metric-caption">{{ caption }}</div>
	</div>
</template>

<style scoped>
.metric {
	display: flex;
	align-items: baseline;
	gap: 10px;
}
.metric-value {
	font-size: var(--text-7xl);
	font-weight: var(--weight-semibold);
	color: var(--ink-gray-9);
	letter-spacing: -0.03em;
	line-height: 1.05;
}
.metric-delta {
	font-size: var(--text-sm);
	font-weight: var(--weight-medium);
	color: var(--ink-green-text);
	display: inline-flex;
	align-items: center;
	gap: 3px;
}
.metric-delta svg {
	width: 13px;
	height: 13px;
	stroke-width: 2.2;
}
.metric-delta.down {
	color: var(--ink-amber-text);
}
.metric-caption {
	font-size: var(--text-xs);
	color: var(--text-secondary);
	margin-top: 6px;
}
</style>
