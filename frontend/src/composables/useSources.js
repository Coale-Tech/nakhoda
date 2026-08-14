import { computed, reactive, ref } from "vue";
import { useCall } from "frappe-ui";

/**
 * Discover DocType schemas for the query builder.
 *
 * `list()` returns readable DocTypes with their machine table names.
 * `loadSchema(doctype)` returns the permitted columns for one DocType.
 */
export function useSources() {
	const loading = ref(false);
	const error = ref(null);
	const sources = ref([]);
	const schema = ref(null);

	const listCall = useCall({
		url: "/api/v2/method/nakhoda.api.query.list_sources",
		method: "GET",
		immediate: false,
	});

	const schemaCall = useCall({
		url: computed(() => {
			if (!schema.value?.doctype) return "";
			return `/api/v2/method/nakhoda.api.query.get_schema?doctype=${encodeURIComponent(schema.value.doctype)}`;
		}),
		method: "GET",
		immediate: false,
	});

	async function list() {
		loading.value = true;
		error.value = null;
		try {
			const result = await listCall.submit();
			const data = result.data ?? result;
			sources.value = Array.isArray(data) ? data : [];
			return sources.value;
		} catch (e) {
			error.value = e;
			throw e;
		} finally {
			loading.value = false;
		}
	}

	async function loadSchema(doctype) {
		if (!doctype) {
			schema.value = null;
			return null;
		}
		loading.value = true;
		error.value = null;
		try {
			schema.value = { doctype };
			const result = await schemaCall.submit();
			schema.value = result.data ?? result;
			return schema.value;
		} catch (e) {
			schema.value = null;
			error.value = e;
			throw e;
		} finally {
			loading.value = false;
		}
	}

	function clearSchema() {
		schema.value = null;
	}

	return reactive({
		loading,
		error,
		sources,
		schema,
		list,
		loadSchema,
		clearSchema,
		listCall,
		schemaCall,
	});
}
