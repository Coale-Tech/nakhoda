<script setup>
import { onMounted } from "vue";
import { useRouter } from "vue-router";
import { Button, LoadingIndicator } from "frappe-ui";
import { List, ListHeader, ListHeaderCell, ListRow, ListCell, ListRows } from "frappe-ui/list";
import { useQueryStore } from "../stores/query.js";

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
	<div class="flex h-full flex-col p-5">
		<div class="mb-4 flex items-center justify-between">
			<h2 class="text-lg-semibold text-ink-gray-9">Queries</h2>
			<Button variant="solid" theme="gray" icon-left="lucide-plus" label="New Query" @click="createQuery" />
		</div>
		<p class="text-p-base mb-4 text-ink-gray-6">
			Saved queries are Operation JSON pipelines compiled to ibis/DuckDB SQL. Open a generated query from
			Ask in the builder to edit and save it.
		</p>
		<div v-if="store.loading" class="flex flex-1 items-center justify-center">
			<LoadingIndicator class="size-6" />
		</div>
		<div v-else-if="store.error" class="rounded-sm border border-outline-red-2 bg-surface-red-1 p-4 text-sm text-ink-red-6">
			Could not load queries.
		</div>
		<List v-else-if="store.queries.length" class="flex-1" :columns="['auto', 'auto', 'auto']">
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
			<p class="text-p-base text-ink-gray-6">No queries yet.</p>
		</div>
	</div>
</template>
