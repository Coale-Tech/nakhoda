<script setup>
import { computed, ref, watch } from "vue";
import { Button, Dialog, FormControl } from "frappe-ui";

/**
 * The connection form for one external database, ported from Insights' four
 * near-identical dialogs (`ConnectMariaDBDialog.vue`,
 * `ConnectPostgreSQLDialog.vue`, `ConnectClickhouseDialog.vue`,
 * `ConnectDuckDBDialog.vue`) into one spec-driven component.
 *
 * Four copies of the same 130-line file is how Insights carries this, and the
 * copies have already drifted: only Postgres offers `schema`, only DuckDB
 * validates its field. One `FIELDS` table keyed by `database_type` makes the
 * difference the data it is - the fields *are* what distinguishes these
 * databases - and leaves one place to fix a bug in.
 *
 * `store` is the page's `useDataSources()` instance, passed in rather than
 * created here: `create`/`update` refresh the list they wrote to, so a second
 * instance would mean a second list request whose result nothing renders.
 *
 * Two adaptations forced by this bench's frappe-ui (`1.0.0-beta.29`):
 *
 * - No `<Form>` component exists (only `FormControl`), so the field list is
 *   looped in the template and `hasRequiredFields` is computed locally.
 * - `Dialog` takes flat props with `#default` / `#actions`, not the
 *   deprecated `:options` + `#body-content` pair Insights still uses.
 *
 * One deliberate divergence in behaviour: editing any field after a
 * successful Connect clears the result. Insights keeps it, which lets you
 * connect to one host, retype the host, and save the untested one - the
 * failure then surfaces as a broken row every other user sees, which is
 * exactly what the Test button exists to prevent.
 */
const props = defineProps({
	// MariaDB | PostgreSQL | ClickHouse | DuckDB
	databaseType: { type: String, required: true },
	// The page's `useDataSources()` instance.
	store: { type: Object, required: true },
	// An existing external row to re-point, or null to create one.
	source: { type: Object, default: null },
});
const emit = defineEmits(["saved"]);

const show = defineModel({ type: Boolean, default: false });

const TITLE = { label: "Title", name: "title", type: "text", placeholder: "My Database", required: true };

const CREDENTIALS = [
	{ label: "Database Name", name: "database_name", type: "text", placeholder: "DB_1267891", required: true },
	{ label: "Username", name: "username", type: "text", placeholder: "read_only_user", required: true },
	{ label: "Password", name: "password", type: "password", placeholder: "**********", required: true },
	{ label: "Use secure connection (SSL)?", name: "use_ssl", type: "checkbox" },
];

/**
 * Ports carry the server's default as a placeholder, not a value: an empty
 * port means "whatever the driver defaults to", which is the same number, and
 * a pre-filled one is a value the user then owns.
 */
const FIELDS = {
	MariaDB: [
		TITLE,
		{ label: "Host", name: "host", type: "text", placeholder: "localhost", required: true },
		{ label: "Port", name: "port", type: "number", placeholder: "3306" },
		...CREDENTIALS,
	],
	PostgreSQL: [
		TITLE,
		{ label: "Host", name: "host", type: "text", placeholder: "localhost", required: true },
		{ label: "Port", name: "port", type: "number", placeholder: "5432" },
		{ label: "Schema", name: "schema", type: "text", placeholder: "eg. schema1,schema2" },
		...CREDENTIALS,
	],
	ClickHouse: [
		TITLE,
		{ label: "Host", name: "host", type: "text", placeholder: "localhost", required: true },
		{ label: "Port", name: "port", type: "number", placeholder: "8123" },
		...CREDENTIALS,
	],
	DuckDB: [
		TITLE,
		{
			label: "File Path or URL",
			name: "database_name",
			type: "text",
			placeholder: "https://example.com/file.duckdb",
			required: true,
			description: "A .duckdb file this site can read - a path under the site's files, or an HTTP URL.",
		},
	],
};

const isEdit = computed(() => Boolean(props.source?.name));

/**
 * The form's fields for this database type. On an edit the password stops
 * being required: `get_data_source` never returns the stored secret, so
 * demanding it back would mean retyping a credential to change a port. Empty
 * means unchanged, both here and in `update_data_source`.
 */
const fields = computed(() =>
	(FIELDS[props.databaseType] ?? []).map((field) =>
		isEdit.value && field.name === "password"
			? {
					...field,
					required: false,
					placeholder: "Unchanged",
					description: "Leave empty to keep the stored password.",
				}
			: field,
	),
);

function blank() {
	const doc = {};
	for (const field of fields.value) doc[field.name] = field.type === "checkbox" ? 0 : "";
	return doc;
}

const doc = ref(blank());
const connected = ref(null);
const message = ref("");
const saveError = ref(null);

// Reopening the dialog, or switching which type it shows, starts a fresh form:
// a password left from a previous attempt would otherwise be submitted against
// a different host.
watch(
	() => [show.value, props.databaseType, props.source?.name],
	() => {
		if (!show.value) return;
		doc.value = { ...blank(), ...(props.source ?? {}) };
		connected.value = null;
		message.value = "";
		saveError.value = null;
	},
	{ immediate: true },
);

const hasRequiredFields = computed(() =>
	fields.value.every((field) => !field.required || String(doc.value[field.name] ?? "").trim()),
);

/**
 * Only the fields this form owns, plus the two the backend keys off. An edit
 * also carries `name`, which is how `test_connection` fills in a password the
 * browser was never given.
 */
function payload() {
	const out = { source_type: "External Database", database_type: props.databaseType };
	if (isEdit.value) out.name = props.source.name;
	for (const field of fields.value) {
		const value = doc.value[field.name];
		if (field.type === "checkbox") out[field.name] = value ? 1 : 0;
		else if (String(value ?? "").trim()) out[field.name] = value;
	}
	return out;
}

const connectLabel = computed(() => {
	if (props.store.probing) return "Connecting...";
	if (connected.value) return "Connected";
	if (connected.value === false) return "Failed, Retry?";
	return "Connect";
});

const connectTheme = computed(() => {
	if (connected.value) return "green";
	if (connected.value === false) return "red";
	return "gray";
});

async function probe() {
	message.value = "";
	try {
		const result = await props.store.probe(payload());
		connected.value = result?.status === "Reachable";
		message.value = result?.message ?? "";
	} catch (e) {
		connected.value = false;
		message.value = e?.message ?? "Could not reach this database.";
	}
}

async function save() {
	saveError.value = null;
	try {
		const result = isEdit.value
			? await props.store.update(props.source.name, payload())
			: await props.store.create(payload());
		show.value = false;
		emit("saved", result);
	} catch (e) {
		saveError.value = e;
	}
}
</script>

<template>
	<Dialog v-model="show" :title="`${isEdit ? 'Edit' : 'Connect to'} ${databaseType}`">
		<div class="mt-4 flex flex-col gap-4">
			<div v-for="field in fields" :key="field.name" class="flex flex-col gap-1">
				<FormControl
					:type="field.type"
					:label="field.label"
					:placeholder="field.placeholder"
					v-model="doc[field.name]"
					@update:modelValue="connected = null"
				/>
				<p v-if="field.description" class="text-p-xs text-ink-gray-6">{{ field.description }}</p>
			</div>

			<p v-if="message" class="text-p-sm" :class="connected ? 'text-ink-green-3' : 'text-ink-red-4'">
				{{ message }}
			</p>

			<div
				v-if="saveError"
				class="rounded-sm border border-outline-red-2 bg-surface-red-1 p-3 text-sm text-ink-red-6"
			>
				{{ saveError.message ?? "Could not save this data source." }}
			</div>
		</div>

		<template #actions>
			<div class="flex justify-end gap-2">
				<Button
					variant="subtle"
					:theme="connectTheme"
					:label="connectLabel"
					:disabled="!hasRequiredFields || store.saving"
					:loading="store.probing"
					@click="probe()"
				/>
				<Button
					:variant="connected ? 'solid' : 'subtle'"
					theme="gray"
					:label="isEdit ? 'Save' : 'Add Data Source'"
					:disabled="!hasRequiredFields || !connected || store.probing"
					:loading="store.saving"
					@click="save()"
				/>
			</div>
		</template>
	</Dialog>
</template>
