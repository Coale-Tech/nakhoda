<script setup>
import { useRouter } from "vue-router";
import { Button } from "frappe-ui";
import { useWorkbookStore } from "../stores/workbook.js";

const router = useRouter();
const store = useWorkbookStore();

function createWorkbook() {
	router.push({ name: "Workbook", params: { name: "new" } });
}
</script>

<template>
	<div class="p-5">
		<div class="mb-4 flex items-center justify-between">
			<h2 class="text-lg-semibold text-ink-gray-9">Workbooks</h2>
			<Button variant="solid" theme="gray" icon-left="lucide-plus" label="New Workbook" @click="createWorkbook" />
		</div>
		<p class="text-p-base text-ink-gray-6">
			Workbooks are named collections of queries, charts, and dashboards. They are shareable, versioned,
			and record the semantic-model version and prompt that produced each artifact.
		</p>
		<div v-if="!store.workbooks.length" class="mt-10 rounded-lg border border-outline-gray-2 bg-surface-elevation-1 p-10 text-center">
			<p class="text-p-base text-ink-gray-6">No workbooks yet.</p>
		</div>
	</div>
</template>
