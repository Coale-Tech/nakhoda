"""The Data Sources surface: what sources exist, what each one exposes, and
what a preview of one table is allowed to contain.

Two properties carry this module, and neither is provable by reading the
endpoints in isolation:

1. The two `source_type` values answer `list_source_tables` *differently* -
   the site database exposes every readable DocType, the warehouse exposes only
   what somebody deliberately imported. That asymmetry is the whole design
   claim ("a DuckDB table nobody asked for does not exist"), so it is graded
   directly rather than assumed.
2. A preview runs through `engine.pipeline.run` behind `engine.permissions.
   for_user`, the same path every query takes. The test that matters is not
   that a preview returns rows but that a *restricted caller's* preview is
   already filtered - the property that made Insights' second, unfiltered
   accessor (`00-REPORT.md` §6.5) unnecessary here.

Three source types now answer, not two. An **External Database** row is
created from a connection form, so this module also grades what a form may and
may not do: it can add and re-point an external row, and it can never touch
the two rows this app makes for itself (`Site Database`, `DuckDB Warehouse`) -
their credentials come from `site_config.json`, and a form that appeared to
accept them would be writing fields nothing reads. An uploaded CSV is the
third shape of table in the warehouse and takes the upload branch of every
listing and preview endpoint, which is graded end to end at the bottom.
"""

from __future__ import annotations

import unittest
from typing import cast
from unittest import mock

import frappe
from frappe.query_builder import DocType
from frappe.utils import cint

from nakhoda import api
from nakhoda.api import data_sources, data_store, files
from nakhoda.nakhoda.doctype.nakhoda_data_source.nakhoda_data_source import NakhodaDataSource

DOCTYPE = "Currency"

SETTINGS = "Nakhoda Settings"
SOURCE = "Nakhoda Data Source"
TABLE = "Nakhoda Table"
EXTERNAL = "External Database"


def connected() -> bool:
	return bool(getattr(frappe, "db", None))


@unittest.skipUnless(connected(), "needs a site: bench --site <site> run-tests --app nakhoda")
class DataSources(unittest.TestCase):
	def setUp(self) -> None:
		frappe.set_user("Administrator")
		# `default_source()` and `_warehouse_source()` are get-or-create and
		# commit; snapshot so tearDown removes only what this test added.
		self.pre_sources = set(frappe.get_all(SOURCE, pluck="name"))
		self.pre_tables = set(frappe.get_all(TABLE, pluck="name"))
		self.site = api.default_source()

	def tearDown(self) -> None:
		frappe.set_user("Administrator")
		frappe.db.rollback()
		for doctype, pre in ((TABLE, self.pre_tables), (SOURCE, self.pre_sources)):
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

	def stored_table(self, doctype: str = DOCTYPE) -> str:
		"""A `Nakhoda Table` row marked as landed in the warehouse, without
		moving any data - every test here is about listing, not copying."""
		doc = frappe.get_doc(
			{
				"doctype": TABLE,
				"data_source": data_store._warehouse_source(),
				"document_type": doctype,
				"table_name": f"tab{doctype}",
				"sync_state": "Synced",
				"stored_in_warehouse": 1,
				"row_count": 7,
			}
		).insert(ignore_permissions=True)
		frappe.db.commit()
		return str(doc.name)

	def warehouse(self) -> str:
		return data_store._warehouse_source()

	# -- the source list ----------------------------------------------------

	def test_the_site_database_is_listed_and_default(self):
		rows = data_sources.list_data_sources()
		site = next(row for row in rows if row["name"] == self.site)
		self.assertEqual(site["source_type"], "Site Database")
		self.assertTrue(site["is_default"])
		# The default sorts first, so the page never opens on a secondary row.
		self.assertEqual(rows[0]["name"], self.site)

	def test_table_counts_describe_the_right_thing_per_source_type(self):
		"""The site database counts what is readable; the warehouse counts what
		was imported. One number over two very different populations."""
		self.stored_table()
		rows = {row["name"]: row for row in data_sources.list_data_sources()}

		self.assertEqual(rows[self.warehouse()]["table_count"], 1)
		self.assertGreater(rows[self.site]["table_count"], 1)

	def test_get_data_source_returns_the_header_fields(self):
		doc = data_sources.get_data_source(self.site)
		self.assertEqual(doc["name"], self.site)
		self.assertEqual(doc["source_type"], "Site Database")
		self.assertTrue(doc["is_default"])

	# -- what a source exposes ----------------------------------------------

	def test_the_site_database_exposes_every_readable_doctype(self):
		rows = data_sources.list_source_tables(self.site, limit=500)
		self.assertIn(DOCTYPE, {row["doctype"] for row in rows})

	def test_the_warehouse_exposes_only_what_was_imported(self):
		"""The asymmetry that decides the screen: an un-imported DocType is not
		listed as merely un-synced, because in the warehouse it does not exist."""
		before = data_sources.list_source_tables(self.warehouse(), limit=500)
		self.assertEqual(before, [])

		self.stored_table()
		after = data_sources.list_source_tables(self.warehouse(), limit=500)
		self.assertEqual([row["doctype"] for row in after], [DOCTYPE])
		self.assertEqual(after[0]["row_count"], 7)

	def test_source_tables_are_filtered_by_the_callers_permissions(self):
		"""Same endpoint, two callers, and the caller's own roles decide - this
		is `api.query.list_sources`, so there is no second accessor to drift.

		Searched rather than capped: this site exposes over a thousand readable
		DocTypes, so any `limit` small enough to be cheap decides the answer by
		alphabet instead of by permission."""

		def visible() -> set[str]:
			rows = data_sources.list_source_tables(self.site, search_term="Sales Invoice")
			return {row["doctype"] for row in rows}

		self.assertIn("Sales Invoice", visible())

		analyst = self.make_user("nakhoda-source-analyst@example.com", ["Nakhoda User"])
		self.assertFalse(frappe.has_permission("Sales Invoice", "read", user=analyst))
		frappe.set_user(analyst)
		self.assertNotIn("Sales Invoice", visible())

	def test_search_filters_the_table_list(self):
		rows = data_sources.list_source_tables(self.site, search_term=DOCTYPE.lower())
		self.assertTrue(rows)
		self.assertTrue(all(DOCTYPE.lower() in row["label"].lower() for row in rows))

	# -- the preview --------------------------------------------------------

	def test_a_preview_is_bounded_and_says_so(self):
		preview = data_sources.get_source_table(self.site, "Sales Invoice")
		self.assertEqual(preview["table_name"], "tabSales Invoice")
		self.assertLessEqual(preview["row_count"], data_sources.PREVIEW_ROWS)
		self.assertEqual(preview["truncated"], preview["row_count"] >= data_sources.PREVIEW_ROWS)
		self.assertTrue(preview["columns"])
		self.assertEqual(len(preview["rows"]), preview["row_count"])

	def test_a_preview_is_the_callers_own_slice_not_everyones(self):
		"""A viewer's preview runs through `for_user`, so it is row-filtered
		before it is capped - not a redacted view of somebody else's rows."""
		privileged = data_sources.get_source_table(self.site, "Sales Invoice")
		self.assertGreater(privileged["row_count"], 0)

		analyst = self.make_user("nakhoda-preview-analyst@example.com", ["Nakhoda User"])
		frappe.set_user(analyst)
		with self.assertRaises(frappe.PermissionError):
			data_sources.get_source_table(self.site, "Sales Invoice")

	def test_a_preview_of_an_unreadable_table_is_refused_not_emptied(self):
		"""An empty grid and a refusal mean different things to a viewer, and
		only one of them is true."""
		analyst = self.make_user("nakhoda-preview-outsider@example.com", ["Nakhoda User"])
		frappe.set_user(analyst)
		with self.assertRaises(frappe.PermissionError):
			data_sources.get_source_table(self.site, "Sales Invoice")

	# -- write actions ------------------------------------------------------

	def test_setting_a_default_moves_it_off_the_previous_row(self):
		"""Exclusivity lives in `NakhodaDataSource.validate`, so a row saved
		through the Desk cannot produce a second default either."""
		warehouse = self.warehouse()
		data_sources.set_default_data_source(warehouse)

		self.assertEqual(frappe.db.get_value(SOURCE, warehouse, "is_default"), 1)
		self.assertEqual(frappe.db.get_value(SOURCE, self.site, "is_default"), 0)

	def test_a_reader_cannot_reconfigure_a_source(self):
		"""`Nakhoda User` may look at a source, not change which one answers."""
		analyst = self.make_user("nakhoda-source-reader@example.com", ["Nakhoda User"])
		frappe.set_user(analyst)

		self.assertTrue(data_sources.list_data_sources())
		with self.assertRaises(frappe.PermissionError):
			data_sources.set_default_data_source(self.site)
		with self.assertRaises(frappe.PermissionError):
			data_sources.test_data_source(self.site)

	def test_testing_the_site_database_records_reachability_rather_than_raising(self):
		result = data_sources.test_data_source(self.site)
		self.assertEqual(result["status"], "Reachable")
		self.assertEqual(frappe.db.get_value(SOURCE, self.site, "status"), "Reachable")
		self.assertTrue(frappe.db.get_value(SOURCE, self.site, "last_checked"))

	# -- external sources ---------------------------------------------------

	def external(self, title: str = "Test Replica", **overrides) -> str:
		"""An external row on disk, inserted with the save-time probe stubbed.

		`on_update` opens a socket to whatever host the form named
		(`nakhoda_data_source.py:155-173`). There is no second database on this
		workstation, so leaving it live would make every test below grade DNS
		instead of this app - the same reason `test_data_store` patches
		`site_db` rather than copying real tables.
		"""
		payload = {
			"doctype": SOURCE,
			"title": title,
			"source_type": EXTERNAL,
			"database_type": "PostgreSQL",
			"host": "db.invalid",
			"port": 5432,
			"username": "reader",
			"password": "s3cret",
			"database_name": "analytics",
			**overrides,
		}
		with self.no_probe():
			doc = frappe.get_doc(payload)
			doc.insert(ignore_permissions=True)
		frappe.db.commit()
		return str(doc.name)

	def no_probe(self):
		"""Stub the save-time connection probe for one block."""
		return mock.patch.object(NakhodaDataSource, "on_update", lambda self: None)

	def test_a_connection_form_creates_an_external_row(self):
		"""What the New Source dialog does: a payload of form fields in, a row
		in the list out - carrying the type the form was for."""
		with mock.patch.object(NakhodaDataSource, "on_update", lambda self: None):
			created = data_sources.create_data_source(
				{
					"title": "Analytics Replica",
					"source_type": EXTERNAL,
					"database_type": "PostgreSQL",
					"host": "db.invalid",
					"username": "reader",
					"password": "s3cret",
					"database_name": "analytics",
				}
			)

		self.assertEqual(created["source_type"], EXTERNAL)
		self.assertEqual(created["database_type"], "PostgreSQL")
		self.assertFalse(created["is_default"])
		listed = {row["name"]: row for row in data_sources.list_data_sources()}
		self.assertIn(created["name"], listed)
		self.assertEqual(listed[created["name"]]["title"], "Analytics Replica")

	def test_a_form_cannot_mint_a_second_site_or_warehouse_row(self):
		"""Two rows claiming the site's own data is not a configuration - it is
		a question the resolver cannot answer, so `before_insert` refuses."""
		for source_type in ("Site Database", "DuckDB Warehouse"):
			with self.assertRaises(frappe.ValidationError):
				data_sources.create_data_source({"title": "Shadow", "source_type": source_type})

	def test_an_external_row_without_credentials_is_refused(self):
		"""The form's own required-field check is a convenience; the document
		is where it is true. A half-filled row would fail later, on a query
		somebody else ran."""
		with self.assertRaises(frappe.ValidationError):
			data_sources.create_data_source(
				{
					"title": "Half",
					"source_type": EXTERNAL,
					"database_type": "PostgreSQL",
					"host": "db.invalid",
				}
			)

	def test_a_database_type_this_deployment_cannot_open_is_refused(self):
		"""`connectors.BACKENDS` is what can actually be opened here; offering
		BigQuery in a Select would mean an ImportError at connect time."""
		with self.assertRaises(frappe.ValidationError):
			data_sources.create_data_source(
				{
					"title": "Warehouse Cloud",
					"source_type": EXTERNAL,
					"database_type": "BigQuery",
					"database_name": "analytics",
				}
			)

	def test_re_pointing_an_external_row_rewrites_only_connection_fields(self):
		name = self.external()
		with self.no_probe():
			data_sources.update_data_source(name, {"host": "other.invalid"})

		doc = cast(NakhodaDataSource, frappe.get_doc(SOURCE, name))
		self.assertEqual(doc.host, "other.invalid")
		self.assertEqual(doc.database_name, "analytics")
		# The credential it did not carry is untouched, not blanked: a form
		# that omits `password` is not asking for the password to be cleared.
		self.assertEqual(doc.get_password("password"), "s3cret")

	def test_renaming_a_source_moves_the_row_rather_than_leaving_two_names(self):
		"""`autoname: field:title`, so the label the list shows *is* the key
		every saved query stores. A title written as a plain column would leave
		the two disagreeing."""
		name = self.external()
		table = self.stored_table()
		frappe.db.set_value(TABLE, table, "data_source", name, update_modified=False)

		with self.no_probe():
			renamed = data_sources.update_data_source(name, {"title": "Renamed Replica"})

		self.assertEqual(renamed["name"], "Renamed Replica")
		self.assertFalse(frappe.db.exists(SOURCE, name))
		# The Link that named the old row came with it.
		self.assertEqual(frappe.db.get_value(TABLE, table, "data_source"), "Renamed Replica")

	def test_the_site_and_warehouse_rows_refuse_a_connection_form(self):
		"""Their credentials come from `site_config.json`. A form that appeared
		to accept them would be writing fields nothing reads."""
		for name in (self.site, self.warehouse()):
			with self.assertRaises(frappe.ValidationError):
				data_sources.update_data_source(name, {"host": "elsewhere.invalid"})

	def test_a_built_in_row_never_keeps_credentials(self):
		"""Clearing rather than ignoring: a host and password on a row whose
		connection comes from `site_config.json` are fields nothing reads and a
		credential waiting for a later reader."""
		doc = cast(NakhodaDataSource, frappe.get_doc(SOURCE, self.site))
		doc.database_type = "PostgreSQL"
		doc.host = "left.invalid"
		doc.password = "s3cret"
		with self.no_probe():
			doc.save(ignore_permissions=True)

		doc.reload()
		self.assertIsNone(doc.host)
		self.assertIsNone(doc.database_type)
		self.assertFalse(doc.get_password("password", raise_exception=False))

	def test_an_external_row_can_be_deleted_and_the_built_ins_cannot(self):
		name = self.external()
		data_sources.delete_data_source(name)
		self.assertFalse(frappe.db.exists(SOURCE, name))

		for built_in in (self.site, self.warehouse()):
			with self.assertRaises(frappe.ValidationError):
				data_sources.delete_data_source(built_in)
			self.assertTrue(frappe.db.exists(SOURCE, built_in))

	def test_probing_an_unsaved_form_writes_nothing(self):
		"""The Test button on a form that has never been saved. Insights has
		the same endpoint because the alternative - save, then test - leaves a
		broken row behind on every typo."""
		before = set(frappe.get_all(SOURCE, pluck="name"))
		result = data_sources.test_connection(
			{
				"title": "Nowhere",
				"source_type": EXTERNAL,
				"database_type": "PostgreSQL",
				"host": "127.0.0.1",
				"port": 1,
				"username": "reader",
				"password": "pw",
				"database_name": "analytics",
			}
		)

		self.assertEqual(result["status"], "Unreachable")
		self.assertTrue(result["message"])
		self.assertEqual(set(frappe.get_all(SOURCE, pluck="name")), before)

	def test_probing_an_edit_reuses_the_password_the_browser_never_got(self):
		"""The edit form's Connect button. `get_data_source` withholds the
		stored password, so a probe that only ever used what the form carried
		could not succeed on a row the user is not re-authenticating."""
		name = self.external()
		seen = {}

		def spy(self):
			seen["password"] = self.password
			return []

		with mock.patch.object(NakhodaDataSource, "table_list", spy):
			result = data_sources.test_connection(
				{
					"name": name,
					"title": "Test Replica",
					"source_type": EXTERNAL,
					"database_type": "PostgreSQL",
					"host": "moved.invalid",
					"username": "reader",
					"database_name": "analytics",
				}
			)

		self.assertEqual(result["status"], "Reachable")
		self.assertEqual(seen["password"], "s3cret")

	def test_the_edit_form_gets_the_connection_but_never_the_password(self):
		"""What `get_data_source` hands the browser: enough to re-point a port
		without retyping a host, and no credential that could be read out of a
		response somebody else's tab also received."""
		header = data_sources.get_data_source(self.external())

		self.assertEqual(header["host"], "db.invalid")
		self.assertEqual(header["username"], "reader")
		self.assertEqual(header["database_name"], "analytics")
		self.assertNotIn("password", header)

		# The built-in rows have no connection to hand back at all.
		self.assertNotIn("host", data_sources.get_data_source(self.site))

	def test_a_reader_cannot_add_re_point_or_remove_a_source(self):
		"""`Nakhoda User` reads the list; only the two admin roles write it."""
		name = self.external()
		analyst = self.make_user("nakhoda-source-writer@example.com", ["Nakhoda User"])
		frappe.set_user(analyst)

		with self.assertRaises(frappe.PermissionError):
			data_sources.create_data_source({"title": "Theirs", "source_type": EXTERNAL})
		with self.assertRaises(frappe.PermissionError):
			data_sources.test_connection({"title": "Theirs", "source_type": EXTERNAL})
		with self.assertRaises(frappe.PermissionError):
			data_sources.update_data_source(name, {"host": "theirs.invalid"})
		with self.assertRaises(frappe.PermissionError):
			data_sources.delete_data_source(name)

	def test_only_frappe_shaped_sources_claim_to_know_their_joins(self):
		"""Link fields are Frappe's own metadata. A foreign schema's
		relationships are not described anywhere this app can read, and a
		guessed join silently changes counts."""
		self.assertTrue(data_sources.get_table_links(self.site))

		name = self.external()
		self.assertEqual(data_sources.get_table_links(name), [])
		self.assertEqual(data_sources.get_table_links(self.warehouse()), [])

	# -- uploaded files -----------------------------------------------------

	def upload(self, body: str = "name,city\nAcme,Nairobi\nGlobex,Mombasa\n") -> str:
		"""A private `File` row holding a CSV, as `FileUploader` would leave."""
		doc = frappe.get_doc(
			{
				"doctype": "File",
				"file_name": "customers.csv",
				"is_private": 1,
				"content": body,
			}
		).insert(ignore_permissions=True)
		self.addCleanup(lambda: frappe.delete_doc("File", doc.name, force=True, ignore_permissions=True))
		frappe.db.commit()
		return str(doc.name)

	def test_a_preview_of_an_uploaded_file_writes_nothing(self):
		"""The two-step flow's whole point: a misread delimiter is visible
		before the warehouse has been touched."""
		file = self.upload()
		before = set(frappe.get_all(TABLE, pluck="name"))

		preview = files.get_upload_preview(file)
		self.assertEqual(preview["table"], "upload_customers")
		self.assertEqual([c["column"] for c in preview["columns"]], ["name", "city"])
		self.assertEqual(preview["row_count"], 2)
		self.assertEqual(set(frappe.get_all(TABLE, pluck="name")), before)

	def test_an_uploaded_file_becomes_a_queryable_warehouse_table(self):
		"""End to end: DuckDB write, `Nakhoda Table` row, and both the listing
		and the preview taking the upload branch rather than the DocType one."""
		from nakhoda.connectors import site_warehouse

		self.set_store(True)
		file = self.upload()
		result = files.import_upload(file)
		self.addCleanup(
			lambda: site_warehouse(read_only=False).backend.drop_table(result["table"], force=True)
		)

		self.assertEqual(result["table"], "upload_customers")
		self.assertEqual(result["row_count"], 2)
		self.assertEqual(site_warehouse().backend.table(result["table"]).count().execute(), 2)

		# The row has no `document_type` - that absence is what marks it as an
		# upload for `tracked_tables` and the daily sweep.
		row = frappe.get_all(
			TABLE,
			filters={"table_name": result["table"]},
			fields=["name", "document_type", "stored_in_warehouse", "row_count"],
		)[0]
		self.assertFalse(row["document_type"])
		self.assertEqual(row["stored_in_warehouse"], 1)

		listed = data_sources.list_source_tables(self.warehouse(), limit=500)
		upload = next(r for r in listed if r["table"] == result["table"])
		self.assertIsNone(upload["doctype"])
		self.assertEqual(upload["row_count"], 2)
		self.assertEqual(upload["label"], "customers")

		preview = data_sources.get_source_table(self.warehouse(), result["table"])
		self.assertEqual(preview["columns"], ["name", "city"])
		self.assertEqual(preview["row_count"], 2)
		self.assertEqual({r["city"] for r in preview["rows"]}, {"Nairobi", "Mombasa"})

	def test_an_upload_is_refused_while_the_data_store_is_off(self):
		"""The same gate `import_table` reads. Off means no new copies, and the
		refusal names the setting rather than failing silently."""
		file = self.upload()
		self.set_store(False)

		with self.assertRaises(frappe.ValidationError):
			files.import_upload(file)
		self.assertFalse(frappe.db.exists(TABLE, {"table_name": "upload_customers"}))

	def set_store(self, enabled: bool) -> None:
		"""Flip `enable_data_store`, putting the site's own value back after.

		Written through `tabSingles` and followed by a cache clear, because
		`setting_enabled` reads the cached Single. Restored on cleanup with a
		commit rather than left to rollback, because the code under test commits
		- a test that switched the store off would otherwise leave the site it
		graded with its Data Store disabled. *Never written* is restored as a
		deletion, not as a zero: absence is what `setting_enabled` reads as on.
		"""
		singles = DocType("Singles")
		rows = (
			frappe.qb.from_(singles)
			.select(singles.value)
			.where((singles.doctype == SETTINGS) & (singles.field == "enable_data_store"))
			.run()
		)
		self.addCleanup(self.write_store, rows[0][0] if rows else None)
		self.write_store(int(enabled))

	def write_store(self, value: str | int | None) -> None:
		if value is None:
			frappe.db.delete("Singles", {"doctype": SETTINGS, "field": "enable_data_store"})
		else:
			frappe.db.set_single_value(SETTINGS, "enable_data_store", cint(value))
		frappe.clear_document_cache(SETTINGS, SETTINGS)
		frappe.db.commit()

	def test_a_reader_cannot_import_a_file(self):
		"""Importing materialises rows into a shared warehouse - the same
		`Nakhoda Table` create permission `data_store.import_table` requires.

		The store is switched on first so this grades the permission rather
		than the gate ahead of it."""
		self.set_store(True)
		file = self.upload()
		analyst = self.make_user("nakhoda-upload-reader@example.com", ["Nakhoda User"])
		frappe.set_user(analyst)

		with self.assertRaises(frappe.PermissionError):
			files.import_upload(file)

	# -- the shape of the surface -------------------------------------------

	def test_the_whitelisted_surface_is_exactly_what_the_pages_call(self):
		"""Every endpoint reachable over HTTP is one a screen drives. The list
		is pinned because adding to it is how an app grows a second, less
		careful accessor - the fork that produced Insights' issue #919."""

		# `@frappe.whitelist()` records the function in `frappe.whitelisted`
		# (a set), it does not tag it - so the registry is the only honest
		# reading of "reachable over HTTP". Restricted to what this module
		# *defines*: it imports `api.query.list_sources`, which is whitelisted
		# where it is written and would otherwise be counted twice.
		def exposed(module) -> set[str]:
			return {
				name
				for name, fn in vars(module).items()
				if callable(fn)
				and fn in frappe.whitelisted
				and getattr(fn, "__module__", "") == module.__name__
			}

		self.assertEqual(
			exposed(data_sources),
			{
				"list_data_sources",
				"get_data_source",
				"test_data_source",
				"test_connection",
				"create_data_source",
				"update_data_source",
				"delete_data_source",
				"set_default_data_source",
				"list_source_tables",
				"refresh_source_tables",
				"get_source_table",
				"get_source_table_columns",
				"get_source_table_row_count",
				"get_table_links",
				"update_table_links",
			},
		)
		# Uploads expose the two steps the dialog drives and nothing else:
		# `uploaded_tables` and `_materialise` are called by other server code
		# and would be a second, unpermissioned way in.
		self.assertEqual(exposed(files), {"get_upload_preview", "import_upload"})

		options = frappe.get_meta(SOURCE).get_options("source_type").split("\n")
		self.assertEqual([o for o in options if o], ["Site Database", "DuckDB Warehouse", EXTERNAL])


if __name__ == "__main__":
	unittest.main()
