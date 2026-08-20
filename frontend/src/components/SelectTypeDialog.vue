<script setup>
import { Badge, Dialog } from "frappe-ui";

/**
 * "What kind of source?" - the first step of adding one, ported from
 * Insights' `src2/components/SelectTypeDialog.vue`.
 *
 * A dialog rather than a Select because each option needs a sentence: the
 * difference between a Postgres connection and an uploaded spreadsheet is not
 * something a dropdown label can carry, and picking wrong means filling in a
 * credential form for the wrong database.
 *
 * Two adaptations to this bench's frappe-ui (`1.0.0-beta.29`): the title is a
 * `Dialog` prop rather than a hand-rolled `<h3>` inside a `#body` override
 * (the deprecated spelling Insights still uses), and `icon` is a lucide CSS
 * class (`lucide-database`) rather than a component - this app renders icons
 * through frappe-ui's tailwind preset, so there is no `lucide-vue-next`
 * dependency to add for five glyphs.
 */
defineProps({
	title: { type: String, required: true },
	types: { type: Array, required: true }, // [{ icon, label, description, tag?, onClick }]
});

const show = defineModel({ type: Boolean, default: false });
</script>

<template>
	<Dialog v-model="show" :title="title">
		<div class="mt-4 grid grid-cols-1 gap-5">
			<button
				v-for="(type, index) in types"
				:key="index"
				type="button"
				class="group flex items-center gap-4 rounded text-left"
				@click="type.onClick?.()"
			>
				<div
					class="rounded border border-outline-gray-2 p-4 text-ink-gray-6 shadow-sm transition-all group-hover:scale-105 motion-reduce:transition-none"
				>
					<span :class="[type.icon, 'block size-6']" aria-hidden="true" />
				</div>
				<div class="min-w-0">
					<div class="flex items-center gap-2">
						<p
							class="text-base font-medium leading-6 text-ink-gray-9 transition-colors group-hover:text-ink-blue-3 motion-reduce:transition-none"
						>
							{{ type.label }}
						</p>
						<Badge v-if="type.tag" theme="green" variant="subtle">{{ type.tag }}</Badge>
					</div>
					<p class="text-p-sm leading-5 text-ink-gray-6">{{ type.description }}</p>
				</div>
			</button>
		</div>
	</Dialog>
</template>
