<script setup>
import { computed, reactive, ref } from "vue";
import OperationRow from "./OperationRow.vue";
import SqlBlock from "./SqlBlock.vue";
import KvList from "./KvList.vue";

/**
 * The slide-out inspector (`14-frontend-design.md` §2, `app.css`
 * `.inspector`/`.insp-*`). One instance, reused across turns - the mockup's
 * `#inspector` is likewise a single `<aside>` whose section content swaps
 * per turn rather than one inspector per answer card.
 *
 * Phase 5's first gate: "every operation inspectable and editable, and a
 * user can correct one wrong step and re-run without retyping the
 * question." The composer is a sibling of this component, not a child or
 * an ancestor - `rerun` carries only the edited operations, so there is no
 * code path back through it.
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
	<aside class="inspector" :hidden="!open">
		<div class="insp-head">
			<span class="insp-title">{{ title }}</span>
			<button class="btn btn-ghost btn-sm" @click="$emit('close')">Close</button>
		</div>
		<div class="insp-scroll">
			<div class="insp-section">
				<h5>
					Operation pipeline
					<button class="btn btn-sm" :disabled="!hasEdits" @click="rerun">Edit &amp; re-run</button>
				</h5>
				<div class="pipe">
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
				<div v-if="lastRerun" class="rerun-hint">
					Recompiled from {{ lastRerun.count }} edited step{{ lastRerun.count > 1 ? "s" : "" }} and re-run - the
					question above was never retyped.
				</div>
			</div>

			<SqlBlock v-if="sql" :html="sql.html" :plain="sql.plain">
				<template #note>
					<div v-if="sqlNote" class="hint" style="margin-top: 10px" v-html="sqlNote" />
				</template>
			</SqlBlock>

			<div v-if="scope.length" class="insp-section">
				<h5>Cost &amp; scope</h5>
				<KvList :rows="scope" />
			</div>

			<div class="insp-section" style="border-bottom: none">
				<h5>Turn log</h5>
				<div class="hint">
					Prompt, tool calls, operations, SQL, row count, tokens and cost are persisted per turn on
					<code class="mono">Nakhoda Query</code>. Retained for audit - this is the artifact, not a scroll-back
					buffer.
				</div>
			</div>
		</div>
	</aside>
</template>

<style scoped>
.inspector {
	width: 452px;
	flex: none;
	border-left: 1px solid var(--outline-gray-2);
	background: var(--surface-white);
	display: flex;
	flex-direction: column;
}
.inspector[hidden] {
	display: none;
}
.insp-head {
	height: 48px;
	flex: none;
	display: flex;
	align-items: center;
	gap: 8px;
	padding: 0 12px 0 16px;
	border-bottom: 1px solid var(--outline-gray-1);
}
.insp-title {
	font-size: var(--text-sm);
	font-weight: var(--weight-semibold);
	color: var(--ink-gray-9);
}
.insp-head .btn {
	margin-left: auto;
}
.insp-scroll {
	flex: 1;
	overflow-y: auto;
}
.insp-section {
	border-bottom: 1px solid var(--outline-gray-1);
	padding: 14px 16px;
}
.insp-section h5 {
	font-size: var(--text-tiny);
	font-weight: var(--weight-semibold);
	color: var(--text-secondary);
	text-transform: uppercase;
	letter-spacing: 0.05em;
	margin-bottom: 10px;
	display: flex;
	align-items: center;
	gap: 7px;
}
.insp-section h5 .btn {
	margin-left: auto;
}
.pipe {
	display: flex;
	flex-direction: column;
}
.hint {
	font-size: var(--text-xs);
	color: var(--text-secondary);
	line-height: 1.6;
	padding: 10px 12px;
	background: var(--surface-gray-1);
	border-radius: var(--border-radius-sm);
	border: 1px solid var(--outline-gray-1);
}
.hint :deep(b) {
	color: var(--ink-gray-8);
	font-weight: var(--weight-medium);
}
.rerun-hint {
	margin-top: 10px;
	font-size: var(--text-xs);
	color: var(--ink-green-text);
	background: var(--surface-green-1);
	border: 1px solid var(--outline-green-1);
	border-radius: var(--border-radius-sm);
	padding: 8px 10px;
	line-height: 1.5;
}
</style>
