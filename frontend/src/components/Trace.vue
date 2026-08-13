<script setup>
/**
 * The collapsed thinking trace above each answer (`.trace`, `app.css` lines
 * 141-153) - "the opposite of a chat bubble" per the mockup's own comment.
 * `ticks` renders one green dot per completed reasoning step when the run
 * used generation; the verified path passes `ticks: 0` and the caller
 * simply omits the `<span class="trace-steps">` markup by not rendering
 * this slot at all.
 */
defineProps({
	summary: { type: String, required: true },
	ticks: { type: Number, default: 0 },
	seconds: { type: Number, required: true },
});
defineEmits(["toggle"]);
</script>

<template>
	<div class="trace" @click="$emit('toggle')">
		<svg viewBox="0 0 16 16" fill="none" stroke="currentColor"><use href="#i-chev" /></svg>
		<span><slot>{{ summary }}</slot></span>
		<span v-if="ticks > 0" class="trace-steps">
			<i v-for="n in ticks" :key="n" class="tick" />
		</span>
		<span>· {{ seconds }}s</span>
	</div>
</template>

<style scoped>
.trace {
	display: flex;
	align-items: center;
	gap: 8px;
	margin: 0 0 14px 34px;
	font-size: var(--text-xs);
	color: var(--text-secondary);
	cursor: pointer;
	user-select: none;
}
.trace:hover {
	color: var(--ink-gray-7);
}
.trace svg {
	width: 12px;
	height: 12px;
	stroke-width: 2;
}
.trace-steps {
	display: flex;
	align-items: center;
	gap: 5px;
}
.tick {
	width: 5px;
	height: 5px;
	border-radius: var(--border-radius-full);
	background: var(--ink-green-2);
}
</style>
