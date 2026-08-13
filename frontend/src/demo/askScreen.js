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
			// Mirrors `docs/design/mockup/index.html` lines 741-836 (`data-insp="ask"`).
			// `editable` is false only on the injected permission filter - that step is
			// not the user's to change, so it carries no "Edit" affordance at all.
			inspector: {
				pipeline: [
					{ kind: "source", origin: "question", expr: "tabSales Invoice", editable: true },
					{ kind: "filter", origin: "model", expr: "docstatus == 1", editable: true },
					{
						kind: "filter",
						origin: "model",
						expr: "is_return == 0\nposting_date >= '2026-01-01'",
						editable: true,
					},
					{
						kind: "join",
						origin: "link",
						expr: "tabCustomer on customer == name\n→ territory",
						editable: true,
					},
					{
						kind: "summarize",
						origin: "question",
						expr: "sum(base_net_total) by territory\norder desc",
						editable: true,
					},
					{
						kind: "permission filter",
						origin: "injected",
						expr: "User Permission: Territory in (India,\nUnited States) → tree descendants →\n(Karnataka, Maharashtra, California, Texas)",
						editable: false,
					},
				],
				sql: {
					html:
						'<span class="c">-- not executed yet · 5 operations compiled</span>\n' +
						'<span class="k">SELECT</span> c.<span class="n">territory</span>,\n' +
						'       <span class="k">SUM</span>(si.<span class="n">base_net_total</span>) <span class="k">AS</span> revenue\n' +
						'<span class="k">FROM</span> <span class="s">&quot;tabSales Invoice&quot;</span> si\n' +
						'<span class="k">JOIN</span> <span class="s">&quot;tabCustomer&quot;</span> c <span class="k">ON</span> c.name = si.customer\n' +
						'<span class="k">WHERE</span> si.docstatus = 1\n' +
						'  <span class="k">AND</span> si.is_return = 0\n' +
						"  <span class=\"k\">AND</span> si.posting_date &gt;= <span class=\"s\">'2026-01-01'</span>\n" +
						'  <span class="inj">AND c.territory IN (…4 permitted)</span>\n' +
						'<span class="k">GROUP BY</span> c.<span class="n">territory</span>\n' +
						'<span class="k">ORDER BY</span> revenue <span class="k">DESC</span>\n' +
						'<span class="k">LIMIT</span> 10000',
					plain:
						"-- not executed yet · 5 operations compiled\n" +
						"SELECT c.territory,\n" +
						"       SUM(si.base_net_total) AS revenue\n" +
						'FROM "tabSales Invoice" si\n' +
						'JOIN "tabCustomer" c ON c.name = si.customer\n' +
						"WHERE si.docstatus = 1\n" +
						"  AND si.is_return = 0\n" +
						"  AND si.posting_date >= '2026-01-01'\n" +
						"  AND c.territory IN (…4 permitted)\n" +
						"GROUP BY c.territory\n" +
						"ORDER BY revenue DESC\n" +
						"LIMIT 10000",
				},
				sqlNote:
					"The highlighted line was <b>injected, not generated</b>. It comes from your Frappe User " +
					"Permissions, is compiled into the query before execution, and cannot be removed by anything " +
					"you or the model type into the prompt.",
				scope: [
					{ label: "Rows scanned", value: "712" },
					{ label: "Rows excluded by permissions", value: "232", color: "var(--ink-blue-text)" },
					{ label: "Row cap", value: "10,000" },
					{ label: "Query time", value: "0.41s" },
					{ label: "Tokens in / out", value: "1,038 / 166" },
					{ label: "Cost", value: "$0.0031" },
					{ label: "Semantic model", value: "sm-2026.08.09-a4f1", mono: true },
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
