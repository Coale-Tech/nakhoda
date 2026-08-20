<script setup>
import { computed, onMounted, onUnmounted, ref } from "vue";
import { Badge, Breadcrumbs, Button, FormControl, LoadingIndicator, toast } from "frappe-ui";
import { List, ListHeader, ListHeaderCell, ListRow, ListCell, ListRows } from "frappe-ui/list";
import ImportTableDialog from "../components/ImportTableDialog.vue";
import { useDataStore } from "../composables/useDataStore.js";
import { useSettings } from "../composables/useSettings.js";
import { useSessionStore } from "../stores/session.js";
import { timeAgo } from "../composables/useTimestamp.js";

/**
 * DuckDB warehouse tables synced from the site's own database. Every readable
 * DocType is a candidate row (`sync_state: "Never"` until imported) - this is
 * a picker over everything importable, not only what has already landed,
 * matching Insights' `DataStoreList.vue`.
 *
 * Importing enqueues a background job (`api/data_store.py:import_table`) and
 * the row goes to "Syncing"; `useDataStore` polls until nothing is in flight,
 * so a finished import lands on screen without a reload. That is the one place
 * this page is deliberately unlike Insights, whose import blocks the request.
 *
 * The Import button is admin-only, matching the endpoint's own gate (create on
 * `Nakhoda Table`) - `Nakhoda User` can see what is in the warehouse and query
 * it, but not decide what gets materialised into it.
 *
 * Built on `frappe-ui/list`, like every other list in this app: `ListView` is
 * the legacy family in the installed frappe-ui (`components/ListView/index.md`
 * says so), and it renders each row as a `<button>`, which cannot legally
 * contain the per-row Import button this page needs.
 *
 * The page owns its own `h-12` header - `Breadcrumbs` left, live state right -
 * rather than leaning on a shell title bar, which is Insights' arrangement
 * (`src2/data_store/DataStoreList.vue`) and the only one that can express the
 * `/data-sources/:name/:table` hierarchy the drill-down pages need.
 *
 * No global "Import Table" button, unlike Insights: there is exactly one
 * warehouse and the table is chosen by the row you clicked, so the dialog it
 * would open has nothing left to ask that the row has not already answered.
 */
const store = useDataStore();
const settings = useSettings();
const session = useSessionStore();

const searchQuery = ref("");
const showImportDialog = ref(false);
const selectedTable = ref(null);
let searchTimer = null;

// `useSettings()`'s GET is immediate (see that composable), so the only thing
// this page kicks off is the table list. Failures land on `store.error`, which
// the template renders; rethrowing past that point only produces an unhandled
// rejection.
onMounted(() => store.list().catch(() => {}));

// The poll outlives the component otherwise: `setInterval` keeps firing (and
// re-listing) against a page nobody is looking at.
onUnmounted(() => {
	clearTimeout(searchTimer);
	store.stopPolling();
});

function onSearch() {
	clearTimeout(searchTimer);
	searchTimer = setTimeout(() => store.list(searchQuery.value).catch(() => {}), 300);
}

const defaultLimit = computed(() => Number(settings.doc?.max_records_to_sync) || 0);

function badgeTheme(state) {
	if (state === "Synced") return "green";
	if (state === "Syncing") return "blue";
	if (state === "Failed") return "red";
	return "gray";
}

function openImport(row) {
	selectedTable.value = row;
	showImportDialog.value = true;
}

async function runImport(rowLimit) {
	const row = selectedTable.value;
	if (!row) return;
	showImportDialog.value = false;
	try {
		const outcome = await store.importTable(row.doctype, rowLimit);
		// `queued: false` is the endpoint reporting that this table is already
		// importing - a fact worth showing, not an error worth throwing.
		if (outcome?.queued === false) {
			toast.info(`${row.label} is already importing.`);
		} else {
			toast.success(`Importing ${row.label} in the background.`);
		}
	} catch (e) {
		toast.error(e?.message || `Could not queue ${row.label}.`);
	}
}
</script>

<template>
	<header
		class="flex h-12 shrink-0 items-center justify-between border-b border-outline-gray-2 py-2.5 pl-5 pr-2"
	>
		<Breadcrumbs :items="[{ label: 'Data Store', route: { name: 'Data Store' } }]" />
		<div class="flex items-center gap-2">
			<Badge v-if="store.polling" theme="blue" variant="subtle">Importing…</Badge>
		</div>
	</header>

	<div class="flex min-h-0 flex-1 flex-col gap-3 overflow-auto px-5 py-3">
		<div class="flex gap-2 overflow-visible py-1">
			<FormControl placeholder="Search tables" v-model="searchQuery" @input="onSearch">
				<template #prefix>
					<span class="lucide-search size-4 text-ink-gray-4" aria-hidden="true" />
				</template>
			</FormControl>
		</div>

		<!-- The sidebar drops this page's link when the store is switched off
		     (Insights hides the same single entry, `src2/components/AppSidebar.vue:167`),
		     but the route stays registered there and here, so a bookmark or a
		     back button still lands. Insights has nothing to say at that point
		     because its switch gates no backend; this one does
		     (`api/data_store.py:import_table` refuses and names the setting), so
		     the page states the gate and withdraws the Import buttons rather
		     than offering an action the server is guaranteed to reject. Listing
		     stays live: reading the warehouse was never gated, and tables
		     already imported remain queryable. -->
		<div
			v-if="!session.dataStoreEnabled"
			class="rounded-sm border border-outline-gray-2 bg-surface-gray-2 p-3 text-sm text-ink-gray-7"
		>
			The Data Store is switched off in Settings &rsaquo; Data Store. Tables already imported stay
			queryable; new imports and the daily refresh are paused.
		</div>

		<div v-if="store.loading && !store.tables.length" class="flex flex-1 items-center justify-center">
			<LoadingIndicator class="size-6" />
		</div>
		<div
			v-else-if="store.error"
			class="rounded-sm border border-outline-red-2 bg-surface-red-1 p-4 text-sm text-ink-red-6"
		>
			Could not load the data store.
		</div>
		<List
			v-else-if="store.tables.length"
			class="min-h-0 flex-1 overflow-y-auto"
			:columns="['minmax(0,1fr)', 'minmax(0,1.5fr)', '7rem', '11rem', '8rem']"
		>
			<ListHeader>
				<ListHeaderCell>Table</ListHeaderCell>
				<ListHeaderCell>DocType</ListHeaderCell>
				<ListHeaderCell>Rows</ListHeaderCell>
				<ListHeaderCell>Last Synced</ListHeaderCell>
				<ListHeaderCell />
			</ListHeader>
			<ListRows :items="store.tables" row-key="doctype">
				<template #default="{ item, value }">
					<ListRow :value="value">
						<ListCell>
							<span class="truncate font-mono text-xs">{{ item.table_name }}</span>
						</ListCell>
						<ListCell>
							<div class="flex min-w-0 items-center gap-2">
								<span class="truncate text-base">{{ item.label }}</span>
								<Badge :theme="badgeTheme(item.sync_state)" variant="subtle">
									{{ item.sync_state }}
								</Badge>
								<!-- The row keeps its own failure text; a state badge alone
								     would say "Failed" without ever saying why. -->
								<span v-if="item.sync_error" class="truncate text-xs text-ink-red-6">
									{{ item.sync_error }}
								</span>
							</div>
						</ListCell>
						<ListCell class="justify-end tabular-nums">
							<span class="truncate text-base">{{ item.row_count ?? "—" }}</span>
						</ListCell>
						<ListCell>
							<!-- The row's state badge already says "Never" for an
							     unsynced table; repeating it here would spend the
							     widest column restating the narrowest one. -->
							<span class="truncate text-base" :title="item.last_synced ?? ''">
								{{ timeAgo(item.last_synced, "—") }}
							</span>
						</ListCell>
						<ListCell class="justify-end">
							<Button
								v-if="session.isAdmin && session.dataStoreEnabled"
								size="sm"
								variant="outline"
								:label="item.sync_state === 'Never' ? 'Import' : 'Re-sync'"
								:loading="store.importingDoctype === item.doctype"
								:disabled="item.sync_state === 'Syncing'"
								@click="openImport(item)"
							/>
						</ListCell>
					</ListRow>
				</template>
			</ListRows>
		</List>
		<div v-else class="mt-10 rounded-lg border border-outline-gray-2 bg-surface-elevation-1 p-10 text-center">
			<p class="text-p-base text-ink-gray-6">
				{{
					searchQuery
						? "No readable DocType matches this search."
						: "No tables found. Importing copies a DocType's rows into the DuckDB warehouse in the background."
				}}
			</p>
		</div>
	</div>

	<ImportTableDialog
		v-model="showImportDialog"
		:table="selectedTable"
		:default-limit="defaultLimit"
		:loading="store.importingDoctype != null"
		@import="runImport"
	/>
</template>
