<script setup>
import Chip from "./Chip.vue";

/**
 * A failed turn. `nakhoda.agent.manager.ask()` never raises to its caller
 * (`12-build-plan.md` Phase 4, point 3) - every terminal failure is a
 * `{error, agent_run}` value; a network/permission failure the frontend
 * observes directly (`src/agent.js`) is folded into the same `{error}`
 * shape. Kept separate from `Turn.vue` because `AnswerCard` requires a
 * title/metric/receipt no failed turn has - forcing an error through it
 * would mean inventing those fields.
 */
defineProps({
	turn: { type: Object, required: true },
});
</script>

<template>
	<div class="turn">
		<div class="ask">
			<div class="avatar">RN</div>
			<div class="ask-text">{{ turn.question }}</div>
		</div>
		<div class="error-card">
			<Chip tone="warn" icon="alert">Error</Chip>
			<span class="error-text">{{ turn.error }}</span>
			<code v-if="turn.agentRun" class="error-run mono">{{ turn.agentRun }}</code>
		</div>
	</div>
</template>

<style scoped>
.turn {
	margin-bottom: 28px;
}
.ask {
	display: flex;
	gap: 10px;
	align-items: flex-start;
	margin-bottom: 16px;
}
.avatar {
	width: 24px;
	height: 24px;
	flex: none;
	border-radius: var(--border-radius-full);
	background: var(--surface-gray-3);
	color: var(--ink-gray-6);
	display: grid;
	place-items: center;
	font-size: var(--text-tiny);
	font-weight: var(--weight-semibold);
}
.ask-text {
	font-size: var(--text-lg);
	font-weight: var(--weight-medium);
	color: var(--ink-gray-9);
	line-height: 1.45;
	padding-top: 1px;
	letter-spacing: -0.011em;
}
.error-card {
	margin-left: 34px;
	display: flex;
	align-items: center;
	gap: 10px;
	flex-wrap: wrap;
	padding: 12px 14px;
	border: 1px solid var(--outline-gray-2);
	border-radius: var(--border-radius-lg);
	background: var(--surface-red-1);
}
.error-text {
	font-size: var(--text-sm);
	color: var(--ink-gray-8);
}
.error-run {
	margin-left: auto;
	font-size: var(--text-tiny);
	color: var(--text-tertiary);
}
</style>
