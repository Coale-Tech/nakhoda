import { defineStore } from "pinia";
import { ref } from "vue";
import { useQuery } from "../composables/useQuery.js";

/**
 * Query list store. Uses `useQuery` to fetch the list of saved Nakhoda Query
 * docs and tracks the selected item for the workbench layout.
 */
export const useQueryStore = defineStore("query", () => {
	const queries = ref([]);
	const loading = ref(false);
	const error = ref(null);
	const selectedId = ref(null);

	const queryApi = useQuery();

	async function fetchQueries() {
		loading.value = true;
		error.value = null;
		try {
			queries.value = await queryApi.list();
		} catch (e) {
			error.value = e;
			throw e;
		} finally {
			loading.value = false;
		}
	}

	function select(id) {
		selectedId.value = id;
	}

	return { queries, loading, error, selectedId, fetchQueries, select };
});
