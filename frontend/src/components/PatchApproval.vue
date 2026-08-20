<script setup>
import { Button } from "frappe-ui";
import { ref } from "vue";
import { useDashboard } from "../composables/useDashboard.js";

/**
 * A proposed dashboard change, and the human who decides.
 *
 * `agent/thread.py:propose_patch` validates and *diffs* a patch but never
 * applies one - `PATCH_OPS` is a closed grammar and this screen is the gate
 * that grammar exists for. Nothing here is applied until the button is
 * pressed, and what is pressed is `apply_dashboard_patch`, the same endpoint a
 * human editing panels by hand would use.
 *
 * **Undo, not "are you sure".** `apply_patch` writes a `Nakhoda Dashboard
 * Version` and hands back its name; that makes the change reversible, which is
 * worth more than a confirmation dialog in front of a change the reader can
 * already see itemised above the button.
 */
const props = defineProps({
	dashboard: { type: String, required: true },
	/** `{ops, diff}` from a `converse` turn. */
	patch: { type: Object, required: true },
	/** The turn that proposed it, stamped onto the version this creates. */
	threadTurn: { type: String, default: "" },
});
const emit = defineEmits(["changed"]);

const api = useDashboard();
const version = ref("");
const busy = ref(false);
const error = ref("");

/** Diff `state` -> how it reads and how it is coloured. Three states, from
 * `engine/dashboard.py:apply_patch`; anything else would be a backend change
 * this component has not been taught about, so it is shown verbatim. */
const STATES = {
	added: { label: "New", class: "bg-surface-green-2 text-ink-green-3" },
	will_change: { label: "Changed", class: "bg-surface-amber-2 text-ink-amber-3" },
	removed: { label: "Removed", class: "bg-surface-red-2 text-ink-red-3" },
};

function badge(state) {
	return STATES[state] || { label: state, class: "bg-surface-gray-3 text-ink-gray-6" };
}

async function apply() {
	busy.value = true;
	error.value = "";
	try {
		const result = await api.applyPatch(props.dashboard, props.patch.ops, props.threadTurn || null);
		version.value = result?.version || "";
		emit("changed");
	} catch (e) {
		error.value = e?.messages?.[0] || e?.message || "Could not apply this change";
	} finally {
		busy.value = false;
	}
}

async function undo() {
	busy.value = true;
	error.value = "";
	try {
		await api.revertPatch(props.dashboard, version.value);
		version.value = "";
		emit("changed");
	} catch (e) {
		error.value = e?.messages?.[0] || e?.message || "Could not undo this change";
	} finally {
		busy.value = false;
	}
}
</script>

<template>
	<div class="patch rounded-lg border border-outline-gray-2 bg-surface-gray-1 p-3">
		<p class="text-p-sm font-medium text-ink-gray-8">
			{{ version ? "Applied to this dashboard" : "Proposed change" }}
		</p>

		<ul class="mt-2 flex flex-col gap-1.5">
			<li v-for="item in patch.diff" :key="`${item.i}:${item.state}`" class="flex items-center gap-2">
				<span class="rounded-sm px-1.5 py-0.5 text-xs font-medium" :class="badge(item.state).class">
					{{ badge(item.state).label }}
				</span>
				<span class="text-p-sm text-ink-gray-8">{{ item.title || item.i }}</span>
				<span v-if="item.field" class="text-p-sm text-ink-gray-5">{{ item.field }}</span>
			</li>
		</ul>

		<p v-if="error" class="mt-2 text-p-sm text-ink-red-4">{{ error }}</p>

		<div class="mt-3 flex items-center gap-2">
			<Button
				v-if="!version"
				variant="solid"
				size="sm"
				label="Apply"
				:loading="busy"
				@click="apply"
			/>
			<Button v-else variant="subtle" size="sm" label="Undo" :loading="busy" @click="undo" />
			<!-- The version name is on screen because it is the record of the
			     change, and the reader may need to name it elsewhere. -->
			<span v-if="version" class="font-mono text-xs text-ink-gray-4">{{ version }}</span>
		</div>
	</div>
</template>
