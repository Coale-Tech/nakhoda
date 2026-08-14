import { defineStore } from "pinia";
import { ref, computed } from "vue";

/**
 * Session identity and boot data. Keeps the small amount of global auth state
 * that used to be scattered across page composables: user, current workspace,
 * and a flag for whether the boot payload has been read.
 */
export const useSessionStore = defineStore("session", () => {
	const user = ref(window.boot?.user?.name || "");
	const isLoggedIn = computed(() => Boolean(user.value));
	const initialized = ref(false);

	function initialize() {
		if (initialized.value) return;
		user.value = window.boot?.user?.name || "";
		initialized.value = true;
	}

	return { user, isLoggedIn, initialized, initialize };
});
