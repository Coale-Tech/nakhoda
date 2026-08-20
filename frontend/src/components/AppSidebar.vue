<script setup>
import { computed, ref } from "vue";
import { useRoute } from "vue-router";
import { useStorage } from "@vueuse/core";
import SidebarLink from "./SidebarLink.vue";
import Settings from "../settings/Settings.vue";
import { useSessionStore } from "../stores/session.js";

/**
 * Persistent left navigation for the workbench, styled after Insights'
 * `AppSidebar.vue`: a collapsible rail (48px icons-only / 224px full) with
 * grouped links, an uppercase group label per section, and a collapse toggle
 * pinned to the bottom. The collapsed preference persists across sessions
 * the same way Insights does it, keyed per-app so the two don't collide.
 */
const route = useRoute();
const isCollapsed = useStorage("nakhoda:sidebarCollapsed", false);
const session = useSessionStore();

/**
 * Served by Frappe's asset pipeline (`nakhoda/public/nakhoda-logo.png`,
 * symlinked to `sites/assets/nakhoda/...` on `bench build`) - not a file
 * inside this Vite project. Bound via `:src` rather than a static template
 * attribute so `@vitejs/plugin-vue`'s asset-url transform leaves it as a
 * plain runtime string instead of trying to resolve/bundle it.
 */
const logoUrl = "/assets/nakhoda/nakhoda-logo.png";

/**
 * `computed`, not a constant, for exactly one link: Insights hides its Data
 * Store entry when the store is switched off
 * (`src2/components/AppSidebar.vue:167`, `hidden: !settings.doc.enable_data_store`)
 * and it is the only conditional entry in that sidebar either. The route
 * stays registered, as it does in Insights - a bookmark or a back button
 * still resolves, and `DataStorePage.vue` says why the import affordances
 * are gone rather than offering buttons `api/data_store.py` would refuse.
 *
 * The flag comes from the session store (boot-seeded, write-through on
 * Settings save) rather than a settings GET here: this component mounts for
 * every user, and `Nakhoda Settings` is unreadable to a plain `Nakhoda User`.
 */
const navGroups = computed(() => [
	{
		label: "Workbench",
		links: [
			{ label: "Ask", icon: "lucide-message-circle", to: "Ask" },
			{ label: "Dashboards", icon: "lucide-layout-grid", to: "Dashboards", isActive: (n) => n === "Dashboard" },
			{
				label: "Workbooks",
				icon: "lucide-book-open",
				to: "Workbooks",
				isActive: (n) => n === "Workbook" || n === "Workbook Item",
			},
			{ label: "Queries", icon: "lucide-database", to: "Queries", isActive: (n) => n === "Query" },
		],
	},
	{
		label: "Data",
		links: [
			{
				label: "Data Sources",
				icon: "lucide-plug",
				to: "Data Sources",
				isActive: (n) => n === "Data Sources" || n === "Data Source Tables" || n === "Data Source Table",
			},
			{
				label: "Data Store",
				icon: "lucide-server",
				to: "Data Store",
				hidden: !session.dataStoreEnabled,
			},
		],
	},
]);

function isGroupLinkActive(link) {
	return link.isActive ? link.isActive(route.name) : route.name === link.to;
}

// Not a route: mirrors Insights' `AppSidebar.vue`, which opens Settings as
// a dialog (`showSettingsDialog`) rather than navigating - see
// `settings/Settings.vue`'s header for why every other link here is a
// route and this one deliberately isn't.
const showSettingsDialog = ref(false);
</script>

<template>
	<nav
		aria-label="Main"
		class="flex h-full flex-col justify-between border-r border-outline-gray-2 bg-surface-gray-1 transition-all duration-300 ease-in-out motion-reduce:transition-none"
		:class="isCollapsed ? 'w-12' : 'w-56'"
	>
		<div class="flex flex-col overflow-hidden">
			<div class="flex h-12 items-center gap-2 overflow-hidden px-3">
				<img :src="logoUrl" alt="" class="h-6 w-6 flex-shrink-0 rounded" />
				<span
					class="text-base-semibold text-ink-gray-9 duration-300 ease-in-out motion-reduce:transition-none"
					:class="isCollapsed ? 'w-0 overflow-hidden opacity-0' : 'w-auto truncate opacity-100'"
				>
					Nakhoda
				</span>
			</div>
			<div class="flex flex-col overflow-y-auto px-2 pb-2">
				<template v-for="group in navGroups" :key="group.label">
					<div
						v-if="!isCollapsed"
						class="px-2 pb-1 pt-3 text-xs font-medium uppercase tracking-wide text-ink-gray-5"
					>
						{{ group.label }}
					</div>
					<template v-for="link in group.links" :key="link.to">
						<SidebarLink
							v-if="!link.hidden"
							class="my-0.5"
							:icon="link.icon"
							:label="link.label"
							:to="link.to"
							:is-active="isGroupLinkActive(link)"
							:is-collapsed="isCollapsed"
						/>
					</template>
				</template>
			</div>
		</div>
		<div class="border-t border-outline-gray-2 px-2 py-2">
			<SidebarLink
				label="Settings"
				icon="lucide-settings"
				:is-collapsed="isCollapsed"
				class="my-0.5"
				@click="showSettingsDialog = true"
			/>
			<SidebarLink
				:label="isCollapsed ? 'Expand' : 'Collapse'"
				:icon="isCollapsed ? 'lucide-panel-left-open' : 'lucide-panel-left-close'"
				:is-collapsed="isCollapsed"
				class="my-0.5"
				@click="isCollapsed = !isCollapsed"
			/>
		</div>
	</nav>

	<Settings v-model="showSettingsDialog" />
</template>
