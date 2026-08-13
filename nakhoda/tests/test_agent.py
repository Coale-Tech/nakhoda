"""Phase 4's second gate: every `Nakhoda Agent Run` row records the tier used
and the structural reason it was chosen, and no row shows an escalation
without a preceding validation failure (`12-build-plan.md` Phase 4).

Against a real site, because `manager.ask()` writes real `Nakhoda Agent Run`
documents and resolves a real default data source - but with `route()` and
`providers.complete()` replaced, so the routing decision and the model's
answer are fixed by the test instead of by the semantic index or a paid API
call. `test_router.py` already grades `route()` itself, offline; this file
grades what `ask()` does with whatever `route()` returns.

Writes are records, never schema; everything rolls back.
"""

from __future__ import annotations

import json
import os
import unittest
from unittest import mock

import frappe

from nakhoda import api
from nakhoda.agent import manager, providers
from nakhoda.agent.router import Route
from nakhoda.agent.tiers import Tier

VALID_OPS = json.dumps(
	[
		{"type": "source", "table": "tabSales Invoice"},
		{"type": "summarize", "measures": [{"name": "n", "expr": {"fn": "count", "args": []}}]},
	]
)

#: A route the tests hand `ask()` directly, so this file never depends on what
#: the real semantic index selects for a question on this site.
SINGLE_TABLE = Route(Tier.FAST, "single table, no join", ("Sales Invoice",))


def connected() -> bool:
	return bool(getattr(frappe, "db", None))


@unittest.skipUnless(connected(), "needs a site: bench --site <site> run-tests --app nakhoda")
class Agent(unittest.TestCase):
	def setUp(self) -> None:
		frappe.set_user("Administrator")
		self._env = mock.patch.dict(
			os.environ,
			{"NAKHODA_AGENT_MODEL_FAST": "fast-1", "NAKHODA_AGENT_MODEL_BALANCED": "bal-1"},
		)
		self._env.start()
		self._route = mock.patch("nakhoda.agent.manager.route", return_value=SINGLE_TABLE)
		self._route.start()
		self._index = mock.patch("nakhoda.agent.manager.build_index", return_value=None)
		self._index.start()

	def tearDown(self) -> None:
		self._index.stop()
		self._route.stop()
		self._env.stop()
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def run_for(self, run_name: str) -> frappe._dict:
		return frappe.get_doc("Nakhoda Agent Run", run_name).as_dict()

	# -- verified queries answer for free, before any model is asked --------

	def test_a_matched_verified_query_never_calls_a_model(self):
		question = "How many invoices, verified style, are there?"
		doc = frappe.get_doc(
			{
				"doctype": "Nakhoda Verified Query",
				"title": "Invoice count (agent test)",
				"question": question,
				"data_source": api.default_source(),
				"operations": frappe.as_json(
					[
						{"type": "source", "table": "tabSales Invoice"},
						{
							"type": "summarize",
							"measures": [{"name": "n", "expr": {"fn": "count", "args": []}}],
						},
					]
				),
			}
		).insert()
		doc.submit()
		doc.reload()

		with mock.patch.object(providers, "complete") as complete:
			result = manager.ask(question.upper() + "  ")  # case/whitespace-insensitive match

		complete.assert_not_called()
		self.assertNotIn("error", result)
		run = self.run_for(result["agent_run"])
		self.assertEqual(run.source, "verified")
		self.assertEqual(run.matched_verified_query, doc.name)
		self.assertEqual(run.status, "ok")

	# -- generated answers: tier and reason are always on the row -----------

	def test_a_first_try_success_records_its_tier_and_reason_unescalated(self):
		with mock.patch.object(providers, "complete", return_value=VALID_OPS) as complete:
			result = manager.ask("how many invoices are there")

		self.assertEqual(complete.call_count, 1)
		self.assertNotIn("error", result)
		run = self.run_for(result["agent_run"])
		self.assertEqual(run.status, "ok")
		self.assertEqual(run.source, "generated")
		self.assertEqual(run.tier, Tier.FAST.value)
		self.assertEqual(run.tier_reason, SINGLE_TABLE.reason)
		self.assertEqual(run.model, "fast-1")
		self.assertFalse(run.escalated)
		self.assertFalse(run.degraded)

	def test_a_validation_failure_escalates_and_the_row_says_why(self):
		"""§Phase 4 gate: no row shows an escalation without a preceding
		validation failure - here there always is one, and the row must
		name it."""
		with mock.patch.object(
			providers, "complete", side_effect=["not a pipeline at all", VALID_OPS]
		) as complete:
			result = manager.ask("how many invoices are there")

		self.assertEqual(complete.call_count, 2)
		self.assertNotIn("error", result)
		run = self.run_for(result["agent_run"])
		self.assertEqual(run.tier, Tier.BALANCED.value)
		self.assertEqual(run.model, "bal-1")
		self.assertTrue(run.escalated)
		self.assertTrue(run.escalation_reason)
		self.assertFalse(run.degraded)

	def test_unavailability_moves_tiers_without_being_recorded_as_escalation(self):
		"""A tier change caused by an outage is `degraded`, not `escalated` -
		the row must not claim a validation failure that never happened."""
		with mock.patch.object(
			providers, "complete", side_effect=[providers.ModelError("no route to host"), VALID_OPS]
		) as complete:
			result = manager.ask("how many invoices are there")

		self.assertEqual(complete.call_count, 2)
		run = self.run_for(result["agent_run"])
		self.assertEqual(run.tier, Tier.BALANCED.value)
		self.assertTrue(run.degraded)
		self.assertFalse(run.escalated)

	def test_three_consecutive_rate_limits_open_the_circuit_and_stop(self):
		with mock.patch.dict(os.environ, {"NAKHODA_AGENT_MODEL_FAST": "f1,f2,f3"}):
			with mock.patch.object(
				providers,
				"complete",
				side_effect=[providers.RateLimited("x")] * 3,
			) as complete:
				result = manager.ask("how many invoices are there")

		self.assertEqual(complete.call_count, 3)
		self.assertIn("rate limited repeatedly", result["error"])
		run = self.run_for(result["agent_run"])
		self.assertEqual(run.status, "error")
		self.assertEqual(run.tier, Tier.FAST.value)
		self.assertEqual(run.tier_reason, SINGLE_TABLE.reason)

	def test_no_model_available_anywhere_is_a_plain_error_not_a_crash(self):
		with mock.patch.dict(
			os.environ, {"NAKHODA_AGENT_MODEL_FAST": "", "NAKHODA_AGENT_MODEL_BALANCED": ""}
		):
			result = manager.ask("how many invoices are there")

		self.assertIn("error", result)
		run = self.run_for(result["agent_run"])
		self.assertEqual(run.status, "error")


if __name__ == "__main__":
	unittest.main()
