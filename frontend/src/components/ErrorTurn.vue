<script setup>
import { Alert } from "frappe-ui";

/**
 * A failed turn. `nakhoda.agent.manager.ask()` never raises to its caller
 * (`12-build-plan.md` Phase 4, point 3) - every terminal failure is a
 * `{error, agent_run}` value; a network/permission failure the frontend
 * observes directly (`src/agent.js`) is folded into the same `{error}`
 * shape. Kept separate from `Turn.vue` because `AnswerCard` requires a
 * title/metric/receipt no failed turn has - forcing an error through it
 * would mean inventing those fields.
 *
 * `Alert` is frappe-ui's inline failure surface, so the red hue, icon and
 * geometry come from the library rather than a local red card. It is not
 * dismissible: a turn that failed stays on the transcript.
 */
defineProps({
	turn: { type: Object, required: true },
});
</script>

<template>
	<div class="mb-7">
		<p class="text-lg-medium mb-4 text-ink-gray-9">{{ turn.question }}</p>
		<Alert theme="red" :title="turn.error" :dismissible="false">
			<template v-if="turn.agentRun" #description>
				<p class="text-p-xs text-ink-gray-6">
					Agent run <code class="font-mono">{{ turn.agentRun }}</code>
				</p>
			</template>
		</Alert>
	</div>
</template>
