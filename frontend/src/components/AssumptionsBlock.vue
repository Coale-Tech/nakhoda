<script setup>
import { Badge } from "frappe-ui";

/**
 * The assumptions container - "the differentiator" per the mockup's own
 * comment. Header count is derived here from the `applied`/`needs_you`
 * counts passed in, not hand-typed, so the summary badge can never drift
 * from the rows actually rendered below it.
 *
 * The section label uses `text-tiny-semibold`: the frappe-ui preset gives
 * the `tiny` size the uppercase transform and letter-spacing this eyebrow
 * needs, so none of it is hand-tuned here.
 */
const props = defineProps({
	applied: { type: Number, required: true },
	needsYou: { type: Number, required: true },
});
</script>

<template>
	<div class="assumptions mt-4 border-t border-outline-gray-1">
		<div class="flex items-center gap-1.5 px-4 pt-3 pb-2">
			<h4 class="text-tiny-semibold text-ink-gray-6">Assumptions</h4>
			<Badge theme="gray" variant="subtle" :label="`${props.applied} applied · ${props.needsYou} needs you`" />
		</div>
		<div class="assumption-list flex flex-col gap-px px-4 pb-3">
			<slot />
		</div>
		<slot name="ambiguity" />
	</div>
</template>
