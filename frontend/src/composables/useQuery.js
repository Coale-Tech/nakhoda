import { computed, reactive, ref } from "vue";
import { useCall } from "frappe-ui";

/**
 * Query CRUD + execution for the workbench query builder.
 *
 * `useCall` unwraps the v2 API envelope (`{data: ...}`) and sends CSRF/site
 * headers automatically. All endpoints are whitelisted in `nakhoda/api/`.
 */
export function useQuery(name = null) {
	const loading = ref(false);
	const saving = ref(false);
	const running = ref(false);
	const error = ref(null);
	const queryName = ref(name);

	const getCall = useCall({
		url: computed(() => {
			const target = queryName.value || name;
			return target ? `/api/v2/document/Nakhoda Query/${encodeURIComponent(target)}` : "";
		}),
		immediate: false,
		method: "GET",
	});

	const listCall = useCall({
		url: "/api/v2/method/nakhoda.api.query.list_queries",
		method: "GET",
		immediate: false,
	});

	const saveCall = useCall({
		url: "/api/v2/method/nakhoda.api.query.save_query",
		method: "POST",
		immediate: false,
	});

	const deleteCall = useCall({
		url: "/api/v2/method/nakhoda.api.query.delete_query",
		method: "POST",
		immediate: false,
	});

	const runCall = useCall({
		url: "/api/v2/method/nakhoda.api.run",
		method: "POST",
		immediate: false,
	});

	const executeCall = useCall({
		url: "/api/v2/method/nakhoda.api.execute",
		method: "POST",
		immediate: false,
	});

	async function load(nextName) {
		const target = nextName || name;
		if (!target) return;
		loading.value = true;
		error.value = null;
		try {
			queryName.value = target;
			const result = await getCall.submit();
			return result.data ?? result;
		} catch (e) {
			error.value = e;
			throw e;
		} finally {
			loading.value = false;
		}
	}

	async function list(filters = {}) {
		loading.value = true;
		error.value = null;
		try {
			const result = await listCall.submit(filters);
			return result.data ?? result;
		} catch (e) {
			error.value = e;
			throw e;
		} finally {
			loading.value = false;
		}
	}

	async function save(payload) {
		saving.value = true;
		error.value = null;
		try {
			const result = await saveCall.submit(payload);
			return result.data ?? result;
		} catch (e) {
			error.value = e;
			throw e;
		} finally {
			saving.value = false;
		}
	}

	async function remove(queryName) {
		loading.value = true;
		error.value = null;
		try {
			const result = await deleteCall.submit({ name: queryName || name });
			return result.data ?? result;
		} catch (e) {
			error.value = e;
			throw e;
		} finally {
			loading.value = false;
		}
	}

	async function run({ operations, data_source, limit }) {
		running.value = true;
		error.value = null;
		try {
			const result = await runCall.submit({ operations, data_source, limit });
			return result.data ?? result;
		} catch (e) {
			error.value = e;
			throw e;
		} finally {
			running.value = false;
		}
	}

	async function execute(queryName) {
		running.value = true;
		error.value = null;
		try {
			const result = await executeCall.submit({ query: queryName || name });
			return result.data ?? result;
		} catch (e) {
			error.value = e;
			throw e;
		} finally {
			running.value = false;
		}
	}

	return reactive({
		loading,
		saving,
		running,
		error,
		load,
		list,
		save,
		remove,
		run,
		execute,
		// Exposed for consumers that want to bind directly to useCall state
		getCall,
		listCall,
		saveCall,
		deleteCall,
		runCall,
		executeCall,
	});
}
