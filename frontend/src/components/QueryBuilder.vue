<script setup>
import { computed, onMounted, ref, watch } from "vue";
import { Button, Combobox, ScrollArea, Textarea } from "frappe-ui";
import { useSources } from "../composables/useSources.js";
import OperationRow from "./OperationRow.vue";
import SqlBlock from "./SqlBlock.vue";

/**
 * Visual query builder. Displays an engine-format Operation JSON pipeline as
 * numbered cards, shows the compiled SQL, and (after running) a results preview.
 *
 * The source selector is the first typed control: it discovers readable
 * DocTypes from the backend and sets the pipeline's first `source` operation.
 * Other operations remain JSON-editable; per-step typed controls will follow.
 */
const props = defineProps({
	pipeline: { type: Array, default: () => [] }, // engine-format [{ type, ... }]
	sql: { type: Object, default: null }, // { html, plain }
	results: { type: Object, default: null }, // { columns, rows, ... }
	loading: { type: Boolean, default: false },
});

const emit = defineEmits(["update:pipeline", "run", "save"]);

const sourceApi = useSources();

const localPipeline = ref([]);
watch(
	() => props.pipeline,
	(next) => {
		localPipeline.value = Array.isArray(next) ? next.map((op) => ({ ...op })) : [];
	},
	{ immediate: true, deep: true },
);

const selectedSource = computed(() => {
	const first = localPipeline.value[0];
	if (!first || first.type !== "source") return null;
	return sourceApi.sources.find((s) => s.table === first.table) || null;
});

const sourceOptions = computed(() =>
	sourceApi.sources.map((s) => ({ label: s.label, value: s.table, description: s.is_child ? "Child table" : "" })),
);

watch(
	selectedSource,
	(next) => {
		if (next?.name) sourceApi.loadSchema(next.name);
		else sourceApi.clearSchema();
	},
	{ immediate: true },
);

onMounted(() => {
	sourceApi.list();
});

function setSource(table) {
	const next = [...localPipeline.value];
	const source = sourceApi.sources.find((s) => s.table === table);
	if (!source) return;
	if (next[0]?.type === "source") {
		next[0] = { type: "source", table: source.table };
	} else {
		next.unshift({ type: "source", table: source.table });
	}
	localPipeline.value = next;
	emit("update:pipeline", next);
}


const jsonText = ref("");
const jsonError = ref(null);
watch(
	localPipeline,
	(next) => {
		jsonText.value = JSON.stringify(next, null, 2);
		jsonError.value = null;
	},
	{ immediate: true, deep: true },
);

function applyJson() {
	try {
		const parsed = JSON.parse(jsonText.value);
		if (!Array.isArray(parsed)) throw new Error("Pipeline must be an array");
		localPipeline.value = parsed;
		jsonError.value = null;
		emit("update:pipeline", parsed);
	} catch (e) {
		jsonError.value = e.message;
	}
}

function addStep() {
	const next = [...localPipeline.value, { type: "filter", where: { col: "name", op: "eq", val: "" } }];
	localPipeline.value = next;
	emit("update:pipeline", next);
}

function removeStep(i) {
	const next = [...localPipeline.value];
	next.splice(i, 1);
	localPipeline.value = next;
	emit("update:pipeline", next);
}

function describeOp(op) {
	if (!op || typeof op !== "object") return "?";
	// `ML_OPERATIONS` (`engine/operations.py`) deliberately have no case
	// here. Phase 8's design gate (`nakhoda.tests.test_no_ml_surface`)
	// requires those four operation kinds to render exactly like a kind
	// nobody has bothered to special-case: the `default` branch below,
	// same as any future/unknown op. A bespoke description string is a
	// small UX nicety that would make this the one place a reviewer
	// could point at as the specially-treated surface.
	switch (op.type) {
		case "source":
			return op.table || "?";
		case "join":
			return `${op.how || "inner"} join ${op.table || "?"}`;
		case "filter":
			return JSON.stringify(op.where || {});
		case "select":
			return (op.columns || []).map((c) => c.name || "?").join(", ") || "?";
		case "summarize":
			return `by ${(op.by || []).map((b) => b.name || "?").join(", ") || "?"}; measures ${(op.measures || []).map((m) => m.name || "?").join(", ") || "?"}`;
		case "order_by":
			return (op.keys || []).map((k) => `${k.expr ? JSON.stringify(k.expr) : "?"}${k.desc ? " desc" : ""}`).join(", ");
		case "limit":
			return String(op.n || "?");
		default:
			return JSON.stringify(op);
	}
}
</script>

<template>
	<div class="query-builder flex h-full min-h-0">
		<div class="flex min-w-0 flex-1 flex-col">
			<div class="flex h-12 flex-none items-center justify-between border-b border-outline-gray-2 px-5">
				<h3 class="text-sm-semibold text-ink-gray-9">Operation pipeline</h3>
				<div class="flex items-center gap-2">
					<Button variant="subtle" size="sm" icon-left="lucide-plus" label="Add step" @click="addStep" />
					<Button
						variant="solid"
						theme="gray"
						size="sm"
						icon-left="lucide-play"
						label="Run"
						:loading="loading"
						@click="emit('run', localPipeline)"
					/>
				</div>
			</div>
			<ScrollArea class="min-h-0 flex-1">
				<div class="p-5">
					<div class="rounded-sm border border-outline-gray-2 bg-surface-gray-1 p-4">
						<div class="flex items-center justify-between">
							<div>
								<h4 class="text-sm-semibold text-ink-gray-9">Source</h4>
								<p v-if="selectedSource" class="mt-1 text-xs text-ink-gray-6">
									{{ selectedSource.label }}
									<span class="text-ink-gray-5">({{ selectedSource.table }})</span>
								</p>
								<p v-else class="mt-1 text-xs text-ink-gray-6">Choose a DocType to start the pipeline.</p>
							</div>
							<Combobox
								:model-value="selectedSource?.table || null"
								:options="sourceOptions"
								:loading="sourceApi.loading"
								placeholder="Select DocType"
								trigger="button"
								size="sm"
								class="source-combobox w-64"
								@update:model-value="setSource"
							/>
						</div>
						<div v-if="sourceApi.error" class="mt-2 text-xs text-ink-red-6">
							{{ sourceApi.error.message || sourceApi.error }}
						</div>
					</div>

					<div class="flex flex-col">
						<OperationRow
							v-for="(op, i) in localPipeline"
							:key="i"
							:index="i + 1"
							:kind="op.type"
							origin="model"
							:expr="describeOp(op)"
							:last="i === localPipeline.length - 1"
							:editable="false"
							:editing="false"
							:edited="false"
						/>
					</div>
					<div v-if="!localPipeline.length" class="mt-4 rounded-sm border border-outline-gray-2 bg-surface-gray-1 p-4 text-sm text-ink-gray-6">
						No operations yet. Add a step or open a generated query from Ask.
					</div>

					<div class="mt-6">
						<div class="mb-2 flex items-center justify-between">
							<h4 class="text-tiny-semibold text-ink-gray-6">Pipeline JSON</h4>
							<span v-if="jsonError" class="text-tiny-medium text-ink-red-6">{{ jsonError }}</span>
						</div>
						<Textarea
							v-model="jsonText"
							class="font-mono text-[11px]"
							variant="outline"
							:rows="10"
							@blur="applyJson"
							@keydown.ctrl.enter="applyJson"
						/>
					</div>
				</div>
			</ScrollArea>
		</div>

		<div class="flex w-[420px] flex-none flex-col border-l border-outline-gray-2 bg-surface-base">
			<div class="flex h-12 flex-none items-center border-b border-outline-gray-2 px-4">
				<h3 class="text-sm-semibold text-ink-gray-9">Preview</h3>
			</div>
			<ScrollArea class="min-h-0 flex-1">
				<div class="p-4">
					<SqlBlock v-if="sql" :html="sql.html" :plain="sql.plain" />
					<div v-else class="rounded-sm border border-outline-gray-2 bg-surface-gray-1 p-4 text-xs text-ink-gray-6">
						Run the pipeline to see the compiled SQL and results.
					</div>

					<div v-if="results" class="mt-4">
						<h4 class="text-tiny-semibold mb-2 text-ink-gray-6">
							Results ({{ results.row_count }} rows{{ results.truncated ? ", truncated" : "" }})
						</h4>
						<pre class="rounded-sm border border-outline-gray-1 bg-surface-gray-1 p-3 text-xs text-ink-gray-7">{{ JSON.stringify(results, null, 2) }}</pre>
					</div>
				</div>
			</ScrollArea>
		</div>
	</div>
</template>
