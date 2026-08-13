<script setup>
import { ref } from "vue";

/**
 * `.sql` dry-run block (`app.css` lines 414-429). `html` carries the
 * pre-tokenised markup (`.k` keyword / `.s` string / `.n` name / `.c`
 * comment / `.inj` injected-filter highlight) exactly as the mockup's inline
 * `<span>` markup does - the compiler emits these spans when it renders a
 * realised query, so this component stays a dumb `v-html` sink rather than
 * a second SQL tokenizer. `plain` is the copy-to-clipboard text: SQL, not
 * HTML, is what a user pastes into a terminal.
 */
const props = defineProps({
	html: { type: String, required: true },
	plain: { type: String, required: true },
});

const copied = ref(false);
let resetTimer = null;

async function copy() {
	await navigator.clipboard.writeText(props.plain);
	copied.value = true;
	clearTimeout(resetTimer);
	resetTimer = setTimeout(() => (copied.value = false), 1500);
}
</script>

<template>
	<div class="insp-section">
		<h5>
			Realised SQL — dry run
			<button class="btn btn-sm" @click="copy">{{ copied ? "Copied" : "Copy" }}</button>
		</h5>
		<div class="sql" v-html="html"></div>
		<slot name="note" />
	</div>
</template>

<style scoped>
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
.sql {
	background: var(--surface-gray-1);
	border: 1px solid var(--outline-gray-1);
	border-radius: var(--border-radius-sm);
	padding: 10px 11px;
	font-family: var(--font-mono);
	font-size: 11px;
	line-height: 1.75;
	color: var(--ink-gray-7);
	overflow-x: auto;
	white-space: pre;
}
.sql :deep(.k) {
	color: var(--ink-gray-9);
	font-weight: var(--weight-semibold);
}
.sql :deep(.s) {
	color: var(--ink-green-text);
}
.sql :deep(.n) {
	color: var(--ink-blue-text);
}
.sql :deep(.c) {
	color: var(--text-tertiary);
	font-style: italic;
}
.sql :deep(.inj) {
	background: var(--surface-green-2);
	color: var(--ink-green-text);
	border-radius: 3px;
	padding: 1px 3px;
	margin: 0 -3px;
	font-weight: var(--weight-medium);
}
</style>
