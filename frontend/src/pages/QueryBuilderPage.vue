<script setup>
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { Button } from "frappe-ui";
import QueryBuilder from "../components/QueryBuilder.vue";
import { useQuery } from "../composables/useQuery.js";

const route = useRoute();
const router = useRouter();

const isNew = computed(() => route.params.name === "new");
const isFromAsk = computed(() => route.params.name === "from-ask");
const queryName = computed(() => (isNew.value || isFromAsk.value ? null : route.params.name));

const title = computed(() => {
	if (isNew.value) return "New Query";
	if (isFromAsk.value) return "From Ask";
	return queryName.value;
});

const stateOperations = window.history?.state?.operations;

/**
 * Seed pipeline: from Ask (history state), a saved query, or the scaffold sample.
 */
const samplePipeline = [
	{ type: "source", table: "tabSales Invoice" },
	{
		type: "summarize",
		measures: [{ name: "total", expr: { fn: "sum", args: [{ col: "grand_total" }] } }],
		by: [{ name: "territory", expr: { col: "territory" } }],
	},
];

const pipeline = ref(isNew.value ? [] : stateOperations || samplePipeline);
const sql = ref(null);
const results = ref(null);

const queryApi = useQuery(queryName.value);

async function load() {
	if (!queryName.value) return;
	const doc = await queryApi.load(queryName.value);
	if (doc?.operations) {
		pipeline.value = doc.operations;
	}
}

watch(queryName, (name) => {
	if (name) load();
});
load();

async function run(next) {
	pipeline.value = next;
	sql.value = null;
	results.value = null;
	const result = await queryApi.run({
		operations: next,
		data_source: "",
		limit: 1000,
	});
	sql.value = {
		html: `<span>${escapeHtml(result.sql || "")}</span>`,
		plain: result.sql || "",
	};
	results.value = result;
}

async function save() {
	const doc = await queryApi.save({
		name: queryName.value || undefined,
		title: title.value || "Untitled query",
		data_source: "",
		operations: pipeline.value,
	});
	if (isNew.value || isFromAsk.value) {
		// Replace the URL with the persisted query so a refresh lands on the saved doc.
		router.replace({ name: "Query", params: { name: doc.name } });
	}
}

function escapeHtml(value) {
	return String(value)
		.replace(/&/g, "&amp;")
		.replace(/</g, "&lt;")
		.replace(/>/g, "&gt;")
		.replace(/"/g, "&quot;")
		.replace(/'/g, "&#039;");
}
</script>

<template>
	<div class="flex h-full flex-col">
		<div class="flex h-12 flex-none items-center justify-between border-b border-outline-gray-2 px-5">
			<div class="flex items-center gap-2">
				<Button variant="ghost" icon="lucide-arrow-left" @click="router.push({ name: 'Queries' })" />
				<span class="text-base-semibold text-ink-gray-9">{{ title }}</span>
			</div>
			<Button
				variant="solid"
				theme="gray"
				icon-left="lucide-save"
				label="Save"
				:loading="queryApi.saving"
				@click="save"
			/>
		</div>
		<QueryBuilder
			v-model:pipeline="pipeline"
			:sql="sql"
			:results="results"
			:loading="queryApi.running"
			@run="run"
		/>
	</div>
</template>
