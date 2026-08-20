<script setup>
import { onMounted, ref, watch } from "vue";

/**
 * A single-line `contenteditable`, ported from Insights'
 * `src2/components/ContentEditable.vue` because the workbook navbar edits its
 * title in place rather than in a field: the title *is* the heading, and a
 * bordered input in the middle of a toolbar reads as a form nobody asked to
 * fill.
 *
 * Three departures from the Insights original, each for a reason:
 *
 * - Only the `div` tag, `modelValue`, `placeholder` and `disabled` props exist
 *   here. The original also carries `tag`, `value`, `noHtml` and `noNl`
 *   switches; every call site in both apps uses the defaults, and a prop with
 *   one possible value is a decision pretending to be an option.
 * - Paste is sanitised through the Range API rather than
 *   `document.execCommand("insertText")`. `execCommand` is deprecated and its
 *   return value is unreliable; the range insert is the same two lines and is
 *   not scheduled for removal.
 * - The element is never re-rendered from `modelValue` while it has focus.
 *   Writing `innerText` moves the caret to the start, so a parent that echoes
 *   every keystroke back (which is exactly what `v-model` does) would type the
 *   text backwards.
 *
 * `blur` and `returned` both carry the current text: the navbar renames on
 * either, and Enter should not need a second event to commit.
 */
const props = defineProps({
	modelValue: { type: String, default: "" },
	placeholder: { type: String, default: "" },
	disabled: { type: Boolean, default: false },
});

const emit = defineEmits(["update:modelValue", "returned", "blur"]);

const element = ref(null);

function currentText() {
	return element.value?.innerText ?? "";
}

function write(text) {
	if (element.value) element.value.innerText = text ?? "";
}

function onInput() {
	emit("update:modelValue", currentText());
}

function onBlur() {
	emit("update:modelValue", currentText());
	emit("blur", currentText());
}

/**
 * A pasted paragraph would otherwise land as newlines inside a one-line
 * heading, which the CSS cannot hide and the server would store verbatim.
 */
function onPaste(event) {
	event.preventDefault();
	const text = (event.clipboardData?.getData("text/plain") || "").replace(/[\r\n]+/g, " ");
	const selection = window.getSelection();
	if (!selection?.rangeCount) return;
	const range = selection.getRangeAt(0);
	range.deleteContents();
	range.insertNode(document.createTextNode(text));
	selection.collapseToEnd();
	onInput();
}

function onKeydown(event) {
	if (event.key !== "Enter") return;
	event.preventDefault();
	emit("update:modelValue", currentText());
	emit("returned", currentText());
	element.value?.blur();
}

onMounted(() => write(props.modelValue));

watch(
	() => props.modelValue,
	(next) => {
		// A load or a rename elsewhere should show; the user's own typing should
		// not be rewritten under the caret.
		if (document.activeElement === element.value) return;
		if (next !== currentText()) write(next);
	},
);
</script>

<template>
	<div
		ref="element"
		class="contenteditable align-middle outline-none transition-all before:text-ink-gray-4 motion-reduce:transition-none"
		:contenteditable="!disabled"
		:placeholder="placeholder"
		spellcheck="false"
		@input="onInput"
		@blur="onBlur"
		@paste="onPaste"
		@keydown="onKeydown"
	/>
</template>

<style>
/* Not scoped: the rule targets the element's own `:empty` state through a
   pseudo-element, and a scoped attribute selector cannot reach `::before`. */
.contenteditable:empty:before {
	content: attr(placeholder);
	pointer-events: none;
	display: block;
}
</style>
