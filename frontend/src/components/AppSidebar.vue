<script setup>
import { computed } from "vue";
import { useRoute, useRouter } from "vue-router";
import { Button } from "frappe-ui";

/**
 * Persistent left navigation for the workbench. Mirrors the route table in
 * `router.js`: every primary list route gets a link. Active state is derived
 * from the current route name. The sidebar collapses to icons on narrow viewports
 * but keeps the labels accessible via `aria-label`.
 */
const route = useRoute();
const router = useRouter();

const links = [
	{ name: "Ask", label: "Ask", icon: "lucide-message-circle" },
	{ name: "Dashboards", label: "Dashboards", icon: "lucide-layout-grid" },
	{ name: "Workbooks", label: "Workbooks", icon: "lucide-book-open" },
	{ name: "Queries", label: "Queries", icon: "lucide-database" },
	{ name: "Data Sources", label: "Data Sources", icon: "lucide-plug" },
	{ name: "Data Store", label: "Data Store", icon: "lucide-server" },
	{ name: "Settings", label: "Settings", icon: "lucide-settings" },
];

const isActive = (name) => {
	// Builder routes (Dashboard, Workbook, Query) highlight their parent list item.
	if (name === "Dashboards" && route.name === "Dashboard") return true;
	if (name === "Workbooks" && route.name === "Workbook") return true;
	if (name === "Queries" && route.name === "Query") return true;
	return route.name === name;
};

function navigate(name) {
	router.push({ name });
}

const activeLink = computed(() => links.find((l) => isActive(l.name)));
</script>

<template>
	<aside class="flex h-full w-[236px] flex-col border-r border-outline-gray-2 bg-surface-gray-1">
		<div class="flex h-12 items-center gap-2 px-4">
			<span class="text-base-semibold text-ink-gray-9">Nakhoda</span>
		</div>
		<nav class="flex flex-1 flex-col gap-1 px-3 py-2" aria-label="Workbench">
			<Button
				v-for="link in links"
				:key="link.name"
				variant="ghost"
				class="justify-start gap-2"
				:class="isActive(link.name) ? 'bg-surface-gray-2 text-ink-gray-9' : 'text-ink-gray-6'"
				:icon-left="link.icon"
				:label="link.label"
				@click="navigate(link.name)"
			/>
		</nav>
		<div class="border-t border-outline-gray-2 px-4 py-3">
			<div class="text-xs text-ink-gray-5">Active</div>
			<div class="text-sm-medium text-ink-gray-8">{{ activeLink?.label || "Ask" }}</div>
		</div>
	</aside>
</template>
