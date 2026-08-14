import { defineStore } from "pinia";
import { ref, computed } from "vue";

/**
 * Stub store for workbooks. Will later hold the workbook list, the active
 * workbook, its queries/charts/dashboards, and share/version state.
 */
export const useWorkbookStore = defineStore("workbook", () => {
	const workbooks = ref([]);
	const loading = ref(false);
	const activeName = ref(null);

	const active = computed(() => workbooks.value.find((w) => w.name === activeName.value) || null);

	function open(name) {
		activeName.value = name;
	}

	return { workbooks, loading, activeName, active, open };
});
