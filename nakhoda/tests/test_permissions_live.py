"""Gate B on a real site: the half `test_permissions.py` deliberately cannot check.

The offline gate drives the boundary from a `RecordedPolicy` - answers captured
from a live site and replayed. That buys determinism, and it buys it by assuming
`FrappePolicy` really returns answers of that shape. This suite is where the
assumption is paid for.

Read-only. Nothing here writes, and that is a standing requirement rather than a
convenience: an earlier test in this app inserted a `Custom Field` to manufacture
a case, `ALTER TABLE` commits implicitly, the rollback in `tearDown` did nothing,
and the column outlived the run on a real site. The rule that came out of it is
the rule here - a live test asserts against whatever the site happens to be, or
it does not run.

The load-bearing test is `test_every_live_fragment_translates`. The grammar in
`engine/permissions.py` is closed, so it can only stay correct for as long as it
still covers what Frappe emits. If a Frappe upgrade adds a construct, this fails
here - loudly, on a site - instead of silently removing rows from users who were
entitled to them.
"""

from __future__ import annotations

import unittest

import frappe

from nakhoda.connectors import site_db
from nakhoda.engine import permissions
from nakhoda.engine.operations import compile_pipeline

#: Sampled rather than exhaustive: enough doctypes to hit link-based User
#: Permissions, owner constraints and child tables, few enough to stay quick.
DOCTYPES = [
	"Sales Invoice",
	"Sales Invoice Item",
	"Customer",
	"Item",
	"Employee",
	"Payment Entry",
	"ToDo",
]


def connected() -> bool:
	return bool(getattr(frappe, "db", None))


@unittest.skipUnless(connected(), "needs a site: bench --site <site> run-tests --app nakhoda")
class LivePermissions(unittest.TestCase):
	@classmethod
	def setUpClass(cls) -> None:
		cls.users = ["Administrator", *frappe.get_all("User", filters={"enabled": 1}, pluck="name", limit=8)]
		cls.doctypes = [d for d in DOCTYPES if frappe.db.exists("DocType", d)]
		cls.connector = site_db()

	def test_every_live_fragment_translates(self):
		"""Whatever this site's permissions compile to, the engine can read it.

		A refusal is safe but lossy, so this is the drift alarm: it fails when
		Frappe starts emitting SQL the closed grammar does not model.
		"""
		checked = 0
		refused = []
		for doctype in self.doctypes:
			table = self.connector.resolve(permissions.table_name(doctype))
			for user in self.users:
				allowed, fragment = permissions.FrappePolicy(user).rows(doctype)
				self.assertIsInstance(allowed, bool)
				if not allowed or fragment is None:
					continue
				checked += 1
				if permissions.row_filter(fragment, table, permissions.table_name(doctype)) is None:
					refused.append((user, doctype, fragment))
		self.assertEqual(refused, [], f"the grammar refused {len(refused)} live fragment(s)")
		if not checked:
			self.skipTest("this site has no restricting User Permissions to translate")

	def test_no_access_is_an_answer_not_an_exception(self):
		"""Frappe raising `PermissionError` must arrive as `(False, None)`.

		Letting the exception escape would turn a denied user into a 500 for the
		whole analysis; swallowing it into "unrestricted" is #919.
		"""
		observed = set()
		for doctype in self.doctypes:
			for user in self.users:
				allowed, fragment = permissions.FrappePolicy(user).rows(doctype)
				observed.add(allowed)
				if not allowed:
					self.assertIsNone(fragment, "a denial must not also carry a filter")
		self.assertIn(True, observed, "no user could read anything - the sample is wrong")

	def test_administrator_is_unrestricted_and_readable(self):
		"""The one permission answer every ERPNext site agrees on."""
		policy = permissions.FrappePolicy("Administrator")
		for doctype in self.doctypes:
			with self.subTest(doctype):
				self.assertEqual(policy.rows(doctype), (True, None))
				columns = policy.columns(doctype)
				assert columns is not None, "FrappePolicy always answers with a set"
				self.assertIn("name", columns, "`name` must survive projection or joins break")

	def test_child_tables_name_their_parents(self):
		"""The grain wiring the offline gate stubs, against real metadata."""
		if "Sales Invoice Item" not in self.doctypes:
			self.skipTest("no Sales Invoice Item on this site")
		policy = permissions.FrappePolicy("Administrator")
		self.assertTrue(policy.is_child("Sales Invoice Item"))
		self.assertIn("Sales Invoice", policy.parents("Sales Invoice Item"))
		self.assertFalse(policy.is_child("Sales Invoice"))

	def test_a_child_table_admits_more_than_the_framework_columns(self):
		"""The regression that shipped: 168 columns arrived as 7.

		Frappe returns *no* permitted fields for a child DocType asked about
		without a `parenttype` (`model/meta.py:698-699`) and then withholds
		`parent`/`parenttype` with them (`model/__init__.py:254-258`). Projected
		with that answer, every line-item table lost both its business columns and
		the keys the parent-row rule joins on, so a question about what was sold
		could not be compiled at all - it reached the browser as the model naming
		a column "not in scope".

		Naming `item_code` would tie this to ERPNext's field list. What must hold
		is structural: a child admits something the framework did not put there,
		and it admits the two keys the grain rule needs.
		"""
		if "Sales Invoice Item" not in self.doctypes:
			self.skipTest("no Sales Invoice Item on this site")
		from frappe.model import default_fields, optional_fields

		columns = permissions.FrappePolicy("Administrator").columns("Sales Invoice Item")
		assert columns is not None, "FrappePolicy always answers with a set"
		framework = set(default_fields) | set(optional_fields) | {"parent", "parentfield", "parenttype"}
		self.assertTrue(
			columns - framework,
			"a child admitting only framework columns cannot answer a question about line items",
		)
		for key in ("parent", "parenttype"):
			self.assertIn(key, columns, "the parent-row rule joins on this")

	def test_a_denied_user_reads_nothing_through_the_engine(self):
		"""End to end, on the site's own database, through the real compiler.

		The offline gate proves this against DuckDB. Here the same pipeline runs
		against MariaDB, which is the backend that actually serves a user.
		"""
		denied = next(
			((u, d) for d in self.doctypes for u in self.users if not permissions.FrappePolicy(u).rows(d)[0]),
			None,
		)
		if denied is None:
			self.skipTest("every sampled user can read every sampled doctype")
		user, doctype = denied

		pipeline = [
			{"type": "source", "table": permissions.table_name(doctype)},
			{"type": "summarize", "measures": [{"name": "n", "expr": {"fn": "count", "args": []}}]},
		]
		resolver = permissions.for_user(self.connector.resolve, user)
		got = int(self.connector.execute(compile_pipeline(pipeline, resolver)).iloc[0]["n"])
		self.assertEqual(got, 0, f"{user} read {got} rows of {doctype} they may not read")

		unrestricted = permissions.for_user(self.connector.resolve, "Administrator")
		total = int(self.connector.execute(compile_pipeline(pipeline, unrestricted)).iloc[0]["n"])
		self.assertGreater(total, 0, "the zero above means nothing if the table is empty")


if __name__ == "__main__":
	unittest.main()
