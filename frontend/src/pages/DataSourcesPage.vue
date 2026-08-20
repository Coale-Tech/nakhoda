<script setup>
import { computed, onMounted, ref } from "vue";
import {
	Avatar,
	Badge,
	Breadcrumbs,
	Button,
	Dropdown,
	FormControl,
	LoadingIndicator,
	dialog,
} from "frappe-ui";
import { List, ListHeader, ListHeaderCell, ListRow, ListCell, ListRows } from "frappe-ui/list";
import ConnectSourceDialog from "../components/ConnectSourceDialog.vue";
import SelectTypeDialog from "../components/SelectTypeDialog.vue";
import UploadTableDialog from "../components/UploadTableDialog.vue";
import { useDataSources } from "../composables/useDataSources.js";
import { useSessionStore } from "../stores/session.js";
import { timeAgo } from "../composables/useTimestamp.js";

/**
 * `Nakhoda Data Source` rows: the site database, the DuckDB warehouse, and any
 * external database somebody connected. Chrome and flow match Insights'
 * `src2/data_source/DataSourceList.vue` - an `h-12` header owning
 * `Breadcrumbs` and a "New Data Source" button, a search row, then the list -
 * and so does the two-step add: pick a type, then fill that type's connection
 * form (`SelectTypeDialog` -> `ConnectSourceDialog` / `UploadTableDialog`).
 *
 * Three kinds of row, and the difference decides what a row can do:
 *
 * - **Site Database** and **DuckDB Warehouse** are created by the backend on
 *   first use (`nakhoda.api.default_source`, `data_store._warehouse_source`).
 *   Their credentials come from `site_config.json` and the site's own files,
 *   so Edit and Delete are absent rather than disabled - there is no form that
 *   could change them, and `update_data_source` / `on_trash` refuse anyway.
 * - **External Database** rows came from the dialog, so they can be
 *   re-pointed and removed.
 *
 * Rows drill into `/data-sources/:name`, matching Insights' `DataSourceList`
 * -> `DataSourceTableList` -> `DataSourceTable` path. Every write action is
 * admin-only, the same split the Data Store draws over its Import button:
 * `Nakhoda User` may look at a source, not reconfigure it.
 *
 * Insights' column set, in Insights' order: Title, Status, Owner, Created,
 * Modified - plus one cell of row actions this list needs and Insights' does
 * not (Insights reconfigures a source from its detail page; here Set Default
 * and Test Connection belong next to the row they act on). Two Nakhoda-only
 * facts fold into cells that already exist rather than widening the table:
 * a source's table count lives on its own page, where counting an external
 * database is affordable, and `last_checked` is the Status cell's tooltip -
 * the badge says whether the connection answered, the tooltip says when.
 *
 * Status is a `Badge`, not Insights' coloured dot plus text: `Untested` is a
 * third state a two-colour indicator has no room for, and the Data Store
 * list next door already reads sync state as a badge.
 *
 * Type glyphs are generic lucide icons rather than Insights' vendor logos:
 * this app ships no brand assets, and a wrong logo is worse than a database
 * icon plus the name.
 *
 * Filtering is client-side over an already-loaded list, exactly as Insights'
 * `filteredDataSources` computed does - the list is a handful of rows, so a
 * debounced round trip per keystroke (the pattern the Data Store page needs
 * for hundreds of DocTypes) would be latency bought for nothing.
 */
const store = useDataSources();
const session = useSessionStore();

const searchQuery = ref("");

const filteredSources = computed(() => {
	const term = searchQuery.value.trim().toLowerCase();
	if (!term) return store.sources;
	return store.sources.filter((source) => source.title.toLowerCase().includes(term));
});

// Failures land on `store.error`, which the template renders; rethrowing past
// that point only produces an unhandled rejection.
onMounted(() => store.list().catch(() => {}));

function statusTheme(status) {
	if (status === "Reachable") return "green";
	if (status === "Unreachable") return "red";
	return "gray";
}

const showTypeDialog = ref(false);
const showConnectDialog = ref(false);
const showUploadDialog = ref(false);
const connectType = ref("MariaDB");
const editing = ref(null); // the external row being re-pointed, or null to create

/**
 * Open the connection form. Editing fetches the row first: the list carries
 * only what its columns show, so a form built from a list row would open with
 * an empty host and ask for a connection the user already configured.
 */
async function openConnect(type, source = null) {
	connectType.value = type;
	editing.value = source ? await store.get(source.name).catch(() => source) : null;
	showTypeDialog.value = false;
	showConnectDialog.value = true;
}

const sourceTypes = [
	{
		label: "MariaDB",
		icon: "lucide-database",
		description: "Connect to a MariaDB or MySQL database",
		onClick: () => openConnect("MariaDB"),
	},
	{
		label: "PostgreSQL",
		icon: "lucide-database",
		description: "Connect to a PostgreSQL database",
		onClick: () => openConnect("PostgreSQL"),
	},
	{
		label: "ClickHouse",
		icon: "lucide-database-zap",
		description: "Connect to a ClickHouse database",
		onClick: () => openConnect("ClickHouse"),
	},
	{
		label: "DuckDB",
		icon: "lucide-file-box",
		description: "Read a DuckDB file this site can reach",
		onClick: () => openConnect("DuckDB"),
	},
	{
		label: "Upload CSV or Excel",
		icon: "lucide-file-up",
		description: "Upload a file and store it as a warehouse table",
		onClick: () => {
			showTypeDialog.value = false;
			showUploadDialog.value = true;
		},
	},
];

/**
 * The glyph in front of a title, standing where Insights renders a vendor
 * logo. Keyed off the same labels the add menu offers, so a type can never
 * appear with one icon in the picker and another in the list; the two built-in
 * rows have no `database_type` and take the icon their own screens use
 * (`AppSidebar.vue`'s Data Store entry is `lucide-server`).
 */
const TYPE_GLYPHS = Object.fromEntries(sourceTypes.map((t) => [t.label, t.icon]));

function glyphFor(source) {
	if (source.source_type === "DuckDB Warehouse") return "lucide-server";
	return TYPE_GLYPHS[source.database_type] ?? "lucide-database";
}

/**
 * Deleting a source drops the connection, not the data behind it - but every
 * saved query pointing at it stops resolving, so the confirm names the row.
 */
function confirmDelete(source) {
	dialog.danger({
		title: "Delete data source",
		message: `Delete ${source.title}? Queries and dashboards built on it will stop working.`,
		onConfirm: () => store.remove(source.name).catch(() => {}),
	});
}
</script>

<template>
	<header
		class="flex h-12 shrink-0 items-center justify-between border-b border-outline-gray-2 py-2.5 pl-5 pr-2"
	>
		<Breadcrumbs :items="[{ label: 'Data Sources', route: { name: 'Data Sources' } }]" />
		<Button
			v-if="session.isAdmin"
			variant="solid"
			theme="gray"
			label="New Data Source"
			@click="showTypeDialog = true"
		>
			<template #prefix>
				<span class="lucide-plus size-4" aria-hidden="true" />
			</template>
		</Button>
	</header>

	<div class="flex min-h-0 flex-1 flex-col gap-3 overflow-auto px-5 py-3">
		<div class="flex gap-2 overflow-visible py-1">
			<FormControl placeholder="Search by Title" v-model="searchQuery">
				<template #prefix>
					<span class="lucide-search size-4 text-ink-gray-4" aria-hidden="true" />
				</template>
			</FormControl>
		</div>

		<div v-if="store.loading && !store.sources.length" class="flex flex-1 items-center justify-center">
			<LoadingIndicator class="size-6" />
		</div>
		<div
			v-else-if="store.error"
			class="rounded-sm border border-outline-red-2 bg-surface-red-1 p-4 text-sm text-ink-red-6"
		>
			Could not load data sources.
		</div>
		<List
			v-else-if="filteredSources.length"
			class="min-h-0 flex-1 overflow-y-auto"
			:columns="['minmax(0,1.5fr)', '9rem', 'minmax(0,1fr)', '9rem', '9rem', '14rem']"
		>
			<ListHeader>
				<ListHeaderCell>Title</ListHeaderCell>
				<ListHeaderCell>Status</ListHeaderCell>
				<ListHeaderCell>Owner</ListHeaderCell>
				<ListHeaderCell>Created</ListHeaderCell>
				<ListHeaderCell>Modified</ListHeaderCell>
				<ListHeaderCell />
			</ListHeader>
			<ListRows :items="filteredSources" row-key="name">
				<template #default="{ item, value }">
					<ListRow :value="value" :to="{ name: 'Data Source Tables', params: { name: item.name } }">
						<ListCell>
							<div class="flex min-w-0 items-center gap-2">
								<span
									:class="glyphFor(item)"
									class="size-4 shrink-0 text-ink-gray-6"
									aria-hidden="true"
								/>
								<span class="truncate text-base">{{ item.title }}</span>
								<Badge v-if="item.is_default" theme="blue" variant="subtle">Default</Badge>
							</div>
						</ListCell>
						<ListCell>
							<Badge
								:theme="statusTheme(item.status)"
								variant="subtle"
								:title="`Last checked ${timeAgo(item.last_checked)}`"
							>
								{{ item.status }}
							</Badge>
						</ListCell>
						<ListCell>
							<div class="flex min-w-0 items-center gap-2">
								<Avatar size="sm" :label="item.owner_name || item.owner" />
								<span class="truncate text-base">{{ item.owner_name || item.owner }}</span>
							</div>
						</ListCell>
						<ListCell>
							<span class="truncate text-base" :title="item.creation ?? ''">
								{{ timeAgo(item.creation) }}
							</span>
						</ListCell>
						<ListCell>
							<span class="truncate text-base" :title="item.modified ?? ''">
								{{ timeAgo(item.modified) }}
							</span>
						</ListCell>
						<!-- The row is an <a> once `to` is set, so an action inside it
						     must swallow the click rather than navigate. -->
						<ListCell class="justify-end gap-2" @click.stop.prevent>
							<Button
								v-if="session.isAdmin && !item.is_default"
								size="sm"
								variant="ghost"
								label="Set Default"
								@click="store.setDefault(item.name).catch(() => {})"
							/>
							<Button
								v-if="session.isAdmin"
								size="sm"
								variant="outline"
								label="Test Connection"
								:loading="store.testing === item.name"
								@click="store.testConnection(item.name).catch(() => {})"
							/>
							<Dropdown
								v-if="session.isAdmin && item.source_type === 'External Database'"
								:options="[
									{
										label: 'Edit Connection',
										icon: 'lucide-pencil',
										onClick: () => openConnect(item.database_type, item),
									},
									{
										label: 'Delete',
										icon: 'lucide-trash-2',
										onClick: () => confirmDelete(item),
									},
								]"
							>
								<Button size="sm" variant="ghost" aria-label="More actions">
									<template #icon>
										<span class="lucide-more-horizontal size-4" aria-hidden="true" />
									</template>
								</Button>
							</Dropdown>
						</ListCell>
					</ListRow>
				</template>
			</ListRows>
		</List>
		<div v-else class="mt-10 rounded-lg border border-outline-gray-2 bg-surface-elevation-1 p-10 text-center">
			<p class="text-p-base text-ink-gray-6">
				{{
					searchQuery
						? "No data source matches this search."
						: "No data sources. The site database is created the first time a question is asked."
				}}
			</p>
			<Button
				v-if="session.isAdmin && !searchQuery"
				class="mt-4"
				variant="solid"
				theme="gray"
				label="New Data Source"
				@click="showTypeDialog = true"
			/>
		</div>
	</div>

	<SelectTypeDialog v-model="showTypeDialog" title="Select a data source" :types="sourceTypes" />
	<ConnectSourceDialog
		v-model="showConnectDialog"
		:database-type="connectType"
		:store="store"
		:source="editing"
	/>
	<UploadTableDialog v-model="showUploadDialog" @imported="store.list().catch(() => {})" />
</template>
