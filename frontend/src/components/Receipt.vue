<script setup>
/**
 * The cost/provenance strip at the bottom of every answer card. The
 * generated and verified paths show different fields entirely (operations /
 * model / query time vs a verified-query name), so this takes free-form
 * `segments` (each `{ html }`, joined with `·`) rather than fixed numeric
 * props - a fixed shape would force the verified path to fake an operation
 * count it does not have.
 *
 * Segment HTML comes from `src/agent.js` and carries `<b>` and
 * `<code class="font-mono">`; both are styled here through arbitrary child
 * selectors so this component needs no stylesheet of its own. Type is
 * `text-xs`, not `text-tiny`: the frappe-ui preset gives `tiny` an
 * `uppercase` transform (it is an eyebrow style), which would shout a
 * sentence-case receipt.
 */
defineProps({
	segments: { type: Array, required: true }, // [{ html: string }]
});
</script>

<template>
	<div
		class="receipt flex flex-wrap items-center gap-3 border-t border-outline-gray-1 bg-surface-gray-1 px-4 py-2.5 text-xs tabular-nums text-ink-gray-6 [&_b]:font-medium [&_b]:text-ink-gray-7 [&_code]:text-ink-gray-7"
	>
		<template v-for="(seg, i) in segments" :key="i">
			<span v-html="seg.html" />
			<span v-if="i < segments.length - 1" aria-hidden="true">·</span>
		</template>
		<div v-if="$slots.actions" class="ml-auto flex items-center gap-1.5">
			<slot name="actions" />
		</div>
	</div>
</template>
