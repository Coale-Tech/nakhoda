# Copyright (c) 2026, Nakhoda and contributors
# For license information, please see license.txt
"""Who may read and write a workbook, and the things inside one.

Not to be confused with `nakhoda/engine/permissions.py`, which decides which
*rows and columns of site data* a pipeline may read. This module decides who
may open a `Nakhoda Workbook` document and the queries, charts, dashboards and
folders that name it.

The distinction matters because the workbook family cannot express its access
rule with DocType permissions alone. A workbook is private to whoever made it
until they share it, and DocType permissions have no per-row notion beyond
`if_owner` - which would make sharing impossible, because a share is precisely
an exception to ownership. So the roles carry `read`/`write` on the whole table
and this module narrows that, exactly the way Frappe intends: `has_permission`
hooks are consulted only after role permissions already allow, so a hook can
refuse but never grant.

Two hooks, because Frappe asks two different questions:

- `has_permission` - one document, already loaded. Called by
  `doc.check_permission()`, so it guards every save, delete and whitelisted
  method that checks.
- `permission_query_conditions` - a SQL fragment appended to list queries, so
  `frappe.get_list` never returns a row the reader could not open. Without it
  the list page would show titles that refuse when clicked.

The rule, one sentence: a document is yours if you own it, if it is shared with
you (or with everyone), or if it belongs to a workbook that is. That last
clause is what makes sharing a workbook mean something - a reader who gets the
container gets its contents, without a `DocShare` row per query. It is the same
rule Insights implements in `insights/permissions.py`, minus teams, which this
app does not have.

`Nakhoda Query` is the one child whose `workbook` may be empty: the agent saves
ad-hoc queries that belong to no container. Those stay owner-only, which is why
the transitive clause is a third alternative rather than a replacement.

Naming note: `DocShare.share_name` is `varchar` while these DocTypes are
`autoincrement`, so `name` is an integer. The comparisons below cast the name
to text rather than letting MariaDB coerce the column - coercion compares as
numbers, which is correct here but silently unusable for the `share_name` index.
"""

from __future__ import annotations

import frappe

WORKBOOK = "Nakhoda Workbook"

#: The doctypes this module governs. Everything else is left to role
#: permissions - notably `Nakhoda Verified Query` and the intelligence
#: templates, which are deliberately organisation-wide.
FAMILY = (WORKBOOK, "Nakhoda Query", "Nakhoda Chart", "Nakhoda Dashboard", "Nakhoda Folder")

#: Children carry a `workbook` Link; the workbook itself does not.
CHILDREN = FAMILY[1:]

#: Roles that see everything. `Nakhoda Admin` is the app's own administrator
#: role; `System Manager` is Frappe's, and a site administrator who cannot read
#: a workbook cannot support the person who owns it.
ADMIN_ROLES = frozenset({"Nakhoda Admin", "System Manager"})

#: `DocShare` has one column per access level. Anything that is not a read or a
#: share is a mutation, and one `write` flag governs all of them: a reader who
#: could delete what they cannot edit would be a strange kind of reader.
_SHARE_LEVELS = frozenset({"read", "write", "share"})


def _is_admin(user: str) -> bool:
	return user == "Administrator" or bool(ADMIN_ROLES & set(frappe.get_roles(user)))


def _level(ptype: str) -> str:
	return ptype if ptype in _SHARE_LEVELS else "write"


def _shared(doctype: str, name: str | int, level: str, user: str) -> bool:
	"""Is this exact document shared with this user, or with everyone?"""
	share = frappe.qb.DocType("DocShare")
	return bool(
		frappe.qb.from_(share)
		.select(share.name)
		.where(share.share_doctype == doctype)
		.where(share.share_name == str(name))
		.where(share[level] == 1)
		.where((share.user == user) | (share.everyone == 1))
		.limit(1)
		.run()
	)


def _may_use_workbook(name: str | int | None, level: str, user: str) -> bool:
	"""Access to a workbook by name, without loading it.

	`frappe.db.get_value` rather than `frappe.get_doc`: this runs inside a
	permission check, and loading the parent document would re-enter this same
	function through the parent's own check.
	"""
	if not name:
		return False
	owner = frappe.db.get_value(WORKBOOK, name, "owner")
	if owner is None:
		# A child pointing at a workbook that no longer exists. Ownership of the
		# child is the only thing left to go on, and the caller checked it first.
		return False
	if owner == user:
		return True
	return _shared(WORKBOOK, name, level, user)


def has_doc_permission(doc, ptype: str, user: str) -> bool:
	"""Narrow role permissions to ownership plus explicit sharing."""
	if doc.doctype not in FAMILY:
		return True
	if _is_admin(user):
		return True

	level = _level(ptype)

	# A document being created has no name to share and no stored owner yet. If
	# it names a workbook, the workbook decides - this is the check that stops a
	# reader adding a query to somebody else's workbook. `write`, not `level`:
	# creating inside a container mutates that container even though `ptype`
	# here is `create`.
	if doc.is_new():
		workbook = doc.get("workbook") if doc.doctype in CHILDREN else None
		if workbook:
			return _may_use_workbook(workbook, "write", user)
		return True

	if doc.owner == user:
		return True
	if _shared(doc.doctype, doc.name, level, user):
		return True
	if doc.doctype in CHILDREN:
		return _may_use_workbook(doc.get("workbook"), level, user)
	return False


def get_permission_query_conditions(user: str | None, doctype: str) -> str:
	"""A `WHERE` fragment restricting list queries to readable documents.

	Only `read` is expressed here. Frappe applies these conditions to reads;
	writes go through `has_doc_permission` above, one document at a time.
	"""
	user = str(user or frappe.session.user)
	if doctype not in FAMILY:
		return ""
	if _is_admin(user):
		return ""

	if doctype == WORKBOOK:
		return f"({_readable_sql(WORKBOOK, user)})"

	# The transitive clause, as a correlated EXISTS over the parent table: a
	# child is readable when its workbook is. A subquery rather than a join
	# because these conditions are appended to a query whose shape this module
	# does not control.
	parent = (
		"exists (select 1 from `tabNakhoda Workbook` where"
		f" `tabNakhoda Workbook`.name = `tab{doctype}`.workbook"
		f" and ({_readable_sql(WORKBOOK, user)}))"
	)
	return f"({_readable_sql(doctype, user)} or {parent})"


def _readable_sql(doctype: str, user: str) -> str:
	"""`owner is me, or a DocShare says read`, for one table."""
	table = f"tab{doctype}"
	quoted = frappe.db.escape(user)
	return (
		f"`{table}`.owner = {quoted}"
		" or exists (select 1 from `tabDocShare` where"
		f" `tabDocShare`.share_doctype = {frappe.db.escape(doctype)}"
		f" and `tabDocShare`.share_name = cast(`{table}`.name as char)"
		" and `tabDocShare`.`read` = 1"
		f" and (`tabDocShare`.user = {quoted} or `tabDocShare`.everyone = 1))"
	)
