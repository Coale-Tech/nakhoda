import { reactive, ref } from "vue";
import { useCall } from "frappe-ui";

/**
 * Configured `Nakhoda Data Source` rows.
 *
 * Three shapes of row, one list: the site database and the DuckDB warehouse
 * are created on demand by the backend (`nakhoda.api.default_source`,
 * `data_store._warehouse_source`) and cannot be edited or removed here -
 * their credentials come from `site_config.json` - while an external database
 * is created from the New Source dialog, re-pointed, and deleted through the
 * endpoints below. That split is enforced in the backend
 * (`update_data_source` refuses non-external rows, `on_trash` refuses the
 * built-ins), not just hidden in this UI.
 *
 * Endpoints live in `nakhoda.api.data_sources`, split out of `api.data_store`
 * when this page grew a per-source table list and a preview screen: that
 * module moves data into the warehouse, this one describes what is there.
 */
export function useDataSources() {
	const loading = ref(false);
	const testing = ref(null); // name of the saved row currently under test, or null
	const probing = ref(false); // an unsaved connection form is being tested
	const saving = ref(false); // create/update/delete in flight
	const error = ref(null);
	const sources = ref([]);

	const listCall = useCall({
		url: "/api/v2/method/nakhoda.api.data_sources.list_data_sources",
		method: "GET",
		immediate: false,
	});

	const testCall = useCall({
		url: "/api/v2/method/nakhoda.api.data_sources.test_data_source",
		method: "POST",
		immediate: false,
	});

	const setDefaultCall = useCall({
		url: "/api/v2/method/nakhoda.api.data_sources.set_default_data_source",
		method: "POST",
		immediate: false,
	});

	const probeCall = useCall({
		url: "/api/v2/method/nakhoda.api.data_sources.test_connection",
		method: "POST",
		immediate: false,
	});

	const createCall = useCall({
		url: "/api/v2/method/nakhoda.api.data_sources.create_data_source",
		method: "POST",
		immediate: false,
	});

	const updateCall = useCall({
		url: "/api/v2/method/nakhoda.api.data_sources.update_data_source",
		method: "POST",
		immediate: false,
	});

	const deleteCall = useCall({
		url: "/api/v2/method/nakhoda.api.data_sources.delete_data_source",
		method: "POST",
		immediate: false,
	});

	const getCall = useCall({
		url: "/api/v2/method/nakhoda.api.data_sources.get_data_source",
		method: "GET",
		immediate: false,
	});

	async function list() {
		loading.value = true;
		error.value = null;
		try {
			const result = await listCall.submit();
			if (result == null && listCall.error) throw listCall.error;
			const data = result?.data ?? result;
			sources.value = Array.isArray(data) ? data : [];
			return sources.value;
		} catch (e) {
			error.value = e;
			throw e;
		} finally {
			loading.value = false;
		}
	}

	async function testConnection(name) {
		testing.value = name;
		error.value = null;
		try {
			const result = await testCall.submit({ name });
			if (result == null && testCall.error) throw testCall.error;
			await list(); // refresh status/last_checked for the tested row
			return result?.data ?? result;
		} catch (e) {
			error.value = e;
			throw e;
		} finally {
			testing.value = null;
		}
	}

	async function setDefault(name) {
		error.value = null;
		try {
			const result = await setDefaultCall.submit({ name });
			if (result == null && setDefaultCall.error) throw setDefaultCall.error;
			await list(); // refresh is_default across every row
			return result?.data ?? result;
		} catch (e) {
			error.value = e;
			throw e;
		}
	}

	/**
	 * Test a connection form that has not been saved. Returns the backend's
	 * `{status, message}` rather than throwing on an unreachable host: a
	 * database being down is an answer to the question the button asked, and
	 * the dialog renders it. Only a request that never got an answer throws.
	 */
	async function probe(payload) {
		probing.value = true;
		try {
			const result = await probeCall.submit({ data_source: payload });
			if (result == null && probeCall.error) throw probeCall.error;
			return result?.data ?? result;
		} finally {
			probing.value = false;
		}
	}

	async function create(payload) {
		saving.value = true;
		error.value = null;
		try {
			const result = await createCall.submit({ data_source: payload });
			if (result == null && createCall.error) throw createCall.error;
			await list();
			return result?.data ?? result;
		} catch (e) {
			error.value = e;
			throw e;
		} finally {
			saving.value = false;
		}
	}

	async function update(name, payload) {
		saving.value = true;
		error.value = null;
		try {
			const result = await updateCall.submit({ name, data_source: payload });
			if (result == null && updateCall.error) throw updateCall.error;
			await list();
			return result?.data ?? result;
		} catch (e) {
			error.value = e;
			throw e;
		} finally {
			saving.value = false;
		}
	}

	async function remove(name) {
		saving.value = true;
		error.value = null;
		try {
			const result = await deleteCall.submit({ name });
			if (result == null && deleteCall.error) throw deleteCall.error;
			await list();
			return result?.data ?? result;
		} catch (e) {
			error.value = e;
			throw e;
		} finally {
			saving.value = false;
		}
	}

	/**
	 * One source with its connection fields, for the edit form. The list rows
	 * carry only what the table shows, so opening Edit on a row would otherwise
	 * present an empty host and username - and re-pointing a port would mean
	 * retyping a connection somebody else configured. The password is never
	 * returned; an empty box leaves the stored one alone.
	 */
	async function get(name) {
		error.value = null;
		try {
			const result = await getCall.submit({ name });
			if (result == null && getCall.error) throw getCall.error;
			return result?.data ?? result;
		} catch (e) {
			error.value = e;
			throw e;
		}
	}

	return reactive({
		loading,
		testing,
		probing,
		saving,
		error,
		sources,
		list,
		get,
		testConnection,
		setDefault,
		probe,
		create,
		update,
		remove,
	});
}

/**
 * One source's tables, and a bounded preview of any one of them.
 *
 * Separate from `useDataSources()` above rather than bolted onto it: the list
 * page holds the sources, the two drill-down pages hold one source each, and
 * a single composable would give every one of them refs the others keep
 * overwriting. Mirrors the split Insights draws between `data_source.ts` and
 * `tables.ts` for the same reason.
 */
export function useSourceTables() {
	const loading = ref(false);
	const previewing = ref(false);
	const error = ref(null);
	const source = ref(null);
	const tables = ref([]);
	const preview = ref(null);

	const sourceCall = useCall({
		url: "/api/v2/method/nakhoda.api.data_sources.get_data_source",
		method: "GET",
		immediate: false,
	});

	const tablesCall = useCall({
		url: "/api/v2/method/nakhoda.api.data_sources.list_source_tables",
		method: "GET",
		immediate: false,
	});

	const previewCall = useCall({
		url: "/api/v2/method/nakhoda.api.data_sources.get_source_table",
		method: "GET",
		immediate: false,
	});

	let requestEpoch = 0;

	/** Header row for the per-source page: title, type, status. */
	async function load(dataSource) {
		error.value = null;
		try {
			const result = await sourceCall.submit({ name: dataSource });
			if (result == null && sourceCall.error) throw sourceCall.error;
			source.value = result?.data ?? result;
			return source.value;
		} catch (e) {
			error.value = e;
			throw e;
		}
	}

	/**
	 * Same shared-instance hazard `useDataStore.list` documents: one `useCall`
	 * backs every search keystroke, so an older response landing late would
	 * otherwise replace a newer one. Epoch-guarded for the same reason.
	 */
	async function list(dataSource, searchTerm) {
		const epoch = ++requestEpoch;
		if (tablesCall.isFetching) tablesCall.abort();
		loading.value = true;
		error.value = null;
		try {
			const params = { data_source: dataSource };
			if (searchTerm) params.search_term = searchTerm;
			const result = await tablesCall.submit(params);
			if (epoch !== requestEpoch) return tables.value; // superseded
			if (result == null && tablesCall.error) throw tablesCall.error;
			const data = result?.data ?? result;
			tables.value = Array.isArray(data) ? data : [];
			return tables.value;
		} catch (e) {
			if (epoch === requestEpoch) error.value = e;
			throw e;
		} finally {
			if (epoch === requestEpoch) loading.value = false;
		}
	}

	/** First `PREVIEW_ROWS` rows of one table, already permission-filtered. */
	async function fetchPreview(dataSource, table) {
		previewing.value = true;
		error.value = null;
		try {
			const result = await previewCall.submit({ data_source: dataSource, table });
			if (result == null && previewCall.error) throw previewCall.error;
			preview.value = result?.data ?? result;
			return preview.value;
		} catch (e) {
			error.value = e;
			throw e;
		} finally {
			previewing.value = false;
		}
	}

	return reactive({
		loading,
		previewing,
		error,
		source,
		tables,
		preview,
		load,
		list,
		fetchPreview,
	});
}
