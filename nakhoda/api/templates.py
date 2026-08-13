# Copyright (c) 2026, Nakhoda and contributors
# For license information, please see license.txt
"""Intelligence Template shipping and versioning - build-plan Phase 9.

Reimplemented clean-room against the *design* of Insights' workbook-template
distribution (`nvumabaranda/apps/insights/insights/api/templates.py`), not its
code: a hook any installed app can declare, one directory per template
underneath it, discovered live off `frappe.get_installed_apps()` with no
migrate step and no registry doctype, keyed `{app}/{folder}` so two apps can't
collide. Import is gated on `required_apps` and warns on `has_source_data()`.
One shared, Administrator-owned, org-shared copy per site, created under a
`filelock` so two admins clicking Import at once don't race a duplicate. A
`sha256` fingerprint stamped at import time is what lets the `migrate`-time
sync push a version bump into every pristine copy while leaving a
site-customized one alone.

Nakhoda's own shape differs from Insights' in one structural way that
simplifies this file: `metrics`/`ml` are real Frappe Table (child) fields on
`Nakhoda Intelligence Template`, not sibling doctypes referencing a parent by
Link the way `Insights Chart v3` references `Insights Workbook`. Replacing a
record's contents is therefore one `doc.update()` + `doc.save()` - Frappe's
own child-table diffing deletes and rebuilds the rows - with no manual
per-child-doctype delete loop to keep in sync.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from pathlib import Path

import frappe
import frappe.share
from frappe import _
from frappe.utils import cint
from frappe.utils.synchronization import filelock

DOCTYPE = "Nakhoda Intelligence Template"
MANIFEST_REQUIRED_KEYS = ("version", "title", "description", "required_apps", "source_doctypes")
TEMPLATES_HOOK = "nakhoda_intelligence_templates"

#: fields a `template.json` payload carries, and the only ones `doc.update()`
#: is ever asked to touch - everything else on the doctype is site metadata
#: (`name`, `owner`, `from_template`, `imported_version`, `imported_checksum`, ...)
#: that an import/update must never take from the shipped copy.
TEMPLATE_FIELDS = ("key", "title", "icon", "color", "source", "metrics", "panels", "skill", "ml")


#: JSON-fieldtype `panels` holds a list of panel specs. Frappe's own save path
#: only auto-serializes a `dict` for a JSON field (see `base_document.py`
#: `get_valid_dict`); a bare `list` is rejected outright ("cannot be a list").
#: A `template.json` payload and `doc.get("panels")` both carry a Python list,
#: so every write goes through `_for_doc` and every read through `_from_doc`.
def _for_doc(payload: dict) -> dict:
	out = dict(payload)
	if isinstance(out.get("panels"), list):
		out["panels"] = json.dumps(out["panels"])
	return out


def _from_doc(payload: dict) -> dict:
	out = dict(payload)
	if isinstance(out.get("panels"), str):
		out["panels"] = frappe.parse_json(out["panels"]) if out["panels"] else []
	return out


def get_installed_apps() -> set[str]:
	# indirection point only: lets a test substitute a fake app set without
	# touching the real frappe.get_installed_apps() every other subsystem trusts
	return set(frappe.get_installed_apps())


def _app_title(app: str) -> str:
	"""What the library shows as the shipping app's name. Reading the real
	title means importing the app, which a test's stand-in app cannot survive
	- so a lookup failure quietly falls back to the raw app name instead of
	taking the library down."""
	try:
		return (frappe.get_hooks("app_title", app_name=app) or [app])[0]
	except Exception:
		return app


def _load_manifest(manifest_path: Path) -> dict:
	"""Read and validate one template's manifest; raise if a required key is
	absent or the two list fields aren't lists, so the caller can skip it."""
	manifest = json.loads(manifest_path.read_text())
	absent = [key for key in MANIFEST_REQUIRED_KEYS if key not in manifest]
	if absent:
		raise ValueError(f"{manifest_path}: manifest omits required key(s) {', '.join(absent)}")
	bad_shape = [key for key in ("required_apps", "source_doctypes") if not isinstance(manifest[key], list)]
	if bad_shape:
		raise ValueError(f"{manifest_path}: field(s) {', '.join(bad_shape)} must hold a JSON array")
	return manifest


def _hook_folders(app: str) -> Iterator[Path]:
	"""Every subfolder of `app`'s declared template hook path that carries a
	`manifest.json` - anything else there (a README, a stray `.gitkeep`) is
	simply not a template and is passed over without complaint."""
	for rel_path in frappe.get_hooks(TEMPLATES_HOOK, app_name=app) or []:
		hook_dir = Path(frappe.get_app_path(app)) / rel_path
		if not hook_dir.is_dir():
			continue
		yield from (
			child
			for child in sorted(hook_dir.iterdir())
			if child.is_dir() and (child / "manifest.json").is_file()
		)


def discover_templates() -> dict[str, dict]:
	"""The site's live template library: every installed app's `manifest.json`
	folders under its declared `nakhoda_intelligence_templates` hook path.
	Installing an app adds its templates, uninstalling removes them - there is
	no migrate step and nothing stored between calls.

	Returns `{app}/{folder}` -> `{app, folder, path, manifest}`. The id is the
	only thing a caller ever resolves to a filesystem path (`_resolve`), which
	is what keeps a hand-crafted id from walking outside its folder.

	A single app shipping a broken manifest is skipped and logged rather than
	taking the whole library down."""
	registry: dict[str, dict] = {}
	for app in sorted(frappe.get_installed_apps()):
		for folder_path in _hook_folders(app):
			try:
				manifest = _load_manifest(folder_path / "manifest.json")
			except Exception:
				frappe.log_error(
					title="Invalid Intelligence Template manifest",
					message=f"Skipping template {app}/{folder_path.name}",
				)
				continue
			key = f"{app}/{folder_path.name}"
			registry[key] = {
				"app": app,
				"folder": folder_path.name,
				"path": str(folder_path),
				"manifest": manifest,
			}
	return registry


def _resolve(template_name: str) -> dict:
	entry = discover_templates().get(template_name)
	if not entry:
		frappe.throw(_("Unknown intelligence template: {0}").format(template_name))
	return entry


def get_template_payload(template_name: str) -> dict:
	template_dir = Path(_resolve(template_name)["path"])
	return json.loads((template_dir / "template.json").read_text())


def get_template_preview(template_name: str) -> str | None:
	preview = Path(_resolve(template_name)["path"]) / "preview.png"
	if not preview.is_file():
		return None
	import base64

	encoded = base64.b64encode(preview.read_bytes()).decode()
	return f"data:image/png;base64,{encoded}"


def has_required_apps(manifest: dict) -> bool:
	missing = set(manifest.get("required_apps") or []) - get_installed_apps()
	return not missing


def has_source_data(manifest: dict) -> bool:
	"""Cheap `EXISTS` across the template's source tables - True the moment any
	one of them holds a row, so the library can warn that importing now would
	produce an empty dashboard. Checking only the first table would miss data
	that only the others hold."""
	live_tables = (dt for dt in manifest.get("source_doctypes") or [] if frappe.db.table_exists(dt))
	return any(frappe.db.get_value(dt, {}, "name") for dt in live_tables)


def get_imported_templates() -> dict[str, str]:
	"""Map of template id -> the record this site already imported from it. One
	shared copy per site, derived from a live query rather than a stored flag,
	so deleting the record re-enables its template in the library on its own."""
	rows = frappe.get_all(
		DOCTYPE,
		filters={"from_template": ["!=", ""]},
		fields=["from_template", "name"],
		order_by="creation asc",
	)
	imported: dict[str, str] = {}
	for row in rows:
		# if a duplicate ever slipped past the import lock, the oldest wins
		imported.setdefault(row.from_template, row.name)
	return imported


@frappe.whitelist()
def get_intelligence_templates() -> list[dict]:
	"""Every installed app's templates whose `required_apps` are all installed
	here. Empty on a site missing the apps a template needs."""
	imported = get_imported_templates()
	out = []
	for name, entry in sorted(discover_templates().items()):
		manifest = entry["manifest"]
		if not has_required_apps(manifest):
			continue
		version = cint(manifest.get("version") or 1)
		imported_name = imported.get(name)
		imported_version = (
			cint(frappe.db.get_value(DOCTYPE, imported_name, "imported_version")) if imported_name else None
		)
		update_available = bool(imported_name) and version > imported_version
		out.append(
			{
				"name": name,
				"title": manifest.get("title") or name,
				"description": manifest.get("description"),
				"module": manifest.get("module"),
				"app": entry["app"],
				"app_title": _app_title(entry["app"]),
				"version": version,
				"has_data": has_source_data(manifest),
				"preview_image": get_template_preview(name),
				"imported_name": imported_name,
				"imported_version": imported_version,
				"update_available": update_available,
				"customized": update_available and _is_customized(imported_name),
			}
		)
	return out


def _find_imported(template_name: str) -> str | None:
	"""This site's existing record for the template, if any (oldest wins)."""
	return frappe.db.get_value(DOCTYPE, {"from_template": template_name}, "name", order_by="creation asc")


def _reassign_to_administrator(doc_name: str) -> None:
	"""Own the imported record as Administrator, so it reads as a shared org
	resource rather than belonging to whichever admin happened to click Import
	(and so only real admins can edit/delete it - everyone else reads via the
	share). `metrics`/`ml` are Table rows, not sibling doctypes, so there is
	nothing else to reassign - one `set_value` covers the whole record."""
	frappe.db.set_value(DOCTYPE, doc_name, "owner", "Administrator")


def _share_with_organization(doc_name: str) -> None:
	"""Implicit organization: everyone-share, read-only - the shape a real admin
	clicking "share with everyone" produces. `ignore_share_permission` is needed
	because ownership has already moved to Administrator by the time this runs,
	so the acting admin no longer holds a share right on the record."""
	frappe.share.add_docshare(
		DOCTYPE,
		doc_name,
		read=1,
		write=0,
		everyone=1,
		flags={"ignore_share_permission": True},
	)


def _require_admin() -> None:
	frappe.only_for(("Nakhoda Admin", "System Manager"))


def _create(template_name: str, manifest: dict) -> str:
	payload = {k: v for k, v in get_template_payload(template_name).items() if k in TEMPLATE_FIELDS}
	doc = frappe.get_doc({"doctype": DOCTYPE, **_for_doc(payload)})
	doc.insert(ignore_permissions=True)
	doc.db_set("from_template", template_name, update_modified=False)
	_reassign_to_administrator(doc.name)
	_share_with_organization(doc.name)
	_stamp_version(doc.name, manifest)
	return doc.name


@frappe.whitelist()
def create_intelligence_template(template_name: str) -> dict:
	"""Import a shipped template as this site's one shared copy. A second call
	for the same template, from any caller, returns the existing copy rather
	than creating a duplicate."""
	_require_admin()
	entry = _resolve(template_name)
	manifest = entry["manifest"]
	if not has_required_apps(manifest):
		frappe.throw(
			_("Intelligence template {0} requires apps that are not installed: {1}").format(
				frappe.bold(manifest.get("title") or template_name),
				", ".join(manifest.get("required_apps") or []),
			)
		)

	# One shared copy per site: serialize check-then-insert so two admins
	# importing at once can't both create one. The id's "/" is flattened so
	# the lock name stays a plain filename, not a nested path.
	lock_key = f"nakhoda_intelligence_template_import_{template_name.replace('/', '_')}"
	with filelock(lock_key, timeout=60):
		existing = _find_imported(template_name)
		if existing:
			return {"name": existing}
		doc_name = _create(template_name, manifest)
		# commit inside the lock so the copy is visible to the next caller that
		# takes the lock; without it, the next holder reads a pre-insert
		# snapshot and creates a silent duplicate
		frappe.db.commit()  # nosemgrep — intentional commit inside the import lock

	return {"name": doc_name}


def _export(doc_name: str) -> dict:
	"""The record's content fields only - the same set a `template.json` ships
	- for both the checksum and an in-place update's diff target. Site
	metadata (`name`, `owner`, timestamps, `from_template`, the version/checksum
	pair themselves) is deliberately excluded: none of it is what "customized"
	means, and re-including it would make every copy read as customized the
	moment `modified` ticks."""
	doc = frappe.get_doc(DOCTYPE, doc_name)
	return _from_doc({field: doc.get(field) for field in TEMPLATE_FIELDS})


def _checksum(payload: dict) -> str:
	serialized = json.dumps(payload, sort_keys=True, default=str)
	return hashlib.sha256(serialized.encode()).hexdigest()


def _is_customized(doc_name: str | None) -> bool:
	"""True if the copy has drifted from what was imported - or if there is no
	stored fingerprint at all, which is treated as customized so a copy is
	never silently overwritten by a guess."""
	if not doc_name:
		return False
	stored = frappe.db.get_value(DOCTYPE, doc_name, "imported_checksum")
	return not stored or stored != _checksum(_export(doc_name))


def _stamp_version(doc_name: str, manifest: dict) -> None:
	frappe.db.set_value(
		DOCTYPE,
		doc_name,
		{
			"imported_version": cint(manifest.get("version") or 1),
			"imported_checksum": _checksum(_export(doc_name)),
		},
		update_modified=False,
	)


def _replace_contents(doc_name: str, payload: dict) -> None:
	"""Swap the record's content fields for the template's, keeping its own
	`name` so anything already pointing at it - a Phase 10 dashboard, a
	bookmark - still resolves. `doc.update` + `doc.save` is enough: `metrics`
	and `ml` are Table fields, so Frappe's own child-row diffing rebuilds them;
	there is no sibling child doctype to delete out from under the record the
	way Insights must for `Insights Chart v3` et al."""
	doc = frappe.get_doc(DOCTYPE, doc_name)
	doc.update(_for_doc({field: payload.get(field) for field in TEMPLATE_FIELDS}))
	doc.save(ignore_permissions=True)


def _update_imported(template_name: str, doc_name: str, manifest: dict) -> None:
	payload = get_template_payload(template_name)
	_replace_contents(doc_name, payload)
	_stamp_version(doc_name, manifest)


@frappe.whitelist()
def update_intelligence_template(template_name: str) -> dict:
	"""Re-take the shipped version into the already-imported record, in place.
	The library offers this once a newer version ships; a customized copy is
	warned about client-side before this is called, since it replaces the
	copy's contents unconditionally."""
	_require_admin()
	entry = _resolve(template_name)
	manifest = entry["manifest"]
	if not has_required_apps(manifest):
		frappe.throw(
			_("Intelligence template {0} requires apps that are not installed: {1}").format(
				frappe.bold(manifest.get("title") or template_name),
				", ".join(manifest.get("required_apps") or []),
			)
		)

	doc_name = _find_imported(template_name)
	if not doc_name:
		return create_intelligence_template(template_name)

	lock_key = f"nakhoda_intelligence_template_import_{template_name.replace('/', '_')}"
	with filelock(lock_key, timeout=60):
		_update_imported(template_name, doc_name, manifest)
		frappe.db.commit()  # nosemgrep — intentional commit inside the import lock

	return {"name": doc_name}


def sync_intelligence_template_updates() -> None:
	"""Run on `migrate` (`hooks.py:after_migrate`): carry a newer shipped
	version into every pristine imported copy with no clicks - there is
	nothing of the site's to clobber. A copy the site has edited is left
	alone; the library surfaces a manual update for it instead."""
	registry = discover_templates()
	# flush whatever earlier after_migrate steps left pending, so a rollback
	# below can only ever discard the one copy it was updating
	frappe.db.commit()  # nosemgrep — flush prior after_migrate work before per-copy rollbacks
	for template_name, doc_name in get_imported_templates().items():
		entry = registry.get(template_name)
		if not entry:
			continue
		manifest = entry["manifest"]
		version = cint(manifest.get("version") or 1)
		imported_version = cint(frappe.db.get_value(DOCTYPE, doc_name, "imported_version"))
		try:
			if not imported_version:
				# a copy imported before versioning existed: adopt the current
				# version as its baseline so it doesn't read as "update
				# available", but its checksum stays empty, which _is_customized
				# reads as customized - so it is never auto-updated on a guess
				frappe.db.set_value(DOCTYPE, doc_name, "imported_version", version, update_modified=False)
			elif imported_version < version and not _is_customized(doc_name):
				_update_imported(template_name, doc_name, manifest)
			else:
				continue
			# commit per copy so each update lands whole or, on failure below,
			# rolls back without taking any other copy's already-landed update with it
			frappe.db.commit()  # nosemgrep — land each copy atomically (paired with the rollback below)
		except Exception:
			frappe.db.rollback()
			frappe.log_error(title=f"Failed to sync intelligence template {template_name}")
