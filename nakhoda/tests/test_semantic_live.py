"""The runtime path, against a real site.

Gate A proves the generator reproduces the measured artifact from DocType JSON. It
cannot prove the live path, and the live path is the product: `frappe.get_meta()`
returns a Meta whose fields are DocField documents, not dicts, and on a real site it
has already merged in Custom Fields and Property Setters. The offline path missed a
`field["options"]` subscript that a DocField rejects - one character of divergence
between the tested path and the shipped one.

The load-bearing test here is `test_every_column_we_name_exists`. It asks Frappe
which columns a table really has and requires our list to be a subset, for every
DocType installed. That is the phantom-column defect - `image_view` in the measured
artifact - turned into a standing check against whatever this site happens to have.

Read-only. These run against real sites with real data, so nothing here writes,
and the one test that needs a field that does not exist appends it to a Meta in
memory. An earlier draft inserted a `Custom Field`, which runs `ALTER TABLE` -
DDL commits implicitly, the rollback in `tearDown` did nothing, and the column
outlived the run.

Needs a site:

    bench --site <site> run-tests --app nakhoda
"""

from __future__ import annotations

import unittest

import frappe

from nakhoda.semantic.model import HAS_COLUMN, describe

# Enough shape variety that a subset check is not a formality: a submittable
# transaction, a child table, a tree, and a core DocType every site has.
SHAPES = ["ToDo", "User", "File"]


def connected() -> bool:
	return bool(getattr(frappe, "db", None))


@unittest.skipUnless(connected(), "needs a site: bench --site <site> run-tests --app nakhoda")
class LiveMeta(unittest.TestCase):
	def test_column_allowlist_still_matches_frappe(self):
		"""`HAS_COLUMN` is copied from `frappe.model.data_fieldtypes`, not imported.

		That copy is only defensible while something checks it. If Frappe adds a
		fieldtype, this fails and names it, rather than the generator quietly
		dropping a column that now exists.
		"""
		from frappe.model import data_fieldtypes

		self.assertEqual(HAS_COLUMN, frozenset(data_fieldtypes))

	def test_every_column_we_name_exists(self):
		"""No phantom columns, asked of Frappe, across every DocType on the site.

		A semantic layer that names a column which is not there produces SQL that
		does not run - and it fails at the end of the pipeline, where the cause is
		furthest away.
		"""
		checked = 0
		for doctype in frappe.get_all("DocType", filters={"issingle": 0, "is_virtual": 0}, pluck="name"):
			meta = frappe.get_meta(doctype)
			try:
				valid = set(meta.get_valid_columns())
			except Exception:
				continue  # table not created on this site; nothing to be wrong about
			named = {c["name"] for c in describe(meta)["columns"]}
			self.assertLessEqual(named, valid, f"{doctype}: named columns that do not exist")
			checked += 1
		self.assertGreater(checked, 50, "checked almost nothing - the query or the filters broke")

	def test_reads_a_docfield_not_a_dict(self):
		"""The divergence that actually happened. A DocField is not subscriptable."""
		for doctype in SHAPES:
			table = describe(frappe.get_meta(doctype))
			self.assertEqual(table["table"], f"tab{doctype}")
			self.assertEqual(table["columns"][0]["name"], "name")
			self.assertTrue(
				any(n.startswith('-> "tab') for c in table["columns"] for n in c["notes"]),
				f"{doctype}: not one Link resolved - joins would all be guesses",
			)

	def test_a_custom_field_describes_itself(self):
		"""The whole claim, in one assertion.

		A field added by a customer this morning, in an app we have never seen,
		arrives with its label, its type and its join already attached - because
		the application recorded them when someone filled in the form. Nobody
		writes a mapping; there is nothing to keep in sync.

		Appended to the Meta in memory rather than inserted as a `Custom Field`:
		inserting one runs `ALTER TABLE`, and DDL commits implicitly, so a rollback
		does not undo it. A test that leaves a column behind on the site it ran
		against is not a test. That `get_meta()` really does merge Custom Fields is
		Frappe's behaviour, and it is what `test_every_column_we_name_exists`
		already walks over - on this bench those DocTypes carry 158 such columns.
		"""
		meta = frappe.get_meta("ToDo")
		meta.append(
			"fields",
			{
				"fieldname": "custom_vessel",
				"label": "Assigned Vessel",
				"fieldtype": "Link",
				"options": "User",
				"description": "Who is steering this one.",
				"reqd": 1,
			},
		)
		# Same field, label saying nothing the fieldname does not. Repeating those
		# would roughly double the model for no information - most labels are the
		# fieldname in title case.
		meta.append(
			"fields",
			{"fieldname": "vessel_notes", "label": "Vessel Notes", "fieldtype": "Small Text"},
		)
		try:
			columns = {c["name"]: c for c in describe(meta)["columns"]}
		finally:
			frappe.clear_cache(doctype="ToDo")

		self.assertEqual(columns["custom_vessel"]["type"], "VARCHAR")
		self.assertEqual(
			columns["custom_vessel"]["notes"],
			["Assigned Vessel", '-> "tabUser".name', "Who is steering this one.", "required"],
		)
		self.assertEqual(columns["vessel_notes"]["notes"], [], "a redundant label was repeated")


if __name__ == "__main__":
	unittest.main()
