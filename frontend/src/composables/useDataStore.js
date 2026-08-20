import { reactive, ref } from "vue";
import { useCall } from "frappe-ui";

/**
 * The Data Store: every readable DocType joined against its `Nakhoda Table`
 * sync state (`nakhoda.api.data_store.list_tables`), plus the action that
 * queues a copy of one into the site's DuckDB warehouse (`import_table`).
 *
 * Mirrors `useSources.js`'s shape and its `result == null && call.error`
 * guard - `submit()` resolves `null` on an HTTP-level failure rather than
 * rejecting, so skipping that check turns a failed fetch into a silent
 * empty list instead of a surfaced `error`.
 *
 * `import_table` enqueues rather than copies inline (see that endpoint's own
 * docstring), so the response says only that a job was accepted. The row's
 * real state arrives later, which is why this composable owns a poll: while
 * any row reads "Syncing" it re-lists on an interval and stops the moment
 * none do. Insights' `useDataStore.ts` has no equivalent because its import
 * is synchronous - it blocks the request instead, which is the behaviour this
 * app deliberately does not have.
 */

//: How often to re-list while an import is in flight. Fast enough that a small
//: table's completion feels immediate, slow enough that a wide-table import
//: does not spend minutes hammering the list endpoint.
const POLL_INTERVAL_MS = 2000;

export function useDataStore() {
	const loading = ref(false);
	const importingDoctype = ref(null);
	const error = ref(null);
	const tables = ref([]);
	const polling = ref(false);

	const listCall = useCall({
		url: "/api/v2/method/nakhoda.api.data_store.list_tables",
		method: "GET",
		immediate: false,
	});

	const importCall = useCall({
		url: "/api/v2/method/nakhoda.api.data_store.import_table",
		method: "POST",
		immediate: false,
	});

	let lastSearchTerm;
	let requestEpoch = 0;
	let pollTimer = null;

	/**
	 * `listCall` is one shared `useCall` instance (frappe-ui vendored
	 * `useCall.ts`): concurrent `submit()`s share its `submitParams`/`error`
	 * refs, so an older in-flight call that resolves *after* a newer one
	 * (e.g. typing in the search box while the initial unfiltered load is
	 * still in flight) can overwrite a successful `tables`/`error` state with
	 * its own stale outcome. `requestEpoch` makes each `list()` call ignore
	 * its own result once a later call has superseded it.
	 */
	async function list(searchTerm) {
		const epoch = ++requestEpoch;
		lastSearchTerm = searchTerm;
		// `submitParams`/`isFetching` live on the single shared `listCall`
		// instance, so a still-in-flight prior call would otherwise have its
		// params silently overwritten by this one before its request even
		// goes out (see comment above). Cancel it first so only one request
		// is ever in flight against this instance.
		if (listCall.isFetching) listCall.abort();
		loading.value = true;
		error.value = null;
		try {
			const result = await listCall.submit(searchTerm ? { search_term: searchTerm } : {});
			if (epoch !== requestEpoch) return tables.value; // superseded by a newer call; drop this result
			if (result == null && listCall.error) throw listCall.error;
			const data = result?.data ?? result;
			tables.value = Array.isArray(data) ? data : [];
			syncPolling();
			return tables.value;
		} catch (e) {
			if (epoch === requestEpoch) error.value = e;
			throw e;
		} finally {
			if (epoch === requestEpoch) loading.value = false;
		}
	}

	/**
	 * Start or stop the poll to match what the last list actually returned.
	 * Driven by the data rather than by the import action, so a page opened
	 * while somebody else's import is running polls too - and a page whose
	 * import finished server-side stops, even if this tab never queued it.
	 */
	function syncPolling() {
		const busy = tables.value.some((t) => t.sync_state === "Syncing");
		if (busy && !pollTimer) {
			polling.value = true;
			pollTimer = setInterval(() => {
				// A poll never surfaces its own failure: a transient 500 mid-import
				// should not replace the table the user is watching with an error.
				list(lastSearchTerm).catch(() => {});
			}, POLL_INTERVAL_MS);
		} else if (!busy && pollTimer) {
			stopPolling();
		}
	}

	function stopPolling() {
		clearInterval(pollTimer);
		pollTimer = null;
		polling.value = false;
	}

	/**
	 * Queue an import. `rowLimit` is the per-table override written onto
	 * `Nakhoda Table.row_limit`; omit it to fall through to the site-wide
	 * `Nakhoda Settings.max_records_to_sync`.
	 */
	async function importTable(doctype, rowLimit) {
		importingDoctype.value = doctype;
		error.value = null;
		try {
			const params = { doctype };
			if (rowLimit) params.row_limit = rowLimit;
			const result = await importCall.submit(params);
			if (result == null && importCall.error) throw importCall.error;
			const outcome = result?.data ?? result;
			// The endpoint reports a refused queue (`queued: false`, because the
			// table is already importing) in its body rather than raising - that
			// is a fact about one table, not a reason to throw here and skip the
			// refresh that shows the in-flight state.
			await list(lastSearchTerm); // pick up "Syncing", keeping the active search filter
			return outcome;
		} catch (e) {
			error.value = e;
			throw e;
		} finally {
			importingDoctype.value = null;
		}
	}

	return reactive({
		loading,
		importingDoctype,
		error,
		tables,
		polling,
		list,
		importTable,
		stopPolling,
	});
}
