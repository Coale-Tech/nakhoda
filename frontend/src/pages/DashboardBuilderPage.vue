<script setup>
import { computed } from "vue";
import { useRoute, useRouter } from "vue-router";
import { Button } from "frappe-ui";
import { useDashboardStore } from "../stores/dashboard.js";

const route = useRoute();
const router = useRouter();
const store = useDashboardStore();

const isNew = computed(() => route.params.name === "new");
const title = computed(() => (isNew.value ? "New Dashboard" : route.params.name));
</script>

<template>
	<div class="flex h-full flex-col">
		<div class="flex h-12 items-center justify-between border-b border-outline-gray-2 px-5">
			<div class="flex items-center gap-2">
				<Button variant="ghost" icon="lucide-arrow-left" @click="router.push({ name: 'Dashboards' })" />
				<span class="text-base-semibold text-ink-gray-9">{{ title }}</span>
			</div>
			<Button v-if="!isNew" variant="solid" theme="gray" icon-left="lucide-save" label="Save" />
		</div>
		<div class="flex-1 p-5">
			<p class="text-p-base text-ink-gray-6">
				Dashboard builder grid. Add charts from workbooks, set filters, and arrange widgets.
				Phase 10 adds the patch/diff review surface.
			</p>
		</div>
	</div>
</template>
