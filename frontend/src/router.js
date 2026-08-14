import { createRouter, createWebHistory } from "vue-router";
import AskPage from "./pages/AskPage.vue";
import DashboardsPage from "./pages/DashboardsPage.vue";
import DashboardBuilderPage from "./pages/DashboardBuilderPage.vue";
import WorkbooksPage from "./pages/WorkbooksPage.vue";
import WorkbookBuilderPage from "./pages/WorkbookBuilderPage.vue";
import QueriesPage from "./pages/QueriesPage.vue";
import QueryBuilderPage from "./pages/QueryBuilderPage.vue";
import DataSourcesPage from "./pages/DataSourcesPage.vue";
import DataStorePage from "./pages/DataStorePage.vue";
import SettingsPage from "./pages/SettingsPage.vue";

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
		{ path: "/workbooks/:name", name: "Workbook", component: WorkbookBuilderPage, meta: { label: "Workbook", icon: "lucide-book-open" } },
		{ path: "/queries", name: "Queries", component: QueriesPage, meta: { label: "Queries", icon: "lucide-database" } },
		{ path: "/queries/:name", name: "Query", component: QueryBuilderPage, meta: { label: "Query", icon: "lucide-database" } },
		{ path: "/data-sources", name: "Data Sources", component: DataSourcesPage, meta: { label: "Data Sources", icon: "lucide-plug" } },
		{ path: "/data-store", name: "Data Store", component: DataStorePage, meta: { label: "Data Store", icon: "lucide-server" } },
		{ path: "/settings", name: "Settings", component: SettingsPage, meta: { label: "Settings", icon: "lucide-settings" } },
		{ path: "/:pathMatch(.*)*", redirect: "/" },
	],
});

export default router;
