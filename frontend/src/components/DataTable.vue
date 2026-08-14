<script setup>
import { computed } from "vue";
import { List, ListCell, ListHeader, ListHeaderCell, ListRow, ListRows } from "frappe-ui/list";

/**
 * The result table. Built on frappe-ui's list family in table mode (a
 * `ListHeader` is what flips it into `role="table"` semantics) rather than a
 * hand-rolled `<table>`: row height, dividers, hover surface and the grid
 * track geometry then come from the library, and the column tracks stay a
 * declared contract instead of browser table layout.
 *
 * `columns[].align === 'num'` right-aligns and tabular-numbers that column;
 * `muted` per cell dims a derived value (e.g. a share-of-total column that
 * is computed, not measured).
 *
 * Header cells override the family's default `text-ink-gray-5` (4.17:1 on
 * white - below AA) with `text-ink-gray-6` (7.36:1). Setting it on the cell
 * rather than the header root makes the override deterministic: the child
 * simply doesn't inherit, so it does not depend on which utility Tailwind
 * emits last.
 */
const props = defineProps({
	columns: { type: Array, required: true }, // [{ label, align? }]
	rows: { type: Array, required: true }, // [{ cells: [{ text, muted? }] }]
});

// Equal, shrinkable tracks: column count is whatever the query returned, so
// there is no per-column width to declare honestly.
const tracks = computed(() => props.columns.map(() => "minmax(0,1fr)"));
</script>

<template>
	<div class="table-wrap overflow-hidden rounded border border-outline-gray-2">
		<List class="list-row-px-3 w-full" :columns="tracks" :row-height="36">
			<ListHeader>
				<ListHeaderCell
					v-for="(c, i) in columns"
					:key="i"
					:class="c.align === 'num' ? 'justify-end text-ink-gray-6' : 'text-ink-gray-6'"
				>
					{{ c.label }}
				</ListHeaderCell>
			</ListHeader>
			<ListRows :items="rows" :row-key="(_, index) => index">
				<template #default="{ item, value }">
					<ListRow :value="value">
						<ListCell
							v-for="(cell, ci) in item.cells"
							:key="ci"
							:class="[
								columns[ci].align === 'num' ? 'justify-end tabular-nums' : '',
								cell.muted ? 'text-ink-gray-6' : 'text-ink-gray-8',
							]"
						>
							<span class="truncate text-xs">{{ cell.text }}</span>
						</ListCell>
					</ListRow>
				</template>
			</ListRows>
		</List>
	</div>
</template>
