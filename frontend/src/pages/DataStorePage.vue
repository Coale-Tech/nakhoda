<script setup>
import { Button } from "frappe-ui";
</script>

<template>
	<div class="p-5">
		<div class="mb-4 flex items-center justify-between">
			<h2 class="text-lg-semibold text-ink-gray-9">Data Store</h2>
			<Button variant="solid" theme="gray" icon-left="lucide-plus" label="Import Table" />
		</div>
		<p class="text-p-base text-ink-gray-6">
			DuckDB warehouse tables synced from connected sources. Manage incremental imports, compaction,
			and pruning here.
		</p>
	</div>
</template>
