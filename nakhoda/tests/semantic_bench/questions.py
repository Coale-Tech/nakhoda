"""Golden question set over the seeded ERPNext-shaped DuckDB.

Written from the point of view of an ERP business user, NOT from the schema.
Each question carries gold SQL and the semantic trap it probes.

trap taxonomy:
  none       - answerable from column names alone
  docstatus  - must exclude Draft(0)/Cancelled(2), keep Submitted(1)
  domain     - must know the allowed values of a Select column
  currency   - must aggregate base_* (company currency), not mixed transaction currency
  returns    - must handle credit notes / is_return
  join       - must resolve a Link column with no DB foreign key
  grain      - must join a child table via parent/parenttype
  display    - must distinguish id column from human-readable label column
"""

Q = [
 # ---------------- no trap: both contexts should manage --------------------
 dict(id="q01", trap="none", q="How many customers are on file?",
      sql='SELECT count(*) AS n FROM "tabCustomer"'),
 dict(id="q02", trap="none", q="List the names of all territories.",
      sql='SELECT name FROM "tabTerritory" ORDER BY name'),
 dict(id="q03", trap="none", q="How many items are in the Products item group?",
      sql='SELECT count(*) AS n FROM "tabItem" WHERE item_group = \'Products\''),
 dict(id="q04", trap="none", q="What is the highest standard rate of any item?",
      sql='SELECT max(standard_rate) AS m FROM "tabItem"'),
 dict(id="q05", trap="none", q="How many sales invoice records exist in total, including every state?",
      sql='SELECT count(*) AS n FROM "tabSales Invoice"'),

 # ---------------- docstatus: the single biggest ERP convention ------------
 dict(id="q06", trap="docstatus", q="What is our total sales revenue, excluding any return/credit-note invoices?",
      sql='SELECT sum(base_grand_total) AS total FROM "tabSales Invoice" WHERE docstatus = 1 AND is_return = 0'),
 dict(id="q07", trap="docstatus", q="How many sales invoices have we actually issued?",
      sql='SELECT count(*) AS n FROM "tabSales Invoice" WHERE docstatus = 1'),
 dict(id="q08", trap="docstatus", q="What was our revenue in 2025, excluding returns?",
      sql="""SELECT sum(base_grand_total) AS total FROM "tabSales Invoice"
             WHERE docstatus = 1 AND is_return = 0 AND posting_date >= DATE '2025-01-01'
               AND posting_date < DATE '2026-01-01'"""),
 dict(id="q09", trap="docstatus", q="What is the average invoice value, excluding returns?",
      sql='SELECT avg(base_grand_total) AS avg_val FROM "tabSales Invoice" WHERE docstatus = 1 AND is_return = 0'),
 dict(id="q10", trap="docstatus", q="How much money is still owed to us across all issued invoices, in company currency?",
      sql='SELECT sum(outstanding_amount * conversion_rate) AS owed FROM "tabSales Invoice" WHERE docstatus = 1'),
 dict(id="q11", trap="docstatus", q="How many payments have we received?",
      sql='SELECT count(*) AS n FROM "tabPayment Entry" WHERE docstatus = 1'),
 dict(id="q12", trap="docstatus", q="What is the total amount we have been paid?",
      sql='SELECT sum(base_paid_amount) AS total FROM "tabPayment Entry" WHERE docstatus = 1'),

 # ---------------- value domain ---------------------------------------------
 dict(id="q13", trap="domain", q="How many invoices are overdue?",
      sql="""SELECT count(*) AS n FROM "tabSales Invoice"
             WHERE docstatus = 1 AND status = 'Overdue'"""),
 dict(id="q14", trap="domain", q="How many invoices have been fully paid?",
      sql="""SELECT count(*) AS n FROM "tabSales Invoice"
             WHERE docstatus = 1 AND status = 'Paid'"""),
 dict(id="q15", trap="domain", q="Break down the number of issued invoices by their status.",
      sql="""SELECT status, count(*) AS n FROM "tabSales Invoice"
             WHERE docstatus = 1 GROUP BY status ORDER BY n DESC, status"""),
 dict(id="q16", trap="domain", q="How many invoices have been only partially paid?",
      sql="""SELECT count(*) AS n FROM "tabSales Invoice"
             WHERE docstatus = 1 AND status = 'Partly Paid'"""),
 dict(id="q17", trap="domain", q="How many draft invoices are sitting unsubmitted?",
      sql='SELECT count(*) AS n FROM "tabSales Invoice" WHERE docstatus = 0'),

 # ---------------- currency --------------------------------------------------
 dict(id="q18", trap="currency", q="What is our total revenue in company currency, excluding returns?",
      sql='SELECT sum(base_grand_total) AS total FROM "tabSales Invoice" WHERE docstatus = 1 AND is_return = 0'),
 dict(id="q19", trap="currency", q="Which transaction currencies do we invoice in, and how many issued invoices in each?",
      sql="""SELECT currency, count(*) AS n FROM "tabSales Invoice"
             WHERE docstatus = 1 GROUP BY currency ORDER BY n DESC, currency"""),
 dict(id="q20", trap="currency", q="Give me total revenue in company currency broken down by transaction currency.",
      sql="""SELECT currency, sum(base_grand_total) AS total FROM "tabSales Invoice"
             WHERE docstatus = 1 GROUP BY currency ORDER BY total DESC"""),

 # ---------------- returns / credit notes ------------------------------------
 dict(id="q21", trap="returns", q="How many of our issued invoices are credit notes or returns?",
      sql='SELECT count(*) AS n FROM "tabSales Invoice" WHERE docstatus = 1 AND is_return = 1'),
 dict(id="q22", trap="returns", q="What is our gross revenue excluding any returns?",
      sql="""SELECT sum(base_grand_total) AS total FROM "tabSales Invoice"
             WHERE docstatus = 1 AND is_return = 0"""),
 dict(id="q23", trap="returns", q="How much have we credited back to customers through returns? Give a positive number.",
      sql="""SELECT abs(sum(base_grand_total)) AS total FROM "tabSales Invoice"
             WHERE docstatus = 1 AND is_return = 1"""),

 # ---------------- joins with no foreign key ---------------------------------
 dict(id="q24", trap="join", q="Which territory generates the most revenue, excluding returns?",
      sql="""SELECT territory, sum(base_grand_total) AS total FROM "tabSales Invoice"
             WHERE docstatus = 1 AND is_return = 0 GROUP BY territory ORDER BY total DESC LIMIT 1"""),
 dict(id="q25", trap="join", q="Show revenue by territory excluding returns, highest first.",
      sql="""SELECT territory, sum(base_grand_total) AS total FROM "tabSales Invoice"
             WHERE docstatus = 1 AND is_return = 0 GROUP BY territory ORDER BY total DESC"""),
 dict(id="q26", trap="join", q="Which customers in Germany have we invoiced, and for how much in total?",
      sql="""SELECT si.customer, sum(si.base_grand_total) AS total
             FROM "tabSales Invoice" si JOIN "tabCustomer" c ON c.name = si.customer
             WHERE si.docstatus = 1 AND c.territory = 'Germany'
             GROUP BY si.customer ORDER BY total DESC"""),
 dict(id="q27", trap="join", q="How many active (not disabled) customers have we ever issued an invoice to?",
      sql="""SELECT count(DISTINCT si.customer) AS n
             FROM "tabSales Invoice" si JOIN "tabCustomer" c ON c.name = si.customer
             WHERE si.docstatus = 1 AND c.disabled = 0"""),
 dict(id="q28", trap="join", q="Which territories sit directly under India?",
      sql="""SELECT name FROM "tabTerritory" WHERE parent_territory = 'India' ORDER BY name"""),

 # ---------------- child-table grain -----------------------------------------
 dict(id="q29", trap="grain", q="Which item sold the most units, excluding returns?",
      sql="""SELECT sii.item_code, sum(sii.qty) AS units
             FROM "tabSales Invoice Item" sii
             JOIN "tabSales Invoice" si ON si.name = sii.parent
             WHERE si.docstatus = 1 AND si.is_return = 0 GROUP BY sii.item_code ORDER BY units DESC LIMIT 1"""),
 dict(id="q30", trap="grain", q="Top 5 items by revenue.",
      sql="""SELECT sii.item_code, sum(sii.base_amount) AS revenue
             FROM "tabSales Invoice Item" sii
             JOIN "tabSales Invoice" si ON si.name = sii.parent
             WHERE si.docstatus = 1 GROUP BY sii.item_code ORDER BY revenue DESC LIMIT 5"""),
 dict(id="q31", trap="grain", q="How many invoice line items are on issued invoices?",
      sql="""SELECT count(*) AS n FROM "tabSales Invoice Item" sii
             JOIN "tabSales Invoice" si ON si.name = sii.parent WHERE si.docstatus = 1"""),
 dict(id="q32", trap="grain", q="What is the average number of line items per issued invoice?",
      sql="""SELECT count(*) * 1.0 / count(DISTINCT sii.parent) AS avg_lines
             FROM "tabSales Invoice Item" sii
             JOIN "tabSales Invoice" si ON si.name = sii.parent WHERE si.docstatus = 1"""),
 dict(id="q33", trap="grain", q="Revenue by item group, highest first.",
      sql="""SELECT sii.item_group, sum(sii.base_amount) AS revenue
             FROM "tabSales Invoice Item" sii
             JOIN "tabSales Invoice" si ON si.name = sii.parent
             WHERE si.docstatus = 1 GROUP BY sii.item_group ORDER BY revenue DESC"""),
 dict(id="q34", trap="grain", q="Which item group did our Karnataka customers buy the most of by value?",
      sql="""SELECT sii.item_group, sum(sii.base_amount) AS revenue
             FROM "tabSales Invoice Item" sii
             JOIN "tabSales Invoice" si ON si.name = sii.parent
             WHERE si.docstatus = 1 AND si.territory = 'Karnataka'
             GROUP BY sii.item_group ORDER BY revenue DESC LIMIT 1"""),

 # ---------------- id vs display label ----------------------------------------
 dict(id="q35", trap="display", q="Who are our top 3 customers by revenue, excluding returns? Give their display names.",
      sql="""SELECT customer_name, sum(base_grand_total) AS total FROM "tabSales Invoice"
             WHERE docstatus = 1 AND is_return = 0 GROUP BY customer_name ORDER BY total DESC LIMIT 3"""),
 dict(id="q36", trap="display", q="Show the item name, not the code, for the 3 items with the highest standard rate.",
      sql='SELECT item_name FROM "tabItem" ORDER BY standard_rate DESC LIMIT 3'),

 # ---------------- combined / harder -------------------------------------------
 dict(id="q37", trap="docstatus", q="Monthly revenue for 2026 so far, excluding returns.",
      sql="""SELECT date_trunc('month', posting_date) AS month, sum(base_grand_total) AS total
             FROM "tabSales Invoice"
             WHERE docstatus = 1 AND is_return = 0 AND posting_date >= DATE '2026-01-01'
             GROUP BY 1 ORDER BY 1"""),
 dict(id="q38", trap="returns", q="Net revenue for 2026 counting returns against us.",
      sql="""SELECT sum(base_grand_total) AS total FROM "tabSales Invoice"
             WHERE docstatus = 1 AND posting_date >= DATE '2026-01-01'"""),
 dict(id="q39", trap="join", q="Average invoice value per territory excluding returns, highest first.",
      sql="""SELECT territory, avg(base_grand_total) AS avg_val FROM "tabSales Invoice"
             WHERE docstatus = 1 AND is_return = 0 GROUP BY territory ORDER BY avg_val DESC"""),
 dict(id="q40", trap="grain", q="How many distinct items has each item group sold on issued invoices?",
      sql="""SELECT sii.item_group, count(DISTINCT sii.item_code) AS n
             FROM "tabSales Invoice Item" sii
             JOIN "tabSales Invoice" si ON si.name = sii.parent
             WHERE si.docstatus = 1 GROUP BY sii.item_group ORDER BY n DESC, sii.item_group"""),
]

if __name__ == "__main__":
    import duckdb, collections
    con = duckdb.connect("/tmp/semantic-bench/erp.duckdb", read_only=True)
    bad = 0
    for q in Q:
        try:
            df = con.execute(q["sql"]).df()
            if len(df) == 0:
                print("EMPTY  ", q["id"], q["q"]); bad += 1
        except Exception as e:
            print("BROKEN ", q["id"], type(e).__name__, e); bad += 1
    print(f"\n{len(Q)} questions, {bad} problems")
    print("traps:", dict(collections.Counter(q["trap"] for q in Q)))
