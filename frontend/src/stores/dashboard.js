import { defineStore } from "pinia";
import { ref, computed } from "vue";

/**
 * Stub store for dashboards. Will later hold the dashboard list, grid layout,
 * filters, and the patch/diff review state used by Phase 10.
 */
export const useDashboardStore = defineStore("dashboard", () => {
	const dashboards = ref([]);
	const loading = ref(false);
	const activeName = ref(null);

	const active = computed(() => dashboards.value.find((d) => d.name === activeName.value) || null);

	function open(name) {
		activeName.value = name;
	}

	return { dashboards, loading, activeName, active, open };
});
