<script setup>
import { LoadingIndicator } from "frappe-ui";
import { onMounted, ref } from "vue";
import { useDashboard } from "../composables/useDashboard.js";
import VegaChart from "./VegaChart.vue";

/**
 * One panel, loading its own rows.
 *
 * Deliberately not folded into `get_dashboard_data`: that call computes every
 * metric in a single execution because they share one pipeline, whereas each
 * panel is its own query with its own cache entry. Fetching here means the
 * grid paints as answers arrive rather than blocking on the slowest panel -
 * and a panel whose query is broken shows its own error instead of taking the
 * dashboard down.
 */
const props = defineProps({
	dashboard: { type: String, required: true },
	panel: { type: Object, required: true },
});

const api = useDashboard();
const data = ref(null);
const error = ref("");
const loading = ref(true);

onMounted(async () => {
	try {
		data.value = await api.panelData(props.dashboard, props.panel.i);
	} catch (e) {
		error.value = e?.messages?.[0] || e?.message || "Could not run this panel";
	} finally {
		loading.value = false;
	}
});
</script>

<template>
	<div class="panel rounded-lg border border-outline-gray-2 p-4" :data-panel="panel.i">
		<p class="text-p-base font-medium text-ink-gray-9">{{ panel.title || panel.i }}</p>

		<div v-if="loading" class="flex h-40 items-center justify-center">
			<LoadingIndicator class="size-4" />
		</div>
		<p v-else-if="error" class="mt-3 text-p-sm text-ink-red-4">{{ error }}</p>
		<p v-else-if="!data?.rows?.length" class="mt-3 text-p-sm text-ink-gray-5">No rows.</p>
		<VegaChart
			v-else
			:columns="data.columns"
			:rows="data.rows"
			:chart-type="data.chart_type"
			:semantic-types="data.semantic_types || {}"
			:field-display-names="data.field_display_names || {}"
		/>
	</div>
</template>
