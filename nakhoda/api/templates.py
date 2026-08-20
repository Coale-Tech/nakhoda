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

from nakhoda.engine import cache, pipeline
from nakhoda.engine.dashboard import normalise
from nakhoda.engine.permissions import for_connector
from nakhoda.nakhoda.doctype.nakhoda_query.nakhoda_query import provider as query_provider

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
	"""Serialize `panels` for the JSON field, canonicalising it on the way in.

	Both write paths - `_create` and `_replace_contents` - funnel through here
	with `panels` and `metrics` in the same payload, which is the one place
	`engine.dashboard.normalise` has everything it needs. Stored canonical
	means every panel carries an `i` and a resolved `measure`, so `set_filter`
	and `remove_item` name real targets on a freshly imported dashboard
	instead of raising `PatchError`.
	"""
	out = dict(payload)
	if isinstance(out.get("panels"), list):
		out["panels"] = json.dumps(normalise(out["panels"], out.get("metrics") or []))
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


@frappe.whitelist()
def list_dashboards() -> list[dict]:
	"""Instantiated dashboards - `Nakhoda Intelligence Template` records with
	`from_template` set, newest-modified first. The shipped-but-not-yet-
	imported entries `get_intelligence_templates` also returns never appear
	here; this list is only what a user can actually open."""
	fields = ["name", "key", "title", "icon", "color", "from_template", "modified"]
	return frappe.get_all(
		DOCTYPE,
		fields=fields,
		filters={"from_template": ["is", "set"]},
		order_by="modified desc",
	)


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


def _ensure_source(doc_name: str, payload: dict) -> None:
	"""Link the template's own verified query, creating and approving it on
	first import.

	A dashboard with no `source` is not a dashboard: `get_dashboard_data`
	returns `metrics_available: False` for it and every panel renders as an
	empty layout. Every shipped `template.json` used to carry `"source": null`
	with nothing on the site for it to point at, so all six templates imported
	cleanly and then showed nothing - the defect this function exists to close.

	The query belongs to the template, not to the site, so it ships in
	`template.json` as `source_query` (a `question` plus `operations`) and is
	created here rather than by hand. `source_query` is deliberately absent
	from `TEMPLATE_FIELDS`: it is not a field on this doctype, and the
	fingerprint `_stamp_version` takes must cover the `source` this produces,
	not the recipe that produced it - otherwise a fresh import would read as
	customized immediately and the `migrate`-time sync would skip it forever.

	Idempotent three ways: an already-linked `source` is never relinked, a
	query whose `question` already matches is reused rather than duplicated
	(the same normalised equality `agent/verified.py` routes on, so a template
	and the agent can never disagree about which query answers a question),
	and a template shipping no `source_query` is left exactly as it was.
	"""
	from nakhoda.api import default_source

	spec = payload.get("source_query") or {}
	operations = spec.get("operations")
	question = (spec.get("question") or "").strip()
	if not operations or not question:
		return
	if frappe.db.get_value(DOCTYPE, doc_name, "source"):
		return

	existing = frappe.db.get_value("Nakhoda Verified Query", {"question": question}, "name")
	if existing:
		query_name = str(existing)
		# a draft left behind by an earlier failed import answers nothing until
		# it is approved (`nakhoda_verified_query.py` Gate A refuses docstatus 0)
		if cint(frappe.db.get_value("Nakhoda Verified Query", existing, "docstatus")) == 0:
			frappe.get_doc("Nakhoda Verified Query", query_name).submit()
	else:
		query = frappe.get_doc(
			{
				"doctype": "Nakhoda Verified Query",
				"title": spec.get("title") or question,
				"question": question,
				"data_source": default_source(),
				"operations": json.dumps(operations),
			}
		)
		query.insert(ignore_permissions=True)
		# submit, not a flag: approval is a Frappe permission, and `_require_admin`
		# has already established the caller holds it
		query.submit()
		query_name = query.name

	frappe.db.set_value(DOCTYPE, doc_name, "source", query_name, update_modified=False)


def _create(template_name: str, manifest: dict) -> str:
	full = get_template_payload(template_name)
	payload = {k: v for k, v in full.items() if k in TEMPLATE_FIELDS}
	doc = frappe.get_doc({"doctype": DOCTYPE, **_for_doc(payload)})
	doc.insert(ignore_permissions=True)
	doc.db_set("from_template", template_name, update_modified=False)
	_ensure_source(str(doc.name), full)
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


@frappe.whitelist()
def get_dashboard_data(template_name: str) -> dict:
	"""Compute this dashboard's metric values by appending one `summarize`
	step - one measure per `Nakhoda Intelligence Metric` row - onto its
	`source` query's own pipeline, then running that through the same
	`engine.pipeline.run` every other execution surface uses. One execution
	computes every metric at once; there is no per-metric round trip.

	A missing source, an unverified source, or a malformed metric expression
	is not an error: the dashboard still returns its `panels` layout, with
	`metrics_available: False` and a reason, so a freshly-imported template
	is visible immediately rather than throwing at load time.
	"""
	doc = frappe.get_doc(DOCTYPE, template_name)
	doc.check_permission("read")
	# Also normalised on read, not only on write: a site that imported this
	# dashboard before `_for_doc` canonicalised anything still has raw shipped
	# panels stored, and repairing them here fixes those records without a
	# migration. `normalise` is idempotent, so a record already canonical
	# round-trips unchanged.
	panels = normalise(frappe.parse_json(doc.get("panels") or "[]"), doc.get("metrics") or [])
	identity = {
		"name": doc.name,
		"key": doc.get("key"),
		"title": doc.get("title"),
		"icon": doc.get("icon"),
		"color": doc.get("color"),
	}

	if not doc.get("source"):
		return {
			**identity,
			"metrics": [],
			"panels": panels,
			"metrics_available": False,
			"reason": _("No source query configured"),
		}

	query = frappe.get_doc("Nakhoda Verified Query", doc.get("source"))
	if query.get("docstatus") != 1:
		return {
			**identity,
			"metrics": [],
			"panels": panels,
			"metrics_available": False,
			"reason": _("Source query is not verified"),
		}

	rows = list(doc.get("metrics") or [])
	if not rows:
		return {**identity, "metrics": [], "panels": panels, "metrics_available": True, "reason": None}

	try:
		measures = [
			{"name": f"m{idx}", "expr": frappe.parse_json(row.get("expression"))}
			for idx, row in enumerate(rows)
		]
		settings = frappe.get_cached_doc("Nakhoda Settings")
		source = frappe.get_cached_doc("Nakhoda Data Source", query.get("data_source"))
		connector = source.connector()
		resolver = for_connector(connector, str(frappe.session.user))
		ttl = int(settings.get("cache_ttl") or cache.DEFAULT_TTL)
		ops = [*frappe.parse_json(query.get("operations")), {"type": "summarize", "measures": measures}]
		result = pipeline.run(
			ops,
			resolver,
			connector,
			cap=1,
			ttl=ttl,
			queries=query_provider(str(query.get("data_source"))),
		)
	except Exception as exc:
		frappe.log_error(title=f"Nakhoda: could not compute dashboard {template_name}")
		return {**identity, "metrics": [], "panels": panels, "metrics_available": False, "reason": str(exc)}

	record = result.frame.to_dict(orient="records")[0] if len(result.frame) else {}
	metrics = [
		{
			"label": row.get("label"),
			"value": record.get(f"m{idx}"),
			"format": row.get("format"),
			"target": row.get("target"),
			"direction": row.get("direction"),
		}
		for idx, row in enumerate(rows)
	]
	return {**identity, "metrics": metrics, "panels": panels, "metrics_available": True, "reason": None}


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
	fields = {field: payload.get(field) for field in TEMPLATE_FIELDS}
	# a template ships `source: null` and names its query in `source_query`
	# instead; overwriting with that null would unlink the query `_ensure_source`
	# created and silently empty a working dashboard on every version bump
	if not fields.get("source"):
		fields.pop("source")
	doc.update(_for_doc(fields))
	doc.save(ignore_permissions=True)


def _update_imported(template_name: str, doc_name: str, manifest: dict) -> None:
	payload = get_template_payload(template_name)
	_replace_contents(doc_name, payload)
	_ensure_source(doc_name, payload)
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
