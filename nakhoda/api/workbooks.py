# Copyright (c) 2026, Nakhoda and contributors
# For license information, please see license.txt
"""The workbook list, its sharing, and the organisation of what is inside it.

Everything here is either a *collection*-level read the document API cannot
express, or a write that must not look like a document edit. The per-document
CRUD the workbench performs - load a query, save a chart, autosave a dashboard -
goes through Frappe's own `/api/v2/document/...` routes, so none of it is
duplicated in this module. If a function here could have been a document method,
it belongs on the controller instead.

Three shapes recur, and all three are deliberate.

**Batched reads.** `get_workbooks` renders a table, so it answers view counts
and share state in one query each rather than one per row. The alternative is
not slower by a constant - it is a round trip per workbook, which is exactly the
kind of list that gets quietly slower as the site gets used.

**Writes with `update_modified=False`.** Expanding a folder, dragging an item
between folders, reordering a sidebar - none of these change what a workbook
*says*, and all of them happen while an autosaving document is open. Bumping
`modified` would make the browser's next save look like a conflict against
state the browser itself produced.

**Payloads are coerced, not trusted.** These are form-encoded endpoints: a list
of permissions arrives as a JSON string from the browser and as a real list from
a Python caller, and `frappe.parse_json` will hand back whatever was in there.
`_rows` and `_mapping` are the only places that shape is decided.

No function here commits. The request boundary commits, and an explicit
`frappe.db.commit()` inside a whitelisted call is what turns a failed test into
a dirty database - Insights' `update_sort_orders`
(`insights/api/workbooks.py:296`) does this and cannot be rolled back.
"""

from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.share import add_docshare
from frappe.utils import cint
from frappe.utils.user import get_users_with_role

WORKBOOK = "Nakhoda Workbook"
FOLDER = "Nakhoda Folder"

# `item_type` as the browser says it, mapped to the DocType that stores it.
ITEM_DOCTYPES = {"query": "Nakhoda Query", "chart": "Nakhoda Chart"}

FOLDER_TYPES = tuple(ITEM_DOCTYPES)

ORG_ACCESS = (None, "", "view", "edit")


def _rows(value: Any) -> list[dict[str, Any]]:
	"""A list of dicts, whatever the transport did to it."""
	parsed = frappe.parse_json(value) if isinstance(value, str) else value
	if not isinstance(parsed, list):
		return []
	return [row for row in parsed if isinstance(row, dict)]


def _mapping(value: Any) -> dict[str, Any]:
	"""A dict, whatever the transport did to it."""
	parsed = frappe.parse_json(value) if isinstance(value, str) else value
	return parsed if isinstance(parsed, dict) else {}


def _require(ptype: str, workbook_name: Any) -> None:
	"""Check one permission on one workbook, and refuse in words.

	`str()` is not decoration. `Nakhoda Workbook` is autoincrement, so a name
	taken from a document is an `int`, and Frappe builds its denial message with
	`doc if isinstance(doc, str) else doc.name` (`frappe/__init__.py:642`) - an
	`int` reaches neither branch, so the refusal surfaces as `AttributeError`
	instead. Whitelisted calls arrive as strings and never see it; a server-side
	caller handing over `doc.name` would, and only when it is *denied*, which is
	the one moment the message matters.
	"""
	frappe.has_permission(WORKBOOK, ptype=ptype, doc=str(workbook_name), throw=True)


@frappe.whitelist()
def get_workbooks(search_term: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
	"""Every workbook this user may read, with view counts and share state.

	`get_list` applies permissions and the DocShare join, so a workbook shared
	with this user appears here without a second lookup. What it cannot do is
	count views or say *who* a workbook is shared with, which is what the two
	batched queries below add.
	"""
	pattern = f"%{search_term}%" if search_term else "%"
	workbooks = frappe.get_list(
		WORKBOOK,
		or_filters={"owner": ("like", pattern), "title": ("like", pattern)},
		fields=["name", "title", "owner", "creation", "modified"],
		limit=cint(limit) or 100,
		order_by="modified desc",
	)
	if not workbooks:
		return workbooks

	# `View Log.reference_name` and `DocShare.share_name` are text columns, while
	# this DocType is `autoincrement` - so `name` arrives here as an integer and
	# comes back from those tables as a string. Keying both sides on `str` is the
	# whole fix; without it every count is zero and every workbook looks unshared.
	names = [str(row["name"]) for row in workbooks]
	views = _view_counts(names)
	org_wide, per_user = _share_state(names)
	# Owners *and* sharees resolve to people, not logins, in the one query
	# `_full_names` already batches: the Access column names a single sharer the
	# way Insights' list does (`src2/workbook/WorkbookList.vue` via its user
	# store), and an email there would read as a different kind of value from
	# every other name on the page.
	people = {row["owner"] for row in workbooks}
	for shared in per_user.values():
		people.update(shared)
	full_names = _full_names(list(people))

	for row in workbooks:
		key = str(row["name"])
		row["views"] = views.get(key, 0)
		row["shared_with_organization"] = key in org_wide
		# The owner's own access is implicit and always present; listing it as a
		# share would tell every reader their own name.
		row["shared_with"] = [user for user in per_user.get(key, ()) if user != row["owner"]]
		row["shared_with_names"] = [full_names.get(user) or user for user in row["shared_with"]]
		row["owner_name"] = full_names.get(row["owner"]) or row["owner"]

	return workbooks


def _view_counts(names: list[str]) -> dict[str, int]:
	"""Views per workbook, in one grouped query."""
	log = frappe.qb.DocType("View Log")
	rows = (
		frappe.qb.from_(log)
		.select(log.reference_name, frappe.qb.functions("COUNT", log.name).as_("views"))
		.where(log.reference_doctype == WORKBOOK)
		.where(log.reference_name.isin(names))
		.groupby(log.reference_name)
		.run(as_dict=True)
	)
	return {row["reference_name"]: cint(row["views"]) for row in rows}


def _share_state(names: list[str]) -> tuple[set[str], dict[str, list[str]]]:
	"""Which workbooks are org-wide, and who else each one is shared with."""
	share = frappe.qb.DocType("DocShare")
	rows = (
		frappe.qb.from_(share)
		.select(share.share_name, share.user, share.everyone)
		.where(share.share_doctype == WORKBOOK)
		.where(share.share_name.isin(names))
		.run(as_dict=True)
	)

	org_wide: set[str] = set()
	per_user: dict[str, list[str]] = {}
	for row in rows:
		if cint(row["everyone"]):
			org_wide.add(row["share_name"])
		elif row["user"]:
			per_user.setdefault(row["share_name"], []).append(row["user"])
	return org_wide, per_user


@frappe.whitelist()
def import_workbook(workbook: dict | str) -> str:
	"""Create a workbook from an exported payload.

	The tree is not rebuilt here: the payload goes into `data_backup` and the
	controller's `after_insert` restores it. One restore path, used by import,
	duplicate and undelete alike.
	"""
	frappe.has_permission(WORKBOOK, "create", throw=True)

	payload = _mapping(workbook)
	if not payload.get("dependencies"):
		frappe.throw(_("This does not look like an exported workbook."))

	doc = frappe.get_doc(
		{
			"doctype": WORKBOOK,
			"title": payload.get("title") or _("Imported Workbook"),
			"data_backup": frappe.as_json(payload),
		}
	).insert()
	return str(doc.name)


@frappe.whitelist()
def get_share_permissions(workbook_name: str) -> dict[str, Any]:
	"""Who can read or edit this workbook, and how the organisation sees it."""
	_require("share", workbook_name)

	shares = frappe.get_all(
		"DocShare",
		filters={"share_doctype": WORKBOOK, "share_name": workbook_name},
		fields=["user", "read", "write", "everyone"],
	)

	organization_access = None
	user_shares = []
	for share in shares:
		if cint(share.everyone):
			organization_access = "edit" if cint(share.write) else "view"
		elif share.user:
			user_shares.append(share)

	full_names = _full_names([share.user for share in user_shares])

	return {
		"user_permissions": [
			{
				"user": share.user,
				"full_name": full_names.get(share.user) or share.user,
				"read": cint(share.read),
				"write": cint(share.write),
			}
			for share in user_shares
		],
		"organization_access": organization_access,
	}


def _full_names(emails: list[str]) -> dict[str, str]:
	"""Display names for a set of users, in one query."""
	if not emails:
		return {}
	rows = frappe.get_all("User", filters={"name": ("in", emails)}, fields=["name", "full_name"])
	return {row["name"]: row["full_name"] for row in rows}


#: Roles that make someone a candidate to share with. Deliberately not
#: `permissions.ADMIN_ROLES`: a `System Manager` already reads every workbook
#: through the resolver, so a `DocShare` naming one grants nothing and would
#: only clutter the picker. `Administrator` is excluded by Frappe's own
#: `get_users_with_role`.
SHAREABLE_ROLES = ("Nakhoda User", "Nakhoda Admin")


@frappe.whitelist()
def list_shareable_users(
	workbook_name: str, search_term: str | None = None, limit: int = 20
) -> list[dict[str, str]]:
	"""People this workbook can be shared with.

	Gated on `share` for the workbook in hand rather than on a role: the picker
	exists to administer one document, so the right question is whether the
	caller administers *that* document. A bare role check would hand the user
	directory to anyone who merely uses the app.
	"""
	_require("share", workbook_name)

	candidates: set[str] = set()
	for role in SHAREABLE_ROLES:
		candidates.update(get_users_with_role(role))
	if not candidates:
		return []

	filters: dict[str, Any] = {"name": ("in", sorted(candidates))}
	or_filters = None
	if search_term:
		pattern = f"%{search_term}%"
		or_filters = {"name": ("like", pattern), "full_name": ("like", pattern)}

	# `get_all`, not `get_list`: `User` is readable only to users who hold a
	# role with permission on it, and an ordinary `Nakhoda User` sharing their
	# own workbook holds none. The permission that matters was already checked
	# above, against the workbook.
	rows = frappe.get_all(
		"User",
		filters=filters,
		or_filters=or_filters,
		fields=["name", "full_name", "user_image"],
		order_by="full_name asc",
		limit_page_length=cint(limit) or 20,
	)
	return [
		{
			"user": row["name"],
			"full_name": row["full_name"] or row["name"],
			"user_image": row["user_image"] or "",
		}
		for row in rows
	]


@frappe.whitelist()
def update_share_permissions(
	workbook_name: str, user_permissions: Any, organization_access: str | None = None
) -> None:
	"""Reconcile the share list to exactly what was sent.

	Sent state wins: a user absent from the payload loses access. The dialog
	always submits the whole list, so treating this as a patch would make
	removal impossible to express.
	"""
	_require("share", workbook_name)

	if organization_access not in ORG_ACCESS:
		frappe.throw(_("Unknown organization access: {0}").format(organization_access))

	owner = frappe.db.get_value(WORKBOOK, workbook_name, "owner")

	wanted: dict[str, int] = {}
	for row in _rows(user_permissions):
		user = row.get("user")
		# The owner's access is structural. A docshare for it would be a row
		# that means nothing and can be revoked to no effect.
		if not user or user == owner:
			continue
		wanted[str(user)] = cint(row.get("write"))

	existing = frappe.get_all(
		"DocShare",
		filters={"share_doctype": WORKBOOK, "share_name": workbook_name, "everyone": 0},
		fields=["name", "user"],
	)

	for user, write in wanted.items():
		# `add_docshare` updates an existing row for the same (doc, user) rather
		# than duplicating it, so add and change are the same call. It always
		# grants read - which is right here, since the UI's two states are
		# "can view" and "can edit".
		add_docshare(
			WORKBOOK,
			workbook_name,
			user,
			write=write,
			flags={"ignore_share_permission": True},
		)

	for share in existing:
		if share.user not in wanted:
			frappe.delete_doc("DocShare", share.name, ignore_permissions=True)

	_set_organization_access(workbook_name, organization_access)


def _set_organization_access(workbook_name: str, access: str | None) -> None:
	"""Create, update or drop the single `everyone` docshare.

	Written directly rather than through `share.add_docshare`, which defaults an
	absent `user` to `frappe.session.user` and would stamp whoever flipped the
	switch onto a row that is supposed to belong to nobody.
	"""
	current = frappe.db.get_value(
		"DocShare",
		{"share_doctype": WORKBOOK, "share_name": workbook_name, "everyone": 1},
		"name",
	)

	if not access:
		if current:
			frappe.delete_doc("DocShare", str(current), ignore_permissions=True)
		return

	share = (
		frappe.get_doc("DocShare", str(current))
		if current
		else frappe.new_doc(
			"DocShare",
			share_doctype=WORKBOOK,
			share_name=workbook_name,
			everyone=1,
		)
	)
	share.update({"read": 1, "write": 1 if access == "edit" else 0})
	share.flags.ignore_share_permission = True
	share.save(ignore_permissions=True)


@frappe.whitelist()
def create_folder(workbook: str, title: str, folder_type: str) -> str:
	"""Add a grouping label to one section of a workbook."""
	_require("write", workbook)
	_validate_folder_type(folder_type)

	title = (title or "").strip()
	if not title:
		frappe.throw(_("A folder needs a name."))

	last = frappe.get_all(
		FOLDER,
		filters={"workbook": workbook, "type": folder_type},
		pluck="sort_order",
		order_by="sort_order desc",
		limit=1,
	)
	doc = frappe.get_doc(
		{
			"doctype": FOLDER,
			"workbook": workbook,
			"title": title,
			"type": folder_type,
			"sort_order": cint(last[0] if last else 0) + 1,
		}
	).insert()
	return str(doc.name)


def _validate_folder_type(folder_type: str) -> None:
	if folder_type not in FOLDER_TYPES:
		frappe.throw(_("A folder holds queries or charts, not {0}.").format(folder_type))


@frappe.whitelist()
def rename_folder(folder_name: str, new_title: str) -> None:
	"""Rename a folder, and every item that names it.

	`folder` on a query or chart is the label, not a Link, so the rename has to
	move with the rows. Doing both here rather than in a controller keeps it one
	transaction: a half-renamed folder would split its contents in two.
	"""
	folder = _folder(folder_name)

	new_title = (new_title or "").strip()
	if not new_title:
		frappe.throw(_("A folder needs a name."))
	if new_title == folder["title"]:
		return

	frappe.db.set_value(
		ITEM_DOCTYPES[folder["type"]],
		{"workbook": folder["workbook"], "folder": folder["title"]},
		"folder",
		new_title,
		update_modified=False,
	)
	frappe.db.set_value(FOLDER, folder_name, "title", new_title)


@frappe.whitelist()
def delete_folder(folder_name: str, move_items_to_root: bool = True) -> None:
	"""Remove a folder, either keeping its contents or taking them with it."""
	folder = _folder(folder_name)
	doctype = ITEM_DOCTYPES[folder["type"]]
	filters = {"workbook": folder["workbook"], "folder": folder["title"]}

	if cint(move_items_to_root):
		frappe.db.set_value(doctype, filters, "folder", None, update_modified=False)
	else:
		for name in frappe.get_all(doctype, filters=filters, pluck="name"):
			frappe.delete_doc(doctype, name)

	frappe.delete_doc(FOLDER, folder_name)


@frappe.whitelist()
def toggle_folder_expanded(folder_name: str, is_expanded: Any) -> None:
	"""Remember whether a folder is open. UI state, not an edit."""
	_folder(folder_name)
	frappe.db.set_value(FOLDER, folder_name, "is_expanded", cint(is_expanded), update_modified=False)


def _folder(folder_name: str) -> dict[str, Any]:
	"""One folder's identity, after proving write access to its workbook.

	Read through `get_all` rather than `db.get_value`, whose single-row shape is
	a union of dict, list and `None` that no caller can index without a cast.
	The permission that matters is on the workbook, and it is checked here.
	"""
	rows = frappe.get_all(
		FOLDER, filters={"name": folder_name}, fields=["title", "type", "workbook"], limit=1
	)
	if not rows:
		frappe.throw(_("Folder {0} does not exist.").format(folder_name))
	folder = dict(rows[0])
	_require("write", folder["workbook"])
	return folder


@frappe.whitelist()
def move_item_to_folder(item_type: str, item_name: str, folder_name: str | None = None) -> None:
	"""Put a query or chart in a folder, or back at the root.

	`folder_name` is a folder *document name* on the way in and is stored as its
	*title*, because that is what the item's `folder` field holds. Taking the
	document name from the caller means the browser passes what the sidebar
	already has, and a folder renamed in another tab still resolves.
	"""
	doctype = _item_doctype(item_type)
	workbook = frappe.db.get_value(doctype, item_name, "workbook")
	if not workbook:
		frappe.throw(_("That item is not in a workbook."))
	_require("write", workbook)

	title = None
	if folder_name:
		folder = _folder(folder_name)
		if folder["workbook"] != workbook:
			frappe.throw(_("That folder is not in this workbook."))
		if folder["type"] != item_type:
			frappe.throw(_("A {0} folder cannot hold a {1}.").format(folder["type"], item_type))
		title = folder["title"]

	frappe.db.set_value(doctype, item_name, "folder", title, update_modified=False)


def _item_doctype(item_type: str) -> str:
	doctype = ITEM_DOCTYPES.get(item_type)
	if not doctype:
		frappe.throw(_("Unknown item type: {0}").format(item_type))
	return str(doctype)


@frappe.whitelist()
def update_sort_orders(workbook: str, items: Any) -> None:
	"""Reorder a workbook's sidebar.

	One statement per row rather than a bulk `CASE` update: this is a sidebar,
	so it is tens of rows, and each row still has to be confirmed as belonging
	to this workbook before it is touched.
	"""
	_require("write", workbook)

	for row in _rows(items):
		doctype = _item_doctype(str(row.get("item_type") or ""))
		name = row.get("item_name")
		if not name:
			continue
		# Scoping the update by workbook is the permission check: the caller
		# proved write access to *this* workbook, not to a row it happens to
		# name.
		frappe.db.set_value(
			doctype,
			{"name": name, "workbook": workbook},
			"sort_order",
			cint(row.get("sort_order")),
			update_modified=False,
		)


@frappe.whitelist()
def create_workbook(title: str | None = None) -> str:
	"""A new, empty workbook, owned by whoever asked for it."""
	doc = frappe.get_doc({"doctype": WORKBOOK, "title": _clamp_title(title, _("Untitled Workbook"))})
	doc.insert()
	return str(doc.name)


@frappe.whitelist()
def save_answer(
	agent_run: str,
	workbook: str | None = None,
	title: str | None = None,
	chart: Any = None,
) -> dict[str, Any]:
	"""Land a chat answer in a workbook: the pipeline as a query, the chart with it.

	This is what makes a workbook an output of the Ask surface rather than a
	place you go and build one by hand. Two shapes of the same call: naming a
	`workbook` saves into it, omitting one creates it - "save this answer" and
	"build me a workbook" are the same write with a different target.

	The pipeline is read from the `Nakhoda Agent Run` row, never from the
	caller. That row *is* the answer on screen, and accepting operations from
	the browser would let "save this answer" save a different one - the query
	would then carry SQL nobody had seen the result of. The chart spec does come
	from the caller: it is presentation JSON in the shape `agent/charts.py`
	emits and `Chart.vue` renders, so saving what the user is looking at is the
	honest thing, and re-running the pipeline server-side to re-derive an
	identical spec would double the cost of a save.
	"""
	# `Any`, not `Document`: every field read below is this app's own, and the
	# generic document class Pyright infers from `get_doc` declares none of them.
	run: Any = frappe.get_doc("Nakhoda Agent Run", agent_run)
	run.check_permission("read")
	if run.status != "ok" or not run.operations:
		frappe.throw(_("That answer has no pipeline to save."), title=_("Nothing to save"))

	target = str(workbook) if workbook else create_workbook(title or str(run.question))
	_require("write", target)

	query = frappe.get_doc(
		{
			"doctype": "Nakhoda Query",
			"title": _answer_title(title, str(run.question)),
			"workbook": target,
			"data_source": _answer_source(run),
			"operations": run.operations,
			# A stored artifact that cannot say what produced it is the thing
			# `12-build-plan.md` §4 requires this row to record. The run carries
			# the question, the source, the tier and the model, and Frappe will
			# refuse to delete a run while a query cites it, so the account
			# survives as long as the artifact does.
			"agent_run": run.name,
		}
	).insert()

	spec = _mapping(chart)
	saved_chart = None
	if spec.get("series"):
		saved_chart = frappe.get_doc(
			{
				"doctype": "Nakhoda Chart",
				"title": _answer_title(title, str(run.question)),
				"workbook": target,
				"query": query.name,
				# `charts.pick` only ever infers a bar series (`agent/charts.py`),
				# so this is the one type an answer can arrive as.
				"chart_type": "Bar",
				"config": frappe.as_json(spec),
			}
		).insert()

	return {
		"workbook": target,
		"query": str(query.name),
		"chart": str(saved_chart.name) if saved_chart else None,
	}


@frappe.whitelist()
def add_chart(
	workbook: str, query: str, title: str | None = None, chart_type: str = "Bar", config: Any = None
) -> str:
	"""A chart on a query already in this workbook.

	The query must belong here: a chart whose query lives elsewhere reads a
	pipeline this workbook cannot see, which is the orphan `Nakhoda Chart`
	guards against on save (`nakhoda_chart.py:validate_query_workbook`). The
	default `config` is empty rather than a guessed series - `Chart.vue` renders
	nothing until a spec exists, and inventing one would draw a chart of data
	nobody ran.
	"""
	_require("write", workbook)

	doc = frappe.get_doc(
		{
			"doctype": "Nakhoda Chart",
			"title": _clamp_title(title, _("Untitled Chart")),
			"workbook": workbook,
			"query": query,
			"chart_type": chart_type,
			"config": frappe.as_json(_mapping(config)),
		}
	).insert()
	return str(doc.name)


@frappe.whitelist()
def add_dashboard(workbook: str, title: str | None = None) -> str:
	"""An empty dashboard in this workbook, for charts to be dropped onto."""
	_require("write", workbook)

	doc = frappe.get_doc(
		{
			"doctype": "Nakhoda Dashboard",
			"title": _clamp_title(title, _("Untitled Dashboard")),
			"workbook": workbook,
			"items": frappe.as_json([]),
		}
	).insert()
	return str(doc.name)


TITLE_MAX = 140


def _clamp_title(text: str | None, fallback: str) -> str:
	"""A title that fits the `Data` column it lands in.

	Frappe raises `CharacterLengthExceededError` at 140 characters rather than
	truncating (`frappe/model/base_document.py:1225`), so without this the one
	save that fails is the long question - exactly the answer worth keeping.
	The ellipsis says the name is short for something; a hard cut at 140 reads
	like the user's own typo.
	"""
	text = (text or "").strip()
	if len(text) > TITLE_MAX:
		return text[: TITLE_MAX - 3] + "..."
	return text or fallback


def _answer_title(title: str | None, question: str) -> str:
	"""The question, trimmed to a title. The question *is* the best name a saved
	answer can carry - it is what the user typed and what they will scan for."""
	return _clamp_title(title or question, _("Saved Answer"))


def _answer_source(run: Any) -> str:
	"""Which source answered, re-resolved the way the manager resolved it.

	`Nakhoda Agent Run` records the space, not the connection, so this repeats
	`agent/manager.py:_resolve_source`'s three steps rather than reading a
	field that does not exist. A verified answer names its own source on the
	verified row, which is more specific than the space and so is preferred.
	"""
	from nakhoda.api import default_source

	if run.source == "verified" and run.matched_verified_query:
		named = frappe.db.get_value("Nakhoda Verified Query", run.matched_verified_query, "data_source")
		if named:
			return str(named)
	if run.space:
		space: Any = frappe.get_doc("Nakhoda Space", run.space)
		space.check_permission("read")
		return str(space.resolve_source())
	return default_source()
