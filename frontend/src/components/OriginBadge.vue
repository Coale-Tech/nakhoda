<script setup>
import { Badge } from "frappe-ui";

/**
 * The four origin badges (`14-frontend-design.md` §2, §4): from question,
 * semantic model, Link graph, injected. Each names which layer produced one
 * operation step, so no two may render alike - `LINK GRAPH` rendering
 * identically to `SEMANTIC MODEL` was a real defect in an earlier draft, and
 * `origin-badges.spec.js` asserts every pair's computed
 * background/color/box-shadow triple is distinct.
 *
 * All four are now frappe-ui Badges, and the four appearances are the ones
 * that are simultaneously distinct *and* WCAG AA at badge text size in both
 * themes (measured against `tailwind/generated/colors.json`):
 *
 *   gray subtle    ink-gray-6 on surface-gray-2    7.04:1 / 5.11:1
 *   green subtle   ink-green-8 on surface-green-2   4.54  / 6.70
 *   gray outline   ink-gray-6 on the panel          7.81  / 5.79
 *   gray solid     ink-base on surface-gray-10     17.93  / 16.88
 *
 * `blue` and `amber` subtle badges - the obvious hues for "from question"
 * and "injected" - measure 4.18:1 and 3.55:1 in light mode and would fail
 * the gate in `contrast.spec.js`, which is why provenance here is carried by
 * fill vs outline vs inversion rather than by five hues. §1 reserves colour
 * for attention, and provenance is not attention.
 */
const ORIGINS = {
	question: { label: "from question", theme: "gray", variant: "subtle" },
	model: { label: "semantic model", theme: "green", variant: "subtle" },
	link: { label: "Link graph", theme: "gray", variant: "outline" },
	injected: { label: "injected", theme: "gray", variant: "solid" },
};

// `defineProps` is hoisted above `<script setup>` scope, so the validator
// lists the keys literally rather than reading `ORIGINS`.
const props = defineProps({
	origin: { type: String, required: true, validator: (v) => ["question", "model", "link", "injected"].includes(v) },
});
</script>

<template>
	<Badge
		class="op-origin"
		size="sm"
		:theme="ORIGINS[props.origin].theme"
		:variant="ORIGINS[props.origin].variant"
		:label="ORIGINS[props.origin].label"
	/>
</template>
