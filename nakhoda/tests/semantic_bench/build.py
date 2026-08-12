"""Build an authentic ERPNext-shaped DuckDB + the two competing context representations.

Context A = what a warehouse sees after ingesting the tables (DDL only).
Context B = what frappe.get_meta() already knows (DocType-derived semantic layer).

Both describe the SAME database. Nothing question-specific is in either.
"""
import json, glob, random, pathlib, datetime as dt, os, sys
import duckdb

# Frozen evidence: this reproduced md5-identical on a from-scratch rebuild (README).
# Two productisation changes only, both required to run it anywhere but the machine
# it was written on - paths resolved instead of hardcoded, and import made an error
# so that test discovery cannot silently trigger a 6-minute destructive rebuild.
if __name__ != "__main__":
    raise ImportError(
        "semantic_bench.build is a script, not a module - importing it would rebuild "
        "the fixture. Run: python -m nakhoda.tests.semantic_bench.build"
    )


def _app(name, env):
    """apps/<name>/<name> from $env, else the bench this file lives in."""
    if p := os.environ.get(env):
        return p
    bench = pathlib.Path(__file__).resolve().parents[5]
    if (found := bench / "apps" / name / name).is_dir():
        return str(found)
    sys.exit(f"{name} not found; set {env} to apps/{name}/{name}")


ERP = _app("erpnext", "SEMANTIC_BENCH_ERPNEXT")
FRP = _app("frappe", "SEMANTIC_BENCH_FRAPPE")
BENCH = pathlib.Path(os.environ.get("SEMANTIC_BENCH_OUT", "/tmp/semantic-bench"))
BENCH.mkdir(parents=True, exist_ok=True)
random.seed(7)

WANT = ["Customer", "Sales Invoice", "Sales Invoice Item", "Item",
        "Item Group", "Territory", "Payment Entry", "Sales Person"]


def load_dt(name):
    slug = name.lower().replace(" ", "_")
    for root in (ERP, FRP):
        hits = glob.glob(f"{root}/**/doctype/{slug}/{slug}.json", recursive=True)
        if hits:
            return json.load(open(hits[0]))
    raise SystemExit(f"missing doctype {name}")


meta = {n: load_dt(n) for n in WANT}

SQLT = {"Data": "VARCHAR", "Link": "VARCHAR", "Select": "VARCHAR", "Small Text": "VARCHAR",
        "Text": "VARCHAR", "Long Text": "VARCHAR", "Text Editor": "VARCHAR", "Code": "VARCHAR",
        "Read Only": "VARCHAR", "Dynamic Link": "VARCHAR", "Attach": "VARCHAR",
        "Attach Image": "VARCHAR", "Barcode": "VARCHAR", "Currency": "DECIMAL(18,6)",
        "Float": "DOUBLE", "Percent": "DOUBLE", "Int": "BIGINT", "Check": "TINYINT",
        "Date": "DATE", "Datetime": "TIMESTAMP", "Time": "TIME", "Duration": "DOUBLE",
        "Rating": "DOUBLE", "JSON": "VARCHAR", "Password": "VARCHAR", "Signature": "VARCHAR",
        "Geolocation": "VARCHAR", "Color": "VARCHAR", "Icon": "VARCHAR",
        "Autocomplete": "VARCHAR", "Phone": "VARCHAR", "Markdown Editor": "VARCHAR"}
SKIP = {"Section Break", "Column Break", "Tab Break", "HTML", "Button", "Heading", "Fold",
        "Table", "Table MultiSelect", "HTML Editor", "Image"}
STD = [("name", "VARCHAR"), ("owner", "VARCHAR"), ("creation", "TIMESTAMP"),
       ("modified", "TIMESTAMP"), ("modified_by", "VARCHAR"), ("docstatus", "TINYINT"),
       ("idx", "BIGINT")]
CHILD_STD = [("parent", "VARCHAR"), ("parentfield", "VARCHAR"), ("parenttype", "VARCHAR")]


def cols_for(name):
    d = meta[name]
    out = list(STD) + (list(CHILD_STD) if d.get("istable") else [])
    seen = {c for c, _ in out}
    for f in d.get("fields", []):
        ft, fn = f.get("fieldtype"), f.get("fieldname")
        if ft in SKIP or not fn or fn in seen:
            continue
        out.append((fn, SQLT.get(ft, "VARCHAR")))
        seen.add(fn)
    return out


TBL = {n: f"tab{n}" for n in WANT}
schema_cols = {n: cols_for(n) for n in WANT}

db = BENCH / "erp.duckdb"
if db.exists():
    db.unlink()
con = duckdb.connect(str(db))
for n in WANT:
    ddl = ", ".join(f'"{c}" {t}' for c, t in schema_cols[n])
    con.execute(f'CREATE TABLE "{TBL[n]}" ({ddl})')

# ---------------------------------------------------------------- seed data
TERRITORIES = [("All Territories", None), ("India", "All Territories"),
               ("United States", "All Territories"), ("Germany", "All Territories"),
               ("Kenya", "All Territories"), ("Maharashtra", "India"), ("Karnataka", "India"),
               ("California", "United States"), ("Texas", "United States")]
LEAF_TERR = ["Maharashtra", "Karnataka", "California", "Texas", "Germany", "Kenya"]
GROUPS = [("All Item Groups", None), ("Raw Material", "All Item Groups"),
          ("Products", "All Item Groups"), ("Consumable", "All Item Groups"),
          ("Services", "All Item Groups")]
LEAF_GROUPS = ["Raw Material", "Products", "Consumable", "Services"]
PERSONS = ["Amara Okafor", "Devi Raman", "Jonas Weber", "Lucia Marin", "Sam Patel"]


def ins(table, rows):
    if not rows:
        return
    cols = [c for c, _ in schema_cols[table]]
    idx = {c: i for i, c in enumerate(cols)}
    tup = []
    for r in rows:
        vals = [None] * len(cols)
        for k, v in r.items():
            vals[idx[k]] = v
        tup.append(tuple(vals))
    ph = ", ".join("?" * len(cols))
    con.executemany(f'INSERT INTO "{TBL[table]}" VALUES ({ph})', tup)


NOW = dt.datetime(2026, 8, 1, 9, 0, 0)
base = dict(owner="Administrator", creation=NOW, modified=NOW,
            modified_by="Administrator", docstatus=0, idx=0)

ins("Territory", [dict(base, name=t, territory_name=t, parent_territory=p,
                       is_group=1 if p is None or t in ("India", "United States") else 0)
                  for t, p in TERRITORIES])
ins("Item Group", [dict(base, name=g, item_group_name=g, parent_item_group=p,
                        is_group=1 if p is None else 0) for g, p in GROUPS])
ins("Sales Person", [dict(base, name=p, sales_person_name=p, enabled=1) for p in PERSONS])

customers = []
for i in range(1, 121):
    cn = f"Customer {i:03d}"
    customers.append(dict(base, name=cn, customer_name=cn,
                          territory=random.choice(LEAF_TERR),
                          customer_group="Commercial",
                          default_currency=random.choice(["USD", "USD", "USD", "EUR", "INR"]),
                          disabled=1 if i % 40 == 0 else 0))
ins("Customer", customers)

items = []
for i in range(1, 61):
    items.append(dict(base, name=f"ITEM-{i:04d}", item_name=f"Item {i:04d}",
                      item_group=random.choice(LEAF_GROUPS), stock_uom="Nos",
                      is_stock_item=1, disabled=0,
                      standard_rate=round(random.uniform(20, 900), 2)))
ins("Item", items)

FX = {"USD": 1.0, "EUR": 1.09, "INR": 0.012}
invoices, lines = [], []
inv_no = 0
for _ in range(4200):
    inv_no += 1
    cust = random.choice(customers)
    d = dt.date(2026, 1, 1) + dt.timedelta(days=random.randint(-730, 210))
    cur = cust["default_currency"]
    rate = FX[cur]
    roll = random.random()
    if roll < 0.11:
        docstatus, status = 0, "Draft"          # never counts as revenue
    elif roll < 0.17:
        docstatus, status = 2, "Cancelled"      # never counts as revenue
    else:
        docstatus = 1
        status = random.choices(
            ["Paid", "Unpaid", "Overdue", "Partly Paid", "Return", "Credit Note Issued"],
            weights=[50, 18, 14, 8, 5, 5])[0]
    is_return = 1 if status == "Return" else 0
    nlines = random.randint(1, 4)
    total = 0.0
    inv_name = f"ACC-SINV-2026-{inv_no:05d}"
    for li in range(nlines):
        it = random.choice(items)
        qty = float(random.randint(1, 25))
        r = round(it["standard_rate"] * random.uniform(0.85, 1.2), 2)
        if is_return:
            qty = -qty
        amt = round(qty * r, 2)
        total += amt
        lines.append(dict(base, name=f"{inv_name}-{li}", parent=inv_name,
                          parentfield="items", parenttype="Sales Invoice",
                          docstatus=docstatus, idx=li + 1, item_code=it["name"],
                          item_name=it["item_name"], item_group=it["item_group"],
                          qty=qty, rate=r, amount=amt,
                          base_rate=round(r * rate, 6), base_amount=round(amt * rate, 6),
                          net_rate=r, net_amount=amt,
                          base_net_rate=round(r * rate, 6),
                          base_net_amount=round(amt * rate, 6),
                          price_list_rate=r, base_price_list_rate=round(r * rate, 6),
                          stock_qty=qty, uom="Nos"))
    total = round(total, 2)
    paid = total if status == "Paid" else (round(total * 0.4, 2) if status == "Partly Paid" else 0.0)
    invoices.append(dict(base, name=inv_name, docstatus=docstatus, status=status,
                         customer=cust["name"], customer_name=cust["customer_name"],
                         territory=cust["territory"], posting_date=d,
                         due_date=d + dt.timedelta(days=30), currency=cur,
                         conversion_rate=rate, grand_total=total,
                         base_grand_total=round(total * rate, 6),
                         total=total, base_total=round(total * rate, 6),
                         net_total=total, base_net_total=round(total * rate, 6),
                         rounded_total=total, base_rounded_total=round(total * rate, 6),
                         outstanding_amount=round(total - paid, 2),
                         is_return=is_return, company="Acme Inc",
                         is_pos=0, update_stock=0))
ins("Sales Invoice", invoices)
ins("Sales Invoice Item", lines)

pays = []
for i, inv in enumerate([x for x in invoices if x["status"] in ("Paid", "Partly Paid")][:1500]):
    st = 1 if i % 25 else 0
    pays.append(dict(base, name=f"ACC-PAY-2026-{i:05d}", docstatus=st,
                     payment_type="Receive", party_type="Customer", party=inv["customer"],
                     party_name=inv["customer_name"], posting_date=inv["posting_date"],
                     paid_amount=float(inv["grand_total"]) - float(inv["outstanding_amount"]),
                     base_paid_amount=float(inv["grand_total"]) - float(inv["outstanding_amount"]),
                     received_amount=float(inv["grand_total"]) - float(inv["outstanding_amount"]),
                     base_received_amount=float(inv["grand_total"]) - float(inv["outstanding_amount"]),
                     source_exchange_rate=1.0,
                     target_exchange_rate=1.0,
                     paid_from_account_currency=inv["currency"], company="Acme Inc"))
ins("Payment Entry", pays)
con.commit()

counts = {n: con.execute(f'SELECT count(*) FROM "{TBL[n]}"').fetchone()[0] for n in WANT}
print("rows:", counts)

# ------------------------------------------------- Context A: warehouse view
a = ["-- Database: DuckDB. Schema as ingested. Use double quotes for identifiers.", ""]
for n in WANT:
    a.append(f'CREATE TABLE "{TBL[n]}" (')
    a.append(",\n".join(f'  "{c}" {t}' for c, t in schema_cols[n]))
    a.append(");")
    a.append("")
(BENCH / "context_a.txt").write_text("\n".join(a))

# ------------------------------------- Context B: DocType-derived semantics
LAYOUT_ONLY = {"Section Break", "Column Break", "Tab Break", "HTML", "Button", "Heading", "Fold"}
b = ["-- Database: DuckDB. Use double quotes for identifiers.",
     "-- Semantic model auto-derived from Frappe DocType metadata (frappe.get_meta).",
     "",
     "## Framework conventions (apply to every table)",
     "- Each table `tab<DocType>` stores one DocType. Column `name` is the primary key.",
     "- Tables flagged SUBMITTABLE below use `docstatus`: 0 = Draft, 1 = Submitted, 2 = Cancelled.",
     "  Only docstatus = 1 rows are real business transactions. Drafts and cancelled rows",
     "  must be excluded from any business figure unless explicitly asked for.",
     "- There are NO database foreign keys. Relationships are declared as Link columns;",
     "  a Link column holds the `name` primary key of the table it targets.",
     "- CHILD tables hold row-level detail. They join to their parent through",
     "  `parent` = parent table's `name`, filtered by `parenttype`.",
     "- Columns prefixed `base_` are the same figure converted to company currency using",
     "  `conversion_rate`. Non-prefixed money columns are in the transaction `currency`.",
     "  Aggregating money across rows requires the `base_` column.",
     ""]
for n in WANT:
    d = meta[n]
    flags = []
    if d.get("istable"):
        flags.append("CHILD")
    if d.get("is_submittable"):
        flags.append("SUBMITTABLE")
    if d.get("is_tree"):
        flags.append("TREE")
    b.append(f'### "{TBL[n]}"  -- {n}{"  [" + ", ".join(flags) + "]" if flags else ""}')
    if d.get("description"):
        b.append(f'-- {d["description"]}')
    seen = set()
    for c, t in STD + (CHILD_STD if d.get("istable") else []):
        seen.add(c)
    b.append(f'  name  VARCHAR  -- primary key')
    if d.get("is_submittable"):
        b.append(f'  docstatus  TINYINT  -- 0=Draft 1=Submitted 2=Cancelled')
    if d.get("istable"):
        b.append(f'  parent  VARCHAR  -- FK to parent document name')
        b.append(f'  parenttype  VARCHAR  -- parent DocType name')
    for f in d.get("fields", []):
        ft, fn = f.get("fieldtype"), f.get("fieldname")
        if ft in LAYOUT_ONLY or ft in ("Table", "Table MultiSelect") or not fn or fn in seen:
            continue
        seen.add(fn)
        sql = SQLT.get(ft, "VARCHAR")
        note = []
        lbl = f.get("label")
        if lbl and lbl.lower().replace(" ", "_") != fn:
            note.append(lbl)
        if ft == "Link" and f.get("options"):
            note.append(f'-> "tab{f["options"]}".name')
        if ft == "Select" and f.get("options"):
            vals = [v for v in str(f["options"]).split("\n") if v.strip()]
            if vals and len(vals) <= 14:
                note.append("one of: " + " | ".join(vals))
        if ft == "Check":
            note.append("boolean 0/1")
        if f.get("description"):
            note.append(f["description"].strip().replace("\n", " ")[:110])
        if f.get("reqd"):
            note.append("required")
        b.append(f'  {fn}  {sql}' + (f'  -- {"; ".join(note)}' if note else ""))
    b.append("")
(BENCH / "context_b.txt").write_text("\n".join(b))

for f in ("context_a.txt", "context_b.txt"):
    p = BENCH / f
    print(f, len(p.read_text()), "chars", len(p.read_text().split("\n")), "lines")
con.close()
