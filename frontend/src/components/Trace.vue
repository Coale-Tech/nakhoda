<script setup>
/**
 * The collapsed thinking trace above each answer - "the opposite of a chat
 * bubble" per the mockup's own comment. `ticks` renders one green dot per
 * completed reasoning step when the run used generation; the verified path
 * passes `ticks: 0` and the dots are omitted entirely.
 */
defineProps({
	summary: { type: String, required: true },
	ticks: { type: Number, default: 0 },
	seconds: { type: Number, required: true },
});
defineEmits(["toggle"]);
</script>

<template>
	<button
		type="button"
		class="trace mb-3.5 flex select-none items-center gap-2 text-xs text-ink-gray-6 hover:text-ink-gray-7"
		@click="$emit('toggle')"
	>
		<span class="lucide-chevron-right size-3" aria-hidden="true" />
		<span>
			<slot>{{ summary }}</slot>
		</span>
		<span v-if="ticks > 0" class="flex items-center gap-1.5">
			<i v-for="n in ticks" :key="n" class="size-[5px] rounded-full bg-surface-green-6" />
		</span>
		<span>· {{ seconds }}s</span>
	</button>
</template>
