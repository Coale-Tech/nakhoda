<script setup>
/**
 * "232 invoices (₹39.2 L) in Germany and Kenya are outside your territory
 * permissions and are not in this total." - `14-frontend-design.md` §3, the
 * answer to issue #919. Every other BI tool silently truncates to what your
 * permissions allow and shows a number that looks complete; this states the
 * gap instead. Only rendered when the engine actually removed rows -
 * `excludedCount === 0` means nothing was hidden, and the caller should not
 * mount this component at all rather than have it print a hollow "0 rows".
 */
defineProps({
	excludedCount: { type: Number, required: true },
	excludedAmount: { type: String, required: true },
	reason: { type: String, required: true },
});
</script>

<template>
	<div class="perm-note">
		<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2">
			<rect x="3" y="7" width="10" height="7" rx="1.5" /><path d="M5 7V4.5a3 3 0 0 1 6 0V7" />
		</svg>
		<span
			><b>{{ excludedCount }}</b> record{{ excludedCount === 1 ? "" : "s" }} ({{ excludedAmount }}) are
			outside your {{ reason }} and are not in this total.</span
		>
	</div>
</template>

<style scoped>
.perm-note {
	display: flex;
	align-items: center;
	gap: 8px;
	padding: 8px 16px;
	background: var(--surface-blue-1);
	border-top: 1px solid var(--outline-blue-1);
	font-size: var(--text-tiny);
	color: var(--ink-blue-text);
}
.perm-note svg {
	width: 13px;
	height: 13px;
	flex: none;
}
.perm-note b {
	font-variant-numeric: tabular-nums;
}
</style>
