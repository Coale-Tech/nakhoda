# Copyright (c) 2026, Nakhoda and contributors
# For license information, please see license.txt
"""Phase 9's two gates, `docs/plan/12-build-plan.md` §Phase 9.

Gate A - a seventh domain costs one folder and zero Python, and none of the
fork's hardcoded per-domain machinery (`DASHBOARD_TYPES`, `_calculate_kpis`,
`_prepare_charts`) has a counterpart anywhere in this tree.

Gate B - distribution is real: a second, unrelated installed app's template is
discovered and importable with no change to `nakhoda/` itself; importing twice
never produces two records; and `migrate` carries a version bump into a
pristine copy while leaving a site-edited one alone.

Everything that touches the database needs a real site
(`bench --site <site> run-tests --app nakhoda`); `test_no_dashboard_types_or_kpi_branches`
is the one exception and always runs, since it only reads files off disk.
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import tempfile
import unittest
from unittest.mock import patch

try:
	import frappe

	from nakhoda.api import templates as api_templates
except ImportError:
	frappe = None
	api_templates = None

DOCTYPE = "Nakhoda Intelligence Template"


def connected() -> bool:
	return bool(getattr(frappe, "db", None))


def _write_folder(base: str, name: str, manifest: dict, payload: dict) -> str:
	path = os.path.join(base, name)
	os.makedirs(path, exist_ok=True)
	with open(os.path.join(path, "manifest.json"), "w") as f:
		json.dump(manifest, f)
	with open(os.path.join(path, "template.json"), "w") as f:
		json.dump(payload, f)
	return path


def _entry(app: str, folder: str, path: str, manifest: dict) -> dict:
	return {"app": app, "folder": folder, "path": path, "manifest": manifest}


class NoLiveSurface(unittest.TestCase):
	"""Bench-independent: reads the tree off disk, needs no site."""

	def test_no_dashboard_types_or_kpi_branches(self) -> None:
		root = pathlib.Path(__file__).resolve().parents[1]
		banned = ("DASHBOARD_TYPES", "_calculate_kpis", "_prepare_charts")
		hits = []
		for path in root.rglob("*.py"):
			if "__pycache__" in path.parts or path.name == "test_templates.py":
				continue
			text = path.read_text()
			for token in banned:
				if token in text:
					hits.append(f"{path}: {token}")
		self.assertEqual(hits, [], "the fork's hardcoded per-domain machinery has a counterpart")


@unittest.skipUnless(connected(), "needs a site: bench --site <site> run-tests --app nakhoda")
class GateA(unittest.TestCase):
	"""A seventh domain is one folder under `nakhoda/intelligence_templates/`,
	discovered live with zero code change."""

	def test_six_shipped_domains_are_discovered(self) -> None:
		registry = api_templates.discover_templates()
		shipped = {name for name in registry if name.startswith("nakhoda/")}
		self.assertEqual(
			shipped,
			{
				f"nakhoda/{key}"
				for key in ("financial", "sales", "procurement", "inventory", "production", "customer")
			},
		)
		for name in shipped:
			manifest = registry[name]["manifest"]
			for key in api_templates.MANIFEST_REQUIRED_KEYS:
				self.assertIn(key, manifest, f"{name} manifest missing {key!r}")
			payload = api_templates.get_template_payload(name)
			for field in api_templates.TEMPLATE_FIELDS:
				self.assertIn(field, payload, f"{name} template.json missing {field!r}")

	def test_seventh_domain_is_one_folder_and_zero_python(self) -> None:
		app_path = frappe.get_app_path("nakhoda")
		target = os.path.join(app_path, "intelligence_templates", "__gate_a_seventh__")
		self.addCleanup(shutil.rmtree, target, ignore_errors=True)
		_write_folder(
			os.path.join(app_path, "intelligence_templates"),
			"__gate_a_seventh__",
			{
				"version": 1,
				"title": "Test Seventh",
				"description": "A seventh domain, added by writing this folder alone.",
				"required_apps": [],
				"source_doctypes": [],
			},
			{
				"key": "seventh",
				"title": "Test Seventh",
				"icon": "star",
				"color": "#000000",
				"source": None,
				"metrics": [],
				"panels": [],
				"skill": "",
				"ml": [],
			},
		)
		registry = api_templates.discover_templates()
		self.assertIn("nakhoda/__gate_a_seventh__", registry)
		shutil.rmtree(target)
		self.assertNotIn("nakhoda/__gate_a_seventh__", api_templates.discover_templates())


@unittest.skipUnless(connected(), "needs a site: bench --site <site> run-tests --app nakhoda")
class GateB(unittest.TestCase):
	"""Distribution, from a second app, exercised without installing a second
	app: `discover_templates` is patched to return entries whose `app` is not
	`nakhoda`, which is exactly what `get_hooks`/`get_app_path` would produce
	for a genuinely separate installed app - the code under test never learns
	the difference."""

	def setUp(self) -> None:
		self.tmp = tempfile.mkdtemp()
		self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
		self.created: list[str] = []
		self.addCleanup(self._cleanup_created)

	def _cleanup_created(self) -> None:
		for name in self.created:
			frappe.delete_doc(DOCTYPE, name, force=True, ignore_permissions=True)
		if self.created:
			frappe.db.commit()

	def _manifest(self, version: int = 1) -> dict:
		return {
			"version": version,
			"title": "Gate B Template",
			"description": "A template shipped by an unrelated app.",
			"required_apps": [],
			"source_doctypes": [],
		}

	def _payload(self, title: str = "Gate B Template") -> dict:
		return {
			"key": "gate_b",
			"title": title,
			"icon": "flag",
			"color": "#123456",
			"source": None,
			"metrics": [
				{
					"label": "Rows",
					"expression": "count()",
					"format": "Number",
					"direction": "Higher Is Better",
				}
			],
			"panels": [],
			"skill": "",
			"ml": [],
		}

	def test_second_app_template_is_discovered_and_importable(self) -> None:
		path = _write_folder(self.tmp, "gate_b_pristine", self._manifest(), self._payload())
		registry = {"other_app/gate_b": _entry("other_app", "gate_b", path, self._manifest())}

		with patch.object(api_templates, "discover_templates", return_value=registry):
			result = api_templates.create_intelligence_template("other_app/gate_b")
			self.created.append(result["name"])

			self.assertTrue(frappe.db.exists(DOCTYPE, result["name"]))
			self.assertEqual(
				frappe.db.get_value(DOCTYPE, result["name"], "from_template"), "other_app/gate_b"
			)
			self.assertEqual(frappe.db.get_value(DOCTYPE, result["name"], "owner"), "Administrator")

			# a second import call - simulating two admins racing the Import
			# button - returns the same record rather than creating another
			again = api_templates.create_intelligence_template("other_app/gate_b")
			self.assertEqual(again["name"], result["name"])

		self.assertEqual(frappe.db.count(DOCTYPE, {"from_template": "other_app/gate_b"}), 1)

	def test_version_bump_updates_pristine_copy_and_skips_customized_one(self) -> None:
		manifest_v1 = self._manifest(version=1)
		pristine_path = _write_folder(self.tmp, "pristine_v1", manifest_v1, self._payload("Pristine v1"))
		customized_path = _write_folder(
			self.tmp, "customized_v1", manifest_v1, self._payload("Customized v1")
		)
		registry_v1 = {
			"other_app/pristine": _entry("other_app", "pristine", pristine_path, manifest_v1),
			"other_app/customized": _entry("other_app", "customized", customized_path, manifest_v1),
		}

		with patch.object(api_templates, "discover_templates", return_value=registry_v1):
			pristine_name = api_templates.create_intelligence_template("other_app/pristine")["name"]
			customized_name = api_templates.create_intelligence_template("other_app/customized")["name"]
		self.created += [pristine_name, customized_name]

		# the site edits one of the two copies
		doc = frappe.get_doc(DOCTYPE, customized_name)
		doc.title = "Edited On Site"
		doc.save(ignore_permissions=True)
		frappe.db.commit()

		# a newer version ships for both
		manifest_v2 = self._manifest(version=2)
		pristine_path_v2 = _write_folder(self.tmp, "pristine_v2", manifest_v2, self._payload("Pristine v2"))
		customized_path_v2 = _write_folder(
			self.tmp, "customized_v2", manifest_v2, self._payload("Customized v2")
		)
		registry_v2 = {
			"other_app/pristine": _entry("other_app", "pristine", pristine_path_v2, manifest_v2),
			"other_app/customized": _entry("other_app", "customized", customized_path_v2, manifest_v2),
		}

		with patch.object(api_templates, "discover_templates", return_value=registry_v2):
			api_templates.sync_intelligence_template_updates()

			# the edited copy is left alone: same name, its own title survives,
			# still reads customized
			self.assertEqual(frappe.db.get_value(DOCTYPE, customized_name, "title"), "Edited On Site")
			self.assertEqual(frappe.db.get_value(DOCTYPE, customized_name, "imported_version"), 1)
			self.assertTrue(api_templates._is_customized(customized_name))

			# the untouched sibling takes the update in place, keeping its name
			self.assertEqual(frappe.db.get_value(DOCTYPE, pristine_name, "title"), "Pristine v2")
			self.assertEqual(frappe.db.get_value(DOCTYPE, pristine_name, "imported_version"), 2)
			self.assertFalse(api_templates._is_customized(pristine_name))

			listing = {row["name"]: row for row in api_templates.get_intelligence_templates()}
		self.assertFalse(listing["other_app/pristine"]["update_available"])
		self.assertTrue(listing["other_app/customized"]["update_available"])
		self.assertTrue(listing["other_app/customized"]["customized"])
