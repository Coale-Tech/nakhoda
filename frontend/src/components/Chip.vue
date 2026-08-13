<script setup>
/**
 * `.chip` family from the mockup: `chip-generated` (sparkle, the SQL path),
 * `chip-verified` (the `Nakhoda Verified Query` path), `chip-gray` (counts),
 * `chip-warn`. Kept as one component with a `tone` prop rather than four
 * near-duplicate spans, since every call site needs exactly one of these.
 */
defineProps({
	tone: { type: String, default: "gray" }, // generated | verified | gray | warn
	icon: { type: String, default: "" },
});
</script>

<template>
	<span class="chip" :class="`chip-${tone}`">
		<svg v-if="icon" viewBox="0 0 16 16" fill="none" stroke="currentColor"><use :href="`#i-${icon}`" /></svg>
		<slot />
	</span>
</template>

<style scoped>
.chip {
	display: inline-flex;
	align-items: center;
	gap: 5px;
	height: 20px;
	padding: 0 8px;
	border-radius: var(--border-radius-full);
	font-size: var(--text-tiny);
	font-weight: var(--weight-medium);
	white-space: nowrap;
}
.chip svg {
	width: 11px;
	height: 11px;
	stroke-width: 2.2;
}
.chip-verified {
	background: var(--surface-green-2);
	color: var(--ink-green-text);
}
.chip-generated {
	background: var(--surface-blue-2);
	color: var(--ink-blue-text);
}
.chip-warn {
	background: var(--surface-amber-2);
	color: var(--ink-amber-text);
}
.chip-gray {
	background: var(--surface-gray-3);
	color: var(--ink-gray-6);
}
</style>
