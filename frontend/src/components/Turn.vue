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
 * One question + answer. `turn` is either a live result from
 * `nakhoda.api.agent.ask` (mapped by `src/agent.js`) or, in tests/stories,
 * anything shaped the same way. Renders whichever optional sections
 * `answer` actually has: `chart` XOR `table`, `assumptions` and `notice`
 * only on the generated path - a verified answer has neither, per
 * `12-build-plan.md` Phase 3's "no ambiguity" gate. Failed turns never
 * reach this component - see `ErrorTurn.vue`.
 *
 * The question is the turn's heading: ink + type scale carry the hierarchy
 * (frappe-ui DESIGN.md, "hierarchy through ink, not boxes"), so the mockup's
 * decorative `RN` avatar - and the 34px indent that aligned the card to it -
 * are gone. Nothing in the SPA's boot context (`www/_nakhoda.py` feeds only
 * `csrf_token` and `site_name`) identifies the user, so those initials could
 * only ever have been fictional.
 */
defineProps({
	turn: { type: Object, required: true },
});
</script>

<template>
	<div class="mb-7">
		<p class="text-lg-medium mb-4 text-ink-gray-9">{{ turn.question }}</p>

		<Trace :summary="turn.trace.summary" :ticks="turn.trace.ticks" :seconds="turn.trace.seconds" />

		<AnswerCard :tone="turn.kind" :icon="turn.answer.icon" :label="turn.answer.label" :title="turn.answer.title">
			<Metric :value="turn.answer.metric.value" :delta="turn.answer.metric.delta" :caption="turn.answer.metric.caption" />

			<template v-if="turn.answer.chart">
				<Chart :series="turn.answer.chart.series" />
				<p class="text-p-xs mt-1.5 text-ink-gray-6">{{ turn.answer.chart.unit }}</p>
			</template>

			<DataTable v-if="turn.answer.table" class="mt-4" v-bind="turn.answer.table" />

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
