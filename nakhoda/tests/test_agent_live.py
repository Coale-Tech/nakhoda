# Copyright (c) 2026, Nakhoda and contributors
# For license information, please see license.txt
"""Live end-to-end proof for the ask -> SQL -> result round-trip.

`test_agent.py` proves the tier ladder, chart wiring, and audit logging by
mocking `route`/`providers.complete`/`build_index` - it never actually
touches a model provider or lets a real question resolve through the real
semantic index. This module is the live counterpart, split into two tiers:

1. The deterministic path (`api.run` -> `engine.pipeline.run` -> the real
   `jkm` site's MariaDB connector) is exercised unconditionally: no model
   provider is required to prove operations compile to SQL and execute
   against real data, because that half of the pipeline has no AI in it.

2. The full chat round-trip (`manager.ask` with a real model call) only runs
   `unittest.skipUnless` a model provider is actually reachable in this
   environment. That question has one answer and it is
   `providers.configured()` - the same helper the settings page's "Active"
   badge calls, so a skip here and a grey badge there can never disagree.
   As of this session no provider is configured on this bench, so that test
   is expected to skip, not fail; skipping is the honest report of
   environment capability, not a stand-in for a passing assertion this
   environment cannot make.
"""

from __future__ import annotations

import unittest

import frappe

from nakhoda import api
from nakhoda.agent import manager, providers


def connected() -> bool:
	return bool(getattr(frappe, "db", None))


def live_provider_configured() -> bool:
	try:
		return providers.configured()
	except Exception:
		return False


@unittest.skipUnless(connected(), "needs a site: bench --site <site> run-tests --app nakhoda")
class DeterministicRunLive(unittest.TestCase):
	"""Proves `api.run()` executes real SQL against the real `jkm` site DB.

	No model provider involved - `operations` is hand-built, exactly the
	shape a model would have produced. This is the half of the chat
	round-trip that has no AI in it, and it is provable in every
	environment regardless of whether a model provider is configured.
	"""

	def test_run_executes_against_real_site_database(self):
		operations = [
			{"type": "source", "table": "tabSales Invoice"},
			{"type": "summarize", "measures": [{"name": "n", "expr": {"fn": "count", "args": []}}]},
		]
		frappe.set_user("Administrator")
		result = api.run(frappe.as_json(operations))
		self.assertIn("columns", result)
		self.assertIn("rows", result)
		self.assertIn("sql", result)
		self.assertIsNone(result.get("error"))
		self.assertGreaterEqual(result["row_count"], 0)
		self.assertEqual(result["columns"], ["n"])
		# One row: the whole-table count. Proves the SQL actually ran, not
		# just compiled - a broken connector would raise, not return one row.
		self.assertEqual(len(result["rows"]), 1)


@unittest.skipUnless(connected(), "needs a site: bench --site <site> run-tests --app nakhoda")
@unittest.skipUnless(
	live_provider_configured(),
	"no live model provider configured in this environment "
	"(AI disabled, or the selected provider's key is unset in both "
	"Nakhoda Settings and NAKHODA_AGENT_API_KEY) - the deterministic-path "
	"test above still proves the non-AI half of the pipeline",
)
class ChatRoundTripLive(unittest.TestCase):
	"""Full chat -> model -> SQL -> result round-trip against a real provider.

	Only runs when this environment actually has a reachable model; skips
	honestly otherwise rather than mocking a provider and calling that
	"live".
	"""

	def test_ask_returns_real_sql_result_for_a_real_question(self):
		frappe.set_user("Administrator")
		result = manager.ask("How many Sales Invoices are there?")
		self.assertIsNone(result.get("error"), result.get("error"))
		self.assertIn("sql", result)
		self.assertIn("rows", result)
		self.assertIn("agent_run", result)


if __name__ == "__main__":
	unittest.main()
