<script setup>
import { computed, ref, watch } from "vue";
import { Avatar, Button, Dialog, Dropdown, FormControl, LoadingIndicator } from "frappe-ui";
import { useSessionStore } from "../stores/session.js";

/**
 * Manage Access for one workbook, ported from Insights'
 * `src2/workbook/WorkbookShareDialog.vue`.
 *
 * The shape of the thing being edited is the backend's, not the dialog's:
 * `get_share_permissions` returns `{user_permissions: [{user, full_name, read,
 * write}], organization_access: null|"view"|"edit"}` and
 * `update_share_permissions` reconciles the list to exactly what is sent
 * (`api/workbooks.py`). Sent state wins, so the dialog holds a *draft* of the
 * whole list and submits all of it - a patch could never express a removal.
 *
 * Three deliberate differences from Insights:
 *
 * - Insights keeps a global user store and renders every user in the site;
 *   this asks the server per search (`list_shareable_users`), which gates on
 *   `share` for this workbook rather than on a role. A workbook's owner should
 *   not need the user directory to share one document.
 * - Removal is a row action ("Remove"), not a third value in the access
 *   dropdown that leaves a ghost row behind: dropping the key is what the
 *   payload means, so the row goes with it.
 * - The owner is never listed as a permission. Their access is structural and
 *   the endpoint skips a docshare naming them, so a row for the owner would be
 *   a control that cannot do anything.
 */
const props = defineProps({
	workbook: { type: Object, required: true },
});

const show = defineModel({ required: true, default: false });

const session = useSessionStore();

const loading = ref(false);
const saving = ref(false);
const error = ref(null);

/** `{ [user]: "view" | "edit" }` - the draft, and what was loaded. */
const draft = ref({});
const loaded = ref({});
const names = ref({});
const images = ref({});

const orgAccess = ref(null);
const loadedOrgAccess = ref(null);

const searchTerm = ref("");
const candidates = ref([]);
const searching = ref(false);
const searched = ref(false);

watch(show, (open) => (open ? load() : reset()), { immediate: true });

function reset() {
	draft.value = {};
	loaded.value = {};
	orgAccess.value = null;
	loadedOrgAccess.value = null;
	searchTerm.value = "";
	candidates.value = [];
	searched.value = false;
	error.value = null;
}

async function load() {
	loading.value = true;
	error.value = null;
	try {
		const permissions = await props.workbook.share();
		const next = {};
		for (const row of permissions?.user_permissions || []) {
			next[row.user] = row.write ? "edit" : "view";
			names.value[row.user] = row.full_name || row.user;
		}
		draft.value = { ...next };
		loaded.value = { ...next };
		orgAccess.value = permissions?.organization_access || null;
		loadedOrgAccess.value = orgAccess.value;
	} catch (e) {
		error.value = e;
	} finally {
		loading.value = false;
	}
}

/**
 * Searched on demand rather than on every keystroke of a prefetched list: the
 * candidate set is every user of the app, which is not a size this dialog can
 * assume anything about.
 */
async function search() {
	searching.value = true;
	try {
		const rows = await props.workbook.shareableUsers(searchTerm.value.trim());
		candidates.value = rows.filter((row) => !(row.user in draft.value));
		for (const row of rows) {
			names.value[row.user] = row.full_name;
			if (row.user_image) images.value[row.user] = row.user_image;
		}
	} finally {
		// Recorded whatever came back, including nothing: an empty result and an
		// unrun search look identical otherwise, so the dialog would answer a
		// search with silence and leave "nobody matches" indistinguishable from
		// "this is broken".
		searched.value = true;
		searching.value = false;
	}
}

function grant(user) {
	draft.value = { ...draft.value, [user]: "view" };
	candidates.value = candidates.value.filter((row) => row.user !== user);
}

function setAccess(user, access) {
	draft.value = { ...draft.value, [user]: access };
}

function revoke(user) {
	const next = { ...draft.value };
	delete next[user];
	draft.value = next;
}

const rows = computed(() =>
	Object.keys(draft.value)
		.sort((a, b) => (names.value[a] || a).localeCompare(names.value[b] || b))
		.map((user) => ({
			user,
			fullName: names.value[user] || user,
			image: images.value[user] || "",
			access: draft.value[user],
		})),
);

const isDirty = computed(
	() =>
		JSON.stringify(draft.value) !== JSON.stringify(loaded.value) ||
		orgAccess.value !== loadedOrgAccess.value,
);

const orgLabel = computed(() => {
	if (orgAccess.value === "edit") return "Can edit";
	if (orgAccess.value === "view") return "Can view";
	return "Disabled";
});

const orgOptions = computed(() => [
	{ label: "Disabled", onClick: () => (orgAccess.value = null) },
	{ label: "Can view", onClick: () => (orgAccess.value = "view") },
	{ label: "Can edit", onClick: () => (orgAccess.value = "edit") },
]);

function accessOptions(user) {
	return [
		{ label: "Can view", onClick: () => setAccess(user, "view") },
		{ label: "Can edit", onClick: () => setAccess(user, "edit") },
		{ label: "Remove", onClick: () => revoke(user) },
	];
}

async function save() {
	saving.value = true;
	error.value = null;
	try {
		await props.workbook.updateShare(
			Object.entries(draft.value).map(([user, access]) => ({
				user,
				read: 1,
				write: access === "edit" ? 1 : 0,
			})),
			orgAccess.value,
		);
		// The list page reads share state from the row; the open document
		// carries `can_share`, which a revoked share can change.
		await props.workbook.load();
		show.value = false;
	} catch (e) {
		error.value = e;
	} finally {
		saving.value = false;
	}
}
</script>

<template>
	<!-- Flat props and `#default`: this frappe-ui (1.0.0-beta.29) deprecates
	     `options` and `#body-content`, and the deprecated spelling warns on
	     every open (`Dialog.vue:234,248`). -->
	<Dialog v-model="show" title="Manage Access" size="lg">
		<template #default>
			<div v-if="loading" class="flex h-40 items-center justify-center">
				<LoadingIndicator class="size-6" />
			</div>

			<div v-else class="flex flex-col gap-3 text-base">
				<div class="flex items-center gap-3 rounded-sm border border-outline-gray-2 px-3 py-2">
					<span class="lucide-building-2 size-5 text-ink-blue-3" aria-hidden="true" />
					<div class="flex flex-1 flex-col">
						<span class="text-p-base font-medium text-ink-gray-8">Organization access</span>
						<span class="text-p-sm text-ink-gray-6">
							{{
								orgAccess
									? `Everyone on this site can ${orgAccess} this workbook`
									: "Only people listed below have access"
							}}
						</span>
					</div>
					<Dropdown
						:options="orgOptions"
						:button="{ label: orgLabel, iconRight: 'chevron-down', variant: 'outline' }"
					/>
				</div>

				<form class="flex gap-2" @submit.prevent="search">
					<FormControl
						v-model="searchTerm"
						class="flex-1"
						type="text"
						placeholder="Search people by name or email"
						aria-label="Search people"
					/>
					<Button variant="subtle" label="Search" :loading="searching" @click="search" />
				</form>

				<div v-if="candidates.length" class="flex flex-col gap-1">
					<button
						v-for="row in candidates"
						:key="row.user"
						type="button"
						class="flex items-center gap-2 rounded-sm px-2 py-1.5 text-left hover:bg-surface-gray-2"
						@click="grant(row.user)"
					>
						<Avatar size="sm" :label="row.full_name" :image="row.user_image" />
						<span class="text-p-sm flex-1 truncate text-ink-gray-8">{{ row.full_name }}</span>
						<span class="text-p-xs text-ink-gray-5">{{ row.user }}</span>
					</button>
				</div>
				<p v-else-if="searched" class="text-p-sm px-2 text-ink-gray-5">
					{{
						searchTerm.trim()
							? `Nobody matches “${searchTerm.trim()}”. Everyone already listed is filtered out.`
							: "No other users of this app yet. Invite someone first, then share with them."
					}}
				</p>

				<div class="flex flex-col gap-1">
					<div v-for="row in rows" :key="row.user" class="flex items-center gap-2 py-1">
						<Avatar size="lg" :label="row.fullName" :image="row.image" />
						<div class="flex min-w-0 flex-1 flex-col">
							<span class="text-p-sm truncate text-ink-gray-8">{{ row.fullName }}</span>
							<span class="text-p-xs truncate text-ink-gray-5">{{ row.user }}</span>
						</div>
						<Button
							v-if="row.user === session.user"
							variant="ghost"
							label="You"
							disabled
							class="shrink-0"
						/>
						<Dropdown
							v-else
							class="shrink-0"
							align="end"
							:options="accessOptions(row.user)"
							:button="{
								label: row.access === 'edit' ? 'Can edit' : 'Can view',
								iconRight: 'chevron-down',
								variant: 'ghost',
							}"
						/>
					</div>

					<div
						v-if="!rows.length"
						class="rounded-sm border border-dashed border-outline-gray-2 py-6 text-center"
					>
						<span class="text-p-sm text-ink-gray-6">
							{{
								orgAccess
									? `Everyone on this site can ${orgAccess} this workbook`
									: "Not shared with anyone yet"
							}}
						</span>
					</div>
				</div>

				<p v-if="error" class="text-p-sm text-ink-red-6">
					{{ error.message || "Could not update access." }}
				</p>
			</div>
		</template>

		<template #actions>
			<Button
				variant="solid"
				label="Save"
				:disabled="!isDirty"
				:loading="saving"
				@click="save"
			/>
		</template>
	</Dialog>
</template>
