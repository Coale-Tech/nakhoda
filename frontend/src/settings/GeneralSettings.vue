<script setup>
import { Button, FormControl, LoadingIndicator } from "frappe-ui";
import SettingItem from "./SettingItem.vue";
import { useSettings } from "../composables/useSettings.js";

/**
 * "Limits" section of the old flat settings page, now the General tab
 * inside `Settings.vue`'s dialog - row caps and result cache lifetime.
 * Nothing AI-related belongs here, see `useSettings.js` for why.
 *
 * Chrome matches the AI Provider tab and Insights' own settings tabs: full
 * width, `text-xl` heading, one `SettingItem` per field. Insights' General
 * tab also carries Logo / Fiscal Year Start / Week Starts On; none has a
 * `Nakhoda Settings` field behind it (the logo is a static asset, and no
 * pipeline operation is fiscal-calendar aware yet), so inventing three dead
 * controls to fill the tab would be worse than a short one.
 */
const settings = useSettings();
</script>

<template>
	<div class="flex h-full flex-col gap-6 overflow-y-auto p-8">
		<div v-if="settings.loading.value" class="flex flex-1 items-center justify-center">
			<LoadingIndicator class="size-6" />
		</div>
		<div
			v-else-if="settings.error.value"
			class="rounded-sm border border-outline-red-2 bg-surface-red-1 p-4 text-sm text-ink-red-6"
		>
			Could not load settings.
		</div>

		<template v-else>
			<div>
				<h1 class="text-xl font-semibold text-ink-gray-9">General</h1>
				<p class="mt-1 text-sm text-ink-gray-6">
					Ceilings every question is answered under, whoever asks it.
				</p>
			</div>

			<SettingItem
				label="Max Rows Returned"
				description="Hard cap applied to every result, after permissions."
			>
				<FormControl type="number" class="w-28" v-model="settings.doc.max_rows" />
			</SettingItem>

			<SettingItem
				label="Result Cache TTL (Seconds)"
				description="How long a pipeline's result stays cached before re-executing."
			>
				<FormControl type="number" class="w-28" v-model="settings.doc.cache_ttl" />
			</SettingItem>

			<div
				v-if="settings.saveError.value"
				class="rounded-sm border border-outline-red-2 bg-surface-red-1 p-3 text-sm text-ink-red-6"
			>
				Could not save settings.
			</div>

			<div class="flex justify-end border-t border-outline-gray-2 pt-4">
				<Button
					label="Save"
					variant="solid"
					theme="gray"
					:disabled="!settings.isDirty.value"
					:loading="settings.saving.value"
					@click="settings.save()"
				/>
			</div>
		</template>
	</div>
</template>
