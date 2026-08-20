<script setup>
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { Avatar, Breadcrumbs, Button, FormControl, LoadingIndicator } from "frappe-ui";
import { List, ListHeader, ListHeaderCell, ListRow, ListCell, ListRows } from "frappe-ui/list";
import { useWorkbookStore } from "../stores/workbook.js";
import { timeAgo } from "../composables/useTimestamp.js";

/**
 * The workbook list. A workbook is the container a chat answer lands in
 * (`api/workbooks.py:save_answer`), so this page is mostly a reading surface:
 * the interesting creation path starts on Ask, not here.
 *
 * Filtering is client-side over the loaded rows, the way `QueriesPage.vue`
 * does it. `get_workbooks` accepts a `search_term`, but the list is capped at
 * 100 rows and a round trip per keystroke would be slower than the filter it
 * replaces - the endpoint's own parameter is there for the save dialog, which
 * searches a list it has not loaded.
 */
const router = useRouter();
const store = useWorkbookStore();
const searchQuery = ref("");
const creating = ref(false);

onMounted(() => {
	store.list();
});

const filtered = computed(() => {
	const term = searchQuery.value.trim().toLowerCase();
	if (!term) return store.workbooks;
	return store.workbooks.filter((w) => String(w.title || "").toLowerCase().includes(term));
});

async function createWorkbook() {
	creating.value = true;
	try {
		const name = await store.create();
		router.push({ name: "Workbook", params: { name } });
	} finally {
		creating.value = false;
	}
}

function openWorkbook(name) {
	router.push({ name: "Workbook", params: { name } });
}

/**
 * How this workbook is shared, in Insights' three states and its wording
 * (`src2/workbook/WorkbookList.vue` Access column): organisation-wide access
 * outranks a per-user list because it is the broader grant, one sharee is
 * named, and an unshared workbook says `Private` rather than showing an empty
 * cell - blank reads as data that failed to load, not as a fact about access.
 */
function accessLabel(workbook) {
	if (workbook.shared_with_organization) return "Everyone";
	const people = workbook.shared_with_names?.length || workbook.shared_with?.length || 0;
	if (!people) return "Private";
	if (people > 1) return `${people} people`;
	return workbook.shared_with_names?.[0] || workbook.shared_with[0];
}

/** The glyph carries the state; the three are never the same shape. */
function accessIcon(workbook) {
	if (workbook.shared_with_organization) return "lucide-building-2 text-ink-blue-2";
	if (!(workbook.shared_with?.length || 0)) return "lucide-lock text-ink-violet-1";
	return "lucide-shield text-ink-green-2";
}
</script>

<template>
	<header
		class="flex h-12 shrink-0 items-center justify-between border-b border-outline-gray-2 py-2.5 pl-5 pr-2"
	>
		<Breadcrumbs :items="[{ label: 'Workbooks', route: { name: 'Workbooks' } }]" />
		<Button
			variant="solid"
			theme="gray"
			icon-left="lucide-plus"
			label="New Workbook"
			:loading="creating"
			@click="createWorkbook"
		/>
	</header>

	<div class="flex min-h-0 flex-1 flex-col gap-3 overflow-auto px-5 py-3">
		<div v-if="store.loading" class="flex flex-1 items-center justify-center">
			<LoadingIndicator class="size-6" />
		</div>
		<div
			v-else-if="store.error"
			class="rounded-sm border border-outline-red-2 bg-surface-red-1 p-4 text-sm text-ink-red-6"
		>
			Could not load workbooks.
		</div>
		<template v-else-if="store.workbooks.length">
			<div class="flex gap-2">
				<FormControl
					v-model="searchQuery"
					class="w-64"
					type="text"
					placeholder="Search by title"
				>
					<template #prefix>
						<span class="lucide-search size-4 text-ink-gray-5" aria-hidden="true" />
					</template>
				</FormControl>
			</div>

			<List
				v-if="filtered.length"
				class="min-h-0 flex-1"
				:columns="['minmax(0,4fr)', 'minmax(0,2fr)', 'minmax(0,1.5fr)', 'minmax(0,2fr)', 'minmax(0,2fr)']"
			>
				<ListHeader>
					<ListHeaderCell
						v-for="col in ['Title', 'Access', 'Views', 'Owner', 'Modified']"
						:key="col"
					>
						{{ col }}
					</ListHeaderCell>
				</ListHeader>
				<ListRows :items="filtered" row-key="name">
					<template #default="{ item, value }">
						<ListRow :value="value" @click="openWorkbook(item.name)">
							<ListCell class="text-ink-gray-8">{{ item.title }}</ListCell>
							<ListCell>
								<div class="flex min-w-0 items-center gap-1.5">
									<span :class="accessIcon(item)" class="size-3.5 shrink-0" aria-hidden="true" />
									<span class="truncate">{{ accessLabel(item) }}</span>
								</div>
							</ListCell>
							<ListCell>
								<div class="flex items-center gap-1">
									<span class="lucide-eye size-3.5 shrink-0 text-ink-gray-5" aria-hidden="true" />
									<span class="font-mono text-sm text-ink-gray-7">{{ item.views ?? 0 }}</span>
								</div>
							</ListCell>
							<ListCell>
								<div class="flex min-w-0 items-center gap-2">
									<Avatar size="md" :label="item.owner_name || item.owner" />
									<span class="truncate text-base">{{ item.owner_name || item.owner }}</span>
								</div>
							</ListCell>
							<ListCell :title="item.modified">{{ timeAgo(item.modified) }}</ListCell>
						</ListRow>
					</template>
				</ListRows>
			</List>
			<div
				v-else
				class="mt-10 rounded-lg border border-outline-gray-2 bg-surface-elevation-1 p-10 text-center"
			>
				<p class="text-p-base text-ink-gray-6">No workbooks match “{{ searchQuery }}”.</p>
			</div>
		</template>
		<div
			v-else
			class="mt-10 rounded-lg border border-outline-gray-2 bg-surface-elevation-1 p-10 text-center"
		>
			<p class="text-p-base text-ink-gray-6">
				No workbooks yet. A workbook is a named collection of queries, charts, and dashboards -
				shareable, and the place an answer goes when you save one from Ask.
			</p>
			<Button
				class="mt-4"
				variant="solid"
				theme="gray"
				icon-left="lucide-plus"
				label="New Workbook"
				:loading="creating"
				@click="createWorkbook"
			/>
		</div>
	</div>
</template>
