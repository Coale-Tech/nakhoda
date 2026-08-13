<script setup>
import Chip from "./Chip.vue";

/**
 * The answer card shell (`.answer`/`.answer-head`/`.answer-body`, `app.css`
 * lines 155-188) - "the product" per the mockup's own comment. Deliberately
 * thin: it owns only the header chip + title + body slot. Assumptions,
 * permission notice, and receipt are separate components composed by the
 * caller (`Turn.vue`) because the verified-query path renders none of the
 * first two - forcing them into this shell would mean an "empty" variant
 * fork instead of the caller simply not passing those slots.
 */
defineProps({
	tone: { type: String, required: true }, // generated | verified
	icon: { type: String, required: true },
	label: { type: String, required: true },
	title: { type: String, required: true },
});
</script>

<template>
	<div class="answer">
		<div class="answer-head">
			<Chip :tone="tone" :icon="icon">{{ label }}</Chip>
			<span class="answer-title">{{ title }}</span>
			<button class="btn btn-sm">Save to workbook</button>
		</div>

		<div class="answer-body"><slot /></div>

		<slot name="assumptions" />
		<slot name="notice" />
		<slot name="receipt" />
	</div>
</template>

<style scoped>
.answer {
	margin-left: 34px;
	border: 1px solid var(--outline-gray-2);
	border-radius: var(--border-radius-lg);
	background: var(--surface-cards);
	box-shadow: var(--shadow-sm);
	overflow: hidden;
}
.answer-head {
	display: flex;
	align-items: center;
	gap: 8px;
	padding: 10px 14px;
	border-bottom: 1px solid var(--outline-gray-1);
}
.answer-title {
	font-size: var(--text-xs);
	color: var(--text-secondary);
	overflow: hidden;
	text-overflow: ellipsis;
	white-space: nowrap;
}
.answer-head .btn {
	margin-left: auto;
}
.answer-body {
	padding: 18px 16px 4px;
}
</style>
