<script setup>
import { Button } from "frappe-ui";
</script>

<template>
	<div class="p-5">
		<div class="mb-4 flex items-center justify-between">
			<h2 class="text-lg-semibold text-ink-gray-9">Data Sources</h2>
			<Button variant="solid" theme="gray" icon-left="lucide-plus" label="New Source" />
		</div>
		<p class="text-p-base text-ink-gray-6">
			Connections to ERPNext site DB, PostgreSQL, MySQL, BigQuery, ClickHouse, and other backends. The
			default source is the current Frappe site database.
		</p>
	</div>
</template>
