<script setup>
import { Button, FormControl, LoadingIndicator } from "frappe-ui";
import SettingItem from "./SettingItem.vue";
import Toggle from "../components/Toggle.vue";
import { useSettings } from "../composables/useSettings.js";

/**
 * The Data Store tab: Insights' three controls, in Insights' order -
 * Enable, Row Limit, Memory Limit (`src2/settings/DataStoreSettings.vue`).
 *
 * Three things about the shape, all of them things this tab got wrong first
 * time round:
 *
 * - `Enable` is a `Toggle` (pill switch), because that is the control
 *   Insights renders here and on its Permissions tab. It is not the labelled
 *   `On`/`Off` checkbox the AI Provider tab uses - Insights renders *that*
 *   tab with a checkbox (`AISettings.vue:356`), and matching means copying
 *   the difference, not averaging it away.
 * - Row Limit and Memory Limit are always visible. They were previously
 *   hidden behind `v-if="enable_data_store"`, which meant an install that
 *   had never written the field saw a single Off switch and nothing else -
 *   the caps were unreachable exactly when someone was about to turn the
 *   store on and wanted to check them.
 * - The tab is full width with an `text-xl` heading, like the AI Provider
 *   tab and like every Insights settings tab. `max-w-2xl` made the controls
 *   sit in a narrow column that matched neither.
 *
 * `Enable` is load-bearing, not decorative. Off, `api/data_store.py`'s
 * `import_table` refuses with a message naming this setting and the daily
 * `sync_stored_tables` sweep returns immediately - but tables already in the
 * warehouse stay queryable. Insights' toggle gates the same direction: it
 * stops new copies, it does not retract landed ones. A switch that changed
 * the answer to a question already being asked would be a bug nobody could
 * reproduce.
 *
 * The two limits are Ints, so an unwritten Single reads `0`. The backend
 * treats that as "unset" and falls back (`DEFAULT_ROW_LIMIT` /
 * `DEFAULT_MEMORY_MB`) rather than importing nothing and refusing to
 * allocate; the placeholders here say the same numbers, so the page and the
 * worker cannot disagree about the default.
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
			<div class="flex items-center justify-between">
				<div>
					<h1 class="text-xl font-semibold text-ink-gray-9">Data Store</h1>
					<p class="mt-1 text-sm text-ink-gray-6">
						Where imported tables land, and how much of one may be copied.
					</p>
				</div>
			</div>

			<SettingItem
				label="Enable"
				description="Copy site tables into a DuckDB database for faster and cross-database queries. Turning this off stops new imports and the daily refresh; tables already imported stay queryable."
			>
				<Toggle v-model="settings.doc.enable_data_store" />
			</SettingItem>

			<SettingItem
				label="Row Limit"
				description="Maximum rows copied per table into the DuckDB warehouse. A table's own Row Limit overrides this. Default is 1,000,000."
			>
				<FormControl
					type="number"
					class="w-28"
					placeholder="1000000"
					v-model="settings.doc.max_records_to_sync"
				/>
			</SettingItem>

			<SettingItem
				label="Memory Limit"
				description="Memory ceiling, in MB, applied to the DuckDB connection while a table imports. Default is 512."
			>
				<FormControl
					type="number"
					class="w-28"
					placeholder="512"
					v-model="settings.doc.max_memory_usage"
				/>
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
