<script setup>
/**
 * The icon glyph defs, copied verbatim from `docs/design/mockup/index.html`
 * lines 12-27. Mounted once in `App.vue`; `Icon.vue` instances everywhere
 * else just `<use>` a name from here. Kept in its own component instead of
 * a global `index.html` `<svg>` block because Vite serves `index.html`
 * outside Vue's reactivity/SSR boundary and this needs to live with the
 * app that consumes it.
 */
</script>

<template>
	<svg width="0" height="0" style="position: absolute" aria-hidden="true">
		<defs>
			<g id="i-ask"><path d="M8 2.5a5.5 5.5 0 0 0-3.4 9.8V14l2.2-1.2a5.5 5.5 0 1 0 1.2-10.3Z" /></g>
			<g id="i-model">
				<ellipse cx="8" cy="4" rx="5.5" ry="2.2" />
				<path d="M2.5 4v8c0 1.2 2.5 2.2 5.5 2.2s5.5-1 5.5-2.2V4" />
				<path d="M2.5 8c0 1.2 2.5 2.2 5.5 2.2s5.5-1 5.5-2.2" />
			</g>
			<g id="i-verified">
				<path d="M8 1.8 2.8 4v4c0 3.2 2.2 5.6 5.2 6.4 3-.8 5.2-3.2 5.2-6.4V4Z" />
				<path d="m5.9 7.8 1.5 1.5 2.9-3" />
			</g>
			<g id="i-book">
				<path
					d="M2.6 3.2A1.2 1.2 0 0 1 3.8 2h8.4a1.2 1.2 0 0 1 1.2 1.2v9.6a1.2 1.2 0 0 1-1.2 1.2H3.8a1.2 1.2 0 0 1-1.2-1.2Z"
				/>
				<path d="M6 2v12" />
			</g>
			<g id="i-gauge">
				<path d="M13.5 10a5.5 5.5 0 1 0-11 0" />
				<path d="m8 10 2.8-2.8" />
			</g>
			<g id="i-plug">
				<path d="M6 2v4M10 2v4" />
				<path d="M4.5 6h7v2.5a3.5 3.5 0 0 1-7 0Z" />
				<path d="M8 12v2" />
			</g>
			<g id="i-table">
				<rect x="2.2" y="2.8" width="11.6" height="10.4" rx="1.2" />
				<path d="M2.2 6.4h11.6M6.4 6.4v6.8" />
			</g>
			<g id="i-chev"><path d="m6 4 4 4-4 4" /></g>
			<g id="i-check"><path d="m3 8.4 3.2 3.2L13 4.8" /></g>
			<g id="i-alert">
				<path d="M8 2.8 1.8 13.2h12.4Z" />
				<path d="M8 6.6v3M8 11.2v.1" />
			</g>
			<g id="i-lock">
				<rect x="3.2" y="7" width="9.6" height="6.6" rx="1.4" />
				<path d="M5.4 7V5.2a2.6 2.6 0 0 1 5.2 0V7" />
			</g>
			<g id="i-up"><path d="M8 12.5v-9M4.2 7.3 8 3.5l3.8 3.8" /></g>
			<g id="i-eye">
				<path d="M1.5 8S4 3.5 8 3.5 14.5 8 14.5 8 12 12.5 8 12.5 1.5 8 1.5 8Z" />
				<circle cx="8" cy="8" r="1.9" />
			</g>
			<g id="i-play"><path d="M5 3.4 12 8l-7 4.6Z" /></g>
			<g id="i-sparkle"><path d="M8 2.2 9.4 6 13 7.4 9.4 8.8 8 12.6 6.6 8.8 3 7.4 6.6 6Z" /></g>
			<g id="i-moon"><path d="M13 9.4A5.6 5.6 0 0 1 6.6 3a5.6 5.6 0 1 0 6.4 6.4Z" /></g>
		</defs>
	</svg>
</template>
