<script setup>
import IconSprite from "./components/IconSprite.vue";
import Turn from "./components/Turn.vue";
import { turns } from "./demo/askScreen.js";
</script>

<template>
	<IconSprite />
	<div class="shell">
		<div class="scroll">
			<div class="page">
				<Turn v-for="t in turns" :key="t.id" :turn="t">
					<template v-if="t.kind === 'generated'" #receipt-actions>
						<button class="btn btn-sm">Inspect {{ t.answer.stepCount }} steps</button>
						<button class="btn btn-sm">Mark verified</button>
					</template>
					<template v-else #receipt-actions>
						<button class="btn btn-sm">View definition</button>
					</template>
				</Turn>
			</div>
		</div>

		<div class="composer-wrap">
			<div class="composer">
				<div
					class="composer-input"
					contenteditable="true"
					data-placeholder="Ask about Finance &amp; Sales…"
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
					<button class="btn btn-primary">Ask <span class="kbd">↵</span></button>
				</div>
			</div>
		</div>
	</div>
</template>

<style scoped>
.shell {
	display: flex;
	flex-direction: column;
	height: 100vh;
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
