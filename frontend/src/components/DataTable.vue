<script setup>
/**
 * The verified-query result table (`.table-wrap`/`table`, `app.css` lines
 * 438-450). `columns[].align === 'num'` maps to `.t-num`; `muted` per-cell
 * maps to `.t-mute` (used for the share-of-total column in the ageing
 * table, which is derived, not measured).
 */
defineProps({
	columns: { type: Array, required: true }, // [{ label, align? }]
	rows: { type: Array, required: true }, // [{ cells: [{ text, muted? }] }]
});
</script>

<template>
	<div class="table-wrap">
		<table>
			<thead>
				<tr>
					<th v-for="(c, i) in columns" :key="i" :class="{ 't-num': c.align === 'num' }">
						{{ c.label }}
					</th>
				</tr>
			</thead>
			<tbody>
				<tr v-for="(r, ri) in rows" :key="ri">
					<td
						v-for="(cell, ci) in r.cells"
						:key="ci"
						:class="{ 't-num': columns[ci].align === 'num', 't-mute': cell.muted }"
					>
						{{ cell.text }}
					</td>
				</tr>
			</tbody>
		</table>
	</div>
</template>

<style scoped>
.table-wrap {
	border: 1px solid var(--outline-gray-2);
	border-radius: var(--border-radius);
	overflow: hidden;
	background: var(--surface-cards);
}
table {
	width: 100%;
	border-collapse: collapse;
	font-size: var(--text-xs);
}
th {
	text-align: left;
	font-weight: var(--weight-semibold);
	color: var(--text-secondary);
	padding: 8px 12px;
	background: var(--surface-gray-1);
	border-bottom: 1px solid var(--outline-gray-2);
	font-size: var(--text-tiny);
	text-transform: uppercase;
	letter-spacing: 0.04em;
	white-space: nowrap;
}
td {
	padding: 8px 12px;
	border-bottom: 1px solid var(--outline-gray-1);
	color: var(--ink-gray-8);
}
tr:last-child td {
	border-bottom: none;
}
tbody tr:hover {
	background: var(--surface-gray-1);
}
.t-num {
	text-align: right;
	font-variant-numeric: tabular-nums;
}
.t-mute {
	color: var(--text-secondary);
}
</style>
