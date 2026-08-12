# Copyright (c) 2026, Nakhoda and contributors
# For license information, please see license.txt
"""A benchmark database with real ERPNext schemas and invented rows.

`semantic_bench/build.py` did this for eight DocTypes in one module and is
frozen: its value is that it reproduces byte-identically, so it is copied from
rather than edited. This generalises it, because `12-build-plan.md` Phase 2b
needs at least three modules and forty questions cannot reach them.

**Schemas are real, rows are not.** Columns come from the DocType JSON shipped
with ERPNext, so every name, type, Link target and Select domain is the one a
real site has - which is the whole subject of the measurement. Rows are
generated, because the alternative is committing a customer's ledger to a public
repository. Realism is needed only where a gold answer depends on it: money in
several currencies so `base_` columns matter, submitted alongside draft and
cancelled so `docstatus` matters, returns as negative quantities, and items that
were bought but never sold so a question can ask for them.

Three modules, chosen for what they let a question span rather than for size:

    Selling     Customer, Sales Invoice and its items, Item, Territory, ...
    Buying      Supplier, Purchase Invoice, Purchase Order and their items
    Stock       Warehouse, Delivery Note and its items, Stock Ledger Entry

The seams between them are where the interesting questions live: margin needs a
purchase rate and a sale rate, "bought but never sold" needs both item sets, and
stock value by warehouse needs ledger entries that agree with the documents that
produced them.

Determinism is by construction: one `random.Random(seed)`, drawn from in a fixed
order, so the same seed yields the same database.

**ERPNext v16.29.0 is a pin, not a detail.** The frozen artifact was derived from
that release, and v15 moves fields on five of the eight DocTypes they share -
`Sales Invoice` alone differs by eleven columns. Built against the pin, this
module reproduces the frozen schema exactly: same names, same types, same order,
zero differences across all eight tables. Built against anything else it
reproduces that release instead, which is a fine database and a different
measurement. `test_fixture.py` holds the equality and skips off-pin rather than
asserting a version it was not given.

    SEMANTIC_BENCH_ERPNEXT=/path/to/apps/erpnext/erpnext \\
    SEMANTIC_BENCH_FRAPPE=/path/to/apps/frappe/frappe \\
    python -m nakhoda.bench.fixture
"""

from __future__ import annotations

import datetime as dt
import json
import os
import random
import re
from collections.abc import Iterable
from functools import lru_cache
from pathlib import Path

#: Module -> the DocTypes it contributes. Order is the order tables are created.
MODULES: dict[str, tuple[str, ...]] = {
	"Selling": (
		"Territory",
		"Item Group",
		"Sales Person",
		"Customer",
		"Item",
		"Sales Invoice",
		"Sales Invoice Item",
		"Payment Entry",
	),
	"Buying": (
		"Supplier Group",
		"Supplier",
		"Purchase Order",
		"Purchase Order Item",
		"Purchase Invoice",
		"Purchase Invoice Item",
	),
	"Stock": (
		"Warehouse",
		"Delivery Note",
		"Delivery Note Item",
		"Stock Ledger Entry",
	),
}

DOCTYPES: tuple[str, ...] = tuple(dt_ for group in MODULES.values() for dt_ in group)

#: Fieldtype -> DuckDB type. Copied from `semantic_bench/build.py`; the schema
#: test fails if the two ever disagree.
SQLT = {
	"Data": "VARCHAR", "Link": "VARCHAR", "Select": "VARCHAR", "Small Text": "VARCHAR",
	"Text": "VARCHAR", "Long Text": "VARCHAR", "Text Editor": "VARCHAR", "Code": "VARCHAR",
	"Read Only": "VARCHAR", "Dynamic Link": "VARCHAR", "Attach": "VARCHAR",
	"Attach Image": "VARCHAR", "Barcode": "VARCHAR", "Currency": "DECIMAL(18,6)",
	"Float": "DOUBLE", "Percent": "DOUBLE", "Int": "BIGINT", "Check": "TINYINT",
	"Date": "DATE", "Datetime": "TIMESTAMP", "Time": "TIME", "Duration": "DOUBLE",
	"Rating": "DOUBLE", "JSON": "VARCHAR", "Password": "VARCHAR", "Signature": "VARCHAR",
	"Geolocation": "VARCHAR", "Color": "VARCHAR", "Icon": "VARCHAR",
	"Autocomplete": "VARCHAR", "Phone": "VARCHAR", "Markdown Editor": "VARCHAR",
}  # fmt: skip

SKIP = {
	"Section Break", "Column Break", "Tab Break", "HTML", "Button", "Heading", "Fold",
	"Table", "Table MultiSelect", "HTML Editor", "Image",
}  # fmt: skip

STD = [
	("name", "VARCHAR"), ("owner", "VARCHAR"), ("creation", "TIMESTAMP"),
	("modified", "TIMESTAMP"), ("modified_by", "VARCHAR"), ("docstatus", "TINYINT"),
	("idx", "BIGINT"),
]  # fmt: skip

CHILD_STD = [("parent", "VARCHAR"), ("parentfield", "VARCHAR"), ("parenttype", "VARCHAR")]


def _app(name: str, env: str) -> Path:
	"""apps/<name>/<name>, from the environment or the bench this file lives in."""
	if p := os.environ.get(env):
		return Path(p)
	apps = Path(__file__).resolve().parents[3]
	found = apps / name / name
	if found.is_dir():
		return found
	raise SystemExit(f"{name} not found; set {env} to apps/{name}/{name}")


#: The release the frozen artifact was derived from. Off this pin the schemas are
#: a different release's, and comparing them measures ERPNext, not this builder.
PINNED_ERPNEXT = "16.29.0"


def erpnext_version() -> str:
	"""The version of the checkout the columns are actually being read from."""
	text = (_app("erpnext", "SEMANTIC_BENCH_ERPNEXT") / "__init__.py").read_text()
	found = re.search(r"""^__version__\s*=\s*["']([^"']+)""", text, re.M)
	return found.group(1) if found else "unknown"


@lru_cache(maxsize=1)
def _index() -> dict[str, Path]:
	"""slug -> DocType JSON, from one walk of both apps.

	The frozen builder globs the whole tree once per DocType and spends most of
	its six minutes doing it. Twenty DocTypes made that worth fixing.
	"""
	found: dict[str, Path] = {}
	for root in (_app("erpnext", "SEMANTIC_BENCH_ERPNEXT"), _app("frappe", "SEMANTIC_BENCH_FRAPPE")):
		for path in root.rglob("doctype/*/*.json"):
			if path.stem == path.parent.name:
				found.setdefault(path.stem, path)
	return found


def load(doctype: str) -> dict:
	"""The DocType definition as ERPNext ships it."""
	slug = doctype.lower().replace(" ", "_")
	path = _index().get(slug)
	if path is None:
		raise SystemExit(f"missing doctype {doctype}")
	return json.loads(path.read_text())


def columns(meta: dict) -> list[tuple[str, str]]:
	"""Physical columns for one DocType, in the order Frappe would create them."""
	out = list(STD) + (list(CHILD_STD) if meta.get("istable") else [])
	seen = {c for c, _ in out}
	for field in meta.get("fields", []):
		fieldtype, fieldname = field.get("fieldtype"), field.get("fieldname")
		if fieldtype in SKIP or not fieldname or fieldname in seen:
			continue
		out.append((fieldname, SQLT.get(fieldtype, "VARCHAR")))
		seen.add(fieldname)
	return out


def create_table(name: str, cols: list[tuple[str, str]], *, indent: str = "") -> str:
	"""The `CREATE TABLE` arm A shows a model and `build` runs, from one source."""
	body = f",\n{indent}".join(f'"{c}" {t}' for c, t in cols)
	return f'CREATE TABLE "tab{name}" (\n{indent}{body}\n);'


def ddl(doctypes: Iterable[str] = DOCTYPES) -> str:
	"""Arm A: the schema as a warehouse sees it after ingestion."""
	lines = ["-- Database: DuckDB. Schema as ingested. Use double quotes for identifiers.", ""]
	for name in doctypes:
		lines.append(create_table(name, columns(load(name)), indent="  "))
		lines.append("")
	return "\n".join(lines)


def semantic(doctypes: Iterable[str] = DOCTYPES) -> str:
	"""Arm B: the product's own semantic layer over the same tables.

	Generated by `nakhoda.semantic.model`, not by this module - the arm has to be
	the thing that ships, or the measurement is of a context file nobody uses.
	Reads DocType JSON off disk, so it needs no site.
	"""
	from nakhoda.semantic.model import describe, render

	return render([describe(load(name)) for name in doctypes])


def contexts(doctypes: Iterable[str] = DOCTYPES) -> dict[str, str]:
	"""Both arms, keyed as `semantic_bench/generated.json` keys them."""
	names = tuple(doctypes)
	return {"A_raw": ddl(names), "B_semantic": semantic(names)}


# --------------------------------------------------------------------- rows

NOW = dt.datetime(2026, 8, 1, 9, 0, 0)
COMPANY = "Acme Inc"
FX = {"USD": 1.0, "EUR": 1.09, "INR": 0.012, "GBP": 1.27}
BASE = dict(
	owner="Administrator", creation=NOW, modified=NOW,
	modified_by="Administrator", docstatus=0, idx=0,
)  # fmt: skip

#: name, parent, is_group, warehouse_type. Two are deliberately never stocked:
#: "which warehouses hold nothing" is a question, and an empty answer is not one.
WAREHOUSES = (
	("All Warehouses - AI", None, 1, None),
	("Stores - AI", "All Warehouses - AI", 0, None),
	("Finished Goods - AI", "All Warehouses - AI", 0, None),
	("Work In Progress - AI", "All Warehouses - AI", 0, "Transit"),
	("Rejected - AI", "All Warehouses - AI", 0, None),
	("Goods In Transit - AI", "All Warehouses - AI", 0, "Transit"),
)

#: An item is received into and issued from one warehouse. Splitting issues
#: across warehouses that never received the item gives a warehouse a large
#: negative balance, which is not a hard question - it is a broken fixture.
STOCKING = ("Stores - AI", "Finished Goods - AI", "Work In Progress - AI")


class Rows:
	"""Generated rows, one bucket per DocType, built in dependency order."""

	def __init__(self, seed: int = 7) -> None:
		self.rnd = random.Random(seed)
		self.data: dict[str, list[dict]] = {name: [] for name in DOCTYPES}
		self.home: dict[str, str] = {}
		self.valuation: dict[str, float] = {}

	def add(self, doctype: str, rows: list[dict]) -> list[dict]:
		self.data[doctype].extend(rows)
		return rows

	# -- Selling ---------------------------------------------------------
	def selling(self) -> None:
		rnd = self.rnd
		territories = [
			("All Territories", None), ("India", "All Territories"),
			("United States", "All Territories"), ("Germany", "All Territories"),
			("Kenya", "All Territories"), ("Maharashtra", "India"), ("Karnataka", "India"),
			("California", "United States"), ("Texas", "United States"),
		]  # fmt: skip
		leaf_terr = ["Maharashtra", "Karnataka", "California", "Texas", "Germany", "Kenya"]
		groups = [
			("All Item Groups", None), ("Raw Material", "All Item Groups"),
			("Products", "All Item Groups"), ("Consumable", "All Item Groups"),
			("Services", "All Item Groups"),
		]  # fmt: skip
		leaf_groups = ["Raw Material", "Products", "Consumable", "Services"]
		persons = ["Amara Okafor", "Devi Raman", "Jonas Weber", "Lucia Marin", "Sam Patel"]

		self.add("Territory", [
			dict(BASE, name=t, territory_name=t, parent_territory=p,
				is_group=1 if p is None or t in ("India", "United States") else 0)
			for t, p in territories
		])  # fmt: skip
		self.add("Item Group", [
			dict(BASE, name=g, item_group_name=g, parent_item_group=p, is_group=1 if p is None else 0)
			for g, p in groups
		])  # fmt: skip
		self.add("Sales Person", [
			dict(BASE, name=p, sales_person_name=p, enabled=1) for p in persons
		])  # fmt: skip

		customers = self.add("Customer", [
			dict(BASE, name=f"Customer {i:03d}", customer_name=f"Customer {i:03d}",
				territory=rnd.choice(leaf_terr), customer_group="Commercial",
				default_currency=rnd.choice(["USD", "USD", "USD", "EUR", "INR"]),
				disabled=1 if i % 40 == 0 else 0)
			for i in range(1, 121)
		])  # fmt: skip

		# Twelve items are never sold and six are never bought, so that "bought
		# but never sold" and its mirror have non-empty answers.
		items = self.add("Item", [
			dict(BASE, name=f"ITEM-{i:04d}", item_name=f"Item {i:04d}",
				item_group=rnd.choice(leaf_groups), stock_uom="Nos", is_stock_item=1,
				disabled=0, standard_rate=round(rnd.uniform(20, 900), 2))
			for i in range(1, 73)
		])  # fmt: skip
		self.sellable = items[:60]
		self.buyable = items[6:]
		self.home = {item["name"]: rnd.choice(STOCKING) for item in items}
		# A moving-average cost, so `stock_value = qty_after_transaction *
		# valuation_rate` holds exactly on every ledger row and can be asserted.
		self.valuation = {item["name"]: round(item["standard_rate"] * 0.55, 2) for item in items}

		invoices, lines = [], []
		for n in range(1, 4201):
			cust = rnd.choice(customers)
			day = dt.date(2026, 1, 1) + dt.timedelta(days=rnd.randint(-730, 210))
			currency = cust["default_currency"]
			rate = FX[currency]
			roll = rnd.random()
			if roll < 0.11:
				docstatus, status = 0, "Draft"
			elif roll < 0.17:
				docstatus, status = 2, "Cancelled"
			else:
				docstatus = 1
				status = rnd.choices(
					["Paid", "Unpaid", "Overdue", "Partly Paid", "Return", "Credit Note Issued"],
					weights=[50, 18, 14, 8, 5, 5],
				)[0]
			is_return = 1 if status == "Return" else 0
			name = f"ACC-SINV-2026-{n:05d}"
			total = 0.0
			for li in range(rnd.randint(1, 4)):
				item = rnd.choice(self.sellable)
				qty = float(rnd.randint(1, 25)) * (-1 if is_return else 1)
				unit = round(item["standard_rate"] * rnd.uniform(0.85, 1.2), 2)
				amount = round(qty * unit, 2)
				total += amount
				lines.append(dict(BASE, name=f"{name}-{li}", parent=name, parentfield="items",
					parenttype="Sales Invoice", docstatus=docstatus, idx=li + 1,
					item_code=item["name"], item_name=item["item_name"],
					item_group=item["item_group"], qty=qty, rate=unit, amount=amount,
					base_rate=round(unit * rate, 6), base_amount=round(amount * rate, 6),
					net_rate=unit, net_amount=amount, base_net_rate=round(unit * rate, 6),
					base_net_amount=round(amount * rate, 6), price_list_rate=unit,
					base_price_list_rate=round(unit * rate, 6), stock_qty=qty, uom="Nos"))  # fmt: skip
			total = round(total, 2)
			paid = total if status == "Paid" else (round(total * 0.4, 2) if status == "Partly Paid" else 0.0)
			invoices.append(dict(BASE, name=name, docstatus=docstatus, status=status,
				customer=cust["name"], customer_name=cust["customer_name"],
				territory=cust["territory"], posting_date=day,
				due_date=day + dt.timedelta(days=30), currency=currency, conversion_rate=rate,
				grand_total=total, base_grand_total=round(total * rate, 6), total=total,
				base_total=round(total * rate, 6), net_total=total,
				base_net_total=round(total * rate, 6), rounded_total=total,
				base_rounded_total=round(total * rate, 6),
				outstanding_amount=round(total - paid, 2), is_return=is_return,
				company=COMPANY, is_pos=0, update_stock=0))  # fmt: skip
		self.add("Sales Invoice", invoices)
		self.add("Sales Invoice Item", lines)

		payable = [i for i in invoices if i["status"] in ("Paid", "Partly Paid")][:1500]
		self.add("Payment Entry", [
			dict(BASE, name=f"ACC-PAY-2026-{i:05d}", docstatus=1 if i % 25 else 0,
				payment_type="Receive", party_type="Customer", party=inv["customer"],
				party_name=inv["customer_name"], posting_date=inv["posting_date"],
				paid_amount=float(inv["grand_total"]) - float(inv["outstanding_amount"]),
				base_paid_amount=float(inv["grand_total"]) - float(inv["outstanding_amount"]),
				received_amount=float(inv["grand_total"]) - float(inv["outstanding_amount"]),
				base_received_amount=float(inv["grand_total"]) - float(inv["outstanding_amount"]),
				source_exchange_rate=1.0, target_exchange_rate=1.0,
				paid_from_account_currency=inv["currency"], company=COMPANY)
			for i, inv in enumerate(payable)
		])  # fmt: skip

	# -- Buying ----------------------------------------------------------
	def buying(self) -> None:
		rnd = self.rnd
		supplier_groups = [
			("All Supplier Groups", None), ("Local", "All Supplier Groups"),
			("Import", "All Supplier Groups"), ("Services", "All Supplier Groups"),
		]  # fmt: skip
		self.add("Supplier Group", [
			dict(BASE, name=g, supplier_group_name=g, parent_supplier_group=p,
				is_group=1 if p is None else 0)
			for g, p in supplier_groups
		])  # fmt: skip

		countries = ["India", "Germany", "United States", "Kenya", "United Kingdom"]
		suppliers = self.add("Supplier", [
			dict(BASE, name=f"Supplier {i:02d}", supplier_name=f"Supplier {i:02d}",
				supplier_group=rnd.choice(["Local", "Import", "Services"]),
				country=rnd.choice(countries), supplier_type="Company",
				default_currency=rnd.choice(["USD", "USD", "EUR", "INR", "GBP"]),
				disabled=1 if i % 13 == 0 else 0, is_frozen=0)
			for i in range(1, 41)
		])  # fmt: skip

		# Purchase orders first: invoices reference them, and receipt shortfall
		# is what makes "still outstanding" a real question.
		orders, order_lines = [], []
		for n in range(1, 901):
			sup = rnd.choice(suppliers)
			day = dt.date(2026, 1, 1) + dt.timedelta(days=rnd.randint(-700, 120))
			currency = sup["default_currency"]
			rate = FX[currency]
			roll = rnd.random()
			docstatus = 0 if roll < 0.08 else (2 if roll < 0.13 else 1)
			received = 0.0 if docstatus != 1 else rnd.choice([0.0, 40.0, 75.0, 100.0, 100.0, 100.0])
			status = {0: "Draft", 2: "Cancelled"}.get(docstatus) or (
				"Completed" if received == 100.0 else "To Receive and Bill"
			)
			name = f"PUR-ORD-2026-{n:05d}"
			total = 0.0
			for li in range(rnd.randint(1, 3)):
				item = rnd.choice(self.buyable)
				qty = float(rnd.randint(5, 60))
				unit = round(item["standard_rate"] * rnd.uniform(0.45, 0.7), 2)
				amount = round(qty * unit, 2)
				total += amount
				order_lines.append(dict(BASE, name=f"{name}-{li}", parent=name,
					parentfield="items", parenttype="Purchase Order", docstatus=docstatus,
					idx=li + 1, item_code=item["name"], item_name=item["item_name"],
					item_group=item["item_group"], qty=qty, rate=unit, amount=amount,
					base_rate=round(unit * rate, 6), base_amount=round(amount * rate, 6),
					received_qty=round(qty * received / 100, 2), warehouse=self.home[item["name"]],
					schedule_date=day + dt.timedelta(days=14), uom="Nos", stock_qty=qty))  # fmt: skip
			total = round(total, 2)
			orders.append(dict(BASE, name=name, docstatus=docstatus, status=status,
				supplier=sup["name"], supplier_name=sup["supplier_name"],
				transaction_date=day, schedule_date=day + dt.timedelta(days=14),
				currency=currency, conversion_rate=rate, per_received=received,
				grand_total=total, base_grand_total=round(total * rate, 6), total=total,
				base_total=round(total * rate, 6), company=COMPANY))  # fmt: skip
		self.add("Purchase Order", orders)
		self.add("Purchase Order Item", order_lines)

		submitted_orders = [o for o in orders if o["docstatus"] == 1]
		invoices, lines = [], []
		for n in range(1, 1201):
			order = rnd.choice(submitted_orders)
			sup_name = order["supplier"]
			currency = order["currency"]
			rate = FX[currency]
			day = order["transaction_date"] + dt.timedelta(days=rnd.randint(1, 45))
			roll = rnd.random()
			if roll < 0.09:
				docstatus, status = 0, "Draft"
			elif roll < 0.14:
				docstatus, status = 2, "Cancelled"
			else:
				docstatus = 1
				status = rnd.choices(
					["Paid", "Unpaid", "Overdue", "Return", "Debit Note Issued"],
					weights=[46, 26, 16, 6, 6],
				)[0]
			is_return = 1 if status == "Return" else 0
			name = f"ACC-PINV-2026-{n:05d}"
			total = 0.0
			for li in range(rnd.randint(1, 3)):
				item = rnd.choice(self.buyable)
				qty = float(rnd.randint(5, 60)) * (-1 if is_return else 1)
				unit = round(item["standard_rate"] * rnd.uniform(0.45, 0.7), 2)
				amount = round(qty * unit, 2)
				total += amount
				lines.append(dict(BASE, name=f"{name}-{li}", parent=name, parentfield="items",
					parenttype="Purchase Invoice", docstatus=docstatus, idx=li + 1,
					item_code=item["name"], item_name=item["item_name"],
					item_group=item["item_group"], qty=qty, rate=unit, amount=amount,
					base_rate=round(unit * rate, 6), base_amount=round(amount * rate, 6),
					net_rate=unit, net_amount=amount, base_net_amount=round(amount * rate, 6),
					warehouse=self.home[item["name"]], purchase_order=order["name"], uom="Nos",
					stock_qty=qty))  # fmt: skip
			total = round(total, 2)
			paid = total if status == "Paid" else 0.0
			invoices.append(dict(BASE, name=name, docstatus=docstatus, status=status,
				supplier=sup_name, supplier_name=sup_name, posting_date=day,
				due_date=day + dt.timedelta(days=30), bill_no=f"INV-{n:05d}",
				currency=currency, conversion_rate=rate, grand_total=total,
				base_grand_total=round(total * rate, 6), total=total,
				base_total=round(total * rate, 6), net_total=total,
				base_net_total=round(total * rate, 6),
				outstanding_amount=round(total - paid, 2), is_return=is_return,
				company=COMPANY))  # fmt: skip
		self.add("Purchase Invoice", invoices)
		self.add("Purchase Invoice Item", lines)

	# -- Stock -----------------------------------------------------------
	def stock(self) -> None:
		rnd = self.rnd
		self.add("Warehouse", [
			dict(BASE, name=w, warehouse_name=w.replace(" - AI", ""), parent_warehouse=p,
				is_group=g, warehouse_type=t, company=COMPANY, disabled=0)
			for w, p, g, t in WAREHOUSES
		])  # fmt: skip

		# Delivery notes are raised against submitted, non-return invoices, so a
		# question can ask what was invoiced but never delivered.
		invoiced = [i for i in self.data["Sales Invoice"] if i["docstatus"] == 1 and not i["is_return"]]
		rnd.shuffle(invoiced)
		by_invoice: dict[str, list[dict]] = {}
		for line in self.data["Sales Invoice Item"]:
			by_invoice.setdefault(line["parent"], []).append(line)

		notes, note_lines = [], []
		for n, inv in enumerate(invoiced[:1500], start=1):
			day = inv["posting_date"] + dt.timedelta(days=rnd.randint(0, 21))
			docstatus = 1 if rnd.random() > 0.07 else 0
			status = "Completed" if docstatus == 1 else "Draft"
			name = f"MAT-DN-2026-{n:05d}"
			total = 0.0
			for li, line in enumerate(by_invoice.get(inv["name"], [])):
				amount = float(line["amount"])
				total += amount
				note_lines.append(dict(BASE, name=f"{name}-{li}", parent=name,
					parentfield="items", parenttype="Delivery Note", docstatus=docstatus,
					idx=li + 1, item_code=line["item_code"], item_name=line["item_name"],
					item_group=line["item_group"], qty=line["qty"], rate=line["rate"],
					amount=amount, base_amount=line["base_amount"],
					warehouse=self.home[line["item_code"]], against_sales_invoice=inv["name"],
					si_detail=line["name"], uom="Nos", stock_qty=line["qty"]))  # fmt: skip
			total = round(total, 2)
			notes.append(dict(BASE, name=name, docstatus=docstatus, status=status,
				customer=inv["customer"], customer_name=inv["customer_name"],
				territory=inv["territory"], posting_date=day, currency=inv["currency"],
				conversion_rate=inv["conversion_rate"], grand_total=total,
				base_grand_total=round(total * float(inv["conversion_rate"]), 6),
				is_return=0, company=COMPANY))  # fmt: skip
		self.add("Delivery Note", notes)
		self.add("Delivery Note Item", note_lines)

		# The ledger is derived from the documents above rather than invented, so
		# that a question can cross-check one against the other. Both sides are
		# valued at the item's cost, never at the price it was sold for: a
		# delivery that removes its own sale value would drain the warehouse of
		# money it never held, and "stock value by warehouse" would have a gold
		# answer that no amount of correct SQL could make sensible.
		ledger = []
		for line in self.data["Purchase Invoice Item"]:
			if line["docstatus"] == 1:
				ledger.append(("Purchase Invoice", line, float(line["qty"])))
		for line in note_lines:
			if line["docstatus"] == 1:
				ledger.append(("Delivery Note", line, -abs(float(line["qty"]))))

		parent_date = {
			row["name"]: row["posting_date"]
			for group in ("Purchase Invoice", "Delivery Note")
			for row in self.data[group]
		}
		running: dict[tuple[str, str], float] = {}
		entries = []
		for i, (voucher_type, line, qty) in enumerate(ledger, start=1):
			item = line["item_code"]
			warehouse = self.home[item]
			key = (item, warehouse)
			running[key] = round(running.get(key, 0.0) + qty, 2)
			rate = self.valuation[item]
			entries.append(dict(BASE, name=f"SLE-{i:07d}", docstatus=1,
				item_code=item, warehouse=warehouse,
				posting_date=parent_date.get(line["parent"], dt.date(2026, 1, 1)),
				actual_qty=qty, qty_after_transaction=running[key],
				valuation_rate=rate, stock_value=round(running[key] * rate, 2),
				stock_value_difference=round(qty * rate, 2), voucher_type=voucher_type,
				voucher_no=line["parent"], voucher_detail_no=line["name"],
				company=COMPANY, is_cancelled=0))  # fmt: skip
		self.add("Stock Ledger Entry", entries)


#: DuckDB type -> the Arrow type a column is staged as. `DECIMAL` is staged as a
#: double and cast by the INSERT: the fixture's money is generated from floats,
#: so building exact decimals here would only be precision theatre.
ARROW = {
	"VARCHAR": "string", "DOUBLE": "float64", "DECIMAL(18,6)": "float64",
	"BIGINT": "int64", "TINYINT": "int8", "DATE": "date32",
	"TIMESTAMP": "timestamp", "TIME": "time64",
}  # fmt: skip


def build(path: Path, *, seed: int = 7) -> dict[str, int]:
	"""Create the database and return the row count per table.

	Rows are loaded a column at a time through Arrow. A parameterised
	`executemany` binds every cell individually, which for these table widths -
	`Sales Invoice` is 140 columns - took six minutes for 34k rows.
	"""
	import duckdb
	import pyarrow as pa

	arrow = {
		"string": pa.string(), "float64": pa.float64(), "int64": pa.int64(),
		"int8": pa.int8(), "date32": pa.date32(), "timestamp": pa.timestamp("us"),
		"time64": pa.time64("us"),
	}  # fmt: skip

	rows = Rows(seed)
	rows.selling()
	rows.buying()
	rows.stock()

	path.parent.mkdir(parents=True, exist_ok=True)
	path.unlink(missing_ok=True)

	con = duckdb.connect(str(path))
	counts = {}
	try:
		for name in DOCTYPES:
			cols = columns(load(name))
			con.execute(create_table(name, cols))
			table = rows.data[name]
			counts[name] = len(table)
			if not table:
				continue
			order = {c: i for i, (c, _) in enumerate(cols)}
			staged: list[list] = [[None] * len(table) for _ in cols]
			for r, row in enumerate(table):
				for key, value in row.items():
					staged[order[key]][r] = value
			batch = pa.Table.from_arrays(
				[pa.array(col, type=arrow[ARROW[t]]) for col, (_, t) in zip(staged, cols, strict=True)],
				names=[c for c, _ in cols],
			)
			con.register("_batch", batch)
			con.execute(f'INSERT INTO "tab{name}" SELECT * FROM _batch')
			con.unregister("_batch")
		con.commit()
	finally:
		con.close()
	return counts


if __name__ == "__main__":
	import sys

	out = Path(os.environ.get("NAKHODA_BENCH_OUT", "/tmp/nakhoda-fixture")) / "erp.duckdb"
	counts = build(out)
	print(f"{out}: {sum(counts.values())} rows")
	for module, names in MODULES.items():
		print(f"  {module}: " + ", ".join(f"{n} {counts[n]}" for n in names))
	sys.exit(0)
