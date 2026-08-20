import { computed, reactive, ref } from "vue";
import { useCall } from "frappe-ui";

import { useSessionStore } from "../stores/session.js";

/**
 * `Nakhoda Settings` is a Single doctype - one row, no `name` param needed
 * beyond the doctype name itself (Frappe's REST convention for Singles).
 * Mirrors `useQuery.js` / `useSources.js`: raw `useCall` against the v2
 * document API, not frappe-ui's `useDoc` - this app has no other doctype
 * resource wired through `useDoc`, so a second convention here would be the
 * one inconsistency in the composables directory.
 *
 * The field list is data (`EDITABLE` / `READONLY`), not six hand-maintained
 * copies of the same names. It used to be the latter, which was survivable for
 * three fields and is not for the ~20 the AI Provider tab now carries: every
 * added field meant six edits, and one missed copy is a control that silently
 * never saves.
 *
 * Password fields (`*_api_key`) round-trip a `"*" * len(value)` dummy Frappe
 * writes back on save (`base_document.py:_save_passwords`), so sending an
 * untouched value back is a no-op, and clearing one to blank deletes the
 * stored key - exactly "fall through to the environment variable", with no
 * extra flag needed.
 *
 * `READONLY` fields are loaded but never sent: they are written by the backend
 * (the device-login modules, `agent/quota.py`) and a PUT carrying a stale copy
 * would clobber a value the server just changed.
 *
 * Module-level singleton (ported from Insights' `src2/settings/settings.ts`
 * `let settings = undefined` pattern) - `Settings.vue` renders General /
 * AI Provider / Data Store / Permissions as separate tabs that each call
 * `useSettings()` independently; without a shared instance, switching tabs
 * would refetch from the server and drop whatever the other tab hadn't
 * saved yet.
 */

/** Fields the form owns: loaded, tracked for `isDirty`, sent on save. */
const EDITABLE = [
	"max_rows",
	"cache_ttl",
	"strict_columns",
	// -- Data Store tab ------------------------------------------------------
	"enable_data_store",
	"max_records_to_sync",
	"max_memory_usage",
	// -- AI Provider tab, mirroring Insights' AI Analytics field set --------
	"enable_ai",
	"ai_provider",
	"openrouter_api_key",
	"ai_model",
	"ai_model_fallback",
	"openai_auth_mode",
	"openai_api_key",
	"openai_base_url",
	"openai_model",
	"nvidia_api_key",
	"nvidia_model",
	"ollama_base_url",
	"ollama_api_key",
	"ollama_model",
	"moonshot_auth_mode",
	"moonshot_api_key",
	"moonshot_model",
	"quota_reset_schedule",
	"daily_ai_quota",
];

/** Backend-owned fields the page displays but must never write back. */
const READONLY = [
	"chatgpt_oauth_account_label",
	"kimi_oauth_account_label",
	"ai_quota_used",
	"last_ai_answer",
	"quota_window_start",
];

/** Check fields, normalised to 0/1 so `isDirty` never sees `false !== 0`. */
const CHECKBOXES = new Set(["strict_columns", "enable_data_store", "enable_ai"]);

const ALL = [...EDITABLE, ...READONLY];

function normalise(fieldname, value) {
	return CHECKBOXES.has(fieldname) ? (value ? 1 : 0) : value;
}

function snapshot(source, fields) {
	return Object.fromEntries(fields.map((f) => [f, normalise(f, source[f])]));
}

let instance = null;

export function useSettings() {
	if (instance) return instance;
	instance = makeSettings();
	return instance;
}

function makeSettings() {
	const doc = reactive(Object.fromEntries(ALL.map((f) => [f, null])));
	// Last-fetched snapshot, used to compute `isDirty` and to restore on a
	// failed save - without it a failed PUT would leave the form clean. A
	// `ref`, not a plain variable: `isDirty` needs to re-run after a
	// successful save even though `doc.*` itself didn't change on that
	// occasion (it already held the value that got saved) - only `saved`
	// changed, so `saved` has to be a tracked dependency in its own right.
	const saved = ref(null);

	function load(data) {
		for (const fieldname of ALL) doc[fieldname] = normalise(fieldname, data[fieldname]);
		saved.value = snapshot(data, EDITABLE);
		// The sidebar's one conditional entry is seeded from boot, which is a
		// page-load snapshot. This is the only place in the app that learns a
		// newer value - both the GET and the PUT land here - so writing
		// through means an admin who flips Enable sees the Data Store link
		// appear or disappear on Save, without a reload. Insights gets this
		// for free because its sidebar reads the settings doc directly; that
		// is not open to a `Nakhoda User` here (see `www/_nakhoda.py`).
		useSessionStore().setDataStoreEnabled(doc.enable_data_store);
	}

	const getCall = useCall({
		url: "/api/v2/document/Nakhoda Settings/Nakhoda Settings",
		method: "GET",
		onSuccess: load,
	});

	const saveCall = useCall({
		url: "/api/v2/document/Nakhoda Settings/Nakhoda Settings",
		method: "PUT",
		immediate: false,
		params: () => snapshot(doc, EDITABLE),
		onSuccess: load,
	});

	const isDirty = computed(() => {
		// Read every field unconditionally, before the `saved` guard - a
		// computed only re-runs when a reactive dependency it *read* changes.
		// An early `if (!saved.value) return false` ahead of these reads
		// would mean the very first evaluation (synchronous, before the GET
		// resolves) tracks only `saved`, so editing a field afterwards would
		// never invalidate this computed and Save would never enable.
		const current = snapshot(doc, EDITABLE);
		if (!saved.value) return false;
		return EDITABLE.some((f) => current[f] !== saved.value[f]);
	});

	function save() {
		return saveCall.submit();
	}

	/** Re-read the document - used after a device login writes token fields. */
	function reload() {
		return getCall.reload();
	}

	return {
		doc,
		loading: computed(() => getCall.loading),
		error: computed(() => getCall.error),
		isDirty,
		saving: computed(() => saveCall.loading),
		saveError: computed(() => saveCall.error),
		save,
		reload,
	};
}
