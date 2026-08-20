<script setup>
import { Tooltip } from "frappe-ui";
import ContentEditable from "./ContentEditable.vue";

/**
 * The workbook's own chrome, ported from Insights'
 * `src2/workbook/WorkbookNavbar.vue`: an `h-11` bar carrying the logo on the
 * left, the editable title centred, and the workbook's actions on the right.
 *
 * It exists because a workbook is a *focused* surface. Insights drops the app
 * sidebar entirely while one is open (`Workbook.vue` renders navbar + workbook
 * sidebar and nothing else), so the only navigation left is the logo, which
 * returns to the list. This app now does the same: `router.js` marks the two
 * workbook routes `chromeless` and `App.vue` hides `AppSidebar` for them. The
 * alternative - a workbook nested inside the workbench shell - spent 224px of
 * a 1440px window on links you are not using and pushed the builder's own
 * sidebar off centre.
 *
 * The title is a `ContentEditable`, not a field: `rename` fires on Enter or
 * blur, and the parent turns that into the one server call. Unchanged and
 * empty titles are the parent's business - this component reports what the
 * user typed.
 *
 * Two token substitutions against the Insights original, forced by this
 * bench's frappe-ui (`1.0.0-beta.29` vs Insights' `0.1.142`): `text-warn` is
 * not in this preset's palette, so the read-only shield uses `text-ink-amber-3`
 * (`node_modules/frappe-ui/tailwind/colors.js` - the `ink` ramp has no `warn`
 * alias), and the logo is this app's own.
 */
defineProps({
	title: { type: String, default: "" },
	placeholder: { type: String, default: "Untitled Workbook" },
	readOnly: { type: Boolean, default: false },
});

const emit = defineEmits(["rename"]);

const logoUrl = "/assets/nakhoda/nakhoda-logo.png";
</script>

<template>
	<!-- `header`, not a bare div: this is the page's top bar, and it is the element
	     `AskPage.vue` already uses for its own, so the two agree. It is not a
	     `banner` landmark - `App.vue` renders every route inside `main`, and a
	     `header` inside `main` is scoped to it by definition - but it is the
	     sectioning root that makes "the Ask button in the navbar" a different
	     thing from the Ask button in the panel, which matters because frappe-ui
	     derives a Button's accessible name from its visible label
	     (`Button.vue:288`) and both are labelled "Ask". -->
	<header
		class="sticky top-0 z-10 flex h-11 w-full shrink-0 items-center gap-3 bg-surface-white px-3 shadow-sm"
	>
		<div class="relative flex flex-1 items-center">
			<div class="absolute left-0">
				<router-link :to="{ name: 'Workbooks' }" aria-label="Workbooks">
					<img :src="logoUrl" alt="" class="h-7 rounded" />
				</router-link>
			</div>

			<div class="flex flex-1 items-center justify-center">
				<div class="relative flex items-center gap-3">
					<Tooltip v-if="readOnly" text="You have read-only access to this workbook">
						<span
							class="lucide-shield-alert absolute -left-6 size-4 text-ink-amber-3"
							role="img"
							aria-label="Read only"
						/>
					</Tooltip>
					<ContentEditable
						class="rounded-sm font-medium !text-ink-gray-8 focus:ring-2 focus:ring-outline-gray-4 focus:ring-offset-4"
						:model-value="title"
						:placeholder="placeholder"
						:disabled="readOnly"
						@returned="(value) => emit('rename', value)"
						@blur="(value) => emit('rename', value)"
					/>
				</div>
			</div>

			<div class="absolute right-0">
				<slot name="actions" />
			</div>
		</div>
	</header>
</template>
