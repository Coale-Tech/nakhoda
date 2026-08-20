<script setup>
/**
 * "232 invoices (₹39.2 L) in Germany and Kenya are outside your territory
 * permissions and are not in this total." - `14-frontend-design.md` §3, the
 * answer to issue #919. Every other BI tool silently truncates to what your
 * permissions allow and shows a number that looks complete; this states the
 * gap instead. Only rendered when the engine actually removed rows -
 * `excludedCount === 0` means nothing was hidden, and the caller should not
 * mount this component at all rather than have it print a hollow "0 rows".
 *
 * `ink-blue-9` on `surface-blue-1` measures 6.25:1 light / 10.02 dark; the
 * `blue-link` token the eye reaches for first is 3.36 and would fail the
 * contrast gate at this text size.
 */
defineProps({
	excludedCount: { type: Number, required: true },
	excludedAmount: { type: String, required: true },
	reason: { type: String, required: true },
});
</script>

<template>
	<div
		class="perm-note flex items-center gap-2 border-t border-outline-blue-1 bg-surface-blue-1 px-4 py-2 text-xs text-ink-blue-9 [&_b]:tabular-nums"
	>
		<span class="lucide-lock size-3.5 flex-none" aria-hidden="true" />
		<span>
			<b>{{ excludedCount }}</b> record{{ excludedCount === 1 ? "" : "s" }}<template v-if="excludedAmount"> ({{ excludedAmount }})</template> are outside your
			{{ reason }} and are not in this total.
		</span>
	</div>
</template>
