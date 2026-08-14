<script setup>
import { computed } from "vue";
import { useRoute } from "vue-router";
import { FrappeUIProvider, PageHeader } from "frappe-ui";
import AppSidebar from "./components/AppSidebar.vue";

/**
 * Workbench shell. A persistent left sidebar (236px) for navigation, a top
 * PageHeader showing the active route label, and a scrollable main area for
 * the current route. `FrappeUIProvider` keeps the imperative `dialog.*` /
 * `toast.*` portals mounted. The shell tokens flip with `[data-theme="dark"]`.
 */
const route = useRoute();
const pageTitle = computed(() => route.meta?.label || route.name || "Nakhoda");
</script>

<template>
	<FrappeUIProvider>
		<div class="flex h-screen w-screen overflow-hidden bg-surface-base text-ink-gray-8">
			<AppSidebar />

			<div class="flex h-full min-w-0 flex-1 flex-col">
				<PageHeader>
					<div class="flex h-full items-center px-4">
						<span class="text-base-semibold text-ink-gray-9">{{ pageTitle }}</span>
					</div>
				</PageHeader>

				<main class="flex-1 overflow-auto">
					<router-view />
				</main>
			</div>
		</div>
	</FrappeUIProvider>
</template>
