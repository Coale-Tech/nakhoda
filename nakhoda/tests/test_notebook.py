# Copyright (c) 2026, Nakhoda and contributors
# For license information, please see license.txt
"""Phase 7's bare-interpreter half: `notebook_worker.run_cell_in_namespace` -
the exact function that runs inside the container - is pure and Docker-free,
so its behaviour is provable without either. What genuinely needs Docker
(the process boundary, the §2.3 exploit probe) lives in `test_notebook_live.py`.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from nakhoda.engine.notebook import _docker_available
from nakhoda.engine.notebook_worker import run_cell_in_namespace


class RunCellInNamespace(unittest.TestCase):
	def test_a_bare_trailing_expression_is_reported_as_result(self):
		out = run_cell_in_namespace("15 + 27", {})
		self.assertEqual(out["result"], "42")
		self.assertIsNone(out["error"])

	def test_a_cell_with_no_trailing_expression_has_no_result(self):
		out = run_cell_in_namespace("x = 1", {})
		self.assertIsNone(out["result"])

	def test_a_trailing_expression_that_is_none_reports_no_result(self):
		out = run_cell_in_namespace("print('hi')", {})
		self.assertIsNone(out["result"])
		self.assertEqual(out["stdout"], "hi\n")

	def test_state_persists_across_calls_sharing_a_namespace(self):
		namespace: dict = {}
		run_cell_in_namespace("x = 21", namespace)
		out = run_cell_in_namespace("x * 2", namespace)
		self.assertEqual(out["result"], "42")

	def test_a_namespace_not_shared_starts_fresh(self):
		run_cell_in_namespace("x = 21", {})
		out = run_cell_in_namespace("x * 2", {})
		self.assertIn("NameError", out["error"])

	def test_stdout_is_captured_not_leaked_to_the_real_stream(self):
		out = run_cell_in_namespace("print('captured')", {})
		self.assertEqual(out["stdout"], "captured\n")

	def test_an_exception_is_reported_not_raised(self):
		out = run_cell_in_namespace("1 / 0", {})
		self.assertIsNone(out["result"])
		self.assertIn("ZeroDivisionError", out["error"])

	def test_a_syntax_error_is_reported_not_raised(self):
		out = run_cell_in_namespace("def (", {})
		self.assertIn("SyntaxError", out["error"])

	def test_one_bad_cell_does_not_poison_the_namespace_for_the_next(self):
		namespace: dict = {}
		run_cell_in_namespace("x = 1", namespace)
		run_cell_in_namespace("1 / 0", namespace)
		out = run_cell_in_namespace("x", namespace)
		self.assertEqual(out["result"], "1")

	def test_statements_before_a_trailing_expression_still_run(self):
		out = run_cell_in_namespace("y = 10\ny + 5", {})
		self.assertEqual(out["result"], "15")

	def test_a_real_scientific_import_works_unrestricted(self):
		# No RestrictedPython, no shim - the boundary is the container, not
		# the language (`00-REPORT.md` §6.3). This module is deliberately
		# permissive; only `engine/notebook.py`'s Docker isolation is the
		# security property.
		out = run_cell_in_namespace("import json\njson.dumps({'a': 1})", {})
		self.assertEqual(out["result"], "'{\"a\": 1}'")
		self.assertIsNone(out["error"])


class DockerAvailability(unittest.TestCase):
	def test_reports_unavailable_when_the_docker_binary_is_missing(self):
		with patch("nakhoda.engine.notebook.shutil.which", return_value=None):
			self.assertFalse(_docker_available())

	def test_reports_unavailable_when_the_daemon_does_not_respond(self):
		with (
			patch("nakhoda.engine.notebook.shutil.which", return_value="/usr/bin/docker"),
			patch("nakhoda.engine.notebook.subprocess.run", side_effect=OSError("no daemon")),
		):
			self.assertFalse(_docker_available())


if __name__ == "__main__":
	unittest.main()
