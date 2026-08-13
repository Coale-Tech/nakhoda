<script setup>
import Icon from "./Icon.vue";

/**
 * The counterfactual for one `needs_you` assumption (`14-frontend-design.md`
 * §1). Not a footnote: it names the number the other reading would have
 * given, so correcting it costs one click, not a re-typed question - the
 * §2 gate this screen exists to satisfy.
 *
 * Two actions, matching the mockup exactly: the alternative reading
 * (`altLabel`, plain `.btn`) and keeping the answer as generated
 * (`keepLabel`, `.btn-primary` - the default the model already picked).
 */
defineProps({
	counterfactual: { type: String, required: true },
	altLabel: { type: String, required: true },
	keepLabel: { type: String, required: true },
});
defineEmits(["choose-alt", "keep"]);
</script>

<template>
	<div class="ambiguity">
		<Icon name="alert" />
		<span v-html="counterfactual" />
		<button class="btn btn-sm" @click="$emit('choose-alt')">{{ altLabel }}</button>
		<button class="btn btn-sm btn-primary" @click="$emit('keep')">{{ keepLabel }}</button>
	</div>
</template>

<style scoped>
.ambiguity {
	margin: 4px 16px 14px;
	padding: 9px 11px;
	background: var(--surface-amber-1);
	border: 1px solid var(--outline-amber-1);
	border-radius: var(--border-radius-sm);
	display: flex;
	align-items: center;
	gap: 9px;
	font-size: var(--text-xs);
	color: var(--ink-gray-8);
}
.ambiguity svg {
	width: 14px;
	height: 14px;
	flex: none;
	color: var(--ink-amber-text);
}
/* Only the first `.btn` gets the leftover flex space; the second sits
   flush beside it - same effect as the mockup's `.ambiguity .btn`. */
.ambiguity .btn:first-of-type {
	margin-left: auto;
}
</style>
