<script setup>
import { useRouter } from "vue-router";
import { Button } from "frappe-ui";
import { useDashboardStore } from "../stores/dashboard.js";

const router = useRouter();
const store = useDashboardStore();

function createDashboard() {
	router.push({ name: "Dashboard", params: { name: "new" } });
}
</script>

<template>
	<div class="p-5">
		<div class="mb-4 flex items-center justify-between">
			<h2 class="text-lg-semibold text-ink-gray-9">Dashboards</h2>
			<Button variant="solid" theme="gray" icon-left="lucide-plus" label="New Dashboard" @click="createDashboard" />
		</div>
		<p class="text-p-base text-ink-gray-6">
			Saved dashboards appear here. Each dashboard is a grid of charts and filters that updates from
			shared workbook queries.
		</p>
		<div v-if="!store.dashboards.length" class="mt-10 rounded-lg border border-outline-gray-2 bg-surface-elevation-1 p-10 text-center">
			<p class="text-p-base text-ink-gray-6">No dashboards yet.</p>
		</div>
	</div>
</template>
