"""The half of the semantic layer a person writes: what `sync` may and may not touch.

Everything else in the semantic layer is derived, and a derived thing can be rebuilt
from the site whenever it looks wrong. This module cannot: `Nakhoda Semantic Model`
carries sentences somebody typed, next to counts a scan produced, in one row that a
migration rewrites. So the properties graded here are about the *seam*:

1. **A curator's words survive every mechanical pass.** `sync` runs on `bench migrate`
   and from the settings tab, and it rewrites the generated half of every row it
   touches - including rows whose prose is hand-written. The statistics beside that
   prose are refreshed at the same time, because they are measurements, not opinions.
   Both halves of that sentence are asserted, in both directions.
2. **`curated` is derived, never declared.** No endpoint takes it as a parameter:
   `NakhodaSemanticModel.validate` reads what the row now holds. Clearing the fields
   therefore hands a document *back* to the generator, which is the only way an
   over-eager curator can undo themselves.
3. **A stale form is refused whole.** A column payload naming a field the schema no
   longer has is a client that has been open too long; applying the half that matched
   would leave the row describing a schema nobody deployed.
4. **A save changes the next question, not the next restart.** The curated layer is
   cached (three queries, read on every ask), so an invalidation that fails is not a
   crash - it is a settings page that appears to work and a retrieval that ignores it.

The fixture is a document this site has never written to and never described, chosen
at runtime: the 439 real curated rows on this bench are somebody's work, and a test
suite that edits them to prove it preserves them would be its own counter-example.
"""

from __future__ import annotations

import unittest
from unittest import mock

import frappe

from nakhoda.api import semantic as api
from nakhoda.semantic import curation
from nakhoda.semantic.retrieval import Index, context

MODEL = curation.MODEL
FIELD = curation.FIELD


def connected() -> bool:
	return bool(getattr(frappe, "db", None))


@unittest.skipUnless(connected(), "needs a site: bench --site <site> run-tests --app nakhoda")
class Curation(unittest.TestCase):
	@classmethod
	def setUpClass(cls) -> None:
		frappe.set_user("Administrator")
		cls.target = cls.pick_target()

	@staticmethod
	def pick_target() -> str:
		"""A document nobody has curated, so this suite never edits a curator's row.

		Sorted, so the choice is the same on two runs of the same site, and filtered
		on the same two exclusions `sync` itself applies (singles and virtuals have no
		table to describe).
		"""
		described = set(frappe.get_all(MODEL, pluck="doctype_name"))
		candidates = frappe.get_all(
			"DocType",
			filters={"issingle": 0, "is_virtual": 0, "istable": 0},
			pluck="name",
			order_by="name asc",
		)
		for name in candidates:
			if name in described or name in curation.used_doctypes():
				continue
			if len(frappe.get_meta(name).get("fields") or []) >= 3:
				return str(name)
		raise unittest.SkipTest("every document on this site is already described")

	def setUp(self) -> None:
		frappe.set_user("Administrator")
		curation.sync([self.target])
		self.row = str(frappe.db.get_value(MODEL, {"doctype_name": self.target}, "name"))
		self.generated = str(frappe.db.get_value(MODEL, self.row, "description"))

	def tearDown(self) -> None:
		frappe.set_user("Administrator")
		frappe.db.rollback()
		for name in frappe.get_all(MODEL, filters={"doctype_name": self.target}, pluck="name"):
			frappe.delete_doc(MODEL, name, force=True, ignore_permissions=True)
		frappe.db.commit()
		# The curated map is cached per site, not per test: a synonym written above
		# would otherwise follow this suite into `test_retrieval`'s live index.
		curation.forget()

	def column(self) -> str:
		"""A real column on the fixture, named as a curator would see it."""
		for row in api.get_model(self.row)["fields"]:
			if row["fieldname"] != "name":
				return str(row["fieldname"])
		self.fail(f"{self.target} renders no columns")

	# --- what a mechanical pass may not touch ------------------------------------

	def test_a_written_description_survives_the_next_sync(self):
		"""The promise the whole doctype exists to make."""
		api.save_model(self.row, description="Revenue this business recognises, per invoice.")

		done = curation.sync([self.target])

		self.assertEqual(done["preserved"], 1, "a curated row was not reported preserved")
		self.assertEqual(
			frappe.db.get_value(MODEL, self.row, "description"),
			"Revenue this business recognises, per invoice.",
		)

	def test_a_synced_row_still_refreshes_its_measurements(self):
		"""Prose is preserved; the numbers beside it are not opinions.

		The failure this catches is the plausible over-correction of the test above:
		skipping a curated row entirely, which leaves a hand-described document
		reporting a column count from before the migration that changed it.
		"""
		api.save_model(self.row, description="Hand-written and therefore preserved.")
		frappe.db.set_value(MODEL, self.row, "row_count", 999_999, update_modified=False)
		frappe.db.set_value(MODEL, self.row, "token_cost", 1, update_modified=False)

		curation.sync([self.target])

		self.assertNotEqual(
			frappe.db.get_value(MODEL, self.row, "row_count"),
			999_999,
			"a curated row kept a stale row count",
		)
		self.assertNotEqual(
			frappe.db.get_value(MODEL, self.row, "token_cost"),
			1,
			"a curated row kept a stale token cost",
		)
		self.assertEqual(
			frappe.db.get_value(MODEL, self.row, "description"),
			"Hand-written and therefore preserved.",
		)

	def test_a_column_synonym_survives_the_child_table_rebuild(self):
		"""Frappe deletes and rebuilds child rows on save; `sync` carries these across.

		Column synonyms are the half of curation that moves answers - retrieval reads
		them exactly like the document's own - and they live in the table `sync`
		rewrites wholesale, which is why the hand-carry is graded rather than trusted.
		"""
		column = self.column()
		api.save_model(self.row, field_synonyms={column: "turnover takings"})

		curation.sync([self.target])

		kept = frappe.db.get_value(FIELD, {"parent": self.row, "fieldname": column}, "synonyms")
		self.assertEqual(kept, "turnover takings")

	def test_syncing_twice_updates_one_row_rather_than_adding_a_second(self):
		"""Upsert, not insert. The lookup is by field for a reason.

		`frappe.db.exists(MODEL, name)` returns the name unchecked when docname equals
		doctype name (`database.py:1275`), so a doctype named after a doctype - which
		this app ships three of - would resolve to a row that was never inserted.
		"""
		first = curation.sync([self.target])
		self.assertEqual((first["created"], first["updated"]), (0, 1))
		self.assertEqual(frappe.db.count(MODEL, {"doctype_name": self.target}), 1)

	def test_a_single_is_never_modelled(self):
		"""Singles have no table, so there is nothing for a column list to describe."""
		done = curation.sync(["Nakhoda Settings"])
		self.assertEqual(done, {"created": 0, "updated": 0, "preserved": 0})

	# --- what a curator can and cannot declare -----------------------------------

	def test_curated_is_derived_from_the_row_not_asked_for(self):
		"""Writing prose marks the row; clearing it hands the document back."""
		api.save_model(self.row, description="A person was here.")
		self.assertTrue(frappe.db.get_value(MODEL, self.row, "curated"))

		api.save_model(self.row, description="", synonyms="")
		self.assertFalse(frappe.db.get_value(MODEL, self.row, "curated"))

		curation.sync([self.target])
		self.assertEqual(frappe.db.get_value(MODEL, self.row, "description"), self.generated)

	def test_a_document_synonym_alone_marks_the_row_curated(self):
		"""Naming a document is curation even when its description is generated."""
		api.save_model(self.row, synonyms="revenue turnover")

		self.assertTrue(frappe.db.get_value(MODEL, self.row, "curated"))
		self.assertEqual(
			frappe.db.get_value(MODEL, self.row, "description"),
			self.generated,
			"a synonym rewrote generated prose",
		)

	def test_a_stale_column_payload_is_refused_whole(self):
		"""One unknown fieldname rejects the save; nothing from it is applied."""
		column = self.column()

		with self.assertRaises(frappe.ValidationError):
			api.save_model(
				self.row,
				field_synonyms={column: "written", "no_such_column_here": "ignored"},
			)

		self.assertFalse(
			frappe.db.get_value(FIELD, {"parent": self.row, "fieldname": column}, "synonyms"),
			"a rejected payload wrote one of its columns anyway",
		)

	# --- caching, permissions, and the seeder ------------------------------------

	def test_a_saved_synonym_reaches_the_next_question(self):
		"""The cache is read on every ask, so a save has to invalidate it here."""
		curation.synonyms()  # warm

		api.save_model(self.row, synonyms="widgetry")

		self.assertIn("widgetry", curation.synonyms().get(self.target, ""))

	def test_a_written_description_replaces_the_generated_one_in_the_prompt(self):
		"""Prose is hand-*correctable*: what a model reads is what a curator wrote."""
		api.save_model(self.row, description="One row per shipment leaving the yard.")

		rendered = context([self.target], Index((frappe.get_meta(self.target),)))

		self.assertIn("One row per shipment leaving the yard.", rendered)
		self.assertNotIn(self.generated, rendered)

	def test_reading_is_open_and_writing_is_not(self):
		"""Anyone who can ask a question can see coverage; only an admin may curate."""
		user = self.make_user("curation-reader@nakhoda.test", ["Nakhoda User"])
		frappe.set_user(user)

		self.assertIn("modelled", api.coverage())
		with self.assertRaises(frappe.PermissionError):
			api.save_model(self.row, description="not mine to write")

	def test_the_seeder_offers_documents_this_site_uses_and_never_our_own(self):
		"""`used_doctypes` is the seed list; this app's tables are not curatable.

		A row modelling `Nakhoda Semantic Model` would describe the curation layer to
		the query engine as if it were business data, and its docname would collide
		with the doctype-name lookup above.
		"""
		used = curation.used_doctypes()

		self.assertTrue(used, "no document on this site is written to or reported on")
		for own in (MODEL, FIELD, curation.METRIC, "Nakhoda Settings"):
			self.assertNotIn(own, used)

	def test_the_seed_flag_widens_the_pass_and_a_busy_run_refuses(self):
		"""Enqueued once, over a set the caller chose, and never twice at once."""
		with (
			mock.patch("nakhoda.api.semantic.is_job_enqueued", return_value=False),
			mock.patch.object(frappe, "enqueue") as enqueue,
		):
			queued = api.regenerate(seed=1)

		self.assertTrue(queued["queued"])
		self.assertEqual(queued["documents"], len(curation.used_doctypes()))
		self.assertEqual(enqueue.call_args.kwargs["job_id"], api.JOB_ID)
		self.assertEqual(len(enqueue.call_args.kwargs["doctypes"]), queued["documents"])

		with (
			mock.patch("nakhoda.api.semantic.is_job_enqueued", return_value=True),
			mock.patch.object(frappe, "enqueue") as enqueue,
		):
			self.assertEqual(api.regenerate(), {"queued": False, "reason": "in_progress"})
		enqueue.assert_not_called()

	def test_coverage_counts_what_the_settings_tab_shows(self):
		"""The tab's three numbers are the three things a curator can have done."""
		before = api.coverage()
		api.save_model(self.row, description="Counted once.", synonyms="counted")

		after = api.coverage()

		self.assertEqual(after["curated"], before["curated"] + 1)
		self.assertEqual(after["with_synonyms"], before["with_synonyms"] + 1)
		self.assertEqual(after["modelled"], before["modelled"], "coverage invented a row")

	def make_user(self, email: str, roles: list[str]) -> str:
		if frappe.db.exists("User", email):
			frappe.delete_doc("User", email, force=True, ignore_permissions=True)
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": email.split("@")[0],
				"send_welcome_email": 0,
				"roles": [{"role": r} for r in roles],
			}
		)
		user.flags.ignore_permissions = True
		user.insert()
		self.addCleanup(self.drop_user, str(user.name))
		return str(user.name)

	def drop_user(self, email: str) -> None:
		frappe.set_user("Administrator")
		frappe.delete_doc("User", email, force=True, ignore_permissions=True)
		frappe.db.commit()


if __name__ == "__main__":
	unittest.main()
