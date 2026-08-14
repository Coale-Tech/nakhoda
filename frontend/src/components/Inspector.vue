<script setup>
import { computed, reactive, ref } from "vue";
import { Button, ScrollArea } from "frappe-ui";
import OperationRow from "./OperationRow.vue";
import SqlBlock from "./SqlBlock.vue";
import KvList from "./KvList.vue";

/**
 * The slide-out inspector (`14-frontend-design.md` §2). One instance, reused
 * across turns - the mockup's `#inspector` is likewise a single `<aside>`
 * whose section content swaps per turn rather than one inspector per answer
 * card.
 *
 * Phase 5's first gate: "every operation inspectable and editable, and a
 * user can correct one wrong step and re-run without retyping the
 * question." The composer is a sibling of this component, not a child or
 * an ancestor - `rerun` carries only the edited operations, so there is no
 * code path back through it.
 *
 * The panel sits on `surface-base` (not `elevation-1`) so the tinted section
 * boxes inside it - `surface-gray-1` hints, the green re-run confirmation -
 * still read as raised in dark mode, where `elevation-1` and `gray-1` are
 * the same step.
 */
const props = defineProps({
	open: { type: Boolean, default: false },
	title: { type: String, default: "Inspect answer" },
	pipeline: { type: Array, default: () => [] }, // [{ kind, origin, expr, editable }]
	sql: { type: Object, default: null }, // { html, plain }
	sqlNote: { type: String, default: "" },
	scope: { type: Array, default: () => [] }, // [{ label, value, color?, mono? }]
});

const emit = defineEmits(["close", "rerun"]);

const editingIndex = ref(null);
const edits = reactive({});
const lastRerun = ref(null);

const hasEdits = computed(() => Object.keys(edits).length > 0);
const canEdit = computed(() => props.pipeline.some((op) => op.editable));

function startEdit(i) {
	editingIndex.value = i;
}
function cancelEdit() {
	editingIndex.value = null;
}
function saveEdit({ index, expr }) {
	edits[index] = expr;
	editingIndex.value = null;
}
function rerun() {
	if (!hasEdits.value) return;
	lastRerun.value = { at: new Date(), count: Object.keys(edits).length };
	emit("rerun", { edits: { ...edits } });
}
</script>

<template>
	<aside
		class="inspector flex w-[452px] flex-none flex-col border-l border-outline-gray-2 bg-surface-base"
		:hidden="!open"
	>
		<div class="flex h-12 flex-none items-center gap-2 border-b border-outline-gray-1 pl-4 pr-3">
			<span class="text-sm-semibold text-ink-gray-9">{{ title }}</span>
			<Button class="ml-auto" variant="ghost" icon="lucide-x" label="Close" @click="$emit('close')" />
		</div>

		<ScrollArea class="min-h-0 flex-1">
			<div class="border-b border-outline-gray-1 px-4 py-3.5">
				<h5 class="text-tiny-semibold mb-2.5 flex items-center gap-1.5 text-ink-gray-6">
					Operation pipeline
					<!-- Only offered when some step is actually editable. `src/agent.js`
					     marks every operation `editable: false` today (no engine surface
					     accepts an edited pipeline), which would otherwise leave a
					     permanently disabled control promising a correction path that
					     cannot exist. -->
					<Button
						v-if="canEdit"
						class="ml-auto"
						variant="subtle"
						size="sm"
						label="Edit & re-run"
						:disabled="!hasEdits"
						@click="rerun"
					/>
				</h5>
				<div class="flex flex-col">
					<OperationRow
						v-for="(op, i) in pipeline"
						:key="i"
						:index="i + 1"
						:kind="op.kind"
						:origin="op.origin"
						:expr="edits[i + 1] ?? op.expr"
						:last="i === pipeline.length - 1"
						:editable="!!op.editable"
						:editing="editingIndex === i + 1"
						:edited="i + 1 in edits"
						@edit="startEdit"
						@cancel="cancelEdit"
						@save="saveEdit"
					/>
				</div>
				<div
					v-if="lastRerun"
					class="rerun-hint mt-2.5 rounded-sm border border-outline-green-1 bg-surface-green-1 px-2.5 py-2 text-xs text-ink-green-9"
				>
					Recompiled from {{ lastRerun.count }} edited step{{ lastRerun.count > 1 ? "s" : "" }} and re-run - the
					question above was never retyped.
				</div>
			</div>

			<SqlBlock v-if="sql" :html="sql.html" :plain="sql.plain">
				<template #note>
					<div
						v-if="sqlNote"
						class="mt-2.5 rounded-sm border border-outline-gray-1 bg-surface-gray-1 px-3 py-2.5 text-xs text-ink-gray-6 [&_b]:font-medium [&_b]:text-ink-gray-8"
						v-html="sqlNote"
					/>
				</template>
			</SqlBlock>

			<div v-if="scope.length" class="border-b border-outline-gray-1 px-4 py-3.5">
				<h5 class="text-tiny-semibold mb-2.5 text-ink-gray-6">Cost &amp; scope</h5>
				<KvList :rows="scope" />
			</div>

			<div class="px-4 py-3.5">
				<h5 class="text-tiny-semibold mb-2.5 text-ink-gray-6">Turn log</h5>
				<div
					class="rounded-sm border border-outline-gray-1 bg-surface-gray-1 px-3 py-2.5 text-p-xs text-ink-gray-6"
				>
					Prompt, tool calls, operations, SQL, row count, tokens and cost are persisted per turn on
					<code class="font-mono text-ink-gray-8">Nakhoda Agent Run</code>. Retained for audit - this is the
					artifact, not a scroll-back buffer.
				</div>
			</div>
		</ScrollArea>
	</aside>
</template>
