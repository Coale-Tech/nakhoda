# Copyright (c) 2026, Nakhoda and contributors
# For license information, please see license.txt
"""Phase 7 against a real container runtime: `NotebookKernel` (needs only
Docker) and `api.notebooks.run_cells` (needs Docker and a site).

`KernelSandbox` is the gate `12-build-plan.md` names for this phase: "the
§2.3 exploit - reading an arbitrary file off disk via an unguarded
`pandas.read_csv` - is attempted against the kernel and fails." It plants a
secret on the host filesystem and proves the sandboxed kernel cannot reach
it, then does the same for outbound network and for the local-file-write
half of the same vulnerability class (`00-REPORT.md` §2.3's table). This
class needs no Frappe site and is the one wired into CI - the property it
proves does not depend on ERPNext being installed anywhere.

`NotebookAPI` additionally needs a real bench (`bench --site <site>
run-tests --app nakhoda`) because it goes through the whitelisted endpoint
and its audit log, like `test_dashboard_live.py` and `test_verified_query.py`
before it - not wired into CI for the same reason those aren't.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nakhoda.engine.notebook import (
	NotebookCellTimeout,
	NotebookError,
	NotebookKernel,
	NotebookUnavailable,
	_docker_available,
	ensure_image_built,
)


def connected() -> bool:
	try:
		import frappe
	except ImportError:
		return False
	return bool(getattr(frappe, "db", None))


@unittest.skipUnless(_docker_available(), "needs docker: the daemon must be installed and running")
class KernelSandbox(unittest.TestCase):
	@classmethod
	def setUpClass(cls) -> None:
		ensure_image_built()

	# -- Phase 7's gate: the §2.3 exploit fails ------------------------------

	def test_reading_an_arbitrary_host_file_fails(self):
		"""The exact shape of Insights' bypassable shim (`00-REPORT.md` §2.3):
		`pandas.read_csv('<a real path>')` against a file the kernel was never
		given - not filtered, unreachable, because no bind mount exists."""
		with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
			f.write("secret\ntop-secret-value\n")
			canary = f.name
		try:
			with NotebookKernel() as kernel:
				result = kernel.run_cell(f"import pandas as pd\npd.read_csv({canary!r})")
			self.assertIsNotNone(result.error)
			self.assertNotIn("top-secret-value", result.stdout)
			self.assertNotIn("top-secret-value", result.error or "")
		finally:
			Path(canary).unlink(missing_ok=True)

	def test_writing_to_an_arbitrary_host_path_fails(self):
		"""§2.3's second finding: `read_csv(...).to_csv('/tmp/_pwn.csv')` ran
		against Insights' shim and created a file. Prove the write side too,
		not only the read side - a `--read-only` root filesystem some
		notebook code will not think to check for."""
		with tempfile.TemporaryDirectory() as tmp:
			target = str(Path(tmp) / "pwned.csv")
			with NotebookKernel() as kernel:
				result = kernel.run_cell(
					"import pandas as pd\npd.DataFrame({'a': [1]}).to_csv(" + repr(target) + ")\n'wrote'"
				)
			self.assertFalse(Path(target).exists())
			self.assertIsNotNone(result.error)

	def test_outbound_network_fails(self):
		with NotebookKernel() as kernel:
			result = kernel.run_cell(
				"import urllib.request\nurllib.request.urlopen('http://example.com', timeout=3).read()"
			)
		self.assertIsNotNone(result.error)

	# -- The kernel still has to work for it to matter -----------------------

	def test_state_persists_across_cells_in_one_kernel(self):
		with NotebookKernel() as kernel:
			kernel.run_cell("x = 21")
			result = kernel.run_cell("x * 2")
		self.assertEqual(result.result, "42")

	def test_two_kernels_do_not_share_state(self):
		with NotebookKernel() as a, NotebookKernel() as b:
			a.run_cell("secret = 'only in a'")
			result = b.run_cell("secret")
		self.assertIsNotNone(result.error)
		self.assertIn("NameError", result.error or "")

	def test_the_real_scientific_stack_is_available(self):
		with NotebookKernel() as kernel:
			result = kernel.run_cell("import numpy as np, pandas as pd, sklearn, statsmodels, scipy\n'ok'")
		self.assertIsNone(result.error)
		self.assertEqual(result.result, "'ok'")

	def test_a_hung_cell_is_killed_not_waited_on_forever(self):
		with NotebookKernel(timeout=2) as kernel:
			with self.assertRaises(NotebookCellTimeout):
				kernel.run_cell("import time\ntime.sleep(30)")
			with self.assertRaises(NotebookError):
				kernel.run_cell("1")  # the kernel was killed; it cannot answer

	def test_docker_unavailable_raises_rather_than_running_in_process(self):
		with patch("nakhoda.engine.notebook._docker_available", return_value=False):
			with self.assertRaises(NotebookUnavailable):
				NotebookKernel()


@unittest.skipUnless(
	_docker_available() and connected(),
	"needs docker and a site: bench --site <site> run-tests --app nakhoda",
)
class NotebookAPI(unittest.TestCase):
	def setUp(self) -> None:
		import frappe

		frappe.set_user("Administrator")

	def tearDown(self) -> None:
		import frappe

		frappe.set_user("Administrator")
		frappe.db.rollback()

	def test_run_cells_executes_in_order_and_logs_the_session(self):
		from nakhoda.api.notebooks import run_cells

		out = run_cells(["x = 21", "x * 2"])
		self.assertEqual(out["cells"][1]["result"], "42")

		import frappe

		log = frappe.get_doc("Nakhoda Notebook Run", {"session": out["session"]})
		self.assertEqual(log.status, "ok")
		self.assertEqual(log.cell_count, 2)
		self.assertEqual(json.loads(log.code), ["x = 21", "x * 2"])

	def test_a_failing_cell_does_not_stop_the_rest_and_is_logged_as_error(self):
		from nakhoda.api.notebooks import run_cells

		out = run_cells(["1 / 0", "2 + 2"])
		self.assertIsNotNone(out["cells"][0]["error"])
		self.assertEqual(out["cells"][1]["result"], "4")

		import frappe

		log = frappe.get_doc("Nakhoda Notebook Run", {"session": out["session"]})
		self.assertEqual(log.status, "error")
		self.assertIsNotNone(log.error)

	def test_docker_unavailable_is_logged_and_raised_not_swallowed(self):
		import frappe

		from nakhoda.api.notebooks import run_cells

		with patch("nakhoda.engine.notebook._docker_available", return_value=False):
			with self.assertRaises(frappe.ValidationError):
				run_cells(["1"])

		log = frappe.get_last_doc("Nakhoda Notebook Run")
		self.assertEqual(log.status, "unavailable")


if __name__ == "__main__":
	unittest.main()
