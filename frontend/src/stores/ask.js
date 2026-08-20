import { defineStore } from "pinia";
import { reactive } from "vue";

/**
 * Conversations, keyed by the surface asking.
 *
 * Ask was a route holding its turns in a local `ref` (`pages/AskPage.vue`), and
 * that was sufficient while Ask was the only place a question could be typed.
 * It is not sufficient once a workbook can ask one: saving an answer navigates
 * to the query it created (`Workbook Item`), and a conversation living in the
 * component that navigated away dies with it - taking the answer that produced
 * the query with it, one keystroke after the user asked to keep it.
 *
 * `14-frontend-design.md` §7 predicted exactly this shape ("local refs in
 * `AskPage.vue` are not enough once workbooks and dashboards hold
 * cross-component state"), so this is that store rather than a lifted ref.
 *
 * **One thread per scope, not one globally.** A workbook's thread is its own:
 * two workbooks open in two tabs are two conversations, and a question asked
 * about last quarter's revenue inside `Finance Review` has no business
 * appearing in `Ops Weekly`. The Ask route is just another scope (`"ask"`), so
 * it keeps its history while a workbook is visited and returned from.
 *
 * **Deliberately in memory only.** Turns hold result rows - real site data,
 * already filtered by the asker's permissions. `localStorage` is readable by
 * every script on the origin and survives logout, so persisting a thread would
 * park permission-filtered rows outside the permission system. The sidebar's
 * collapsed flag is a preference and is persisted (`AppSidebar.vue`); an answer
 * is not.
 */
export const useAskStore = defineStore("ask", () => {
	/**
	 * `reactive`, and mutated by assignment rather than a `Map`: Vue tracks new
	 * keys on a reactive object, and every read here is by known scope string -
	 * nothing iterates, so a Map buys only its own reactivity caveats.
	 */
	const threads = reactive({});

	/** The scope key for a workbook's thread. One place, so the two callers cannot disagree. */
	function workbookScope(name) {
		return `workbook:${name}`;
	}

	/**
	 * The scope key for a dashboard's thread. A dashboard conversation holds
	 * loop turns (`agent/thread.py`), not `ask()` answers - a different turn
	 * shape in the same store, because the reason threads are keyed at all is
	 * that leaving the page must not discard the conversation, and that is as
	 * true of a proposed patch as it is of a saved answer.
	 */
	function dashboardScope(name) {
		return `dashboard:${name}`;
	}

	/**
	 * The thread for `scope`, created empty on first ask. Returned by reference
	 * so a component can `v-model` the draft question and push turns onto the
	 * same array the next mount will read.
	 */
	function thread(scope) {
		if (!threads[scope]) threads[scope] = { turns: [], question: "" };
		return threads[scope];
	}

	/** Start over in one scope, leaving every other conversation alone. */
	function clear(scope) {
		if (threads[scope]) threads[scope] = { turns: [], question: "" };
	}

	return { threads, thread, clear, workbookScope, dashboardScope };
});
