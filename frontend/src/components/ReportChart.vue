<script setup>
import { LoadingIndicator, useCall } from "frappe-ui";
import { onMounted, ref } from "vue";
import VegaChart from "./VegaChart.vue";

/**
 * One `chart://<agent run>` reference inside a report, re-executed on read.
 *
 * The failure is shown in place and never thrown: a report is prose the reader
 * came for, and one unreadable citation must not blank the paragraphs around
 * it. A run the reader may not read is exactly that case - `run_chart` refuses
 * it, and the note that appears is the honest answer.
 */
const props = defineProps({
	agentRun: { type: String, required: true },
});

const call = useCall({
	url: "/api/v2/method/nakhoda.api.agent.run_chart",
	method: "GET",
	immediate: false,
});

const data = ref(null);
const error = ref("");
const loading = ref(true);

onMounted(async () => {
	try {
		const result = await call.submit({ agent_run: props.agentRun });
		if (call.error) throw call.error;
		data.value = result?.data ?? result;
	} catch (e) {
		error.value = e?.messages?.[0] || e?.message || "Could not draw this result";
	} finally {
		loading.value = false;
	}
});
</script>

<template>
	<div class="report-chart rounded-lg border border-outline-gray-2 p-3" :data-agent-run="agentRun">
		<div v-if="loading" class="flex h-32 items-center justify-center">
			<LoadingIndicator class="size-4" />
		</div>
		<p v-else-if="error" class="text-p-sm text-ink-gray-5">
			{{ error }}
			<span class="font-mono text-ink-gray-4">{{ agentRun }}</span>
		</p>
		<p v-else-if="!data?.rows?.length" class="text-p-sm text-ink-gray-5">No rows for this result.</p>
		<VegaChart
			v-else
			:columns="data.columns"
			:rows="data.rows"
			:title="data.title"
			:semantic-types="data.semantic_types || {}"
			:field-display-names="data.field_display_names || {}"
		/>
	</div>
</template>
