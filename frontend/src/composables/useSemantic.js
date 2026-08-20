import { computed, reactive, ref } from "vue";
import { useCall } from "frappe-ui";

/**
 * The curated semantic layer: what a person wrote about this site's documents.
 *
 * Two halves in one row, and this composable keeps them apart. The generated
 * half - grain, column types, row and reporting counts, which columns are
 * always empty - is derived by `nakhoda.semantic.curation.sync` from
 * `frappe.get_meta` plus the nightly profile, and is read-only here: editing a
 * measurement would only make it wrong until the next migrate. The written
 * half - description, document synonyms, per-column synonyms - is the whole
 * point of the tab, and is what `save_model` persists.
 *
 * Retrieval reads both (`semantic/retrieval.py`), which is why the list ranks
 * by reporting count then rows: those are the same two priors the scorer uses,
 * so the first screen holds the documents whose description is worth writing.
 *
 * Endpoints live in `nakhoda.api.semantic`. Separate from `useSettings()`
 * because Settings is one Singles row and this is 428 documents with children -
 * the same split `useDataSources()` draws against the Data Store tab.
 */
export function useSemantic() {
	const loading = ref(false);
	const saving = ref(false);
	const regenerating = ref(false);
	const error = ref(null);
	const saveError = ref(null);
	const models = ref([]);
	const coverage = ref(null);

	const coverageCall = useCall({
		url: "/api/v2/method/nakhoda.api.semantic.coverage",
		method: "GET",
		immediate: false,
	});

	const listCall = useCall({
		url: "/api/v2/method/nakhoda.api.semantic.list_models",
		method: "GET",
		immediate: false,
	});

	const getCall = useCall({
		url: "/api/v2/method/nakhoda.api.semantic.get_model",
		method: "GET",
		immediate: false,
	});

	const saveCall = useCall({
		url: "/api/v2/method/nakhoda.api.semantic.save_model",
		method: "POST",
		immediate: false,
	});

	const regenerateCall = useCall({
		url: "/api/v2/method/nakhoda.api.semantic.regenerate",
		method: "POST",
		immediate: false,
	});

	async function load() {
		loading.value = true;
		error.value = null;
		try {
			const [cov, list] = await Promise.all([coverageCall.submit(), listCall.submit()]);
			if (cov == null && coverageCall.error) throw coverageCall.error;
			if (list == null && listCall.error) throw listCall.error;
			coverage.value = cov?.data ?? cov;
			const data = list?.data ?? list;
			models.value = Array.isArray(data) ? data : [];
			return models.value;
		} catch (e) {
			error.value = e;
			throw e;
		} finally {
			loading.value = false;
		}
	}

	/**
	 * One row with its columns. The list deliberately omits `description` and the
	 * child table (see `LIST_FIELDS`), so opening a document is a second request
	 * rather than a heavier first one.
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

	/**
	 * Write the curated half. `field_synonyms` is a `{fieldname: words}` map of
	 * only the columns the editor touched - the backend rejects a fieldname the
	 * document no longer has, so a stale form fails loudly instead of silently
	 * half-writing.
	 */
	async function save(name, { description, synonyms, fieldSynonyms }) {
		saving.value = true;
		saveError.value = null;
		try {
			const result = await saveCall.submit({
				name,
				description,
				synonyms,
				field_synonyms: fieldSynonyms ? JSON.stringify(fieldSynonyms) : null,
			});
			if (result == null && saveCall.error) throw saveCall.error;
			const fresh = result?.data ?? result;
			// Patch the list and the strip in place. `curated` and `synonyms` are both
			// visible there, and re-fetching would cost a `row_counts()` scan (~0.7s,
			// `coverage()` calls `used_doctypes()`) to learn two numbers this client
			// already knows - while losing the scroll position mid-curation.
			const row = models.value.find((m) => m.name === name);
			if (row && fresh) {
				row.curated = fresh.curated ? 1 : 0;
				row.synonyms = fresh.synonyms;
			}
			if (coverage.value) {
				coverage.value = {
					...coverage.value,
					curated: models.value.filter((m) => m.curated).length,
					with_synonyms: models.value.filter((m) => (m.synonyms || "").trim()).length,
				};
			}
			return fresh;
		} catch (e) {
			saveError.value = e;
			throw e;
		} finally {
			saving.value = false;
		}
	}

	/**
	 * Re-derive the generated half. Enqueued backend-side, so this resolves as
	 * soon as the job is queued - it does not mean the rows have changed yet.
	 * `seed` widens the pass from described documents to every document this
	 * site uses, which is how the first 428 rows arrive on a fresh install.
	 */
	async function regenerate({ seed = false } = {}) {
		regenerating.value = true;
		error.value = null;
		try {
			const result = await regenerateCall.submit({ seed: seed ? 1 : 0 });
			if (result == null && regenerateCall.error) throw regenerateCall.error;
			return result?.data ?? result;
		} catch (e) {
			error.value = e;
			throw e;
		} finally {
			regenerating.value = false;
		}
	}

	const curatedCount = computed(() => models.value.filter((m) => m.curated).length);

	return reactive({
		loading,
		saving,
		regenerating,
		error,
		saveError,
		models,
		coverage,
		curatedCount,
		load,
		get,
		save,
		regenerate,
	});
}
