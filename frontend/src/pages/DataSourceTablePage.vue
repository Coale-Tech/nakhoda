<script setup>
import { computed, onMounted, watch } from "vue";
import { Badge, Breadcrumbs, LoadingIndicator } from "frappe-ui";
import DataTable from "../components/DataTable.vue";
import { useSourceTables } from "../composables/useDataSources.js";

/**
 * A bounded preview of one table. Ported from Insights' `DataSourceTable.vue`,
 * rendered through this app's own `DataTable` rather than a second table
 * component - the result grid a query returns and the preview a source shows
 * are the same artefact, and two of them would drift.
 *
 * The rows arrive already row- and column-filtered: the endpoint runs them
 * through `engine.pipeline.run` behind `for_user`, the same resolver every
 * query uses (`api/data_sources.py:get_source_table`). A viewer's preview is
 * therefore their own slice, not a redacted view of everyone's.
 *
 * Chrome is the app-wide `h-12` header: crumbs left, the truncation notice
 * right, where Insights puts the same pair (`src2/data_source/
 * DataSourceTable.vue`).
 */
const props = defineProps({
	name: { type: String, required: true },
	table: { type: String, required: true },
});

const store = useSourceTables();

// Failures land on `store.error`, which the template renders; rethrowing past
// that point only produces an unhandled rejection.
function load() {
	store.load(props.name).catch(() => {});
	store.fetchPreview(props.name, props.table).catch(() => {});
}

onMounted(load);
watch(() => [props.name, props.table], load);

/**
 * A column is right-aligned when every non-empty value in it is a number -
 * decided from the data because the preview carries no column metadata, and
 * guessing from the name would right-align `phone` and left-align `qty`.
 */
const tableColumns = computed(() => {
	const preview = store.preview;
	if (!preview) return [];
	return preview.columns.map((label) => {
		const values = preview.rows.map((r) => r[label]).filter((v) => v !== null && v !== "");
		const numeric = values.length > 0 && values.every((v) => typeof v === "number");
		return { label, align: numeric ? "num" : undefined };
	});
});

const tableRows = computed(() => {
	const preview = store.preview;
	if (!preview) return [];
	return preview.rows.map((row) => ({
		cells: preview.columns.map((col) => {
			const value = row[col];
			return { text: value === null || value === undefined ? "\u2014" : String(value), muted: value === null };
		}),
	}));
});

const crumbs = computed(() => [
	{ label: "Data Sources", route: { name: "Data Sources" } },
	{ label: store.source?.title || props.name, route: { name: "Data Source Tables", params: { name: props.name } } },
	{ label: props.table, route: { name: "Data Source Table", params: { name: props.name, table: props.table } } },
]);
</script>

<template>
	<header
		class="flex h-12 shrink-0 items-center justify-between border-b border-outline-gray-2 py-2.5 pl-5 pr-2"
	>
		<Breadcrumbs :items="crumbs" />
		<Badge v-if="store.preview?.truncated" theme="gray" variant="subtle">
			First {{ store.preview.row_count }} rows
		</Badge>
	</header>

	<div class="flex min-h-0 flex-1 flex-col gap-3 overflow-auto px-5 py-3">
		<div v-if="store.previewing && !store.preview" class="flex flex-1 items-center justify-center">
			<LoadingIndicator class="size-6" />
		</div>
		<div
			v-else-if="store.error"
			class="rounded-sm border border-outline-red-2 bg-surface-red-1 p-4 text-sm text-ink-red-6"
		>
			Could not preview this table.
		</div>
		<template v-else-if="store.preview">
			<p class="text-p-sm font-mono text-ink-gray-6">{{ store.preview.table_name }}</p>
			<div v-if="!store.preview.row_count" class="rounded-lg border border-outline-gray-2 bg-surface-elevation-1 p-10 text-center">
				<p class="text-p-base text-ink-gray-6">No rows visible to you in this table.</p>
			</div>
			<div v-else class="min-h-0 flex-1 overflow-auto">
				<DataTable :columns="tableColumns" :rows="tableRows" />
			</div>
		</template>
	</div>
</template>
