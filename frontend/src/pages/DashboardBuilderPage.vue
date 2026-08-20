<script setup>
import { computed, onMounted, ref, watch } from "vue";
import { useRoute } from "vue-router";
import { Breadcrumbs, Button, LoadingIndicator } from "frappe-ui";
import { useDashboardStore } from "../stores/dashboard.js";
import DashboardAskPanel from "../components/DashboardAskPanel.vue";
import DashboardPanel from "../components/DashboardPanel.vue";

/**
 * One dashboard. Chrome is the app-wide `h-12` header carrying `Breadcrumbs`,
 * the same two-item trail Insights' `dashboard/Dashboard.vue` renders
 * (`Dashboards` -> this one) - a back arrow says only "leave", crumbs say
 * where you are.
 */
const route = useRoute();
const store = useDashboardStore();

const isNew = computed(() => route.params.name === "new");

function load() {
	if (!isNew.value) store.open(route.params.name);
}

onMounted(load);
watch(() => route.params.name, load);

const title = computed(() => store.activeData?.title || route.params.name);

const crumbs = computed(() => [
	{ label: "Dashboards", route: { name: "Dashboards" } },
	{
		label: isNew.value ? "New Dashboard" : title.value,
		route: { name: "Dashboard", params: { name: route.params.name } },
	},
]);

function formatValue(metric) {
	if (metric.value === null || metric.value === undefined) return "—";
	const value = Number(metric.value);
	if (Number.isNaN(value)) return String(metric.value);
	if (metric.format === "Currency")
		return value.toLocaleString(undefined, { style: "currency", currency: "USD" });
	if (metric.format === "Percent") return `${(value * 100).toFixed(1)}%`;
	return value.toLocaleString();
}

/** Ask is opt-in and remembered per visit, not per dashboard: the thread it
 *  shows already survives closing the panel (`stores/ask.js`), so this flag is
 *  chrome rather than state worth persisting. */
const asking = ref(false);

/**
 * Bumped when an applied patch changes the panels. Every panel fetches its own
 * rows once, on mount, so a `set_filter` that keeps a panel's `i` would
 * otherwise leave the old numbers on screen - keying on the revision remounts
 * exactly the panels a change could have touched, which is all of them.
 */
const revision = ref(0);

/** `refresh`, not `open`: the panel that proposed the patch is inside the
 *  branch `open`'s loading state unmounts, and it holds the only handle on
 *  undoing the change (`stores/dashboard.js:refresh`). */
async function reload() {
	await store.refresh(route.params.name);
	revision.value += 1;
}
</script>

<template>
	<header
		class="flex h-12 shrink-0 items-center justify-between border-b border-outline-gray-2 py-2.5 pl-5 pr-2"
	>
		<Breadcrumbs :items="crumbs" />
		<Button
			v-if="!isNew"
			:variant="asking ? 'subtle' : 'ghost'"
			size="sm"
			icon-left="lucide-sparkles"
			label="Ask"
			@click="asking = !asking"
		/>
	</header>

	<div v-if="isNew" class="flex-1 p-5">
		<p class="text-p-base text-ink-gray-6">
			Dashboards are created from a template - go back and pick one from
			<span class="font-medium">New from Template</span>.
		</p>
	</div>

	<div v-else-if="store.activeLoading" class="flex flex-1 items-center justify-center">
		<LoadingIndicator class="size-6" />
	</div>

	<div
		v-else-if="store.activeError"
		class="m-5 rounded-sm border border-outline-red-2 bg-surface-red-1 p-4 text-sm text-ink-red-6"
	>
		Could not load this dashboard.
	</div>

	<div v-else class="flex min-h-0 flex-1">
		<div class="min-h-0 flex-1 overflow-y-auto p-5">
			<div
				v-if="!store.activeData?.metrics_available"
				class="mb-4 rounded-sm border border-outline-gray-2 bg-surface-gray-1 p-3 text-sm text-ink-gray-6"
			>
				{{ store.activeData?.reason || "Metrics are not available yet." }}
			</div>

			<div v-if="store.activeData?.metrics?.length" class="mb-6 grid grid-cols-4 gap-3">
				<div
					v-for="metric in store.activeData.metrics"
					:key="metric.label"
					class="rounded-lg border border-outline-gray-2 p-4"
				>
					<p class="text-p-sm text-ink-gray-6">{{ metric.label }}</p>
					<p class="text-2xl-semibold mt-1 text-ink-gray-9">{{ formatValue(metric) }}</p>
				</div>
			</div>

			<div
				v-if="!store.activeData?.panels?.length"
				class="rounded-lg border border-outline-gray-2 bg-surface-elevation-1 p-10 text-center"
			>
				<p class="text-p-base text-ink-gray-6">No panels on this dashboard yet.</p>
			</div>
			<div v-else class="grid grid-cols-2 gap-3">
				<!-- `panel.i` is the panel's identity everywhere else in the system -
				     `engine/dashboard.py` mints it, `set_filter`/`remove_item` name
				     it, `panel_data` looks it up. `panel.id` never existed, so every
				     panel keyed on `undefined` and Vue reused one DOM node for all
				     of them. The revision suffix remounts a panel whose filter an
				     approved patch just changed. -->
				<DashboardPanel
					v-for="panel in store.activeData.panels"
					:key="`${panel.i}:${revision}`"
					:dashboard="store.activeName"
					:panel="panel"
				/>
			</div>
		</div>

		<DashboardAskPanel
			v-if="asking"
			:dashboard="store.activeName"
			@changed="reload"
			@close="asking = false"
		/>
	</div>
</template>
