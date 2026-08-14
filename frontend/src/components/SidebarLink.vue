<script setup>
import { computed } from "vue";
import { useRoute, useRouter } from "vue-router";
import { Tooltip } from "frappe-ui";

/**
 * One row in `AppSidebar`. Mirrors Insights' `SidebarLink.vue`: a pill button
 * that shows an icon + label when expanded, and just the icon (with a
 * right-placed tooltip carrying the label) when the rail is collapsed. Active
 * state is route-derived by default (`to` matches the current route name),
 * overridable via `isActive` for links whose route has child routes that
 * should also read as "on this section" (e.g. a builder route highlighting
 * its parent list item).
 */
const props = defineProps({
	icon: { type: String, default: null },
	label: { type: String, required: true },
	to: { type: String, default: null },
	isCollapsed: { type: Boolean, default: false },
	isActive: { type: Boolean, default: false },
});

const emit = defineEmits(["click"]);
const route = useRoute();
const router = useRouter();

const active = computed(() => props.isActive || (props.to !== null && route.name === props.to));

function handleClick() {
	if (props.to) router.push({ name: props.to });
	emit("click");
}
</script>

<template>
	<button
		type="button"
		class="flex h-7 w-full cursor-pointer items-center rounded duration-150 ease-out motion-reduce:duration-0 focus:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-3"
		:class="
			active
				? 'bg-surface-gray-3 font-medium text-ink-gray-9'
				: 'text-ink-gray-7 hover:bg-surface-gray-2 hover:text-ink-gray-9'
		"
		@click="handleClick"
	>
		<div
			class="flex items-center overflow-hidden duration-300 ease-in-out motion-reduce:transition-none"
			:class="isCollapsed ? 'p-1' : 'px-2 py-1'"
		>
			<Tooltip :text="label" placement="right" :disabled="!isCollapsed">
				<slot name="icon">
					<span class="grid h-5 w-6 flex-shrink-0 place-items-center">
						<span
							v-if="icon"
							:class="[icon, 'size-4', active ? 'text-ink-gray-9' : 'text-ink-gray-6']"
							aria-hidden="true"
						/>
					</span>
				</slot>
			</Tooltip>
			<span
				class="flex-1 flex-shrink-0 text-base duration-300 ease-in-out motion-reduce:transition-none"
				:class="
					isCollapsed
						? 'ml-0 w-0 overflow-hidden opacity-0'
						: 'ml-2 w-auto truncate opacity-100'
				"
			>
				{{ label }}
			</span>
		</div>
	</button>
</template>
