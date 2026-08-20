<script setup>
import { Button, ScrollArea } from "frappe-ui";
import { computed, nextTick, ref } from "vue";
import { useConverse } from "../agent.js";
import { useAskStore } from "../stores/ask.js";
import AskComposer from "./AskComposer.vue";
import PatchApproval from "./PatchApproval.vue";
import ReportView from "./ReportView.vue";

/**
 * Ask, inside one dashboard - the loop rather than a single answer.
 *
 * The same 452px panel and the same composer as a workbook's Ask
 * (`AskPanel.vue`), because the guarantees badged on that composer are the
 * product's claim about every question asked anywhere in this app. What
 * differs is the turn: `converse` spends up to a step budget and ends in
 * exactly one of a report, a patch proposal, or a sentence
 * (`agent/thread.py`), so a turn here shows *what it did* before what it
 * concluded. That is not decoration - a report whose steps are hidden is a
 * claim without a receipt, which is the thing this app refuses to ship.
 *
 * **Why the dashboard, not a space, is passed.** A dashboard is a real scope
 * here: it owns the panels a patch can name and the `skill` playbook that goes
 * into the prompt. `AskPanel.vue`'s docstring declines to hand the agent a
 * workbook for the opposite reason - a workbook is a bag of artifacts with no
 * source of its own.
 */
const props = defineProps({
	dashboard: { type: String, required: true },
});
const emit = defineEmits(["changed", "close"]);

const store = useAskStore();
const thread = computed(() => store.thread(store.dashboardScope(props.dashboard)));

const { converse, pending } = useConverse();
const scrollArea = ref(null);

async function submit() {
	const text = thread.value.question.trim();
	if (!text || pending.value) return;
	thread.value.question = "";
	thread.value.turns.push(await converse(text, { dashboard: props.dashboard }));
	await nextTick();
	const el = scrollArea.value?.viewportElement;
	if (el) el.scrollTop = el.scrollHeight;
}

/** One step, in a sentence. The step objects are the loop's own records
 * (`agent/thread.py:_observe`), so this reads them rather than restating them:
 * a query that returned nothing says so, and a refused action says why. */
function describe(step) {
	if (step.error) return `${step.action}: ${step.error}`;
	if (step.action === "ask_data") {
		const rows = step.row_count ?? 0;
		return `Asked: ${step.question} — ${rows} row${rows === 1 ? "" : "s"}`;
	}
	if (step.action === "propose_patch") return "Proposed a change to this dashboard";
	if (step.action === "write_report") return "Wrote a report";
	return "Replied";
}
</script>

<template>
	<aside
		class="dashboard-ask flex w-[452px] flex-none flex-col border-l border-outline-gray-2 bg-surface-base"
		aria-label="Ask about this dashboard"
	>
		<div class="flex h-10 shrink-0 items-center justify-between border-b border-outline-gray-2 px-4">
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
					@click="store.clear(store.dashboardScope(dashboard))"
				/>
				<Button variant="ghost" size="sm" icon="x" aria-label="Close Ask" @click="emit('close')" />
			</div>
		</div>

		<ScrollArea ref="scrollArea" class="min-h-0 flex-1">
			<div class="flex flex-col gap-4 px-4 pt-4 pb-6">
				<!-- Empty state names the two things this surface can do that the
				     Ask route cannot: read the panels, and propose changing them. -->
				<div v-if="!thread.turns.length" class="flex flex-col items-center py-14 text-center">
					<div class="flex size-9 items-center justify-center rounded-full bg-surface-gray-2">
						<span class="lucide-sparkles size-4 text-ink-gray-5" aria-hidden="true" />
					</div>
					<p class="text-p-base mt-3 font-medium text-ink-gray-8">Ask about this dashboard</p>
					<p class="text-p-sm mt-1 max-w-xs text-ink-gray-6">
						Questions are answered from the data behind these panels. A change to the dashboard is
						proposed for you to approve, never applied.
					</p>
				</div>

				<div v-for="turn in thread.turns" :key="turn.id" class="flex flex-col gap-2">
					<p class="text-p-base font-medium text-ink-gray-9">{{ turn.question }}</p>

					<ol v-if="turn.steps?.length" class="flex flex-col gap-1">
						<li
							v-for="(step, idx) in turn.steps"
							:key="idx"
							class="text-p-sm flex gap-2 text-ink-gray-6"
						>
							<span class="font-mono text-ink-gray-4">{{ idx + 1 }}</span>
							<span>{{ describe(step) }}</span>
						</li>
					</ol>

					<ReportView v-if="turn.report" :markdown="turn.report" />

					<PatchApproval
						v-if="turn.patch"
						:dashboard="dashboard"
						:patch="turn.patch"
						:thread-turn="turn.threadTurn"
						@changed="emit('changed')"
					/>

					<p
						v-if="turn.error"
						class="text-p-sm rounded-sm border border-outline-red-2 bg-surface-red-1 p-2.5 text-ink-red-6"
					>
						{{ turn.error }}
					</p>
				</div>
			</div>
		</ScrollArea>

		<div class="shrink-0 border-t border-outline-gray-2 px-4 py-3">
			<AskComposer
				v-model="thread.question"
				compact
				:pending="pending"
				placeholder="Ask about this dashboard…"
				@submit="submit"
			/>
		</div>
	</aside>
</template>
