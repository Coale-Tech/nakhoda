<script setup>
import { computed, nextTick, ref } from "vue";
import { useRouter } from "vue-router";
import { Badge, Button, ScrollArea, Textarea } from "frappe-ui";
import Turn from "../components/Turn.vue";
import ErrorTurn from "../components/ErrorTurn.vue";
import Inspector from "../components/Inspector.vue";
import { useAsk } from "../agent.js";

// Live conversation state - no demo data. `nakhoda.api.agent.ask` is called
// per question (`src/agent.js`); `turns` only ever holds what that endpoint,
// and the `Nakhoda Agent Run` it writes, actually returned.
const turns = ref([]);
const question = ref("");
const router = useRouter();
const { ask, pending } = useAsk();

// The scroll area owns the turns list; the composer sits below it as a real
// footer rather than a sticky overlay. ScrollArea exposes the actual scrolling
// element, which is what has to move.
const scrollArea = ref(null);

async function submit() {
	const text = question.value.trim();
	if (!text || pending.value) return;
	question.value = "";
	turns.value.push(await ask(text));
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
	<div class="flex h-full min-h-0">
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
							<template v-if="t.answer.inspector" #receipt-actions>
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
						</Turn>
					</template>
				</div>
			</ScrollArea>

			<div class="border-t border-outline-gray-2 bg-surface-base px-5 py-4">
				<div class="mx-auto w-full max-w-3xl">
					<Textarea
						v-model="question"
						class="composer-input"
						size="md"
						variant="outline"
						:rows="2"
						:disabled="pending"
						placeholder="Ask about Finance &amp; Sales…"
						@keydown.enter.exact.prevent="submit"
					/>
					<div class="mt-2 flex items-center gap-2">
						<Badge theme="gray" variant="subtle" label="Your permissions">
							<template #prefix>
								<span class="lucide-lock size-3" aria-hidden="true" />
							</template>
						</Badge>
						<Badge theme="gray" variant="subtle" label="Dry-run first">
							<template #prefix>
								<span class="lucide-play size-3" aria-hidden="true" />
							</template>
						</Badge>
						<Button
							class="ml-auto"
							variant="solid"
							theme="gray"
							size="md"
							:loading="pending"
							loading-text="Asking…"
							label="Ask"
							@click="submit"
						>
							<template #suffix>
								<span class="lucide-corner-down-left size-4" aria-hidden="true" />
							</template>
						</Button>
					</div>
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
	</div>
</template>
