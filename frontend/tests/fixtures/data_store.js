import { expect } from "@playwright/test";

/**
 * Mocks for the Data Store (`nakhoda.api.data_store.*`) and Data Sources
 * (`nakhoda.api.data_sources.*`) pages. Mirrors `query.js`'s pattern: fixed
 * rows for GET, and POST handlers that mutate an in-memory copy so the UI's
 * refetch flow exercises the same component code a live site would.
 *
 * Two things here are shaped by the backend and not by convenience:
 *
 * - `import_table` *enqueues* (`api/data_store.py`), so its response says only
 *   that a job was accepted. The row reaches "Synced" on a later `list_tables`,
 *   which is what makes `useDataStore`'s poll load-bearing rather than
 *   decorative - `syncAfter` below controls how many polls that takes.
 * - Admin-only actions read `window.boot.is_admin`, which Playwright never gets
 *   from Jinja (see `stores/session.js`). `mockBoot` stubs it before any script
 *   runs; without it the Import / Set Default / Test buttons are correctly
 *   absent and every action assertion would fail for the wrong reason.
 */
export const TABLES_ROWS = [
	{
		doctype: "Sales Invoice",
		label: "Sales Invoice",
		table_name: "tabSales Invoice",
		is_child: false,
		nakhoda_table: null,
		sync_state: "Never",
		row_count: null,
		row_limit: null,
		last_synced: null,
		sync_error: null,
		stored_in_warehouse: false,
	},
	{
		doctype: "Customer",
		label: "Customer",
		table_name: "tabCustomer",
		is_child: false,
		nakhoda_table: "NKT-00001",
		sync_state: "Synced",
		row_count: 480,
		row_limit: null,
		last_synced: "2026-08-14 10:00:00",
		sync_error: null,
		stored_in_warehouse: true,
	},
];

/**
 * The site's `System Settings.time_zone`, as `www/_nakhoda.py` ships it in
 * boot. Offset from the browser's pinned zone (`playwright.config.js`) on
 * purpose: this bench really is an `Asia/Kolkata` site read from
 * `Africa/Nairobi`, and reading its naive timestamps as browser-local dated
 * every freshly synced row two hours into the future.
 */
export const SITE_TIME_ZONE = "Asia/Kolkata";

/**
 * A Frappe-shaped naive timestamp `hours` in the past - written the way the
 * server writes one, in the site's zone rather than the reader's.
 *
 * The Last Checked column renders relative time (`composables/useTimestamp.js`),
 * so a hard-coded date would assert something different every day the calendar
 * advances - "yesterday", then "3 days ago", then "last week".
 */
export function hoursAgo(hours, timeZone = SITE_TIME_ZONE) {
	const at = new Intl.DateTimeFormat("en-CA", {
		timeZone,
		hour12: false,
		year: "numeric",
		month: "2-digit",
		day: "2-digit",
		hour: "2-digit",
		minute: "2-digit",
		second: "2-digit",
	}).formatToParts(new Date(Date.now() - hours * 3_600_000));
	const part = (type) => at.find((p) => p.type === type).value;
	return (
		`${part("year")}-${part("month")}-${part("day")} ` +
		`${part("hour") === "24" ? "00" : part("hour")}:${part("minute")}:${part("second")}`
	);
}

export const SOURCES_ROWS = [
	{
		name: "Nakhoda Data Source",
		title: "Site Database",
		source_type: "Site Database",
		is_default: 1,
		status: "Reachable",
		last_checked: hoursAgo(2),
		table_count: 2,
		owner: "Administrator",
		owner_name: "Administrator",
		creation: hoursAgo(72),
		modified: hoursAgo(2),
	},
	{
		name: "Nakhoda Data Source-1",
		title: "DuckDB Warehouse",
		source_type: "DuckDB Warehouse",
		is_default: 0,
		status: "Untested",
		last_checked: null,
		table_count: 1,
		owner: "Administrator",
		owner_name: "Administrator",
		creation: hoursAgo(72),
		modified: hoursAgo(70),
	},
	{
		name: "Nakhoda Data Source-2",
		title: "Reporting Replica",
		source_type: "External Database",
		database_type: "PostgreSQL",
		is_default: 0,
		status: "Reachable",
		last_checked: hoursAgo(30),
		table_count: 0,
		// A source somebody else configured: the Owner column is the one place
		// this list says who, so a second name proves it is read per row rather
		// than printed from the session.
		owner: "analyst@example.com",
		owner_name: "Amina Analyst",
		creation: hoursAgo(30),
		modified: hoursAgo(4),
		// What the row's own connection is, for the edit form to open on. The
		// password is deliberately absent: `get_data_source` never returns it.
		host: "db.internal",
		port: 5432,
		username: "reader",
		database_name: "reporting",
		schema: "public",
	},
];

/** Rows `get_source_table` previews for `Customer`. */
export const PREVIEW = {
	doctype: "Customer",
	data_source: "Nakhoda Data Source",
	table_name: "tabCustomer",
	columns: ["name", "customer_name", "outstanding"],
	rows: [
		{ name: "CUST-0001", customer_name: "Acme", outstanding: 1200 },
		{ name: "CUST-0002", customer_name: "Globex", outstanding: null },
	],
	row_count: 2,
	truncated: false,
	fetched_at: "2026-08-15 12:30:00",
};

/**
 * A `/api/v2` error exactly as Frappe sends one: the message lives in
 * `errors[0]`, and `frappe-ui`'s fetch layer reads it from there
 * (`useFrappeFetch.ts:89-109`). A v1-shaped `{exception, message}` body parses
 * as no error at all, leaving components with the bare HTTP reason phrase -
 * so a fixture in the wrong shape silently grades the wrong string.
 */
export function frappeError(type, message, status = 417) {
	return {
		status,
		json: { errors: [{ type, message, title: "Message", indicator: "red" }] },
	};
}

/**
 * Stub the Jinja boot payload. `is_admin: false` proves the read-only path -
 * the same page with no write affordances.
 *
 * `dataStoreEnabled` mirrors `www/_nakhoda.py`'s `data_store_enabled` key. It
 * travels in boot rather than being read from `Nakhoda Settings` because an
 * ordinary `Nakhoda User` has no read permission on that Single, so a
 * client-side lookup would 403 for exactly the people the nav gate is for.
 *
 * `timeZone` is that file's `time_zone` key. Pass `null` to render a page that
 * never received it: `timeAgo` then falls back to browser-local, which is what
 * shipped before this key existed.
 */
export async function mockBoot(
	page,
	{ isAdmin = true, dataStoreEnabled = true, timeZone = SITE_TIME_ZONE } = {},
) {
	await page.addInitScript(
		([admin, storeOn, zone]) => {
			window.boot = {
				csrf_token: "test",
				site_name: "test",
				user: { name: "test@example.com", full_name: "Test User" },
				is_admin: admin,
				data_store_enabled: storeOn,
				...(zone ? { time_zone: zone } : {}),
			};
		},
		[isAdmin, dataStoreEnabled, timeZone],
	);
}

/**
 * Mock `list_tables` and `import_table`.
 *
 * `syncAfter` is how many `list_tables` calls a queued import stays "Syncing"
 * for before flipping to "Synced" - `1` (the default) means the very next list
 * shows the finished state, `2+` forces the poll to actually run.
 */
export async function mockDataStore(
	page,
	{ failImport = false, alreadyQueued = false, syncAfter = 1 } = {},
) {
	const rows = TABLES_ROWS.map((r) => ({ ...r }));
	const pending = new Map(); // doctype -> lists remaining before it settles

	await page.route("**/api/v2/method/nakhoda.api.data_store.list_tables**", (route) => {
		for (const [doctype, remaining] of pending) {
			if (remaining > 1) {
				pending.set(doctype, remaining - 1);
				continue;
			}
			pending.delete(doctype);
			const row = rows.find((r) => r.doctype === doctype);
			if (!row) continue;
			if (failImport) {
				row.sync_state = "Failed";
				row.sync_error = "connection refused";
			} else {
				row.sync_state = "Synced";
				row.row_count = 3730;
				row.last_synced = "2026-08-15 12:30:00";
				row.stored_in_warehouse = true;
			}
		}
		const url = new URL(route.request().url());
		const term = (url.searchParams.get("search_term") || "").toLowerCase();
		const filtered = term ? rows.filter((r) => r.label.toLowerCase().includes(term)) : rows;
		return route.fulfill({ json: { data: filtered.map((r) => ({ ...r })) } });
	});

	await page.route("**/api/v2/method/nakhoda.api.data_store.import_table**", (route) => {
		const { doctype, row_limit } = route.request().postDataJSON();
		const row = rows.find((r) => r.doctype === doctype);
		if (alreadyQueued) {
			// The endpoint's own refusal shape: a fact about one table, not an error.
			return route.fulfill({
				json: { data: { queued: false, table: row?.nakhoda_table, log: null, reason: "in_progress" } },
			});
		}
		if (row) {
			row.sync_state = "Syncing";
			row.sync_error = null;
			if (row_limit) row.row_limit = row_limit;
		}
		pending.set(doctype, syncAfter);
		return route.fulfill({ json: { data: { queued: true, table: row?.nakhoda_table, log: "NTIL-0001" } } });
	});
}

/** Mock every `nakhoda.api.data_sources` endpoint the three pages call. */
export async function mockDataSources(page, { previewFails = false, unreachable = false } = {}) {
	const rows = SOURCES_ROWS.map((r) => ({ ...r }));
	const tables = TABLES_ROWS.map((r) => ({
		table: r.doctype,
		doctype: r.doctype,
		label: r.label,
		table_name: r.table_name,
		is_child: r.is_child,
		row_count: r.row_count,
		last_synced: r.last_synced,
		stored_in_warehouse: r.stored_in_warehouse,
	}));

	// Two shapes, as the backend has them: the list carries what its columns
	// show, and only `get_data_source` hands back a connection - so a form built
	// from a list row would open empty, which is the bug this split catches.
	const LIST_FIELDS = [
		"name",
		"title",
		"source_type",
		"database_type",
		"is_default",
		"status",
		"last_checked",
		"table_count",
		"owner",
		"owner_name",
		"creation",
		"modified",
	];
	const listed = (row) => Object.fromEntries(LIST_FIELDS.map((f) => [f, row[f]]));

	await page.route("**/api/v2/method/nakhoda.api.data_sources.list_data_sources**", (route) =>
		route.fulfill({ json: { data: rows.map(listed) } }),
	);

	await page.route("**/api/v2/method/nakhoda.api.data_sources.get_data_source**", (route) => {
		const url = new URL(route.request().url());
		const row = rows.find((r) => r.name === url.searchParams.get("name"));
		if (!row) return route.fulfill({ json: { data: null } });
		// Only an external row has a connection; neither shape carries a password.
		return route.fulfill({
			json: { data: row.source_type === "External Database" ? { ...row } : listed(row) },
		});
	});

	// The warehouse source lists only what was imported; the site database lists
	// everything readable. That split is the whole point of the page.
	await page.route("**/api/v2/method/nakhoda.api.data_sources.list_source_tables**", (route) => {
		const url = new URL(route.request().url());
		const source = rows.find((r) => r.name === url.searchParams.get("data_source"));
		const term = (url.searchParams.get("search_term") || "").toLowerCase();
		let out = tables;
		if (source?.source_type === "DuckDB Warehouse") out = out.filter((t) => t.stored_in_warehouse);
		if (term) out = out.filter((t) => t.label.toLowerCase().includes(term));
		return route.fulfill({ json: { data: out.map((t) => ({ ...t })) } });
	});

	await page.route("**/api/v2/method/nakhoda.api.data_sources.get_source_table**", (route) => {
		if (previewFails) {
			return route.fulfill(frappeError("PermissionError", "Not permitted to read Customer", 403));
		}
		const url = new URL(route.request().url());
		return route.fulfill({ json: { data: { ...PREVIEW, doctype: url.searchParams.get("table") } } });
	});

	await page.route("**/api/v2/method/nakhoda.api.data_sources.test_data_source**", (route) => {
		const { name } = route.request().postDataJSON();
		const row = rows.find((r) => r.name === name);
		if (row) row.status = "Reachable";
		return route.fulfill({ json: { data: { status: "Reachable", message: "Connected." } } });
	});

	await page.route("**/api/v2/method/nakhoda.api.data_sources.set_default_data_source**", (route) => {
		const { name } = route.request().postDataJSON();
		for (const row of rows) row.is_default = row.name === name ? 1 : 0;
		return route.fulfill({ json: { data: { name, is_default: true } } });
	});

	// The New Source form's own probe: an unsaved payload, so there is no row to
	// record the result on. `unreachable` drives the failure branch.
	await page.route("**/api/v2/method/nakhoda.api.data_sources.test_connection**", (route) => {
		const payload = route.request().postDataJSON();
		if (unreachable || payload.host === "nope.invalid") {
			return route.fulfill({
				json: { data: { status: "Unreachable", message: "could not connect to server" } },
			});
		}
		return route.fulfill({ json: { data: { status: "Reachable", message: "Connected." } } });
	});

	await page.route("**/api/v2/method/nakhoda.api.data_sources.create_data_source**", (route) => {
		const payload = route.request().postDataJSON().data_source;
		const row = {
			name: `Nakhoda Data Source-${rows.length}`,
			title: payload.title,
			source_type: "External Database",
			database_type: payload.database_type,
			is_default: 0,
			status: "Untested",
			last_checked: null,
			table_count: 0,
		};
		rows.push(row);
		return route.fulfill({ json: { data: { ...row } } });
	});

	// A re-point writes the fields the form sent, so a second read of the row
	// shows what was saved rather than what it started as.
	await page.route("**/api/v2/method/nakhoda.api.data_sources.update_data_source**", (route) => {
		const { name, data_source: payload } = route.request().postDataJSON();
		const row = rows.find((r) => r.name === name);
		if (row) Object.assign(row, payload, { name: row.name, source_type: row.source_type });
		return route.fulfill({ json: { data: { name, title: row?.title } } });
	});

	await page.route("**/api/v2/method/nakhoda.api.data_sources.delete_data_source**", (route) => {
		const { name } = route.request().postDataJSON();
		const at = rows.findIndex((r) => r.name === name);
		if (at !== -1) rows.splice(at, 1);
		return route.fulfill({ json: { data: { name } } });
	});

	await page.route("**/api/v2/method/nakhoda.api.data_sources.refresh_source_tables**", (route) =>
		route.fulfill({ json: { data: { name: "Nakhoda Data Source", table_count: tables.length } } }),
	);
}

/**
 * Wait for the Data Store screen. Every routed page names itself in the `h-12`
 * header's `Breadcrumbs`, which renders each crumb as a `router-link`. The
 * sidebar carries a link of the same name, so the assertion is scoped to the
 * page header - the one `<header>` in the app (`src/pages/DataStorePage.vue`).
 */
export async function openDataStore(page) {
	await page.goto("./data-store");
	await expect(page.locator("header").getByRole("link", { name: "Data Store" })).toBeVisible();
}

/**
 * Mock the CSV/Excel upload path: frappe's own `upload_file` (which the
 * `FileUploader` posts to directly, not through `useCall`), then the two
 * `nakhoda.api.files` steps the dialog drives.
 *
 * `importFails` proves the dialog surfaces a refused import - the Data Store
 * being switched off is the live version of that failure.
 */
export async function mockUploads(page, { importFails = false } = {}) {
	await page.route("**/api/method/upload_file**", (route) =>
		route.fulfill({
			json: { message: { name: "abc123", file_name: "customers.csv", file_url: "/private/files/customers.csv" } },
		}),
	);

	await page.route("**/api/v2/method/nakhoda.api.files.get_upload_preview**", (route) =>
		route.fulfill({
			json: {
				data: {
					file: "abc123",
					file_name: "customers.csv",
					table: "upload_customers",
					label: "customers",
					extension: "csv",
					columns: [
						{ column: "name", label: "name", type: "string" },
						{ column: "city", label: "city", type: "string" },
					],
					rows: [
						{ name: "Acme", city: "Nairobi" },
						{ name: "Globex", city: "Mombasa" },
					],
					row_count: 2,
					preview_rows: 2,
					truncated: false,
				},
			},
		}),
	);

	await page.route("**/api/v2/method/nakhoda.api.files.import_upload**", (route) => {
		if (importFails) {
			return route.fulfill(
				frappeError("ValidationError", "The Data Store is turned off in Nakhoda Settings."),
			);
		}
		return route.fulfill({
			json: {
				data: { table: "upload_customers", label: "customers", row_count: 2, truncated: false, log: "NTIL-0002" },
			},
		});
	});
}

/** Wait for the Data Sources screen - same breadcrumb contract. */
export async function openDataSources(page) {
	await page.goto("./data-sources");
	await expect(page.locator("header").getByRole("link", { name: "Data Sources" })).toBeVisible();
}
