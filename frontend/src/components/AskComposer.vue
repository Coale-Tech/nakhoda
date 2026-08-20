<script setup>
import { Badge, Button, Textarea } from "frappe-ui";

/**
 * The question box, shared by the Ask route and a workbook's Ask panel.
 *
 * Extracted rather than copied: the two badges are the product's claim about
 * every question asked anywhere in this app (`14-frontend-design.md` §0 - the
 * guarantees are invisible unless the UI says them), so a second composer that
 * drifted on which badges it shows would be a second claim. `compact` changes
 * the size of the same controls, never which ones are there.
 */
const props = defineProps({
	pending: { type: Boolean, default: false },
	placeholder: { type: String, default: "Ask about Finance & Sales…" },
	/** Panel width, not page width: smaller controls, badges stacked out of the way. */
	compact: { type: Boolean, default: false },
});

const question = defineModel({ type: String, default: "" });
const emit = defineEmits(["submit"]);

/** Enter and the button are the same action, and neither fires mid-flight: a
 *  second question sent while the first is running would render out of order. */
function submit() {
	if (props.pending || !question.value.trim()) return;
	emit("submit");
}
</script>

<template>
	<div>
		<Textarea
			v-model="question"
			class="composer-input"
			:size="compact ? 'sm' : 'md'"
			variant="outline"
			:rows="2"
			:disabled="pending"
			:placeholder="placeholder"
			@keydown.enter.exact.prevent="submit"
		/>
		<div class="mt-2 flex items-center gap-2">
			<template v-if="!compact">
				<Badge theme="gray" variant="subtle" label="Your permissions">
					<template #prefix>
						<span class="lucide-lock size-3" aria-hidden="true" />
					</template>
				</Badge>
				<Badge theme="gray" variant="subtle" label="Dry-run first">
					<template #prefix>
						<span class="lucide-play size-3" aria-hidden="true" />
					</template>
				</Badge>
			</template>
			<!-- Compact keeps the claim, drops the second label: the panel is 452px
			     and two badges plus a button wrap onto a second row, which reads as
			     a layout accident rather than a statement. -->
			<Badge v-else theme="gray" variant="subtle" label="Your permissions · dry-run">
				<template #prefix>
					<span class="lucide-lock size-3" aria-hidden="true" />
				</template>
			</Badge>
			<Button
				class="ml-auto"
				variant="solid"
				theme="gray"
				:size="compact ? 'sm' : 'md'"
				:loading="pending"
				loading-text="Asking…"
				label="Ask"
				@click="submit"
			>
				<template #suffix>
					<span v-if="!compact" class="lucide-corner-down-left size-4" aria-hidden="true" />
				</template>
			</Button>
		</div>
	</div>
</template>
