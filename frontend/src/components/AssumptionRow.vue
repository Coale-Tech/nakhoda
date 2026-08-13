<script setup>
/**
 * One row of the assumption taxonomy (`14-frontend-design.md` §1). `state`
 * carries the product's honesty: `applied` is the semantic model settling a
 * question the model didn't have to guess at; `needs_you` is the model
 * picking a side on a genuinely ambiguous question, which is why it renders
 * amber, not grey - colour is reserved for attention, and an unstated
 * assumption is the one place in this card that earns it.
 *
 * `tag` is free text, not restricted to the seven measured trap classes in
 * §1's table - the mockup itself tags one row `measure`, which is not one
 * of the seven. The taxonomy names the *known* failure modes; it does not
 * forbid the generator from surfacing an assumption outside it.
 */
defineProps({
	tag: { type: String, required: true },
	state: { type: String, required: true, validator: (v) => v === "applied" || v === "needs_you" },
});
defineEmits(["change"]);
</script>

<template>
	<div class="assumption">
		<span class="a-tag" :class="state === 'needs_you' ? 'a-ask' : 'a-auto'">{{ tag }}</span>
		<span><slot /></span>
		<span class="a-edit" @click="$emit('change')">Change</span>
	</div>
</template>

<style scoped>
.assumption {
	display: flex;
	align-items: baseline;
	gap: 9px;
	padding: 6px 8px;
	margin: 0 -8px;
	border-radius: var(--border-radius-sm);
	font-size: var(--text-xs);
	color: var(--ink-gray-7);
	line-height: 1.5;
}
.assumption:hover {
	background: var(--surface-gray-2);
}
.assumption :deep(code) {
	font-family: var(--font-mono);
	font-size: 11px;
	background: var(--surface-gray-2);
	color: var(--ink-gray-8);
	padding: 1px 4px;
	border-radius: var(--border-radius-tiny);
}
.assumption:hover :deep(code) {
	background: var(--surface-gray-3);
}
.a-tag {
	flex: none;
	width: 62px;
	font-size: 10px;
	font-weight: var(--weight-semibold);
	text-transform: uppercase;
	letter-spacing: 0.04em;
	padding-top: 1px;
}
.a-auto {
	color: var(--text-tertiary);
}
.a-ask {
	color: var(--ink-amber-text);
}
.a-edit {
	margin-left: auto;
	flex: none;
	opacity: 0;
	font-size: var(--text-tiny);
	color: var(--ink-blue-text);
	font-weight: var(--weight-medium);
	cursor: pointer;
	white-space: nowrap;
}
.assumption:hover .a-edit {
	opacity: 1;
}
</style>
