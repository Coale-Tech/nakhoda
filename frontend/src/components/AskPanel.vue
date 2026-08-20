<script setup>
import { computed, nextTick, ref } from "vue";
import { Button, ScrollArea } from "frappe-ui";
import AskComposer from "./AskComposer.vue";
import Turn from "./Turn.vue";
import ErrorTurn from "./ErrorTurn.vue";
import { useAsk } from "../agent.js";
import { useAskStore } from "../stores/ask.js";
import { useSaveAnswer } from "../composables/useSaveAnswer.js";

/**
 * Ask, inside one workbook.
 *
 * `14-frontend-design.md` §9 makes the workbook "the container the analyst fills
 * by hand; here the interesting path starts at Ask", and §7 demoted Ask from the
 * whole app to one entry - so the workbook could already *hold* an answer but
 * not be a place to ask for one. This panel closes that: the question is asked
 * where the artifacts live, and the save has no target to choose.
 *
 * **A panel, not a floating button.** Insights puts chat in a 96×500px box
 * (`src2/components/DashboardChatButton.vue`, mounted on eight intelligence
 * dashboards). That works for a chat bubble; it does not work for this answer
 * card, whose whole argument is the provenance strip under it (§0 - assumptions,
 * rows removed, cost). At 452px this shares the Inspector's width, which is the
 * width already proven to hold that content on the Ask route.
 *
 * **Why the workbook is not passed to the agent.** `ask()` takes a `space`
 * (`api/agent.py:17`), and `Nakhoda Space` owns `default_source` and
 * `instructions`. A workbook is a collection of artifacts, not a scope with a
 * source, so handing one to the agent would create a second scoping authority
 * and a question nobody has answered - which wins when a space and a workbook
 * disagree about the source. Left open deliberately (`12-build-plan.md` §8);
 * this panel scopes the *save*, never the query.
 */
const props = defineProps({
	workbook: { type: String, required: true },
	/** A shared workbook is readable but not writable: ask, do not offer to save. */
	readOnly: { type: Boolean, default: false },
});
const emit = defineEmits(["saved", "close"]);

const store = useAskStore();
// Keyed by workbook: two workbooks are two conversations, and returning to this
// one finds the answer that produced its queries still on screen.
const thread = computed(() => store.thread(store.workbookScope(props.workbook)));

const { ask, pending } = useAsk();
const { save, saving, messageFor } = useSaveAnswer();

const scrollArea = ref(null);
const error = ref(null);
/** The turn being saved, so one in-flight save cannot grey out the whole list. */
const savingId = ref(null);

async function submit() {
	const text = thread.value.question.trim();
	if (!text || pending.value) return;
	thread.value.question = "";
	error.value = null;
	thread.value.turns.push(await ask(text));
	await nextTick();
	const el = scrollArea.value?.viewportElement;
	if (el) el.scrollTop = el.scrollHeight;
}

/**
 * Save into *this* workbook - no dialog, because the target is the page. The
 * saved query's name comes back from the server, so the caller can open it
 * rather than announce success and leave the user to find it.
 */
async function saveHere(turn) {
	error.value = null;
	savingId.value = turn.id;
	try {
		emit("saved", await save(turn, { workbook: props.workbook }));
	} catch (e) {
		// The turn stays on screen: an answer someone asked to keep must not
		// vanish because the save failed.
		error.value = messageFor(e);
	} finally {
		savingId.value = null;
	}
}
</script>

<template>
	<aside
		class="ask-panel flex w-[452px] flex-none flex-col border-l border-outline-gray-2 bg-surface-base"
		aria-label="Ask"
	>
		<div
			class="flex h-10 shrink-0 items-center justify-between border-b border-outline-gray-2 px-4"
		>
			<div class="flex items-center gap-2">
				<span class="lucide-message-circle size-4 text-ink-gray-6" aria-hidden="true" />
				<h2 class="text-p-base font-medium text-ink-gray-8">Ask</h2>
			</div>
			<div class="flex items-center gap-1">
				<Button
					v-if="thread.turns.length"
					variant="ghost"
					size="sm"
					label="Clear"
					@click="store.clear(store.workbookScope(workbook))"
				/>
				<Button
					variant="ghost"
					size="sm"
					icon="x"
					aria-label="Close Ask"
					@click="emit('close')"
				/>
			</div>
		</div>

		<ScrollArea ref="scrollArea" class="min-h-0 flex-1">
			<div class="px-4 pt-4 pb-6">
				<!-- Empty state says what a save does here, because that is the one
				     thing this surface does differently from the Ask route. -->
				<div v-if="!thread.turns.length" class="flex flex-col items-center py-14 text-center">
					<div class="flex size-9 items-center justify-center rounded-full bg-surface-gray-2">
						<span class="lucide-sparkles size-4 text-ink-gray-5" aria-hidden="true" />
					</div>
					<p class="text-p-base mt-3 font-medium text-ink-gray-8">Ask about your data</p>
					<p class="text-p-sm mt-1 max-w-xs text-ink-gray-6">
						Answers arrive with the operations they ran and what your permissions removed. Keep one
						and it becomes a query in this workbook.
					</p>
				</div>

				<template v-for="t in thread.turns" :key="t.id">
					<ErrorTurn v-if="t.error" :turn="t" />
					<Turn v-else :turn="t">
						<template #receipt-actions>
							<!-- No "Open in builder": the builder is already on the left, and
							     the way to get a pipeline into it here is to save it. -->
							<Button
								v-if="t.agentRun && !readOnly"
								variant="ghost"
								size="sm"
								icon-left="lucide-bookmark"
								label="Save to this workbook"
								:loading="saving && savingId === t.id"
								@click="saveHere(t)"
							/>
						</template>
					</Turn>
				</template>

				<p
					v-if="error"
					class="text-p-sm mt-2 rounded-sm border border-outline-red-2 bg-surface-red-1 p-2.5 text-ink-red-6"
				>
					{{ error }}
				</p>
			</div>
		</ScrollArea>

		<div class="shrink-0 border-t border-outline-gray-2 px-4 py-3">
			<AskComposer
				v-model="thread.question"
				compact
				:pending="pending"
				placeholder="Ask a question…"
				@submit="submit"
			/>
		</div>
	</aside>
</template>
