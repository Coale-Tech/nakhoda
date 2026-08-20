<script setup>
import { Button, LoadingIndicator } from "frappe-ui";
import SettingItem from "./SettingItem.vue";
import Toggle from "../components/Toggle.vue";
import { useSettings } from "../composables/useSettings.js";

/**
 * "Permissions" tab inside `Settings.vue`'s dialog. Only field here is
 * column-permission strictness; row-level user permissions are deliberately
 * not a switch (see the field's own description below).
 *
 * The control is a `Toggle` pill switch, the same one Insights uses for both
 * of its Permissions checks (`src2/settings/PermissionsSettings.vue:88,95`).
 * Insights' two fields have no equivalent here on purpose: `enable_permissions`
 * gates *its* teams layer, and Nakhoda has no teams doctype - every read goes
 * through Frappe's own role and user-permission stack in
 * `engine/permissions.py:for_user`, which is not something a settings switch
 * may turn off.
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
				<h1 class="text-xl font-semibold text-ink-gray-9">Permissions</h1>
				<p class="mt-1 text-sm text-ink-gray-6">
					How strictly a pipeline reacts to a column the viewer may not read.
				</p>
			</div>

			<SettingItem
				label="Fail On Unreadable Columns"
				description="Off: a pipeline naming a column the viewer cannot read has that column dropped. On: it raises. Either way the column is never returned. There is deliberately no switch for user permissions themselves - they are injected by the resolver that builds every pipeline."
			>
				<Toggle v-model="settings.doc.strict_columns" />
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
