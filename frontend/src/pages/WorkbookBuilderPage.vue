<script setup>
import { computed, onMounted, onUnmounted, ref, watch, watchEffect } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useStorage } from "@vueuse/core";
import { Button, Dialog, Dropdown, FormControl, LoadingIndicator } from "frappe-ui";
import Chart from "../components/Chart.vue";
import QueryBuilder from "../components/QueryBuilder.vue";
import WorkbookSidebarSection from "../components/WorkbookSidebarSection.vue";
import WorkbookNavbar from "../components/WorkbookNavbar.vue";
import WorkbookShareDialog from "../components/WorkbookShareDialog.vue";
import AskPanel from "../components/AskPanel.vue";
import { useWorkbook } from "../composables/useWorkbook.js";
import { useQuery } from "../composables/useQuery.js";
import { useSessionStore } from "../stores/session.js";

/**
 * One workbook: a sidebar of everything in it, and whichever item the route
 * names in the body.
 *
 * The sidebar is the workbook's whole reason to exist - three collections that
 * belong together, in one place, with folders as grouping labels rather than
 * nesting (`api/workbooks.py:create_folder`). Item selection is a route, not
 * local state, so a saved answer's query is linkable: `save_answer` returns
 * `{workbook, query}` and the Ask page's toast points straight at it.
 *
 * `readOnly` comes from the document (`Nakhoda Workbook.as_dict`) and removes
 * write affordances rather than disabling them: a reader offered a greyed-out
 * "Add query" has been told they may act and then contradicted.
 */
const route = useRoute();
const router = useRouter();
const session = useSessionStore();

const workbookName = computed(() => String(route.params.name));
const itemType = computed(() => (route.params.itemType ? String(route.params.itemType) : null));
const itemId = computed(() => (route.params.itemId ? String(route.params.itemId) : null));

/** The route id an unsaved query holds until its first save creates the row. */
const NEW = "new";
const isDraftQuery = computed(() => itemType.value === "query" && itemId.value === NEW);

const workbook = useWorkbook(workbookName.value);
workbook.load(workbookName.value);
watch(workbookName, (name) => name && workbook.load(name));

/**
 * A bare `/workbooks/:name` has nothing to show: the body renders whichever
 * item the route names, and the route names none. Insights answers this by
 * redirecting to the first query, creating one when the workbook is empty
 * (`src2/workbook/Workbook.vue:24-33`). The redirect is the same here; the
 * creation cannot be, because `validate_pipeline` refuses a query with no
 * source (`nakhoda_query.py`), so an empty workbook opens the *draft* query -
 * which is precisely what Insights' `addQuery()` produces client-side, minus a
 * row written by merely looking at a workbook.
 */
watch(
	[() => route.name, () => workbook.doc],
	() => {
		if (route.name !== "Workbook" || !workbook.doc) return;
		const first = workbook.queries[0];
		openItem("query", first ? first.name : NEW);
	},
	{ immediate: true },
);

watchEffect(() => {
	document.title = `${workbook.title || workbookName.value} | Workbook`;
});

// -- sidebar ---------------------------------------------------------------

/**
 * Dashboards are listed but not filed or ordered: the DocType has neither
 * field and `api/workbooks.py` refuses the item type, so the affordance would
 * be a button that raises. The same split Insights draws.
 */
const SECTIONS = [
	{ type: "query", label: "Queries", organizable: true },
	{ type: "chart", label: "Charts", organizable: true },
	{ type: "dashboard", label: "Dashboards", organizable: false },
];

const collections = computed(() => ({
	query: workbook.queries,
	chart: workbook.charts,
	dashboard: workbook.dashboards,
}));

/**
 * Icons per row, mirroring Insights' intent (`src2/workbook/WorkbookSidebar.vue`
 * gives queries a table glyph and charts one derived from `chart_type`). Insights
 * additionally distinguishes native-SQL and script queries; this app has neither
 * kind, so a single query glyph is the whole truth here.
 */
const CHART_ICONS = {
	Bar: "lucide-bar-chart-3",
	Line: "lucide-line-chart",
	Pie: "lucide-pie-chart",
	Donut: "lucide-pie-chart",
	Number: "lucide-hash",
	Table: "lucide-table-2",
};

function iconFor(type, item) {
	if (type === "chart") return CHART_ICONS[item.chart_type] || "lucide-bar-chart-3";
	if (type === "dashboard") return "lucide-layout-panel-top";
	return "lucide-table-2";
}

function isActive(type, name) {
	return itemType.value === type && itemId.value === String(name);
}

/**
 * Removing the row that is open would leave the body rendering a document that
 * no longer exists, so navigation happens first - back to the bare workbook,
 * whose own effect then picks the next query.
 */
async function removeItem(type, name) {
	if (isActive(type, name)) {
		await router.replace({ name: "Workbook", params: { name: workbookName.value } });
	}
	await workbook.remove(type, name);
}

/**
 * A folder is deleted with its items kept: `delete_folder(move_items_to_root)`
 * defaults to true, and losing a query because its label was tidied away would
 * be a data loss nobody asked for.
 */
function deleteFolder(folderName) {
	return workbook.deleteFolder(folderName, true);
}

/** The one place a sidebar row's destination is spelled out. */
function itemRoute(type, name) {
	return {
		name: "Workbook Item",
		params: { name: workbookName.value, itemType: type, itemId: String(name) },
	};
}

function openItem(type, name) {
	router.push(itemRoute(type, name));
}

// -- ask panel -------------------------------------------------------------

/**
 * Ask, alongside the workbook rather than on its own route.
 *
 * Persisted per app, not per workbook, and keyed like the sidebar's collapse
 * flag (`AppSidebar.vue`): "I work with Ask open" is a working style, whereas
 * remembering it per document would mean the same analyst's next workbook opens
 * differently for no reason they chose.
 *
 * Workbook routes are `meta.chromeless` and `App.vue` hides `AppSidebar` for
 * them, so this panel cannot be a sidebar link - and should not be: at 452px it
 * matches the Inspector, which is the width the answer card's provenance strip
 * was built against.
 */
const askOpen = useStorage("nakhoda:workbookAskOpen", false);

/**
 * A save writes a query into the tree behind us, so the tree is refetched
 * rather than appended to - `get_workbook` computes each row's own columns, and
 * a locally-invented row would be the one entry whose fields were guesses (the
 * same reason `stores/workbook.js` refetches after create).
 *
 * Then it opens: the answer became an artifact, and the whole point of asking
 * here was to land in it.
 */
async function onAskSaved(saved) {
	await workbook.load();
	if (saved?.query) openItem("query", saved.query);
}

const adding = ref(null);

async function add(type) {
	// A new query is a *draft*, not a row: `validate_pipeline` refuses a
	// pipeline with no source, so nothing can be inserted until the builder has
	// one. Charts and dashboards are real writes - both are valid empty.
	if (type === "query") {
		openItem("query", NEW);
		return;
	}
	adding.value = type;
	try {
		if (type === "chart") {
			// A chart reads a query, and `add_chart` refuses one from another
			// workbook (`nakhoda_chart.py:validate_query_workbook`), so the
			// first query here is the only defensible default - and with none,
			// there is nothing to chart yet.
			const query = workbook.queries[0];
			if (!query) return;
			const name = await workbook.addChart(query.name);
			if (name) openItem("chart", name);
			return;
		}
		const name = await workbook.addDashboard();
		if (name) openItem("dashboard", name);
	} finally {
		adding.value = null;
	}
}

function canAdd(type) {
	if (workbook.readOnly) return false;
	// Charts need something to read.
	return type !== "chart" || workbook.queries.length > 0;
}

// -- title -----------------------------------------------------------------

/**
 * The navbar's `ContentEditable` reports what the user typed; deciding whether
 * that is a rename belongs here. An empty title and an unchanged one are both
 * no-ops - blur fires on every pass through the field, and a PUT per focus
 * change would make `modified` meaningless.
 */
async function renameWorkbook(next) {
	const title = String(next || "").trim();
	if (!title || title === workbook.title) return;
	await workbook.rename(title);
}

// -- body ------------------------------------------------------------------

const activeQuery = computed(() =>
	itemType.value === "query" ? workbook.queries.find((q) => String(q.name) === itemId.value) : null,
);
const activeChart = computed(() =>
	itemType.value === "chart" ? workbook.charts.find((c) => String(c.name) === itemId.value) : null,
);
const activeDashboard = computed(() =>
	itemType.value === "dashboard"
		? workbook.dashboards.find((d) => String(d.name) === itemId.value)
		: null,
);

/** `config`/`items` arrive as JSON text from the document API. */
function parseJson(value, fallback) {
	if (!value) return fallback;
	if (typeof value !== "string") return value;
	try {
		return JSON.parse(value);
	} catch {
		return fallback;
	}
}

/**
 * `1 queries` is the kind of detail that makes a real product look unfinished,
 * and the empty state is the first thing a new workbook shows.
 */
function count(n, singular, plural = null) {
	return `${n} ${n === 1 ? singular : plural || singular + "s"}`;
}

const chartSeries = computed(() => parseJson(activeChart.value?.config, {}).series || []);

const dashboardTiles = computed(() => {
	const items = parseJson(activeDashboard.value?.items, []);
	return Array.isArray(items) ? items : [];
});

function tileChart(tile) {
	return workbook.charts.find((c) => String(c.name) === String(tile.chart));
}

function tileSeries(tile) {
	return parseJson(tileChart(tile)?.config, {}).series || [];
}

// The query tab drives the real builder, so it needs the query surface itself:
// pipeline in, SQL and rows back. `useQuery` owns that contract already
// (`composables/useQuery.js`); duplicating its `run` here would be a second
// path to the same endpoint.
const queryApi = useQuery(null);
const pipeline = ref([]);
const sql = ref(null);
const results = ref(null);
const draftTitle = ref("");

// A pipeline with no source cannot be stored (`validate_pipeline`), so the
// button says so by being unavailable rather than by throwing on click.
const canSaveQuery = computed(() => pipeline.value.some((op) => op.type === "source"));

// The draft resets on entry and a saved query loads its stored pipeline. Both
// are the same event - "which query is open changed" - so one watcher, keyed on
// the route id rather than the row, or entering the draft twice would keep the
// first draft's operations.
watch(
	[itemId, activeQuery],
	() => {
		pipeline.value = isDraftQuery.value ? [] : parseJson(activeQuery.value?.operations, []);
		if (isDraftQuery.value) draftTitle.value = "";
		sql.value = null;
		results.value = null;
	},
	{ immediate: true },
);

async function runQuery(next) {
	pipeline.value = next;
	const result = await queryApi.run({
		operations: next,
		data_source: activeQuery.value?.data_source || "",
		limit: 1000,
	});
	sql.value = { html: `<span>${escapeHtml(result.sql || "")}</span>`, plain: result.sql || "" };
	results.value = result;
}

/** A draft's save creates the row; a saved query's save updates it. */
async function saveQuery() {
	if (isDraftQuery.value) {
		const saved = await workbook.addQuery(pipeline.value, draftTitle.value.trim() || "Untitled Query");
		if (saved?.name) openItem("query", saved.name);
		return;
	}
	if (!activeQuery.value) return;
	await queryApi.save({
		name: activeQuery.value.name,
		title: activeQuery.value.title,
		data_source: activeQuery.value.data_source || "",
		operations: pipeline.value,
	});
	await workbook.load();
}

function escapeHtml(value) {
	return String(value)
		.replace(/&/g, "&amp;")
		.replace(/</g, "&lt;")
		.replace(/>/g, "&gt;")
		.replace(/"/g, "&quot;")
		.replace(/'/g, "&#039;");
}

// -- workbook actions ------------------------------------------------------

const busy = ref(false);

async function duplicateWorkbook() {
	busy.value = true;
	try {
		const name = await workbook.duplicate();
		if (name) router.push({ name: "Workbook", params: { name } });
	} finally {
		busy.value = false;
	}
}

async function exportWorkbook() {
	busy.value = true;
	try {
		const payload = await workbook.exportWorkbook();
		// A workbook's export is a JSON tree `import_workbook` accepts back
		// (`api/workbooks.py:import_workbook`), so the useful thing to do with
		// it in a browser is hand the user the file.
		const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
		const url = URL.createObjectURL(blob);
		const link = document.createElement("a");
		link.href = url;
		link.download = `${workbook.title || workbookName.value}.json`;
		link.click();
		URL.revokeObjectURL(url);
	} finally {
		busy.value = false;
	}
}

/**
 * Insights' `Copy JSON` (`workbook.ts:281`): the same export tree, on the
 * clipboard instead of on disk, because the paste handler below reads it back.
 * Copy here, paste in another workbook, and one query or chart crosses over -
 * which is the entire reason the entry exists rather than being a second
 * spelling of Export.
 */
async function copyWorkbookJson() {
	busy.value = true;
	try {
		const payload = await workbook.exportWorkbook();
		await navigator.clipboard?.writeText(JSON.stringify(payload, null, 2));
	} finally {
		busy.value = false;
	}
}

/**
 * The other half of Copy JSON: a pasted query or chart is imported into this
 * workbook (`nakhoda_workbook.py:import_query` / `import_chart`).
 *
 * Insights binds Cmd+V through `useMagicKeys` and then asks
 * `navigator.clipboard.readText()` for the text (`Workbook.vue:52-69`), which
 * needs a permission this app would have to prompt for. The native `paste`
 * event carries the same clipboard on the same keystroke with no permission at
 * all, so that is what this listens to. It also gives the one thing the
 * keys-based version cannot: `event.target`, so pasting into the title or a
 * builder input stays a text paste instead of silently importing a chart.
 */
async function onPaste(event) {
	if (workbook.readOnly) return;
	const target = event.target;
	if (target?.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target?.tagName)) return;
	const text = event.clipboardData?.getData("text/plain");
	if (!text) return;
	let payload;
	try {
		payload = JSON.parse(text);
	} catch {
		return;
	}
	if (payload?.type !== "Query" && payload?.type !== "Chart") return;
	event.preventDefault();
	busy.value = true;
	try {
		const name =
			payload.type === "Query"
				? await workbook.importQuery(payload)
				: await workbook.importChart(payload);
		if (name) openItem(payload.type === "Query" ? "query" : "chart", name);
	} finally {
		busy.value = false;
	}
}

const showShareDialog = ref(false);
const confirmingDelete = ref(false);

async function deleteWorkbook() {
	busy.value = true;
	try {
		await workbook.deleteWorkbook();
		router.replace({ name: "Workbooks" });
	} finally {
		busy.value = false;
		confirmingDelete.value = false;
	}
}

/**
 * Insights' own action set (`src2/workbook/WorkbookNavbarActions.vue`): duplicate,
 * the JSON, delete, and the desk. Each entry is dropped rather than disabled
 * when it cannot apply - a reader offered a greyed-out Delete has been told they
 * may act and then contradicted, which is the same rule the sidebar follows.
 */
const workbookActions = computed(() => {
	const actions = [];
	if (!workbook.readOnly) {
		actions.push({ label: "Duplicate", icon: "copy", onClick: duplicateWorkbook });
	}
	actions.push({ label: "Copy JSON", icon: "copy", onClick: copyWorkbookJson });
	actions.push({ label: "Export", icon: "download", onClick: exportWorkbook });
	if (!workbook.readOnly) {
		actions.push({
			label: "Delete",
			icon: "trash-2",
			onClick: () => (confirmingDelete.value = true),
		});
	}
	if (session.hasDeskAccess) {
		actions.push({
			label: "Open in Desk",
			icon: "external-link",
			onClick: () =>
				window.open(`/app/nakhoda-workbook/${encodeURIComponent(workbookName.value)}`, "_blank"),
		});
	}
	return actions;
});

/**
 * Cmd/Ctrl+S saves whatever the query tab is holding, matching Insights
 * (`src2/workbook/Workbook.vue:49`). Bound on the window rather than the
 * textarea: the pipeline builder is a tree of inputs and the shortcut has to
 * work from any of them. Only the query tab has an unsaved state - charts and
 * dashboards write on change - so elsewhere this is deliberately inert rather
 * than a save of something already saved.
 */
function onKeydown(event) {
	if (!(event.metaKey || event.ctrlKey) || event.key !== "s") return;
	if (!(activeQuery.value || isDraftQuery.value) || workbook.readOnly) return;
	event.preventDefault();
	saveQuery();
}

onMounted(() => {
	window.addEventListener("keydown", onKeydown);
	window.addEventListener("paste", onPaste);
});
onUnmounted(() => {
	window.removeEventListener("keydown", onKeydown);
	window.removeEventListener("paste", onPaste);
});
</script>

<template>
	<WorkbookNavbar
		:title="workbook.title"
		:placeholder="workbookName"
		:read-only="workbook.readOnly"
		@rename="renameWorkbook"
	>
		<template #actions>
			<div class="flex items-center gap-2">
				<!-- A toggle, not a link: the panel is part of this workbook's surface.
				     `aria-pressed` carries which state it is in, so the label does not
				     have to change under the pointer; `variant` says the same thing
				     visually. No `aria-label` here - frappe-ui derives a Button's
				     accessible name from `label` and ignores the attribute
				     (`Button.vue:288`), so one would read as working and do nothing. -->
				<Button
					:variant="askOpen ? 'subtle' : 'outline'"
					icon-left="lucide-message-circle"
					label="Ask"
					:aria-pressed="askOpen ? 'true' : 'false'"
					@click="askOpen = !askOpen"
				/>
				<Button
					v-if="workbook.canShare"
					variant="outline"
					icon-left="lucide-share-2"
					label="Share"
					@click="showShareDialog = true"
				/>
				<Dropdown v-if="workbookActions.length" :options="workbookActions" align="end">
					<Button variant="outline" icon="more-horizontal" :loading="busy" aria-label="Workbook actions" />
				</Dropdown>
			</div>
		</template>
	</WorkbookNavbar>

	<div v-if="workbook.loading && !workbook.doc" class="flex flex-1 items-center justify-center">
		<LoadingIndicator class="size-6" />
	</div>
	<div
		v-else-if="workbook.error && !workbook.doc"
		class="m-5 rounded-sm border border-outline-red-2 bg-surface-red-1 p-4 text-sm text-ink-red-6"
	>
		Could not load this workbook.
	</div>

	<div v-else class="flex min-h-0 flex-1">
		<aside
			class="relative z-[1] flex h-full w-[17rem] shrink-0 flex-col overflow-y-auto bg-surface-white"
		>
			<WorkbookSidebarSection
				v-for="section in SECTIONS"
				:key="section.type"
				:type="section.type"
				:label="section.label"
				:items="collections[section.type]"
				:folders="workbook.folders"
				:read-only="workbook.readOnly"
				:organizable="section.organizable"
				:can-add="canAdd(section.type)"
				:extra-rows="section.type === 'query' && isDraftQuery ? 1 : 0"
				:adding="adding === section.type"
				:is-active="(name) => isActive(section.type, name)"
				:route="(item) => itemRoute(section.type, item.name)"
				@add="add(section.type)"
				@remove="(name) => removeItem(section.type, name)"
				@rename="(name, title) => workbook.renameItem(section.type, name, title)"
				@move="(name, folder) => workbook.moveToFolder(section.type, name, folder)"
				@reorder="(rows) => workbook.reorder(rows)"
				@create-folder="(title) => workbook.createFolder(title, section.type)"
				@rename-folder="(folder, title) => workbook.renameFolder(folder, title)"
				@delete-folder="deleteFolder"
				@toggle-folder="(folder, expanded) => workbook.toggleFolder(folder, expanded)"
			>
				<template #item-icon="{ item }">
					<span class="size-3.5 shrink-0 text-ink-gray-6" :class="iconFor(section.type, item)" aria-hidden="true" />
				</template>

				<!-- The draft, listed where it will land once saved: a body with no
				     corresponding sidebar row reads as a lost place. -->
				<template v-if="section.type === 'query' && isDraftQuery" #trailing>
					<router-link
						:to="itemRoute('query', NEW)"
						class="flex h-7.5 items-center gap-1.5 truncate rounded bg-surface-gray-2 pl-1.5 text-sm text-ink-gray-9"
					>
						{{ draftTitle.trim() || "Untitled Query" }}
						<span class="text-xs text-ink-gray-5">unsaved</span>
					</router-link>
				</template>
			</WorkbookSidebarSection>
		</aside>

		<div class="flex min-w-0 flex-1 flex-col">
			<template v-if="activeQuery || isDraftQuery">
				<div class="flex h-10 shrink-0 items-center justify-between border-b border-outline-gray-2 px-4">
					<FormControl
						v-if="isDraftQuery"
						v-model="draftTitle"
						class="w-72"
						type="text"
						size="sm"
						placeholder="Untitled Query"
					/>
					<span v-else class="text-p-base text-ink-gray-8">{{ activeQuery.title }}</span>
					<Button
						v-if="!workbook.readOnly"
						variant="subtle"
						size="sm"
						icon-left="lucide-save"
						label="Save"
						:disabled="!canSaveQuery"
						:loading="queryApi.saving || workbook.saving"
						@click="saveQuery"
					/>
				</div>
				<QueryBuilder
					v-model:pipeline="pipeline"
					class="min-h-0 flex-1"
					:sql="sql"
					:results="results"
					:loading="queryApi.running"
					@run="runQuery"
				/>
			</template>

			<div v-else-if="activeChart" class="min-h-0 flex-1 overflow-y-auto p-5">
				<h2 class="text-lg-semibold text-ink-gray-9">{{ activeChart.title }}</h2>
				<p class="text-p-sm mt-0.5 text-ink-gray-6">
					{{ activeChart.chart_type }} · reads
					<router-link
						class="underline underline-offset-2 hover:text-ink-gray-8"
						:to="itemRoute('query', activeChart.query)"
					>
						{{ workbook.queries.find((q) => String(q.name) === String(activeChart.query))?.title || activeChart.query }}
					</router-link>
				</p>
				<div class="mt-4 rounded-lg border border-outline-gray-2 p-4">
					<Chart v-if="chartSeries.length" :series="chartSeries" />
					<p v-else class="text-p-base text-ink-gray-6">
						This chart has no series yet. Run its query and save the answer to give it one.
					</p>
				</div>
			</div>

			<div v-else-if="activeDashboard" class="min-h-0 flex-1 overflow-y-auto p-5">
				<h2 class="text-lg-semibold text-ink-gray-9">{{ activeDashboard.title }}</h2>
				<div v-if="!dashboardTiles.length" class="mt-4 rounded-lg border border-outline-gray-2 bg-surface-elevation-1 p-10 text-center">
					<p class="text-p-base text-ink-gray-6">No charts on this dashboard yet.</p>
				</div>
				<div v-else class="mt-4 grid grid-cols-12 gap-3">
					<div
						v-for="tile in dashboardTiles"
						:key="tile.i ?? tile.chart"
						class="rounded-lg border border-outline-gray-2 p-4"
						:style="{ gridColumn: `span ${Math.min(Math.max(Number(tile.w) || 6, 1), 12)}` }"
					>
						<p class="text-p-sm mb-2 text-ink-gray-7">
							{{ tileChart(tile)?.title || tile.chart }}
						</p>
						<Chart v-if="tileSeries(tile).length" :series="tileSeries(tile)" :compact="true" />
					</div>
				</div>
			</div>

			<div v-else class="min-h-0 flex-1 overflow-y-auto p-5">
				<div class="rounded-lg border border-outline-gray-2 bg-surface-elevation-1 p-10 text-center">
					<p class="text-lg-semibold text-ink-gray-8">{{ workbook.title || workbookName }}</p>
					<p class="text-p-base mt-1 text-ink-gray-6">
						{{ count(workbook.queries.length, "query", "queries") }} ·
						{{ count(workbook.charts.length, "chart") }} ·
						{{ count(workbook.dashboards.length, "dashboard") }}
					</p>
					<!-- The line used to point at Ask as somewhere else to go. It is here
					     now, so it is a button. -->
					<p class="text-p-base mt-3 text-ink-gray-6">Pick something from the sidebar, or ask for it.</p>
					<Button
						v-if="!askOpen && !workbook.readOnly"
						class="mt-3"
						variant="subtle"
						icon-left="lucide-message-circle"
						label="Ask a question"
						@click="askOpen = true"
					/>
				</div>
			</div>
		</div>

		<AskPanel
			v-if="askOpen"
			:workbook="workbookName"
			:read-only="workbook.readOnly"
			@saved="onAskSaved"
			@close="askOpen = false"
		/>
	</div>

	<WorkbookShareDialog v-if="workbook.canShare" v-model="showShareDialog" :workbook="workbook" />

	<!-- Deleting takes the queries, charts and dashboards with it
	     (`nakhoda_workbook.py:on_trash`), which is exactly the thing a
	     confirmation is for. -->
	<Dialog
		v-model="confirmingDelete"
		title="Delete workbook"
		:message="`This deletes ${workbook.title || workbookName} and everything inside it. This cannot be undone.`"
		:actions="[
			{
				label: 'Delete',
				variant: 'solid',
				theme: 'red',
				loading: busy,
				onClick: deleteWorkbook,
			},
		]"
	/>
</template>
