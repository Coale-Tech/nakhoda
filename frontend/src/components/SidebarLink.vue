<script setup>
import { computed } from "vue";
import { useRoute } from "vue-router";
import { Tooltip } from "frappe-ui";

/**
 * One AppSidebar entry. Mirrors Insights' `SidebarLink.vue`: a pill that shows
 * an icon + label when expanded, and just the icon (with a right-placed
 * tooltip carrying the label) when the rail is collapsed.
 *
 * Renders a **link** when `to` is set and a **button** when it is not, because
 * the two entries behave differently and only one of them is navigation:
 * `Data Store` goes somewhere and so must be ctrl/middle-clickable, copyable,
 * and announced as a link; `Settings` opens a dialog and `Collapse` resizes the
 * rail, which are buttons. A single `<button>` that called `router.push` -
 * which this was - broke open-in-new-tab for every route in the app and told
 * screen readers that navigation was an action.
 *
 * `active` state is route-derived by default (`to` matches the current route
 * name) and overridable via `isActive` for links whose children should also
 * read as "on this section" (e.g. a builder route highlighting its parent list
 * item). The active entry carries `aria-current="page"`, which is what conveys
 * the highlight to anyone not seeing the background tint.
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

const active = computed(() => props.isActive || (props.to !== null && route.name === props.to));
const classes = computed(() => [
	"flex h-7 w-full cursor-pointer items-center rounded duration-150 ease-out motion-reduce:duration-0 focus:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-3",
	active.value
		? "bg-surface-gray-3 font-medium text-ink-gray-9"
		: "text-ink-gray-7 hover:bg-surface-gray-2 hover:text-ink-gray-9",
]);
</script>

<template>
	<router-link
		v-if="to"
		:to="{ name: to }"
		:class="classes"
		:aria-current="active ? 'page' : undefined"
		@click="emit('click')"
	>
		<span
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
				:class="isCollapsed ? 'ml-0 w-0 overflow-hidden opacity-0' : 'ml-2 w-auto truncate opacity-100'"
			>
				{{ label }}
			</span>
		</span>
	</router-link>
	<button v-else type="button" :class="classes" @click="emit('click')">
		<span
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
				:class="isCollapsed ? 'ml-0 w-0 overflow-hidden opacity-0' : 'ml-2 w-auto truncate opacity-100'"
			>
				{{ label }}
			</span>
		</span>
	</button>
</template>
