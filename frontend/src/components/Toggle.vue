<script setup>
import { computed } from "vue";
import { Switch } from "frappe-ui";

/**
 * The pill switch Insights uses for every boolean *setting*
 * (`src2/settings/DataStoreSettings.vue`, `PermissionsSettings.vue` -
 * `<Toggle>`, globally registered in `src2/globals.ts` onto their local
 * `components/Checkbox.vue`, a headlessui `Switch`).
 *
 * Here it wraps frappe-ui's own `Switch` (1.0.0-beta.29, reka-ui based)
 * rather than reaching past the package for headlessui: same control, one
 * dependency, and the design tokens come from the preset this app already
 * loads (`tailwind.config.js` globs frappe-ui's source so the switch's
 * `surface-gray-*` classes survive purging).
 *
 * The adapter is the only reason this file exists. A Frappe `Check` field
 * round-trips as `0`/`1`, `Switch`'s model is a `boolean`, and reka-ui's
 * `SwitchRoot` warns when handed a number. Writing `1`/`0` back - not
 * `true`/`false` - also keeps `useSettings.js`'s dirty check comparing like
 * with like, so toggling a switch off and on again leaves Save disabled
 * instead of falsely dirty.
 *
 * Not used for the AI Provider tab's `Enable AI`: Insights renders *that*
 * one as a labelled checkbox (`AISettings.vue:356`), and this port matches
 * Insights tab for tab rather than imposing a consistency Insights itself
 * does not have.
 */
const model = defineModel({ type: [Number, Boolean], default: 0 });

const checked = computed({
	get: () => Boolean(model.value),
	set: (value) => (model.value = value ? 1 : 0),
});
</script>

<template>
	<Switch v-model="checked" v-bind="$attrs" />
</template>
