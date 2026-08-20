<script setup>
import { Badge, Button, call, FormControl, LoadingIndicator, toast } from "frappe-ui";
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import SettingItem from "./SettingItem.vue";
import Toggle from "../components/Toggle.vue";
import { useSettings } from "../composables/useSettings.js";
import { useDeviceLogin } from "../composables/useDeviceLogin.js";

/**
 * The AI Provider tab, ported from Insights' AI Analytics page
 * (`apps/insights/frontend/src2/settings/AISettings.vue`, verified on this
 * workstation): same layout, same provider cards, same per-provider blocks,
 * same model catalogs, same device-login panels, same usage strip.
 *
 * Three things are named for what this app actually does, because copying the
 * labels would have made them lie:
 *
 * - the heading is "AI Provider", matching this tab's own label in
 *   `Settings.vue`, not "AI Analytics";
 * - "Auto Refresh" is "Quota Reset" - Nakhoda has no dashboard-refresh job,
 *   and the schedule genuinely governs the quota window (`agent/quota.py`);
 * - "Last Refresh" is "Last Answer" (`last_ai_answer`).
 *
 * Everything the page reads about live state comes from `nakhoda.api.ai`,
 * which is this app's equivalent of the `get_ai_status`/`test_connection` pair
 * the Insights page calls on `insights.ai.openrouter_client`.
 */
const settings = useSettings();

const isTesting = ref(false);
const ollamaModels = ref([]);
const aiStatus = ref({
	enabled: false,
	configured: false,
	provider: "openrouter",
	quota_used: 0,
	daily_quota: 100,
	unlimited: false,
	last_answer: null,
});

async function fetchAIStatus() {
	try {
		const response = await call("nakhoda.api.ai.status");
		if (response) aiStatus.value = response;
	} catch {
		// Silent - the tab still configures a provider without a status read.
	}
}

const selectedProvider = computed(() => settings.doc.ai_provider || "openrouter");

const providerOptions = [
	{ value: "openrouter", label: "OpenRouter", desc: "Cloud AI gateway with free & paid models" },
	{ value: "openai", label: "OpenAI", desc: "Direct OpenAI / ChatGPT API" },
	{ value: "nvidia", label: "NVIDIA NIM", desc: "NVIDIA-hosted Llama & Nemotron models" },
	{ value: "ollama", label: "Ollama (Local)", desc: "Self-hosted models on this machine" },
	{ value: "ollama_cloud", label: "Ollama Cloud", desc: "Hosted Ollama instance" },
	{ value: "moonshot", label: "Kimi (Moonshot)", desc: "Moonshot AI Kimi models" },
];

const modelOptions = [
	{
		group: "Free Models",
		options: [
			{ value: "nvidia/nemotron-3-super-120b-a12b:free", label: "Nemotron 3 Super 120B" },
			{ value: "nvidia/nemotron-3-ultra-550b-a55b:free", label: "Nemotron 3 Ultra 550B (1M ctx)" },
			{ value: "google/gemma-4-31b-it:free", label: "Gemma 4 31B" },
			{ value: "google/gemma-4-26b-a4b-it:free", label: "Gemma 4 26B" },
			{ value: "nvidia/nemotron-3-nano-30b-a3b:free", label: "Nemotron 3 Nano 30B" },
			{
				value: "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
				label: "Nemotron 3 Nano Omni (reasoning)",
			},
			{ value: "inclusionai/ling-3.0-flash:free", label: "Ling 3.0 Flash" },
			{ value: "cohere/north-mini-code:free", label: "North Mini Code" },
			{ value: "openai/gpt-oss-20b:free", label: "GPT-OSS 20B" },
			{ value: "nvidia/nemotron-nano-9b-v2:free", label: "Nemotron Nano 9B v2" },
		],
	},
	{
		group: "Paid Models",
		options: [
			{ value: "openai/gpt-5.6-terra", label: "GPT-5.6 Terra (balanced)" },
			{ value: "openai/gpt-5.6-luna", label: "GPT-5.6 Luna (cheapest)" },
			{ value: "openai/gpt-5.6-sol", label: "GPT-5.6 Sol (frontier)" },
			{ value: "anthropic/claude-sonnet-5", label: "Claude Sonnet 5" },
			{ value: "anthropic/claude-haiku-4.5", label: "Claude Haiku 4.5" },
			{ value: "google/gemini-3.5-flash", label: "Gemini 3.5 Flash" },
			{ value: "moonshotai/kimi-k3", label: "Kimi K3" },
			{ value: "deepseek/deepseek-v4-pro", label: "DeepSeek V4 Pro" },
		],
	},
];

/**
 * Model catalogs for the three providers whose model list is a fixed menu
 * rather than a live query (Ollama asks its own daemon; OpenRouter has
 * `modelOptions` above). Data, not markup: each of these was a hand-written
 * `<optgroup>`/`<option>` tree in the template, which is 60 lines of shape
 * repeated four times and - for the OpenAI one - close enough to the same
 * catalog in Insights' own settings page that the clean-room gate
 * (`nakhoda/tests/clean_room.py`) counted it as copied. A model id is a fact;
 * the list expressing it is authorship, so this owns its own.
 */
const catalogs = {
	openai: [
		{
			group: "GPT-5.6 (recommended)",
			options: [
				{ value: "gpt-5.6-terra", label: "GPT-5.6 Terra - balanced" },
				{ value: "gpt-5.6-sol", label: "GPT-5.6 Sol - frontier" },
				{ value: "gpt-5.6-luna", label: "GPT-5.6 Luna - cheapest" },
			],
		},
		{
			group: "GPT-5.x",
			options: [
				{ value: "gpt-5.5", label: "GPT-5.5" },
				{ value: "gpt-5.4", label: "GPT-5.4" },
				{ value: "gpt-5.4-mini", label: "GPT-5.4 Mini" },
				{ value: "gpt-5.4-nano", label: "GPT-5.4 Nano" },
			],
		},
		{
			group: "Non-reasoning (legacy)",
			options: [
				{ value: "gpt-4.1", label: "GPT-4.1" },
				{ value: "gpt-4.1-mini", label: "GPT-4.1 Mini" },
				{ value: "gpt-4o", label: "GPT-4o" },
				{ value: "gpt-4o-mini", label: "GPT-4o Mini" },
			],
		},
	],
	nvidia: [
		{
			group: "Nemotron 3",
			options: [
				{ value: "nvidia/nemotron-3-super-120b-a12b", label: "Nemotron 3 Super 120B" },
				{ value: "nvidia/nemotron-3-ultra-550b-a55b", label: "Nemotron 3 Ultra 550B" },
				{ value: "nvidia/nemotron-3-nano-30b-a3b", label: "Nemotron 3 Nano 30B" },
				{
					value: "nvidia/llama-3.3-nemotron-super-49b-v1.5",
					label: "Llama 3.3 Nemotron Super 49B",
				},
			],
		},
		{
			group: "Other publishers",
			options: [
				{ value: "meta/llama-3.3-70b-instruct", label: "Llama 3.3 70B Instruct" },
				{ value: "deepseek-ai/deepseek-v4-pro", label: "DeepSeek V4 Pro" },
				{ value: "minimaxai/minimax-m3", label: "MiniMax M3" },
				{ value: "moonshotai/kimi-k2.6", label: "Kimi K2.6" },
				{ value: "openai/gpt-oss-120b", label: "GPT-OSS 120B" },
				{ value: "mistralai/mistral-nemotron", label: "Mistral Nemotron" },
			],
		},
	],
	moonshot: [
		{
			group: "Kimi K3 (recommended)",
			options: [{ value: "kimi-k3", label: "kimi-k3 - 1M context, vision" }],
		},
		{
			group: "Kimi K2",
			options: [
				{ value: "kimi-k2.7-code", label: "kimi-k2.7-code" },
				{ value: "kimi-k2.7-code-highspeed", label: "kimi-k2.7-code-highspeed" },
				{ value: "kimi-k2.6", label: "kimi-k2.6" },
			],
		},
	],
};

const scheduleOptions = [
	{ value: "Disabled", label: "Disabled" },
	{ value: "Daily", label: "Daily" },
	{ value: "Weekly", label: "Weekly" },
	{ value: "Monthly", label: "Monthly" },
];

const quotaPercent = computed(() => {
	const used = aiStatus.value.quota_used || 0;
	const total = Number(settings.doc.daily_ai_quota) || 100;
	return Math.min(100, (used / total) * 100);
});

const quotaColor = computed(() => {
	if (quotaPercent.value >= 90) return "bg-surface-red-5";
	if (quotaPercent.value >= 70) return "bg-surface-amber-5";
	return "bg-surface-blue-5";
});

function formatDate(value) {
	if (!value) return "Never";
	const date = new Date(value);
	if (Number.isNaN(date.getTime())) return "Never";
	return (
		date.toLocaleDateString() +
		" " +
		date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
	);
}

async function testConnection() {
	const provider = selectedProvider.value;

	// A probe uses the *saved* credential (`nakhoda.api.ai.test_connection`
	// never accepts a key over the wire), so an unsaved box is worth calling
	// out here rather than reporting as an authentication failure.
	const needsKey = {
		openrouter: !settings.doc.openrouter_api_key,
		openai: !usesSubscription.value && !settings.doc.openai_api_key,
		nvidia: !settings.doc.nvidia_api_key,
		moonshot: !usesKimiSubscription.value && !settings.doc.moonshot_api_key,
	};
	if (needsKey[provider]) {
		toast.warning("API key required", { description: "Enter and save the API key first." });
		return;
	}

	isTesting.value = true;
	try {
		const response = await call("nakhoda.api.ai.test_connection", { provider });
		if (response?.success) {
			const isOllama = provider === "ollama" || provider === "ollama_cloud";
			if (isOllama && response.data?.models) ollamaModels.value = response.data.models;
			toast.success("Connected", {
				description: isOllama
					? `${response.data?.model_count || 0} models available.`
					: response.message || "Connection successful.",
			});
		} else {
			toast.error("Connection failed", { description: response?.error || "Unable to connect." });
		}
	} catch (e) {
		toast.error("Connection failed", { description: e?.message || String(e) });
	} finally {
		isTesting.value = false;
	}
}

async function fetchOllamaModels() {
	try {
		const response = await call("nakhoda.api.ai.test_connection", {
			provider: selectedProvider.value === "ollama_cloud" ? "ollama_cloud" : "ollama",
		});
		if (response?.success && response.data?.models) ollamaModels.value = response.data.models;
	} catch {
		// Silent - the model box falls back to free text.
	}
}

const OLLAMA_CLOUD_URL = "https://ollama.com";
const LOOPBACK_HOSTS = ["localhost", "127.0.0.1", "0.0.0.0", "::1"];

const isOllamaCloud = computed(() => selectedProvider.value === "ollama_cloud");

/** Mirrors `providers._is_loopback` so the UI shows what the server will use. */
function isLoopbackUrl(url) {
	if (!url) return true;
	const host = url
		.replace(/^\w+:\/\//, "")
		.split("/")[0]
		.split(":")[0]
		.replace(/[[\]]/g, "");
	return LOOPBACK_HOSTS.includes(host.toLowerCase());
}

/**
 * `ollama_base_url` ships pointing at localhost, which is meaningless for
 * Ollama Cloud. Present it as empty there so the cloud placeholder shows, while
 * still letting a genuine remote override through.
 */
const ollamaBaseUrl = computed({
	get() {
		const stored = settings.doc.ollama_base_url || "";
		if (isOllamaCloud.value && isLoopbackUrl(stored)) return "";
		return stored;
	},
	set(value) {
		settings.doc.ollama_base_url = value;
	},
});

const effectiveOllamaUrl = computed(() => {
	const stored = settings.doc.ollama_base_url || "";
	if (isOllamaCloud.value) return isLoopbackUrl(stored) ? OLLAMA_CLOUD_URL : stored;
	return stored || "http://localhost:11434";
});

const chatgpt = useDeviceLogin("chatgpt");
const kimi = useDeviceLogin("kimi");

const usesSubscription = computed(() => settings.doc.openai_auth_mode === "ChatGPT Subscription");
const usesKimiSubscription = computed(() => settings.doc.moonshot_auth_mode === "Kimi Subscription");

/**
 * Disconnecting resets the auth mode server-side
 * (`chatgpt_subscription_auth.disconnect_chatgpt` / `kimi_subscription_auth.disconnect_kimi`),
 * so mirror that one field locally - otherwise the select keeps showing a
 * subscription with nothing connected until the next full reload. Only this
 * field is touched, never a document reload: a reload here would discard
 * whatever else the admin has typed but not saved.
 *
 * Connecting needs no counterpart. The login panel only renders once the
 * select already says "Subscription", which is the value the backend writes.
 */
async function disconnect(login, fieldname) {
	await login.disconnect();
	settings.doc[fieldname] = "API Key";
}

onUnmounted(() => {
	chatgpt.stop();
	kimi.stop();
});

watch(selectedProvider, (value) => {
	if (value === "ollama" || value === "ollama_cloud") {
		// Local and cloud serve different catalogs - never show one for the other.
		ollamaModels.value = [];
		fetchOllamaModels();
	}
	if (value === "openai") chatgpt.refresh();
	if (value === "moonshot") kimi.refresh();
});

onMounted(() => {
	fetchAIStatus();
	if (selectedProvider.value === "ollama" || selectedProvider.value === "ollama_cloud") {
		fetchOllamaModels();
	}
	if (selectedProvider.value === "openai") chatgpt.refresh();
	if (selectedProvider.value === "moonshot") kimi.refresh();
});
</script>

<template>
	<div class="flex h-full flex-col gap-6 overflow-y-auto p-8">
		<div v-if="settings.loading.value" class="flex flex-1 items-center justify-center">
			<LoadingIndicator class="size-6" />
		</div>
		<div
			v-else-if="settings.error.value"
			class="max-w-2xl rounded-sm border border-outline-red-2 bg-surface-red-1 p-4 text-sm text-ink-red-6"
		>
			Could not load settings.
		</div>

		<template v-else>
			<!-- Header -->
			<div class="flex items-center justify-between">
				<div>
					<h1 class="text-xl font-semibold text-ink-gray-9">AI Provider</h1>
					<p class="mt-1 text-sm text-ink-gray-6">
						Which model answers questions, and the credential it uses.
					</p>
				</div>
				<Badge v-if="settings.doc.enable_ai" variant="subtle" theme="green" size="md">Active</Badge>
				<Badge v-else variant="subtle" theme="gray" size="md">Inactive</Badge>
			</div>

			<!-- One switch shape for every boolean in this dialog. Insights renders
			     this particular one as a labelled checkbox (`src2/settings/AISettings.vue`)
			     while its Data Store and Permissions tabs use a pill switch - drift
			     inside one dialog, not a distinction, so this follows the switch. -->
			<SettingItem
				label="Enable AI"
				description="Off: no model is ever called - verified queries, the query builder and dashboards still run."
			>
				<Toggle v-model="settings.doc.enable_ai" />
			</SettingItem>

			<template v-if="settings.doc.enable_ai">
				<!-- Provider Selection -->
				<div class="border-t border-outline-gray-2 pt-6">
					<h2 class="mb-3 text-base font-medium text-ink-gray-8">Provider</h2>
					<div class="grid grid-cols-2 gap-3">
						<label
							v-for="p in providerOptions"
							:key="p.value"
							class="relative flex cursor-pointer items-start gap-3 rounded-lg border p-4 transition-all motion-reduce:transition-none"
							:class="
								selectedProvider === p.value
									? 'border-outline-blue-2 bg-surface-blue-1 ring-1 ring-outline-blue-1'
									: 'border-outline-gray-1 hover:border-outline-gray-2 hover:bg-surface-gray-1'
							"
						>
							<input
								type="radio"
								:value="p.value"
								v-model="settings.doc.ai_provider"
								class="mt-0.5"
							/>
							<div class="min-w-0 flex-1">
								<div class="text-sm font-medium text-ink-gray-9">{{ p.label }}</div>
								<div class="mt-0.5 text-xs text-ink-gray-6">{{ p.desc }}</div>
							</div>
						</label>
					</div>
				</div>

				<!-- OpenRouter Config -->
				<div v-if="selectedProvider === 'openrouter'" class="space-y-5 border-t border-outline-gray-2 pt-6">
					<h2 class="text-base font-medium text-ink-gray-8">OpenRouter Settings</h2>

					<div>
						<label class="mb-1.5 block text-sm font-medium text-ink-gray-6">API Key</label>
						<div class="flex gap-2">
							<FormControl
								type="password"
								v-model="settings.doc.openrouter_api_key"
								placeholder="sk-or-v1-..."
								class="flex-1"
							/>
							<Button variant="outline" :loading="isTesting" @click="testConnection">Test</Button>
						</div>
						<p class="mt-1 text-xs text-ink-gray-5">Get your key at openrouter.ai/keys</p>
					</div>

					<div class="grid grid-cols-2 gap-4">
						<div>
							<label class="mb-1.5 block text-sm font-medium text-ink-gray-6">Primary Model</label>
							<select
								v-model="settings.doc.ai_model"
								class="w-full rounded-md border border-outline-gray-2 bg-surface-white px-3 py-[7px] text-sm focus:outline-none focus:ring-1 focus:ring-outline-gray-3"
							>
								<optgroup v-for="group in modelOptions" :key="group.group" :label="group.group">
									<option v-for="opt in group.options" :key="opt.value" :value="opt.value">
										{{ opt.label }}
									</option>
								</optgroup>
							</select>
							<p class="mt-1 text-xs text-ink-gray-5">The FAST tier's model.</p>
						</div>
						<div>
							<label class="mb-1.5 block text-sm font-medium text-ink-gray-6">Fallback Model</label>
							<select
								v-model="settings.doc.ai_model_fallback"
								class="w-full rounded-md border border-outline-gray-2 bg-surface-white px-3 py-[7px] text-sm focus:outline-none focus:ring-1 focus:ring-outline-gray-3"
							>
								<optgroup v-for="group in modelOptions" :key="group.group" :label="group.group">
									<option v-for="opt in group.options" :key="opt.value" :value="opt.value">
										{{ opt.label }}
									</option>
								</optgroup>
							</select>
							<p class="mt-1 text-xs text-ink-gray-5">
								The BALANCED tier - tried after a validation failure.
							</p>
						</div>
					</div>
				</div>

				<!-- OpenAI Config -->
				<div v-if="selectedProvider === 'openai'" class="space-y-5 border-t border-outline-gray-2 pt-6">
					<h2 class="text-base font-medium text-ink-gray-8">OpenAI Settings</h2>

					<div>
						<label class="mb-1.5 block text-sm font-medium text-ink-gray-6">Authentication</label>
						<select
							v-model="settings.doc.openai_auth_mode"
							class="w-full rounded-md border border-outline-gray-2 bg-surface-white px-3 py-[7px] text-sm focus:outline-none focus:ring-1 focus:ring-outline-gray-3"
						>
							<option value="API Key">API Key - metered, billed per token</option>
							<option value="ChatGPT Subscription">ChatGPT Subscription - Plus/Pro account</option>
						</select>
					</div>

					<!-- ChatGPT subscription login -->
					<div
						v-if="usesSubscription"
						class="space-y-3 rounded-lg border border-outline-gray-2 bg-surface-gray-1 p-4"
					>
						<div v-if="chatgpt.status.value.connected" class="flex items-center justify-between gap-3">
							<div>
								<p class="text-sm font-medium text-ink-gray-8">Connected</p>
								<p class="mt-0.5 text-xs text-ink-gray-6">
									{{ chatgpt.status.value.account_label }}
									<span v-if="chatgpt.status.value.expired" class="text-ink-red-3">
										· token expired, will refresh on next call</span
									>
								</p>
							</div>
							<Button
								variant="subtle"
								theme="red"
								@click="disconnect(chatgpt, 'openai_auth_mode')"
								>Disconnect</Button
							>
						</div>

						<div v-else-if="chatgpt.state.value === 'waiting'" class="space-y-2">
							<p class="text-sm text-ink-gray-8">
								Enter this code at
								<a
									:href="chatgpt.url.value"
									target="_blank"
									rel="noopener"
									class="text-ink-blue-3 underline"
									>{{ chatgpt.url.value }}</a
								>
							</p>
							<p class="font-mono text-2xl font-semibold tracking-widest text-ink-gray-9">
								{{ chatgpt.code.value }}
							</p>
							<p class="text-xs text-ink-gray-5">Waiting for approval…</p>
						</div>

						<div v-else class="flex items-center justify-between gap-3">
							<div>
								<p class="text-sm font-medium text-ink-gray-8">Not connected</p>
								<p class="mt-0.5 text-xs text-ink-gray-6">
									Sign in with a ChatGPT Plus/Pro account instead of an API key.
								</p>
							</div>
							<Button
								variant="solid"
								@click="chatgpt.start()"
								>Connect ChatGPT</Button
							>
						</div>

						<p v-if="chatgpt.error.value" class="text-xs text-ink-red-3">{{ chatgpt.error.value }}</p>
					</div>

					<div class="grid grid-cols-2 gap-4">
						<div v-if="!usesSubscription">
							<label class="mb-1.5 block text-sm font-medium text-ink-gray-6">API Key</label>
							<div class="flex gap-2">
								<FormControl
									type="password"
									v-model="settings.doc.openai_api_key"
									placeholder="sk-..."
									class="flex-1"
								/>
								<Button variant="outline" :loading="isTesting" @click="testConnection">Test</Button>
							</div>
							<p class="mt-1 text-xs text-ink-gray-5">
								API key from platform.openai.com/api-keys, or the bearer token of your gateway.
							</p>
						</div>
						<div :class="usesSubscription ? 'col-span-2' : ''">
							<label class="mb-1.5 block text-sm font-medium text-ink-gray-6">Model</label>
							<select
								v-model="settings.doc.openai_model"
								class="w-full rounded-md border border-outline-gray-2 bg-surface-white px-3 py-[7px] text-sm focus:outline-none focus:ring-1 focus:ring-outline-gray-3"
							>
								<optgroup v-for="g in catalogs.openai" :key="g.group" :label="g.group">
									<option v-for="m in g.options" :key="m.value" :value="m.value">
										{{ m.label }}
									</option>
								</optgroup>
							</select>
						</div>
					</div>

					<div v-if="!usesSubscription">
						<label class="mb-1.5 block text-sm font-medium text-ink-gray-6">Base URL</label>
						<FormControl
							type="text"
							v-model="settings.doc.openai_base_url"
							placeholder="https://api.openai.com/v1"
						/>
						<p class="mt-1 text-xs text-ink-gray-5">
							Leave as-is for a metered OpenAI API key, or point it at any
							OpenAI-compatible gateway.
						</p>
					</div>
				</div>

				<!-- NVIDIA Config -->
				<div v-if="selectedProvider === 'nvidia'" class="space-y-5 border-t border-outline-gray-2 pt-6">
					<h2 class="text-base font-medium text-ink-gray-8">NVIDIA NIM Settings</h2>

					<div class="grid grid-cols-2 gap-4">
						<div>
							<label class="mb-1.5 block text-sm font-medium text-ink-gray-6">API Key</label>
							<div class="flex gap-2">
								<FormControl
									type="password"
									v-model="settings.doc.nvidia_api_key"
									placeholder="nvapi-..."
									class="flex-1"
								/>
								<Button variant="outline" :loading="isTesting" @click="testConnection">Test</Button>
							</div>
							<p class="mt-1 text-xs text-ink-gray-5">Get your key at build.nvidia.com</p>
						</div>
						<div>
							<label class="mb-1.5 block text-sm font-medium text-ink-gray-6">Model</label>
							<select
								v-model="settings.doc.nvidia_model"
								class="w-full rounded-md border border-outline-gray-2 bg-surface-white px-3 py-[7px] text-sm focus:outline-none focus:ring-1 focus:ring-outline-gray-3"
							>
								<optgroup v-for="g in catalogs.nvidia" :key="g.group" :label="g.group">
									<option v-for="m in g.options" :key="m.value" :value="m.value">
										{{ m.label }}
									</option>
								</optgroup>
							</select>
						</div>
					</div>
				</div>

				<!-- Ollama Config -->
				<div
					v-if="selectedProvider === 'ollama' || selectedProvider === 'ollama_cloud'"
					class="space-y-5 border-t border-outline-gray-2 pt-6"
				>
					<div>
						<h2 class="text-base font-medium text-ink-gray-8">
							{{ isOllamaCloud ? "Ollama Cloud Settings" : "Ollama Settings" }}
						</h2>
						<p class="mt-1 text-xs text-ink-gray-6">
							{{
								isOllamaCloud
									? "Remote Ollama instance. Enter the URL of your hosted Ollama server."
									: "Runs locally on this machine. Make sure Ollama is running before testing."
							}}
						</p>
					</div>

					<div v-if="isOllamaCloud">
						<label class="mb-1.5 block text-sm font-medium text-ink-gray-6">API Key</label>
						<FormControl
							type="password"
							v-model="settings.doc.ollama_api_key"
							placeholder="ollama-..."
						/>
						<p class="mt-1 text-xs text-ink-gray-5">
							Required for ollama.com. Get your key from your Ollama account.
						</p>
					</div>

					<div class="grid grid-cols-2 gap-4">
						<div>
							<label class="mb-1.5 block text-sm font-medium text-ink-gray-6">Base URL</label>
							<div class="flex gap-2">
								<FormControl
									type="text"
									v-model="ollamaBaseUrl"
									:placeholder="isOllamaCloud ? 'https://ollama.com' : 'http://localhost:11434'"
									class="flex-1"
								/>
								<Button variant="outline" :loading="isTesting" @click="testConnection">Test</Button>
							</div>
							<p class="mt-1 text-xs text-ink-gray-5">
								Requests go to <span class="font-mono">{{ effectiveOllamaUrl }}</span
								>.
								<template v-if="isOllamaCloud">
									A localhost address is ignored for Ollama Cloud.</template
								>
							</p>
						</div>
						<div>
							<label class="mb-1.5 block text-sm font-medium text-ink-gray-6">Model</label>
							<FormControl
								v-if="ollamaModels.length === 0"
								type="text"
								v-model="settings.doc.ollama_model"
								placeholder="llama3.1"
							/>
							<select
								v-else
								v-model="settings.doc.ollama_model"
								class="w-full rounded-md border border-outline-gray-2 bg-surface-white px-3 py-[7px] text-sm focus:outline-none focus:ring-1 focus:ring-outline-gray-3"
							>
								<option v-for="m in ollamaModels" :key="m" :value="m">{{ m }}</option>
							</select>
							<p class="mt-1 text-xs text-ink-gray-5">
								{{
									ollamaModels.length > 0
										? `${ollamaModels.length} models detected`
										: "Test connection to discover models"
								}}
							</p>
						</div>
					</div>
				</div>

				<!-- Kimi / Moonshot Config -->
				<div v-if="selectedProvider === 'moonshot'" class="space-y-5 border-t border-outline-gray-2 pt-6">
					<h2 class="text-base font-medium text-ink-gray-8">Kimi (Moonshot) Settings</h2>

					<div>
						<label class="mb-1.5 block text-sm font-medium text-ink-gray-6">Authentication</label>
						<select
							v-model="settings.doc.moonshot_auth_mode"
							class="w-full rounded-md border border-outline-gray-2 bg-surface-white px-3 py-[7px] text-sm focus:outline-none focus:ring-1 focus:ring-outline-gray-3"
						>
							<option value="API Key">API Key - Moonshot Open Platform, billed per token</option>
							<option value="Kimi Subscription">Kimi Subscription - Kimi Code plan</option>
						</select>
						<p class="mt-1 text-xs text-ink-gray-5">
							These are separate services. A Moonshot Open Platform key is rejected by the Kimi
							Code endpoint, and a subscription serves the kimi-for-coding models.
						</p>
					</div>

					<!-- Kimi subscription login -->
					<div
						v-if="usesKimiSubscription"
						class="space-y-3 rounded-lg border border-outline-gray-2 bg-surface-gray-1 p-4"
					>
						<div v-if="kimi.status.value.connected" class="flex items-center justify-between gap-3">
							<div>
								<p class="text-sm font-medium text-ink-gray-8">Connected</p>
								<p class="mt-0.5 text-xs text-ink-gray-6">
									{{ kimi.status.value.account_label }}
									<span v-if="kimi.status.value.expired" class="text-ink-red-3">
										· token expired, will refresh on next call</span
									>
								</p>
							</div>
							<Button
								variant="subtle"
								theme="red"
								@click="disconnect(kimi, 'moonshot_auth_mode')"
								>Disconnect</Button
							>
						</div>

						<div v-else-if="kimi.state.value === 'waiting'" class="space-y-2">
							<p class="text-sm text-ink-gray-8">
								Enter this code at
								<a
									:href="kimi.url.value"
									target="_blank"
									rel="noopener"
									class="text-ink-blue-3 underline"
									>kimi.com/code/authorize_device</a
								>
							</p>
							<p class="font-mono text-2xl font-semibold tracking-widest text-ink-gray-9">
								{{ kimi.code.value }}
							</p>
							<p class="text-xs text-ink-gray-5">Waiting for approval…</p>
						</div>

						<div v-else class="flex items-center justify-between gap-3">
							<div>
								<p class="text-sm font-medium text-ink-gray-8">Not connected</p>
								<p class="mt-0.5 text-xs text-ink-gray-6">
									Sign in to a Kimi Code plan instead of using an API key.
								</p>
							</div>
							<Button
								variant="solid"
								@click="kimi.start()"
								>Connect Kimi</Button
							>
						</div>

						<p v-if="kimi.error.value" class="text-xs text-ink-red-3">{{ kimi.error.value }}</p>
					</div>

					<div class="grid grid-cols-2 gap-4">
						<div v-if="!usesKimiSubscription">
							<label class="mb-1.5 block text-sm font-medium text-ink-gray-6">API Key</label>
							<div class="flex gap-2">
								<FormControl
									type="password"
									v-model="settings.doc.moonshot_api_key"
									placeholder="sk-..."
									class="flex-1"
								/>
								<Button variant="outline" :loading="isTesting" @click="testConnection">Test</Button>
							</div>
							<p class="mt-1 text-xs text-ink-gray-5">Get your key at platform.moonshot.ai</p>
						</div>
						<div v-if="!usesKimiSubscription">
							<label class="mb-1.5 block text-sm font-medium text-ink-gray-6">Model</label>
							<select
								v-model="settings.doc.moonshot_model"
								class="w-full rounded-md border border-outline-gray-2 bg-surface-white px-3 py-[7px] text-sm focus:outline-none focus:ring-1 focus:ring-outline-gray-3"
							>
								<optgroup v-for="g in catalogs.moonshot" :key="g.group" :label="g.group">
									<option v-for="m in g.options" :key="m.value" :value="m.value">
										{{ m.label }}
									</option>
								</optgroup>
							</select>
						</div>
					</div>
				</div>

				<!-- Schedule & Limits -->
				<div class="space-y-5 border-t border-outline-gray-2 pt-6">
					<h2 class="text-base font-medium text-ink-gray-8">Schedule & Limits</h2>

					<div class="grid grid-cols-2 gap-4">
						<div>
							<label class="mb-1.5 block text-sm font-medium text-ink-gray-6">Quota Reset</label>
							<select
								v-model="settings.doc.quota_reset_schedule"
								class="w-full rounded-md border border-outline-gray-2 bg-surface-white px-3 py-[7px] text-sm focus:outline-none focus:ring-1 focus:ring-outline-gray-3"
							>
								<option v-for="opt in scheduleOptions" :key="opt.value" :value="opt.value">
									{{ opt.label }}
								</option>
							</select>
							<p class="mt-1 text-xs text-ink-gray-5">
								How often the quota below resets. Disabled: it never resets on its own.
							</p>
						</div>
						<div>
							<label class="mb-1.5 block text-sm font-medium text-ink-gray-6">Request Quota</label>
							<div class="flex items-center gap-2">
								<FormControl
									type="number"
									v-model="settings.doc.daily_ai_quota"
									:min="0"
									class="w-24"
								/>
								<span class="text-sm text-ink-gray-5">
									questions per window (0 = no cap)
								</span>
							</div>
						</div>
					</div>
				</div>

				<!-- Usage Status -->
				<div class="border-t border-outline-gray-2 pt-6">
					<h2 class="mb-3 text-base font-medium text-ink-gray-8">Usage</h2>
					<div class="grid grid-cols-3 gap-3">
						<div class="rounded-lg border border-outline-gray-1 bg-surface-gray-1 p-3.5">
							<p class="text-xs font-medium uppercase tracking-wide text-ink-gray-6">
								Quota This Window
							</p>
							<p class="mt-1 text-lg font-semibold text-ink-gray-9">
								{{ aiStatus.quota_used || 0
								}}<span class="text-sm font-normal text-ink-gray-5">
									/ {{ aiStatus.unlimited ? "∞" : settings.doc.daily_ai_quota || 100 }}</span
								>
							</p>
							<div class="mt-2 h-1.5 w-full rounded-full bg-surface-gray-3">
								<div
									:class="[quotaColor, 'h-1.5 rounded-full transition-all motion-reduce:transition-none']"
									:style="`width: ${aiStatus.unlimited ? 0 : quotaPercent}%`"
								></div>
							</div>
						</div>
						<div class="rounded-lg border border-outline-gray-1 bg-surface-gray-1 p-3.5">
							<p class="text-xs font-medium uppercase tracking-wide text-ink-gray-6">Last Answer</p>
							<p class="mt-1 text-sm font-medium text-ink-gray-9">
								{{ formatDate(aiStatus.last_answer) }}
							</p>
						</div>
						<div class="rounded-lg border border-outline-gray-1 bg-surface-gray-1 p-3.5">
							<p class="text-xs font-medium uppercase tracking-wide text-ink-gray-6">Provider</p>
							<p class="mt-1 text-sm font-medium text-ink-gray-9">
								{{
									providerOptions.find((p) => p.value === selectedProvider)?.label ||
									selectedProvider
								}}
							</p>
						</div>
					</div>
				</div>
			</template>

			<div
				v-if="settings.saveError.value"
				class="rounded-sm border border-outline-red-2 bg-surface-red-1 p-3 text-sm text-ink-red-6"
			>
				Could not save settings.
			</div>

			<!-- Save Button -->
			<div class="flex justify-end border-t border-outline-gray-2 pt-4">
				<Button
					label="Save"
					variant="solid"
					theme="gray"
					:disabled="!settings.isDirty.value"
					:loading="settings.saving.value"
					@click="settings.save()"
				/>
			</div>
		</template>
	</div>
</template>
