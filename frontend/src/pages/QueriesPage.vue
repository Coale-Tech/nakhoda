<script setup>
import { onMounted } from "vue";
import { useRouter } from "vue-router";
import { Breadcrumbs, Button, LoadingIndicator } from "frappe-ui";
import { List, ListHeader, ListHeaderCell, ListRow, ListCell, ListRows } from "frappe-ui/list";
import { useQueryStore } from "../stores/query.js";

/**
 * Unfiled queries: the ones no workbook holds.
 *
 * Insights has no page like this because `insights_query_v3.workbook` is
 * `reqd` - there, every query is inside a workbook and the workbook sidebar is
 * the only list needed. `Nakhoda Query.workbook` is optional, so the builder
 * can save a query that belongs to no container, and those rows would
 * otherwise be unreachable. `api/query.py:list_queries` filters to them, so
 * this page is not a second copy of every workbook's Queries section.
 */

const router = useRouter();
const store = useQueryStore();

onMounted(() => {
	store.fetchQueries();
});

function createQuery() {
	router.push({ name: "Query", params: { name: "new" } });
}

function openQuery(name) {
	router.push({ name: "Query", params: { name } });
}
</script>

<template>
	<header
		class="flex h-12 shrink-0 items-center justify-between border-b border-outline-gray-2 py-2.5 pl-5 pr-2"
	>
		<Breadcrumbs :items="[{ label: 'Queries', route: { name: 'Queries' } }]" />
		<Button variant="solid" theme="gray" icon-left="lucide-plus" label="New Query" @click="createQuery" />
	</header>

	<div class="flex min-h-0 flex-1 flex-col gap-3 overflow-auto px-5 py-3">
		<div v-if="store.loading" class="flex flex-1 items-center justify-center">
			<LoadingIndicator class="size-6" />
		</div>
		<div v-else-if="store.error" class="rounded-sm border border-outline-red-2 bg-surface-red-1 p-4 text-sm text-ink-red-6">
			Could not load queries.
		</div>
		<List v-else-if="store.queries.length" class="min-h-0 flex-1" :columns="['auto', 'auto', 'auto']">
			<ListHeader>
				<ListHeaderCell v-for="col in ['Title', 'Data Source', 'Modified']" :key="col">{{ col }}</ListHeaderCell>
			</ListHeader>
			<ListRows :items="store.queries" row-key="name">
				<template #default="{ item, value }">
					<ListRow :value="value" @click="openQuery(item.name)">
						<ListCell>{{ item.title }}</ListCell>
						<ListCell>{{ item.data_source }}</ListCell>
						<ListCell>{{ item.modified }}</ListCell>
					</ListRow>
				</template>
			</ListRows>
		</List>
		<div v-else class="mt-10 rounded-lg border border-outline-gray-2 bg-surface-elevation-1 p-10 text-center">
			<p class="text-p-base text-ink-gray-6">
				No unfiled queries. A query saved into a workbook is listed in that workbook, not here -
				this page holds the ones that belong to no container, saved straight from the builder.
			</p>
		</div>
	</div>
</template>
