"""Gate A - the generator reproduces the semantic layer that was measured at 95.8%.

The research measured a text file, not this code. Without this test the 17.5-point
lift belongs to an artifact in a folder and the shipped generator merely resembles
it. So: feed the same eight DocTypes, from the same JSON the harness read, through
the module, and require the output to match `semantic_bench/context_b.txt` line for
line - with two allowed divergences, asserted explicitly rather than tolerated.

Needs no site and no database: `describe()` reads anything that answers `.get()`,
which is the whole reason it was written that way.
"""

from __future__ import annotations

import difflib
import glob
import json
import os
import unittest
from pathlib import Path

from nakhoda.semantic.model import HAS_COLUMN, describe, render

HERE = Path(__file__).resolve().parent
ARTIFACT = HERE / "semantic_bench" / "context_b.txt"

# The artifact was derived from this exact tree. DocTypes change between releases -
# v15 alone moves 22 fields on these eight - so a byte comparison against a
# different version measures the release, not the generator. Pinned rather than
# vendored: copying ERPNext's DocType JSON in here would be GPL source entering an
# AGPL tree, which is the thing invariant 11 exists to stop. The gate borrows the
# tree, it does not own it.
ARTIFACT_ERPNEXT = "16.29.0"

# The eight the benchmark used: two masters, a submittable transaction and its child,
# two tree dimensions, a second transaction type, and a lookup. Enough shapes that a
# generator cannot pass by handling only the easy one.
DOCTYPES = [
	"Customer",
	"Sales Invoice",
	"Sales Invoice Item",
	"Item",
	"Item Group",
	"Territory",
	"Payment Entry",
	"Sales Person",
]

# Two fields the artifact published that have no column: `image_view` (an `Image`
# field on Sales Invoice Item - a widget that re-renders the `image` column, and
# Frappe excludes `Image` from `data_fieldtypes`) and `last_scanned_warehouse` (a
# `Data` field on Purchase Receipt with `is_virtual: 1` - computed on read, never
# written, so `SELECT` cannot name it either). The measured 95.8% was scored
# against a schema advertising two columns that did not exist. The generator
# drops both. This is the only pair of lines the diff is allowed to carry, and
# the test fails if it ever differs by another.
KNOWN_ARTIFACT_DEFECTS = frozenset({"  image_view  VARCHAR", "  last_scanned_warehouse  VARCHAR"})


def erpnext_root() -> Path | None:
	"""The ERPNext the artifact came from, if this machine has it.

	Explicit env var first, then any sibling bench at the right version. Returns
	None rather than guessing: a near-miss version silently rewrites the gate into
	a release-notes diff.
	"""
	if env := os.environ.get("SEMANTIC_BENCH_ERPNEXT"):
		return Path(env)
	benches = HERE.parents[4]
	for candidate in sorted(benches.glob("*/apps/erpnext")):
		init = candidate / "erpnext" / "__init__.py"
		if init.exists() and f'"{ARTIFACT_ERPNEXT}"' in init.read_text():
			return candidate
	return None


def load_doctype_json(root: Path, name: str) -> dict:
	"""The DocType as the harness read it - off disk, no site."""
	slug = name.lower().replace(" ", "_")
	hits = glob.glob(f"{root}/**/doctype/{slug}/{slug}.json", recursive=True)
	if not hits:
		raise FileNotFoundError(f"{name} not under {root}")
	return json.loads(Path(hits[0]).read_text())


class GateA(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		root = erpnext_root()
		if root is None:
			# On a machine without the pinned tree there is nothing to compare
			# against. In CI there is no such excuse - the workflow checks out
			# erpnext at the tag, so absence there means the gate was disarmed.
			missing = f"no ERPNext {ARTIFACT_ERPNEXT} checkout; set SEMANTIC_BENCH_ERPNEXT"
			if os.environ.get("CI"):
				raise AssertionError(f"CI ran with {missing}")
			raise unittest.SkipTest(missing)
		cls.metas = [load_doctype_json(root, d) for d in DOCTYPES]
		cls.generated = render([describe(m) for m in cls.metas])
		cls.artifact = ARTIFACT.read_text()

	def test_matches_the_measured_artifact(self):
		expected = [ln for ln in self.artifact.splitlines() if ln not in KNOWN_ARTIFACT_DEFECTS]
		actual = self.generated.splitlines()
		if expected != actual:
			diff = difflib.unified_diff(expected, actual, "measured", "generated", lineterm="", n=1)
			self.fail("the generator no longer reproduces the measured layer:\n" + "\n".join(diff))

	def test_drops_the_phantom_column(self):
		"""The two divergences, each asserted as a fix rather than accepted as drift."""
		for defect in KNOWN_ARTIFACT_DEFECTS:
			self.assertIn(defect, self.artifact, "artifact changed; re-check the defect")
		self.assertNotIn("image_view", self.generated)
		self.assertNotIn("last_scanned_warehouse", self.generated)
		self.assertNotIn("Image", HAS_COLUMN, "frappe now says Image has a column")

	def test_conventions_survive(self):
		"""The six framework rules carry most of the lift. Losing them is silent."""
		for rule in ("docstatus", "parenttype", "base_", "NO database foreign keys"):
			self.assertIn(rule, self.generated, f"the {rule} convention went missing")

	def test_child_and_submittable_are_marked(self):
		by_doctype = {m["name"]: describe(m) for m in self.metas}
		self.assertEqual(by_doctype["Sales Invoice Item"]["flags"], ["CHILD"])
		self.assertEqual(by_doctype["Sales Invoice"]["flags"], ["SUBMITTABLE"])
		self.assertIn("TREE", by_doctype["Item Group"]["flags"])

		child = {c["name"] for c in by_doctype["Sales Invoice Item"]["columns"]}
		self.assertLessEqual({"parent", "parenttype"}, child, "a child row cannot reach its parent")
		self.assertNotIn("docstatus", child, "child tables carry no docstatus of their own")

	def test_links_name_their_target(self):
		"""The line that replaces a foreign key. Without it every join is a guess."""
		customer = next(m for m in self.metas if m["name"] == "Customer")
		territory = next(c for c in describe(customer)["columns"] if c["name"] == "territory")
		self.assertIn('-> "tabTerritory".name', territory["notes"])


if __name__ == "__main__":
	unittest.main()
