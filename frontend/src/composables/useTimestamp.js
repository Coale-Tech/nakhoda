import { formatTimeAgo } from "@vueuse/core";

/**
 * Relative time for the list columns that show when something last happened -
 * `last_checked` on Data Sources, `last_synced` on the Data Store and its
 * per-source table list, `generated_on` on the Semantic Model.
 *
 * Insights renders the same class of column through `useTimeAgo`
 * (`src2/data_source/data_source.ts`), and for good reason: a table cell is
 * 11rem wide, so a full Frappe timestamp truncates to
 * `2026-08-15 16:24:50.78…` - the part it cuts is the only part a reader
 * scanning for staleness cares about. `formatTimeAgo` is the one-shot
 * function rather than the `useTimeAgo` ref because these cells re-render
 * from the list call, not from a ticking clock.
 *
 * The exact value moves to the `title` attribute at the call site, so nothing
 * is actually lost - hovering still answers "when precisely".
 */
export function timeAgo(value, fallback = "Never") {
	if (!value) return fallback;
	const parsed = parseSiteTimestamp(value);
	return parsed ? formatTimeAgo(parsed) : String(value);
}

/**
 * Frappe timestamps are naive strings written in the *site's* timezone
 * (`System Settings.time_zone`, read by `utils/data.py:get_system_timezone`),
 * not the reader's and not UTC. `new Date("2026-08-16 21:33:29")` resolves
 * them against the browser's zone instead, which on this bench - an
 * `Asia/Kolkata` site read from `Africa/Nairobi` - rendered a row synced
 * minutes earlier as "in 2 hours". A future-dated staleness column is worse
 * than no column: it says the opposite of the truth.
 *
 * The zone arrives in the boot payload (`www/_nakhoda.py`). Without it - a
 * page rendered before that key existed, or a test that stubs a thinner boot -
 * this falls back to browser-local, which is exactly the old behaviour and
 * correct whenever the two zones agree.
 */
export function parseSiteTimestamp(value) {
	const naive = String(value).trim().replace(" ", "T");
	const local = new Date(naive);
	if (Number.isNaN(local.getTime())) return null;

	const zone = siteTimeZone();
	if (!zone) return local;

	// `naive` read as if it were UTC, then walked back by the site's offset at
	// that moment. Two passes because the offset is itself a function of the
	// instant: a timestamp inside a DST transition needs the offset that
	// applies *there*, not the one an hour off.
	const asUtc = new Date(`${naive.length <= 10 ? `${naive}T00:00:00` : naive}Z`);
	if (Number.isNaN(asUtc.getTime())) return local;
	let instant = new Date(asUtc.getTime() - zoneOffsetMs(asUtc, zone));
	instant = new Date(asUtc.getTime() - zoneOffsetMs(instant, zone));
	return instant;
}

/** How far ahead of UTC `zone` is at `instant`, in milliseconds. */
function zoneOffsetMs(instant, zone) {
	const parts = formatterFor(zone).formatToParts(instant);
	const at = {};
	for (const part of parts) if (part.type !== "literal") at[part.type] = Number(part.value);
	const wall = Date.UTC(at.year, at.month - 1, at.day, at.hour % 24, at.minute, at.second);
	return wall - instant.getTime();
}

const formatters = new Map();

/** One `Intl.DateTimeFormat` per zone: constructing one is the expensive part. */
function formatterFor(zone) {
	let formatter = formatters.get(zone);
	if (!formatter) {
		formatter = new Intl.DateTimeFormat("en-US", {
			timeZone: zone,
			hour12: false,
			year: "numeric",
			month: "2-digit",
			day: "2-digit",
			hour: "2-digit",
			minute: "2-digit",
			second: "2-digit",
		});
		formatters.set(zone, formatter);
	}
	return formatter;
}

let resolvedZone;

/**
 * Read once and remembered, including the "boot never said" answer: this is
 * called per row per render, and an unknown zone must not re-probe
 * `Intl.DateTimeFormat` for every cell.
 */
function siteTimeZone() {
	if (resolvedZone !== undefined) return resolvedZone;
	const zone = window.boot?.time_zone;
	if (!zone) {
		resolvedZone = null;
		return resolvedZone;
	}
	try {
		// A zone the browser's ICU build does not know throws here rather than
		// silently formatting in UTC, which would shift every column instead.
		formatterFor(zone);
		resolvedZone = zone;
	} catch {
		resolvedZone = null;
	}
	return resolvedZone;
}
