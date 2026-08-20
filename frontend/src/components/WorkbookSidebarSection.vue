<script setup>
import { computed, nextTick, ref } from "vue";
import { Button } from "frappe-ui";

/**
 * One collection in the workbook sidebar - Queries, Charts or Dashboards -
 * with its folders, its rows, and every affordance those rows have.
 *
 * Ported from Insights' pair of components (`src2/workbook/`
 * `WorkbookSidebarFolders.vue` for queries/charts, `WorkbookSidebarListSection.vue`
 * for dashboards). They are one component here because the only difference
 * between them upstream is that dashboards cannot be foldered, and this app's
 * `create_folder` takes a `folder_type` for all three - so the split would be a
 * capability this backend does not lack.
 *
 * Two structural facts drive the shape:
 *
 * - A folder is a *label*, not a parent. `move_item_to_folder` writes the
 *   folder's **title** into the item's `folder` field (`api/workbooks.py:397`),
 *   so grouping is a string match and a folder cannot nest. The folder list
 *   drives the groups rather than the items' own labels, because an empty
 *   folder still has to appear - otherwise creating one looks like a no-op.
 *
 * - Ordering is server-side (`update_sort_orders`), one row per item, so a drag
 *   emits the whole section's new order rather than a swap. `sort_order` is
 *   recomputed densely from the dropped arrangement: sparse or duplicate values
 *   survive a round trip but make the next drag's arithmetic guesswork.
 *
 * Inline editing rather than dialogs, and no `window.prompt`: a prompt cannot be
 * styled, cannot be tested by role, and loses the row's context.
 */
const props = defineProps({
	type: { type: String, required: true },
	label: { type: String, required: true },
	items: { type: Array, required: true },
	folders: { type: Array, default: () => [] },
	readOnly: { type: Boolean, default: false },
	isActive: { type: Function, required: true },
	/**
	 * Rows the caller renders through `trailing` that this component cannot see.
	 * `$slots.trailing` is truthy whenever the parent *passes* the slot, even
	 * when it renders nothing, so it cannot decide whether the section is empty.
	 */
	extraRows: { type: Number, default: 0 },
	/**
	 * Separate from `readOnly`: a chart reads a query, so with no queries there
	 * is nothing to chart and `add_chart` would refuse
	 * (`nakhoda_chart.py:validate_query_workbook`). That is a missing
	 * prerequisite, not a missing permission, and it must not also strip the
	 * folder and row affordances a writer still has.
	 */
	canAdd: { type: Boolean, default: true },
	/** In flight: `add_chart` and `add_dashboard` are server round trips. */
	adding: { type: Boolean, default: false },
	/**
	 * Whether the server can file and order this collection. False for
	 * dashboards: `Nakhoda Dashboard` has neither a `folder` nor a `sort_order`
	 * field, and `_item_doctype` knows only queries and charts
	 * (`api/workbooks.py`), so a folder button here would raise "Unknown item
	 * type" on use. Insights draws the same line - its folder sidebar serves
	 * queries and charts, dashboards get the plain list.
	 */
	organizable: { type: Boolean, default: true },
	/**
	 * A row's destination, as a router location. Rows are links rather than
	 * buttons because the open item *is* the route (`router.js`): a link gives
	 * the browser's own affordances - middle-click, Cmd-click, a visible target
	 * in the status bar - which a click handler emitting an event cannot.
	 * Insights passes the same thing (`route(row)` in `WorkbookSidebarFolders`).
	 */
	route: { type: Function, required: true },
});

const emit = defineEmits([
	"add",
	"remove",
	"rename",
	"move",
	"reorder",
	"create-folder",
	"rename-folder",
	"delete-folder",
	"toggle-folder",
]);

const emptyMessage = computed(() => `No ${props.label.toLowerCase()}`);

const byOrder = (a, b) => (Number(a.sort_order) || 0) - (Number(b.sort_order) || 0);

const sectionFolders = computed(() =>
	props.organizable ? props.folders.filter((f) => f.type === props.type).slice().sort(byOrder) : [],
);

const rootItems = computed(() =>
	props.organizable
		? props.items.filter((item) => !item.folder).slice().sort(byOrder)
		: props.items.slice(),
);

function itemsIn(folder) {
	return props.items.filter((item) => item.folder === folder.title).slice().sort(byOrder);
}

/**
 * `move_item_to_folder` takes a folder *document name* and stores its *title*
 * (`api/workbooks.py`), while an item's own `folder` field holds the title. So
 * every hop from an item back to a folder has to go through this lookup - and
 * sending the title the item carries, which reads plausibly, silently resolves
 * to no folder at all.
 */
function folderNameFor(title) {
	if (!title) return null;
	return sectionFolders.value.find((f) => f.title === title)?.name ?? null;
}

const isEmpty = computed(
	() => !props.items.length && !sectionFolders.value.length && !props.extraRows,
);

// -- inline editing ---------------------------------------------------------

/** One editor at a time, keyed by what is being edited. */
const editing = ref(null); // { kind: "item" | "folder" | "new-folder", key: string }
const draft = ref("");

function isEditing(kind, key) {
	return editing.value?.kind === kind && editing.value?.key === key;
}

async function startEdit(kind, key, seed = "") {
	editing.value = { kind, key };
	draft.value = seed;
	await nextTick();
	const el = document.querySelector(`[data-editor="${kind}:${key}"]`);
	if (el) {
		el.focus();
		el.select?.();
	}
}

function cancelEdit() {
	editing.value = null;
	draft.value = "";
}

/**
 * Commit is idempotent and blur-safe: Enter commits and clears the editor, and
 * the blur that Enter causes then finds nothing to commit. Without the guard a
 * rename fires twice, and the second one races the refetch the first triggered.
 */
function commitEdit(kind, key, current = "") {
	if (!isEditing(kind, key)) return;
	const title = draft.value.trim();
	cancelEdit();
	if (!title || title === current) return;
	if (kind === "item") emit("rename", key, title);
	else if (kind === "folder") emit("rename-folder", key, title);
	else if (kind === "new-folder") emit("create-folder", title);
}

// -- drag and drop ----------------------------------------------------------

/**
 * Module-free drag state: the payload travels in `dataTransfer`, but Safari and
 * Firefox refuse to read it during `dragover` (only on `drop`), so the same
 * facts are mirrored in a ref to decide whether a hovered target is legal.
 */
const dragging = ref(null); // { type, name }
const dropTarget = ref(null); // { kind: "item" | "folder" | "root", key, edge }

function onDragStart(event, item) {
	if (props.readOnly) return;
	dragging.value = { type: props.type, name: String(item.name) };
	event.dataTransfer.effectAllowed = "move";
	event.dataTransfer.setData("text/plain", JSON.stringify(dragging.value));
}

function onDragEnd() {
	dragging.value = null;
	dropTarget.value = null;
}

/** A drag from another section is not a reorder of this one. */
function dragIsMine() {
	return Boolean(dragging.value) && dragging.value.type === props.type;
}

function onDragOverItem(event, item) {
	if (!dragIsMine() || dragging.value.name === String(item.name)) return;
	event.preventDefault();
	// The section itself is a root drop zone, so an unstopped `dragover` from a
	// row bubbles up and overwrites this target with "root" on every frame -
	// the edge indicator would never show and every drop would unfile.
	event.stopPropagation();
	const box = event.currentTarget.getBoundingClientRect();
	const edge = event.clientY < box.top + box.height / 2 ? "before" : "after";
	dropTarget.value = { kind: "item", key: String(item.name), edge };
}

function onDragOverFolder(event, folder) {
	if (!dragIsMine()) return;
	event.preventDefault();
	event.stopPropagation();
	dropTarget.value = { kind: "folder", key: folder.name, edge: null };
}

function onDragOverRoot(event) {
	if (!dragIsMine()) return;
	event.preventDefault();
	dropTarget.value = { kind: "root", key: "", edge: null };
}

function isDropTarget(kind, key) {
	return dropTarget.value?.kind === kind && dropTarget.value?.key === key;
}

function dropEdge(name) {
	return isDropTarget("item", String(name)) ? dropTarget.value.edge : null;
}

/**
 * The dropped item lands next to its target *inside that target's folder*, so a
 * drag across a folder boundary is a move and a reorder at once - which is one
 * `move_item_to_folder` plus one `update_sort_orders`, in that order. Reversed,
 * the sort would be computed against the arrangement the move is about to
 * invalidate.
 */
function onDropOnItem(event, target) {
	event.preventDefault();
	event.stopPropagation();
	if (!dragIsMine()) return onDragEnd();

	const edge = dropTarget.value?.edge ?? "after";
	const moved = props.items.find((i) => String(i.name) === dragging.value.name);
	const targetFolder = folderNameFor(target.folder);
	if (!moved) return onDragEnd();

	if ((moved.folder || null) !== (target.folder || null)) {
		emit("move", moved.name, targetFolder);
	}

	const siblings = props.items
		.filter((i) => (i.folder || null) === (target.folder || null) && String(i.name) !== dragging.value.name)
		.slice()
		.sort(byOrder);
	const at = siblings.findIndex((i) => String(i.name) === String(target.name));
	siblings.splice(edge === "before" ? Math.max(at, 0) : at + 1, 0, moved);
	emitOrder(siblings);
	onDragEnd();
}

function onDropOnFolder(event, folder) {
	event.preventDefault();
	event.stopPropagation();
	if (dragIsMine()) emit("move", dragging.value.name, folder.name);
	onDragEnd();
}

function onDropOnRoot(event) {
	event.preventDefault();
	if (dragIsMine()) emit("move", dragging.value.name, null);
	onDragEnd();
}

function emitOrder(ordered) {
	emit(
		"reorder",
		ordered.map((item, index) => ({
			item_type: props.type,
			item_name: item.name,
			sort_order: index + 1,
		})),
	);
}
</script>

<template>
	<!-- Geometry copied from Insights' `WorkbookSidebarFolders.vue` template:
	     `px-3.5 pt-3` per section, an `h-6` header, `h-7.5` rows, and the
	     section's separator on the *list* rather than the section, so an empty
	     collection shows its dashed box without a rule under it.

	     Two token substitutions, both forced: Insights' drop indicator is
	     `bg-accent` and its rows read `text-sm`, but `accent` is an
	     Insights-only extension (`insights/frontend/tailwind.config.js:36` maps
	     it to `--app-accent`), absent from the frappe-ui preset this app builds
	     on. `bg-outline-blue-2` is the Espresso token for the same job - a
	     visible blue hairline - and keeps the rule "never hardcode a colour".
	-->
	<section class="flex flex-col px-3.5 pt-3" @dragover="onDragOverRoot" @drop="onDropOnRoot">
		<div class="mb-1 flex h-6 items-center justify-between">
			<div class="flex items-center gap-1">
				<div class="text-sm font-medium text-ink-gray-8">{{ label }}</div>
			</div>
			<div v-if="!readOnly && !isEditing('new-folder', type)" class="flex gap-1">
				<Button
					v-if="organizable"
					class="!h-fit !p-1"
					variant="ghost"
					:aria-label="`New folder in ${label}`"
					@click="startEdit('new-folder', type)"
				>
					<span class="lucide-folder-plus size-4 text-ink-gray-6" aria-hidden="true" />
				</Button>
				<Button
					v-if="canAdd"
					class="!h-fit !p-1"
					:loading="adding"
					variant="ghost"
					:aria-label="`Add ${label}`"
					@click="emit('add')"
				>
					<span class="lucide-plus size-4 text-ink-gray-6" aria-hidden="true" />
				</Button>
			</div>
		</div>

		<input
			v-if="isEditing('new-folder', type)"
			v-model="draft"
			:data-editor="`new-folder:${type}`"
			class="mb-1 h-7.5 w-full rounded border border-outline-gray-2 bg-surface-white px-1.5 text-sm text-ink-gray-9 outline-none"
			placeholder="Folder name"
			@keydown.enter.prevent="commitEdit('new-folder', type)"
			@keydown.esc.prevent="cancelEdit"
			@blur="commitEdit('new-folder', type)"
		/>

		<!-- Insights' dashed box rather than a bare line of text: an empty
		     collection is a place something goes, not a statement of fact. -->
		<div
			v-if="isEmpty"
			class="flex h-12 flex-col items-center justify-center rounded border border-dashed border-outline-gray-2 py-2"
		>
			<div class="text-xs text-ink-gray-6">{{ emptyMessage }}</div>
		</div>

		<div v-else class="flex flex-col border-b border-outline-gray-2 pb-3">
			<!-- Loose rows first, then folders: Insights' order, and the one that
			     matches how the server files things - a folder is a label applied
			     to rows, so unlabelled rows are not "after" any label. -->
			<div v-for="item in rootItems" :key="item.name" class="relative">
				<div
					v-if="dropEdge(item.name) === 'before'"
					class="absolute -top-0.5 left-0 right-0 h-0.5 bg-outline-blue-2 transition-all motion-reduce:transition-none"
				/>

				<div
					class="group w-full cursor-pointer rounded transition-all hover:bg-surface-gray-2 motion-reduce:transition-none"
					:class="[
						isActive(item.name) ? 'bg-surface-gray-2' : '',
						isDropTarget('item', item.name) ? 'bg-surface-blue-1' : '',
					]"
					:draggable="!readOnly && organizable"
					@dragstart="onDragStart($event, item)"
					@dragend="onDragEnd"
					@dragover="onDragOverItem($event, item)"
					@drop="onDropOnItem($event, item)"
				>
					<router-link
						:to="route(item)"
						class="flex h-7.5 items-center justify-between rounded pl-1.5 text-sm"
						:class="isActive(item.name) ? 'text-ink-gray-9' : 'text-ink-gray-7'"
					>
						<div class="flex gap-1.5 overflow-hidden">
							<div class="flex-shrink-0">
								<slot name="item-icon" :item="item" />
							</div>
							<input
								v-if="isEditing('item', String(item.name))"
								v-model="draft"
								:data-editor="`item:${item.name}`"
								class="min-w-0 flex-1 truncate border-none bg-transparent text-sm outline-none"
								@click.stop.prevent
								@keydown.enter.prevent="commitEdit('item', String(item.name), item.title)"
								@keydown.esc.prevent="cancelEdit"
								@blur="commitEdit('item', String(item.name), item.title)"
							/>
							<p v-else class="truncate">{{ item.title }}</p>
						</div>
						<div
							v-if="!readOnly && !isEditing('item', String(item.name))"
							class="invisible flex shrink-0 gap-0.5 pr-1 group-hover:visible"
						>
							<button
								class="cursor-pointer rounded p-1 transition-all hover:bg-surface-gray-3 motion-reduce:transition-none"
								:aria-label="`Rename ${item.title}`"
								@click.prevent.stop="startEdit('item', String(item.name), item.title)"
							>
								<span class="lucide-pen-line size-3.5 text-ink-gray-6" aria-hidden="true" />
							</button>
							<button
								class="cursor-pointer rounded p-1 transition-all hover:bg-surface-gray-3 motion-reduce:transition-none"
								:aria-label="`Remove ${item.title}`"
								@click.prevent.stop="emit('remove', item.name)"
							>
								<span class="lucide-x size-3.5 text-ink-gray-6" aria-hidden="true" />
							</button>
						</div>
					</router-link>
				</div>

				<div
					v-if="dropEdge(item.name) === 'after'"
					class="absolute -bottom-0.5 left-0 right-0 h-0.5 bg-outline-blue-2 transition-all motion-reduce:transition-none"
				/>
			</div>

			<div
				v-for="folder in sectionFolders"
				:key="folder.name"
				class="mt-1 rounded transition-all motion-reduce:transition-none"
				:class="isDropTarget('folder', folder.name) ? 'bg-surface-blue-1 ring-1 ring-outline-blue-1' : ''"
				@dragover="onDragOverFolder($event, folder)"
				@drop="onDropOnFolder($event, folder)"
			>
				<div
					class="group mb-0.5 flex h-7.5 cursor-pointer items-center justify-between rounded px-1.5 text-sm transition-all hover:bg-surface-gray-2 motion-reduce:transition-none"
					:class="isEditing('folder', folder.name) ? 'ring-1 ring-outline-gray-3' : ''"
					@click="!isEditing('folder', folder.name) && emit('toggle-folder', folder.name, !folder.is_expanded)"
				>
					<div class="flex items-center gap-1.5 overflow-hidden">
						<span
							v-if="!isEditing('folder', folder.name)"
							class="size-4 flex-shrink-0 text-ink-gray-6"
							:class="folder.is_expanded ? 'lucide-chevron-down' : 'lucide-chevron-right'"
							aria-hidden="true"
						/>
						<input
							v-if="isEditing('folder', folder.name)"
							v-model="draft"
							:data-editor="`folder:${folder.name}`"
							class="w-full flex-1 truncate border-none bg-transparent text-sm outline-none"
							@click.stop
							@keydown.enter.prevent="commitEdit('folder', folder.name, folder.title)"
							@keydown.esc.prevent="cancelEdit"
							@blur="commitEdit('folder', folder.name, folder.title)"
						/>
						<p v-else class="flex-1 truncate text-ink-gray-8">{{ folder.title }}</p>
					</div>
					<div
						v-if="!readOnly && !isEditing('folder', folder.name)"
						class="invisible flex gap-0.5 group-hover:visible"
					>
						<button
							class="cursor-pointer rounded p-1 transition-all hover:bg-surface-gray-3 motion-reduce:transition-none"
							:aria-label="`Rename folder ${folder.title}`"
							@click.stop="startEdit('folder', folder.name, folder.title)"
						>
							<span class="lucide-pen-line size-3.5 text-ink-gray-6" aria-hidden="true" />
						</button>
						<button
							class="cursor-pointer rounded p-1 transition-all hover:bg-surface-gray-3 motion-reduce:transition-none"
							:aria-label="`Delete folder ${folder.title}`"
							@click.stop="emit('delete-folder', folder.name)"
						>
							<span class="lucide-x size-3.5 text-ink-gray-6" aria-hidden="true" />
						</button>
					</div>
				</div>

				<div v-if="folder.is_expanded" class="ml-3 rounded">
					<div v-for="item in itemsIn(folder)" :key="item.name" class="relative">
						<div
							v-if="dropEdge(item.name) === 'before'"
							class="absolute -top-0.5 left-0 right-0 h-0.5 bg-outline-blue-2 transition-all motion-reduce:transition-none"
						/>

						<div
							class="group w-full cursor-pointer rounded transition-all hover:bg-surface-gray-2 motion-reduce:transition-none"
							:class="[
								isActive(item.name) ? 'bg-surface-gray-2' : '',
								isDropTarget('item', item.name) ? 'bg-surface-blue-1' : '',
							]"
							:draggable="!readOnly && organizable"
							@dragstart="onDragStart($event, item)"
							@dragend="onDragEnd"
							@dragover="onDragOverItem($event, item)"
							@drop="onDropOnItem($event, item)"
						>
							<router-link
								:to="route(item)"
								class="flex h-7.5 items-center justify-between rounded pl-1.5 text-sm"
								:class="isActive(item.name) ? 'text-ink-gray-9' : 'text-ink-gray-7'"
							>
								<div class="flex gap-1.5 overflow-hidden">
									<div class="flex-shrink-0">
										<slot name="item-icon" :item="item" />
									</div>
									<input
										v-if="isEditing('item', String(item.name))"
										v-model="draft"
										:data-editor="`item:${item.name}`"
										class="min-w-0 flex-1 truncate border-none bg-transparent text-sm outline-none"
										@click.stop.prevent
										@keydown.enter.prevent="commitEdit('item', String(item.name), item.title)"
										@keydown.esc.prevent="cancelEdit"
										@blur="commitEdit('item', String(item.name), item.title)"
									/>
									<p v-else class="truncate">{{ item.title }}</p>
								</div>
								<div
									v-if="!readOnly && !isEditing('item', String(item.name))"
									class="invisible flex shrink-0 gap-0.5 pr-1 group-hover:visible"
								>
									<button
										class="cursor-pointer rounded p-1 transition-all hover:bg-surface-gray-3 motion-reduce:transition-none"
										:aria-label="`Rename ${item.title}`"
										@click.prevent.stop="startEdit('item', String(item.name), item.title)"
									>
										<span class="lucide-pen-line size-3.5 text-ink-gray-6" aria-hidden="true" />
									</button>
									<button
										class="cursor-pointer rounded p-1 transition-all hover:bg-surface-gray-3 motion-reduce:transition-none"
										:aria-label="`Remove ${item.title}`"
										@click.prevent.stop="emit('remove', item.name)"
									>
										<span class="lucide-x size-3.5 text-ink-gray-6" aria-hidden="true" />
									</button>
								</div>
							</router-link>
						</div>

						<div
							v-if="dropEdge(item.name) === 'after'"
							class="absolute -bottom-0.5 left-0 right-0 h-0.5 bg-outline-blue-2 transition-all motion-reduce:transition-none"
						/>
					</div>
				</div>
			</div>

			<slot name="trailing" />
		</div>
	</section>
</template>
