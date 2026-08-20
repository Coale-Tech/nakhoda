import { defineStore } from "pinia";
import { ref, computed } from "vue";

/**
 * Session identity and boot data. Keeps the small amount of global auth state
 * that used to be scattered across page composables: user, admin capability,
 * and a flag for whether the boot payload has been read.
 *
 * `window.boot` is written by the Jinja block `frappe-ui`'s `jinjaBootData`
 * plugin injects into the built `index.html`, fed by `www/_nakhoda.py`'s
 * `context.boot["boot"]`. It is absent in two situations and both must degrade
 * to "not an admin" rather than throw:
 *
 * - Playwright, which serves the *built* bundle statically with no Jinja
 *   renderer, so the injected block is literal `{% %}` text that never runs.
 *   Specs that need an admin stub it with `page.addInitScript` (see
 *   `tests/fixtures/data_store.js`).
 * - Any deploy where the www controller failed. Hiding admin affordances is
 *   the safe direction: every endpoint behind them re-checks permission
 *   server-side, so a false `isAdmin` costs a hidden button, never access.
 */
export const useSessionStore = defineStore("session", () => {
	const user = ref(window.boot?.user?.name || "");
	const fullName = ref(window.boot?.user?.full_name || "");
	const isAdmin = ref(Boolean(window.boot?.is_admin));
	/**
	 * Whether a desk link would resolve for this user (`www/_nakhoda.py` reads
	 * `User.user_type`). Absent means *no*, the opposite default from
	 * `dataStoreEnabled`: an offered link that 403s is worse than a missing
	 * one, because the user cannot tell a permission wall from a broken app.
	 */
	const hasDeskAccess = ref(Boolean(window.boot?.has_desk_access));
	const isLoggedIn = computed(() => Boolean(user.value));
	const initialized = ref(false);

	/**
	 * Whether the Data Store is switched on site-wide
	 * (`Nakhoda Settings.enable_data_store`, delivered by `www/_nakhoda.py`).
	 * Drives the one conditional nav entry, the same single link Insights
	 * hides (`src2/components/AppSidebar.vue:167`).
	 *
	 * Absent means *unknown*, not *off*: only an explicit `false` from the
	 * server hides the entry. The opposite default would make a configured
	 * feature vanish with nothing on screen to explain it whenever boot
	 * itself failed, which is a worse failure than showing a page that says
	 * the store is off - the import gate is server-side either way
	 * (`api/data_store.py`), so this flag never grants anything.
	 *
	 * Admins get a live value the moment they open Settings: `useSettings`'s
	 * GET/PUT handler writes through to `setDataStoreEnabled`, so toggling
	 * the switch adds or removes the link without a reload.
	 */
	const dataStoreEnabled = ref(window.boot?.data_store_enabled !== false);

	function initialize() {
		if (initialized.value) return;
		user.value = window.boot?.user?.name || "";
		fullName.value = window.boot?.user?.full_name || "";
		isAdmin.value = Boolean(window.boot?.is_admin);
		hasDeskAccess.value = Boolean(window.boot?.has_desk_access);
		dataStoreEnabled.value = window.boot?.data_store_enabled !== false;
		initialized.value = true;
	}

	function setDataStoreEnabled(enabled) {
		dataStoreEnabled.value = Boolean(enabled);
	}

	return {
		user,
		fullName,
		isAdmin,
		hasDeskAccess,
		isLoggedIn,
		initialized,
		initialize,
		dataStoreEnabled,
		setDataStoreEnabled,
	};
});
