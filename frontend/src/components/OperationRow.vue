<script setup>
import { ref, watch } from "vue";
import OriginBadge from "./OriginBadge.vue";

/**
 * One step of the operation pipeline the inspector renders (`14-frontend-
 * design.md` §2, ported from `app.css` `.op`/`.op-rail`/`.op-body`). The
 * numbered rail with a connecting line is what makes this read as a
 * *pipeline* rather than a bag of steps - `.op-line` is hidden on the last
 * row by `:last-child`, driven here by the `last` prop since Vue components
 * don't get sibling CSS selectors for free across component boundaries.
 *
 * `editable` rows (source/filter/join/summarize - never the permission
 * filter, which is injected and not the user's to change) open an inline
 * textarea on "Edit" and emit `save` with the new text on confirm. This is
 * Phase 5's gate: a wrong step is corrected *here*, not by retyping the
 * question in the composer - `save`/`cancel` never touch it.
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
	<div class="op">
		<div class="op-rail">
			<span class="op-n num">{{ index }}</span>
			<span v-if="!last" class="op-line" />
		</div>
		<div class="op-body">
			<div class="op-kind">
				<span>{{ kind }}</span>
				<OriginBadge :origin="origin" />
				<span v-if="edited" class="op-edited">edited</span>
			</div>
			<div v-if="expr && !editing" class="op-expr">{{ expr }}</div>
			<div v-if="editing" class="op-edit-form">
				<textarea class="op-edit-input" v-model="draft" rows="3" />
				<div class="op-edit-actions">
					<button class="btn btn-sm" @click="$emit('cancel', index)">Cancel</button>
					<button class="btn btn-sm btn-primary" @click="$emit('save', { index, expr: draft })">Save</button>
				</div>
			</div>
		</div>
		<span v-if="editable && !editing" class="op-edit" @click="$emit('edit', index)">Edit</span>
	</div>
</template>

<style scoped>
.op {
	display: flex;
	gap: 10px;
	padding: 8px;
	margin: 0 -8px;
	border-radius: var(--border-radius-sm);
	cursor: pointer;
	position: relative;
}
.op:hover {
	background: var(--surface-gray-2);
}
.op-rail {
	flex: none;
	display: flex;
	flex-direction: column;
	align-items: center;
}
.op-n {
	width: 18px;
	height: 18px;
	border-radius: var(--border-radius-full);
	background: var(--surface-gray-3);
	color: var(--ink-gray-6);
	font-size: 10px;
	font-weight: var(--weight-semibold);
	display: grid;
	place-items: center;
}
.op:hover .op-n {
	background: var(--surface-gray-4);
}
.op-line {
	width: 1px;
	flex: 1;
	background: var(--outline-gray-2);
	margin: 3px 0 -8px;
}
.op-body {
	flex: 1;
	min-width: 0;
	padding-bottom: 3px;
}
.op-kind {
	font-size: var(--text-xs);
	font-weight: var(--weight-semibold);
	color: var(--ink-gray-9);
	display: flex;
	align-items: center;
	gap: 7px;
}
.op-edited {
	font-size: 10px;
	font-weight: var(--weight-medium);
	padding: 1px 5px;
	border-radius: var(--border-radius-tiny);
	text-transform: uppercase;
	letter-spacing: 0.03em;
	background: var(--surface-amber-1);
	color: var(--ink-amber-text);
}
.op-expr {
	font-family: var(--font-mono);
	font-size: 11px;
	color: var(--ink-gray-6);
	margin-top: 3px;
	line-height: 1.5;
	word-break: break-word;
	white-space: pre-line;
}
.op-edit {
	position: absolute;
	right: 8px;
	top: 8px;
	opacity: 0;
	font-size: var(--text-tiny);
	color: var(--ink-blue-text);
	font-weight: var(--weight-medium);
}
.op:hover .op-edit {
	opacity: 1;
}
.op-edit-form {
	margin-top: 4px;
}
.op-edit-input {
	width: 100%;
	font-family: var(--font-mono);
	font-size: 11px;
	line-height: 1.5;
	color: var(--ink-gray-8);
	background: var(--surface-white);
	border: 1px solid var(--outline-gray-3);
	border-radius: var(--border-radius-sm);
	padding: 6px 8px;
	resize: vertical;
}
.op-edit-actions {
	display: flex;
	gap: 6px;
	justify-content: flex-end;
	margin-top: 6px;
}
</style>
