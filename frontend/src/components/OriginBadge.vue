<script setup>
/**
 * The four origin badges (`14-frontend-design.md` §2, §4): FROM QUESTION,
 * SEMANTIC MODEL, LINK GRAPH, INJECTED. Each names which layer produced one
 * operation step, so no two may render alike - `LINK GRAPH` rendering
 * identically to `SEMANTIC MODEL` (both `.o-model`) was a real defect in an
 * earlier draft. `LINK GRAPH` is separated by an inset ring (fill vs
 * outline) rather than a fifth hue, because §1 reserves colour for
 * attention and provenance is not attention - see `test_badges.spec.js`,
 * which asserts every pair's computed style triple is distinct.
 */
const ORIGINS = {
	question: { label: "from question", cls: "o-ask" },
	model: { label: "semantic model", cls: "o-model" },
	link: { label: "Link graph", cls: "o-link" },
	injected: { label: "injected", cls: "o-perm" },
};

const props = defineProps({
	origin: { type: String, required: true, validator: (v) => ["question", "model", "link", "injected"].includes(v) },
});
</script>

<template>
	<span class="op-origin" :class="ORIGINS[props.origin].cls">{{ ORIGINS[props.origin].label }}</span>
</template>

<style scoped>
.op-origin {
	font-size: 10px;
	font-weight: var(--weight-medium);
	padding: 1px 5px;
	border-radius: var(--border-radius-tiny);
	text-transform: uppercase;
	letter-spacing: 0.03em;
}
.o-model {
	background: var(--surface-gray-3);
	color: var(--text-secondary);
}
.o-ask {
	background: var(--surface-blue-2);
	color: var(--ink-blue-text);
}
.o-perm {
	background: var(--surface-green-2);
	color: var(--ink-green-text);
}
/* Fill vs outline, not a fifth hue - see the docstring above. */
.o-link {
	background: var(--surface-gray-1);
	color: var(--text-secondary);
	box-shadow: inset 0 0 0 1px var(--outline-gray-3);
}
</style>
