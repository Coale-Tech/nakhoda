/**
 * Demo data for the Ask screen, shaped like the fields Phase 4's
 * `Nakhoda Agent Run` doctype actually records (`agent_run.json`) plus the
 * `Nakhoda Verified Query` fields for turn 2 - not invented shapes, so
 * wiring this to the real `execute`/`run_verified` endpoints later is a
 * data-source swap, not a re-model. Numbers copied verbatim from
 * `docs/design/mockup/index.html` turns 1-2.
 */
export const turns = [
	{
		id: "t1",
		kind: "generated",
		question: "What was our revenue in 2026 so far, by territory?",
		trace: { summary: "Resolved 4 entities, 1 join path, 5 operations", ticks: 5, seconds: 1.9 },
		answer: {
			icon: "sparkle",
			label: "Generated",
			title: "Sales Invoice → Customer → Territory · FY 2026 to date",
			stepCount: 5,
			metric: {
				value: "₹62.4 L",
				delta: "-13.7%",
				caption: "Net of tax, excluding returns · 480 invoices · 1 Jan – 11 Aug 2026 · vs ₹72.3 L same period 2025",
			},
			chart: {
				series: [
					{ label: "Texas", value: 18.2 },
					{ label: "Maharashtra", value: 17.9 },
					{ label: "California", value: 16.8 },
					{ label: "Karnataka", value: 9.6, muted: true },
				],
				unit: "₹ lakh · four permitted territories",
			},
			assumptions: {
				applied: 5,
				needsYou: 1,
				rows: [
					{ tag: "docstatus", state: "applied", html: "Counted submitted invoices only - drafts and cancelled excluded (<code>docstatus = 1</code>)" },
					{ tag: "measure", state: "applied", html: '"Revenue" resolved to <code>base_net_total</code> - net of tax, in company currency' },
					{ tag: "currency", state: "applied", html: "Summed the <code>base_</code> column, so multi-currency invoices are comparable" },
					{ tag: "join", state: "applied", html: "Territory reached via <code>Sales Invoice.customer → Customer.territory</code> (Link graph)" },
					{ tag: "grain", state: "applied", html: "Aggregated at invoice grain - no child-table fan-out" },
					{ tag: "returns", state: "needs_you", html: "Credit notes excluded (<code>is_return = 0</code>) - <b>you did not specify</b>" },
				],
				ambiguity: {
					counterfactual: 'Netting returns off would give <b>₹59.5 L</b>. Which do you mean by "revenue"?',
					altLabel: "Net of returns",
					keepLabel: "Keep gross",
				},
			},
			notice: { excludedCount: 232, excludedAmount: "₹39.2 L", reason: "territory permissions" },
			receipt: {
				segments: [
					{ html: "<b>5</b> operations" },
					{ html: "<b>2</b> tables" },
					{ html: "<b>0.4s</b> query" },
					{ html: "<b>1,204</b> tokens" },
					{ html: "<b>$0.0031</b>" },
				],
			},
		},
	},
	{
		id: "t2",
		kind: "verified",
		question: "And how much is still unpaid?",
		trace: { summary: 'Matched verified query "Outstanding receivables" - no SQL generated', ticks: 0, seconds: 0.1 },
		answer: {
			icon: "verified",
			label: "Verified",
			title: "Approved by Meera Shah · Finance · 14 Jul 2026 · used 89×",
			metric: { value: "₹1.60 Cr", caption: "Outstanding across 1,034 submitted invoices · 921 overdue > 90 days" },
			table: {
				columns: [
					{ label: "Ageing bucket" },
					{ label: "Invoices", align: "num" },
					{ label: "Outstanding", align: "num" },
					{ label: "Share", align: "num" },
				],
				rows: [
					{ cells: [{ text: "Not due" }, { text: "14" }, { text: "₹0.03 Cr" }, { text: "1.6%", muted: true }] },
					{ cells: [{ text: "1 - 30 days" }, { text: "32" }, { text: "₹0.05 Cr" }, { text: "3.4%", muted: true }] },
					{ cells: [{ text: "31 - 90 days" }, { text: "67" }, { text: "₹0.11 Cr" }, { text: "6.8%", muted: true }] },
					{ cells: [{ text: "> 90 days" }, { text: "921" }, { text: "₹1.41 Cr" }, { text: "88.2%", muted: true }] },
				],
			},
			receipt: {
				segments: [
					{ html: "<b>Verified query</b> · parameters: company, as_of_date" },
					{ html: "<b>0.1s</b>" },
					{ html: "<b>0</b> tokens" },
				],
			},
		},
	},
];
