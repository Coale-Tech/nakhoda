<script setup>
import { computed, onMounted, ref } from "vue";
import { Badge, Button, Dialog, Dropdown, FormControl, LoadingIndicator } from "frappe-ui";
import { List, ListHeader, ListHeaderCell, ListRow, ListCell, ListRows } from "frappe-ui/list";
import { useSemantic } from "../composables/useSemantic.js";
import { timeAgo } from "../composables/useTimestamp.js";

/**
 * The Semantic Model tab: what a person wrote about this site's documents, and
 * what the site wrote about itself.
 *
 * The design contract for this surface is "coverage of the auto-derivation;
 * per-entity grain warnings; the derived `status` domain shown verbatim"
 * (`docs/design/14-frontend-design.md` §2). All three are here, and each is a
 * measurement rather than a decoration:
 *
 * - **Coverage** is four counts from `api/semantic.coverage`: documents this
 *   site uses, documents modelled, documents a person has written on, and
 *   documents carrying synonyms. The last is the one that moves retrieval -
 *   `semantic/retrieval.py`'s `CURATED = 3.0` weight only fires on curated
 *   terms, and it took recall from 37/40 to 40/40 on this bench.
 * - **Grain warnings** are per row: a child table whose parents are all absent
 *   can be joined to nothing and is dropped from the index, so it is flagged
 *   amber here rather than silently ranked and skipped.
 * - **The domain verbatim** is the `Domain` column of the editor's column list:
 *   `one of: Draft, Submitted, Cancelled` is exactly the string the model is
 *   handed, not a paraphrase of it.
 *
 * List in the tab, editor in a Dialog - Insights' own shape for a settings tab
 * that holds many rows (`src2/settings/UsersSettings.vue`), and the reason the
 * list omits `description`: 428 essays is not a payload a search box needs.
 *
 * The generated fields are read-only on purpose. Editing a row count would not
 * change the row count; it would make the number wrong until the next migrate.
 */
const store = useSemantic();

const searchQuery = ref("");
const curatedOnly = ref(false);

const showEditor = ref(false);
const detail = ref(null);
const detailLoading = ref(false);
const columnFilter = ref("");

/** The editor's own copy: nothing is written until Save. */
const form = ref({ description: "", synonyms: "", fieldSynonyms: {} });
const original = ref({ description: "", synonyms: "" });

onMounted(() => store.load().catch(() => {}));

const filtered = computed(() => {
	const needle = searchQuery.value.trim().toLowerCase();
	return store.models.filter((row) => {
		if (curatedOnly.value && !row.curated) return false;
		if (!needle) return true;
		return (
			(row.doctype_name || "").toLowerCase().includes(needle) ||
			(row.label || "").toLowerCase().includes(needle) ||
			(row.synonyms || "").toLowerCase().includes(needle)
		);
	});
});

/**
 * A child table with no reachable parent. `retrieval.Table.requires()` returns
 * its parents, and the selector will not put a table in the budget it cannot
 * join - so this row is costing schema tokens for an answer it can never give.
 */
function orphaned(row) {
	return Boolean(row.is_child) && !(row.parent_doctypes || "").trim();
}

const columns = computed(() => {
	const rows = detail.value?.fields || [];
	const needle = columnFilter.value.trim().toLowerCase();
	if (!needle) return rows;
	return rows.filter(
		(c) =>
			(c.fieldname || "").toLowerCase().includes(needle) ||
			(c.label || "").toLowerCase().includes(needle) ||
			(c.synonyms || "").toLowerCase().includes(needle),
	);
});

const isDirty = computed(() => {
	if (!detail.value) return false;
	if ((form.value.description || "") !== (original.value.description || "")) return true;
	if ((form.value.synonyms || "") !== (original.value.synonyms || "")) return true;
	return Object.keys(form.value.fieldSynonyms).length > 0;
});

async function open(row) {
	showEditor.value = true;
	detailLoading.value = true;
	detail.value = null;
	columnFilter.value = "";
	try {
		const doc = await store.get(row.name);
		detail.value = doc;
		form.value = {
			description: doc.description || "",
			synonyms: doc.synonyms || "",
			fieldSynonyms: {},
		};
		original.value = { description: doc.description || "", synonyms: doc.synonyms || "" };
	} finally {
		detailLoading.value = false;
	}
}

/**
 * Only columns the curator touched are sent. The backend rejects a fieldname
 * the document no longer has, so a form left open across a migration fails
 * loudly instead of half-writing.
 */
function onColumnSynonyms(column, value) {
	column.synonyms = value;
	form.value.fieldSynonyms[column.fieldname] = value;
}

/**
 * Both write paths land their failure on the store (`saveError` / `error`) and
 * stop there: a rethrow past this point is an unhandled rejection, and the
 * editor already renders the backend's message beside Save. The stale-column
 * refusal is the case that matters - the row must stay on screen, unsaved and
 * unchanged, so the curator can reopen it rather than lose what they typed.
 */
async function save() {
	if (!detail.value) return;
	let fresh;
	try {
		fresh = await store.save(detail.value.name, {
			description: form.value.description,
			synonyms: form.value.synonyms,
			fieldSynonyms: Object.keys(form.value.fieldSynonyms).length ? form.value.fieldSynonyms : null,
		});
	} catch {
		return;
	}
	detail.value = fresh;
	form.value = {
		description: fresh.description || "",
		synonyms: fresh.synonyms || "",
		fieldSynonyms: {},
	};
	original.value = { description: fresh.description || "", synonyms: fresh.synonyms || "" };
}

/** Queued, not done: the pass runs in a worker (`api/semantic.regenerate`). */
const notice = ref(null);

async function regenerate(seed) {
	notice.value = null;
	let result;
	try {
		result = await store.regenerate({ seed });
	} catch {
		notice.value = { failed: true, text: store.error?.message || "Could not start the pass." };
		return;
	}
	notice.value = {
		failed: false,
		text: result?.queued
			? seed
				? `Queued: re-deriving ${result.documents} documents.`
				: "Queued: re-deriving every described document."
			: "Already running.",
	};
}

const regenerateOptions = computed(() => [
	{
		label: "Refresh described documents",
		onClick: () => regenerate(false),
	},
	{
		label: "Seed every used document",
		onClick: () => regenerate(true),
	},
]);
</script>

<template>
	<div class="flex h-full w-full min-h-0 flex-col gap-4 overflow-hidden p-8">
		<div class="flex shrink-0 items-start justify-between gap-3">
			<div>
				<h1 class="text-xl font-semibold text-ink-gray-9">Semantic Model</h1>
				<p class="mt-1 text-sm text-ink-gray-6">
					What the model is told about each document. Names a person writes here are read
					back by retrieval.
				</p>
			</div>
			<Dropdown :options="regenerateOptions" placement="right">
				<Button variant="outline" :loading="store.regenerating" label="Regenerate">
					<template #suffix>
						<span class="lucide-chevron-down size-4" aria-hidden="true" />
					</template>
				</Button>
			</Dropdown>
		</div>

		<div v-if="store.loading && !store.models.length" class="flex flex-1 items-center justify-center">
			<LoadingIndicator class="size-6" />
		</div>
		<div
			v-else-if="store.error && !store.models.length"
			class="rounded-sm border border-outline-red-2 bg-surface-red-1 p-4 text-sm text-ink-red-6"
		>
			Could not load the semantic model.
		</div>

		<template v-else>
			<div v-if="store.coverage" class="grid shrink-0 grid-cols-4 gap-3">
				<div class="rounded-lg border border-outline-gray-1 bg-surface-gray-1 p-3.5">
					<p class="text-xs font-medium uppercase tracking-wide text-ink-gray-6">Documents Used</p>
					<p class="mt-1 text-lg font-semibold text-ink-gray-9">{{ store.coverage.used }}</p>
				</div>
				<div class="rounded-lg border border-outline-gray-1 bg-surface-gray-1 p-3.5">
					<p class="text-xs font-medium uppercase tracking-wide text-ink-gray-6">Modelled</p>
					<p class="mt-1 text-lg font-semibold text-ink-gray-9">
						{{ store.coverage.modelled
						}}<span class="text-sm font-normal text-ink-gray-5"> / {{ store.coverage.used }}</span>
					</p>
				</div>
				<div class="rounded-lg border border-outline-gray-1 bg-surface-gray-1 p-3.5">
					<p class="text-xs font-medium uppercase tracking-wide text-ink-gray-6">Written By Hand</p>
					<p class="mt-1 text-lg font-semibold text-ink-gray-9">{{ store.coverage.curated }}</p>
				</div>
				<div class="rounded-lg border border-outline-gray-1 bg-surface-gray-1 p-3.5">
					<p class="text-xs font-medium uppercase tracking-wide text-ink-gray-6">With Synonyms</p>
					<p class="mt-1 text-lg font-semibold text-ink-gray-9">
						{{ store.coverage.with_synonyms }}
					</p>
				</div>
			</div>

			<div
				v-if="notice"
				class="shrink-0 rounded-sm border p-3 text-sm"
				:class="
					notice.failed
						? 'border-outline-red-2 bg-surface-red-1 text-ink-red-6'
						: 'border-outline-blue-1 bg-surface-blue-1 text-ink-blue-6'
				"
			>
				{{ notice.text }}
			</div>

			<div class="flex shrink-0 items-center gap-3 overflow-visible">
				<FormControl placeholder="Search documents" v-model="searchQuery" class="w-72">
					<template #prefix>
						<span class="lucide-search size-4 text-ink-gray-4" aria-hidden="true" />
					</template>
				</FormControl>
				<FormControl type="checkbox" v-model="curatedOnly" label="Written by hand only" />
				<span class="ml-auto text-sm text-ink-gray-5">{{ filtered.length }} shown</span>
			</div>

			<List
				v-if="filtered.length"
				class="min-h-0 flex-1 overflow-y-auto"
				:columns="['minmax(0,1.4fr)', 'minmax(0,1.2fr)', '6rem', '6rem', 'minmax(0,1fr)', '9rem']"
			>
				<ListHeader>
					<ListHeaderCell>Document</ListHeaderCell>
					<ListHeaderCell>One Row Is</ListHeaderCell>
					<ListHeaderCell>Rows</ListHeaderCell>
					<ListHeaderCell>Charts</ListHeaderCell>
					<ListHeaderCell>Synonyms</ListHeaderCell>
					<ListHeaderCell>Derived</ListHeaderCell>
				</ListHeader>
				<ListRows :items="filtered" row-key="name">
					<template #default="{ item, value }">
						<ListRow :value="value" :onClick="() => open(item)">
							<ListCell>
								<div class="flex min-w-0 items-center gap-2">
									<span class="truncate text-base">{{ item.doctype_name }}</span>
									<Badge v-if="item.curated" theme="green" variant="subtle">Written</Badge>
									<Badge v-if="orphaned(item)" theme="orange" variant="subtle" title="A child table with no reachable parent is dropped from the index">
										No parent
									</Badge>
								</div>
							</ListCell>
							<ListCell>
								<span class="truncate text-p-sm text-ink-gray-6">{{ item.grain }}</span>
							</ListCell>
							<ListCell>
								<span class="text-p-sm text-ink-gray-7">{{ item.row_count?.toLocaleString() }}</span>
							</ListCell>
							<ListCell>
								<span class="text-p-sm text-ink-gray-7">{{ item.reporting_count }}</span>
							</ListCell>
							<ListCell>
								<span v-if="item.synonyms" class="truncate text-p-sm text-ink-gray-7">
									{{ item.synonyms }}
								</span>
								<span v-else class="text-p-sm text-ink-gray-4">&mdash;</span>
							</ListCell>
							<ListCell>
								<span class="text-p-sm text-ink-gray-5">{{ timeAgo(item.generated_on) }}</span>
							</ListCell>
						</ListRow>
					</template>
				</ListRows>
			</List>
			<div
				v-else
				class="flex min-h-0 flex-1 items-center justify-center rounded-lg border border-outline-gray-2 text-p-base text-ink-gray-5"
			>
				{{
					store.models.length
						? "No document matches this search."
						: "Nothing modelled yet. Regenerate → Seed every used document."
				}}
			</div>
		</template>
	</div>

	<Dialog v-model="showEditor" size="3xl" bare>
		<div class="flex flex-col" :style="{ maxHeight: 'calc(100vh - 14rem)' }">
			<div class="flex shrink-0 items-start justify-between gap-3 border-b border-outline-gray-2 p-5">
				<div class="min-w-0">
					<h2 class="truncate text-lg font-semibold text-ink-gray-9">
						{{ detail?.doctype_name || "Document" }}
					</h2>
					<p v-if="detail" class="mt-0.5 text-p-sm text-ink-gray-6">{{ detail.grain }}</p>
				</div>
				<Badge v-if="detail?.curated" theme="green" variant="subtle" size="md">Written by hand</Badge>
				<Badge v-else-if="detail" theme="gray" variant="subtle" size="md">Generated</Badge>
			</div>

			<div v-if="detailLoading" class="flex h-40 items-center justify-center">
				<LoadingIndicator class="size-6" />
			</div>

			<div v-else-if="detail" class="flex min-h-0 flex-1 flex-col gap-5 overflow-y-auto p-5">
				<div class="grid grid-cols-4 gap-3">
					<div class="rounded-lg border border-outline-gray-1 bg-surface-gray-1 p-3">
						<p class="text-xs font-medium uppercase tracking-wide text-ink-gray-6">Rows</p>
						<p class="mt-1 text-base font-medium text-ink-gray-9">
							{{ detail.row_count?.toLocaleString() }}
						</p>
					</div>
					<div class="rounded-lg border border-outline-gray-1 bg-surface-gray-1 p-3">
						<p class="text-xs font-medium uppercase tracking-wide text-ink-gray-6">Charts</p>
						<p class="mt-1 text-base font-medium text-ink-gray-9">{{ detail.reporting_count }}</p>
					</div>
					<div class="rounded-lg border border-outline-gray-1 bg-surface-gray-1 p-3">
						<p class="text-xs font-medium uppercase tracking-wide text-ink-gray-6">Never Filled</p>
						<p class="mt-1 text-base font-medium text-ink-gray-9">
							{{ detail.empty_column_count }}<span class="text-sm font-normal text-ink-gray-5">
								/ {{ detail.fields.length }}</span
							>
						</p>
					</div>
					<div class="rounded-lg border border-outline-gray-1 bg-surface-gray-1 p-3">
						<p class="text-xs font-medium uppercase tracking-wide text-ink-gray-6">Schema Cost</p>
						<p class="mt-1 text-base font-medium text-ink-gray-9">
							{{ detail.token_cost?.toLocaleString() }}
							<span class="text-sm font-normal text-ink-gray-5">tokens</span>
						</p>
					</div>
				</div>

				<div
					v-if="detail.is_child && !(detail.parent_doctypes || '').trim()"
					class="rounded-sm border border-outline-amber-2 bg-surface-amber-1 p-3 text-p-sm text-ink-amber-3"
				>
					This is a child table and no parent document was found for it. A child cannot be
					queried on its own, so retrieval drops it - describing it will not make it reachable.
				</div>
				<div v-else-if="detail.is_child" class="text-p-sm text-ink-gray-6">
					Hangs off: <span class="text-ink-gray-8">{{ detail.parent_doctypes }}</span>
				</div>

				<div>
					<label class="mb-1.5 block text-p-sm font-medium text-ink-gray-8">Description</label>
					<FormControl
						type="textarea"
						:rows="5"
						v-model="form.description"
						placeholder="What this document is, in the words the business uses for it."
					/>
					<p class="mt-1.5 text-p-sm text-ink-gray-5">
						Generated from the schema until someone writes here. Once edited, migrations
						leave it alone.
					</p>
				</div>

				<div>
					<label class="mb-1.5 block text-p-sm font-medium text-ink-gray-8">Synonyms</label>
					<FormControl v-model="form.synonyms" placeholder="revenue, turnover, topline, billings" />
					<p class="mt-1.5 text-p-sm text-ink-gray-5">
						Words a question may use that the schema never says. These carry the heaviest
						weight in retrieval.
					</p>
				</div>

				<div class="min-h-0">
					<div class="mb-2 flex items-center justify-between gap-3">
						<label class="text-p-sm font-medium text-ink-gray-8">Columns</label>
						<FormControl placeholder="Filter columns" v-model="columnFilter" class="w-56">
							<template #prefix>
								<span class="lucide-search size-4 text-ink-gray-4" aria-hidden="true" />
							</template>
						</FormControl>
					</div>
					<div class="overflow-hidden rounded-lg border border-outline-gray-2">
						<div
							class="grid grid-cols-[minmax(0,1fr)_7rem_minmax(0,1.3fr)_minmax(0,1fr)] gap-2 border-b border-outline-gray-2 bg-surface-gray-2 px-3 py-2 text-xs font-medium uppercase tracking-wide text-ink-gray-6"
						>
							<span>Column</span>
							<span>Type</span>
							<span>Domain</span>
							<span>Synonyms</span>
						</div>
						<div class="max-h-72 overflow-y-auto">
							<div
								v-for="column in columns"
								:key="column.fieldname"
								class="grid grid-cols-[minmax(0,1fr)_7rem_minmax(0,1.3fr)_minmax(0,1fr)] items-center gap-2 border-b border-outline-gray-1 px-3 py-1.5 last:border-b-0"
							>
								<div class="flex min-w-0 items-center gap-1.5">
									<span class="truncate text-p-sm text-ink-gray-8">{{
										column.label || column.fieldname
									}}</span>
									<Badge
										v-if="column.empty"
										theme="gray"
										variant="subtle"
										title="No row on this site has a value here - retrieval prunes it"
									>
										empty
									</Badge>
								</div>
								<span class="truncate text-p-sm text-ink-gray-6">{{ column.fieldtype }}</span>
								<span class="truncate text-p-sm text-ink-gray-6" :title="column.domain || ''">
									{{ column.join_target ? `→ ${column.join_target}` : column.domain || "—" }}
								</span>
								<FormControl
									size="sm"
									:modelValue="column.synonyms"
									placeholder="—"
									@update:modelValue="(value) => onColumnSynonyms(column, value)"
								/>
							</div>
						</div>
					</div>
				</div>
			</div>

			<div class="flex shrink-0 items-center justify-between gap-3 border-t border-outline-gray-2 p-5">
				<p v-if="store.saveError" class="truncate text-p-sm text-ink-red-6">
					{{ store.saveError.message || "Could not save." }}
				</p>
				<p v-else-if="detail" class="text-p-sm text-ink-gray-5">
					Derived {{ timeAgo(detail.generated_on) }}
				</p>
				<span v-else />
				<div class="flex gap-2">
					<Button label="Close" variant="subtle" @click="showEditor = false" />
					<Button
						label="Save"
						variant="solid"
						theme="gray"
						:disabled="!isDirty"
						:loading="store.saving"
						@click="save()"
					/>
				</div>
			</div>
		</div>
	</Dialog>
</template>
