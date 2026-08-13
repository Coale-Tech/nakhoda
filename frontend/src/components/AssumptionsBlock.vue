<script setup>
import Chip from "./Chip.vue";

/**
 * `.assumptions` container (`app.css` lines 236-245) - "the differentiator"
 * per the mockup's own comment. Header count is derived here from the
 * `applied`/`needs_you` counts passed in, not hand-typed, so the summary
 * chip can never drift from the rows actually rendered below it.
 */
const props = defineProps({
	applied: { type: Number, required: true },
	needsYou: { type: Number, required: true },
});
</script>

<template>
	<div class="assumptions">
		<div class="assumptions-head">
			<h4>Assumptions</h4>
			<Chip tone="gray">{{ props.applied }} applied · {{ props.needsYou }} needs you</Chip>
		</div>
		<div class="assumption-list">
			<slot />
		</div>
		<slot name="ambiguity" />
	</div>
</template>

<style scoped>
.assumptions {
	border-top: 1px solid var(--outline-gray-1);
	margin-top: 16px;
}
.assumptions-head {
	display: flex;
	align-items: center;
	gap: 7px;
	padding: 11px 16px 8px;
}
.assumptions-head h4 {
	font-size: var(--text-tiny);
	font-weight: var(--weight-semibold);
	color: var(--text-secondary);
	text-transform: uppercase;
	letter-spacing: 0.05em;
}
.assumption-list {
	padding: 0 16px 12px;
	display: flex;
	flex-direction: column;
	gap: 1px;
}
</style>
