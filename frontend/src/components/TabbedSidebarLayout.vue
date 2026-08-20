<script setup>
import { computed } from "vue";
import SidebarLink from "./SidebarLink.vue";

/**
 * Ported from Insights' `src2/components/TabbedSidebarLayout.vue`: a fixed
 * sidebar of grouped tabs on the left, the active tab's component filling
 * the rest. One difference from the source, to avoid a second icon
 * convention next to the one this app already has:
 *
 * - Icons are `lucide-*` CSS classes resolved by `SidebarLink` (this app's
 *   existing icon convention, see `AppSidebar.vue`), not imported
 *   `lucide-vue-next` components - that package isn't a dependency here.
 *
 * Mounted by `settings/Settings.vue` inside a `bare` `Dialog`, same as
 * Insights mounts its own copy inside its Settings dialog.
 *
 * `tabs` accepts either a flat array of `{ label, icon, component }` or an
 * array of `{ groupLabel, tabs }` groups; a flat array is normalised into
 * one unlabelled group.
 */
const props = defineProps({
	title: { type: String, default: null },
	tabs: { type: Array, required: true },
});

const activeTab = defineModel("activeTab");

const tabGroups = computed(() => {
	if (!props.tabs.length) return [];
	if (Object.prototype.hasOwnProperty.call(props.tabs[0], "tabs")) {
		return props.tabs;
	}
	return [{ groupLabel: "", tabs: props.tabs }];
});
</script>

<template>
	<div class="flex h-full w-full">
		<div
			class="flex w-52 shrink-0 flex-col overflow-y-auto border-r border-outline-gray-2 bg-surface-gray-1 p-2"
		>
			<h2 v-if="title" class="px-2 pt-2 text-base-semibold text-ink-gray-9">{{ title }}</h2>
			<div v-for="group in tabGroups" :key="group.groupLabel" class="flex flex-col">
				<div
					v-if="group.groupLabel"
					class="mb-2 mt-4 px-2 text-p-sm font-medium text-ink-gray-5"
				>
					{{ group.groupLabel }}
				</div>
				<nav class="flex flex-col gap-0.5 p-0.5">
					<SidebarLink
						v-for="tab in group.tabs"
						:key="tab.label"
						:icon="tab.icon"
						:label="tab.label"
						:is-active="activeTab?.label === tab.label"
						@click="activeTab = tab"
					/>
				</nav>
			</div>
		</div>
		<div class="flex h-full flex-1 flex-col overflow-hidden">
			<component :is="activeTab.component" v-if="activeTab?.component" />
		</div>
	</div>
</template>
