import { createRouter, createWebHistory } from "vue-router";
import AskPage from "./pages/AskPage.vue";
import DashboardsPage from "./pages/DashboardsPage.vue";
import DashboardBuilderPage from "./pages/DashboardBuilderPage.vue";
import WorkbooksPage from "./pages/WorkbooksPage.vue";
import WorkbookBuilderPage from "./pages/WorkbookBuilderPage.vue";
import QueriesPage from "./pages/QueriesPage.vue";
import QueryBuilderPage from "./pages/QueryBuilderPage.vue";
import DataSourcesPage from "./pages/DataSourcesPage.vue";
import DataSourceTablesPage from "./pages/DataSourceTablesPage.vue";
import DataSourceTablePage from "./pages/DataSourceTablePage.vue";
import DataStorePage from "./pages/DataStorePage.vue";

/**
 * History base is `/nakhoda` when the Frappe www route serves the SPA, but
 * Vite preview serves the built bundle at `/assets/nakhoda/frontend/` and the
 * tests use that URL. If `window.location.pathname` is under the asset base,
 * use the asset base as the router base so client-side pushes stay inside the
 * preview server; otherwise use the production `/nakhoda` base.
 */
const assetBase = import.meta.env.BASE_URL; // e.g. /assets/nakhoda/frontend/
const currentPath = window.location.pathname || "/nakhoda";
const isPreview = currentPath.startsWith(assetBase) && assetBase !== "/nakhoda/";
export const HISTORY_BASE = isPreview ? assetBase : "/nakhoda";

/**
 * One route today (Ask). A router is not optional even so: frappe-ui's
 * `<Button>` injects `Symbol(router)` and warns on every render without one,
 * and `Button :route` / `ListRow :to` only work with an instance installed.
 *
 * `/nakhoda` is the Frappe www route that serves this SPA
 * (`nakhoda/www/_nakhoda.py`), so it is the history base - not `/`.
 */
export const router = createRouter({
	history: createWebHistory(HISTORY_BASE),
	routes: [
		{ path: "/", name: "Ask", component: AskPage, meta: { label: "Ask", icon: "lucide-message-circle" } },
		{ path: "/dashboards", name: "Dashboards", component: DashboardsPage, meta: { label: "Dashboards", icon: "lucide-layout-grid" } },
		{ path: "/dashboards/:name", name: "Dashboard", component: DashboardBuilderPage, meta: { label: "Dashboard", icon: "lucide-layout-grid" } },
		{ path: "/workbooks", name: "Workbooks", component: WorkbooksPage, meta: { label: "Workbooks", icon: "lucide-book-open" } },
		// `chromeless`: a workbook replaces the workbench shell rather than
		// nesting inside it. Insights does the same (`src2/workbook/Workbook.vue`
		// renders its own navbar plus the workbook sidebar and no app sidebar) -
		// the builder needs the width, and the workbook's own navbar carries the
		// one link back out.
		{
			path: "/workbooks/:name",
			name: "Workbook",
			component: WorkbookBuilderPage,
			meta: { label: "Workbook", icon: "lucide-book-open", chromeless: true },
		},
		// The open item is a route, not local state, so a saved answer is
		// linkable: `save_answer` hands back `{workbook, query}` and Ask points
		// at exactly that query. One record for all three item types - the
		// builder switches on `itemType`, and constraining the param here means
		// a typo lands on the catch-all redirect rather than an empty panel.
		{
			path: "/workbooks/:name/:itemType(query|chart|dashboard)/:itemId",
			name: "Workbook Item",
			component: WorkbookBuilderPage,
			meta: { label: "Workbook", icon: "lucide-book-open", chromeless: true },
		},
		{ path: "/queries", name: "Queries", component: QueriesPage, meta: { label: "Queries", icon: "lucide-database" } },
		{ path: "/queries/:name", name: "Query", component: QueryBuilderPage, meta: { label: "Query", icon: "lucide-database" } },
		{ path: "/data-sources", name: "Data Sources", component: DataSourcesPage, meta: { label: "Data Sources", icon: "lucide-plug" } },
		// `props: true` so the pages take `name`/`table` as declared props rather
		// than reaching into `$route` - the same shape the builder pages use.
		{ path: "/data-sources/:name", name: "Data Source Tables", component: DataSourceTablesPage, props: true, meta: { label: "Data Source", icon: "lucide-plug" } },
		{ path: "/data-sources/:name/:table", name: "Data Source Table", component: DataSourceTablePage, props: true, meta: { label: "Table", icon: "lucide-table" } },
		{ path: "/data-store", name: "Data Store", component: DataStorePage, meta: { label: "Data Store", icon: "lucide-server" } },
		{ path: "/:pathMatch(.*)*", redirect: "/" },
	],
});

export default router;
