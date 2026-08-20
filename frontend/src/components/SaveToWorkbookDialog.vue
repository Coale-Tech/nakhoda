<script setup>
import { computed, ref, watch } from "vue";
import { Button, Dialog, ErrorMessage, FormControl, LoadingIndicator } from "frappe-ui";
import { useWorkbookStore } from "../stores/workbook.js";
import { useSaveAnswer } from "../composables/useSaveAnswer.js";

/**
 * "Save this answer" and "build me a workbook" are the same write with a
 * different target, which is why this is one dialog with two modes rather than
 * two actions: `save_answer` creates the workbook when none is named
 * (`api/workbooks.py:save_answer`).
 *
 * What travels is the *run id*, never the pipeline: the backend re-reads the
 * operations from `Nakhoda Agent Run`, so a save cannot store SQL whose result
 * nobody saw. The chart spec does travel, because it is presentation JSON in
 * the shape `agent/charts.py` emitted and `Chart.vue` rendered - saving what
 * is on screen beats re-deriving it.
 */
const props = defineProps({
	turn: { type: Object, required: true },
});

const open = defineModel({ type: Boolean, default: false });
const emit = defineEmits(["saved"]);

const store = useWorkbookStore();

const mode = ref("new");
const title = ref("");
const selected = ref(null);
const error = ref(null);

// The write itself lives in `useSaveAnswer` - this dialog owns only the choice
// of target, which is the one thing a workbook's own panel does not have to ask.
const { save: saveAnswer, saving, messageFor } = useSaveAnswer();

// Opening resets the form and refetches the list: a workbook created since the
// last open has to be offered, and a title left over from a previous answer
// would name this one wrongly.
//
// Which branch opens is decided *after* the list lands, not from whatever was
// in the store when the button was clicked - the first save of a session opens
// against an unloaded store, and guessing "new" there would hide every
// existing workbook behind a second click.
watch(open, async (isOpen) => {
	if (!isOpen) return;
	error.value = null;
	title.value = props.turn.question || "";
	selected.value = null;
	try {
		await store.list();
	} catch {
		// The list is an affordance, not the operation: with it unavailable a new
		// workbook is still nameable, so the dialog stays usable.
	}
	mode.value = store.workbooks.length ? "existing" : "new";
	// `immediate` because the parent mounts this already open, keyed per turn:
	// without it the first open of every answer skips the reset and the fetch.
}, { immediate: true });

const canSave = computed(() => {
	if (saving.value) return false;
	return mode.value === "new" ? Boolean(title.value.trim()) : Boolean(selected.value);
});

async function save() {
	error.value = null;
	try {
		const saved = await saveAnswer(props.turn, {
			workbook: mode.value === "existing" ? selected.value : null,
			title: mode.value === "new" ? title.value.trim() : null,
		});
		open.value = false;
		emit("saved", saved);
	} catch (e) {
		// The dialog stays open: an answer someone asked to keep must not
		// vanish because the save failed.
		error.value = messageFor(e);
	}
}
</script>

<template>
	<Dialog v-model="open" size="xl">
		<template #body-title>
			<h3 class="text-lg-semibold text-ink-gray-9">Save to workbook</h3>
		</template>
		<template #body-content>
			<div class="flex flex-col gap-4">
				<p class="text-p-sm text-ink-gray-6">
					The pipeline behind this answer is saved as a query, with its chart if it has one.
				</p>

				<div class="flex gap-2">
					<Button
						:variant="mode === 'existing' ? 'subtle' : 'ghost'"
						size="sm"
						label="Existing workbook"
						:disabled="!store.workbooks.length"
						@click="mode = 'existing'"
					/>
					<Button
						:variant="mode === 'new' ? 'subtle' : 'ghost'"
						size="sm"
						label="New workbook"
						@click="mode = 'new'"
					/>
				</div>

				<div v-if="mode === 'new'">
					<FormControl
						v-model="title"
						type="text"
						label="Title"
						placeholder="Untitled Workbook"
					/>
				</div>

				<div v-else class="flex max-h-60 flex-col overflow-y-auto rounded-sm border border-outline-gray-2">
					<div v-if="store.loading" class="flex items-center justify-center py-6">
						<LoadingIndicator class="size-4" />
					</div>
					<button
						v-for="workbook in store.workbooks"
						v-else
						:key="workbook.name"
						class="flex items-center justify-between px-3 py-2 text-left"
						:class="
							selected === workbook.name
								? 'bg-surface-gray-3 text-ink-gray-9'
								: 'text-ink-gray-7 hover:bg-surface-gray-2'
						"
						@click="selected = workbook.name"
					>
						<span class="text-p-sm truncate">{{ workbook.title }}</span>
						<span v-if="selected === workbook.name" class="lucide-check size-4" aria-hidden="true" />
					</button>
				</div>

				<ErrorMessage v-if="error" :message="error" />
			</div>
		</template>
		<template #actions>
			<div class="flex justify-end gap-2">
				<Button variant="ghost" label="Cancel" @click="open = false" />
				<Button
					variant="solid"
					theme="gray"
					label="Save"
					:disabled="!canSave"
					:loading="saving"
					@click="save"
				/>
			</div>
		</template>
	</Dialog>
</template>
