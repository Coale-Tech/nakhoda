"""Row and column permissions, injected where they cannot be forgotten.

Frappe already decides who may read what. It answers in SQL: a WHERE fragment
from `DatabaseQuery.build_match_conditions()`, and a column list from
`get_permitted_fields()`. This module translates both into the engine's own
terms so that a pipeline compiled for a user is *structurally* incapable of
reading past that user's boundary.

The design decision that matters is where the boundary sits. Insights puts it in
helper functions beside an unfiltered `t(doctype)` that 43 files import, and the
ML surface grew 17 endpoints that never called them (`00-REPORT.md` §6.5); the
same shape produced issue #919. Here there is no unfiltered accessor reachable
from execution: `permitted_resolver()` wraps the connector's resolver, and the
compiler is handed nothing else. Forgetting to apply permissions is not a
mistake you can make in one file - you would have to change the call that builds
the pipeline.

Three rules, all of which fail towards showing less:

*Unmodelled SQL is refused.* The fragment grammar is closed, and it is small
because Frappe's output is small - parentheses, AND/OR, `=`, `IN`, `IS NULL`,
`COALESCE`, qualified columns, string literals. Anything else - a subquery, a
function we do not model, a column qualified with another table, a column the
warehouse does not carry - yields the empty table. A filter we cannot read is
not a filter we may ignore.

*No permission means no rows.* A user with no read access gets zero rows, not an
error and not everything. `PermissionError` from Frappe is an answer, not a
failure.

*Child tables answer to their parents.* A child row is readable when its parent
row is, so the child is semi-joined against the permitted parent set on
(`parent`, `parenttype`). A child table with no readable parent is empty.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any, Protocol

import ibis
import ibis.expr.types as ir
import sqlglot
import sqlglot.expressions as sg

#: A table name (`tabSales Invoice`) to an unfiltered ibis table.
TableResolver = Callable[[str], ir.Table]


class PermissionRefusal(Exception):
	"""Raised internally when a fragment cannot be admitted; never escapes."""


def table_name(doctype: str) -> str:
	"""The warehouse/site table backing a DocType. Frappe's own convention."""
	return f"tab{doctype}"


def doctype_of(table: str) -> str:
	"""Inverse of `table_name`."""
	return table.removeprefix("tab")


# --------------------------------------------------------------------------
# The fragment grammar
# --------------------------------------------------------------------------


def _literal(node: sg.Literal) -> ir.Value:
	if node.is_string:
		return ibis.literal(node.this)
	text = node.name
	try:
		return ibis.literal(int(text))
	except ValueError:
		pass
	try:
		return ibis.literal(float(text))
	except ValueError as exc:
		raise PermissionRefusal(f"uninterpretable literal {text!r}") from exc


def _column(node: sg.Column, table: ir.Table, owner: str) -> ir.Value:
	qualifier = node.table
	if qualifier and qualifier != owner:
		raise PermissionRefusal(f"column qualified with {qualifier!r}, not {owner!r}")
	name = node.name
	if name not in table.columns:
		raise PermissionRefusal(f"column {name!r} is not in the table")
	return table[name]


def _translate(node: sg.Expression, table: ir.Table, owner: str) -> Any:
	"""One node of Frappe's WHERE fragment, as an ibis expression."""
	if isinstance(node, sg.Paren):
		return _translate(node.this, table, owner)
	if isinstance(node, sg.And):
		return _translate(node.this, table, owner) & _translate(node.expression, table, owner)
	if isinstance(node, sg.Or):
		return _translate(node.this, table, owner) | _translate(node.expression, table, owner)
	if isinstance(node, sg.Not):
		return ~_translate(node.this, table, owner)
	if isinstance(node, sg.EQ):
		return _translate(node.this, table, owner) == _translate(node.expression, table, owner)
	if isinstance(node, sg.NEQ):
		return _translate(node.this, table, owner) != _translate(node.expression, table, owner)
	if isinstance(node, sg.Is):
		if isinstance(node.expression, sg.Null):
			return _translate(node.this, table, owner).isnull()
		raise PermissionRefusal("IS against a non-NULL operand")
	if isinstance(node, sg.In):
		if node.args.get("query") is not None:
			raise PermissionRefusal("IN over a subquery")
		values = [_translate(v, table, owner) for v in node.expressions]
		if not values:
			raise PermissionRefusal("empty IN list")
		return _translate(node.this, table, owner).isin(values)
	if isinstance(node, sg.Coalesce):
		rest = node.expressions or []
		out = _translate(node.this, table, owner)
		for alternative in rest:
			out = out.coalesce(_translate(alternative, table, owner))
		return out
	if isinstance(node, sg.Column):
		return _column(node, table, owner)
	if isinstance(node, sg.Literal):
		return _literal(node)
	if isinstance(node, sg.Boolean):
		return ibis.literal(bool(node.this))
	if isinstance(node, sg.Null):
		return ibis.null()
	raise PermissionRefusal(f"unmodelled node {type(node).__name__}")


def row_filter(fragment: str, table: ir.Table, owner: str) -> ir.BooleanValue | None:
	"""Frappe's WHERE fragment as an ibis predicate, or None if it cannot be read.

	`owner` is the table name the fragment is expected to qualify its columns
	with. Returning None means *refuse*, and every caller turns it into an empty
	table - never into an unfiltered one.
	"""
	try:
		parsed = sqlglot.parse_one(fragment, read="mysql")
	except Exception:
		return None
	try:
		out = _translate(parsed, table, owner)
	except PermissionRefusal:
		return None
	except Exception:
		return None
	if not isinstance(out, ir.BooleanValue):
		return None
	return out


def empty(table: ir.Table) -> ir.Table:
	"""The table, guaranteed to yield no rows.

	A literal predicate is a valid filter at runtime and keeps the shape the
	pipeline expects: an empty result, not a missing table.
	"""
	return table.filter(ibis.literal(False))  # type: ignore[arg-type]


# --------------------------------------------------------------------------
# What Frappe is asked
# --------------------------------------------------------------------------


class Policy(Protocol):
	"""Everything the engine needs to know about one user's access.

	Three questions, and the seam exists so all three can be answered from a
	recorded transcript instead of a live site. Gate B has to prove fail-closed
	behaviour, two-user divergence and child-table grain *deterministically*;
	against a live site those properties are only as strong as whatever
	permissions that site happens to carry today. `FrappePolicy` is the
	production answer and the live tests check that it returns what the offline
	tests replay.
	"""

	def columns(self, doctype: str) -> set[str] | None:
		"""Readable columns, or None for "all of them"."""

	def rows(self, doctype: str) -> tuple[bool, str | None]:
		"""`(allowed, fragment)`. False means no access; None means no restriction."""

	def parents(self, child_doctype: str) -> list[str]:
		"""DocTypes that carry `child_doctype` as a child table."""

	def is_child(self, doctype: str) -> bool:
		"""Whether rows of `doctype` belong to a parent document."""


class FrappePolicy:
	"""The production policy: Frappe answers, we translate."""

	def __init__(self, user: str) -> None:
		self.user = user

	def columns(self, doctype: str) -> set[str] | None:
		from frappe.model import get_permitted_fields

		if not self.is_child(doctype):
			return set(get_permitted_fields(doctype, user=self.user))

		# A child DocType carries no permissions of its own, and Frappe says so
		# by returning *nothing* for one asked about without a `parenttype`
		# (`model/meta.py:698-699`). `get_permitted_fields` then falls back to
		# `default_fields` and withholds `parent`/`parenttype` with it
		# (`model/__init__.py:254-258`), so every line-item table arrived here as
		# seven framework columns: measured on `jkm` 2026-08-17, `Sales Invoice
		# Item` 168 -> 7, which is why "revenue by item group" could not be
		# answered at all and the model was blamed for naming `parent`.
		#
		# Ask once per parent, as the row rule already does, and union: a child
		# row is readable exactly when one of its parent rows is, so its columns
		# are readable on that same grain. A parent whose rows are denied
		# contributes neither rows nor columns.
		fields: set[str] = set()
		for parent in self.parents(doctype):
			if not self.rows(parent)[0]:
				continue
			fields |= set(get_permitted_fields(doctype, parenttype=parent, user=self.user))
		return fields

	def rows(self, doctype: str) -> tuple[bool, str | None]:
		"""Frappe's row filter, with its two absences kept apart.

		An empty string from Frappe means *unrestricted*; treating it as denied
		would make the engine useless, and treating a denial as unrestricted is
		issue #919.
		"""
		import frappe
		from frappe.model.db_query import DatabaseQuery

		try:
			if not frappe.has_permission(doctype, "read", user=self.user):
				return False, None
			condition = DatabaseQuery(doctype, user=self.user).build_match_conditions()
		except frappe.PermissionError:
			return False, None
		if not condition:
			return True, None
		return True, str(condition)

	def parents(self, child_doctype: str) -> list[str]:
		import frappe

		fieldtypes = ["Table", "Table MultiSelect"]
		standard = frappe.get_all(
			"DocField",
			filters={"fieldtype": ["in", fieldtypes], "options": child_doctype},
			pluck="parent",
			distinct=True,
		)
		custom = frappe.get_all(
			"Custom Field",
			filters={"fieldtype": ["in", fieldtypes], "options": child_doctype},
			pluck="dt",
			distinct=True,
		)
		return sorted(set(standard) | set(custom))

	def is_child(self, doctype: str) -> bool:
		import frappe

		return bool(getattr(frappe.get_meta(doctype), "istable", 0))


# --------------------------------------------------------------------------
# Applying it
# --------------------------------------------------------------------------


def _projected(table: ir.Table, allowed: set[str] | None) -> ir.Table:
	"""`table` narrowed to `allowed`, or emptied when it admits nothing that is
	actually there.

	`None` means unrestricted, which is not the same as an empty set: one is
	"every column", the other is "no column", and conflating them is how a
	fail-closed layer starts failing open.
	"""
	if allowed is None:
		return table
	keep = [c for c in table.columns if c in allowed]
	if not keep:
		return empty(table)
	return table.select(keep) if len(keep) != len(table.columns) else table


def permitted(table: ir.Table, doctype: str, policy: Policy, resolve: TableResolver) -> ir.Table:
	"""`table`, restricted to the rows and columns this policy admits.

	Fails closed: any refusal along the way yields zero rows.
	"""
	if policy.is_child(doctype):
		# The parent-row rule joins on `parent`/`parenttype`, so it runs before
		# the projection: those two are a structural need of the rule, not data
		# the caller asked for, and a column policy that did not admit them used
		# to switch the rule off by deleting them - a permission rule failing
		# open with nothing to see.
		gated = _permitted_child(table, doctype, policy, resolve)
		return _projected(gated, policy.columns(doctype))

	projected = _projected(table, policy.columns(doctype))
	allowed, condition = policy.rows(doctype)
	if not allowed:
		return empty(projected)
	if condition is None:
		return projected
	predicate = row_filter(condition, projected, table_name(doctype))
	if predicate is None:
		return empty(projected)
	return projected.filter(predicate)


def _permitted_child(child: ir.Table, doctype: str, policy: Policy, resolve: TableResolver) -> ir.Table:
	"""A child row is readable exactly when its parent row is."""
	if "parent" not in child.columns or "parenttype" not in child.columns:
		return empty(child)

	readable = []
	for parent_doctype in policy.parents(doctype):
		try:
			parent_table = resolve(table_name(parent_doctype))
		except Exception:
			continue
		if "name" not in parent_table.columns:
			continue
		rows = permitted(parent_table, parent_doctype, policy, resolve)
		readable.append(
			rows.select(
				__nk_parent=rows["name"],
				__nk_parenttype=ibis.literal(parent_doctype),
			)
		)
	if not readable:
		return empty(child)

	keys = readable[0]
	for more in readable[1:]:
		keys = keys.union(more)
	return child.semi_join(
		keys,
		[child["parent"] == keys["__nk_parent"], child["parenttype"] == keys["__nk_parenttype"]],
	)


def permitted_resolver(resolve: TableResolver, policy: Policy) -> TableResolver:
	"""The only resolver execution is given.

	Wrapping at this seam is what makes the boundary structural: a compiled
	pipeline never holds a reference to an unfiltered table, so there is no call
	site that can forget to filter one.
	"""

	def resolver(name: str) -> ir.Table:
		return permitted(resolve(name), doctype_of(name), policy, resolve)

	return resolver


def _referenced_columns(node: sg.Expression) -> set[str]:
	"""Every column name Frappe's WHERE fragment mentions, for naming a
	permission notice ("territory permissions") without guessing."""
	return {c.name for c in node.find_all(sg.Column)}


def excluded(
	table: ir.Table, doctype: str, policy: Policy, resolve: TableResolver
) -> tuple[ir.Table, str] | None:
	"""The structural complement of `permitted()`'s row filter: the rows a
	policy's row-level condition hides from `table`, plus a human reason
	naming the restricted field(s) - `"territory permissions"`, not
	`"restricted"`.

	`None` when there is nothing reportable, by the same fail-toward-less
	rule `permitted()` follows: a child doctype (its grain is its parent's,
	not its own - reporting excluded child rows independent of parent
	visibility would double-count or misattribute them), global read denial
	(no row-level fragment to name; `permitted()` already shows zero rows,
	which is its own answer), no restriction at all, or a fragment this
	module cannot read. A notice that cannot name what it excluded is not a
	notice this module will show.
	"""
	if policy.is_child(doctype):
		return None

	allowed_columns = policy.columns(doctype)
	if allowed_columns is None:
		projected = table
	else:
		keep = [c for c in table.columns if c in allowed_columns]
		if not keep:
			return None
		projected = table.select(keep) if len(keep) != len(table.columns) else table

	allowed, condition = policy.rows(doctype)
	if not allowed or not condition:
		return None
	predicate = row_filter(condition, projected, table_name(doctype))
	if predicate is None:
		return None
	try:
		columns = sorted(_referenced_columns(sqlglot.parse_one(condition, read="mysql")))
	except Exception:
		return None
	if not columns:
		return None

	return projected.filter(~predicate), " and ".join(columns) + " permissions"


def excluded_resolver(resolve: TableResolver, policy: Policy) -> tuple[TableResolver, dict[str, str]]:
	"""The complement of `permitted_resolver()`: a resolver yielding the rows
	each table's row filter hides, for re-running an identical pipeline to
	measure what permissions removed from it. `reasons` fills in as tables
	are resolved during compilation - a pipeline may touch more than one.

	Raises `PermissionRefusal` from `excluded()` returning `None`, so a
	caller compiling a pipeline against this resolver gets a clean exception
	when nothing here is reportable, rather than a resolver that silently
	returns an unfiltered table.
	"""
	reasons: dict[str, str] = {}

	def resolver(name: str) -> ir.Table:
		doctype = doctype_of(name)
		found = excluded(resolve(name), doctype, policy, resolve)
		if found is None:
			raise PermissionRefusal(f"no reportable exclusion for {name!r}")
		table, reason = found
		reasons[name] = reason
		return table

	return resolver, reasons


def filters_applied(doctypes: Iterable[str], policy: Policy) -> list[dict[str, str]]:
	"""Which of `doctypes` carry a row-level permission filter `permitted()`
	would apply while compiling a pipeline that touches them - read-only
	provenance for display, never a step the compiled pipeline itself
	contains.

	This is deliberately not `excluded()`'s job: `excluded()` computes the
	*rows* a filter hides, which needs `resolve` and an executed query and
	fails closed when anything is unreadable. This only names *whether* a
	filter was structurally injected and which column(s) it names, from the
	same policy answer `permitted()` itself asks - so it is always available,
	even when a pipeline never runs (an inspector rendering a cached answer)
	or `excluded()` refuses. Same fail-toward-less rule: a child doctype, a
	global denial, no restriction, or an unreadable fragment all contribute
	nothing rather than a guess.
	"""
	applied: list[dict[str, str]] = []
	for doctype in doctypes:
		if policy.is_child(doctype):
			continue
		allowed, condition = policy.rows(doctype)
		if not allowed or not condition:
			continue
		try:
			columns = sorted(_referenced_columns(sqlglot.parse_one(condition, read="mysql")))
		except Exception:
			continue
		if not columns:
			continue
		applied.append({"table": table_name(doctype), "reason": " and ".join(columns) + " permissions"})
	return sorted(applied, key=lambda entry: entry["table"])


def for_user(resolve: TableResolver, user: str) -> TableResolver:
	"""The production entry point for DocType-backed sources: a resolver bound
	to a Frappe user."""
	return permitted_resolver(resolve, FrappePolicy(user))


class UnrestrictedPolicy:
	"""The policy for tables Frappe has no rules about.

	Every answer is the widest one, and each is a statement rather than a
	shortcut: a foreign schema has no `tabDocPerm` row to read (`rows`), no
	permitted-field list (`columns`), and no parent/child relationship Frappe
	models (`is_child`, `parents`). Saying so through the same Protocol the
	filtered path uses is what keeps external sources inside the one boundary
	instead of beside it - `permitted()` still wraps their tables, it simply
	finds nothing to remove, and `pipeline.notice()`/`injected()` report no
	filter because there is none to report rather than because nobody asked.
	"""

	def columns(self, doctype: str) -> set[str] | None:
		return None

	def rows(self, doctype: str) -> tuple[bool, str | None]:
		return True, None

	def parents(self, child_doctype: str) -> list[str]:
		return []

	def is_child(self, doctype: str) -> bool:
		return False


class SourceConnector(Protocol):
	"""What the two entry points below need from a connector, without importing
	one. `nakhoda.connectors.Connector` satisfies this; the engine stays
	ignorant of drivers, and a test can hand in anything of the same shape.
	"""

	@property
	def describes_doctypes(self) -> bool:
		"""Whether this backend's tables are the ones `tabDocPerm` describes."""

	def resolve(self, table: str) -> ir.Table:
		"""The unfiltered table."""


def policy_for(connector: SourceConnector, user: str) -> Policy:
	"""Which access rules describe this source's tables.

	One decision, made by the thing that knows, so that the four execution
	paths (`api/__init__.py`, `api/templates.py`, `Nakhoda Query`,
	`Nakhoda Verified Query`) cannot disagree about it. The alternative - each
	endpoint testing `source_type` before choosing - is the shape that produced
	Insights issue #919: several places that must agree, and one added later
	that does not.
	"""
	return FrappePolicy(user) if connector.describes_doctypes else UnrestrictedPolicy()


def for_connector(connector: SourceConnector, user: str) -> TableResolver:
	"""The resolver every execution path builds, whatever the source is.

	Still `permitted_resolver`, always: the invariant this module opens with -
	nothing reachable from execution holds an unwrapped table - would be worth
	nothing if external sources were the documented exception to it. What
	changes for them is the policy, not the wrapping, and an unrestricted policy
	costs nothing at compile time (`permitted()` returns the table untouched
	when there is no column list and no row fragment).
	"""
	return permitted_resolver(connector.resolve, policy_for(connector, user))
