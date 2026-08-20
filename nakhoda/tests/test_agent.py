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
from typing import Any, ClassVar
from unittest import mock

import frappe
from frappe.utils import now_datetime

from nakhoda import api
from nakhoda.agent import charts, manager, providers, quota
from nakhoda.agent.router import Route
from nakhoda.agent.tiers import Tier
from nakhoda.semantic.retrieval import Index


#: `manager.ask()` now prompts target `"ops_annotated"` (`driver.py`), so a
#: mocked `providers.complete` return value is the envelope that target
#: expects, not a bare array - `envelope()` builds it so every test below
#: states only the `ops`/`assumptions` it cares about.
def envelope(ops: list, assumptions: list[dict] | None = None) -> str:
	payload = {"ops": ops}
	if assumptions is not None:
		payload["assumptions"] = assumptions
	return json.dumps(payload)


OPS = [
	{"type": "source", "table": "tabSales Invoice"},
	{"type": "summarize", "measures": [{"name": "n", "expr": {"fn": "count", "args": []}}]},
]
VALID_OPS = envelope(OPS)

#: A grouped pipeline - `charts.MAX_BARS`-bounded territory list, so the
#: chart-wiring test below stays deterministic regardless of what this
#: site's real territories are, per `charts.pick`'s eligibility rule.
GROUPED_OPS_LIST = [
	{"type": "source", "table": "tabSales Invoice"},
	{
		"type": "summarize",
		"by": [{"name": "territory", "expr": {"col": "territory"}}],
		"measures": [{"name": "total", "expr": {"fn": "sum", "args": [{"col": "grand_total"}]}}],
	},
]
GROUPED_OPS = envelope(GROUPED_OPS_LIST)

#: A route the tests hand `ask()` directly, so this file never depends on what
#: the real semantic index selects for a question on this site.
SINGLE_TABLE = Route(Tier.FAST, "single table, no join", ("Sales Invoice",))


def connected() -> bool:
	return bool(getattr(frappe, "db", None))


@unittest.skipUnless(connected(), "needs a site: bench --site <site> run-tests --app nakhoda")
class Agent(unittest.TestCase):
	#: Tier ids now come from the selected provider's own settings fields
	#: (`agent/tiers.py`), not `NAKHODA_AGENT_MODEL_*` - the env vars only
	#: speak for a tier the settings left blank. So the fixture writes the
	#: Single, which is also what an admin editing the AI Provider tab does.
	#: `daily_ai_quota = 0` means "no cap": these tests grade the tier ladder,
	#: and a shared counter would otherwise make the last test in a run behave
	#: differently from the first.
	SETTINGS: ClassVar[dict[str, Any]] = {
		"enable_ai": 1,
		"ai_provider": "openrouter",
		"ai_model": "fast-1",
		"ai_model_fallback": "bal-1",
		"daily_ai_quota": 0,
	}

	def setUp(self) -> None:
		frappe.set_user("Administrator")
		for fieldname, value in self.SETTINGS.items():
			frappe.db.set_single_value("Nakhoda Settings", fieldname, value)
		self._route = mock.patch("nakhoda.agent.manager.route", return_value=SINGLE_TABLE)
		self._route.start()
		# A real index over the one table `SINGLE_TABLE` names, not `None`: the manager
		# renders the semantic context through `retrieval.context`, which reads the
		# index to prune the same columns it costed. These tests do not care what the
		# context says, but they do exercise the renderer, as they always have.
		self._index = mock.patch(
			"nakhoda.agent.manager.build_index",
			return_value=Index([frappe.get_meta("Sales Invoice")]),
		)
		self._index.start()

	def tearDown(self) -> None:
		self._index.stop()
		self._route.stop()
		frappe.set_user("Administrator")
		frappe.db.rollback()
		frappe.clear_document_cache("Nakhoda Settings", "Nakhoda Settings")

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
		self.assertNotIn("assumptions", result)
		self.assertFalse(run.assumptions)
		self.assertFalse(run.degraded)

	def test_a_refused_answer_is_repaired_on_the_same_model(self):
		"""2026-08-16: `providers.complete` samples at temperature 0, so the old
		ladder's answer to a refusal - the same prompt, a different rung - asked
		one model for the identical wrong pipeline twice before it could improve
		on it. The refusal names the offending node, so the second call carries
		it and the cheap model gets to correct itself, which is what
		`api.validate`'s "a model correcting itself" was always for."""
		with mock.patch.object(
			providers, "complete", side_effect=["not a pipeline at all", VALID_OPS]
		) as complete:
			result = manager.ask("how many invoices are there")

		self.assertEqual(complete.call_count, 2)
		self.assertNotIn("error", result)
		# Both calls went to the cheap rung: repair is not escalation.
		self.assertEqual([call.args[1] for call in complete.call_args_list], ["fast-1", "fast-1"])
		run = self.run_for(result["agent_run"])
		self.assertEqual(run.status, "ok")
		self.assertEqual(run.tier, Tier.FAST.value)
		self.assertEqual(run.model, "fast-1")
		self.assertFalse(run.escalated)
		self.assertFalse(run.degraded)

	def test_the_repair_prompt_carries_the_refused_answer_and_the_refusal(self):
		"""A retry that does not say what was wrong is the dead work this
		replaced. The mechanism is the prompt, so assert on the prompt."""
		with mock.patch.object(
			providers, "complete", side_effect=["not a pipeline at all", VALID_OPS]
		) as complete:
			manager.ask("how many invoices are there")

		repair_prompt = complete.call_args_list[1].args[0]
		self.assertIn("not a pipeline at all", repair_prompt)
		self.assertIn("no JSON object or array in completion", repair_prompt)
		# Still the original question, so the model is answering the same thing.
		self.assertIn("how many invoices are there", repair_prompt)

	def test_a_repair_that_also_fails_escalates_and_the_row_says_why(self):
		"""§Phase 4 gate: no row shows an escalation without a preceding
		validation failure - here there always is one, and the row must
		name it. Escalation is now what happens after the cheap model has had
		its correction and still failed."""
		with mock.patch.object(
			providers, "complete", side_effect=["not a pipeline at all", "still not one", VALID_OPS]
		) as complete:
			result = manager.ask("how many invoices are there")

		self.assertEqual(complete.call_count, 3)
		self.assertNotIn("error", result)
		run = self.run_for(result["agent_run"])
		self.assertEqual(run.tier, Tier.BALANCED.value)
		self.assertEqual(run.model, "bal-1")
		self.assertTrue(run.escalated)
		self.assertTrue(run.escalation_reason)
		self.assertFalse(run.degraded)

	def test_one_model_id_on_two_rungs_is_asked_once_per_question(self):
		"""Measured on `jkm` 2026-08-16: a site with one model id standing for
		both tiers spent two identical 59-second calls on one identical refusal.
		A rung with nothing new to offer is skipped, and skipping is not an
		outage - the row must not claim it was degraded."""
		frappe.db.set_single_value("Nakhoda Settings", "ai_model_fallback", "fast-1")
		with mock.patch.object(providers, "complete", return_value="not a pipeline at all") as complete:
			result = manager.ask("how many invoices are there")

		# The ask and its one repair - not four calls across the ladder.
		self.assertEqual(complete.call_count, 2)
		self.assertIn("error", result)
		run = self.run_for(result["agent_run"])
		self.assertFalse(run.degraded)
		# The rung that asked, and the model that refused. `7u3g3n2ss6` on `jkm`
		# recorded this failure with an empty `model`: unattributable.
		self.assertEqual(run.tier, Tier.FAST.value)
		self.assertEqual(run.model, "fast-1")
		# Nothing new was reachable, so nothing was escalated to - the reason
		# field stays empty and `error` carries the diagnosis instead.
		self.assertFalse(run.escalated)
		self.assertFalse(run.escalation_reason)
		self.assertIn("no JSON object or array in completion", run.error)
		# What the analyst reads names whose failure it was; the parser's own
		# words ride along in the parenthesis rather than standing alone.
		self.assertIn("could not produce a query", result["error"])
		self.assertIn("no JSON object or array in completion", result["error"])

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

	def test_a_bad_expression_escalates_like_any_other_invalid_pipeline(self):
		"""2026-08-16, from a live model: `{"and": [...]}`, the shorthand for a
		conjunction this grammar spells `{"fn": "and", "args": [...]}`. The
		expression layer raises `ExpressionError`, which `api.run` did not
		catch alongside `OperationError`, so the refusal left `ask()` as an
		exception instead of a value: HTTP 500, no `Nakhoda Agent Run` row,
		nothing on screen. A malformed answer is a quality signal like any
		other, and escalating is what this ladder does with those."""
		bad = envelope(
			[
				{"type": "source", "table": "tabSales Invoice"},
				{
					"type": "filter",
					"where": {
						"and": [
							{"fn": "eq", "args": [{"col": "docstatus"}, {"lit": 1}]},
							{"fn": "eq", "args": [{"col": "is_return"}, {"lit": 0}]},
						]
					},
				},
			]
		)
		with mock.patch.object(providers, "complete", side_effect=[bad, bad, VALID_OPS]) as complete:
			result = manager.ask("how many invoices are there")

		# Ask, repair, then the next rung: escalation is what a model that
		# cannot use its own refusal earns.
		self.assertEqual(complete.call_count, 3)
		self.assertNotIn("error", result)
		run = self.run_for(result["agent_run"])
		self.assertEqual(run.status, "ok")
		self.assertTrue(run.escalated)
		# The reason names the node, so a prompt fix has something to aim at.
		self.assertIn("expected exactly one of col/lit/fn", run.escalation_reason)

	def test_a_clash_only_the_schema_knows_about_also_escalates(self):
		"""The second half of the same defect, and the harder half: this pipeline
		*passes* validation. `tabSales Invoice.customer_name` and the joined
		`tabCustomer.customer_name` only collide once both schemas are resolved,
		so the refusal comes from `compile_pipeline`, past the endpoint's
		validate call. It reached the browser as a 500 for the same reason the
		expression one did, and it is fixed at the same boundary rather than by
		widening validation into a schema check it cannot do.
		"""
		clashing = envelope(
			[
				{"type": "source", "table": "tabSales Invoice"},
				{
					"type": "join",
					"table": "tabCustomer",
					"left_on": {"col": "customer"},
					"right_on": {"col": "name"},
					"select": [{"name": "customer_name", "expr": {"col": "customer_name"}}],
				},
			]
		)
		with mock.patch.object(
			providers, "complete", side_effect=[clashing, clashing, VALID_OPS]
		) as complete:
			result = manager.ask("total invoiced per customer")

		self.assertEqual(complete.call_count, 3)
		self.assertNotIn("error", result)
		run = self.run_for(result["agent_run"])
		self.assertEqual(run.status, "ok")
		self.assertTrue(run.escalated)
		self.assertIn("already in scope", run.escalation_reason)

	def test_an_unavailable_tier_names_the_reason_it_was_unavailable(self):
		"""2026-08-16, from a real report: `openai` was undeclared *and*
		uninstalled, so every question came back "every model in tier BALANCED
		was unavailable" and nothing else. A missing SDK, a rejected key and an
		unreachable host all rendered identically, leaving an operator with no
		next move. Degrading stays unconditional; degrading *silently* is the
		defect this asserts against."""
		with mock.patch.object(
			providers, "complete", side_effect=ModuleNotFoundError("No module named 'openai'")
		) as complete:
			result = manager.ask("how many invoices are there")

		# FAST then BALANCED; PREMIUM carries no ids, so it asks no model.
		self.assertEqual(complete.call_count, 2)
		self.assertIn("No module named 'openai'", result["error"])
		# Which id failed, not just that something did.
		self.assertIn("fast-1", result["error"])
		run = self.run_for(result["agent_run"])
		self.assertEqual(run.status, "error")
		self.assertTrue(run.degraded)
		# The same sentence the browser got is the one the audit row keeps.
		self.assertEqual(run.degradation_reason, result["error"])

	def test_a_provider_failure_with_no_message_still_names_its_kind(self):
		"""Some SDK errors stringify to nothing; a detail ending in a bare
		colon would be worse than the exception's class."""
		with mock.patch.object(providers, "complete", side_effect=TimeoutError()):
			result = manager.ask("how many invoices are there")

		self.assertIn("TimeoutError", result["error"])

	def test_three_consecutive_rate_limits_open_the_circuit_and_stop(self):
		# A settings field holds one id, so a multi-candidate rung is the env
		# var's job - and it only speaks for a tier the settings left blank
		# (`agent/tiers.py`). Blank the field, then set the list.
		frappe.db.set_single_value("Nakhoda Settings", "ai_model", "")
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
		"""Both rungs empty - and empty means empty: a variable set to `""` is
		ops saying "this tier has no models", which must not fall through to
		the provider's shipped default (`tiers._env_models`)."""
		for fieldname in ("ai_model", "ai_model_fallback"):
			frappe.db.set_single_value("Nakhoda Settings", fieldname, "")
		with mock.patch.dict(
			os.environ, {"NAKHODA_AGENT_MODEL_FAST": "", "NAKHODA_AGENT_MODEL_BALANCED": ""}
		):
			result = manager.ask("how many invoices are there")

		self.assertIn("error", result)
		run = self.run_for(result["agent_run"])
		self.assertEqual(run.status, "error")

	# -- the two gates that can refuse to ask a model ------------------------

	def test_the_master_switch_off_refuses_generated_answers(self):
		frappe.db.set_single_value("Nakhoda Settings", "enable_ai", 0)
		with mock.patch.object(providers, "complete") as complete:
			result = manager.ask("how many invoices are there")

		complete.assert_not_called()
		self.assertIn("AI is turned off", result["error"])
		self.assertEqual(self.run_for(result["agent_run"]).status, "error")

	def test_an_unwritten_master_switch_is_on_not_off(self):
		# A Check field with no `tabSingles` row reads back as 0
		# (`BaseDocument.init_valid_columns`), which is indistinguishable from
		# an admin's "off" through the document. It is not the same thing: the
		# field defaults to 1, and every site upgraded before an admin opens
		# the settings page has no row at all.
		frappe.db.delete("Singles", {"doctype": "Nakhoda Settings", "field": "enable_ai"})
		frappe.clear_document_cache("Nakhoda Settings", "Nakhoda Settings")

		self.assertTrue(providers.enabled())

		frappe.db.set_single_value("Nakhoda Settings", "enable_ai", 0)
		frappe.clear_document_cache("Nakhoda Settings", "Nakhoda Settings")
		self.assertFalse(providers.enabled())

	def test_a_spent_quota_refuses_generated_answers(self):
		# The window matters as much as the count: `quota.available` resets a *due*
		# window before comparing the cap, so a spent counter under an elapsed window
		# is allowed through by design. Without pinning the start, this test asserted
		# the refusal only on the day the site's own window last opened - it read
		# `2026-08-15 18:40` and went green, then failed the next morning.
		frappe.db.set_single_value(
			"Nakhoda Settings",
			{
				"daily_ai_quota": 5,
				"ai_quota_used": 5,
				"quota_reset_schedule": "Daily",
				"quota_window_start": now_datetime(),
			},
		)
		with mock.patch.object(providers, "complete") as complete:
			result = manager.ask("how many invoices are there")

		complete.assert_not_called()
		self.assertIn("quota", result["error"])
		self.assertEqual(self.run_for(result["agent_run"]).status, "error")

	def test_an_answered_question_consumes_exactly_one_unit_of_quota(self):
		frappe.db.set_single_value("Nakhoda Settings", "daily_ai_quota", 5)
		frappe.db.set_single_value("Nakhoda Settings", "ai_quota_used", 0)
		with mock.patch.object(providers, "complete", return_value=VALID_OPS):
			result = manager.ask("how many invoices are there")

		self.assertNotIn("error", result)
		# Read it back the way the settings page's status strip does, not with
		# a raw column read - that is the number a user is shown.
		self.assertEqual(quota.status()["quota_used"], 1)

	# -- a grouped answer's shape decides whether a chart comes along --------

	def test_a_grouped_answer_attaches_a_chart_when_the_shape_supports_it(self):
		"""Wiring proof, not a `charts.pick` correctness proof - `test_charts.py`
		grades `pick()` itself against fixed rows. This confirms `manager.ask()`
		actually calls it with the real pipeline result and threads the outcome
		into the response, for whatever territories this site's Sales Invoices
		actually have - `GROUPED_OPS` only guarantees the shape (two columns),
		not the row count, so the assertion follows whichever branch
		`charts.MAX_BARS`/`MIN_BARS` puts the real result in."""
		with mock.patch.object(providers, "complete", return_value=GROUPED_OPS) as complete:
			result = manager.ask("revenue by territory")

		self.assertEqual(complete.call_count, 1)
		self.assertNotIn("error", result)
		if charts.MIN_BARS <= result["row_count"] <= charts.MAX_BARS:
			self.assertIn("chart", result)
			self.assertEqual(len(result["chart"]["series"]), result["row_count"])
			for point in result["chart"]["series"]:
				self.assertIsInstance(point["label"], str)
				self.assertIsInstance(point["value"], float)
		else:
			self.assertNotIn("chart", result)

	# -- the model's own assumptions, when it reports any --------------------

	def test_assumptions_the_model_reports_are_recorded_and_returned(self):
		assumptions = [
			{"tag": "period", "state": "applied", "text": "assumed this fiscal year"},
			{
				"tag": "territory",
				"state": "needs_you",
				"text": "assumed all territories",
				"counterfactual": "Kenya only would total less",
				"alt_label": "Kenya only",
				"keep_label": "Keep all",
			},
		]
		with mock.patch.object(providers, "complete", return_value=envelope(OPS, assumptions)):
			result = manager.ask("how many invoices are there")

		self.assertNotIn("error", result)
		self.assertEqual(result["assumptions"], assumptions)
		run = self.run_for(result["agent_run"])
		self.assertIsNotNone(run.assumptions)
		self.assertEqual(json.loads(run.assumptions or "null"), assumptions)

	def test_a_verified_answer_never_carries_assumptions(self):
		"""`12-build-plan.md` Phase 3's "no ambiguity" gate: a verified query is
		never asked for one, so the key must not appear even if a stale value
		is somehow lying around."""
		question = "How many invoices, verified and unambiguous?"
		doc = frappe.get_doc(
			{
				"doctype": "Nakhoda Verified Query",
				"title": "Invoice count, no ambiguity (agent test)",
				"question": question,
				"data_source": api.default_source(),
				"operations": frappe.as_json(OPS),
			}
		).insert()
		doc.submit()

		with mock.patch.object(providers, "complete") as complete:
			result = manager.ask(question)

		complete.assert_not_called()
		self.assertNotIn("assumptions", result)

	def test_malformed_assumptions_from_the_model_never_block_a_valid_pipeline(self):
		"""A garbled `assumptions` list is dropped by `driver._valid_assumptions`
		before `manager` ever sees it - the pipeline still answers and the run
		still records `status = ok`, not an escalation."""
		raw = json.dumps({"ops": OPS, "assumptions": ["not an object", {"tag": "x"}]})
		with mock.patch.object(providers, "complete", return_value=raw) as complete:
			result = manager.ask("how many invoices are there")

		self.assertEqual(complete.call_count, 1)
		self.assertNotIn("error", result)
		self.assertNotIn("assumptions", result)
		run = self.run_for(result["agent_run"])
		self.assertEqual(run.status, "ok")
		self.assertFalse(run.escalated)
		self.assertFalse(run.assumptions)


class ResponsesStream(unittest.TestCase):
	"""`providers._parse_responses_sse` - the one place this app reads a wire
	format instead of letting the SDK do it, because a subscription token
	cannot reach `chat/completions` and the backend that answers it speaks the
	Responses API over SSE (`_codex_complete`). No site needed: it is a pure
	string function."""

	def frame(self, **event) -> str:
		return f"data: {json.dumps(event)}"

	def finished(self, *parts) -> str:
		return self.frame(type="response.completed", response={"output": [{"content": list(parts)}]})

	def test_deltas_are_joined_in_order(self):
		body = "\n".join(
			[
				": keepalive",
				self.frame(type="response.output_text.delta", delta="Total "),
				self.frame(type="response.output_text.delta", delta="is 42"),
				"data: [DONE]",
			]
		)
		self.assertEqual(providers._parse_responses_sse(body), "Total is 42")

	def test_a_terminal_message_answers_when_no_delta_ever_arrived(self):
		"""A backend that streams nothing still answers: the completed event
		repeats the whole message, and non-text parts are not answer text."""
		body = "\n".join(
			[
				self.finished(
					{"type": "reasoning", "text": "thinking out loud"},
					{"type": "output_text", "text": "42 exactly"},
				),
				"data: [DONE]",
			]
		)
		self.assertEqual(providers._parse_responses_sse(body), "42 exactly")

	def test_deltas_win_over_the_terminal_copy_rather_than_doubling_it(self):
		body = "\n".join(
			[
				self.frame(type="response.output_text.delta", delta="42"),
				self.finished({"type": "output_text", "text": "42"}),
			]
		)
		self.assertEqual(providers._parse_responses_sse(body), "42")

	def test_a_truncated_stream_returns_what_arrived_instead_of_raising(self):
		"""There is no retry above this that could fetch the missing bytes, so a
		half-written frame is a short answer, not an exception."""
		body = self.frame(type="response.output_text.delta", delta="partial") + '\ndata: {"type":"resp'
		self.assertEqual(providers._parse_responses_sse(body), "partial")

	def test_a_body_with_no_events_is_empty_not_an_error(self):
		self.assertEqual(providers._parse_responses_sse(""), "")
		self.assertEqual(providers._parse_responses_sse("event: ping\ndata: [DONE]"), "")


if __name__ == "__main__":
	unittest.main()
