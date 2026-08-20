<script setup>
/**
 * The headline number + delta + caption. `delta` is signed text like
 * `"-13.7%"`; a leading `-` flips the arrow and switches the hue - same
 * weight as positive, per the mockup's comment: a decline is not rendered
 * as an error.
 *
 * Hue steps are the deepest semantic ink that clears WCAG AA on a card in
 * both themes: `ink-green-9` (7.89:1 light / 11.37 dark) and `ink-amber-9`
 * (7.14 / 9.99). The shallower steps the eye reaches for first - green-7,
 * amber-8 - measure 4.21 and 3.89 in light and would fail the gate in
 * `contrast.spec.js`.
 */
const props = defineProps({
	value: { type: String, required: true },
	delta: { type: String, default: "" },
	caption: { type: String, default: "" },
});
const isDown = props.delta.trim().startsWith("-");
</script>

<template>
	<div class="metric">
		<div class="flex items-baseline gap-2.5">
			<div class="text-7xl-semibold tabular-nums text-ink-gray-9">{{ value }}</div>
			<div
				v-if="delta"
				class="text-sm-medium inline-flex items-center gap-1"
				:class="isDown ? 'text-ink-amber-9' : 'text-ink-green-9'"
			>
				<span :class="isDown ? 'lucide-trending-down' : 'lucide-trending-up'" class="size-3.5" aria-hidden="true" />
				{{ delta.replace(/^-/, "") }}
			</div>
		</div>
		<div v-if="caption" class="text-p-xs mt-1.5 text-ink-gray-6">{{ caption }}</div>
	</div>
</template>
