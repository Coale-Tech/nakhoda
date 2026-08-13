"""Phase 4's router: structure decides the tier, never a keyword.

Pure - `Index` reads anything that answers `.get()` like a Frappe document
(`nakhoda.semantic.retrieval.Index`, `nakhoda.semantic.model.describe`), so
this grades the router against tiny synthetic DocTypes, no site and no model.
That is the property `12-build-plan.md` Phase 4 asks for: the router is
deterministic, so it can be tested like one.
"""

from __future__ import annotations

import unittest

from nakhoda.agent.router import escalate, route
from nakhoda.agent.tiers import LADDER, Tier
from nakhoda.semantic.retrieval import Index

#: A master with no children and nothing in common with the other two.
WIDGET = {"name": "Widget", "fields": [{"fieldname": "widget_name", "fieldtype": "Data"}]}

#: A second master, with a child table named so its own vocabulary ("basket")
#: overlaps its child's, and the child's own word ("line") does not exist
#: anywhere else - the property the child-alone test below depends on.
BASKET = {
	"name": "Basket",
	"fields": [
		{"fieldname": "customer", "fieldtype": "Link", "options": "Customer"},
		{"fieldname": "lines", "fieldtype": "Table", "options": "Basket Line"},
	],
}
BASKET_LINE = {
	"name": "Basket Line",
	"istable": 1,
	"fields": [{"fieldname": "qty", "fieldtype": "Float"}],
}


def index() -> Index:
	return Index([WIDGET, BASKET, BASKET_LINE])


class Router(unittest.TestCase):
	def test_no_table_matched_routes_fast(self):
		r = route("what is the meaning of life", index())
		self.assertEqual(r.tier, Tier.FAST)
		self.assertEqual(r.tables, ())

	def test_single_master_no_join_routes_fast(self):
		r = route("how many widgets are there", index())
		self.assertEqual(r.tier, Tier.FAST)
		self.assertEqual(r.tables, ("Widget",))
		self.assertIn("single table", r.reason)

	def test_two_masters_route_balanced(self):
		r = route("widgets in baskets", index())
		self.assertEqual(r.tier, Tier.BALANCED)
		self.assertGreaterEqual(len(r.tables), 2)

	def test_child_alone_pulls_in_its_parent_and_routes_balanced(self):
		r = route("how many lines are there", index())
		self.assertEqual(r.tier, Tier.BALANCED)
		self.assertIn("Basket Line", r.tables)
		self.assertIn("Basket", r.tables)  # requires() adds the parent
		self.assertIn("join", r.reason)

	def test_structural_router_never_starts_at_premium(self):
		"""`PREMIUM` is earned only by `escalate()`, never a first pick - the
		gate that disables `PREMIUM` entirely and still requires >=95% depends
		on this (`12-build-plan.md` Phase 4)."""
		for question in (
			"how many widgets",
			"widgets in baskets",
			"how many lines",
			"widgets baskets lines customers",
			"nonsense that matches nothing at all",
		):
			r = route(question, index())
			self.assertNotEqual(r.tier, Tier.PREMIUM)


class EscalationLadder(unittest.TestCase):
	def test_ladder_order(self):
		self.assertEqual(LADDER, (Tier.FAST, Tier.BALANCED, Tier.PREMIUM))

	def test_escalates_one_step_at_a_time(self):
		self.assertEqual(escalate(Tier.FAST), Tier.BALANCED)
		self.assertEqual(escalate(Tier.BALANCED), Tier.PREMIUM)

	def test_premium_is_the_ceiling(self):
		self.assertIsNone(escalate(Tier.PREMIUM))


if __name__ == "__main__":
	unittest.main()
