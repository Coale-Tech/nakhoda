import { ref } from "vue";
import { call } from "frappe-ui";

/**
 * RFC 8628 device-login driver - ported from Insights'
 * `src2/settings/AISettings.vue` `createDeviceLogin()` verbatim (same
 * start/poll/disconnect/status cadence), pointed at this app's auth modules.
 *
 * Two subscriptions use it, and they are the same flow with different
 * endpoints, so the cadence and error handling live here once:
 *
 * - `openai_auth_mode === "ChatGPT Subscription"` -> `agent/chatgpt_subscription_auth.py`
 * - `moonshot_auth_mode === "Kimi Subscription"`  -> `agent/kimi_subscription_auth.py`
 *
 * Response shapes match Insights' 1:1 - both backends are ports of the same
 * device flows (verified against `insights/ai/openai_codex_auth.py` and
 * `insights/ai/kimi_code_auth.py`).
 *
 * One instance per subscription, cached by name: `AISettings.vue` is the only
 * caller today, but a second caller re-polling the same device code would race
 * two independent `setTimeout` chains against one cache key.
 */
const instances = new Map();

const ENDPOINTS = {
	chatgpt: {
		label: "ChatGPT",
		start: "nakhoda.agent.chatgpt_subscription_auth.start_chatgpt_login",
		poll: "nakhoda.agent.chatgpt_subscription_auth.poll_chatgpt_login",
		disconnect: "nakhoda.agent.chatgpt_subscription_auth.disconnect_chatgpt",
		status: "nakhoda.agent.chatgpt_subscription_auth.chatgpt_auth_status",
	},
	kimi: {
		label: "Kimi",
		start: "nakhoda.agent.kimi_subscription_auth.start_kimi_login",
		poll: "nakhoda.agent.kimi_subscription_auth.poll_kimi_login",
		disconnect: "nakhoda.agent.kimi_subscription_auth.disconnect_kimi",
		status: "nakhoda.agent.kimi_subscription_auth.kimi_auth_status",
	},
};

export function useDeviceLogin(name) {
	if (!ENDPOINTS[name]) throw new Error(`unknown device login: ${name}`);
	if (!instances.has(name)) instances.set(name, makeDeviceLogin(ENDPOINTS[name]));
	return instances.get(name);
}

function makeDeviceLogin(api) {
	const status = ref({ connected: false, account_label: "", expired: false });
	const code = ref("");
	const url = ref("");
	const state = ref("idle"); // idle | waiting | error
	const error = ref("");
	let timer;

	function stop() {
		if (timer) {
			clearTimeout(timer);
			timer = undefined;
		}
	}

	async function refresh() {
		try {
			const r = await call(api.status);
			if (r) status.value = r;
		} catch {
			// Silent - the AI Provider tab still renders without a status read.
		}
	}

	async function poll(intervalMs) {
		try {
			const r = await call(api.poll);
			if (r?.status === "connected") {
				state.value = "idle";
				code.value = "";
				await refresh();
				return;
			}
			if (r?.status === "pending") {
				timer = setTimeout(() => poll(intervalMs), intervalMs);
				return;
			}
			state.value = "error";
			error.value = r?.error || "Login failed";
		} catch (e) {
			state.value = "error";
			error.value = e?.message || String(e);
		}
	}

	async function start() {
		error.value = "";
		stop();
		try {
			const r = await call(api.start);
			if (!r?.success) {
				state.value = "error";
				error.value = r?.error || "Could not start login";
				return;
			}
			code.value = r.user_code;
			url.value = r.verification_url;
			state.value = "waiting";
			window.open(r.verification_url, "_blank");
			const interval = Math.max(3, Number(r.interval) || 5) * 1000;
			timer = setTimeout(() => poll(interval), interval);
		} catch (e) {
			state.value = "error";
			error.value = e?.message || String(e);
		}
	}

	async function disconnect() {
		stop();
		try {
			await call(api.disconnect);
			state.value = "idle";
			code.value = "";
			await refresh();
		} catch (e) {
			error.value = e?.message || String(e);
		}
	}

	return { label: api.label, status, code, url, state, error, start, poll, disconnect, refresh, stop };
}
