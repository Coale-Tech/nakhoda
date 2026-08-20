/**
 * Mocks for `useSemantic.js` - the five `nakhoda.api.semantic.*` endpoints the
 * Semantic Model tab reads.
 *
 * Two rows, chosen to cover the two states the tab renders differently: one
 * curated document with synonyms, and one child table whose `parent_doctypes`
 * is empty - the orphan case the design contract asks to be flagged rather
 * than silently ranked (`docs/design/14-frontend-design.md` §2).
 *
 * `save_model` echoes the fields it was sent back through `get_model`'s shape,
 * mirroring `mockSettings`'s PUT: a save round-trips through the same component
 * code a real POST would exercise, including the `curated` flip the backend
 * derives - here stated as data, because the derivation itself is graded in
 * `nakhoda/tests/test_curation.py` against a real site.
 */
export const COVERAGE = { used: 439, modelled: 428, curated: 7, with_synonyms: 5, metrics: 3, certified_metrics: 1 };

export const SALES_INVOICE = {
	name: "Sales Invoice",
	doctype_name: "Sales Invoice",
	label: "Sales Invoice",
	grain: "one submitted transaction",
	description: "Revenue this business recognises, one row per invoice sent to a customer.",
	synonyms: "revenue, turnover, billings",
	curated: true,
	is_child: false,
	parent_doctypes: "",
	row_count: 12_480,
	reporting_count: 30,
	empty_column_count: 61,
	token_cost: 2624,
	generated_on: "2026-08-15 09:30:00",
	fields: [
		{
			fieldname: "customer",
			label: "Customer",
			fieldtype: "VARCHAR",
			domain: "link: tabCustomer.name",
			join_target: "Customer",
			synonyms: "client, account",
			empty: false,
		},
		{
			fieldname: "grand_total",
			label: "Grand Total",
			fieldtype: "DECIMAL",
			domain: "",
			join_target: null,
			synonyms: "",
			empty: false,
		},
		{
			fieldname: "po_no",
			label: "Customer's Purchase Order",
			fieldtype: "VARCHAR",
			domain: "",
			join_target: null,
			synonyms: "",
			empty: true,
		},
	],
};

export const ORPHAN_CHILD = {
	name: "Payment Reconciliation Invoice",
	doctype_name: "Payment Reconciliation Invoice",
	label: "Payment Reconciliation Invoice",
	grain: "one child row",
	description: "Payment Reconciliation Invoice: a child with 9 readable columns.",
	synonyms: "",
	curated: false,
	is_child: true,
	parent_doctypes: "",
	row_count: 0,
	reporting_count: 0,
	empty_column_count: 4,
	token_cost: 210,
	generated_on: "2026-08-15 09:30:00",
	fields: [
		{
			fieldname: "invoice_number",
			label: "Invoice Number",
			fieldtype: "VARCHAR",
			domain: "",
			join_target: null,
			synonyms: "",
			empty: false,
		},
	],
};

/** What `list_models` returns: the list omits `description` and `fields`. */
export function listRow(doc) {
	const { description, fields, ...row } = doc;
	return row;
}

/**
 * Mock the Semantic Model tab's endpoints. Call before `page.goto`.
 *
 * `queued` overrides what `regenerate` reports, so a test can drive both the
 * accepted and the already-running branch.
 */
export async function mockSemantic(page, { docs = [SALES_INVOICE, ORPHAN_CHILD], coverage = COVERAGE, queued } = {}) {
	const byName = new Map(docs.map((doc) => [doc.name, structuredClone(doc)]));
	// What the generator would have written, so `curated` can turn back off the way
	// the checksum comparison in the controller does.
	const generated = new Map(docs.map((doc) => [doc.name, doc.curated ? null : doc.description]));

	await page.route("**/api/v2/method/nakhoda.api.semantic.coverage**", (route) =>
		route.fulfill({ json: { data: coverage } }),
	);
	await page.route("**/api/v2/method/nakhoda.api.semantic.list_models**", (route) =>
		route.fulfill({ json: { data: [...byName.values()].map(listRow) } }),
	);
	await page.route("**/api/v2/method/nakhoda.api.semantic.get_model**", (route) => {
		const name = new URL(route.request().url()).searchParams.get("name");
		return route.fulfill({ json: { data: byName.get(name) || byName.values().next().value } });
	});
	await page.route("**/api/v2/method/nakhoda.api.semantic.save_model**", (route) => {
		const body = route.request().postDataJSON() || {};
		const doc = byName.get(body.name) || byName.values().next().value;
		if (body.description != null) doc.description = body.description;
		if (body.synonyms != null) doc.synonyms = body.synonyms;
		const columns = body.field_synonyms ? JSON.parse(body.field_synonyms) : {};
		for (const row of doc.fields) {
			if (columns[row.fieldname] != null) row.synonyms = columns[row.fieldname];
		}
		// The backend derives this from the row (`NakhodaSemanticModel.validate`):
		// prose that differs from the generated description, or a synonym anywhere.
		// Stated here because a fixture that always echoed `curated: true` would
		// hide the badge never turning off.
		doc.curated = Boolean(
			(doc.synonyms || "").trim() ||
				doc.fields.some((row) => (row.synonyms || "").trim()) ||
				((doc.description || "").trim() && doc.description !== generated.get(doc.name)),
		);
		return route.fulfill({ json: { data: doc } });
	});
	await page.route("**/api/v2/method/nakhoda.api.semantic.regenerate**", (route) =>
		route.fulfill({ json: { data: queued || { queued: true, documents: coverage.used } } }),
	);
}
