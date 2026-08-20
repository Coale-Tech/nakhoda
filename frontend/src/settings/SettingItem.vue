<script setup>
/**
 * Copied verbatim from Insights' `src2/settings/SettingItem.vue` - layout
 * only, no logic to diverge from. Label + description on the left, a
 * slotted control on the right.
 */
defineProps({
	label: { type: String, required: true },
	description: { type: String, required: true },
});
</script>

<template>
	<div class="flex items-start justify-between gap-8">
		<div class="flex w-3/4 flex-col">
			<span class="text-p-base font-medium text-ink-gray-9">{{ label }}</span>
			<span class="text-p-sm text-ink-gray-6">{{ description }}</span>
		</div>
		<div class="flex h-full w-1/4 items-center justify-end">
			<slot />
		</div>
	</div>
</template>
