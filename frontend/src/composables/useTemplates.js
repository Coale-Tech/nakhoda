import { reactive, ref } from "vue";
import { useCall } from "frappe-ui";

/**
 * Intelligence Template shipping - the workbook-template mechanism
 * (`nakhoda/api/templates.py`, ported from Insights' filesystem-template
 * design per `docs/plan/00-REPORT.md`). `list()` returns every template this
 * site's installed apps can satisfy, each already flagged `imported_name`/
 * `update_available`/`customized` so the gallery never has to cross-reference
 * against a separate "my dashboards" list. `create()`/`update()` return the
 * live `Nakhoda Intelligence Template` doc name to route to.
 */
export function useTemplates() {
	const loading = ref(false);
	const error = ref(null);
	const templates = ref([]);

	const listCall = useCall({
		url: "/api/v2/method/nakhoda.api.templates.get_intelligence_templates",
		method: "GET",
		immediate: false,
	});

	const createCall = useCall({
		url: "/api/v2/method/nakhoda.api.templates.create_intelligence_template",
		method: "POST",
		immediate: false,
	});

	const updateCall = useCall({
		url: "/api/v2/method/nakhoda.api.templates.update_intelligence_template",
		method: "POST",
		immediate: false,
	});

	async function list() {
		loading.value = true;
		error.value = null;
		try {
			const result = await listCall.submit();
			const data = result.data ?? result;
			templates.value = Array.isArray(data) ? data : [];
			return templates.value;
		} catch (e) {
			error.value = e;
			throw e;
		} finally {
			loading.value = false;
		}
	}

	async function create(templateName) {
		const result = await createCall.submit({ template_name: templateName });
		return (result.data ?? result)?.name;
	}

	async function update(templateName) {
		const result = await updateCall.submit({ template_name: templateName });
		return (result.data ?? result)?.name;
	}

	return reactive({ loading, error, templates, list, create, update, listCall, createCall, updateCall });
}
