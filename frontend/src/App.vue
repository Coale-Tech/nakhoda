<script setup>
import { nextTick, ref } from "vue";
import IconSprite from "./components/IconSprite.vue";
import Turn from "./components/Turn.vue";
import ErrorTurn from "./components/ErrorTurn.vue";
import Inspector from "./components/Inspector.vue";
import { askQuestion } from "./agent.js";

// Live conversation state - no demo data. `nakhoda.api.agent.ask` is called
// per question (`src/agent.js`); `turns` only ever holds what that endpoint,
// and the `Nakhoda Agent Run` it writes, actually returned.
const turns = ref([]);
const pending = ref(false);
const composerEl = ref(null);
const scrollEl = ref(null);

async function submit() {
	const question = composerEl.value?.innerText.trim();
	if (!question || pending.value) return;
	pending.value = true;
	composerEl.value.textContent = "";
	try {
		turns.value.push(await askQuestion(question));
	} finally {
		pending.value = false;
	}
	await nextTick();
	if (scrollEl.value) scrollEl.value.scrollTop = scrollEl.value.scrollHeight;
}

// Single reused inspector (`14-frontend-design.md` §2 / `app.css` `#inspector`)
// - one `<aside>`, its section content swaps per turn rather than one
// instance per answer card.
const inspectingId = ref(null);
const inspecting = ref(false);

function openInspector(id) {
	inspectingId.value = id;
	inspecting.value = true;
}
function closeInspector() {
	inspecting.value = false;
}
function onRerun({ edits }) {
	// The inspector's "Edit & re-run" is UI-only: it recompiles nothing
	// against the real engine (`src/agent.js` marks every real operation row
	// `editable: false` for exactly this reason - editing here would silently
	// do nothing to the answer above it).
	console.info("nakhoda: pipeline re-run requested", edits);
}
</script>

<template>
	<IconSprite />
	<div class="shell">
		<div class="main">
			<div class="scroll" ref="scrollEl">
				<div class="page">
					<template v-for="t in turns" :key="t.id">
						<ErrorTurn v-if="t.error" :turn="t" />
						<Turn v-else :turn="t">
							<template v-if="t.kind === 'generated'" #receipt-actions>
								<button class="btn btn-sm" @click="openInspector(t.id)">Inspect {{ t.answer.stepCount }} steps</button>
								<button class="btn btn-sm">Mark verified</button>
							</template>
							<template v-else #receipt-actions>
								<button class="btn btn-sm">View definition</button>
							</template>
						</Turn>
					</template>
				</div>
			</div>

			<div class="composer-wrap">
				<div class="composer">
					<div
						ref="composerEl"
						class="composer-input"
						:contenteditable="!pending"
						data-placeholder="Ask about Finance &amp; Sales…"
						@keydown.enter.exact.prevent="submit"
					></div>
					<div class="composer-foot">
						<span class="scope"
							><svg viewBox="0 0 16 16" fill="none" stroke="currentColor"><use href="#i-model" /></svg>41
							tables</span
						>
						<span class="scope"
							><svg viewBox="0 0 16 16" fill="none" stroke="currentColor"><use href="#i-lock" /></svg>Your
							permissions</span
						>
						<span class="scope"
							><svg viewBox="0 0 16 16" fill="none" stroke="currentColor"><use href="#i-play" /></svg>Dry-run
							first</span
						>
						<button class="btn btn-primary" :disabled="pending" @click="submit">
							{{ pending ? "Asking…" : "Ask" }} <span v-if="!pending" class="kbd">↵</span>
						</button>
					</div>
				</div>
			</div>
		</div>

		<Inspector
			v-for="t in turns.filter((t) => t.answer?.inspector)"
			v-show="inspecting && inspectingId === t.id"
			:key="'insp-' + t.id"
			:open="inspecting && inspectingId === t.id"
			title="Inspect answer"
			:pipeline="t.answer.inspector.pipeline"
			:sql="t.answer.inspector.sql"
			:sql-note="t.answer.inspector.sqlNote"
			:scope="t.answer.inspector.scope"
			@close="closeInspector"
			@rerun="onRerun"
		/>
	</div>
</template>

<style scoped>
.shell {
	display: flex;
	height: 100vh;
}
.main {
	flex: 1;
	min-width: 0;
	display: flex;
	flex-direction: column;
}
.scroll {
	flex: 1;
	overflow-y: auto;
}
.page {
	max-width: 780px;
	margin: 0 auto;
	padding: 28px 24px 120px;
}
.composer-wrap {
	position: sticky;
	bottom: 0;
	padding: 12px 24px 20px;
	background: linear-gradient(to top, var(--surface-white) 62%, transparent);
}
.composer {
	max-width: 780px;
	margin: 0 auto;
	border: 1px solid var(--outline-gray-3);
	border-radius: var(--border-radius-lg);
	background: var(--surface-cards);
	box-shadow: var(--shadow-md);
	padding: 12px 14px 10px;
}
.composer:focus-within {
	border-color: var(--outline-gray-4);
}
.composer-input {
	font-size: var(--text-base);
	color: var(--ink-gray-9);
	min-height: 24px;
	outline: none;
}
.composer-input:empty::before {
	content: attr(data-placeholder);
	color: var(--text-tertiary);
}
.composer-foot {
	display: flex;
	align-items: center;
	gap: 6px;
	margin-top: 8px;
}
.scope {
	display: inline-flex;
	align-items: center;
	gap: 5px;
	height: 22px;
	padding: 0 8px;
	border-radius: var(--border-radius-full);
	background: var(--surface-gray-1);
	color: var(--text-secondary);
	font-size: var(--text-tiny);
}
.scope svg {
	width: 11px;
	height: 11px;
	stroke-width: 2;
}
.composer-foot .btn {
	margin-left: auto;
}
</style>
