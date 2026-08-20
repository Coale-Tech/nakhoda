<script setup>
import { computed, ref } from "vue";
import { Button, Dialog, FileUploader, LoadingIndicator, toast } from "frappe-ui";
import DataTable from "./DataTable.vue";
import { useUploads } from "../composables/useUploads.js";

/**
 * Upload a CSV or Excel file and land it in the warehouse as a table. Ported
 * from Insights' `src2/data_source/UploadCSVFileDialog.vue`: drop zone, then a
 * preview of what was parsed, then Import.
 *
 * The preview is the point of the two-step flow. A misread delimiter shows up
 * as one column holding the whole row, and seeing that *before* anything is
 * written means walking away rather than deleting a bad table - the file is
 * parsed in a throwaway in-memory DuckDB (`api/files.get_upload_preview`), so
 * nothing has been written yet at that moment.
 *
 * Differences from Insights, both of them consequences of where the table
 * goes:
 *
 * - No editable "Table Name" box. The physical name is derived by the backend
 *   (`upload_<slug>`, prefixed so an upload can never collide with `tab*`),
 *   and letting the browser choose a name for a table in a shared warehouse
 *   is how two people overwrite each other's data.
 * - Row cap comes from `Nakhoda Settings.max_records_to_sync`, applied by the
 *   backend like every other warehouse import, rather than being a field on
 *   this dialog.
 */
const show = defineModel({ type: Boolean, default: false });
const emit = defineEmits(["imported"]);

const uploads = useUploads();

const file = ref(null); // { name, file_name } - the `File` doc, not the bytes
const uploadError = ref("");

const columns = computed(() => {
	const preview = uploads.preview;
	if (!preview) return [];
	return preview.columns.map((column) => ({
		label: column.label,
		// Numbers right-align; the type comes from DuckDB's own inference, so
		// this is the file's shape rather than a guess made from the values.
		align: /int|float|decimal|double|numeric/i.test(column.type) ? "num" : undefined,
	}));
});

const rows = computed(() => {
	const preview = uploads.preview;
	if (!preview) return [];
	return preview.rows.map((row) => ({
		cells: preview.columns.map((column) => ({ text: formatCell(row[column.column]) })),
	}));
});

function formatCell(value) {
	if (value === null || value === undefined) return "—";
	return String(value);
}

async function onUploaded(doc) {
	uploadError.value = "";
	file.value = doc;
	try {
		await uploads.load(doc.name);
	} catch (e) {
		uploadError.value = e?.message ?? "Could not read this file.";
		file.value = null;
	}
}

async function runImport() {
	if (!file.value) return;
	try {
		const result = await uploads.importFile(file.value.name);
		toast.success(`Imported ${result?.label ?? file.value.file_name}`);
		show.value = false;
		reset();
		emit("imported", result);
	} catch (e) {
		uploadError.value = e?.message ?? "Could not import this file.";
	}
}

function reset() {
	file.value = null;
	uploadError.value = "";
	uploads.reset();
}
</script>

<template>
	<Dialog
		v-model="show"
		:title="file ? 'Import Table' : 'Upload CSV or Excel File'"
		:size="uploads.preview ? '4xl' : 'lg'"
	>
		<div class="mt-4 flex flex-col gap-4">
			<FileUploader
				v-if="!file"
				:upload-args="{ private: true }"
				:file-types="['.csv', '.xlsx']"
				@success="onUploaded"
			>
				<template #default="{ progress, uploading, openFileSelector }">
					<button
						type="button"
						class="flex w-full cursor-pointer flex-col items-center justify-center gap-3 rounded border border-dashed border-outline-gray-3 p-12"
						@click="openFileSelector"
					>
						<span v-if="!uploading" class="lucide-file-up size-6 text-ink-gray-6" aria-hidden="true" />
						<template v-if="!uploading">
							<p class="text-p-sm font-medium text-ink-gray-8">
								Select a CSV or Excel file to upload
							</p>
							<p class="text-p-xs text-ink-gray-6">or drag and drop it here</p>
						</template>
						<div v-else class="flex w-60 flex-col gap-2">
							<div class="h-2 w-full rounded-full bg-surface-gray-3">
								<div
									class="h-2 rounded-full bg-surface-gray-7 transition-all motion-reduce:transition-none"
									:style="{ width: `${progress}%` }"
								/>
							</div>
							<p class="text-p-xs text-ink-gray-6">Uploading… {{ progress }}%</p>
						</div>
					</button>
				</template>
			</FileUploader>

			<div v-else-if="uploads.loading" class="flex h-40 items-center justify-center">
				<LoadingIndicator class="size-6" />
			</div>

			<template v-else-if="uploads.preview">
				<div class="flex items-baseline justify-between">
					<p class="text-p-base text-ink-gray-8">{{ uploads.preview.label }}</p>
					<p class="text-p-sm font-mono text-ink-gray-6">{{ uploads.preview.table }}</p>
				</div>
				<DataTable :columns="columns" :rows="rows" />
				<p class="text-p-sm text-ink-gray-6">
					Showing {{ uploads.preview.preview_rows }} of {{ uploads.preview.row_count }} rows
				</p>
			</template>

			<div
				v-if="uploadError"
				class="rounded-sm border border-outline-red-2 bg-surface-red-1 p-3 text-sm text-ink-red-6"
			>
				{{ uploadError }}
			</div>
		</div>

		<template #actions>
			<div class="flex justify-end gap-2">
				<Button variant="subtle" theme="gray" label="Reset File" :disabled="!file" @click="reset()" />
				<Button
					variant="solid"
					theme="gray"
					label="Import"
					:disabled="!uploads.preview || uploads.importing"
					:loading="uploads.importing"
					@click="runImport()"
				/>
			</div>
		</template>
	</Dialog>
</template>
