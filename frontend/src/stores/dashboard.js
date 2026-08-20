import { defineStore } from "pinia";
import { ref, computed } from "vue";
import { useDashboard } from "../composables/useDashboard.js";

/**
 * Dashboard list + one open dashboard's computed metric data. Every
 * dashboard is a `Nakhoda Intelligence Template` record with `from_template`
 * set - there is no separate "blank dashboard" creation path; new ones come
 * from `TemplateGallery.vue` via `nakhoda.api.templates.create_intelligence_template`.
 */
export const useDashboardStore = defineStore("dashboard", () => {
	const dashboards = ref([]);
	const loading = ref(false);
	const error = ref(null);
	const activeName = ref(null);
	const activeData = ref(null);
	const activeLoading = ref(false);
	const activeError = ref(null);

	const api = useDashboard();

	const active = computed(
		() => dashboards.value.find((d) => d.name === activeName.value) || null,
	);

	async function fetchDashboards() {
		loading.value = true;
		error.value = null;
		try {
			dashboards.value = await api.list();
		} catch (e) {
			error.value = e;
		} finally {
			loading.value = false;
		}
	}

	async function open(name) {
		activeName.value = name;
		activeData.value = null;
		activeError.value = null;
		activeLoading.value = true;
		try {
			activeData.value = await api.data(name);
		} catch (e) {
			activeError.value = e;
		} finally {
			activeLoading.value = false;
		}
	}

	/**
	 * Re-read the open dashboard *in place*: same data, no spinner, nothing
	 * unmounted. `open()` cannot be reused for this - it blanks `activeData`
	 * and raises `activeLoading`, which takes the page's whole content branch
	 * down with it. That is right on navigation and wrong after an applied
	 * patch: the Ask panel that proposed the change lives in that branch, and
	 * remounting it discards the version name that is the only handle on
	 * undoing what was just approved.
	 */
	async function refresh(name) {
		try {
			activeData.value = await api.data(name);
			activeError.value = null;
		} catch (e) {
			activeError.value = e;
		}
	}

	return {
		dashboards,
		loading,
		error,
		activeName,
		active,
		activeData,
		activeLoading,
		activeError,
		fetchDashboards,
		open,
		refresh,
	};
});
