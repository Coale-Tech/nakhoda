# Copyright (c) 2026, Nakhoda and contributors
# For license information, please see license.txt
"""The agentic-dashboard gates, against a real site.

`docs/plan/16-agentic-dashboards.md` §7 lists eight. Six are here; the other
two are not Python:

* **gate 2** (the measured `ask` path is untouched) is a `git diff` plus a
  `semantic_bench` re-grade - a claim about a diff, which a test cannot make
  about itself;
* **gate 7** (bar geometry) is `frontend/tests/chart-geometry.spec.js`, which
  measures rendered DOM in a browser.

Four of the six are proven with the model call stubbed, and that is
deliberate: a *bound* (the loop stops), a *refusal* (the loop applies
nothing), an *audit link* (every query names its turn) and a *prompt* (the
dashboard's skill reaches the model) are properties of this app's own code,
and asserting them through a live model would make them depend on a sentence
a provider chose. The live loop is exercised too, `skipUnless` a provider is
reachable - the same `providers.configured()` gate `test_agent_live.py` uses,
for the same reason.

Writes are records, never schema; everything inserted here rolls back.
"""

from __future__ import annotations

import json
import unittest
from contextlib import ExitStack, contextmanager
from unittest import mock

import frappe

from nakhoda.agent import providers, thread
from nakhoda.api import dashboards as dashboards_api
from nakhoda.api import default_source

DASHBOARD_DOCTYPE = "Nakhoda Intelligence Template"
VERSION_DOCTYPE = "Nakhoda Dashboard Version"
TURN_DOCTYPE = "Nakhoda Thread Turn"

#: One shipped-shaped panel: `type`/`x` rather than `chart_type`/`dimension`,
#: which is exactly what `intelligence_templates/Financial/template.json`
#: writes and what `normalise()` has to repair before a patch can name it
#: (gate 4).
SHIPPED_PANELS = [
	{"type": "bar", "title": "Movement by Account", "measure": "Net Movement", "x": "account"},
]

SKILL = "Exclude intercompany accounts when reporting movement."


def connected() -> bool:
	return bool(getattr(frappe, "db", None))


def live_provider_configured() -> bool:
	try:
		return providers.configured()
	except Exception:
		return False


def make_dashboard(panels=None, skill: str | None = None) -> str:
	doc = frappe.get_doc(
		{
			"doctype": DASHBOARD_DOCTYPE,
			"key": frappe.generate_hash(length=10),
			"title": "Gate Dashboard",
			"panels": frappe.as_json(SHIPPED_PANELS if panels is None else panels),
			"skill": skill,
		}
	)
	doc.insert(ignore_permissions=True)
	return str(doc.name)


def panels_of(dashboard: str) -> list[dict]:
	"""The stored panels, parsed. Read back through the document rather than
	the row so this sees exactly what a caller would."""
	parsed = frappe.parse_json(str(frappe.get_doc(DASHBOARD_DOCTYPE, dashboard).get("panels") or "[]"))
	return list(parsed)


class _Model:
	"""A canned model, standing in for `thread._complete`.

	Stubbed at the completion rather than at `_step` so the real envelope
	parser still runs: a test that bypassed `_envelope` would prove the loop's
	arithmetic against a shape no model can actually emit. Every prompt is
	recorded, so a test can assert on what the loop actually said rather than
	on what it meant to say."""

	def __init__(self, *envelopes: dict):
		self.envelopes = [json.dumps(e) for e in envelopes]
		self.prompts: list[str] = []

	def __call__(self, prompt: str, _rate_limits: list[int]) -> tuple[str | None, str | None]:
		self.prompts.append(prompt)
		if not self.envelopes:
			return None, "the canned model ran out of answers"
		return self.envelopes.pop(0), None


@contextmanager
def canned(model: _Model, **ask):
	"""The loop with its model call replaced, yielding the stubbed
	`manager.ask` when the test passed one (`return_value=` /
	`side_effect=`).

	`providers.enabled` and the quota are stubbed too: both are site settings,
	and a gate about the loop's own arithmetic must not pass or fail on
	whether this bench happens to have an API key in it today.
	"""
	with ExitStack() as stack:
		stack.enter_context(mock.patch.object(thread, "_complete", model))
		stack.enter_context(mock.patch.object(thread.providers, "enabled", return_value=True))
		stack.enter_context(mock.patch.object(thread.quota, "available", return_value=True))
		stack.enter_context(mock.patch.object(thread.quota, "consume"))
		yield stack.enter_context(mock.patch.object(thread.manager, "ask", **ask)) if ask else None


@unittest.skipUnless(connected(), "needs a site: bench --site <site> run-tests --app nakhoda")
class Gates(unittest.TestCase):
	def setUp(self) -> None:
		frappe.set_user("Administrator")

	def tearDown(self) -> None:
		frappe.set_user("Administrator")
		frappe.db.rollback()

	# -- gate 1: the loop terminates and is bounded -------------------------

	def test_gate_1_the_loop_is_bounded_by_its_step_budget(self):
		"""A model that only ever asks for data still stops.

		`ask_data` is the one action that continues, so a model stuck on it is
		the worst case for termination: the run must end at `MAX_STEPS` with
		`status: budget`, and must not have queried more than `MAX_DATA_STEPS`
		times whatever the model asked for.
		"""
		name = make_dashboard()
		asking = _Model(*[{"action": "ask_data", "question": f"q{i}"} for i in range(thread.MAX_STEPS + 3)])
		answer = {"columns": ["n"], "rows": [{"n": 1}], "row_count": 1, "agent_run": None}
		with canned(asking, return_value=answer) as asked:
			result = thread.converse("how are we doing", dashboard=name)

		self.assertEqual(result["status"], "budget")
		self.assertLessEqual(len(result["steps"]), thread.MAX_STEPS)
		self.assertLessEqual(asked.call_count if asked else 0, thread.MAX_DATA_STEPS)
		turn = frappe.get_doc(TURN_DOCTYPE, result["thread_turn"])
		self.assertEqual(turn.get("step_count"), len(result["steps"]))

	def test_gate_1_every_question_the_loop_asked_names_the_turn(self):
		"""Each `ask_data` is its own permission-checked `Nakhoda Agent Run`,
		and `thread_turn` is the only link back to the prompt that caused it -
		an audit trail with a gap is not one."""
		name = make_dashboard()
		created = [
			frappe.get_doc(
				{
					"doctype": "Nakhoda Agent Run",
					"user": "Administrator",
					"question": f"q{i}",
					"source": "generated",
					"status": "ok",
				}
			).insert(ignore_permissions=True)
			for i in range(2)
		]
		answers = [{"columns": [], "rows": [], "row_count": 0, "agent_run": doc.name} for doc in created]
		model = _Model(
			{"action": "ask_data", "question": "q0"},
			{"action": "ask_data", "question": "q1"},
			{"action": "reply", "text": "steady"},
		)
		with canned(model, side_effect=answers):
			result = thread.converse("how are we doing", dashboard=name)

		self.assertEqual(result["status"], "ok")
		for doc in created:
			self.assertEqual(
				frappe.db.get_value("Nakhoda Agent Run", doc.name, "thread_turn"), result["thread_turn"]
			)

	# -- gate 3: a patch is never applied by the loop -----------------------

	def test_gate_3_a_proposed_patch_changes_nothing_until_approved(self):
		name = make_dashboard()
		before_panels = panels_of(name)
		before_versions = frappe.db.count(VERSION_DOCTYPE, {"dashboard": name})
		model = _Model(
			{
				"action": "propose_patch",
				"ops": [
					{"op": "set_filter", "i": "panel_1", "column": "account", "operator": "=", "value": "X"}
				],
			}
		)
		with canned(model):
			result = thread.converse("only intercompany please", dashboard=name)

		self.assertEqual(result["status"], "ok")
		self.assertIn("patch", result)
		self.assertEqual(panels_of(name), before_panels)
		self.assertEqual(frappe.db.count(VERSION_DOCTYPE, {"dashboard": name}), before_versions)

		# ...and the approval, which is a separate call by a human, does.
		applied = dashboards_api.apply_dashboard_patch(name, result["patch"]["ops"], result["thread_turn"])
		self.assertEqual(frappe.db.count(VERSION_DOCTYPE, {"dashboard": name}), before_versions + 1)
		self.assertEqual(
			frappe.db.get_value(TURN_DOCTYPE, result["thread_turn"], "applied_version"), applied["version"]
		)

		# Undo unlinks it: the field means "live on the dashboard".
		dashboards_api.revert_dashboard_patch(name, applied["version"])
		self.assertFalse(frappe.db.get_value(TURN_DOCTYPE, result["thread_turn"], "applied_version"))

	# -- gate 4: shipped panels are patchable ------------------------------

	def test_gate_4_a_shipped_panel_can_be_filtered(self):
		"""`set_filter` on a panel a *template* wrote, not one an agent minted.

		This is the defect §2a names: a shipped panel has no `i`, so every
		`set_filter` against a freshly imported dashboard raised `PatchError`.
		`normalise()` stamps positional ids on read and write, which is what
		makes `panel_1` nameable here.
		"""
		name = make_dashboard()
		result = dashboards_api.apply_dashboard_patch(
			name,
			[{"op": "set_filter", "i": "panel_1", "column": "account", "operator": "=", "value": "X"}],
		)
		self.assertEqual(result["diff"][0]["state"], "will_change")
		panel = panels_of(name)[0]
		self.assertEqual(panel["filters"], [{"column": "account", "operator": "=", "value": "X"}])
		# The shipped keys survived the round-trip through `normalise`.
		self.assertEqual(panel["title"], "Movement by Account")
		self.assertEqual(panel["chart_type"], "bar")

	def test_gate_4_a_shipped_panel_can_be_removed(self):
		name = make_dashboard()
		dashboards_api.apply_dashboard_patch(name, [{"op": "remove_item", "i": "panel_1"}])
		# Removal is a flag: the card stays on the page saying what left.
		self.assertTrue(panels_of(name)[0]["removed"])

	# -- gate 5: panels return data ----------------------------------------

	def test_gate_5_a_panel_backed_by_a_query_returns_rows(self):
		"""`panel_data` runs the panel's own query and hands back flint's input
		shape. Executed against the real site database - a panel that compiles
		but does not run is the failure this gate exists to catch."""
		query = frappe.get_doc(
			{
				"doctype": "Nakhoda Query",
				"title": "Gate Query",
				"data_source": default_source(),
				"operations": frappe.as_json(
					[
						{"type": "source", "table": "tabSales Invoice"},
						{
							"type": "summarize",
							"by": [{"name": "status", "expr": {"col": "status"}}],
							"measures": [{"name": "n", "expr": {"fn": "count", "args": []}}],
						},
					]
				),
			}
		).insert(ignore_permissions=True)
		name = make_dashboard(
			[{"chart_type": "bar", "title": "By status", "query": query.name, "i": "chart_1"}]
		)

		data = dashboards_api.panel_data(name, "chart_1")
		self.assertEqual(data["columns"], ["status", "n"])
		self.assertEqual(data["chart_type"], "bar")
		self.assertIsInstance(data["rows"], list)
		# Semantic types are what flint needs to pick a mark: a count is a
		# `Count`, never a `Category`, whatever the column is called - and
		# `Count` rather than `Number` because flint sizes a tally
		# differently from a measured quantity (`agent/charts.py`).
		self.assertEqual(data["semantic_types"].get("n"), "Count")

	# -- gate 6: permissions hold ------------------------------------------

	def test_gate_6_panel_data_is_read_as_the_caller(self):
		"""No `ignore_permissions` on the read path: a user who cannot read the
		dashboard gets a refusal, not rows."""
		name = make_dashboard()
		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError):
			dashboards_api.panel_data(name, "panel_1")

	def test_gate_6_converse_refuses_a_dashboard_the_caller_cannot_read(self):
		name = make_dashboard()
		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError):
			thread.converse("what is going on", dashboard=name)
		# Nothing was written under a name the caller could not read.
		self.assertEqual(frappe.db.count(TURN_DOCTYPE, {"dashboard": name}), 0)

	# -- gate 8: the dashboard's skill is live -----------------------------

	def test_gate_8_the_dashboard_skill_reaches_the_prompt(self):
		"""`Nakhoda Intelligence Template.skill` describes itself as "a playbook
		fragment routed into the agent's prompt". This asserts the routing, on
		the prompt text the loop actually sent."""
		name = make_dashboard(skill=SKILL)
		model = _Model({"action": "reply", "text": "noted"})
		with canned(model):
			result = thread.converse("how are we doing", dashboard=name)

		self.assertEqual(result["status"], "ok")
		self.assertTrue(model.prompts)
		self.assertIn(SKILL, model.prompts[0])
		# And the panels, so `set_filter` can name a real target.
		self.assertIn("Movement by Account", model.prompts[0])


@unittest.skipUnless(connected(), "needs a site")
@unittest.skipUnless(live_provider_configured(), "needs a reachable model provider")
class LiveLoop(unittest.TestCase):
	"""The same loop with a real model. Bounded, not graded: what the model
	*says* is not this gate's business - that it stops, records what it did,
	and applies nothing is."""

	def setUp(self) -> None:
		frappe.set_user("Administrator")

	def tearDown(self) -> None:
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def test_a_real_turn_stays_inside_its_budget_and_records_itself(self):
		name = make_dashboard(skill=SKILL)
		before = panels_of(name)
		result = thread.converse("how many sales invoices are there?", dashboard=name)

		self.assertIn(result["status"], {"ok", "error", "budget"})
		self.assertLessEqual(len(result["steps"]), thread.MAX_STEPS)
		turn = frappe.get_doc(TURN_DOCTYPE, result["thread_turn"])
		self.assertEqual(turn.get("question"), "how many sales invoices are there?")
		# The loop never applies: the panels are identical whatever it did.
		self.assertEqual(panels_of(name), before)


if __name__ == "__main__":
	unittest.main()
