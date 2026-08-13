import { test, expect } from "@playwright/test";

/**
 * Phase 5 gate (`12-build-plan.md` §5, gate index row "5 - badges are
 * distinguishable"): "0 WCAG AA text failures across every screen x light
 * and dark, measured on the rendered DOM. The mockup passes both today,
 * and got there by failing them: 87 light and 17 dark contrast failures
 * before two text token roles were defined." This runs the same audit
 * against the shipped Ask screen, closed and with the inspector open, in
 * both themes.
 */
async function contrastFailures(page) {
	return await page.evaluate(() => {
		function parseRgb(str) {
			const m = str.match(/rgba?\(([^)]+)\)/);
			if (!m) return null;
			const parts = m[1].split(",").map((s) => parseFloat(s.trim()));
			const [r, g, b, a = 1] = parts;
			if (a === 0) return null; // fully transparent - not a real background
			return { r, g, b, a };
		}

		function relLuminance({ r, g, b }) {
			const chan = (c) => {
				const s = c / 255;
				return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
			};
			return 0.2126 * chan(r) + 0.7152 * chan(g) + 0.0722 * chan(b);
		}

		function contrastRatio(a, b) {
			const la = relLuminance(a) + 0.05;
			const lb = relLuminance(b) + 0.05;
			return la > lb ? la / lb : lb / la;
		}

		function effectiveBackground(el) {
			let node = el;
			while (node) {
				const bg = parseRgb(getComputedStyle(node).backgroundColor);
				if (bg && bg.a >= 0.99) return bg;
				node = node.parentElement;
			}
			return { r: 255, g: 255, b: 255 }; // canvas default
		}

		const failures = [];
		const all = document.querySelectorAll("body *");
		for (const el of all) {
			if (el.children.length > 0 && !Array.from(el.childNodes).some((n) => n.nodeType === 3 && n.textContent.trim()))
				continue; // only elements carrying their own visible text, not pure wrappers
			const text = el.textContent.trim();
			if (!text) continue;
			const style = getComputedStyle(el);
			if (style.visibility === "hidden" || style.display === "none" || Number(style.opacity) === 0) continue;
			const rect = el.getBoundingClientRect();
			if (rect.width === 0 || rect.height === 0) continue;

			const fg = parseRgb(style.color);
			if (!fg) continue;
			const bg = effectiveBackground(el);
			const ratio = contrastRatio(fg, bg);

			const px = parseFloat(style.fontSize);
			const weight = parseInt(style.fontWeight, 10) || 400;
			const isLarge = px >= 24 || (px >= 18.66 && weight >= 700);
			const required = isLarge ? 3 : 4.5;

			if (ratio < required) {
				failures.push({
					text: text.slice(0, 40),
					tag: el.tagName.toLowerCase(),
					className: el.className?.toString?.() || "",
					ratio: Math.round(ratio * 100) / 100,
					required,
				});
			}
		}
		return failures;
	});
}

for (const theme of ["light", "dark"]) {
	test(`0 WCAG AA text contrast failures - ${theme}, inspector closed`, async ({ page }) => {
		await page.goto("./");
		if (theme === "dark") await page.evaluate(() => document.documentElement.setAttribute("data-theme", "dark"));
		const failures = await contrastFailures(page);
		expect(failures, JSON.stringify(failures, null, 2)).toEqual([]);
	});

	test(`0 WCAG AA text contrast failures - ${theme}, inspector open`, async ({ page }) => {
		await page.goto("./");
		if (theme === "dark") await page.evaluate(() => document.documentElement.setAttribute("data-theme", "dark"));
		await page.getByRole("button", { name: /Inspect \d+ steps/ }).click();
		await expect(page.locator(".inspector")).toBeVisible();
		const failures = await contrastFailures(page);
		expect(failures, JSON.stringify(failures, null, 2)).toEqual([]);
	});
}
