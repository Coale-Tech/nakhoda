<script setup>
/**
 * Thin wrapper over the mockup's `<use href="#i-name"/>` icon sprite
 * (defs mounted once by `IconSprite.vue` in `App.vue`). Keeps every icon
 * reference to a single glyph name instead of copy-pasted inline `<path>`
 * data per component.
 */
defineProps({
	name: { type: String, required: true },
});
</script>

<template>
	<svg viewBox="0 0 16 16" fill="none" stroke="currentColor"><use :href="`#i-${name}`" /></svg>
</template>
