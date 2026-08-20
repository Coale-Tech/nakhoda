import { defineStore } from "pinia";
import { ref } from "vue";
import { useWorkbooks } from "../composables/useWorkbook.js";

/**
 * The workbook list. One open workbook is deliberately *not* here: its tree
 * belongs to `useWorkbook(name)` in the builder page, keyed by route, so
 * opening a second workbook cannot leave the first one's queries on screen.
 * This store holds only what more than one surface reads - the list page, and
 * the Ask page's "Save to workbook" dialog.
 */
export const useWorkbookStore = defineStore("workbook", () => {
	const workbooks = ref([]);
	const loading = ref(false);
	const error = ref(null);

	const api = useWorkbooks();

	async function list(searchTerm = null) {
		loading.value = true;
		error.value = null;
		try {
			workbooks.value = await api.list(searchTerm);
			return workbooks.value;
		} catch (e) {
			error.value = e;
		} finally {
			loading.value = false;
		}
	}

	/**
	 * Create one and hand back its name. The list is refetched rather than
	 * appended to: `get_workbooks` computes `views` and share state per row
	 * (`api/workbooks.py:get_workbooks`), and a locally-invented row would be
	 * the one entry in the list whose columns were guesses.
	 */
	async function create(title = null) {
		const name = await api.create(title);
		await list();
		return name;
	}

	return { workbooks, loading, error, list, create };
});
