<script setup>
import { ref } from "vue";
import { Button } from "frappe-ui";

/**
 * The dry-run SQL block. `html` carries pre-tokenised markup (`.k` keyword /
 * `.s` string / `.n` name / `.c` comment / `.inj` injected-filter highlight)
 * exactly as the compiler emits it when it renders a realised query, so this
 * component stays a dumb `v-html` sink rather than a second SQL tokenizer.
 * `plain` is the copy-to-clipboard text: SQL, not HTML, is what a user
 * pastes into a terminal.
 *
 * The token colours are arbitrary child selectors over semantic ink steps
 * (`ink-green-9`, `ink-blue-9`) rather than a stylesheet, and they are the
 * deep steps on purpose: `green-text`/`blue-link`-style shallow steps
 * measure 3.4:1 on the panel and would fail the AA gate at 11px.
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
	<div class="border-b border-outline-gray-1 px-4 py-3.5">
		<h5 class="text-tiny-semibold mb-2.5 flex items-center gap-1.5 text-ink-gray-6">
			Realised SQL — dry run
			<Button class="ml-auto" variant="subtle" size="sm" :label="copied ? 'Copied' : 'Copy'" @click="copy" />
		</h5>
		<div
			class="sql overflow-x-auto whitespace-pre rounded-sm border border-outline-gray-1 bg-surface-gray-1 px-3 py-2.5 font-mono text-[11px] leading-[1.75] text-ink-gray-7 [&_.c]:italic [&_.c]:text-ink-gray-6 [&_.inj]:-mx-0.5 [&_.inj]:rounded-sm [&_.inj]:bg-surface-green-2 [&_.inj]:px-0.5 [&_.inj]:font-medium [&_.inj]:text-ink-green-9 [&_.k]:font-semibold [&_.k]:text-ink-gray-9 [&_.n]:text-ink-blue-9 [&_.s]:text-ink-green-9"
			v-html="html"
		></div>
		<slot name="note" />
	</div>
</template>
