<script setup>
import { ref, watch } from "vue";
import { Button, Textarea } from "frappe-ui";
import OriginBadge from "./OriginBadge.vue";

/**
 * One step of the operation pipeline the inspector renders (`14-frontend-
 * design.md` §2). The numbered rail with a connecting line is what makes
 * this read as a *pipeline* rather than a bag of steps - the line is hidden
 * on the last row via the `last` prop, since Vue components don't get
 * sibling CSS selectors for free across component boundaries.
 *
 * `editable` rows (source/filter/join/summarize - never the permission
 * filter, which is injected and not the user's to change) open an inline
 * textarea on "Edit" and emit `save` with the new text on confirm. This is
 * Phase 5's gate: a wrong step is corrected *here*, not by retyping the
 * question in the composer - `save`/`cancel` never touch it.
 *
 * `Edit` / `Cancel` / `Save` are frappe-ui Buttons, so the hover-revealed
 * action is a real focusable button rather than a blue-tinted span; the edit
 * field is a frappe-ui Textarea, which puts the passed class straight on the
 * `<textarea>` element (no label slot in play), keeping `.op-edit-input` a
 * fillable node for `correction.spec.js`.
 */
const props = defineProps({
	index: { type: Number, required: true },
	kind: { type: String, required: true },
	origin: { type: String, required: true },
	expr: { type: String, default: "" },
	last: { type: Boolean, default: false },
	editable: { type: Boolean, default: false },
	editing: { type: Boolean, default: false },
	edited: { type: Boolean, default: false },
});

const emit = defineEmits(["edit", "save", "cancel"]);

const draft = ref(props.expr);
watch(
	() => props.editing,
	(now) => {
		if (now) draft.value = props.expr;
	},
);
</script>

<template>
	<div class="op group relative -mx-2 flex gap-2.5 rounded-sm p-2 hover:bg-surface-gray-2">
		<div class="op-rail flex flex-none flex-col items-center">
			<span
				class="op-n grid size-[18px] place-items-center rounded-full bg-surface-gray-3 text-[10px] font-semibold tabular-nums text-ink-gray-6 group-hover:bg-surface-gray-4"
			>
				{{ index }}
			</span>
			<span v-if="!last" class="op-line -mb-2 mt-[3px] w-px flex-1 bg-outline-gray-2" />
		</div>
		<div class="op-body min-w-0 flex-1 pb-1">
			<div class="op-kind text-xs-semibold flex items-center gap-1.5 text-ink-gray-9">
				<span>{{ kind }}</span>
				<OriginBadge :origin="origin" />
				<span
					v-if="edited"
					class="op-edited rounded-sm bg-surface-amber-1 px-1.5 py-px text-[10px] font-medium uppercase tracking-[0.03em] text-ink-amber-9"
				>
					edited
				</span>
			</div>
			<div v-if="expr && !editing" class="op-expr mt-1 whitespace-pre-line break-words font-mono text-[11px] text-ink-gray-6">
				{{ expr }}
			</div>
			<div v-if="editing" class="mt-1">
				<Textarea
					v-model="draft"
					class="op-edit-input font-mono !text-[11px]"
					variant="outline"
					:rows="3"
				/>
				<div class="mt-1.5 flex justify-end gap-1.5">
					<Button variant="subtle" size="sm" label="Cancel" @click="$emit('cancel', index)" />
					<Button
						variant="solid"
						theme="gray"
						size="sm"
						label="Save"
						@click="$emit('save', { index, expr: draft })"
					/>
				</div>
			</div>
		</div>
		<Button
			v-if="editable && !editing"
			class="op-edit absolute right-2 top-2 opacity-0 group-hover:opacity-100"
			variant="ghost"
			size="sm"
			label="Edit"
			@click="$emit('edit', index)"
		/>
	</div>
</template>
