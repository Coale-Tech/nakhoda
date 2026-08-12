"""Phase 0, Gate B: the permission boundary, proved without a live site.

The gate the build plan sets is three properties, not one: a user with no read
access gets **zero rows, not an error and not everything**; two users with
different User Permissions get **different, correct** numbers from the same
aggregate; and child tables are filtered at **their parent's grain**. None of
those can be demonstrated against whatever permissions a development site
happens to carry this week, so the policy is a seam and these tests drive it
from recorded answers.

Two kinds of evidence appear here, and they are kept apart on purpose.

`RECORDED` holds permission SQL captured verbatim from a live ERPNext site
(`jkm`, 2026-08-12, five users across five DocTypes). Nothing in it is edited.
It is the reason the fragment grammar has the shape it has, and
`test_recorded_fragments_all_translate` is what stops the grammar drifting away
from what Frappe emits.

The fixture tests use the same *shape* instantiated on `territory`, because the
generated fixture has one company and one owner and so cannot tell two users
apart on the columns the recording used. `territory` is a Link field on Sales
Invoice exactly as `company` is, and Frappe's User Permission fragment for a
Link field is structural - the fieldname is the only thing that varies. That
substitution is the one liberty taken, and it is taken in the open.
"""

from __future__ import annotations

import unittest
from pathlib import Path

import ibis

from nakhoda.engine import cache, permissions
from nakhoda.engine.operations import compile_pipeline

FIXTURE = Path("/tmp/semantic-bench/erp.duckdb")

INVOICES = "tabSales Invoice"
ITEMS = "tabSales Invoice Item"

#: Verbatim from `DatabaseQuery(doctype, user=u).build_match_conditions()` on the
#: `jkm` site, 2026-08-12. Recorded, not written.
RECORDED: dict[str, str] = {
	"company only": (
		"(((ifnull(`tabSales Invoice`.`company`, '')='' "
		"or `tabSales Invoice`.`company` in ('JKM Chemtrade'))))"
	),
	"owner or shared names": (
		"((((`tabCustomer`.`owner` = 'chem@jkmchemtrade.com'))) "
		"or (`tabCustomer`.name in ('CS00950', 'CS00567', 'CS00565', 'CS00977')))"
	),
	"two user permissions anded": (
		"(((ifnull(`tabEmployee`.`company`, '')='' "
		"or `tabEmployee`.`company` in ('JKM Chemtrade')) "
		"and (ifnull(`tabEmployee`.`name`, '')='' "
		"or `tabEmployee`.`name` in ('HR-EMP-00024'))))"
	),
	"custom field plus share": (
		"(((((ifnull(`tabSales Invoice`.`company`, '')='' "
		"or `tabSales Invoice`.`company` in ('JKM Chemtrade')) "
		"and (ifnull(`tabSales Invoice`.`custom_sales_person`, '')='' "
		"or `tabSales Invoice`.`custom_sales_person` in ('domestic@jkmchemtrade.com'))))) "
		"or (`tabSales Invoice`.name in ('SI2627621')))"
	),
}

#: The columns the recorded fragments reference, so they can be translated
#: against a schema instead of against the fixture.
RECORDED_SCHEMA = {
	"tabSales Invoice": {
		"name": "string",
		"company": "string",
		"custom_sales_person": "string",
	},
	"tabCustomer": {"name": "string", "owner": "string"},
	"tabEmployee": {"name": "string", "company": "string"},
}


def territory_fragment(*allowed: str) -> str:
	"""Frappe's User Permission fragment for a Link field, on `territory`.

	The shape is copied from `RECORDED["company only"]` character for character;
	only the fieldname and the permitted values differ.
	"""
	values = ", ".join(f"'{v}'" for v in allowed)
	return (
		f"(((ifnull(`{INVOICES}`.`territory`, '')='' "
		f"or `{INVOICES}`.`territory` in ({values}))))"
	)


class RecordedPolicy:
	"""A policy that replays answers instead of asking a site for them."""

	def __init__(
		self,
		rows: dict[str, tuple[bool, str | None]] | None = None,
		*,
		columns: dict[str, set[str]] | None = None,
		parents: dict[str, list[str]] | None = None,
		children: frozenset[str] = frozenset(),
	) -> None:
		self._rows = rows or {}
		self._columns = columns or {}
		self._parents = parents or {}
		self._children = children

	def columns(self, doctype: str) -> set[str] | None:
		return self._columns.get(doctype)

	def rows(self, doctype: str) -> tuple[bool, str | None]:
		return self._rows.get(doctype, (True, None))

	def parents(self, child_doctype: str) -> list[str]:
		return self._parents.get(child_doctype, [])

	def is_child(self, doctype: str) -> bool:
		return doctype in self._children


@unittest.skipUnless(FIXTURE.exists(), f"needs the benchmark fixture at {FIXTURE}")
class GateB(unittest.TestCase):
	"""The permission boundary, against the same DuckDB the engine gate uses."""

	@classmethod
	def setUpClass(cls) -> None:
		cls.con = ibis.duckdb.connect(str(FIXTURE), read_only=True)
		cls.resolve = cls.con.table
		cls.raw = cls.con.raw_sql

	def sql_scalar(self, query: str):
		"""An expected value, computed by SQL that never touches the engine."""
		return self.con.raw_sql(query).fetchone()[0]

	def total_for(self, policy: permissions.Policy) -> float:
		"""The one aggregate every row test uses, run through the real compiler."""
		resolver = permissions.permitted_resolver(self.resolve, policy)
		expr = compile_pipeline(
			[
				{"type": "source", "table": INVOICES},
				{
					"type": "summarize",
					"measures": [{"name": "total", "expr": {"fn": "sum", "args": [{"col": "base_grand_total"}]}}],
				},
			],
			resolver,
		)
		value = self.con.execute(expr).iloc[0]["total"]
		return float(value) if value is not None else 0.0

	# -- the grammar --------------------------------------------------------

	def test_recorded_fragments_all_translate(self):
		"""Every fragment a real site produced is one the engine can read.

		If this fails the grammar has drifted from Frappe, and the failure mode
		is silent over-restriction: users lose rows they are entitled to.
		"""
		for label, fragment in RECORDED.items():
			with self.subTest(label):
				table_name = "tabSales Invoice" if "Sales Invoice" in fragment else None
				table_name = table_name or ("tabCustomer" if "tabCustomer" in fragment else "tabEmployee")
				table = ibis.table(RECORDED_SCHEMA[table_name], name=table_name)
				predicate = permissions.row_filter(fragment, table, table_name)
				self.assertIsNotNone(predicate, f"refused a fragment Frappe really emitted: {fragment}")

	def test_unmodelled_sql_is_refused(self):
		"""Anything outside the grammar yields no filter, and callers make that empty."""
		table = self.resolve(INVOICES)
		refusals = {
			"subquery": f"`{INVOICES}`.`name` in (select name from `tabCustomer`)",
			"unknown function": f"weekday(`{INVOICES}`.`posting_date`) = 1",
			"foreign qualifier": "`tabOther`.`territory` = 'Germany'",
			"absent column": f"`{INVOICES}`.`not_a_column` = 'x'",
			"not a predicate": f"`{INVOICES}`.`territory`",
			"malformed": "((( and",
		}
		for label, fragment in refusals.items():
			with self.subTest(label):
				self.assertIsNone(permissions.row_filter(fragment, table, INVOICES))

	# -- the three properties the gate names --------------------------------

	def test_denied_user_gets_zero_rows_not_every_row(self):
		"""No read access is an answer, and the answer is nothing.

		Both halves matter. Zero proves it did not fail open; a non-zero
		unrestricted total proves the zero means something.
		"""
		denied = self.total_for(RecordedPolicy({"Sales Invoice": (False, None)}))
		unrestricted = self.total_for(RecordedPolicy())
		self.assertEqual(denied, 0.0)
		self.assertGreater(unrestricted, 0.0)

	def test_unreadable_filter_fails_closed(self):
		"""A permission query we cannot parse is a denial, never a pass-through."""
		opaque = RecordedPolicy(
			{"Sales Invoice": (True, f"`{INVOICES}`.`name` in (select name from `tabCustomer`)")}
		)
		self.assertEqual(self.total_for(opaque), 0.0)

	def test_two_users_diverge_and_both_are_right(self):
		"""The gate, in one test: same aggregate, different permissions, correct numbers."""
		germany = self.total_for(RecordedPolicy({"Sales Invoice": (True, territory_fragment("Germany"))}))
		texas = self.total_for(RecordedPolicy({"Sales Invoice": (True, territory_fragment("Texas"))}))

		expect = "SELECT sum(base_grand_total) FROM \"{t}\" WHERE ifnull(territory,'')='' OR territory IN ({v})"
		self.assertAlmostEqual(germany, float(self.sql_scalar(expect.format(t=INVOICES, v="'Germany'"))), places=4)
		self.assertAlmostEqual(texas, float(self.sql_scalar(expect.format(t=INVOICES, v="'Texas'"))), places=4)

		self.assertNotAlmostEqual(germany, texas, places=2)
		unrestricted = self.total_for(RecordedPolicy())
		self.assertLess(germany, unrestricted)
		self.assertLess(texas, unrestricted)

	def test_columns_the_user_cannot_read_leave_the_table(self):
		"""A permlevel-restricted column is not in scope, so a pipeline cannot name it."""
		policy = RecordedPolicy(columns={"Sales Invoice": {"name", "territory", "base_grand_total"}})
		resolver = permissions.permitted_resolver(self.resolve, policy)
		table = resolver(INVOICES)
		self.assertEqual(set(table.columns), {"name", "territory", "base_grand_total"})
		self.assertNotIn("customer", table.columns)

	def test_child_rows_follow_their_parent(self):
		"""Child grain: an item is readable exactly when its invoice is."""
		policy = RecordedPolicy(
			{"Sales Invoice": (True, territory_fragment("Germany"))},
			parents={"Sales Invoice Item": ["Sales Invoice"]},
			children=frozenset({"Sales Invoice Item"}),
		)
		resolver = permissions.permitted_resolver(self.resolve, policy)
		expr = compile_pipeline(
			[
				{"type": "source", "table": ITEMS},
				{"type": "summarize", "measures": [{"name": "n", "expr": {"fn": "count", "args": []}}]},
			],
			resolver,
		)
		got = int(self.con.execute(expr).iloc[0]["n"])

		expected = int(
			self.sql_scalar(
				f'SELECT count(*) FROM "{ITEMS}" i JOIN "{INVOICES}" s ON i.parent = s.name '
				f"AND i.parenttype = 'Sales Invoice' "
				f"WHERE ifnull(s.territory,'')='' OR s.territory IN ('Germany')"
			)
		)
		self.assertEqual(got, expected)
		self.assertGreater(expected, 0, "the fixture must have German invoice lines for this to mean anything")

		total = int(self.sql_scalar(f'SELECT count(*) FROM "{ITEMS}"'))
		self.assertLess(got, total)

	def test_child_with_no_readable_parent_is_empty(self):
		"""Denial propagates down the grain, not just across it."""
		policy = RecordedPolicy(
			{"Sales Invoice": (False, None)},
			parents={"Sales Invoice Item": ["Sales Invoice"]},
			children=frozenset({"Sales Invoice Item"}),
		)
		resolver = permissions.permitted_resolver(self.resolve, policy)
		expr = compile_pipeline(
			[
				{"type": "source", "table": ITEMS},
				{"type": "summarize", "measures": [{"name": "n", "expr": {"fn": "count", "args": []}}]},
			],
			resolver,
		)
		self.assertEqual(int(self.con.execute(expr).iloc[0]["n"]), 0)

	# -- the property the cache inherits ------------------------------------

	def test_permissions_reach_the_compiled_sql(self):
		"""The filter is in the SQL, not applied to the rows afterwards.

		This is what makes a cache keyed on compiled SQL safe, and it is the
		difference between this design and `insights/api/ml/utils.py:cached_run`,
		where one key served every user who passed a coarse permission check.
		"""
		germany = permissions.permitted_resolver(
			self.resolve, RecordedPolicy({"Sales Invoice": (True, territory_fragment("Germany"))})
		)
		texas = permissions.permitted_resolver(
			self.resolve, RecordedPolicy({"Sales Invoice": (True, territory_fragment("Texas"))})
		)
		pipeline = [
			{"type": "source", "table": INVOICES},
			{"type": "summarize", "measures": [{"name": "total", "expr": {"fn": "sum", "args": [{"col": "base_grand_total"}]}}]},
		]
		sql_g = str(ibis.to_sql(compile_pipeline(pipeline, germany), dialect="duckdb"))
		sql_t = str(ibis.to_sql(compile_pipeline(pipeline, texas), dialect="duckdb"))

		self.assertIn("Germany", sql_g)
		self.assertIn("Texas", sql_t)
		self.assertNotEqual(
			cache.key(sql_g, "duckdb:fixture"),
			cache.key(sql_t, "duckdb:fixture"),
			"two users' queries must not share a cache entry",
		)
		self.assertEqual(cache.key(sql_g, "duckdb:fixture"), cache.key(sql_g, "duckdb:fixture"))
		self.assertNotEqual(
			cache.key(sql_g, "duckdb:fixture"),
			cache.key(sql_g, "site:other"),
			"the same SQL against different data must not share a cache entry",
		)


if __name__ == "__main__":
	unittest.main()
