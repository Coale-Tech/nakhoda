import { computed, reactive, ref } from "vue";
import { useCall } from "frappe-ui";

/**
 * `Nakhoda Intelligence Template` docs *are* dashboards once imported - the
 * doctype does double duty as both the shipped template shape and the live
 * record (`from_template` set once instantiated; see `api/templates.py`
 * module docstring). This composable is the "live dashboard" half of that:
 * listing instantiated docs and computing one doc's metric values.
 */
export function useDashboard() {
	const loading = ref(false);
	const error = ref(null);
	const dashboards = ref([]);

	const listCall = useCall({
		url: "/api/v2/method/nakhoda.api.templates.list_dashboards",
		method: "GET",
		immediate: false,
	});

	const dataCall = useCall({
		url: "/api/v2/method/nakhoda.api.templates.get_dashboard_data",
		method: "GET",
		immediate: false,
	});

	const panelCall = useCall({
		url: "/api/v2/method/nakhoda.api.dashboards.panel_data",
		method: "GET",
		immediate: false,
	});

	const applyCall = useCall({
		url: "/api/v2/method/nakhoda.api.dashboards.apply_dashboard_patch",
		method: "POST",
		immediate: false,
	});

	const revertCall = useCall({
		url: "/api/v2/method/nakhoda.api.dashboards.revert_dashboard_patch",
		method: "POST",
		immediate: false,
	});

	async function list() {
		loading.value = true;
		error.value = null;
		try {
			const result = await listCall.submit();
			const data = result.data ?? result;
			dashboards.value = Array.isArray(data) ? data : [];
			return dashboards.value;
		} catch (e) {
			error.value = e;
			throw e;
		} finally {
			loading.value = false;
		}
	}

	async function data(templateName) {
		const result = await dataCall.submit({ template_name: templateName });
		return result.data ?? result;
	}

	/**
	 * One panel's rows. Separate from `data()` on purpose: `get_dashboard_data`
	 * computes the whole metric strip in one execution, but a panel is its own
	 * query and its own cache entry, so the grid can render each as it arrives
	 * instead of waiting for the slowest.
	 */
	async function panelData(templateName, panelId) {
		const result = await panelCall.submit({ dashboard_name: templateName, panel_id: panelId });
		return result.data ?? result;
	}

	/**
	 * Apply a proposed patch. Returns `{diff, version}` - the version name is
	 * what makes the change undoable, so a caller that discards it has taken
	 * away the only handle on the change it just made. `threadTurn` links the
	 * version back to the proposal that became it.
	 */
	async function applyPatch(templateName, ops, threadTurn = null) {
		const result = await applyCall.submit({
			dashboard_name: templateName,
			ops,
			thread_turn: threadTurn,
		});
		return result.data ?? result;
	}

	/** Put the panels back to what they were immediately before `version`. */
	async function revertPatch(templateName, version) {
		await revertCall.submit({ dashboard_name: templateName, version_name: version });
	}

	const byName = computed(() => (name) => dashboards.value.find((d) => d.name === name) || null);

	return reactive({
		loading,
		error,
		dashboards,
		byName,
		list,
		data,
		panelData,
		applyPatch,
		revertPatch,
		listCall,
		dataCall,
		panelCall,
		applyCall,
		revertCall,
	});
}
