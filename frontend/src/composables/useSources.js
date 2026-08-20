import { reactive, ref } from "vue";
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
		url: "/api/v2/method/nakhoda.api.query.get_schema",
		// `useCall` always appends its own `?` + querystring for GET requests
		// (even with no params) - building `doctype=...` into `url` ourselves
		// produced a double `?` once frappe-ui appended its own, corrupting the
		// doctype value into a 404. `params` accepts a plain object or a plain
		// `() => TParams` function (per `UseCallOptions`) - NOT a Vue `computed()`
		// ref, which `unrefObject` cannot unwrap and instead iterates as if the
		// ref's own internal fields (`fn`, `dep`, `effect`, ...) were params.
		params: () => (schema.value?.doctype ? { doctype: schema.value.doctype } : undefined),
		method: "GET",
		immediate: false,
	});

	async function list() {
		loading.value = true;
		error.value = null;
		try {
			const result = await listCall.submit();
			// `submit()` resolves `null` on an HTTP-level failure rather than
			// rejecting (frappe-ui doesn't throw on non-2xx) - without this check
			// a failed fetch surfaces as a silent empty list instead of `error`.
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
			if (result == null && schemaCall.error) throw schemaCall.error;
			schema.value = result?.data ?? result;
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
