<script setup>
import { Button } from "frappe-ui";

/**
 * The counterfactual for one `needs_you` assumption (`14-frontend-design.md`
 * §1). Not a footnote: it names the number the other reading would have
 * given, so correcting it costs one click, not a re-typed question - the
 * §2 gate this screen exists to satisfy.
 *
 * Two actions: the alternative reading (`altLabel`, subtle) and keeping the
 * answer as generated (`keepLabel`, solid - the default the model already
 * picked, and the one primary action in this block).
 */
defineProps({
	counterfactual: { type: String, required: true },
	altLabel: { type: String, required: true },
	keepLabel: { type: String, required: true },
});
defineEmits(["choose-alt", "keep"]);
</script>

<template>
	<div
		class="ambiguity mx-4 mt-1 mb-3.5 flex items-center gap-2.5 rounded-sm border border-outline-amber-1 bg-surface-amber-1 px-3 py-2 text-xs text-ink-gray-8"
	>
		<span class="lucide-triangle-alert size-3.5 flex-none text-ink-amber-9" aria-hidden="true" />
		<span class="min-w-0" v-html="counterfactual" />
		<Button class="ml-auto flex-none" variant="subtle" size="sm" :label="altLabel" @click="$emit('choose-alt')" />
		<Button class="flex-none" variant="solid" theme="gray" size="sm" :label="keepLabel" @click="$emit('keep')" />
	</div>
</template>
