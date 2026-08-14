<script setup>
/**
 * Label/value rows for the inspector's "Cost & scope" section. `rows[].mono`
 * renders the value in the mono face (run names, model ids); `rows[].color`
 * is an escape hatch for a caller that needs one value tinted - it takes a
 * CSS colour or `var(--ink-*)` reference, since a Tailwind class can't be
 * passed through a style binding.
 */
defineProps({
	rows: { type: Array, required: true }, // [{ label, value, color?, mono? }]
});
</script>

<template>
	<dl>
		<div v-for="(row, i) in rows" :key="i" class="kv flex justify-between gap-3 py-1 text-xs">
			<dt class="text-ink-gray-6">{{ row.label }}</dt>
			<dd
				class="text-right tabular-nums text-ink-gray-8"
				:class="{ 'font-mono': row.mono }"
				:style="row.color ? { color: row.color } : null"
			>
				{{ row.value }}
			</dd>
		</div>
	</dl>
</template>
