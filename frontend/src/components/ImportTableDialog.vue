<script setup>
import { computed, ref, watch } from "vue";
import { Button, Dialog, FormControl } from "frappe-ui";

/**
 * Confirms one import and collects its per-table row limit. Ported from
 * Insights' `ImportTableDialog.vue`, minus the source/table pickers: there is
 * exactly one warehouse and the table is already chosen by the row the button
 * sits on, so the only thing left to ask is how much of it to copy.
 *
 * The limit is a per-table override of `Nakhoda Settings.max_records_to_sync`
 * (`Nakhoda Table.row_limit`); left blank it falls through to the site-wide
 * cap, which is the honest default - a number typed once into a dialog should
 * not silently become a table's permanent policy.
 */
const props = defineProps({
	table: { type: Object, default: null }, // the Data Store row being imported
	defaultLimit: { type: Number, default: 0 }, // site-wide cap, shown as the placeholder
	loading: { type: Boolean, default: false },
});
const emit = defineEmits(["import"]);
const show = defineModel({ type: Boolean, default: false });

const rowLimit = ref("");

// Re-opening for a different table must not inherit the previous one's answer.
watch(
	() => props.table?.doctype,
	(doctype) => {
		rowLimit.value = doctype && props.table?.row_limit ? String(props.table.row_limit) : "";
	},
);

const isResync = computed(() => props.table?.sync_state && props.table.sync_state !== "Never");

function confirm() {
	const parsed = parseInt(rowLimit.value, 10);
	emit("import", Number.isFinite(parsed) && parsed > 0 ? parsed : null);
}
</script>

<template>
	<Dialog v-model="show" :title="isResync ? 'Re-sync Table' : 'Import Table'">
		<template #default>
			<div v-if="table" class="flex flex-col gap-4">
				<p class="text-p-base text-ink-gray-7">
					Copies <span class="font-medium text-ink-gray-9">{{ table.label }}</span> into the site's
					DuckDB warehouse. The copy runs in the background; this table stays queryable while it does.
				</p>
				<FormControl
					type="number"
					label="Row Limit"
					:placeholder="defaultLimit ? String(defaultLimit) : 'Site default'"
					v-model="rowLimit"
				/>
				<p class="text-p-sm text-ink-gray-6">
					Leave blank to use the site-wide limit from Settings. A value here is remembered as this
					table's own limit for future syncs.
				</p>
			</div>
		</template>
		<template #actions>
			<div class="flex justify-end gap-2">
				<Button variant="outline" label="Cancel" @click="show = false" />
				<Button
					variant="solid"
					:label="isResync ? 'Re-sync' : 'Import'"
					:loading="loading"
					@click="confirm"
				/>
			</div>
		</template>
	</Dialog>
</template>
