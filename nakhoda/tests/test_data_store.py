"""The Data Store surface: what is importable, who may import it, and what
happens to a copy that never comes back.

The structural change this file grades is `import_table` enqueueing instead of
copying inline (`api/data_store.py`'s docstring: Insights' synchronous
`data_warehouse.py:85-126` holds an HTTP worker open for a full table copy).
Enqueueing buys three failure modes that a synchronous copy does not have, and
each one is a test below: a second click while a copy is running, a worker that
dies mid-copy leaving the row on `Syncing` forever, and a scheduler that could
quietly widen the warehouse past what an admin asked for.

`frappe.enqueue` is mocked everywhere except `test_a_real_import_lands_rows_in_
the_warehouse` - the queue is Frappe's, not this app's, and a test that proves
RQ works proves nothing about this module. What is graded instead is the state
this module commits *before* handing over, because a worker that loads a row
still marked from the previous run is exactly the bug the ordering prevents.

Unlike the rest of the suite these writes cannot roll back: `_tracking_row` and
`_queue_import` commit, deliberately, so the enqueued job can read them from its
own connection. Every test therefore records what it created and deletes it in
`tearDown`.
"""

from __future__ import annotations

import unittest
from typing import Any
from unittest import mock

import frappe
from frappe.query_builder import DocType
from frappe.utils import add_to_date, cint, now_datetime

from nakhoda.api import data_store
from nakhoda.patches.v1_0 import data_store_setting_defaults

#: Present on any ERPNext site and small enough to copy in a test.
DOCTYPE = "Currency"

TABLE = "Nakhoda Table"
LOG = "Nakhoda Table Import Log"
SETTINGS = "Nakhoda Settings"

#: The two Int caps on the Data Store tab, whose stored zero is not a legal
#: value - see `patches/v1_0/data_store_setting_defaults.py`.
CAPS = ("max_records_to_sync", "max_memory_usage")


def connected() -> bool:
	return bool(getattr(frappe, "db", None))


def value(doctype: str, name: str, field: str) -> Any:
	"""One field off one row. `frappe.db.get_value`'s declared return is a
	union over every call shape it supports, so reading a scalar column
	through it directly makes every numeric assertion below a type error."""
	return frappe.db.get_value(doctype, name, field)


@unittest.skipUnless(connected(), "needs a site: bench --site <site> run-tests --app nakhoda")
class DataStore(unittest.TestCase):
	def setUp(self) -> None:
		frappe.set_user("Administrator")
		# The switch is deployment state, not a fixture: an operator who turned
		# the store off would otherwise fail every import test below. The three
		# tests that grade the gate itself flip it again from here.
		self.set_store(True)
		# The code under test commits, so rollback cannot undo it; snapshot what
		# was already there and delete only what this test adds.
		self.pre_tables = set(frappe.get_all(TABLE, pluck="name"))
		self.pre_logs = set(frappe.get_all(LOG, pluck="name"))

	def tearDown(self) -> None:
		frappe.set_user("Administrator")
		frappe.db.rollback()
		for doctype, pre in ((LOG, self.pre_logs), (TABLE, self.pre_tables)):
			for name in set(frappe.get_all(doctype, pluck="name")) - pre:
				frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)
		frappe.db.commit()

	def make_user(self, email: str, roles: list[str]) -> str:
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
		return str(user.name)

	def queue(self, doctype: str = DOCTYPE, **kwargs):
		"""`import_table` with the queue stubbed. Returns (result, enqueue mock)."""
		with mock.patch.object(frappe, "enqueue") as enqueue:
			result = data_store.import_table(doctype, **kwargs)
		return result, enqueue

	# -- the picker ---------------------------------------------------------

	def test_an_unimported_doctype_is_still_listed(self):
		"""The Data Store is a picker over everything importable.

		Insights' `DataStoreList` shows unimported tables too; listing only
		what has already landed would leave no way to import a first table.
		"""
		row = self.find(data_store.list_tables(limit=500), DOCTYPE)
		self.assertEqual(row["sync_state"], "Never")
		self.assertIsNone(row["nakhoda_table"])
		self.assertFalse(row["stored_in_warehouse"])
		self.assertEqual(row["table_name"], f"tab{DOCTYPE}")

	def test_listing_reflects_the_tracking_row(self):
		"""One join, so the picker and the warehouse cannot disagree."""
		self.queue()
		row = self.find(data_store.list_tables(limit=500), DOCTYPE)
		self.assertEqual(row["sync_state"], "Syncing")
		self.assertIsNotNone(row["nakhoda_table"])

	def test_search_filters_by_label(self):
		matches = data_store.list_tables(search_term=DOCTYPE.lower())
		self.assertTrue(matches)
		self.assertTrue(all(DOCTYPE.lower() in row["label"].lower() for row in matches))

	def test_a_reader_without_the_doctype_never_sees_it_listed(self):
		"""The picker is `api.query.list_sources`, so it is already filtered."""
		analyst = self.make_user("nakhoda-store-reader@example.com", ["Nakhoda User"])
		self.assertFalse(frappe.has_permission("Sales Invoice", "read", user=analyst))
		frappe.set_user(analyst)
		labels = {row["doctype"] for row in data_store.list_tables(limit=500)}
		self.assertNotIn("Sales Invoice", labels)

	# -- the master switch --------------------------------------------------

	def test_the_switch_off_refuses_an_import_and_says_which_setting(self):
		"""An admin who turned the store off and forgot gets a one-line answer.

		The alternative - accepting the call and quietly enqueueing nothing -
		is precisely the silent failure the import log exists to prevent.
		"""
		self.set_store(False)
		with mock.patch.object(frappe, "enqueue") as enqueue:
			with self.assertRaises(frappe.ValidationError) as caught:
				data_store.import_table(DOCTYPE)

		enqueue.assert_not_called()
		self.assertIn("Data Store", str(caught.exception))
		# The gate runs before `_tracking_row`, so a refused call leaves no
		# half-created row behind claiming a table is being tracked.
		self.assertFalse(frappe.db.exists(TABLE, {"document_type": DOCTYPE}))

	def test_the_switch_off_stops_the_daily_refresh(self):
		"""A switch that blocked the button but left a nightly job writing to
		the same warehouse would not mean what it says."""
		queued, _ = self.queue()
		frappe.db.set_value(TABLE, queued["table"], "stored_in_warehouse", 1, update_modified=False)
		frappe.db.delete(LOG, {"name": queued["log"]})

		self.set_store(False)
		with mock.patch.object(data_store, "_queue_import") as requeue:
			data_store.sync_stored_tables()
		requeue.assert_not_called()

		self.set_store(True)
		with mock.patch.object(data_store, "_queue_import") as requeue:
			data_store.sync_stored_tables()
		self.assertIn(queued["table"], {call.args[0].name for call in requeue.call_args_list})

	def test_the_switch_gates_copying_never_reading(self):
		"""Off, the picker still lists and a landed table keeps its state.

		A setting that changed the answer to a question already being asked
		would be a bug nobody could reproduce, so this one narrows to movement.
		"""
		queued, _ = self.queue()
		frappe.db.set_value(TABLE, queued["table"], "stored_in_warehouse", 1, update_modified=False)

		self.set_store(False)
		row = self.find(data_store.list_tables(limit=500), DOCTYPE)
		self.assertTrue(row["stored_in_warehouse"])
		self.assertEqual(row["sync_state"], "Syncing")

	def test_an_unwritten_switch_is_on_not_off(self):
		"""A Check with no `tabSingles` row reads back as 0
		(`BaseDocument.init_valid_columns`), which is indistinguishable from an
		admin's explicit off. It is not the same thing: the field ships
		`"default": "1"`, so every site upgraded past this field would
		otherwise find its Data Store switched off by the upgrade itself."""
		self.set_store(None)
		self.assertTrue(data_store.data_store_enabled())

		self.set_store(False)
		self.assertFalse(data_store.data_store_enabled())

	def test_the_patch_writes_every_unwritten_data_store_default(self):
		"""The readers already refuse to believe a missing row - the Check
		through `setting_enabled`, the caps through their `or` fallbacks - but
		the settings page reads the document API, which hands it the cast
		zeroes. Unpatched, the tab renders `Enable` off over a store that is
		importing and `0`/`0` over a worker copying a million rows with 512 MB.
		"""
		self.set_store(None)
		self.forget_caps()

		data_store_setting_defaults.execute()

		self.assertEqual(cint(self.store_row()), 1)
		self.assertTrue(data_store.data_store_enabled())
		self.assertEqual(cint(frappe.db.get_single_value(SETTINGS, "max_records_to_sync")), 1_000_000)
		self.assertEqual(cint(frappe.db.get_single_value(SETTINGS, "max_memory_usage")), 512)

	def test_the_patch_leaves_a_deliberate_value_alone(self):
		"""An admin who switched the store off, or typed a smaller cap, has a
		row saying so. Re-running `migrate` must not read that as "never
		configured" - which is the whole reason the patch tests row presence
		rather than truthiness."""
		self.set_store(False)
		self.set_cap("max_records_to_sync", 5000)

		data_store_setting_defaults.execute()

		self.assertEqual(cint(self.store_row()), 0)
		self.assertFalse(data_store.data_store_enabled())
		self.assertEqual(cint(frappe.db.get_single_value(SETTINGS, "max_records_to_sync")), 5000)

	def test_a_cleared_cap_saves_as_the_default_not_as_zero(self):
		"""Clearing an Int box on the settings page posts `0`, and `0` is the
		one thing neither cap can mean - `_row_limit` would have to override it
		on every import while the page kept showing zero. `validate` writes the
		real number back instead, so clearing the box means "use the default"
		and the form, the DB and the worker agree afterwards."""
		self.forget_caps()

		settings = frappe.get_doc(SETTINGS)
		settings.max_records_to_sync = 0
		settings.max_memory_usage = 0
		settings.save()

		self.assertEqual(cint(frappe.db.get_single_value(SETTINGS, "max_records_to_sync")), 1_000_000)
		self.assertEqual(cint(frappe.db.get_single_value(SETTINGS, "max_memory_usage")), 512)
		# A table with no override of its own falls through to the site cap.
		self.assertEqual(data_store._row_limit(frappe._dict(row_limit=0)), data_store.DEFAULT_ROW_LIMIT)
		self.assertEqual(data_store._memory_limit(), data_store.DEFAULT_MEMORY_MB)

	# -- who may import -----------------------------------------------------

	def test_import_requires_create_on_nakhoda_table(self):
		"""`Nakhoda User` browses the store; only the admin roles populate it -
		the same split Insights draws with `session.user.is_admin`."""
		analyst = self.make_user("nakhoda-store-analyst@example.com", ["Nakhoda User"])
		frappe.set_user(analyst)
		with self.assertRaises(frappe.PermissionError):
			data_store.import_table(DOCTYPE)

	def test_import_requires_read_on_the_doctype_itself(self):
		"""Materialising rows is not an escalation: an admin who cannot read a
		doctype one row at a time cannot copy all of them at once either."""
		with mock.patch.object(frappe, "has_permission") as has_permission:
			has_permission.side_effect = lambda dt, *_a, **_kw: (
				True if dt == TABLE else frappe.throw("no", frappe.PermissionError)
			)
			with self.assertRaises(frappe.PermissionError):
				data_store.import_table("Sales Invoice")

	# -- the enqueue contract -----------------------------------------------

	def test_queueing_opens_a_log_and_marks_the_row_before_handing_over(self):
		"""Ordering is the contract: a fast worker must never load a row still
		carrying the previous run's state."""
		result, enqueue = self.queue()

		self.assertTrue(result["queued"])
		self.assertEqual(value(TABLE, result["table"], "sync_state"), "Syncing")
		self.assertEqual(value(LOG, result["log"], "status"), "In Progress")
		self.assertEqual(value(LOG, result["log"], "document_type"), DOCTYPE)

		enqueue.assert_called_once()
		kwargs = enqueue.call_args.kwargs
		self.assertEqual(kwargs["table"], result["table"])
		self.assertEqual(kwargs["log"], result["log"])
		# The default 300s kills a wide-doctype copy partway and leaves the log
		# for `expire_stale_imports` to retire.
		self.assertEqual(kwargs["timeout"], 3600)
		self.assertEqual(kwargs["queue"], "long")

	def test_a_second_click_is_told_the_work_is_already_happening(self):
		"""Two concurrent writers of one DuckDB table is a corrupted table, and
		the button that produced the second click wants an answer, not a 500."""
		first, _ = self.queue()
		second, enqueue = self.queue()

		self.assertFalse(second["queued"])
		self.assertEqual(second["reason"], "in_progress")
		self.assertEqual(second["table"], first["table"])
		enqueue.assert_not_called()

	def test_an_open_log_blocks_a_retry_even_once_rq_has_forgotten_the_job(self):
		"""RQ's registry drops a job the moment its worker picks it up, so
		mid-import `is_job_enqueued` is False and only the log knows."""
		first, _ = self.queue()
		with mock.patch.object(data_store, "is_job_enqueued", return_value=False):
			second, enqueue = self.queue()
		self.assertFalse(second["queued"])
		self.assertEqual(second["log"], None)
		self.assertEqual(value(LOG, first["log"], "status"), "In Progress")
		enqueue.assert_not_called()

	# -- the limits ---------------------------------------------------------

	def test_a_per_table_row_limit_overrides_the_site_wide_cap(self):
		"""A number typed into the import dialog is that table's policy."""
		self.set_cap("max_records_to_sync", 900)

		result, enqueue = self.queue(row_limit=17)
		self.assertEqual(enqueue.call_args.kwargs["row_limit"], 17)
		self.assertEqual(value(TABLE, result["table"], "row_limit"), 17)
		self.assertEqual(value(LOG, result["log"], "row_limit"), 17)

	def test_an_unwritten_settings_zero_falls_back_to_the_shipped_default(self):
		"""Both fields are Int, so an untouched Single reads 0 - which as a row
		cap imports nothing and as a memory cap makes DuckDB refuse to start.
		Never trust the stored zero (`nakhoda_settings.py`)."""
		self.set_cap("max_records_to_sync", 0)
		self.set_cap("max_memory_usage", 0)

		_, enqueue = self.queue()
		self.assertEqual(enqueue.call_args.kwargs["row_limit"], data_store.DEFAULT_ROW_LIMIT)
		self.assertEqual(enqueue.call_args.kwargs["memory_limit"], data_store.DEFAULT_MEMORY_MB)

	# -- the worker half ----------------------------------------------------

	def test_a_failed_copy_is_recorded_on_both_the_row_and_the_log(self):
		"""`run_import` never raises to the worker: a traceback is not
		something the Data Store page can render."""
		result, _ = self.queue()
		with mock.patch.object(data_store, "site_db", side_effect=RuntimeError("boom")):
			data_store.run_import(table=result["table"], log=result["log"], row_limit=10, memory_limit=64)

		self.assertEqual(value(TABLE, result["table"], "sync_state"), "Failed")
		self.assertIn("boom", str(value(TABLE, result["table"], "sync_error")))
		self.assertEqual(value(LOG, result["log"], "status"), "Failed")
		self.assertIn("boom", str(value(LOG, result["log"], "output")))

	def test_a_real_import_lands_rows_in_the_warehouse(self):
		"""The one end-to-end pass: MariaDB read, DuckDB write, row committed.

		Capped hard because this is the only test in the file that moves data;
		everything above grades the bookkeeping around it.
		"""
		result, enqueue = self.queue(row_limit=5)
		data_store.run_import(
			**{k: enqueue.call_args.kwargs[k] for k in ("table", "log", "row_limit", "memory_limit")}
		)

		self.assertEqual(value(TABLE, result["table"], "sync_state"), "Synced")
		self.assertEqual(value(TABLE, result["table"], "stored_in_warehouse"), 1)
		self.assertEqual(value(LOG, result["log"], "status"), "Completed")

		row_count = cint(value(TABLE, result["table"], "row_count"))
		self.assertGreater(row_count, 0)
		self.assertLessEqual(row_count, 5)

		from nakhoda.connectors import site_warehouse

		warehouse = site_warehouse(read_only=False)
		self.addCleanup(lambda: warehouse.backend.drop_table(f"tab{DOCTYPE}", force=True))
		self.assertEqual(warehouse.backend.table(f"tab{DOCTYPE}").count().execute(), row_count)

	# -- the scheduled halves -----------------------------------------------

	def test_the_daily_refresh_never_widens_the_warehouse(self):
		"""Only tables somebody explicitly imported are re-synced. A cron that
		pulled in anything else would be materialising data nobody asked for."""
		queued, _ = self.queue()
		# Leave this one un-imported: Syncing, but never stored.
		frappe.db.set_value(TABLE, queued["table"], "sync_state", "Never", update_modified=False)
		frappe.db.delete(LOG, {"name": queued["log"]})

		with mock.patch.object(data_store, "_queue_import") as requeue:
			data_store.sync_stored_tables()
		requeued = {call.args[0].name for call in requeue.call_args_list}
		self.assertNotIn(queued["table"], requeued)

		frappe.db.set_value(TABLE, queued["table"], "stored_in_warehouse", 1, update_modified=False)
		with mock.patch.object(data_store, "_queue_import") as requeue:
			data_store.sync_stored_tables()
		self.assertIn(queued["table"], {call.args[0].name for call in requeue.call_args_list})

	def test_a_dead_worker_does_not_make_a_table_permanently_unimportable(self):
		"""Without the hourly sweep, a killed worker leaves `Syncing` forever
		and `import_table`'s own duplicate guard then refuses every retry."""
		result, _ = self.queue()
		stale = add_to_date(now_datetime(), hours=-(data_store.STALE_IMPORT_HOURS + 1))
		frappe.db.set_value(LOG, result["log"], "started_at", stale, update_modified=False)

		data_store.expire_stale_imports()

		self.assertEqual(value(LOG, result["log"], "status"), "Failed")
		self.assertEqual(value(TABLE, result["table"], "sync_state"), "Failed")

		# And the retry the guard used to refuse now goes through.
		retry, enqueue = self.queue()
		self.assertTrue(retry["queued"])
		enqueue.assert_called_once()

	def test_a_running_import_is_left_alone_by_the_sweep(self):
		"""The cutoff is what separates "slow" from "dead"; a fresh log is
		neither retired nor reported."""
		result, _ = self.queue()
		data_store.expire_stale_imports()
		self.assertEqual(value(LOG, result["log"], "status"), "In Progress")
		self.assertEqual(value(TABLE, result["table"], "sync_state"), "Syncing")

	# -- helpers ------------------------------------------------------------

	def find(self, rows: list[dict], doctype: str) -> dict:
		for row in rows:
			if row["doctype"] == doctype:
				return row
		self.fail(f"{doctype} missing from the Data Store listing")

	def set_store(self, enabled: bool | None) -> None:
		"""Flip `enable_data_store`; `None` deletes the row entirely.

		Restored on cleanup rather than left to rollback: the code under test
		commits, so a test that switched the store off could otherwise leave
		the site it graded with its Data Store disabled.
		"""
		if not getattr(self, "_store_restore_registered", False):
			self._store_restore_registered = True
			self.addCleanup(self.restore_store, self.store_row())
		self.write_store(enabled)

	def restore_store(self, original: str | None) -> None:
		self.write_store(None if original is None else bool(cint(original)))
		frappe.db.commit()

	def write_store(self, enabled: bool | None) -> None:
		if enabled is None:
			frappe.db.delete("Singles", {"doctype": SETTINGS, "field": "enable_data_store"})
		else:
			frappe.db.set_single_value(SETTINGS, "enable_data_store", int(enabled))
		frappe.clear_document_cache(SETTINGS, SETTINGS)

	def forget_caps(self) -> None:
		"""Delete the two cap rows, putting the Single back in the state an
		install that never opened this tab is in.

		Restored on cleanup for the same reason `set_store` is: these tests run
		against a real site, and a cap left at `NULL` would render as `0` on the
		settings page - the exact defect the patch beside them exists to fix.
		"""
		self.remember_caps()
		frappe.db.delete("Singles", {"doctype": SETTINGS, "field": ("in", CAPS)})
		frappe.clear_document_cache(SETTINGS, SETTINGS)

	def set_cap(self, fieldname: str, value: int) -> None:
		"""Write one cap, restoring whatever was there before."""
		self.remember_caps()
		frappe.db.set_single_value(SETTINGS, fieldname, value)
		frappe.clear_document_cache(SETTINGS, SETTINGS)

	def remember_caps(self) -> None:
		"""Snapshot both cap rows once per test, raw: `None` means *no row*,
		which has to be restored as a deletion rather than as a written
		`None` - `set_single_value(..., None)` stores SQL `NULL`, which the
		settings page reads back as `0` and would leave the site claiming a
		zero row cap.
		"""
		if getattr(self, "_caps_restore_registered", False):
			return
		self._caps_restore_registered = True
		self.addCleanup(self.restore_caps, {f: self.cap_row(f) for f in CAPS})

	def restore_caps(self, original: dict[str, str | None]) -> None:
		for fieldname, value in original.items():
			if value is None:
				frappe.db.delete("Singles", {"doctype": SETTINGS, "field": fieldname})
			else:
				frappe.db.set_single_value(SETTINGS, fieldname, value)
		frappe.clear_document_cache(SETTINGS, SETTINGS)
		frappe.db.commit()

	def store_row(self) -> str | None:
		return self.single_row("enable_data_store")

	def cap_row(self, fieldname: str) -> str | None:
		return self.single_row(fieldname)

	def single_row(self, fieldname: str) -> str | None:
		"""The raw `tabSingles` value, or `None` when never written - the
		distinction `get_single_value` erases by casting a missing row to 0.

		Read through the query builder, not `get_all`: `Singles` is a physical
		table with no DocType of its own, so the ORM path throws on it.
		"""
		singles = DocType("Singles")
		rows = (
			frappe.qb.from_(singles)
			.select(singles.value)
			.where((singles.doctype == SETTINGS) & (singles.field == fieldname))
			.run()
		)
		return rows[0][0] if rows else None


if __name__ == "__main__":
	unittest.main()
