<script setup>
import { watch } from "vue";
import { useRouter } from "vue-router";
import { Badge, Button, Dialog, LoadingIndicator } from "frappe-ui";
import { useTemplates } from "../composables/useTemplates.js";

/**
 * The workbook-template picker (build-plan Phase 9 / success criterion 1):
 * a card grid over `nakhoda.api.templates.get_intelligence_templates`,
 * ported from Insights' filesystem-template gallery design
 * (`nvumabaranda/apps/insights/insights/api/templates.py` +
 * `WorkbookList.vue`'s "New from template" dialog) but ibis-native - a
 * template import here creates a real `Nakhoda Intelligence Template`
 * record, not an `Insights Workbook` reconstructed from a serialized
 * `workbook.json`.
 *
 * `size="4xl"` + `#default` (no `options`/`#body`) matches this installed
 * frappe-ui version's flat-prop `Dialog` API - see `settings/Settings.vue`
 * for why the deprecated pair is avoided.
 *
 * Each card already carries `imported_name`/`update_available`/`customized`
 * from the backend, so the button label is decided here, not re-derived
 * from a separate "my dashboards" list:
 * - not imported: "Add" -> `create_intelligence_template`, then navigate.
 * - imported, no update: "Open" -> navigate straight to the existing record.
 * - update available, not customized: "Update" -> `update_intelligence_template`
 *   in place, then navigate (safe: nothing site-specific to lose).
 * - update available, customized: "Open" only - an unconditional update
 *   would silently replace the site's edits, so this surface does not offer
 *   it; the customization badge is the signal an admin acts on directly.
 */
const showDialog = defineModel({ required: true, default: false });
const emit = defineEmits(["imported"]);

const router = useRouter();
const templates = useTemplates();

watch(showDialog, (open) => {
	if (open) templates.list();
});

async function openTemplate(template) {
	let name = template.imported_name;
	if (!name) {
		name = await templates.create(template.name);
	} else if (template.update_available && !template.customized) {
		await templates.update(template.name);
	}
	showDialog.value = false;
	emit("imported", name);
	router.push({ name: "Dashboard", params: { name } });
}

function actionLabel(template) {
	if (!template.imported_name) return "Add";
	if (template.update_available && !template.customized) return "Update";
	return "Open";
}
</script>

<template>
	<Dialog v-model="showDialog" size="4xl" bare>
		<div class="flex max-h-[80vh] flex-col gap-4 p-6">
			<div>
				<h3 class="text-lg-semibold text-ink-gray-9">New from template</h3>
				<p class="text-p-sm mt-1 text-ink-gray-6">
					Domain dashboards ship with metrics, panels and an agent skill fragment already wired - only
					the data source needs connecting.
				</p>
			</div>
			<div v-if="templates.loading" class="flex flex-1 items-center justify-center py-10">
				<LoadingIndicator class="size-6" />
			</div>
			<div
				v-else-if="templates.error"
				class="rounded-sm border border-outline-red-2 bg-surface-red-1 p-4 text-sm text-ink-red-6"
			>
				Could not load templates.
			</div>
			<div v-else-if="!templates.templates.length" class="py-10 text-center text-p-base text-ink-gray-6">
				No intelligence templates are available - none of the installed apps ship one this site can use.
			</div>
			<div v-else class="grid flex-1 grid-cols-2 gap-3 overflow-y-auto">
				<div
					v-for="template in templates.templates"
					:key="template.name"
					class="flex flex-col justify-between gap-3 rounded-lg border border-outline-gray-2 p-4"
				>
					<div>
						<div class="mb-1 flex items-center justify-between gap-2">
							<span class="text-base-semibold text-ink-gray-9">{{ template.title }}</span>
							<Badge v-if="template.customized" theme="orange" variant="subtle">Customized</Badge>
							<Badge v-else-if="template.update_available" theme="blue" variant="subtle">Update available</Badge>
						</div>
						<p class="text-p-sm mb-2 text-ink-gray-6">{{ template.description }}</p>
						<div class="flex items-center gap-2 text-xs text-ink-gray-5">
							<Badge variant="subtle" theme="gray">{{ template.app_title }}</Badge>
							<span v-if="!template.has_data">No sample data on this site</span>
						</div>
					</div>
					<Button
						variant="solid"
						theme="gray"
						class="self-end"
						:label="actionLabel(template)"
						:loading="templates.createCall.loading || templates.updateCall.loading"
						@click="openTemplate(template)"
					/>
				</div>
			</div>
		</div>
	</Dialog>
</template>
