<script setup>
import { computed } from "vue";
import { Badge } from "frappe-ui";

/**
 * The answer card shell - "the product" per the mockup's own comment.
 * Deliberately thin: it owns only the header badge + title + body slot.
 * Assumptions, permission notice, and receipt are separate components
 * composed by the caller (`Turn.vue`) because the verified-query path
 * renders none of the first two - forcing them into this shell would mean an
 * "empty" variant fork instead of the caller simply not passing those slots.
 *
 * Header hues are restricted to the two Badge themes that clear WCAG AA in
 * both themes at badge text size: `gray` (7.04:1 light / 5.11:1 dark) and
 * `green` (4.54 / 6.7). `blue` and `amber` subtle badges measure 4.18 and
 * 3.55 in light - below the 4.5 this app gates on (`contrast.spec.js`) -
 * so "generated" is gray with a sparkle rather than a violet chip.
 */
const props = defineProps({
	tone: { type: String, required: true }, // generated | verified
	icon: { type: String, required: true }, // sparkle | verified
	label: { type: String, required: true },
	title: { type: String, required: true },
});

const iconClass = computed(
	() => ({ verified: "lucide-badge-check", sparkle: "lucide-sparkles" })[props.icon] ?? "lucide-sparkles",
);
</script>

<template>
	<div class="answer overflow-hidden rounded-lg border bg-surface-elevation-1 shadow-sm">
		<div class="flex items-center gap-2 border-b border-outline-gray-1 px-3.5 py-2.5">
			<Badge :theme="tone === 'verified' ? 'green' : 'gray'" variant="subtle" :label="label">
				<template #prefix>
					<span :class="iconClass" class="size-3" aria-hidden="true" />
				</template>
			</Badge>
			<span class="truncate text-xs text-ink-gray-6">{{ title }}</span>
			<div class="ml-auto flex items-center gap-1">
				<slot name="actions" />
			</div>
		</div>

		<div class="px-4 pt-4 pb-1"><slot /></div>

		<slot name="assumptions" />
		<slot name="notice" />
		<slot name="receipt" />
	</div>
</template>
