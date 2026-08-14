<script setup>
import { Button } from "frappe-ui";

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
 *
 * The amber step is `ink-amber-9`, not the `amber-8` the eye reaches for:
 * amber-8 measures 3.89:1 on a card in light mode and would fail the
 * contrast gate. `Change` is a real ghost Button revealed on row hover,
 * rather than a styled span pretending to be a link.
 */
defineProps({
	tag: { type: String, required: true },
	state: { type: String, required: true, validator: (v) => v === "applied" || v === "needs_you" },
});
defineEmits(["change"]);
</script>

<template>
	<div
		class="assumption group -mx-2 flex items-baseline gap-2.5 rounded-sm px-2 py-1.5 text-xs text-ink-gray-7 hover:bg-surface-gray-2 [&_code]:rounded-sm [&_code]:bg-surface-gray-2 [&_code]:px-1 [&_code]:py-px [&_code]:font-mono [&_code]:text-[11px] [&_code]:text-ink-gray-8"
	>
		<span
			class="w-[62px] flex-none text-[10px] font-semibold uppercase tracking-[0.04em]"
			:class="state === 'needs_you' ? 'text-ink-amber-9' : 'text-ink-gray-6'"
		>
			{{ tag }}
		</span>
		<span class="min-w-0"><slot /></span>
		<Button
			class="ml-auto flex-none self-center opacity-0 group-hover:opacity-100"
			variant="ghost"
			size="sm"
			label="Change"
			@click="$emit('change')"
		/>
	</div>
</template>
