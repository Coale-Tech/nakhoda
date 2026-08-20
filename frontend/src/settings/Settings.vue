<script setup>
import { Dialog } from "frappe-ui";
import { shallowRef } from "vue";
import TabbedSidebarLayout from "../components/TabbedSidebarLayout.vue";
import AISettings from "./AISettings.vue";
import DataStoreSettings from "./DataStoreSettings.vue";
import GeneralSettings from "./GeneralSettings.vue";
import PermissionsSettings from "./PermissionsSettings.vue";
import SemanticSettings from "./SemanticSettings.vue";

/**
 * Ported from Insights' `src2/settings/Settings.vue`: a `Dialog` holding a
 * `TabbedSidebarLayout` of grouped tabs, opened from `AppSidebar.vue`
 * instead of routed - every other surface in this SPA is a route, but
 * Settings specifically is not, to match Insights' actual UX (a modal, not
 * a page with its own URL). Two adaptations for this installed frappe-ui
 * version, not Insights' bespoke `TabbedSidebarLayout`:
 *
 * - `size="4xl"` + `bare` as flat props, not `:options="{ size: '4xl' }"`
 *   + `#body` - this frappe-ui version (`1.0.0-beta.29`) deprecated the
 *   `options`/`#body` pair in favour of flat props + `#default`, and using
 *   the deprecated spelling would just emit a console warning on every
 *   open for no behavioural difference.
 * - Icons are `lucide-*` CSS classes (`TabbedSidebarLayout`'s existing
 *   contract, see that file), not imported `lucide-vue-next` components.
 *
 * Insights ships Profile / General / AI Analytics / Users / Permissions /
 * Data Store across an Account group and an Organization group. General /
 * AI Provider / Data Store / Permissions carry over into the Organization
 * group here - Profile/Users have no in-SPA user management to back them
 * (Frappe's own desk user list and the `Nakhoda Admin` role cover it).
 *
 * Data Store is both a route (`/data-store`) and a tab, for the reason
 * Insights splits them too: choosing what to import is a task, capping every
 * import is a setting. The tab owns only the two site-wide ceilings
 * (`max_records_to_sync`, `max_memory_usage`) that the page's own import
 * dialog then shows as its placeholder default - one number, one owner.
 *
 * AI Provider (`AISettings.vue`) was reconsidered - it was previously left
 * out entirely, on the reasoning that model routing is tier-based
 * (`agent/manager.py`) and Insights' per-field provider config had no
 * doctype-backed equivalent here. `useSettings.js` documents why that's no
 * longer true: `agent/providers.py`'s `credentials()` and
 * `agent/tiers.py`'s `models()` now read `Nakhoda Settings` DB-first,
 * env-fallback, matching Raven's own settings precedent
 * (`raven_settings.json`, `get_password`).
 *
 * A fourth candidate, MCP/plugin config (`Nakhoda MCP Server`,
 * `12-build-plan.md` Phase 6), stays out: it's a `Link` field pointing at
 * `Nakhoda Space` (per-space plugin registration), not a global setting,
 * and no Space-scoped page exists yet in this frontend to host it - adding
 * it here would model per-space plugin config as an app-wide toggle, which
 * the schema doesn't support.
 */
const showDialog = defineModel({ required: true, default: false });

const tabGroups = [
	{
		groupLabel: "Organization",
		tabs: [
			{ label: "General", icon: "lucide-settings", component: GeneralSettings },
			{ label: "AI Provider", icon: "lucide-brain", component: AISettings },
			{ label: "Data Store", icon: "lucide-server", component: DataStoreSettings },
			{ label: "Semantic Model", icon: "lucide-book-open", component: SemanticSettings },
			{ label: "Permissions", icon: "lucide-key-round", component: PermissionsSettings },
		],
	},
];
const activeTab = shallowRef(tabGroups[0].tabs[0]);
</script>

<template>
	<Dialog v-model="showDialog" size="4xl" bare>
		<div class="relative flex text-base" :style="{ height: 'calc(100vh - 12rem)' }">
			<TabbedSidebarLayout title="Settings" :tabs="tabGroups" v-model:activeTab="activeTab" />
		</div>
	</Dialog>
</template>
