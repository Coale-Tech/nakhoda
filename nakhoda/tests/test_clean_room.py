"""Invariant 11's gate, plus proof that the gate is not vacuous.

A clean-room check that always passes is worse than none: it converts an unproven
claim into a green tick. So two of these three tests exist to attack the gate rather
than the tree - one feeds it a file that *is* copied and demands a failure, the other
feeds it original work and demands silence.

Needs no site and no database. Run it anywhere:

    python -m unittest nakhoda.tests.test_clean_room -v
"""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from pathlib import Path

from nakhoda.tests.clean_room import check, discover_roots

APP = Path(__file__).resolve().parents[2]


class CleanRoom(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.roots = [r for r in discover_roots() if r != APP]
		if not cls.roots:
			# On a contributor's laptop with no Insights checkout there is nothing to
			# compare against, and skipping is honest. In CI there is no such excuse:
			# the workflow checks out frappe/insights and sets the roots explicitly,
			# so an empty corpus there means the gate was silently disarmed.
			msg = "no copyleft corpus; set NAKHODA_COPYLEFT_ROOTS"
			if os.environ.get("CI"):
				raise AssertionError(f"CI ran with {msg}")
			raise unittest.SkipTest(msg)

	def test_no_copied_window_in_tree(self):
		"""The gate itself. Every window in nakhoda/ is ours."""
		_, hits, windows = check(APP, self.roots)
		self.assertGreater(windows, 0, "checked nothing - walk() or the filters are broken")
		self.assertEqual(
			hits,
			[],
			"\n".join(f"  {r}:{ln} <- {s}:{sl}" for r, ln, s, sl in hits[:20]),
		)

	def test_detects_a_copied_file(self):
		"""Feed it a real copied file. Silence here would mean the gate is decorative."""
		big = [p for p in (self.roots[0] / "insights").rglob("*.py") if p.stat().st_size > 4000]
		if not big:
			self.skipTest("no Insights source large enough to shingle")
		source = max(big, key=lambda p: p.stat().st_size)

		with tempfile.TemporaryDirectory() as tmp:
			shutil.copy(source, Path(tmp) / "stolen.py")
			_, hits, _ = check(Path(tmp), self.roots)

		self.assertTrue(hits, f"copied {source.name} verbatim and the gate stayed quiet")
		self.assertEqual(hits[0][0], "stolen.py")

	def test_original_work_passes(self):
		"""Frappe idioms are not copying. A file that only *looks* like the ecosystem
		must not trip the gate, or the first real hit gets ignored as noise."""
		original = """
import frappe

def build_semantic_model(doctype: str) -> dict:
	meta = frappe.get_meta(doctype)
	fields = {}
	for df in meta.fields:
		if df.fieldtype in ("Section Break", "Column Break", "Tab Break"):
			continue
		fields[df.fieldname] = {
			"label": df.label,
			"type": df.fieldtype,
			"target": df.options if df.fieldtype == "Link" else None,
			"required": bool(df.reqd),
		}
	return {"table": f"tab{doctype}", "grain": "child" if meta.istable else "document",
		"submittable": bool(meta.is_submittable), "fields": fields}
"""
		with tempfile.TemporaryDirectory() as tmp:
			(Path(tmp) / "original.py").write_text(original)
			_, hits, windows = check(Path(tmp), self.roots)

		self.assertGreater(windows, 0, "the sample produced no windows to test with")
		self.assertEqual(hits, [], "flagged original work - the filters are too loose")


if __name__ == "__main__":
	unittest.main()
