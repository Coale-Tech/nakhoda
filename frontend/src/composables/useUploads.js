import { reactive, ref } from "vue";
import { useCall } from "frappe-ui";

/**
 * A file on its way to becoming a warehouse table.
 *
 * Two steps, deliberately separate - the same shape Insights' New Source ›
 * "Upload CSV or Excel" flow has (`src2/data_source/UploadCSVFileDialog.vue`):
 *
 * 1. `preview(file)` parses the uploaded file in a throwaway in-memory DuckDB
 *    and returns its columns and first rows. Nothing is written, so a person
 *    can look at a badly delimited file and walk away without leaving a
 *    half-imported table behind.
 * 2. `importFile(file)` copies it into the site warehouse under the
 *    `upload_` prefix and registers a `Nakhoda Table` row, which is what makes
 *    it queryable and visible on the Data Store page.
 *
 * `file` is a `File` **document name** throughout - what frappe-ui's
 * `FileUploader` hands back on success - not a path or a browser `File`
 * object: the bytes are already on the server by the time this composable is
 * involved, and the docname is the only handle that survives the round trip.
 */
export function useUploads() {
	const loading = ref(false);
	const importing = ref(false);
	const error = ref(null);
	const preview = ref(null);

	const previewCall = useCall({
		url: "/api/v2/method/nakhoda.api.files.get_upload_preview",
		method: "GET",
		immediate: false,
	});

	const importCall = useCall({
		url: "/api/v2/method/nakhoda.api.files.import_upload",
		method: "POST",
		immediate: false,
	});

	async function load(file) {
		loading.value = true;
		error.value = null;
		try {
			const result = await previewCall.submit({ file });
			if (result == null && previewCall.error) throw previewCall.error;
			preview.value = result?.data ?? result;
			return preview.value;
		} catch (e) {
			error.value = e;
			throw e;
		} finally {
			loading.value = false;
		}
	}

	async function importFile(file, rowLimit) {
		importing.value = true;
		error.value = null;
		try {
			const params = { file };
			if (rowLimit) params.row_limit = rowLimit;
			const result = await importCall.submit(params);
			if (result == null && importCall.error) throw importCall.error;
			return result?.data ?? result;
		} catch (e) {
			error.value = e;
			throw e;
		} finally {
			importing.value = false;
		}
	}

	function reset() {
		preview.value = null;
		error.value = null;
	}

	return reactive({
		loading,
		importing,
		error,
		preview,
		load,
		importFile,
		reset,
	});
}
