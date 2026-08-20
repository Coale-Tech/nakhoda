<script setup>
import { computed, nextTick, ref } from "vue";
import { useRouter } from "vue-router";
import { Breadcrumbs, Button, ScrollArea } from "frappe-ui";
import AskComposer from "../components/AskComposer.vue";
import Turn from "../components/Turn.vue";
import ErrorTurn from "../components/ErrorTurn.vue";
import Inspector from "../components/Inspector.vue";
import SaveToWorkbookDialog from "../components/SaveToWorkbookDialog.vue";
import { useAsk } from "../agent.js";
import { useAskStore } from "../stores/ask.js";

// Live conversation state - no demo data. `nakhoda.api.agent.ask` is called
// per question (`src/agent.js`); the thread only ever holds what that endpoint,
// and the `Nakhoda Agent Run` it writes, actually returned.
//
// The thread lives in `stores/ask.js` under this route's own scope rather than
// in a local ref: a workbook can now ask too, and leaving for one - or for the
// query a save just created - must not be the thing that discards the
// conversation.
const thread = useAskStore().thread("ask");
const turns = computed(() => thread.turns);
const router = useRouter();
const { ask, pending } = useAsk();

// The turn whose answer is being saved. One dialog for the whole list rather
// than one per turn: only one can be open, and mounting N dialogs to show one
// is how a conversation of forty answers gets slow.
const savingTurn = ref(null);
const savedNotice = ref(null);

/**
 * `save_answer` hands back the workbook and the query it created, which is
 * exactly enough to link straight at the saved item rather than telling the
 * user it "worked" and leaving them to find it.
 */
function onSaved(saved) {
	savedNotice.value = saved;
}

function openSaved() {
	const saved = savedNotice.value;
	if (!saved) return;
	savedNotice.value = null;
	router.push({
		name: "Workbook Item",
		params: { name: saved.workbook, itemType: "query", itemId: saved.query },
	});
}

// The scroll area owns the turns list; the composer sits below it as a real
// footer rather than a sticky overlay. ScrollArea exposes the actual scrolling
// element, which is what has to move.
const scrollArea = ref(null);

async function submit() {
	const text = thread.question.trim();
	if (!text || pending.value) return;
	thread.question = "";
	thread.turns.push(await ask(text));
	await nextTick();
	const el = scrollArea.value?.viewportElement;
	if (el) el.scrollTop = el.scrollHeight;
}

// Single reused inspector (`14-frontend-design.md` §2) - one <aside> whose
// section content swaps per turn rather than one instance per answer card.
// Keyed by turn so switching turns starts the panel's local edit state fresh.
const inspectingId = ref(null);
const inspected = computed(() => turns.value.find((t) => t.id === inspectingId.value));

function onRerun({ edits }) {
	// The inspector's "Edit & re-run" is UI-only: it recompiles nothing
	// against the real engine (`src/agent.js` marks every real operation row
	// `editable: false` for exactly this reason - editing here would silently
	// do nothing to the answer above it).
	console.info("nakhoda: pipeline re-run requested", edits);
}

function openInBuilder(turn) {
	const operations = turn.answer.operations || [];
	if (!operations.length) return;
	// Pass the generated pipeline via history state so the builder can seed
	// itself without a persisted query DocType. This is scaffold state; once
	// queries are saved, Ask will link to /queries/:name instead.
	router.push({
		name: "Query",
		params: { name: "from-ask" },
		state: { operations, sourceTurn: turn.id },
	});
}
</script>

<template>
	<header
		class="flex h-12 shrink-0 items-center justify-between border-b border-outline-gray-2 py-2.5 pl-5 pr-2"
	>
		<Breadcrumbs :items="[{ label: 'Ask', route: { name: 'Ask' } }]" />
	</header>

	<div class="flex min-h-0 flex-1">
		<div class="flex min-w-0 flex-1 flex-col">
			<ScrollArea ref="scrollArea" class="min-h-0 flex-1">
				<div class="mx-auto w-full max-w-3xl px-5 pt-7 pb-10">
					<!-- Empty state, not a blank screen: nothing has been asked yet. -->
					<div v-if="!turns.length" class="flex flex-col items-center py-20 text-center">
						<div class="flex size-10 items-center justify-center rounded-full bg-surface-gray-2">
							<span class="lucide-sparkles size-5 text-ink-gray-5" aria-hidden="true" />
						</div>
						<p class="text-lg-semibold mt-3 text-ink-gray-8">Ask a question</p>
						<p class="text-p-base mt-1 max-w-sm text-ink-gray-6">
							Every answer arrives with the operations it ran, the SQL they compiled to, and what your
							permissions removed.
						</p>
					</div>

					<template v-for="t in turns" :key="t.id">
						<ErrorTurn v-if="t.error" :turn="t" />
						<Turn v-else :turn="t">
							<template #receipt-actions>
								<template v-if="t.answer.inspector">
									<Button
										variant="ghost"
										size="sm"
										icon-left="lucide-list-tree"
										:label="`Inspect ${t.answer.stepCount} steps`"
										@click="inspectingId = t.id"
									/>
									<Button
										variant="ghost"
										size="sm"
										icon-left="lucide-pencil"
										label="Open in builder"
										@click="openInBuilder(t)"
									/>
								</template>
								<!-- Saving needs the audit row, not the inspector: an
								     answer with a chart and no operations to inspect is
								     still worth keeping, and `save_answer` re-reads the
								     pipeline from that row. -->
								<Button
									v-if="t.agentRun"
									variant="ghost"
									size="sm"
									icon-left="lucide-bookmark"
									label="Save to workbook"
									@click="savingTurn = t"
								/>
							</template>
						</Turn>
					</template>
				</div>
			</ScrollArea>

			<div class="border-t border-outline-gray-2 bg-surface-base px-5 py-4">
				<div class="mx-auto w-full max-w-3xl">
					<AskComposer v-model="thread.question" :pending="pending" @submit="submit" />
				</div>
			</div>
		</div>

		<Inspector
			v-if="inspected?.answer?.inspector"
			:key="inspected.id"
			:open="true"
			title="Inspect answer"
			:pipeline="inspected.answer.inspector.pipeline"
			:sql="inspected.answer.inspector.sql"
			:sql-note="inspected.answer.inspector.sqlNote"
			:scope="inspected.answer.inspector.scope"
			@close="inspectingId = null"
			@rerun="onRerun"
		/>

		<SaveToWorkbookDialog
			v-if="savingTurn"
			:key="savingTurn.id"
			:model-value="true"
			:turn="savingTurn"
			@update:model-value="(open) => !open && (savingTurn = null)"
			@saved="onSaved"
		/>

		<!-- The saved answer's own link, not a toast that disappears before it
		     can be clicked. -->
		<div
			v-if="savedNotice"
			class="fixed bottom-6 left-1/2 z-10 flex -translate-x-1/2 items-center gap-3 rounded-lg border border-outline-gray-2 bg-surface-white px-4 py-2.5 shadow-lg"
		>
			<span class="text-p-sm text-ink-gray-7">Saved to workbook.</span>
			<Button variant="subtle" size="sm" label="Open" @click="openSaved" />
			<Button variant="ghost" size="sm" icon="x" aria-label="Dismiss" @click="savedNotice = null" />
		</div>
	</div>
</template>
