<script setup>
import AmbiguityPrompt from "./AmbiguityPrompt.vue";
import AnswerCard from "./AnswerCard.vue";
import AssumptionRow from "./AssumptionRow.vue";
import AssumptionsBlock from "./AssumptionsBlock.vue";
import Chart from "./Chart.vue";
import DataTable from "./DataTable.vue";
import Metric from "./Metric.vue";
import PermissionNotice from "./PermissionNotice.vue";
import Receipt from "./Receipt.vue";
import Trace from "./Trace.vue";

/**
 * One question + answer, shaped exactly like `src/demo/askScreen.js`
 * (itself shaped like `Nakhoda Agent Run` / `Nakhoda Verified Query`).
 * Renders whichever optional sections the turn's `answer` actually has:
 * `chart` XOR `table`, `assumptions` and `notice` only on the generated
 * path - a verified answer has neither, per `12-build-plan.md` Phase 3's
 * "no ambiguity" gate.
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

		<Trace :summary="turn.trace.summary" :ticks="turn.trace.ticks" :seconds="turn.trace.seconds" />

		<AnswerCard :tone="turn.kind" :icon="turn.answer.icon" :label="turn.answer.label" :title="turn.answer.title">
			<Metric :value="turn.answer.metric.value" :delta="turn.answer.metric.delta" :caption="turn.answer.metric.caption" />

			<template v-if="turn.answer.chart">
				<Chart :series="turn.answer.chart.series" />
				<div class="chart-unit">{{ turn.answer.chart.unit }}</div>
			</template>

			<DataTable v-if="turn.answer.table" style="margin-top: 16px" v-bind="turn.answer.table" />

			<template #assumptions v-if="turn.answer.assumptions">
				<AssumptionsBlock :applied="turn.answer.assumptions.applied" :needs-you="turn.answer.assumptions.needsYou">
					<AssumptionRow v-for="(row, i) in turn.answer.assumptions.rows" :key="i" :tag="row.tag" :state="row.state">
						<span v-html="row.html" />
					</AssumptionRow>
					<template #ambiguity v-if="turn.answer.assumptions.ambiguity">
						<AmbiguityPrompt
							:counterfactual="turn.answer.assumptions.ambiguity.counterfactual"
							:alt-label="turn.answer.assumptions.ambiguity.altLabel"
							:keep-label="turn.answer.assumptions.ambiguity.keepLabel"
						/>
					</template>
				</AssumptionsBlock>
			</template>

			<template #notice v-if="turn.answer.notice">
				<PermissionNotice
					:excluded-count="turn.answer.notice.excludedCount"
					:excluded-amount="turn.answer.notice.excludedAmount"
					:reason="turn.answer.notice.reason"
				/>
			</template>

			<template #receipt>
				<Receipt :segments="turn.answer.receipt.segments">
					<template #actions>
						<slot name="receipt-actions" :turn="turn" />
					</template>
				</Receipt>
			</template>
		</AnswerCard>
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
.chart-unit {
	font-size: var(--text-xs);
	color: var(--text-secondary);
	margin-top: 7px;
	line-height: 1.5;
}
</style>
