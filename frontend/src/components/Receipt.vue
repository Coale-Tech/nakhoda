<script setup>
/**
 * `.receipt` (`app.css` lines 285+) - the cost/provenance strip at the
 * bottom of every answer card. The generated and verified paths show
 * different fields entirely (5 operations/2 tables/cost vs a verified-query
 * name + parameter list, no cost line), so this takes free-form `segments`
 * (each `{ html }`, joined with `·`) rather than fixed numeric props - a
 * fixed shape would force the verified path to fake an operation count it
 * does not have.
 */
defineProps({
	segments: { type: Array, required: true }, // [{ html: string }]
});
</script>

<template>
	<div class="receipt num">
		<template v-for="(seg, i) in segments" :key="i">
			<span v-html="seg.html" />
			<span v-if="i < segments.length - 1" class="sep">·</span>
		</template>
		<div class="receipt-actions">
			<slot name="actions" />
		</div>
	</div>
</template>

<style scoped>
.receipt {
	display: flex;
	align-items: center;
	gap: 12px;
	flex-wrap: wrap;
	padding: 9px 16px;
	border-top: 1px solid var(--outline-gray-1);
	background: var(--surface-gray-1);
	font-size: var(--text-tiny);
	color: var(--text-secondary);
}
.receipt :deep(b) {
	font-weight: var(--weight-medium);
	color: var(--ink-gray-7);
}
.receipt .sep {
	color: var(--text-tertiary);
}
.receipt-actions {
	margin-left: auto;
	display: flex;
	gap: 6px;
}
</style>
