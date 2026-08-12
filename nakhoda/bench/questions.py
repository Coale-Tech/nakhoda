"""The full question set: the frozen forty, and 165 written over three modules.

`tests/semantic_bench/questions.py` holds the forty behind the published 95.8%.
They are Selling-only, and forty is too few to separate a five-point difference
from noise - `10-eval-methodology.md` §6 says so in its own limitations. This
module is the answer to that: the same forty, unedited, plus 165 more spanning
Buying, Stock, and questions that cross module boundaries.

Every question carries `ordered`, which the frozen forty do not: whether the
question *text* demands a ranking. The frozen set encodes the same fact as a
hand-kept id list in `grade.py`, because it was derived after the fact from
questions already written. Writing it per question is the honest version, and
`ORDERED` stays where it is so a replay of the published run cannot shift.

Gold SQL is DuckDB, executed against `bench/fixture.py`'s database. Each entry
also carries the trap it probes; the taxonomy is the frozen set's, extended:

  tree      - must walk a self-referential parent link (Territory, Item Group,
              Supplier Group) rather than reading one level
  negation  - the answer is what is absent: an anti-join, not a filter
  sign      - a quantity whose sign carries meaning (returns, stock issues)
  derived   - no column holds the answer; it comes out of a calculation
  ambiguity - an English word maps to two tables and only one is right
"""

from nakhoda.bench.grade import ORDERED
from nakhoda.tests.semantic_bench.questions import Q as FROZEN

BUYING = [
	# ---- Buying - Supplier, Supplier Group, Purchase Order, Purchase Invoice and their items ---
	dict(
		id="q041",
		trap="join",
		ordered=True,
		q="Which suppliers have we spent the most with so far? Rank them by total company-currency spend from highest to lowest.",
		sql="""SELECT s.name AS supplier, sum(pi.base_grand_total) AS total
FROM "tabPurchase Invoice" pi
JOIN "tabSupplier" s ON s.name = pi.supplier
WHERE pi.docstatus = 1 AND pi.is_return = 0
GROUP BY s.name
ORDER BY total DESC, s.name
""",
	),
	dict(
		id="q042",
		trap="tree",
		ordered=True,
		q="Show our total spend with suppliers broken down by supplier category (Local, Import, Services), highest spend first.",
		sql="""SELECT s.supplier_group, sum(pi.base_grand_total) AS total
FROM "tabPurchase Invoice" pi
JOIN "tabSupplier" s ON s.name = pi.supplier
WHERE pi.docstatus = 1 AND pi.is_return = 0
GROUP BY s.supplier_group
ORDER BY total DESC, s.supplier_group
""",
	),
	dict(
		id="q043",
		trap="domain",
		ordered=True,
		q="Break down our total supplier spend by the supplier's country, in company currency, highest first.",
		sql="""SELECT s.country, sum(pi.base_grand_total) AS total
FROM "tabPurchase Invoice" pi
JOIN "tabSupplier" s ON s.name = pi.supplier
WHERE pi.docstatus = 1 AND pi.is_return = 0
GROUP BY s.country
ORDER BY total DESC, s.country
""",
	),
	dict(
		id="q044",
		trap="docstatus",
		ordered=True,
		q="List purchase orders we have actually confirmed but never received a bill for, oldest first.",
		sql="""SELECT po.name, po.supplier, po.transaction_date
FROM "tabPurchase Order" po
WHERE po.docstatus = 1
  AND NOT EXISTS (
    SELECT 1 FROM "tabPurchase Invoice Item" pii
    JOIN "tabPurchase Invoice" pi ON pi.name = pii.parent
    WHERE pii.purchase_order = po.name
      AND pi.docstatus = 1 AND pi.is_return = 0
  )
ORDER BY po.transaction_date, po.name
""",
	),
	dict(
		id="q045",
		trap="grain",
		ordered=False,
		q="Which line items on submitted purchase orders are not fully received yet? Show each order, item, ordered qty, and received qty.",
		sql="""SELECT poi.parent, poi.item_code, poi.qty, poi.received_qty
FROM "tabPurchase Order Item" poi
WHERE poi.docstatus = 1 AND poi.received_qty < poi.qty
ORDER BY poi.parent, poi.item_code
""",
	),
	dict(
		id="q046",
		trap="display",
		ordered=False,
		q="Which suppliers are currently disabled? Show their display name and country.",
		sql="""SELECT s.supplier_name, s.country
FROM "tabSupplier" s
WHERE s.disabled = 1
ORDER BY s.supplier_name
""",
	),
	dict(
		id="q047",
		trap="returns",
		ordered=False,
		q="How many debit notes have we issued against suppliers, and what is the net total of those notes in company currency?",
		sql="""SELECT count(*) AS n, sum(pi.base_grand_total) AS total
FROM "tabPurchase Invoice" pi
WHERE pi.docstatus = 1 AND pi.is_return = 1
""",
	),
	dict(
		id="q048",
		trap="join",
		ordered=True,
		q="Rank our item groups by total spend on purchased items, in company currency, highest first.",
		sql="""SELECT pii.item_group, sum(pii.base_amount) AS total
FROM "tabPurchase Invoice Item" pii
JOIN "tabPurchase Invoice" pi ON pi.name = pii.parent
WHERE pi.docstatus = 1 AND pi.is_return = 0
GROUP BY pii.item_group
ORDER BY total DESC, pii.item_group
""",
	),
	dict(
		id="q049",
		trap="currency",
		ordered=False,
		q="What is the total value, in company currency, of bills we have received that were originally billed in US dollars?",
		sql="""SELECT sum(pi.base_grand_total) AS total
FROM "tabPurchase Invoice" pi
WHERE pi.docstatus = 1 AND pi.is_return = 0 AND pi.currency = 'USD'
""",
	),
	dict(
		id="q050",
		trap="domain",
		ordered=False,
		q="How many purchase orders are still open and unbilled, and what is their total value?",
		sql="""SELECT count(*) AS n, sum(base_grand_total) AS total
FROM "tabPurchase Order"
WHERE docstatus = 1 AND status = 'To Receive and Bill'
""",
	),
	dict(
		id="q051",
		trap="grain",
		ordered=True,
		q="For each submitted purchase order, how many line items does it carry and what is the total quantity? Show the largest orders first.",
		sql="""SELECT po.name, count(poi.name) AS lines, sum(poi.qty) AS total_qty
FROM "tabPurchase Order" po
JOIN "tabPurchase Order Item" poi ON poi.parent = po.name
WHERE po.docstatus = 1
GROUP BY po.name
ORDER BY total_qty DESC, po.name
""",
	),
	dict(
		id="q052",
		trap="ambiguity",
		ordered=False,
		q="How many supplier bills did we post in 2024, and what was their total value in company currency?",
		sql="""SELECT count(*) AS n, sum(pi.base_grand_total) AS total
FROM "tabPurchase Invoice" pi
WHERE pi.docstatus = 1 AND pi.is_return = 0
  AND pi.posting_date >= DATE '2024-01-01'
  AND pi.posting_date <  DATE '2025-01-01'
""",
	),
	dict(
		id="q053",
		trap="currency",
		ordered=True,
		q="Break down submitted purchase orders by their billing currency and show the original-currency grand totals, highest first.",
		sql="""SELECT po.currency, sum(po.grand_total) AS total_txn
FROM "tabPurchase Order" po
WHERE po.docstatus = 1
GROUP BY po.currency
ORDER BY total_txn DESC, po.currency
""",
	),
	dict(
		id="q054",
		trap="docstatus",
		ordered=False,
		q="How many purchase orders are still in draft and what is their combined value in the original currency?",
		sql="""SELECT count(*) AS n, sum(grand_total) AS total
FROM "tabPurchase Order"
WHERE docstatus = 0
""",
	),
	dict(
		id="q055",
		trap="tree",
		ordered=False,
		q="Show our supplier group hierarchy, each group's parent group, and whether it is a group node.",
		sql="""SELECT sg.supplier_group_name, sg.parent_supplier_group, sg.is_group
FROM "tabSupplier Group" sg
ORDER BY sg.lft
""",
	),
	dict(
		id="q056",
		trap="join",
		ordered=False,
		q="For every supplier, show their immediate supplier category and that category's parent in the hierarchy.",
		sql="""SELECT s.name AS supplier, sg.supplier_group_name, sg.parent_supplier_group
FROM "tabSupplier" s
JOIN "tabSupplier Group" sg ON sg.supplier_group_name = s.supplier_group
ORDER BY s.name
""",
	),
	dict(
		id="q057",
		trap="returns",
		ordered=False,
		q="Which suppliers have we ever issued a debit note against? List the supplier id and display name.",
		sql="""SELECT DISTINCT pi.supplier, pi.supplier_name
FROM "tabPurchase Invoice" pi
WHERE pi.docstatus = 1 AND pi.is_return = 1
ORDER BY pi.supplier_name, pi.supplier
""",
	),
	dict(
		id="q058",
		trap="returns",
		ordered=False,
		q="How many debit notes reduce the amount we owe, and what is their net value in company currency?",
		sql="""SELECT count(*) AS n, sum(pi.base_grand_total) AS total
FROM "tabPurchase Invoice" pi
WHERE pi.docstatus = 1 AND pi.is_return = 1 AND pi.base_grand_total < 0
""",
	),
	dict(
		id="q059",
		trap="grain",
		ordered=True,
		q="For each posted bill, how many line items does it have? Show the most detailed bills first.",
		sql="""SELECT pi.name, pi.supplier, count(pii.name) AS lines
FROM "tabPurchase Invoice" pi
JOIN "tabPurchase Invoice Item" pii ON pii.parent = pi.name
WHERE pi.docstatus = 1 AND pi.is_return = 0
GROUP BY pi.name, pi.supplier
ORDER BY lines DESC, pi.name
""",
	),
	dict(
		id="q060",
		trap="domain",
		ordered=False,
		q="How many bills are overdue, what is their total face value, and how much of that is still unpaid?",
		sql="""SELECT count(*) AS n,
       sum(base_grand_total) AS total,
       sum(outstanding_amount) AS outstanding
FROM "tabPurchase Invoice"
WHERE docstatus = 1 AND is_return = 0 AND status = 'Overdue'
""",
	),
	dict(
		id="q061",
		trap="docstatus",
		ordered=True,
		q="Across all our posted bills, what is the breakdown by payment status, showing count and total value, highest value first?",
		sql="""SELECT status, count(*) AS n, sum(base_grand_total) AS total
FROM "tabPurchase Invoice"
WHERE docstatus = 1 AND is_return = 0
GROUP BY status
ORDER BY total DESC, status
""",
	),
	dict(
		id="q062",
		trap="domain",
		ordered=False,
		q="How many submitted purchase orders are not yet fully received?",
		sql="""SELECT count(*) AS n
FROM "tabPurchase Order"
WHERE docstatus = 1 AND per_received < 100
""",
	),
	dict(
		id="q063",
		trap="display",
		ordered=True,
		q="Rank suppliers by total spend using their display name rather than the id, highest first.",
		sql="""SELECT s.supplier_name, sum(pi.base_grand_total) AS total
FROM "tabPurchase Invoice" pi
JOIN "tabSupplier" s ON s.name = pi.supplier
WHERE pi.docstatus = 1 AND pi.is_return = 0
GROUP BY s.supplier_name
ORDER BY total DESC, s.supplier_name
""",
	),
	dict(
		id="q064",
		trap="join",
		ordered=True,
		q="Which suppliers buy the widest variety of items from us? Show the distinct item count per supplier, most diverse first.",
		sql="""SELECT pi.supplier, count(DISTINCT pii.item_code) AS items
FROM "tabPurchase Invoice" pi
JOIN "tabPurchase Invoice Item" pii ON pii.parent = pi.name
WHERE pi.docstatus = 1 AND pi.is_return = 0
GROUP BY pi.supplier
ORDER BY items DESC, pi.supplier
""",
	),
	dict(
		id="q065",
		trap="currency",
		ordered=False,
		q="What is the total company-currency value, and how many bills, were originally billed in euros?",
		sql="""SELECT sum(pi.base_grand_total) AS total, count(*) AS n
FROM "tabPurchase Invoice" pi
WHERE pi.docstatus = 1 AND pi.is_return = 0 AND pi.currency = 'EUR'
""",
	),
	dict(
		id="q066",
		trap="tree",
		ordered=False,
		q="List every supplier in our Import category, ordered by supplier id.",
		sql="""SELECT s.name, s.supplier_name, s.supplier_group
FROM "tabSupplier" s
WHERE s.supplier_group = 'Import'
ORDER BY s.name
""",
	),
	dict(
		id="q067",
		trap="ambiguity",
		ordered=False,
		q="How many purchase orders did we place in 2025, and what was their combined value in company currency?",
		sql="""SELECT count(*) AS n, sum(base_grand_total) AS total
FROM "tabPurchase Order" po
WHERE po.docstatus = 1
  AND po.transaction_date >= DATE '2025-01-01'
  AND po.transaction_date <  DATE '2026-01-01'
""",
	),
	dict(
		id="q068",
		trap="returns",
		ordered=True,
		q="For each supplier we have issued a debit note to, show how many notes and the net company-currency total, most negative first.",
		sql="""SELECT pi.supplier, count(*) AS n, sum(pi.base_grand_total) AS total
FROM "tabPurchase Invoice" pi
WHERE pi.docstatus = 1 AND pi.is_return = 1
GROUP BY pi.supplier
ORDER BY total, pi.supplier
""",
	),
	dict(
		id="q069",
		trap="grain",
		ordered=True,
		q="Which items have we spent the most on, in company currency? Rank by total billed amount, highest first.",
		sql="""SELECT pii.item_code, sum(pii.base_amount) AS total
FROM "tabPurchase Invoice Item" pii
JOIN "tabPurchase Invoice" pi ON pi.name = pii.parent
WHERE pi.docstatus = 1 AND pi.is_return = 0
GROUP BY pii.item_code
ORDER BY total DESC, pii.item_code
""",
	),
	dict(
		id="q070",
		trap="negation",
		ordered=False,
		q="Which suppliers have we never issued a debit note against? List them by id and display name.",
		sql="""SELECT s.name, s.supplier_name
FROM "tabSupplier" s
WHERE NOT EXISTS (
  SELECT 1 FROM "tabPurchase Invoice" pi
  WHERE pi.supplier = s.name
    AND pi.docstatus = 1 AND pi.is_return = 1
)
ORDER BY s.name
""",
	),
	dict(
		id="q071",
		trap="docstatus",
		ordered=False,
		q="How many purchase orders have been cancelled, and what was their combined value in company currency?",
		sql="""SELECT count(*) AS n, sum(base_grand_total) AS total
FROM "tabPurchase Order"
WHERE docstatus = 2
""",
	),
	dict(
		id="q072",
		trap="join",
		ordered=True,
		q="Which countries have placed the most purchase orders with us? Show order counts, most active first.",
		sql="""SELECT s.country, count(*) AS n
FROM "tabPurchase Order" po
JOIN "tabSupplier" s ON s.name = po.supplier
WHERE po.docstatus = 1
GROUP BY s.country
ORDER BY n DESC, s.country
""",
	),
	dict(
		id="q073",
		trap="grain",
		ordered=False,
		q="For each submitted purchase order line that is only partially received, show the order, item, ordered qty, and received qty.",
		sql="""SELECT poi.parent, poi.item_code, poi.qty, poi.received_qty
FROM "tabPurchase Order Item" poi
JOIN "tabPurchase Order" po ON po.name = poi.parent
WHERE po.docstatus = 1 AND poi.qty > 0 AND poi.received_qty < poi.qty
ORDER BY poi.parent, poi.item_code
""",
	),
	dict(
		id="q074",
		trap="currency",
		ordered=False,
		q="What is the total company-currency value, and how many bills, were originally billed in British pounds?",
		sql="""SELECT sum(pi.base_grand_total) AS total, count(*) AS n
FROM "tabPurchase Invoice" pi
WHERE pi.docstatus = 1 AND pi.is_return = 0 AND pi.currency = 'GBP'
""",
	),
	dict(
		id="q075",
		trap="domain",
		ordered=False,
		q="How many bills are still Unpaid, and what is their total company-currency face value?",
		sql="""SELECT count(*) AS n, sum(base_grand_total) AS total
FROM "tabPurchase Invoice"
WHERE docstatus = 1 AND is_return = 0 AND status = 'Unpaid'
""",
	),
	dict(
		id="q076",
		trap="join",
		ordered=True,
		q="For each submitted purchase order that has been billed, show the order id, supplier, date, number of bill lines, and total billed amount, highest billed first.",
		sql="""SELECT po.name AS po, po.supplier, po.transaction_date,
       count(pii.name) AS bill_lines,
       sum(pii.base_amount) AS billed
FROM "tabPurchase Order" po
JOIN "tabPurchase Invoice Item" pii ON pii.purchase_order = po.name
JOIN "tabPurchase Invoice" pi ON pi.name = pii.parent
WHERE po.docstatus = 1 AND pi.docstatus = 1 AND pi.is_return = 0
GROUP BY po.name, po.supplier, po.transaction_date
ORDER BY billed DESC, po.name
""",
	),
	dict(
		id="q077",
		trap="docstatus",
		ordered=False,
		q="How many purchase invoices are in each document state (Draft, Submitted, Cancelled)?",
		sql="""SELECT docstatus, count(*) AS n
FROM "tabPurchase Invoice"
GROUP BY docstatus
ORDER BY docstatus
""",
	),
	dict(
		id="q078",
		trap="none",
		ordered=False,
		q="Break down our debit notes by calendar month of posting, showing the count and net value in company currency for each month.",
		sql="""SELECT EXTRACT(MONTH FROM pi.posting_date) AS m,
       count(*) AS n,
       sum(pi.base_grand_total) AS total
FROM "tabPurchase Invoice" pi
WHERE pi.docstatus = 1 AND pi.is_return = 1
GROUP BY 1
ORDER BY 1
""",
	),
	dict(
		id="q079",
		trap="grain",
		ordered=True,
		q="Which purchase order lines received the most quantity? Show the order, item, and received qty, largest first.",
		sql="""SELECT poi.parent, poi.item_code, poi.received_qty
FROM "tabPurchase Order Item" poi
WHERE poi.docstatus = 1
ORDER BY poi.received_qty DESC, poi.parent, poi.item_code
""",
	),
	dict(
		id="q080",
		trap="join",
		ordered=False,
		q="List every bill line that traces back to a specific purchase order, showing the order, the bill, the item, and the company-currency amount.",
		sql="""SELECT po.name AS po,
       po.supplier,
       pii.parent AS bill,
       pii.item_code,
       pii.base_amount
FROM "tabPurchase Order" po
JOIN "tabPurchase Invoice Item" pii ON pii.purchase_order = po.name
JOIN "tabPurchase Invoice" pi ON pi.name = pii.parent
WHERE po.docstatus = 1 AND pi.docstatus = 1 AND pi.is_return = 0
ORDER BY po.name, pii.parent, pii.item_code
""",
	),
	dict(
		id="q081",
		trap="docstatus",
		ordered=False,
		q="How many purchase invoices have been cancelled?",
		sql="""SELECT count(*) AS n
FROM "tabPurchase Invoice"
WHERE docstatus = 2
""",
	),
	dict(
		id="q082",
		trap="none",
		ordered=False,
		q="For each posted bill linked to a submitted purchase order, show the order id, the order date, the bill posting date, and the company-currency total.",
		sql="""SELECT po.name AS po,
       po.transaction_date,
       pi.posting_date,
       pi.base_grand_total
FROM "tabPurchase Order" po
JOIN "tabPurchase Invoice Item" pii ON pii.purchase_order = po.name
JOIN "tabPurchase Invoice" pi ON pi.name = pii.parent
WHERE po.docstatus = 1 AND pi.docstatus = 1 AND pi.is_return = 0
ORDER BY pi.posting_date, po.name
""",
	),
	dict(
		id="q083",
		trap="currency",
		ordered=False,
		q="What is the total company-currency value, and how many bills, were originally billed in Indian rupees?",
		sql="""SELECT sum(pi.base_grand_total) AS total, count(*) AS n
FROM "tabPurchase Invoice" pi
WHERE pi.docstatus = 1 AND pi.is_return = 0 AND pi.currency = 'INR'
""",
	),
	dict(
		id="q084",
		trap="domain",
		ordered=False,
		q="How many purchase orders are fully Completed, and what is their total company-currency value?",
		sql="""SELECT count(*) AS n, sum(base_grand_total) AS total
FROM "tabPurchase Order"
WHERE docstatus = 1 AND status = 'Completed'
""",
	),
	dict(
		id="q085",
		trap="grain",
		ordered=True,
		q="For each submitted purchase order, count how many line items it has. Show the orders with the most lines first.",
		sql="""SELECT po.name, count(poi.name) AS line_count
FROM "tabPurchase Order" po
JOIN "tabPurchase Order Item" poi ON poi.parent = po.name
WHERE po.docstatus = 1
GROUP BY po.name
ORDER BY line_count DESC, po.name
""",
	),
	dict(
		id="q086",
		trap="negation",
		ordered=False,
		q="How many items have we purchased from suppliers but never sold to any customer?",
		sql="""SELECT count(*) AS n
FROM (
  SELECT DISTINCT pii.item_code
  FROM "tabPurchase Invoice Item" pii
  JOIN "tabPurchase Invoice" pi ON pi.name = pii.parent
  WHERE pi.docstatus = 1 AND pi.is_return = 0
  EXCEPT
  SELECT DISTINCT sii.item_code
  FROM "tabSales Invoice Item" sii
  JOIN "tabSales Invoice" si ON si.name = sii.parent
  WHERE si.docstatus = 1 AND si.is_return = 0
) sub
""",
	),
	dict(
		id="q087",
		trap="tree",
		ordered=False,
		q="List every supplier in our Services category along with their country, sorted by supplier id.",
		sql="""SELECT s.name, s.supplier_name, s.country
FROM "tabSupplier" s
WHERE s.supplier_group = 'Services'
ORDER BY s.name
""",
	),
	dict(
		id="q088",
		trap="join",
		ordered=True,
		q="For each supplier country, what is the average submitted purchase order value in company currency? Show highest first.",
		sql="""SELECT s.country, avg(po.base_grand_total) AS avg_po
FROM "tabPurchase Order" po
JOIN "tabSupplier" s ON s.name = po.supplier
WHERE po.docstatus = 1
GROUP BY s.country
ORDER BY avg_po DESC, s.country
""",
	),
	dict(
		id="q089",
		trap="docstatus",
		ordered=False,
		q="Across all submitted purchase orders, what are the average, minimum, and maximum per_received percentage?",
		sql="""SELECT avg(per_received) AS avg_pct,
       min(per_received) AS min_pct,
       max(per_received) AS max_pct
FROM "tabPurchase Order"
WHERE docstatus = 1
""",
	),
	dict(
		id="q090",
		trap="grain",
		ordered=True,
		q="For each partially received purchase order line, show the order, item, ordered qty, received qty, and the still-outstanding qty, biggest gaps first.",
		sql="""SELECT poi.parent, poi.item_code, poi.qty, poi.received_qty,
       (poi.qty - poi.received_qty) AS outstanding
FROM "tabPurchase Order Item" poi
WHERE poi.docstatus = 1 AND poi.qty > 0 AND poi.received_qty < poi.qty
ORDER BY outstanding DESC, poi.parent, poi.item_code
""",
	),
	dict(
		id="q091",
		trap="none",
		ordered=False,
		q="Break down our posted bills by year, showing the count and total company-currency value per year.",
		sql="""SELECT EXTRACT(YEAR FROM pi.posting_date) AS yr,
       count(*) AS n,
       sum(pi.base_grand_total) AS total
FROM "tabPurchase Invoice" pi
WHERE pi.docstatus = 1 AND pi.is_return = 0
GROUP BY 1
ORDER BY 1
""",
	),
	dict(
		id="q092",
		trap="display",
		ordered=True,
		q="For each year, show the total company-currency value of posted bills by payment status, years newest first.",
		sql="""SELECT EXTRACT(YEAR FROM pi.posting_date) AS yr,
       pi.status,
       sum(pi.base_grand_total) AS total
FROM "tabPurchase Invoice" pi
WHERE pi.docstatus = 1 AND pi.is_return = 0
GROUP BY 1, pi.status
ORDER BY yr DESC, pi.status
""",
	),
	dict(
		id="q093",
		trap="negation",
		ordered=True,
		q="Which submitted purchase orders are still completely unreceived? Show the order id, supplier, and company-currency value, biggest values first.",
		sql="""SELECT po.name, po.supplier, po.base_grand_total
FROM "tabPurchase Order" po
WHERE po.docstatus = 1 AND po.per_received = 0
ORDER BY po.base_grand_total DESC, po.name
""",
	),
	dict(
		id="q094",
		trap="tree",
		ordered=True,
		q="For each supplier category, show the total company-currency spend and how many distinct suppliers it covers, highest spend first.",
		sql="""SELECT s.supplier_group,
       sum(pi.base_grand_total) AS total,
       count(DISTINCT s.name) AS n_suppliers
FROM "tabPurchase Invoice" pi
JOIN "tabSupplier" s ON s.name = pi.supplier
WHERE pi.docstatus = 1 AND pi.is_return = 0
GROUP BY s.supplier_group
ORDER BY total DESC, s.supplier_group
""",
	),
	dict(
		id="q095",
		trap="ambiguity",
		ordered=True,
		q="Which suppliers are we still owing the most money to? Show the total outstanding company-currency amount per supplier, highest first.",
		sql="""SELECT pi.supplier, sum(pi.outstanding_amount) AS total
FROM "tabPurchase Invoice" pi
WHERE pi.docstatus = 1 AND pi.is_return = 0 AND pi.outstanding_amount > 0
GROUP BY pi.supplier
ORDER BY total DESC, pi.supplier
""",
	),
]

STOCK = [
	# ---- Stock - Warehouse, Delivery Note, Stock Ledger Entry ----------------------
	dict(
		id="q096",
		trap="none",
		ordered=False,
		q="How many warehouses do we operate?",
		sql='SELECT count(*) AS n FROM "tabWarehouse"',
	),
	dict(
		id="q097",
		trap="none",
		ordered=False,
		q="How many shipment records have we created in total?",
		sql='SELECT count(*) AS n FROM "tabDelivery Note"',
	),
	dict(
		id="q098",
		trap="none",
		ordered=False,
		q="How many distinct items have ever appeared on a shipment line?",
		sql='SELECT count(DISTINCT item_code) AS n FROM "tabDelivery Note Item"',
	),
	dict(
		id="q099",
		trap="none",
		ordered=False,
		q="How many distinct warehouses have ever held stock?",
		sql='SELECT count(DISTINCT warehouse) AS n FROM "tabStock Ledger Entry"',
	),
	dict(
		id="q100",
		trap="docstatus",
		ordered=False,
		q="How many of our shipment records are actually posted (i.e. not drafts)?",
		sql='SELECT count(*) AS n FROM "tabDelivery Note" WHERE docstatus = 1',
	),
	dict(
		id="q101",
		trap="docstatus",
		ordered=False,
		q="How many stock movement records have we posted?",
		sql='SELECT count(*) AS n FROM "tabStock Ledger Entry" WHERE docstatus = 1',
	),
	dict(
		id="q102",
		trap="docstatus",
		ordered=False,
		q="How many shipment line items sit on posted deliveries?",
		sql='SELECT count(*) AS n FROM "tabDelivery Note Item" WHERE docstatus = 1',
	),
	dict(
		id="q103",
		trap="docstatus",
		ordered=False,
		q="How many units did we receive into stock on posted purchase bills?",
		sql="""SELECT sum(actual_qty) AS qty FROM "tabStock Ledger Entry" WHERE docstatus = 1 AND voucher_type = 'Purchase Invoice'
""",
	),
	dict(
		id="q104",
		trap="docstatus",
		ordered=False,
		q="What is the total value of goods we actually dispatched, in company currency, ignoring drafts?",
		sql='SELECT sum(base_grand_total) AS total FROM "tabDelivery Note" WHERE docstatus = 1 AND is_return = 0',
	),
	dict(
		id="q105",
		trap="docstatus",
		ordered=False,
		q="How many of our shipment records are still in draft?",
		sql='SELECT count(*) AS n FROM "tabDelivery Note" WHERE docstatus = 0',
	),
	dict(
		id="q106",
		trap="domain",
		ordered=False,
		q="How many shipments are flagged as completed (i.e. fully delivered)?",
		sql="""SELECT count(*) AS n FROM "tabDelivery Note" WHERE status = 'Completed'
""",
	),
	dict(
		id="q107",
		trap="domain",
		ordered=False,
		q="How many stock movements came from shipments (as opposed to purchase receipts)?",
		sql="""SELECT count(*) AS n FROM "tabStock Ledger Entry" WHERE voucher_type = 'Delivery Note'
""",
	),
	dict(
		id="q108",
		trap="domain",
		ordered=False,
		q="Which warehouses are configured as transit-only?",
		sql="""SELECT name FROM "tabWarehouse" WHERE warehouse_type = 'Transit' ORDER BY name
""",
	),
	dict(
		id="q109",
		trap="currency",
		ordered=False,
		q="What is the total value of goods we have dispatched, in our company currency?",
		sql='SELECT sum(base_grand_total) AS total FROM "tabDelivery Note" WHERE docstatus = 1 AND is_return = 0',
	),
	dict(
		id="q110",
		trap="currency",
		ordered=False,
		q="Show the total value of shipments in each transaction currency.",
		sql='SELECT currency, sum(grand_total) AS total FROM "tabDelivery Note" WHERE docstatus = 1 AND is_return = 0 GROUP BY currency ORDER BY total DESC',
	),
	dict(
		id="q111",
		trap="currency",
		ordered=False,
		q="What is the average exchange rate applied to USD-denominated shipments?",
		sql="""SELECT avg(conversion_rate) AS avg_rate FROM "tabDelivery Note" WHERE docstatus = 1 AND currency = 'USD'
""",
	),
	dict(
		id="q112",
		trap="join",
		ordered=False,
		q="How many shipments has each customer received, showing the customer display name?",
		sql="""SELECT c.name, c.customer_name, count(*) AS n
        FROM "tabDelivery Note" d JOIN "tabCustomer" c ON c.name = d.customer
        WHERE d.docstatus = 1
        GROUP BY 1, 2
        ORDER BY n DESC, c.name
""",
	),
	dict(
		id="q113",
		trap="join",
		ordered=False,
		q="List items by their total shipped quantity, showing the human-readable item name.",
		sql="""SELECT dni.item_code, dni.item_name, sum(dni.qty) AS qty
        FROM "tabDelivery Note Item" dni
        WHERE dni.docstatus = 1
        GROUP BY 1, 2
        ORDER BY qty DESC, dni.item_code
""",
	),
	dict(
		id="q114",
		trap="join",
		ordered=False,
		q="What is the current stock on hand per item, with each item's human-readable label?",
		sql="""SELECT i.name, i.item_name, sum(la.qty) AS on_hand
        FROM (
          SELECT item_code, warehouse, qty_after_transaction AS qty,
                 row_number() OVER (PARTITION BY item_code, warehouse ORDER BY name DESC) AS rn
          FROM "tabStock Ledger Entry"
        ) la JOIN "tabItem" i ON i.name = la.item_code
        WHERE la.rn = 1
        GROUP BY 1, 2
        ORDER BY on_hand DESC, i.name
""",
	),
	dict(
		id="q115",
		trap="join",
		ordered=False,
		q="What is the current on-hand quantity, broken out by warehouse and item?",
		sql="""SELECT la.warehouse, la.item_code, la.qty
        FROM (
          SELECT item_code, warehouse, qty_after_transaction AS qty,
                 row_number() OVER (PARTITION BY item_code, warehouse ORDER BY name DESC) AS rn
          FROM "tabStock Ledger Entry"
        ) la
        WHERE la.rn = 1
        ORDER BY la.warehouse, la.item_code
""",
	),
	dict(
		id="q116",
		trap="join",
		ordered=False,
		q="How many shipment lines have we sent out of each warehouse (sum of quantities)?",
		sql="""SELECT dni.warehouse, count(*) AS lines, sum(dni.qty) AS qty
        FROM "tabDelivery Note Item" dni
        WHERE dni.docstatus = 1
        GROUP BY 1
        ORDER BY qty DESC, dni.warehouse
""",
	),
	dict(
		id="q117",
		trap="join",
		ordered=False,
		q="How many shipment lines are tied back to a posted sales invoice?",
		sql="""SELECT count(*) AS n
        FROM "tabDelivery Note Item" dni
        JOIN "tabSales Invoice" si ON si.name = dni.against_sales_invoice
        WHERE dni.docstatus = 1 AND si.docstatus = 1
""",
	),
	dict(
		id="q118",
		trap="grain",
		ordered=False,
		q="How many shipments have we sent per customer?",
		sql="""SELECT customer, count(*) AS n
        FROM "tabDelivery Note"
        WHERE docstatus = 1
        GROUP BY 1
        ORDER BY n DESC, customer
""",
	),
	dict(
		id="q119",
		trap="grain",
		ordered=False,
		q="How many lines does each shipment carry on average?",
		sql="""SELECT avg(c) AS avg_lines
        FROM (SELECT count(*) AS c
              FROM "tabDelivery Note Item"
              WHERE docstatus = 1
              GROUP BY parent)
""",
	),
	dict(
		id="q120",
		trap="grain",
		ordered=False,
		q="How much of each item has been shipped to each customer?",
		sql="""SELECT d.customer, dni.item_code, sum(dni.qty) AS qty
        FROM "tabDelivery Note" d
        JOIN "tabDelivery Note Item" dni ON dni.parent = d.name
        WHERE d.docstatus = 1
        GROUP BY 1, 2
        ORDER BY d.customer, dni.item_code
""",
	),
	dict(
		id="q121",
		trap="grain",
		ordered=True,
		q="Show the running stock balance per item per warehouse, ordered chronologically.",
		sql="""SELECT item_code, warehouse, qty_after_transaction, posting_date
        FROM "tabStock Ledger Entry"
        ORDER BY item_code, warehouse, posting_date, name
""",
	),
	dict(
		id="q122",
		trap="grain",
		ordered=False,
		q="What is the current on-hand balance for each item in each warehouse?",
		sql="""SELECT item_code, warehouse, qty_after_transaction AS on_hand
        FROM (
          SELECT item_code, warehouse, qty_after_transaction,
                 row_number() OVER (PARTITION BY item_code, warehouse ORDER BY name DESC) AS rn
          FROM "tabStock Ledger Entry"
        )
        WHERE rn = 1
        ORDER BY item_code, warehouse
""",
	),
	dict(
		id="q123",
		trap="grain",
		ordered=False,
		q="How many stock movement lines were created per posted shipment, on average?",
		sql="""SELECT avg(c) AS avg_sle_per_dn
        FROM (SELECT count(*) AS c
              FROM "tabStock Ledger Entry"
              WHERE voucher_type = 'Delivery Note' AND docstatus = 1
              GROUP BY voucher_no)
""",
	),
	dict(
		id="q124",
		trap="grain",
		ordered=False,
		q="How many distinct items appear on each posted shipment?",
		sql="""SELECT parent, count(DISTINCT item_code) AS items
        FROM "tabDelivery Note Item"
        WHERE docstatus = 1
        GROUP BY 1
        ORDER BY items DESC, parent
""",
	),
	dict(
		id="q125",
		trap="display",
		ordered=True,
		q="Which warehouse holds the most stock right now, by human-readable name?",
		sql="""SELECT w.warehouse_name, sum(la.qty) AS on_hand
        FROM (
          SELECT warehouse, qty_after_transaction AS qty,
                 row_number() OVER (PARTITION BY item_code, warehouse ORDER BY name DESC) AS rn
          FROM "tabStock Ledger Entry"
        ) la JOIN "tabWarehouse" w ON w.name = la.warehouse
        WHERE la.rn = 1
        GROUP BY 1
        ORDER BY on_hand DESC, w.warehouse_name
""",
	),
	dict(
		id="q126",
		trap="display",
		ordered=True,
		q="Who are the top 5 customers by number of shipments, with their display name?",
		sql="""SELECT customer, customer_name, count(*) AS n
        FROM "tabDelivery Note"
        WHERE docstatus = 1
        GROUP BY 1, 2
        ORDER BY n DESC, customer
        LIMIT 5
""",
	),
	dict(
		id="q127",
		trap="tree",
		ordered=False,
		q="What is the total stock value across all our warehouses (i.e. under the 'All Warehouses' root group)?",
		sql="""SELECT sum(la.value) AS total_value
        FROM (
          SELECT stock_value AS value,
                 row_number() OVER (PARTITION BY item_code, warehouse ORDER BY name DESC) AS rn
          FROM "tabStock Ledger Entry"
        ) la
        WHERE la.rn = 1
""",
	),
	dict(
		id="q128",
		trap="tree",
		ordered=False,
		q="Which warehouses sit directly under the 'All Warehouses' root?",
		sql="""SELECT name, warehouse_name
        FROM "tabWarehouse"
        WHERE parent_warehouse = 'All Warehouses - AI'
        ORDER BY name
""",
	),
	dict(
		id="q129",
		trap="tree",
		ordered=False,
		q="How many shipments went to customers in the India region (India group and its sub-territories)?",
		sql="""SELECT count(*) AS n
        FROM "tabDelivery Note" d
        JOIN "tabTerritory" t ON t.name = d.territory
        WHERE d.docstatus = 1
          AND (t.parent_territory = 'India' OR t.name = 'India')
""",
	),
	dict(
		id="q130",
		trap="tree",
		ordered=False,
		q="What is the total shipment value (in company currency) delivered to the India region (India and its sub-territories)?",
		sql="""SELECT sum(d.base_grand_total) AS total
        FROM "tabDelivery Note" d
        JOIN "tabTerritory" t ON t.name = d.territory
        WHERE d.docstatus = 1
          AND (t.parent_territory = 'India' OR t.name = 'India')
""",
	),
	dict(
		id="q131",
		trap="negation",
		ordered=False,
		q="Which non-group warehouses currently hold no stock at all?",
		sql="""SELECT w.name
        FROM "tabWarehouse" w
        WHERE w.is_group = 0
          AND NOT EXISTS (SELECT 1 FROM "tabStock Ledger Entry" sle WHERE sle.warehouse = w.name)
        ORDER BY w.name
""",
	),
	dict(
		id="q132",
		trap="negation",
		ordered=False,
		q="Which items have been shipped to customers but were never received on a purchase bill?",
		sql="""SELECT DISTINCT item_code
        FROM "tabStock Ledger Entry"
        WHERE voucher_type = 'Delivery Note' AND actual_qty < 0
          AND item_code NOT IN (
            SELECT DISTINCT item_code
            FROM "tabStock Ledger Entry"
            WHERE voucher_type = 'Purchase Invoice' AND actual_qty > 0
          )
        ORDER BY item_code
""",
	),
	dict(
		id="q133",
		trap="negation",
		ordered=False,
		q="How many customers have been invoiced but never received a shipment (no delivery line links to any of their invoices)?",
		sql="""SELECT count(*) AS n
        FROM "tabCustomer" c
        JOIN "tabSales Invoice" si ON si.customer = c.name
        WHERE si.docstatus = 1 AND si.is_return = 0
          AND NOT EXISTS (
            SELECT 1 FROM "tabDelivery Note Item" dni
            WHERE dni.against_sales_invoice = si.name
          )
""",
	),
	dict(
		id="q134",
		trap="negation",
		ordered=False,
		q="Which items have no shipment history at all (no line on any posted delivery)?",
		sql="""SELECT i.name, i.item_name
        FROM "tabItem" i
        WHERE NOT EXISTS (
          SELECT 1 FROM "tabDelivery Note Item" dni
          WHERE dni.item_code = i.name AND dni.docstatus = 1
        )
        ORDER BY 1
""",
	),
	dict(
		id="q135",
		trap="sign",
		ordered=False,
		q="How many units have we received into stock in total (a positive quantity figure)?",
		sql="""SELECT sum(actual_qty) AS total_received
        FROM "tabStock Ledger Entry"
        WHERE actual_qty > 0 AND voucher_type = 'Purchase Invoice'
""",
	),
	dict(
		id="q136",
		trap="sign",
		ordered=False,
		q="How many units have we shipped to customers in total (as a positive count, even though the ledger records issues as negative)?",
		sql="""SELECT abs(sum(actual_qty)) AS total_shipped
        FROM "tabStock Ledger Entry"
        WHERE actual_qty < 0 AND voucher_type = 'Delivery Note'
""",
	),
	dict(
		id="q137",
		trap="sign",
		ordered=False,
		q="What is our net stock movement (receipts positive, issues negative) across the whole ledger?",
		sql="""SELECT sum(actual_qty) AS net
        FROM "tabStock Ledger Entry"
""",
	),
	dict(
		id="q138",
		trap="sign",
		ordered=False,
		q="For each voucher type, what is the net quantity moved (receipts positive, issues negative)?",
		sql="""SELECT voucher_type, sum(actual_qty) AS net_qty
        FROM "tabStock Ledger Entry"
        GROUP BY 1
        ORDER BY voucher_type
""",
	),
	dict(
		id="q139",
		trap="derived",
		ordered=False,
		q="What is the net units position per item (total received from purchase bills minus total shipped to customers)?",
		sql="""WITH r AS (
          SELECT item_code, sum(actual_qty) AS received
          FROM "tabStock Ledger Entry"
          WHERE voucher_type = 'Purchase Invoice'
          GROUP BY 1
        ),
        s AS (
          SELECT item_code, abs(sum(actual_qty)) AS shipped
          FROM "tabStock Ledger Entry"
          WHERE voucher_type = 'Delivery Note'
          GROUP BY 1
        )
        SELECT coalesce(r.item_code, s.item_code) AS item_code,
               coalesce(r.received, 0) - coalesce(s.shipped, 0) AS net
        FROM r FULL OUTER JOIN s ON s.item_code = r.item_code
        ORDER BY 1
""",
	),
	dict(
		id="q140",
		trap="derived",
		ordered=False,
		q="Which item/warehouse pairs currently have a negative on-hand stock value (i.e. the cumulative valuation is below zero)?",
		sql="""SELECT item_code, warehouse, qty_after_transaction AS qty, stock_value AS value
        FROM (
          SELECT item_code, warehouse, qty_after_transaction, stock_value,
                 row_number() OVER (PARTITION BY item_code, warehouse ORDER BY name DESC) AS rn
          FROM "tabStock Ledger Entry"
        )
        WHERE rn = 1 AND stock_value < 0
        ORDER BY item_code, warehouse
""",
	),
]

CROSS = [
	# ---- Cross-module - every question spans at least two of the three -------------
	dict(
		id="q141",
		trap="derived",
		ordered=True,
		q="For every item we both buy and sell, what is the gap between its average sales rate and its average purchase rate, expressed in company currency?",
		sql="""WITH s AS (SELECT sii.item_code, AVG(sii.base_rate) AS avg_sale
                   FROM "tabSales Invoice Item" sii
                   JOIN "tabSales Invoice" si ON si.name = sii.parent
                  WHERE si.docstatus = 1 AND si.is_return = 0
                  GROUP BY sii.item_code),
            p AS (SELECT pii.item_code, AVG(pii.base_rate) AS avg_cost
                   FROM "tabPurchase Invoice Item" pii
                   JOIN "tabPurchase Invoice" pi ON pi.name = pii.parent
                  WHERE pi.docstatus = 1 AND pi.is_return = 0
                  GROUP BY pii.item_code)
        SELECT s.item_code, (s.avg_sale - p.avg_cost) AS rate_gap
          FROM s JOIN p USING (item_code)
         ORDER BY rate_gap DESC, s.item_code
""",
	),
	dict(
		id="q142",
		trap="derived",
		ordered=True,
		q="Which ten items deliver the highest gross margin, expressed as a percentage of cost, when we compare their average sales rate against their average purchase rate in company currency?",
		sql="""WITH s AS (SELECT sii.item_code, AVG(sii.base_rate) AS avg_sale
                   FROM "tabSales Invoice Item" sii
                   JOIN "tabSales Invoice" si ON si.name = sii.parent
                  WHERE si.docstatus = 1 AND si.is_return = 0
                  GROUP BY sii.item_code),
            p AS (SELECT pii.item_code, AVG(pii.base_rate) AS avg_cost
                   FROM "tabPurchase Invoice Item" pii
                   JOIN "tabPurchase Invoice" pi ON pi.name = pii.parent
                  WHERE pi.docstatus = 1 AND pi.is_return = 0
                   GROUP BY pii.item_code)
        SELECT s.item_code,
               (s.avg_sale - p.avg_cost) / NULLIF(p.avg_cost, 0) AS margin_pct
          FROM s JOIN p USING (item_code)
         ORDER BY margin_pct DESC, s.item_code
         LIMIT 10
""",
	),
	dict(
		id="q143",
		trap="derived",
		ordered=True,
		q="For each item group we both buy and sell, what gross margin do we make in company currency?",
		sql="""WITH sales AS (SELECT sii.item_group, SUM(sii.base_amount) AS revenue
                         FROM "tabSales Invoice Item" sii
                         JOIN "tabSales Invoice" si ON si.name = sii.parent
                        WHERE si.docstatus = 1 AND si.is_return = 0
                        GROUP BY sii.item_group),
            purch AS (SELECT pii.item_group, SUM(pii.base_amount) AS cost
                         FROM "tabPurchase Invoice Item" pii
                         JOIN "tabPurchase Invoice" pi ON pi.name = pii.parent
                        WHERE pi.docstatus = 1 AND pi.is_return = 0
                        GROUP BY pii.item_group)
        SELECT sales.item_group, (sales.revenue - purch.cost) AS gross_margin
          FROM sales JOIN purch USING (item_group)
         ORDER BY gross_margin DESC, sales.item_group
""",
	),
	dict(
		id="q144",
		trap="derived",
		ordered=False,
		q="How much gross profit (company currency) have we made on each item whose purchase and sales invoices are both submitted?",
		sql="""WITH s AS (SELECT sii.item_code, SUM(sii.base_amount) AS rev
                   FROM "tabSales Invoice Item" sii
                   JOIN "tabSales Invoice" si ON si.name = sii.parent
                  WHERE si.docstatus = 1 AND si.is_return = 0
                  GROUP BY sii.item_code),
            p AS (SELECT pii.item_code, SUM(pii.base_amount) AS cost
                   FROM "tabPurchase Invoice Item" pii
                   JOIN "tabPurchase Invoice" pi ON pi.name = pii.parent
                  WHERE pi.docstatus = 1 AND pi.is_return = 0
                   GROUP BY pii.item_code)
        SELECT s.item_code, (s.rev - p.cost) AS gross_profit
          FROM s JOIN p USING (item_code)
""",
	),
	dict(
		id="q145",
		trap="derived",
		ordered=True,
		q="For each item that has been both purchased and sold, what is its average sales rate compared to its most recent purchase rate, in company currency?",
		sql="""WITH last_buy AS (SELECT pii.item_code, AVG(pii.base_rate) AS buy_rate
                            FROM "tabPurchase Invoice Item" pii
                            JOIN "tabPurchase Invoice" pi ON pi.name = pii.parent
                           WHERE pi.docstatus = 1 AND pi.is_return = 0
                           GROUP BY pii.item_code),
            avg_sell AS (SELECT sii.item_code, AVG(sii.base_rate) AS sell_rate
                            FROM "tabSales Invoice Item" sii
                            JOIN "tabSales Invoice" si ON si.name = sii.parent
                           WHERE si.docstatus = 1 AND si.is_return = 0
                           GROUP BY sii.item_code)
        SELECT a.item_code, a.sell_rate - b.buy_rate AS premium
          FROM avg_sell a JOIN last_buy b USING (item_code)
         ORDER BY premium DESC, a.item_code
""",
	),
	dict(
		id="q146",
		trap="derived",
		ordered=True,
		q="How much stock is on hand today for the ten items we have billed the most revenue on?",
		sql="""WITH top_rev AS (SELECT sii.item_code, SUM(sii.base_amount) AS rev
                            FROM "tabSales Invoice Item" sii
                            JOIN "tabSales Invoice" si ON si.name = sii.parent
                           WHERE si.docstatus = 1 AND si.is_return = 0
                           GROUP BY sii.item_code
                           ORDER BY rev DESC
                           LIMIT 10)
        SELECT tr.item_code,
               COALESCE(SUM(sle.actual_qty), 0) AS on_hand
          FROM top_rev tr
          LEFT JOIN "tabStock Ledger Entry" sle ON sle.item_code = tr.item_code
         GROUP BY tr.item_code
         ORDER BY on_hand DESC, tr.item_code
""",
	),
	dict(
		id="q147",
		trap="derived",
		ordered=False,
		q="How does the company-currency cash we have collected from customers compare with the company-currency value of all posted purchase bills?",
		sql="""SELECT (SELECT SUM(pe.base_received_amount)
                  FROM "tabPayment Entry" pe
                 WHERE pe.docstatus = 1 AND pe.payment_type = 'Receive')
             AS cash_in_company_currency,
            (SELECT SUM(pi.base_grand_total)
                  FROM "tabPurchase Invoice" pi
                  JOIN "tabPurchase Invoice Item" pii ON pii.parent = pi.name
                 WHERE pi.docstatus = 1 AND pi.is_return = 0)
             AS billed_supplier_obligations
""",
	),
	dict(
		id="q148",
		trap="derived",
		ordered=False,
		q="What are the total outstanding amounts on submitted sales invoices and submitted purchase bills in company currency?",
		sql="""SELECT (SELECT SUM(si.outstanding_amount)
                  FROM "tabSales Invoice" si
                  JOIN "tabSales Invoice Item" sii ON sii.parent = si.name
                 WHERE si.docstatus = 1 AND si.is_return = 0)
             AS receivable_outstanding,
            (SELECT SUM(pi.outstanding_amount)
                  FROM "tabPurchase Invoice" pi
                  JOIN "tabPurchase Invoice Item" pii ON pii.parent = pi.name
                 WHERE pi.docstatus = 1 AND pi.is_return = 0)
             AS payable_outstanding
""",
	),
	dict(
		id="q149",
		trap="derived",
		ordered=True,
		q="For each supplier, what is the gross margin on their items in company currency, computed as the average sales rate minus the average purchase rate of items they supply?",
		sql="""WITH buy AS (SELECT pi.supplier, pii.item_code, AVG(pii.base_rate) AS buy_rate
                      FROM "tabPurchase Invoice Item" pii
                      JOIN "tabPurchase Invoice" pi ON pi.name = pii.parent
                     WHERE pi.docstatus = 1 AND pi.is_return = 0
                     GROUP BY pi.supplier, pii.item_code),
            sell AS (SELECT sii.item_code, AVG(sii.base_rate) AS sell_rate
                      FROM "tabSales Invoice Item" sii
                      JOIN "tabSales Invoice" si ON si.name = sii.parent
                     WHERE si.docstatus = 1 AND si.is_return = 0
                      GROUP BY sii.item_code)
        SELECT buy.supplier, AVG(sell.sell_rate - buy.buy_rate) AS avg_margin
          FROM buy JOIN sell USING (item_code)
         GROUP BY buy.supplier
         ORDER BY avg_margin DESC, buy.supplier
""",
	),
	dict(
		id="q150",
		trap="derived",
		ordered=True,
		q="For each territory where we bill customers, how much revenue did we book and how much of that revenue was actually shipped to customers?",
		sql="""WITH s AS (SELECT si.territory, SUM(si.base_grand_total) AS revenue
                   FROM "tabSales Invoice" si
                   JOIN "tabSales Invoice Item" sii ON sii.parent = si.name
                  WHERE si.docstatus = 1 AND si.is_return = 0
                  GROUP BY si.territory),
            d AS (SELECT dn.territory, SUM(dn.base_grand_total) AS shipped
                   FROM "tabDelivery Note" dn
                   JOIN "tabDelivery Note Item" dni ON dni.parent = dn.name
                  WHERE dn.docstatus = 1 AND dn.is_return = 0
                  GROUP BY dn.territory)
        SELECT s.territory, s.revenue,
               COALESCE(d.shipped, 0) AS shipped_value,
               s.revenue - COALESCE(d.shipped, 0) AS unbilled
          FROM s LEFT JOIN d ON d.territory = s.territory
         ORDER BY unbilled DESC, s.territory
""",
	),
	dict(
		id="q151",
		trap="negation",
		ordered=True,
		q="Which items have we purchased on submitted bills but never sold on a submitted sales invoice?",
		sql="""SELECT pii.item_code
           FROM "tabPurchase Invoice Item" pii
           JOIN "tabPurchase Invoice" pi ON pi.name = pii.parent
          WHERE pi.docstatus = 1 AND pi.is_return = 0
            AND pii.item_code NOT IN (
                  SELECT sii.item_code
                    FROM "tabSales Invoice Item" sii
                    JOIN "tabSales Invoice" si ON si.name = sii.parent
                   WHERE si.docstatus = 1 AND si.is_return = 0)
          ORDER BY pii.item_code
""",
	),
	dict(
		id="q152",
		trap="negation",
		ordered=True,
		q="Which items have we sold on submitted invoices but never purchased on a submitted purchase invoice?",
		sql="""SELECT sii.item_code
           FROM "tabSales Invoice Item" sii
           JOIN "tabSales Invoice" si ON si.name = sii.parent
          WHERE si.docstatus = 1 AND si.is_return = 0
            AND sii.item_code NOT IN (
                  SELECT pii.item_code
                    FROM "tabPurchase Invoice Item" pii
                    JOIN "tabPurchase Invoice" pi ON pi.name = pii.parent
                   WHERE pi.docstatus = 1 AND pi.is_return = 0)
          ORDER BY sii.item_code
""",
	),
	dict(
		id="q153",
		trap="negation",
		ordered=False,
		q="How many submitted, non-return sales invoices have no associated delivery note?",
		sql="""SELECT COUNT(*) AS unbilled_shipped
           FROM "tabSales Invoice" si
           JOIN "tabSales Invoice Item" sii ON sii.parent = si.name
          WHERE si.docstatus = 1 AND si.is_return = 0
            AND NOT EXISTS (SELECT 1 FROM "tabDelivery Note Item" dni
                             JOIN "tabDelivery Note" dn ON dn.name = dni.parent
                            WHERE dni.against_sales_invoice = si.name
                              AND dn.docstatus = 1)
""",
	),
	dict(
		id="q154",
		trap="negation",
		ordered=True,
		q="Which submitted purchase orders have not been fully received, have no submitted purchase invoice, and yet their items have already been received into stock?",
		sql="""SELECT po.name
           FROM "tabPurchase Order" po
           JOIN "tabPurchase Order Item" poi ON poi.parent = po.name
          WHERE po.docstatus = 1 AND po.per_received < 100
            AND NOT EXISTS (SELECT 1 FROM "tabPurchase Invoice Item" pii
                             JOIN "tabPurchase Invoice" pi ON pi.name = pii.parent
                            WHERE pii.purchase_order = po.name
                              AND pi.docstatus = 1)
            AND poi.item_code IN (SELECT DISTINCT sle.item_code
                                    FROM "tabStock Ledger Entry" sle
                                   WHERE sle.actual_qty > 0)
          ORDER BY po.name
""",
	),
	dict(
		id="q155",
		trap="negation",
		ordered=True,
		q="Which customers still owe us more than 50 percent of their billed amount on submitted sales invoices, have no payment entries in the last year, and the items they buy are well-stocked?",
		sql="""WITH owed AS (
   SELECT si.customer, SUM(si.outstanding_amount) AS owed_amt
     FROM "tabSales Invoice" si
     JOIN "tabSales Invoice Item" sii ON sii.parent = si.name
    WHERE si.docstatus = 1 AND si.is_return = 0
      AND si.outstanding_amount > 0.5 * si.grand_total
    GROUP BY si.customer
   ),
  items AS (
   SELECT si.customer, sii.item_code
     FROM "tabSales Invoice Item" sii
     JOIN "tabSales Invoice" si ON si.name = sii.parent
    WHERE si.docstatus = 1 AND si.is_return = 0
    GROUP BY si.customer, sii.item_code
  ),
  stock AS (
   SELECT i.customer, SUM(sle.actual_qty) AS on_hand
     FROM items i JOIN "tabStock Ledger Entry" sle ON sle.item_code = i.item_code
    GROUP BY i.customer
  )
  SELECT o.customer, o.owed_amt, COALESCE(s.on_hand, 0) AS on_hand
    FROM owed o
    LEFT JOIN stock s ON s.customer = o.customer
   WHERE o.customer NOT IN (
         SELECT pe.party FROM "tabPayment Entry" pe
          WHERE pe.docstatus = 1 AND pe.posting_date >= '2025-08-12')
   ORDER BY o.owed_amt DESC, o.customer
""",
	),
	dict(
		id="q156",
		trap="negation",
		ordered=True,
		q="Which items do we currently hold stock of but have never sold on a submitted sales invoice?",
		sql="""SELECT DISTINCT sle.item_code
           FROM "tabStock Ledger Entry" sle
          WHERE sle.actual_qty > 0
            AND sle.item_code NOT IN (
                  SELECT sii.item_code
                    FROM "tabSales Invoice Item" sii
                    JOIN "tabSales Invoice" si ON si.name = sii.parent
                   WHERE si.docstatus = 1 AND si.is_return = 0)
          ORDER BY sle.item_code
""",
	),
	dict(
		id="q157",
		trap="negation",
		ordered=True,
		q="Which items have been received on submitted purchase invoices but have never been shipped on a submitted delivery note?",
		sql="""SELECT pii.item_code
           FROM "tabPurchase Invoice Item" pii
           JOIN "tabPurchase Invoice" pi ON pi.name = pii.parent
          WHERE pi.docstatus = 1 AND pi.is_return = 0
            AND pii.item_code NOT IN (
                  SELECT dni.item_code
                    FROM "tabDelivery Note Item" dni
                    JOIN "tabDelivery Note" dn ON dn.name = dni.parent
                   WHERE dn.docstatus = 1 AND dn.is_return = 0)
          ORDER BY pii.item_code
""",
	),
	dict(
		id="q158",
		trap="join",
		ordered=True,
		q="For every supplier, what is the company-currency revenue we have billed for the items they supply?",
		sql="""SELECT pi.supplier, SUM(sii.base_amount) AS revenue
           FROM "tabPurchase Invoice Item" pii
           JOIN "tabPurchase Invoice" pi ON pi.name = pii.parent
           JOIN "tabSales Invoice Item" sii ON sii.item_code = pii.item_code
           JOIN "tabSales Invoice" si ON si.name = sii.parent
          WHERE pi.docstatus = 1 AND pi.is_return = 0
            AND si.docstatus = 1 AND si.is_return = 0
          GROUP BY pi.supplier
          ORDER BY revenue DESC, pi.supplier
""",
	),
	dict(
		id="q159",
		trap="join",
		ordered=True,
		q="For each item, how many distinct suppliers have billed us and how many distinct customers have bought it?",
		sql="""WITH s AS (
   SELECT i.name AS item_code,
     (SELECT COUNT(DISTINCT pi.supplier) FROM "tabPurchase Invoice Item" pii
        JOIN "tabPurchase Invoice" pi ON pi.name = pii.parent
        WHERE pii.item_code = i.name AND pi.docstatus = 1 AND pi.is_return = 0) AS supplier_count,
     (SELECT COUNT(DISTINCT si.customer) FROM "tabSales Invoice Item" sii
        JOIN "tabSales Invoice" si ON si.name = sii.parent
        WHERE sii.item_code = i.name AND si.docstatus = 1 AND si.is_return = 0) AS customer_count
   FROM "tabItem" i
  )
  SELECT item_code, supplier_count, customer_count
    FROM s
   ORDER BY supplier_count + customer_count DESC, item_code
""",
	),
	dict(
		id="q160",
		trap="join",
		ordered=True,
		q="Per warehouse used in stock movements, what is the company-currency revenue billed for items that pass through it?",
		sql="""WITH ship_items AS (SELECT DISTINCT sle.warehouse, sle.item_code
                              FROM "tabStock Ledger Entry" sle),
            rev AS (SELECT sii.item_code, SUM(sii.base_amount) AS revenue
                      FROM "tabSales Invoice Item" sii
                      JOIN "tabSales Invoice" si ON si.name = sii.parent
                     WHERE si.docstatus = 1 AND si.is_return = 0
                     GROUP BY sii.item_code)
        SELECT si.warehouse, SUM(rev.revenue) AS revenue
           FROM ship_items si JOIN rev ON rev.item_code = si.item_code
          GROUP BY si.warehouse
          ORDER BY revenue DESC, si.warehouse
""",
	),
	dict(
		id="q161",
		trap="join",
		ordered=True,
		q="Per item group, what is the company-currency value of submitted purchases versus submitted sales?",
		sql="""WITH buy AS (SELECT pii.item_group, SUM(pii.base_amount) AS buy_value
                       FROM "tabPurchase Invoice Item" pii
                       JOIN "tabPurchase Invoice" pi ON pi.name = pii.parent
                      WHERE pi.docstatus = 1 AND pi.is_return = 0
                      GROUP BY pii.item_group),
            sell AS (SELECT sii.item_group, SUM(sii.base_amount) AS sell_value
                       FROM "tabSales Invoice Item" sii
                       JOIN "tabSales Invoice" si ON si.name = sii.parent
                      WHERE si.docstatus = 1 AND si.is_return = 0
                       GROUP BY sii.item_group)
        SELECT COALESCE(buy.item_group, sell.item_group) AS item_group,
               COALESCE(buy.buy_value, 0) AS purchases,
               COALESCE(sell.sell_value, 0) AS sales
          FROM buy FULL OUTER JOIN sell USING (item_group)
         ORDER BY item_group
""",
	),
	dict(
		id="q162",
		trap="join",
		ordered=True,
		q="Which customers have made payments in EUR, and how many units of the items they bought were purchased from suppliers on submitted purchase invoices?",
		sql="""WITH eu AS (SELECT DISTINCT pe.party
                       FROM "tabPayment Entry" pe
                      WHERE pe.docstatus = 1 AND pe.paid_from_account_currency = 'EUR'),
            items AS (SELECT si.customer, sii.item_code
                        FROM "tabSales Invoice Item" sii
                        JOIN "tabSales Invoice" si ON si.name = sii.parent
                       WHERE si.docstatus = 1 AND si.is_return = 0
                       GROUP BY si.customer, sii.item_code),
            buy AS (SELECT i.customer, SUM(pii.qty) AS units_purchased
                      FROM items i
                      JOIN "tabPurchase Invoice Item" pii ON pii.item_code = i.item_code
                      JOIN "tabPurchase Invoice" pi ON pi.name = pii.parent
                     WHERE pi.docstatus = 1 AND pi.is_return = 0
                     GROUP BY i.customer)
        SELECT eu.party, COALESCE(b.units_purchased, 0) AS units_purchased
          FROM eu LEFT JOIN buy b ON b.customer = eu.party
         ORDER BY units_purchased DESC, eu.party
""",
	),
	dict(
		id="q163",
		trap="join",
		ordered=True,
		q="For each warehouse, what is the total quantity issued (negative stock movement) and the company-currency value of submitted purchase receipts that landed there?",
		sql="""WITH w AS (
   SELECT sle.warehouse,
          SUM(CASE WHEN sle.actual_qty < 0 THEN -sle.actual_qty ELSE 0 END) AS qty_issued
     FROM "tabStock Ledger Entry" sle
    GROUP BY sle.warehouse
  )
  SELECT w.warehouse, w.qty_issued,
         COALESCE((SELECT SUM(pii.base_amount)
                  FROM "tabPurchase Invoice Item" pii
                  JOIN "tabPurchase Invoice" pi ON pi.name = pii.parent
                 WHERE pii.warehouse = w.warehouse
                   AND pi.docstatus = 1 AND pi.is_return = 0), 0) AS received_value
    FROM w
   ORDER BY received_value DESC, w.warehouse
""",
	),
	dict(
		id="q164",
		trap="join",
		ordered=True,
		q="For each item, list its primary supplier (the one with most invoiced quantity) and the total quantity we have sold on submitted sales invoices, ranked by units sold.",
		sql="""WITH buy AS (SELECT pii.item_code, pi.supplier, SUM(pii.qty) AS qty_buy,
                            ROW_NUMBER() OVER (PARTITION BY pii.item_code ORDER BY SUM(pii.qty) DESC, pi.supplier) AS rn
                       FROM "tabPurchase Invoice Item" pii
                       JOIN "tabPurchase Invoice" pi ON pi.name = pii.parent
                      WHERE pi.docstatus = 1 AND pi.is_return = 0
                      GROUP BY pii.item_code, pi.supplier),
            sell AS (SELECT sii.item_code, SUM(sii.qty) AS qty_sell
                       FROM "tabSales Invoice Item" sii
                       JOIN "tabSales Invoice" si ON si.name = sii.parent
                      WHERE si.docstatus = 1 AND si.is_return = 0
                      GROUP BY sii.item_code)
        SELECT buy.item_code, buy.supplier, COALESCE(sell.qty_sell, 0) AS qty_sold
           FROM buy LEFT JOIN sell ON sell.item_code = buy.item_code
          WHERE buy.rn = 1
          ORDER BY qty_sold DESC, buy.item_code
""",
	),
	dict(
		id="q165",
		trap="grain",
		ordered=True,
		q="Per purchase order line, what quantity was ordered, how much has been invoiced, and how much has actually been received into stock?",
		sql="""WITH inv AS (
   SELECT pii.purchase_order, pii.item_code, SUM(pii.qty) AS invoiced_qty
     FROM "tabPurchase Invoice Item" pii
     JOIN "tabPurchase Invoice" pi ON pi.name = pii.parent
    WHERE pi.docstatus = 1 AND pi.is_return = 0
      AND pii.purchase_order IS NOT NULL AND pii.purchase_order != ''
    GROUP BY pii.purchase_order, pii.item_code
  ),
  rec AS (
   SELECT pii.purchase_order AS po, pii.item_code, SUM(sle.actual_qty) AS received_qty
     FROM "tabStock Ledger Entry" sle
     JOIN "tabPurchase Invoice Item" pii ON pii.parent = sle.voucher_no AND pii.item_code = sle.item_code
     JOIN "tabPurchase Invoice" pi ON pi.name = pii.parent
    WHERE sle.voucher_type = 'Purchase Invoice' AND sle.actual_qty > 0
      AND pi.docstatus = 1 AND pii.purchase_order IS NOT NULL
    GROUP BY pii.purchase_order, pii.item_code
  )
  SELECT poi.parent AS po, poi.item_code, poi.qty AS ordered_qty,
         COALESCE(inv.invoiced_qty, 0) AS invoiced_qty,
         COALESCE(rec.received_qty, 0) AS received_qty
    FROM "tabPurchase Order Item" poi
    JOIN "tabPurchase Order" po ON po.name = poi.parent
    LEFT JOIN inv ON inv.purchase_order = poi.parent AND inv.item_code = poi.item_code
    LEFT JOIN rec ON rec.po = poi.parent AND rec.item_code = poi.item_code
   WHERE po.docstatus = 1
   ORDER BY poi.parent, poi.item_code
""",
	),
	dict(
		id="q166",
		trap="grain",
		ordered=False,
		q="For each sales invoice line, what is the invoiced quantity and how much of it has been delivered according to delivery notes?",
		sql="""SELECT sii.parent AS invoice,
               sii.item_code,
               sii.qty AS invoiced_qty,
               COALESCE((SELECT SUM(dni.qty)
                  FROM "tabDelivery Note Item" dni
                  JOIN "tabDelivery Note" dn ON dn.name = dni.parent
                 WHERE dni.against_sales_invoice = sii.parent
                   AND dni.item_code = sii.item_code
                   AND dn.docstatus = 1), 0) AS delivered_qty
           FROM "tabSales Invoice Item" sii
           JOIN "tabSales Invoice" si ON si.name = sii.parent
          WHERE si.docstatus = 1
""",
	),
	dict(
		id="q167",
		trap="grain",
		ordered=True,
		q="For each customer, how many submitted sales invoices do they have, what is the total units billed, and how much have those items cost us to buy from suppliers?",
		sql="""WITH cust AS (
   SELECT si.customer, COUNT(DISTINCT si.name) AS invoice_count, SUM(si.base_grand_total) AS total
     FROM "tabSales Invoice" si
     JOIN "tabSales Invoice Item" sii ON sii.parent = si.name
    WHERE si.docstatus = 1 AND si.is_return = 0
    GROUP BY si.customer
  ),
  cust_items AS (
   SELECT si.customer, sii.item_code
     FROM "tabSales Invoice Item" sii
     JOIN "tabSales Invoice" si ON si.name = sii.parent
    WHERE si.docstatus = 1 AND si.is_return = 0
    GROUP BY si.customer, sii.item_code
  ),
  buy_cost AS (
   SELECT ci.customer, SUM(pii.base_amount) AS supply_cost
     FROM cust_items ci
     JOIN "tabPurchase Invoice Item" pii ON pii.item_code = ci.item_code
     JOIN "tabPurchase Invoice" pi ON pi.name = pii.parent
    WHERE pi.docstatus = 1 AND pi.is_return = 0
    GROUP BY ci.customer
  )
  SELECT c.customer, c.invoice_count, c.total, COALESCE(b.supply_cost, 0) AS supply_cost
    FROM cust c LEFT JOIN buy_cost b ON b.customer = c.customer
   ORDER BY c.total DESC, c.customer
""",
	),
	dict(
		id="q168",
		trap="grain",
		ordered=True,
		q="Per item, what is the total delivered quantity and the total invoiced quantity on submitted documents?",
		sql="""WITH d AS (SELECT dni.item_code, SUM(dni.qty) AS delivered_qty
                     FROM "tabDelivery Note Item" dni
                     JOIN "tabDelivery Note" dn ON dn.name = dni.parent
                    WHERE dn.docstatus = 1 AND dn.is_return = 0
                    GROUP BY dni.item_code),
        s AS (SELECT sii.item_code, SUM(sii.qty) AS invoiced_qty
                     FROM "tabSales Invoice Item" sii
                     JOIN "tabSales Invoice" si ON si.name = sii.parent
                    WHERE si.docstatus = 1 AND si.is_return = 0
                    GROUP BY sii.item_code)
        SELECT d.item_code, d.delivered_qty, COALESCE(s.invoiced_qty, 0) AS invoiced_qty
          FROM d LEFT JOIN s ON s.item_code = d.item_code
         ORDER BY d.delivered_qty DESC, d.item_code
""",
	),
	dict(
		id="q169",
		trap="grain",
		ordered=True,
		q="For each item-warehouse pair, what is the current stock on hand and how much of that item have we sold on submitted sales invoices?",
		sql="""WITH on_hand AS (
   SELECT sle.item_code, sle.warehouse, SUM(sle.actual_qty) AS qty
     FROM "tabStock Ledger Entry" sle
    GROUP BY sle.item_code, sle.warehouse
  ),
  sold AS (
   SELECT sii.item_code, SUM(sii.qty) AS sold
     FROM "tabSales Invoice Item" sii
     JOIN "tabSales Invoice" si ON si.name = sii.parent
    WHERE si.docstatus = 1 AND si.is_return = 0
    GROUP BY sii.item_code
  )
  SELECT o.item_code, o.warehouse, o.qty AS on_hand, COALESCE(s.sold, 0) AS sold
    FROM on_hand o LEFT JOIN sold s ON s.item_code = o.item_code
   ORDER BY o.item_code, o.warehouse
""",
	),
	dict(
		id="q170",
		trap="grain",
		ordered=True,
		q="What is the received-versus-ordered percentage of each submitted purchase order, paired with the count of its submitted bills and total quantity received into stock?",
		sql="""WITH bills AS (
   SELECT po.name AS po, COUNT(DISTINCT pi.name) AS bill_count
     FROM "tabPurchase Order" po
     LEFT JOIN "tabPurchase Invoice Item" pii ON pii.purchase_order = po.name
     LEFT JOIN "tabPurchase Invoice" pi ON pi.name = pii.parent AND pi.docstatus = 1
    WHERE po.docstatus = 1
    GROUP BY po.name
  ),
  received AS (
   SELECT pii.purchase_order AS po, SUM(sle.actual_qty) AS qty_received
     FROM "tabStock Ledger Entry" sle
     JOIN "tabPurchase Invoice Item" pii ON pii.parent = sle.voucher_no AND pii.item_code = sle.item_code
     JOIN "tabPurchase Invoice" pi ON pi.name = pii.parent
    WHERE sle.voucher_type = 'Purchase Invoice' AND sle.actual_qty > 0
      AND pi.docstatus = 1 AND pii.purchase_order IS NOT NULL
    GROUP BY pii.purchase_order
  )
  SELECT po.name, po.per_received, b.bill_count, COALESCE(r.qty_received, 0) AS qty_received
    FROM "tabPurchase Order" po
    JOIN bills b ON b.po = po.name
    LEFT JOIN received r ON r.po = po.name
   ORDER BY po.per_received ASC, po.name
""",
	),
	dict(
		id="q171",
		trap="currency",
		ordered=False,
		q="In USD, how much have we billed customers on submitted sales invoices, and what quantity of those items have we issued out of our warehouses?",
		sql="""SELECT SUM(si.grand_total) AS total_usd,
               COALESCE((SELECT SUM(-sle.actual_qty)
                  FROM "tabStock Ledger Entry" sle
                  JOIN "tabSales Invoice Item" sii ON sii.item_code = sle.item_code
                  JOIN "tabSales Invoice" si2 ON si2.name = sii.parent
                 WHERE sle.actual_qty < 0 AND sle.voucher_type = 'Delivery Note'
                   AND si2.currency = 'USD' AND si2.docstatus = 1 AND si2.is_return = 0), 0) AS qty_issued_usd
           FROM "tabSales Invoice" si
           JOIN "tabSales Invoice Item" sii ON sii.parent = si.name
          WHERE si.docstatus = 1 AND si.is_return = 0
            AND si.currency = 'USD'
""",
	),
	dict(
		id="q172",
		trap="currency",
		ordered=False,
		q="In INR, how much have we been billed by suppliers on submitted purchase invoices, and what quantity of those items have we received into stock?",
		sql="""SELECT SUM(pi.grand_total) AS total_inr,
               COALESCE((SELECT SUM(sle.actual_qty)
                  FROM "tabStock Ledger Entry" sle
                  JOIN "tabPurchase Invoice Item" pii ON pii.item_code = sle.item_code
                  JOIN "tabPurchase Invoice" pi2 ON pi2.name = pii.parent
                 WHERE sle.actual_qty > 0 AND sle.voucher_type = 'Purchase Invoice'
                   AND pi2.currency = 'INR' AND pi2.docstatus = 1 AND pi2.is_return = 0), 0) AS qty_received_inr
           FROM "tabPurchase Invoice" pi
           JOIN "tabPurchase Invoice Item" pii ON pii.parent = pi.name
          WHERE pi.docstatus = 1 AND pi.is_return = 0
            AND pi.currency = 'INR'
""",
	),
	dict(
		id="q173",
		trap="currency",
		ordered=False,
		q="In our company currency, what is the total of all submitted, non-return sales invoices and the total of submitted purchase bills?",
		sql="""SELECT (SELECT SUM(si.base_grand_total)
                  FROM "tabSales Invoice" si
                  JOIN "tabSales Invoice Item" sii ON sii.parent = si.name
                 WHERE si.docstatus = 1 AND si.is_return = 0) AS sales_company,
            (SELECT SUM(pi.base_grand_total)
                  FROM "tabPurchase Invoice" pi
                  JOIN "tabPurchase Invoice Item" pii ON pii.parent = pi.name
                 WHERE pi.docstatus = 1 AND pi.is_return = 0) AS purchases_company
""",
	),
	dict(
		id="q174",
		trap="currency",
		ordered=True,
		q="Per currency, what is the billed sales amount, the cash actually received from customers, and the value of items issued from stock?",
		sql="""WITH s AS (SELECT si.currency, SUM(si.grand_total) AS billed
                     FROM "tabSales Invoice" si
                     JOIN "tabSales Invoice Item" sii ON sii.parent = si.name
                    WHERE si.docstatus = 1 AND si.is_return = 0
                    GROUP BY si.currency),
            p AS (SELECT pe.paid_from_account_currency AS currency, SUM(pe.received_amount) AS received
                     FROM "tabPayment Entry" pe
                    WHERE pe.docstatus = 1
                    GROUP BY pe.paid_from_account_currency),
            d AS (SELECT si.currency, SUM(dni.amount) AS issued
                     FROM "tabDelivery Note Item" dni
                     JOIN "tabDelivery Note" dn ON dn.name = dni.parent
                     JOIN "tabSales Invoice" si ON si.name = dni.against_sales_invoice
                    WHERE dn.docstatus = 1 AND dn.is_return = 0
                    GROUP BY si.currency)
        SELECT COALESCE(s.currency, p.currency, d.currency) AS currency,
               COALESCE(s.billed, 0) AS billed,
               COALESCE(p.received, 0) AS received,
               COALESCE(d.issued, 0) AS issued
          FROM s FULL OUTER JOIN p ON s.currency = p.currency
          FULL OUTER JOIN d ON COALESCE(s.currency, p.currency) = d.currency
         ORDER BY currency
""",
	),
	dict(
		id="q175",
		trap="docstatus",
		ordered=True,
		q="What is the company-currency value of draft purchase invoices versus submitted ones, per supplier group, and the quantity of items received into stock for each?",
		sql="""WITH agg AS (
   SELECT COALESCE(s.supplier_group, '<None>') AS supplier_group,
          pi.docstatus, SUM(pi.base_grand_total) AS total
     FROM "tabPurchase Invoice" pi
     JOIN "tabPurchase Invoice Item" pii ON pii.parent = pi.name
     LEFT JOIN "tabSupplier" s ON s.name = pi.supplier
    WHERE pi.is_return = 0
    GROUP BY s.supplier_group, pi.docstatus
  ),
  recv AS (
   SELECT COALESCE(s.supplier_group, '<None>') AS supplier_group,
          SUM(sle.actual_qty) AS qty_received
     FROM "tabStock Ledger Entry" sle
     JOIN "tabPurchase Invoice Item" pii ON pii.parent = sle.voucher_no AND pii.item_code = sle.item_code
     JOIN "tabPurchase Invoice" pi ON pi.name = pii.parent AND pi.is_return = 0
     LEFT JOIN "tabSupplier" s ON s.name = pi.supplier
    WHERE sle.voucher_type = 'Purchase Invoice' AND sle.actual_qty > 0
    GROUP BY s.supplier_group
  )
  SELECT a.supplier_group, a.docstatus, a.total, COALESCE(r.qty_received, 0) AS qty_received
    FROM agg a LEFT JOIN recv r ON r.supplier_group = a.supplier_group
   ORDER BY a.supplier_group, a.docstatus
""",
	),
	dict(
		id="q176",
		trap="docstatus",
		ordered=True,
		q="Per territory, how many sales invoices are still in draft versus submitted, and how many delivery notes did we ship there?",
		sql="""WITH inv AS (
   SELECT si.territory, si.docstatus, COUNT(*) AS n
     FROM "tabSales Invoice" si
     JOIN "tabSales Invoice Item" sii ON sii.parent = si.name
    GROUP BY si.territory, si.docstatus
  ),
  ship AS (
   SELECT dn.territory, COUNT(*) AS deliveries
     FROM "tabDelivery Note" dn
     JOIN "tabDelivery Note Item" dni ON dni.parent = dn.name
    WHERE dn.docstatus = 1 AND dn.is_return = 0
    GROUP BY dn.territory
  )
  SELECT inv.territory, inv.docstatus, inv.n, COALESCE(s.deliveries, 0) AS deliveries
    FROM inv LEFT JOIN ship s ON s.territory = inv.territory
   ORDER BY inv.territory, inv.docstatus
""",
	),
	dict(
		id="q177",
		trap="docstatus",
		ordered=True,
		q="Per customer, compare the company-currency billed amount on cancelled sales invoices to the submitted ones, with the company-currency value of delivery notes shipped to them.",
		sql="""WITH inv AS (
   SELECT si.customer, si.docstatus, SUM(si.base_grand_total) AS billed
     FROM "tabSales Invoice" si
     JOIN "tabSales Invoice Item" sii ON sii.parent = si.name
    WHERE si.is_return = 0
    GROUP BY si.customer, si.docstatus
  ),
  ship AS (
   SELECT dn.customer, SUM(dn.base_grand_total) AS shipped
     FROM "tabDelivery Note" dn
     JOIN "tabDelivery Note Item" dni ON dni.parent = dn.name
    WHERE dn.docstatus = 1 AND dn.is_return = 0
    GROUP BY dn.customer
  )
  SELECT inv.customer, inv.docstatus, inv.billed, COALESCE(s.shipped, 0) AS shipped
    FROM inv LEFT JOIN ship s ON s.customer = inv.customer
   ORDER BY inv.customer, inv.docstatus
""",
	),
	dict(
		id="q178",
		trap="ambiguity",
		ordered=False,
		q="How many purchase orders did we place with our suppliers, and how many delivery notes did those items eventually ship to customers?",
		sql="""SELECT (SELECT COUNT(*)
                  FROM "tabPurchase Order" po
                  JOIN "tabPurchase Order Item" poi ON poi.parent = po.name
                 WHERE po.docstatus = 1) AS orders_placed,
            (SELECT COUNT(*)
                  FROM "tabDelivery Note" dn
                  JOIN "tabDelivery Note Item" dni ON dni.parent = dn.name
                 WHERE dn.docstatus = 1 AND dn.is_return = 0) AS orders_received
""",
	),
	dict(
		id="q179",
		trap="ambiguity",
		ordered=False,
		q="How many delivery notes did we ship to customers, and how many submitted sales invoices are we billing them on?",
		sql="""SELECT (SELECT COUNT(*)
                  FROM "tabDelivery Note" dn
                  JOIN "tabDelivery Note Item" dni ON dni.parent = dn.name
                 WHERE dn.docstatus = 1 AND dn.is_return = 0) AS delivery_notes,
            (SELECT COUNT(*)
                  FROM "tabSales Invoice" si
                  JOIN "tabSales Invoice Item" sii ON sii.parent = si.name
                 WHERE si.docstatus = 1 AND si.is_return = 0) AS sales_invoices
""",
	),
	dict(
		id="q180",
		trap="ambiguity",
		ordered=True,
		q="List our ten best-selling items by units sold on submitted sales invoices, with the units purchased on submitted purchase bills.",
		sql="""WITH sold AS (
   SELECT sii.item_code, SUM(sii.qty) AS units_sold
     FROM "tabSales Invoice Item" sii
     JOIN "tabSales Invoice" si ON si.name = sii.parent
    WHERE si.docstatus = 1 AND si.is_return = 0
    GROUP BY sii.item_code
  ),
  bought AS (
   SELECT pii.item_code, SUM(pii.qty) AS units_bought
     FROM "tabPurchase Invoice Item" pii
     JOIN "tabPurchase Invoice" pi ON pi.name = pii.parent
    WHERE pi.docstatus = 1 AND pi.is_return = 0
    GROUP BY pii.item_code
  )
  SELECT s.item_code, s.units_sold, COALESCE(b.units_bought, 0) AS units_bought
    FROM sold s LEFT JOIN bought b ON b.item_code = s.item_code
   ORDER BY s.units_sold DESC, s.item_code
   LIMIT 10
""",
	),
]

SELLING = [
	# ---- Selling - written after the frozen forty, over ground they left -----------
	dict(
		id="q181",
		trap="tree",
		ordered=False,
		q="What is the total revenue generated by India and all its sub-territories?",
		sql="""WITH RECURSIVE ind AS (
        SELECT name FROM "tabTerritory" WHERE name = 'India'
        UNION ALL
        SELECT t.name FROM "tabTerritory" t JOIN ind ON t.parent_territory = ind.name
       )
       SELECT sum(base_grand_total) AS total FROM "tabSales Invoice" si
       WHERE si.docstatus = 1 AND si.is_return = 0 AND si.territory IN (SELECT name FROM ind)
""",
	),
	dict(
		id="q182",
		trap="tree",
		ordered=False,
		q="How many customers are based in India or any of its sub-territories?",
		sql="""WITH RECURSIVE ind AS (
        SELECT name FROM "tabTerritory" WHERE name = 'India'
        UNION ALL
        SELECT t.name FROM "tabTerritory" t JOIN ind ON t.parent_territory = ind.name
       )
       SELECT count(*) AS n FROM "tabCustomer" c WHERE c.territory IN (SELECT name FROM ind)
""",
	),
	dict(
		id="q183",
		trap="tree",
		ordered=False,
		q="What is the total revenue generated by the United States and its sub-territories?",
		sql="""WITH RECURSIVE us AS (
        SELECT name FROM "tabTerritory" WHERE name = 'United States'
        UNION ALL
        SELECT t.name FROM "tabTerritory" t JOIN us ON t.parent_territory = us.name
       )
       SELECT sum(base_grand_total) AS total FROM "tabSales Invoice" si
       WHERE si.docstatus = 1 AND si.is_return = 0 AND si.territory IN (SELECT name FROM us)
""",
	),
	dict(
		id="q184",
		trap="tree",
		ordered=False,
		q="How many leaf item groups exist (item groups with no further sub-groups)?",
		sql='SELECT count(*) AS n FROM "tabItem Group" WHERE is_group = 0',
	),
	dict(
		id="q185",
		trap="tree",
		ordered=False,
		q="How many leaf territories are there (territories that are not grouping nodes)?",
		sql='SELECT count(*) AS n FROM "tabTerritory" WHERE is_group = 0',
	),
	dict(
		id="q186",
		trap="negation",
		ordered=False,
		q="How many items on our master have never been sold on any submitted invoice?",
		sql="""SELECT count(*) AS n FROM "tabItem" i WHERE NOT EXISTS (
        SELECT 1 FROM "tabSales Invoice Item" sii JOIN "tabSales Invoice" si ON si.name = sii.parent
        WHERE sii.item_code = i.name AND si.docstatus = 1)
""",
	),
	dict(
		id="q187",
		trap="negation",
		ordered=False,
		q="How many items in the Products group have never been sold?",
		sql="""SELECT count(*) AS n FROM "tabItem" i WHERE i.item_group = 'Products' AND NOT EXISTS (
        SELECT 1 FROM "tabSales Invoice Item" sii JOIN "tabSales Invoice" si ON si.name = sii.parent
        WHERE sii.item_code = i.name AND si.docstatus = 1)
""",
	),
	dict(
		id="q188",
		trap="negation",
		ordered=False,
		q="How many items in the Services group have never been sold?",
		sql="""SELECT count(*) AS n FROM "tabItem" i WHERE i.item_group = 'Services' AND NOT EXISTS (
        SELECT 1 FROM "tabSales Invoice Item" sii JOIN "tabSales Invoice" si ON si.name = sii.parent
        WHERE sii.item_code = i.name AND si.docstatus = 1)
""",
	),
	dict(
		id="q189",
		trap="negation",
		ordered=False,
		q="List territories that have no customers on file.",
		sql="""SELECT name FROM "tabTerritory" t WHERE NOT EXISTS (
        SELECT 1 FROM "tabCustomer" c WHERE c.territory = t.name) ORDER BY name
""",
	),
	dict(
		id="q190",
		trap="negation",
		ordered=False,
		q="How many items in the Consumable group have never been sold?",
		sql="""SELECT count(*) AS n FROM "tabItem" i WHERE i.item_group = 'Consumable' AND NOT EXISTS (
        SELECT 1 FROM "tabSales Invoice Item" sii JOIN "tabSales Invoice" si ON si.name = sii.parent
        WHERE sii.item_code = i.name AND si.docstatus = 1)
""",
	),
	dict(
		id="q191",
		trap="display",
		ordered=False,
		q="How many distinct items have a display name on submitted invoice lines that differs from the item code?",
		sql="""SELECT count(DISTINCT sii.item_code) AS n FROM "tabSales Invoice Item" sii
        JOIN "tabSales Invoice" si ON si.name = sii.parent
        WHERE si.docstatus = 1 AND sii.item_name != sii.item_code
""",
	),
	dict(
		id="q192",
		trap="display",
		ordered=True,
		q="Top 5 items by standard rate, return their display names.",
		sql='SELECT item_name FROM "tabItem" ORDER BY standard_rate DESC, item_name LIMIT 5',
	),
	dict(
		id="q193",
		trap="display",
		ordered=False,
		q="How many submitted invoice line items have a display item name that differs from the item code?",
		sql="""SELECT count(*) AS n FROM "tabSales Invoice Item" sii
        JOIN "tabSales Invoice" si ON si.name = sii.parent
        WHERE si.docstatus = 1 AND sii.item_name != sii.item_code
""",
	),
	dict(
		id="q194",
		trap="grain",
		ordered=False,
		q="How many units in total have we sold on submitted invoices, excluding returns?",
		sql="""SELECT sum(sii.qty) AS total FROM "tabSales Invoice Item" sii
        JOIN "tabSales Invoice" si ON si.name = sii.parent
        WHERE si.docstatus = 1 AND si.is_return = 0
""",
	),
	dict(
		id="q195",
		trap="grain",
		ordered=False,
		q="What is the average quantity per line item on submitted invoices, excluding returns?",
		sql="""SELECT avg(sii.qty) AS avg_qty FROM "tabSales Invoice Item" sii
        JOIN "tabSales Invoice" si ON si.name = sii.parent
        WHERE si.docstatus = 1 AND si.is_return = 0
""",
	),
	dict(
		id="q196",
		trap="grain",
		ordered=False,
		q="How many line items have we issued on Karnataka invoices?",
		sql="""SELECT count(*) AS n FROM "tabSales Invoice Item" sii
        JOIN "tabSales Invoice" si ON si.name = sii.parent
        WHERE si.docstatus = 1 AND si.territory = 'Karnataka'
""",
	),
	dict(
		id="q197",
		trap="grain",
		ordered=True,
		q="How many distinct items have we sold per year on submitted invoices, in chronological order?",
		sql="""SELECT EXTRACT('year' FROM si.posting_date) AS y, count(DISTINCT sii.item_code) AS n
        FROM "tabSales Invoice" si
        JOIN "tabSales Invoice Item" sii ON sii.parent = si.name
        WHERE si.docstatus = 1 AND si.is_return = 0 GROUP BY 1 ORDER BY 1
""",
	),
	dict(
		id="q198",
		trap="currency",
		ordered=True,
		q="Show outstanding amount in company currency, broken down by transaction currency, highest first.",
		sql="""SELECT currency, sum(outstanding_amount * conversion_rate) AS total FROM "tabSales Invoice"
        WHERE docstatus = 1 GROUP BY currency ORDER BY total DESC, currency
""",
	),
	dict(
		id="q199",
		trap="currency",
		ordered=True,
		q="Revenue in company currency for 2026 by quarter, in chronological order.",
		sql="""SELECT date_trunc('quarter', posting_date) AS q, sum(base_grand_total) AS total FROM "tabSales Invoice"
        WHERE docstatus = 1 AND is_return = 0 AND posting_date >= DATE '2026-01-01' GROUP BY 1 ORDER BY 1
""",
	),
	dict(
		id="q200",
		trap="currency",
		ordered=True,
		q="Net revenue in company currency by transaction currency, considering returns, highest first.",
		sql="""SELECT currency, sum(base_grand_total) AS total FROM "tabSales Invoice"
        WHERE docstatus = 1 GROUP BY currency ORDER BY total DESC, currency
""",
	),
	dict(
		id="q201",
		trap="domain",
		ordered=False,
		q="How many submitted invoices have a status of 'Credit Note Issued'?",
		sql="""SELECT count(*) AS n FROM "tabSales Invoice" WHERE docstatus = 1 AND status = 'Credit Note Issued'
""",
	),
	dict(
		id="q202",
		trap="domain",
		ordered=True,
		q="How many submitted invoices fall into each overdue bucket from the due date, ordered by bucket.",
		sql="""SELECT
          CASE
            WHEN due_date >= CURRENT_DATE THEN 'Not yet due'
            WHEN due_date >= CURRENT_DATE - INTERVAL '30 days' THEN '1-30 days overdue'
            WHEN due_date >= CURRENT_DATE - INTERVAL '60 days' THEN '31-60 days overdue'
            WHEN due_date >= CURRENT_DATE - INTERVAL '90 days' THEN '61-90 days overdue'
            ELSE '90+ days overdue'
          END AS bucket,
          count(*) AS n
        FROM "tabSales Invoice" WHERE docstatus = 1 GROUP BY 1 ORDER BY bucket
""",
	),
	dict(
		id="q203",
		trap="derived",
		ordered=False,
		q="What fraction of our customers have come back for a second purchase?",
		sql="""WITH stats AS (
        SELECT customer, count(*) AS inv_count FROM "tabSales Invoice" WHERE docstatus = 1 GROUP BY customer
       )
       SELECT (SELECT count(*) FROM stats WHERE inv_count > 1) * 1.0 / (SELECT count(*) FROM stats) AS rate
       FROM (SELECT 1)
""",
	),
	dict(
		id="q204",
		trap="derived",
		ordered=False,
		q="On average, how many days span between a customer's first and last submitted invoice?",
		sql="""WITH cust AS (
        SELECT customer, max(posting_date) AS last_d, min(posting_date) AS first_d
        FROM "tabSales Invoice" WHERE docstatus = 1 GROUP BY customer
       )
       SELECT avg(date_diff('day', first_d, last_d)) AS avg_days FROM cust
""",
	),
	dict(
		id="q205",
		trap="ambiguity",
		ordered=False,
		q="How many distinct items have we ever sold on a submitted invoice?",
		sql="""SELECT count(DISTINCT sii.item_code) AS n FROM "tabSales Invoice Item" sii
        JOIN "tabSales Invoice" si ON si.name = sii.parent
        WHERE si.docstatus = 1
""",
	),
]

#: The frozen forty keep their ids and their text. `ordered` is read off the
#: grader's list rather than re-decided here - deciding again could disagree
#: with the run this set extends, and a benchmark that quietly re-scores its
#: own history is worth nothing.
Q: list[dict] = (
	[{**q, "ordered": q["id"] in ORDERED, "module": "selling"} for q in FROZEN]
	+ [{**q, "module": "buying"} for q in BUYING]
	+ [{**q, "module": "stock"} for q in STOCK]
	+ [{**q, "module": "cross"} for q in CROSS]
	+ [{**q, "module": "selling"} for q in SELLING]
)
