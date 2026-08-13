<script setup>
/**
 * `.kv` label/value rows (`app.css` lines 415-418) - used by the inspector's
 * "Cost & scope" section. `rows[].color` is a CSS var reference for the one
 * case the mockup hand-colours a value (rows excluded by permissions, in
 * `--ink-blue-text`) - everything else inherits the default ink.
 */
defineProps({
	rows: { type: Array, required: true }, // [{ label, value, color? }]
});
</script>

<template>
	<dl class="kv-list">
		<div class="kv" v-for="(row, i) in rows" :key="i">
			<dt>{{ row.label }}</dt>
			<dd :style="row.color ? { color: row.color } : null" :class="{ mono: row.mono }">{{ row.value }}</dd>
		</div>
	</dl>
</template>

<style scoped>
.kv {
	display: flex;
	justify-content: space-between;
	gap: 12px;
	font-size: var(--text-xs);
	padding: 4px 0;
}
.kv dt {
	color: var(--text-secondary);
}
.kv dd {
	color: var(--ink-gray-8);
	font-variant-numeric: tabular-nums;
	text-align: right;
}
.kv dd.mono {
	font-family: var(--font-mono);
}
</style>
