# Copyright (c) 2026, Nakhoda and contributors
# For license information, please see license.txt
"""The generalised fixture builds the same schema as the frozen one, and its
three modules are actually joined to each other.

Two claims are worth testing here and the rest is decoration.

The first is that `nakhoda/bench/fixture.py` and `semantic_bench/build.py` agree
about what an ERPNext table looks like. If they do not, the 200-question set
Phase 2b runs on a different database from the 40-question set that produced
95.8%, and the two numbers cannot be put in the same sentence. That is checked by
byte-comparing every column of the eight DocTypes they share - against the frozen
`.duckdb` itself, not against a description of it.

The second is that the modules are joined. A fixture with three modules that
never reference each other is three single-module fixtures in one file, and every
"cross-module" question in the set is quietly single-module. Each seam gets a
query that must return rows.

Determinism gets two tests, because one is not enough: an assertion that the same
seed gives the same data passes trivially if the seed is ignored and the data is
constant. The second test demands that a different seed gives different data.

Needs `duckdb`. The schema comparison additionally needs the frozen artifact and
an ERPNext v16.29.0 checkout, and skips without them rather than asserting a
version it was not given:

    SEMANTIC_BENCH_ERPNEXT=~/ERPNext/toysam/apps/erpnext/erpnext \\
    SEMANTIC_BENCH_FRAPPE=~/ERPNext/toysam/apps/frappe/frappe \\
    python -m unittest nakhoda.tests.test_fixture -v
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from nakhoda.bench import fixture

FROZEN = Path("/tmp/semantic-bench/erp.duckdb")


def _available() -> bool:
	try:
		import duckdb

		del duckdb
	except ImportError:
		return False
	return True


@unittest.skipUnless(_available(), "needs duckdb")
class Fixture(unittest.TestCase):
	tmp: tempfile.TemporaryDirectory
	counts: dict[str, int]

	@classmethod
	def setUpClass(cls) -> None:
		import duckdb

		cls.tmp = tempfile.TemporaryDirectory()
		path = Path(cls.tmp.name) / "erp.duckdb"
		cls.counts = fixture.build(path)
		cls.con = duckdb.connect(str(path), read_only=True)

	@classmethod
	def tearDownClass(cls) -> None:
		cls.con.close()
		cls.tmp.cleanup()

	def rows(self, sql: str) -> list[tuple]:
		return self.con.execute(sql).fetchall()

	def one(self, sql: str):
		row = self.con.execute(sql).fetchone()
		self.assertIsNotNone(row, f"no row from: {sql}")
		return row[0]

	# -- the schema is the frozen one ------------------------------------
	def test_schema_matches_the_frozen_artifact(self):
		"""Same columns, same types, same order, for every shared DocType.

		This is the whole reason the builder was generalised rather than
		rewritten. A difference here means the 40-question and 200-question sets
		describe different databases.
		"""
		import duckdb

		if not FROZEN.exists():
			self.skipTest(f"no frozen artifact at {FROZEN}; run semantic_bench/build.py")
		version = fixture.erpnext_version()
		if version != fixture.PINNED_ERPNEXT:
			self.skipTest(
				f"erpnext {version}, artifact is {fixture.PINNED_ERPNEXT}; "
				"set SEMANTIC_BENCH_ERPNEXT to the pin"
			)

		frozen = duckdb.connect(str(FROZEN), read_only=True)
		try:
			shared = sorted(r[0] for r in frozen.execute("SHOW TABLES").fetchall())
			self.assertTrue(shared, "frozen artifact has no tables")
			for table in shared:
				with self.subTest(table):
					want = frozen.execute(f'DESCRIBE "{table}"').fetchall()
					got = self.con.execute(f'DESCRIBE "{table}"').fetchall()
					self.assertEqual(
						[(r[0], r[1]) for r in want],
						[(r[0], r[1]) for r in got],
						f"{table} disagrees with the artifact behind the published number",
					)
		finally:
			frozen.close()

	def test_layout_fieldtypes_never_become_columns(self):
		"""`Section Break` is not a column. A DocType is mostly layout, so a
		builder that forgot to filter would produce plausible-looking garbage
		that only a column count would catch."""
		meta = fixture.load("Sales Invoice")
		layout = {
			f["fieldname"]
			for f in meta["fields"]
			if f.get("fieldtype") in fixture.SKIP and f.get("fieldname")
		}
		self.assertTrue(layout, "Sales Invoice has no layout fields - wrong DocType JSON")
		named = {c for c, _ in fixture.columns(meta)}
		self.assertEqual(layout & named, set())

	def test_child_tables_carry_their_parent_link(self):
		"""Without `parent` a child row cannot be joined to anything, and the
		grain questions the set is built around are unanswerable."""
		for name in ("Sales Invoice Item", "Purchase Invoice Item", "Delivery Note Item"):
			with self.subTest(name):
				named = [c for c, _ in fixture.columns(fixture.load(name))]
				self.assertEqual(named[7:10], ["parent", "parentfield", "parenttype"])

	# -- determinism, and proof the seed is read -------------------------
	def test_same_seed_same_data(self):
		a, b = fixture.Rows(7), fixture.Rows(7)
		for stage in ("selling", "buying", "stock"):
			getattr(a, stage)()
			getattr(b, stage)()
		self.assertEqual(a.data, b.data)

	def test_a_different_seed_changes_the_data(self):
		"""Guards the test above. If the seed were ignored, equality would hold
		for free and the determinism claim would be worthless."""
		a, b = fixture.Rows(7), fixture.Rows(8)
		for stage in ("selling", "buying", "stock"):
			getattr(a, stage)()
			getattr(b, stage)()
		self.assertNotEqual(a.data, b.data)
		self.assertEqual(
			{k: len(v) for k, v in a.data.items()}.keys(),
			{k: len(v) for k, v in b.data.items()}.keys(),
		)

	# -- the modules are joined ------------------------------------------
	def test_every_module_has_rows(self):
		for module, names in fixture.MODULES.items():
			with self.subTest(module):
				for name in names:
					self.assertGreater(self.counts[name], 0, f"{name} is empty")

	def test_the_seams_between_modules_carry_rows(self):
		"""One query per seam. An empty result means a question written across
		that seam has an empty gold answer, which grades every wrong SQL as
		right."""
		seams = {
			"selling<->buying: an item bought and sold": """
				SELECT DISTINCT s.item_code FROM "tabSales Invoice Item" s
				JOIN "tabPurchase Invoice Item" p USING (item_code)
				WHERE s.docstatus = 1 AND p.docstatus = 1""",
			"selling<->buying: bought but never sold": """
				SELECT DISTINCT item_code FROM "tabPurchase Invoice Item"
				WHERE docstatus = 1 AND item_code NOT IN
				(SELECT item_code FROM "tabSales Invoice Item" WHERE docstatus = 1)""",
			"selling<->stock: an invoice with its delivery": """
				SELECT i.name FROM "tabSales Invoice" i
				JOIN "tabDelivery Note Item" d ON d.against_sales_invoice = i.name
				WHERE i.docstatus = 1""",
			"selling<->stock: invoiced, never delivered": """
				SELECT i.name FROM "tabSales Invoice" i WHERE i.docstatus = 1 AND i.is_return = 0
				AND NOT EXISTS (SELECT 1 FROM "tabDelivery Note Item" d
				WHERE d.against_sales_invoice = i.name)""",
			"buying<->stock: a receipt in the ledger": """
				SELECT l.name FROM "tabStock Ledger Entry" l
				JOIN "tabPurchase Invoice" p ON p.name = l.voucher_no
				WHERE l.voucher_type = 'Purchase Invoice'""",
			"buying<->stock: a PO not yet received": """
				SELECT name FROM "tabPurchase Order" WHERE docstatus = 1 AND per_received < 100""",
			"three modules: margin by item group": """
				SELECT s.item_group FROM "tabSales Invoice Item" s
				JOIN "tabPurchase Invoice Item" p USING (item_code)
				JOIN "tabStock Ledger Entry" l ON l.item_code = s.item_code
				WHERE s.docstatus = 1 AND p.docstatus = 1 GROUP BY 1""",
		}
		for label, sql in seams.items():
			with self.subTest(label):
				self.assertTrue(self.rows(sql), f"no rows across {label}")

	# -- the ledger agrees with the documents that produced it -----------
	def test_ledger_quantity_reconciles_with_its_vouchers(self):
		"""The ledger is derived, so it can be checked against its source. A
		question that cross-checks stock against invoices is only fair if the
		fixture itself reconciles."""
		received = self.one(
			"""SELECT round(sum(actual_qty), 2) FROM "tabStock Ledger Entry"
			WHERE voucher_type = 'Purchase Invoice'"""
		)
		invoiced = self.one(
			"""SELECT round(sum(qty), 2) FROM "tabPurchase Invoice Item" WHERE docstatus = 1"""
		)
		self.assertEqual(received, invoiced)

	def test_stock_value_follows_quantity_and_rate(self):
		"""`stock_value = qty_after_transaction * valuation_rate` on every row."""
		off = self.one(
			"""SELECT count(*) FROM "tabStock Ledger Entry"
			WHERE abs(stock_value - round(qty_after_transaction * valuation_rate, 2)) > 0.011"""
		)
		self.assertEqual(off, 0)

	def test_running_balance_matches_the_sum_of_its_moves(self):
		off = self.one(
			"""SELECT count(*) FROM (
				SELECT item_code, warehouse FROM "tabStock Ledger Entry" GROUP BY 1, 2
				HAVING abs(round(sum(actual_qty), 2)
					- max_by(qty_after_transaction, name)) > 0.011)"""
		)
		self.assertEqual(off, 0)

	def test_no_warehouse_issues_stock_it_never_received(self):
		"""Every warehouse that ships also receives. Splitting issues across
		warehouses that never took delivery gives one a large negative balance -
		not a hard question, a broken fixture."""
		shipped = {
			r[0]
			for r in self.rows(
				"""SELECT DISTINCT warehouse FROM "tabStock Ledger Entry" WHERE actual_qty < 0"""
			)
		}
		received = {
			r[0]
			for r in self.rows(
				"""SELECT DISTINCT warehouse FROM "tabStock Ledger Entry" WHERE actual_qty > 0"""
			)
		}
		self.assertTrue(shipped)
		self.assertEqual(shipped - received, set())

	def test_some_warehouses_hold_nothing(self):
		""" "Which warehouses are empty" is a question a real site can ask, and an
		empty gold answer would grade any wrong query as right."""
		empty = self.rows(
			"""SELECT name FROM "tabWarehouse" w WHERE w.is_group = 0 AND NOT EXISTS
			(SELECT 1 FROM "tabStock Ledger Entry" s WHERE s.warehouse = w.name)"""
		)
		self.assertTrue(empty)

	# -- the shapes a question needs -------------------------------------
	def test_the_document_states_a_question_can_filter_on_all_occur(self):
		"""Draft, submitted, cancelled and returned all present, in both the
		selling and the buying module. `docstatus` is the single most common
		trap in the question set; a fixture where every row is submitted cannot
		catch a model that ignores it."""
		for table in ("Sales Invoice", "Purchase Invoice"):
			with self.subTest(table):
				states = {r[0] for r in self.rows(f'SELECT DISTINCT docstatus FROM "tab{table}"')}
				self.assertEqual(states, {0, 1, 2})
				returns = self.one(f'SELECT count(*) FROM "tab{table}" WHERE is_return = 1 AND docstatus = 1')
				self.assertGreater(returns, 0)

	def test_money_is_in_more_than_one_currency(self):
		"""`base_grand_total` and `grand_total` differ only when a document is
		not in company currency, and telling them apart is a graded distinction."""
		for table in ("Sales Invoice", "Purchase Invoice"):
			with self.subTest(table):
				currencies = {r[0] for r in self.rows(f'SELECT DISTINCT currency FROM "tab{table}"')}
				self.assertGreater(len(currencies), 1)
				differing = self.one(
					f"""SELECT count(*) FROM "tab{table}"
					WHERE docstatus = 1 AND abs(grand_total - base_grand_total) > 0.01"""
				)
				self.assertGreater(differing, 0)


if __name__ == "__main__":
	unittest.main()
