import { ref } from "vue";
import { useCall } from "frappe-ui";

/**
 * The one client-side caller of `save_answer` (`api/workbooks.py:547`).
 *
 * Two surfaces save an answer now - the Ask route through a dialog that also
 * picks or names the target, and a workbook's own panel where the target is the
 * workbook already on screen. The dialog is a different affordance; the write is
 * the same write, so the parameter rules live here once:
 *
 * - **The run id travels, never the pipeline.** The backend re-reads operations
 *   from `Nakhoda Agent Run`, so a save cannot store SQL whose result nobody
 *   saw. A client that posted operations could keep a pipeline the engine never
 *   approved for that user.
 * - **The chart spec does travel**, because it is presentation JSON in the shape
 *   `agent/charts.py` emitted and `Chart.vue` rendered. Re-deriving it
 *   server-side would let the saved chart differ from the one on screen, and
 *   would double the cost of a save.
 * - **`workbook` xor `title`.** Naming a workbook saves into it; omitting one
 *   creates it from the title. Sending both would leave the server to choose,
 *   and it chooses `workbook` - so the title would be silently dropped.
 *
 * Errors are thrown, not swallowed: each caller keeps its own surface open and
 * renders the message where the user is looking.
 */
export function useSaveAnswer() {
	const saveCall = useCall({
		url: "/api/v2/method/nakhoda.api.workbooks.save_answer",
		method: "POST",
		immediate: false,
	});
	const saving = ref(false);

	/**
	 * @param turn      a turn carrying `agentRun` (an errored turn has none)
	 * @param workbook  an existing workbook's name, or null to create one
	 * @param title     the new workbook's title, used only when `workbook` is null
	 * @returns `{workbook, query}` - enough to link straight at what was written
	 */
	async function save(turn, { workbook = null, title = null } = {}) {
		if (!turn?.agentRun) throw new Error("That answer has no audit record to save.");
		saving.value = true;
		try {
			const params = { agent_run: turn.agentRun };
			if (workbook) params.workbook = String(workbook);
			else if (title) params.title = title;
			// Absent for a table answer, and absent is not the same as empty.
			if (turn.answer?.chart) params.chart = turn.answer.chart;

			const result = await saveCall.submit(params);
			return result?.data ?? result;
		} finally {
			saving.value = false;
		}
	}

	/** `e.messages` is Frappe's own list; `e.message` is the transport's. */
	function messageFor(e) {
		return e?.messages?.[0] || e?.message || "Could not save this answer.";
	}

	return { save, saving, messageFor };
}
