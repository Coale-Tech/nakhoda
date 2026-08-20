<script setup>
import DOMPurify from "dompurify";
import { marked } from "marked";
import { computed } from "vue";
import ReportChart from "./ReportChart.vue";

/**
 * A written report (`agent/thread.py:write_report`).
 *
 * Markdown, with one exception: a line that is only `chart://<agent run>`
 * becomes a chart. The report cites the run rather than embedding rows, so the
 * numbers are computed under the *reader's* permissions when they read it
 * (`api/agent.py:run_chart`) - a report forwarded to someone with narrower
 * grants shows them their own figures, not the author's.
 *
 * **Why the markdown is sanitised.** `marked` passes HTML in its input
 * straight through, and this input is a language model's output shaped by a
 * user's question - the one place in this app where untrusted text reaches
 * `v-html`. DOMPurify strips scripts and event handlers; both libraries are
 * already on disk as `frappe-ui` dependencies, so this costs no new bytes.
 */
const props = defineProps({
	markdown: { type: String, required: true },
});

/** `chart://<run>` alone on a line, optionally in backticks - a model that was
 * told to write a bare reference will sometimes format it as code anyway. */
const CHART_LINE = /^[ \t]*`?chart:\/\/([^\s`]+)`?[ \t]*$/;

/**
 * The report as an ordered list of prose and chart blocks. Splitting on whole
 * lines rather than with an inline pattern is what keeps a reference inside a
 * sentence ("see chart://x") as prose: a chart interrupting a clause would be
 * unreadable, and a bare line is the shape the menu asks for.
 */
const blocks = computed(() => {
	const out = [];
	let prose = [];
	const flush = () => {
		const text = prose.join("\n").trim();
		if (text) out.push({ kind: "prose", html: DOMPurify.sanitize(marked.parse(text)) });
		prose = [];
	};
	for (const line of String(props.markdown || "").split("\n")) {
		const match = CHART_LINE.exec(line);
		if (match) {
			flush();
			out.push({ kind: "chart", run: match[1] });
		} else {
			prose.push(line);
		}
	}
	flush();
	return out;
});
</script>

<template>
	<div class="report flex flex-col gap-3">
		<template v-for="(block, idx) in blocks" :key="idx">
			<!-- eslint-disable-next-line vue/no-v-html -->
			<div v-if="block.kind === 'prose'" class="report-prose text-p-base text-ink-gray-8" v-html="block.html" />
			<ReportChart v-else :agent-run="block.run" />
		</template>
	</div>
</template>

<style scoped>
/* Espresso has no prose stylesheet, so the handful of elements markdown can
   produce are given the same type scale and ink the rest of the app uses.
   Tailwind's typography plugin is not installed and is not worth installing
   for one component. */
.report-prose :deep(h1),
.report-prose :deep(h2),
.report-prose :deep(h3) {
	margin-top: 0.75rem;
	font-weight: 600;
	color: var(--ink-gray-9);
}
.report-prose :deep(h1) {
	font-size: 1.125rem;
}
.report-prose :deep(h2) {
	font-size: 1rem;
}
.report-prose :deep(h3) {
	font-size: 0.875rem;
}
.report-prose :deep(p),
.report-prose :deep(ul),
.report-prose :deep(ol) {
	margin-top: 0.5rem;
}
.report-prose :deep(ul) {
	list-style: disc;
	padding-left: 1.25rem;
}
.report-prose :deep(ol) {
	list-style: decimal;
	padding-left: 1.25rem;
}
.report-prose :deep(strong) {
	font-weight: 600;
	color: var(--ink-gray-9);
}
.report-prose :deep(code) {
	border-radius: 0.25rem;
	background: var(--surface-gray-2);
	padding: 0.0625rem 0.25rem;
	font-family: ui-monospace, monospace;
	font-size: 0.8125rem;
}
.report-prose :deep(table) {
	margin-top: 0.5rem;
	border-collapse: collapse;
}
.report-prose :deep(th),
.report-prose :deep(td) {
	border: 1px solid var(--outline-gray-2);
	padding: 0.25rem 0.5rem;
	text-align: left;
}
</style>
