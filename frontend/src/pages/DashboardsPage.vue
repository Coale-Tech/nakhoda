<script setup>
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { Breadcrumbs, Button, LoadingIndicator } from "frappe-ui";
import TemplateGallery from "../components/TemplateGallery.vue";
import { useDashboardStore } from "../stores/dashboard.js";

const router = useRouter();
const store = useDashboardStore();
const showGallery = ref(false);

onMounted(() => {
	store.fetchDashboards();
});

function openDashboard(name) {
	router.push({ name: "Dashboard", params: { name } });
}
</script>

<template>
	<header
		class="flex h-12 shrink-0 items-center justify-between border-b border-outline-gray-2 py-2.5 pl-5 pr-2"
	>
		<Breadcrumbs :items="[{ label: 'Dashboards', route: { name: 'Dashboards' } }]" />
		<Button
			variant="solid"
			theme="gray"
			icon-left="lucide-plus"
			label="New from Template"
			@click="showGallery = true"
		/>
	</header>

	<div class="flex min-h-0 flex-1 flex-col gap-3 overflow-auto px-5 py-3">
		<div v-if="store.loading" class="flex items-center justify-center py-10">
			<LoadingIndicator class="size-6" />
		</div>
		<div
			v-else-if="store.error"
			class="rounded-sm border border-outline-red-2 bg-surface-red-1 p-4 text-sm text-ink-red-6"
		>
			Could not load dashboards.
		</div>
		<div
			v-else-if="!store.dashboards.length"
			class="mt-10 rounded-lg border border-outline-gray-2 bg-surface-elevation-1 p-10 text-center"
		>
			<p class="text-p-base text-ink-gray-6">
				No dashboards yet. Each one is a domain Intelligence Template instantiated for this site, with
				its own metrics, panels and data source.
			</p>
			<Button class="mt-3" variant="solid" theme="gray" label="Browse templates" @click="showGallery = true" />
		</div>
		<div v-else class="grid grid-cols-3 gap-3">
			<button
				v-for="dashboard in store.dashboards"
				:key="dashboard.name"
				class="flex flex-col items-start gap-2 rounded-lg border border-outline-gray-2 p-4 text-left hover:bg-surface-gray-1"
				@click="openDashboard(dashboard.name)"
			>
				<span
					class="grid size-8 place-items-center rounded-md"
					:style="{ backgroundColor: (dashboard.color || '#6B7280') + '20', color: dashboard.color || '#6B7280' }"
				>
					<span :class="`lucide-${dashboard.icon || 'layout-grid'}`" class="size-4" aria-hidden="true" />
				</span>
				<span class="text-base-semibold text-ink-gray-9">{{ dashboard.title }}</span>
				<span class="text-xs text-ink-gray-5">Updated {{ dashboard.modified }}</span>
			</button>
		</div>
	</div>
	<TemplateGallery v-model="showGallery" />
</template>
