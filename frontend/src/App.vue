<script setup>
import { computed } from "vue";
import { useRoute } from "vue-router";
import { FrappeUIProvider } from "frappe-ui";
import AppSidebar from "./components/AppSidebar.vue";

/**
 * Workbench shell: a persistent left sidebar (236px) and a scrollable main
 * area. `FrappeUIProvider` keeps the imperative `dialog.*` / `toast.*`
 * portals mounted. The shell tokens flip with `[data-theme="dark"]`.
 *
 * The shell deliberately renders no title bar. It used to carry a `PageHeader`
 * echoing `route.meta.label`, which meant every page showed its own name
 * twice - once from the shell, once from the page's own `<h2>` - and left the
 * drill-down pages rendering breadcrumbs *underneath* a bar that already
 * named where you were. Each route now owns one `h-12` header with
 * `Breadcrumbs` on the left and its actions on the right, which is Insights'
 * arrangement (`src2/workbook/WorkbookList.vue`, `src2/data_store/
 * DataStoreList.vue`) and the only one that can express a hierarchy.
 *
 * Routes flagged `meta.chromeless` opt out of the sidebar entirely: a workbook
 * is a surface you work *inside*, and Insights drops its own app sidebar for
 * exactly those routes (`src2/workbook/Workbook.vue`). The workbook's navbar
 * carries the way back, so nothing becomes unreachable.
 */
const route = useRoute();
const chrome = computed(() => !route.meta?.chromeless);
</script>

<template>
	<FrappeUIProvider>
		<div class="flex h-screen w-screen overflow-hidden bg-surface-base text-ink-gray-8">
			<AppSidebar v-if="chrome" />

			<main class="flex h-full min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
				<router-view />
			</main>
		</div>
	</FrappeUIProvider>
</template>
