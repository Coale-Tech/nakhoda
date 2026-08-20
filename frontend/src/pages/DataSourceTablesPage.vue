<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { Badge, Breadcrumbs, FormControl, LoadingIndicator } from "frappe-ui";
import { List, ListHeader, ListHeaderCell, ListRow, ListCell, ListRows } from "frappe-ui/list";
import { useSourceTables } from "../composables/useDataSources.js";
import { timeAgo } from "../composables/useTimestamp.js";

/**
 * One source's tables. Ported from Insights' `DataSourceTableList.vue`, with
 * the difference that decides the whole screen: the two `source_type` values
 * answer differently. The site database lists every DocType the viewer may
 * read; the warehouse lists only what somebody deliberately imported, because
 * a DuckDB table nobody asked for does not exist (`api/data_sources.py:
 * list_source_tables`).
 *
 * The `h-12` header is the same one every routed page owns, which is what
 * makes the hierarchy legible: the crumbs here continue the trail the flat
 * `Data Sources` header starts (Insights' `DataSourceTableList.vue`).
 */
const props = defineProps({ name: { type: String, required: true } });

const store = useSourceTables();
const searchQuery = ref("");
let searchTimer = null;

// The composable records the failure on `store.error`, which the template
// renders; rethrowing past that point only produces an unhandled rejection.
function load(name) {
	store.load(name).catch(() => {});
	store.list(name).catch(() => {});
}

onMounted(() => load(props.name));

onUnmounted(() => clearTimeout(searchTimer));

// Route param changes without remounting when navigating between sources.
watch(
	() => props.name,
	(name) => {
		searchQuery.value = "";
		load(name);
	},
);

function onSearch() {
	clearTimeout(searchTimer);
	searchTimer = setTimeout(() => store.list(props.name, searchQuery.value).catch(() => {}), 300);
}

const crumbs = computed(() => [
	{ label: "Data Sources", route: { name: "Data Sources" } },
	{ label: store.source?.title || props.name, route: { name: "Data Source Tables", params: { name: props.name } } },
]);

const emptyMessage = computed(() =>
	store.source?.source_type === "DuckDB Warehouse"
		? "Import a table from the Data Store to see it here."
		: "No readable DocTypes match this search.",
);
</script>

<template>
	<header
		class="flex h-12 shrink-0 items-center justify-between border-b border-outline-gray-2 py-2.5 pl-5 pr-2"
	>
		<Breadcrumbs :items="crumbs" />
		<Badge v-if="store.source" theme="gray" variant="subtle">{{ store.source.source_type }}</Badge>
	</header>

	<div class="flex min-h-0 flex-1 flex-col gap-3 overflow-auto px-5 py-3">
		<div class="flex gap-2 overflow-visible py-1">
			<FormControl placeholder="Search tables" v-model="searchQuery" @input="onSearch">
				<template #prefix>
					<span class="lucide-search size-4 text-ink-gray-4" aria-hidden="true" />
				</template>
			</FormControl>
		</div>

		<div v-if="store.loading && !store.tables.length" class="flex flex-1 items-center justify-center">
			<LoadingIndicator class="size-6" />
		</div>
		<div
			v-else-if="store.error"
			class="rounded-sm border border-outline-red-2 bg-surface-red-1 p-4 text-sm text-ink-red-6"
		>
			Could not load tables for this source.
		</div>
		<List
			v-else-if="store.tables.length"
			class="min-h-0 flex-1 overflow-y-auto"
			:columns="['minmax(0,1fr)', 'minmax(0,1fr)', '7rem', '11rem']"
		>
			<ListHeader>
				<ListHeaderCell>Table Name</ListHeaderCell>
				<ListHeaderCell>Name</ListHeaderCell>
				<ListHeaderCell>Rows</ListHeaderCell>
				<ListHeaderCell>Last Synced</ListHeaderCell>
			</ListHeader>
			<ListRows :items="store.tables" row-key="table">
				<template #default="{ item, value }">
					<ListRow
						:value="value"
						:to="{ name: 'Data Source Table', params: { name: props.name, table: item.table } }"
					>
						<ListCell>
							<span class="truncate font-mono text-xs">{{ item.table_name }}</span>
						</ListCell>
						<ListCell>
							<div class="flex min-w-0 items-center gap-2">
								<span class="truncate text-base">{{ item.label }}</span>
								<Badge v-if="item.is_child" theme="gray" variant="subtle">Child</Badge>
								<Badge v-else-if="!item.doctype" theme="blue" variant="subtle">Upload</Badge>
							</div>
						</ListCell>
						<ListCell class="justify-end tabular-nums">
							<span class="truncate text-base">{{ item.row_count ?? "—" }}</span>
						</ListCell>
						<ListCell>
							<span class="truncate text-base" :title="item.last_synced ?? ''">
								{{ timeAgo(item.last_synced) }}
							</span>
						</ListCell>
					</ListRow>
				</template>
			</ListRows>
		</List>
		<div v-else class="mt-10 rounded-lg border border-outline-gray-2 bg-surface-elevation-1 p-10 text-center">
			<p class="text-p-base text-ink-gray-6">{{ emptyMessage }}</p>
		</div>
	</div>
</template>
