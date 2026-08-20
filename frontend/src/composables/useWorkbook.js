import { computed, reactive, ref } from "vue";
import { useCall } from "frappe-ui";

/**
 * The workbook container: the list of them, and one open one with its tree.
 *
 * Two composables in one file for the same reason `useDataSources.js` holds
 * two: the list page and the builder page ask different questions of the same
 * DocType, and a single composable would make every list render carry the
 * per-workbook machinery it never uses.
 *
 * Every mutation below re-reads the workbook rather than patching local state.
 * One GET returns the whole tree (`Nakhoda Workbook.as_dict`), so a refetch
 * costs one request and cannot drift from what the server actually did - and
 * these writes have server-side consequences a client cannot predict:
 * `delete_folder` moves items, `nakhoda_chart.py:cleanup_empty_folder` deletes
 * a folder the caller never named, and `rename_folder` rewrites the `folder`
 * label on every item in it.
 */

const DOC = "/api/v2/document/Nakhoda Workbook";
const METHOD = "/api/v2/method/nakhoda.api.workbooks";

/** Which DocType a sidebar item type means, mirroring `api/workbooks.py:ITEM_DOCTYPES`. */
const ITEM_DOCTYPES = {
	query: "Nakhoda Query",
	chart: "Nakhoda Chart",
	dashboard: "Nakhoda Dashboard",
};

/** The list, and the two ways a new one comes into being. */
export function useWorkbooks() {
	const loading = ref(false);
	const error = ref(null);

	const listCall = useCall({ url: `${METHOD}.get_workbooks`, method: "GET", immediate: false });
	const createCall = useCall({ url: `${METHOD}.create_workbook`, method: "POST", immediate: false });
	const importCall = useCall({ url: `${METHOD}.import_workbook`, method: "POST", immediate: false });

	async function list(searchTerm = null) {
		loading.value = true;
		error.value = null;
		try {
			const result = await listCall.submit(searchTerm ? { search_term: searchTerm } : {});
			return result?.data ?? result ?? [];
		} catch (e) {
			error.value = e;
			throw e;
		} finally {
			loading.value = false;
		}
	}

	async function create(title = null) {
		const result = await createCall.submit(title ? { title } : {});
		return String(result?.data ?? result);
	}

	async function importWorkbook(workbook) {
		const result = await importCall.submit({ workbook });
		return String(result?.data ?? result);
	}

	return reactive({ loading, error, list, create, importWorkbook });
}

/** One workbook: its row, its four collections, and everything that edits them. */
export function useWorkbook(name = null) {
	const workbookName = ref(name);
	const doc = ref(null);
	const loading = ref(false);
	const saving = ref(false);
	const error = ref(null);

	const docUrl = computed(() =>
		workbookName.value ? `${DOC}/${encodeURIComponent(workbookName.value)}` : "",
	);

	const getCall = useCall({ url: docUrl, method: "GET", immediate: false });
	const patchCall = useCall({ url: docUrl, method: "PUT", immediate: false });
	const shareCall = useCall({ url: `${METHOD}.get_share_permissions`, method: "GET", immediate: false });
	const updateShareCall = useCall({
		url: `${METHOD}.update_share_permissions`,
		method: "POST",
		immediate: false,
	});
	const usersCall = useCall({
		url: `${METHOD}.list_shareable_users`,
		method: "GET",
		immediate: false,
	});
	const saveQueryCall = useCall({
		url: "/api/v2/method/nakhoda.api.query.save_query",
		method: "POST",
		immediate: false,
	});
	const addChartCall = useCall({ url: `${METHOD}.add_chart`, method: "POST", immediate: false });
	const addDashboardCall = useCall({ url: `${METHOD}.add_dashboard`, method: "POST", immediate: false });
	const createFolderCall = useCall({ url: `${METHOD}.create_folder`, method: "POST", immediate: false });
	const renameFolderCall = useCall({ url: `${METHOD}.rename_folder`, method: "POST", immediate: false });
	const deleteFolderCall = useCall({ url: `${METHOD}.delete_folder`, method: "POST", immediate: false });
	const toggleFolderCall = useCall({
		url: `${METHOD}.toggle_folder_expanded`,
		method: "POST",
		immediate: false,
	});
	const moveCall = useCall({ url: `${METHOD}.move_item_to_folder`, method: "POST", immediate: false });
	const sortCall = useCall({ url: `${METHOD}.update_sort_orders`, method: "POST", immediate: false });

	// One call object per verb, aimed by a ref, rather than a fresh `useCall`
	// per rename or delete: the URL is the only thing that varies, and these
	// fire from a sidebar where a click is one row among dozens.
	const itemPath = ref("");
	const methodPath = ref("");
	const itemPatchCall = useCall({ url: itemPath, method: "PUT", immediate: false });
	const itemDeleteCall = useCall({ url: itemPath, method: "DELETE", immediate: false });
	const methodCall = useCall({ url: methodPath, method: "POST", immediate: false });
	const docDeleteCall = useCall({ url: docUrl, method: "DELETE", immediate: false });

	const queries = computed(() => doc.value?.queries || []);
	const charts = computed(() => doc.value?.charts || []);
	const dashboards = computed(() => doc.value?.dashboards || []);
	const folders = computed(() => doc.value?.folders || []);
	const title = computed(() => doc.value?.title || "");
	// Absent until the row has loaded: treating "unknown" as writable would
	// paint add buttons a reader is about to lose.
	const readOnly = computed(() => (doc.value ? Boolean(doc.value.read_only) : true));
	// Sharing is its own level: a shared editor holds `write` and not `share`
	// (`nakhoda_workbook.py:as_dict`).
	const canShare = computed(() => Boolean(doc.value?.can_share));

	async function load(nextName) {
		const target = nextName || workbookName.value;
		if (!target) return null;
		workbookName.value = String(target);
		loading.value = true;
		error.value = null;
		try {
			const result = await getCall.submit();
			doc.value = result?.data ?? result ?? null;
			return doc.value;
		} catch (e) {
			error.value = e;
			throw e;
		} finally {
			loading.value = false;
		}
	}

	/** Run a write, then re-read the tree it changed. */
	async function mutate(call, params) {
		saving.value = true;
		error.value = null;
		try {
			const result = await call.submit(params);
			await load();
			return result?.data ?? result;
		} catch (e) {
			error.value = e;
			throw e;
		} finally {
			saving.value = false;
		}
	}

	function itemUrl(itemType, itemName) {
		const doctype = ITEM_DOCTYPES[itemType];
		if (!doctype) throw new Error(`unknown workbook item type: ${itemType}`);
		return `/api/v2/document/${doctype}/${encodeURIComponent(itemName)}`;
	}

	async function rename(newTitle) {
		return mutate(patchCall, { title: newTitle });
	}

	/**
	 * Create a query in this workbook from a pipeline the caller already has.
	 *
	 * There is deliberately no "add an empty query" here: `validate_pipeline`
	 * refuses a pipeline with no source (`engine/operations.py`), so a blank
	 * row cannot be inserted and filled in later. The builder holds the draft
	 * until it has a source, and this runs on save.
	 */
	async function addQuery(operations, queryTitle = "Untitled Query") {
		return mutate(saveQueryCall, {
			title: queryTitle,
			workbook: workbookName.value,
			operations,
		});
	}

	async function addChart(query, chartTitle = "Untitled Chart") {
		return mutate(addChartCall, { workbook: workbookName.value, query, title: chartTitle });
	}

	async function addDashboard(dashboardTitle = "Untitled Dashboard") {
		return mutate(addDashboardCall, { workbook: workbookName.value, title: dashboardTitle });
	}

	async function renameItem(itemType, itemName, itemTitle) {
		itemPath.value = itemUrl(itemType, itemName);
		return mutate(itemPatchCall, { title: itemTitle });
	}

	async function remove(itemType, itemName) {
		itemPath.value = itemUrl(itemType, itemName);
		return mutate(itemDeleteCall);
	}

	async function moveToFolder(itemType, itemName, folderName = null) {
		return mutate(moveCall, { item_type: itemType, item_name: itemName, folder_name: folderName });
	}

	async function reorder(items) {
		return mutate(sortCall, { workbook: workbookName.value, items });
	}

	async function createFolder(folderTitle, folderType) {
		return mutate(createFolderCall, {
			workbook: workbookName.value,
			title: folderTitle,
			folder_type: folderType,
		});
	}

	async function renameFolder(folderName, newTitle) {
		return mutate(renameFolderCall, { folder_name: folderName, new_title: newTitle });
	}

	async function deleteFolder(folderName, moveItemsToRoot = true) {
		return mutate(deleteFolderCall, {
			folder_name: folderName,
			move_items_to_root: moveItemsToRoot,
		});
	}

	/**
	 * Expanding a folder is UI state the backend records without touching
	 * `modified` (`api/workbooks.py:toggle_folder_expanded`), so this is the one
	 * write that does not refetch: a reload here would cost a full tree read
	 * every time a section is opened.
	 */
	async function toggleFolder(folderName, isExpanded) {
		await toggleFolderCall.submit({ folder_name: folderName, is_expanded: isExpanded ? 1 : 0 });
		const folder = folders.value.find((f) => f.name === folderName);
		if (folder) folder.is_expanded = isExpanded ? 1 : 0;
	}

	/**
	 * Document methods, run through v2's `execute_doc_method` route - which is
	 * registered *with* a trailing slash (`frappe/api/v2.py:295`), so omitting
	 * one costs a redirect that drops the POST body.
	 */
	async function runDocMethod(method, args = undefined) {
		methodPath.value = `${docUrl.value}/method/${method}/`;
		const result = await methodCall.submit(args);
		return result?.data ?? result;
	}

	async function duplicate() {
		return String(await runDocMethod("duplicate"));
	}

	async function exportWorkbook() {
		return runDocMethod("export");
	}

	/**
	 * Pull one exported query or chart into this workbook. The controller
	 * re-parents and re-titles the copy (`nakhoda_workbook.py:import_query`,
	 * `import_chart`), and both refetch: the sidebar has to show the new row.
	 */
	async function importQuery(query) {
		const name = String(await runDocMethod("import_query", { query }));
		await load();
		return name;
	}

	async function importChart(chart) {
		const name = String(await runDocMethod("import_chart", { chart }));
		await load();
		return name;
	}

	async function share() {
		const result = await shareCall.submit({ workbook_name: workbookName.value });
		return result?.data ?? result;
	}

	async function updateShare(userPermissions, organizationAccess = null) {
		return updateShareCall.submit({
			workbook_name: workbookName.value,
			user_permissions: userPermissions,
			organization_access: organizationAccess,
		});
	}

	/** Candidates for the share picker, filtered server-side. */
	async function shareableUsers(searchTerm = "") {
		const result = await usersCall.submit({
			workbook_name: workbookName.value,
			search_term: searchTerm || undefined,
		});
		return result?.data ?? result ?? [];
	}

	/**
	 * Delete the workbook itself. Its contents go with it: every child carries
	 * a `workbook` Link, so Frappe's own link check would refuse the delete
	 * unless the children are removed first, which the controller's `on_trash`
	 * does (`nakhoda_workbook.py`).
	 */
	async function deleteWorkbook() {
		return docDeleteCall.submit();
	}

	return reactive({
		workbookName,
		doc,
		title,
		loading,
		saving,
		error,
		readOnly,
		canShare,
		queries,
		charts,
		dashboards,
		folders,
		load,
		rename,
		addQuery,
		addChart,
		addDashboard,
		renameItem,
		remove,
		moveToFolder,
		reorder,
		createFolder,
		renameFolder,
		deleteFolder,
		toggleFolder,
		duplicate,
		exportWorkbook,
		importQuery,
		importChart,
		share,
		updateShare,
		shareableUsers,
		deleteWorkbook,
	});
}
