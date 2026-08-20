# Copyright (c) 2026, Nakhoda and contributors
# For license information, please see license.txt
"""The `DashboardPatch` grammar: a closed set of ops over `panels[]`
(`Nakhoda Intelligence Template.panels` - "the dashboard's `items[]` shape",
per that doctype's own field description), compiled to a diff and applied
only on approval.

Three ops and nothing else - `docs/plan/12-build-plan.md` Phase 10,
`14-frontend-design.md` §3. An adversarial prompt asking for a write or a
`DROP` fails validation here, before a dry run is even attempted, because
`PATCH_OPS` has no member for it - the same closed-grammar move
`engine/operations.py` makes for the query pipeline, applied to a second
surface (invariant 1).

Removal is a flag, not a deletion. `remove_item` leaves its target in
`panels[]` with `removed: True` set: "The removed card stays on the page
showing what left and why; a patch that silently deletes a chart is a patch
nobody will approve twice" (Phase 10). Reverting later restores the exact
prior array - `NakhodaIntelligenceTemplate.revert` reads it back from
`Nakhoda Dashboard Version.prior_panels` verbatim, "restoring a row, not
replaying an inverse patch" (`12-build-plan.md`'s own words for that
doctype).

Nothing here executes a query, resolves a table or touches a database -
`panels` and `ops` are plain data in and plain data out, which is what lets
the whole grammar and diff run on a bare interpreter
(`tests/test_dashboard.py`). A caller that needs to confirm a referenced
query actually exists compiles that check itself, against a live site - the
same split `nakhoda_query.py` draws between `validate` (grammar, no site) and
`execute` (needs one).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

#: The closed op set. There is no `sql`, `code`, `write` or `delete_table`
#: member - an agent cannot emit what the grammar has no name for.
PATCH_OPS = ("add_chart", "set_filter", "remove_item")

_LAYOUT_KEYS = ("x", "y", "w", "h")
_OPERATORS = ("=", "!=", ">", ">=", "<", "<=", "between", "in")
_OPTIONAL_STRINGS = ("dimension", "measure", "title")


class PatchError(ValueError):
	"""A malformed patch, or one whose `i` names no item on the dashboard."""


def _int(value: Any) -> bool:
	return isinstance(value, int) and not isinstance(value, bool)


def _layout(spec: Any, path: str) -> dict[str, int]:
	if not isinstance(spec, Mapping) or set(spec) != set(_LAYOUT_KEYS):
		raise PatchError(f"{path}.layout: must be an object with exactly {_LAYOUT_KEYS}")
	out = {}
	for key in _LAYOUT_KEYS:
		value = spec[key]
		if not _int(value) or value < 0:
			raise PatchError(f"{path}.layout.{key}: must be a non-negative integer")
		out[key] = value
	return out


def _value_for(operator: str, value: Any, path: str) -> Any:
	if operator == "between":
		if not isinstance(value, Sequence) or isinstance(value, str) or len(value) != 2:
			raise PatchError(f"{path}.value: `between` needs a 2-element list")
	elif operator == "in":
		if not isinstance(value, Sequence) or isinstance(value, str) or len(value) == 0:
			raise PatchError(f"{path}.value: `in` needs a non-empty list")
	return value


def validate_patch(ops: Any) -> list[dict]:
	"""Check patch structure without touching `panels[]`.

	Every op not a member of `PATCH_OPS` is rejected here, unconditionally -
	this is the whole of the adversarial-prompt gate. There is no op that
	writes a row, alters a schema, or carries SQL, so a model that emits one
	fails here because the grammar has no name for it, not because a filter
	caught a keyword in a string.
	"""
	if not isinstance(ops, Sequence) or isinstance(ops, (str, bytes)) or not ops:
		raise PatchError("patch: must be a non-empty list of ops")

	out = []
	for i, op in enumerate(ops):
		path = f"ops[{i}]"
		if not isinstance(op, Mapping):
			raise PatchError(f"{path}: must be an object")
		kind = op.get("op")
		if kind not in PATCH_OPS:
			raise PatchError(f"{path}.op: must be one of {list(PATCH_OPS)}, got {kind!r}")
		_validate_one(op, path)
		out.append(dict(op))
	return out


def _validate_one(op: Mapping, path: str) -> None:
	kind = op["op"]
	if kind == "add_chart":
		chart_type = op.get("chart_type")
		if not isinstance(chart_type, str) or not chart_type:
			raise PatchError(f"{path}.chart_type: must be a non-empty string")
		query = op.get("query")
		if not isinstance(query, str) or not query:
			raise PatchError(f"{path}.query: must name an existing query")
		_layout(op.get("layout"), path)
		for optional in _OPTIONAL_STRINGS:
			value = op.get(optional)
			if value is not None and not isinstance(value, str):
				raise PatchError(f"{path}.{optional}: must be a string")

	elif kind == "set_filter":
		target = op.get("i")
		if not isinstance(target, str) or not target:
			raise PatchError(f"{path}.i: must name the item this filter scopes")
		column = op.get("column")
		if not isinstance(column, str) or not column:
			raise PatchError(f"{path}.column: must be a non-empty string")
		operator = op.get("operator")
		if operator not in _OPERATORS:
			raise PatchError(f"{path}.operator: must be one of {list(_OPERATORS)}, got {operator!r}")
		if "value" not in op:
			raise PatchError(f"{path}.value: required")
		_value_for(operator, op["value"], path)

	else:  # remove_item
		target = op.get("i")
		if not isinstance(target, str) or not target:
			raise PatchError(f"{path}.i: must name the item to remove")


def _index(panels: list[dict], item_id: str, path: str) -> int:
	for idx, item in enumerate(panels):
		if item.get("i") == item_id:
			return idx
	raise PatchError(f"{path}.i: no item {item_id!r} on this dashboard")


def _next_id(panels: list[dict]) -> str:
	existing = set()
	for item in panels:
		item_id = item.get("i")
		if isinstance(item_id, str) and item_id.startswith("chart_"):
			suffix = item_id[len("chart_") :]
			if suffix.isdigit():
				existing.add(int(suffix))
	return f"chart_{(max(existing) + 1) if existing else 1}"


def _scrub(text: Any) -> str:
	"""`frappe.scrub` (`frappe/__init__.py:840`) for the one case this module
	needs - a metric label to the slug a shipped `template.json` writes in
	`measure`. Mirrored rather than imported so the module stays runnable on a
	bare interpreter, the same reason nothing else here touches Frappe."""
	return str(text or "").replace(" ", "_").replace("-", "_").lower()


def normalise(panels: Sequence[Any] | None, metrics: Sequence[Any] | None = None) -> list[dict]:
	"""Canonicalise `panels[]` so every item is patchable and executable.

	A shipped template writes the shape a human writes -
	`{type: "line", title, measure: "net_movement", x: "posting_date"}` - while
	`add_chart` writes the canonical one. Since `_index()` matches on `i`,
	`set_filter` and `remove_item` raised `PatchError` for *every* shipped
	panel: the agent could add a chart to a dashboard but never filter or
	remove one that shipped with it.

	Three fixes, all here:

	- **`i` is stamped** by position (`panel_1`, `panel_2`, ...) on any panel
	  lacking one. Positional so it is stable across calls - the same panel
	  keeps the same id whether it was normalised at import or on read - and
	  distinct from `_next_id`'s `chart_N` so a stamped id can never collide
	  with one the agent is about to mint.
	- **`type`/`x` are mapped** onto `chart_type`/`dimension`. A shipped
	  `type: "line"` names the *geometry*; canonical `type` is always
	  `"chart"`.
	- **`measure` is linked** to the metric whose label scrubs to it. Shipped
	  `"net_movement"` is `scrub("Net Movement")` - the link was intended and
	  no code performed it, which is why panels rendered as title-only
	  placeholders. Resolving to the *label* rather than copying the
	  expression keeps one copy of the expression (on the metric row, where an
	  edit reaches every reader) and makes this idempotent: a normalised
	  `"Net Movement"` scrubs back to the same slug next time.

	Pure, and tolerant by design: an unmatched `measure` is left verbatim
	rather than dropped, so a panel referring to a metric this dashboard no
	longer carries still renders its title instead of vanishing. `metrics`
	rows are read through `.get` rather than as mappings, so a live
	`Nakhoda Intelligence Metric` child row and a `template.json` dict both
	work without this module importing Frappe to tell them apart.
	"""
	by_slug: dict[str, Any] = {}
	for metric in metrics or ():
		label = metric.get("label") if hasattr(metric, "get") else None
		if label:
			by_slug.setdefault(_scrub(label), label)

	out: list[dict] = []
	for idx, panel in enumerate(panels or ()):
		if not isinstance(panel, Mapping):
			continue
		kind = panel.get("type")
		item_id = panel.get("i")
		measure = panel.get("measure")
		out.append(
			{
				**panel,
				"i": item_id if isinstance(item_id, str) and item_id else f"panel_{idx + 1}",
				"type": "chart",
				"chart_type": panel.get("chart_type") or (kind if kind and kind != "chart" else "bar"),
				"query": panel.get("query"),
				"dimension": panel.get("dimension") or panel.get("x"),
				"measure": by_slug.get(_scrub(measure), measure) if measure else measure,
				"title": panel.get("title") or measure or f"panel_{idx + 1}",
				"filters": list(panel.get("filters") or []),
				"removed": bool(panel.get("removed")),
			}
		)
	return out


def apply_patch(panels: Sequence[dict], ops: Any) -> tuple[list[dict], list[dict]]:
	"""Validate `ops`, apply them to `panels`, and return `(new_panels, diff)`.

	`panels` is never mutated in place - the caller's list survives untouched,
	which is what lets it be stored verbatim as `Nakhoda Dashboard
	Version.prior_panels` for a later `revert` to restore.

	`diff` names every touched item: `i`, `title`, `state`
	(`added` / `will_change` / `removed`) and `field` (which field changed,
	or `None` for a removal) - the build-plan's own gate text for what a
	patch preview must render.
	"""
	validated = validate_patch(ops)
	new_panels = [dict(item) for item in panels]
	diff: list[dict] = []

	for op in validated:
		kind = op["op"]
		path = f"ops[{kind}]"

		if kind == "add_chart":
			item_id = _next_id(new_panels)
			item = {
				"i": item_id,
				"type": "chart",
				"chart_type": op["chart_type"],
				"query": op["query"],
				"dimension": op.get("dimension"),
				"measure": op.get("measure"),
				"title": op.get("title") or op["query"],
				"layout": op["layout"],
				"filters": [],
				"removed": False,
			}
			new_panels.append(item)
			diff.append(
				{"i": item_id, "title": item["title"], "state": "added", "field": "layout", "op": kind}
			)

		elif kind == "set_filter":
			idx = _index(new_panels, op["i"], path)
			item = dict(new_panels[idx])
			filters = [f for f in item.get("filters", []) if f.get("column") != op["column"]]
			filters.append({"column": op["column"], "operator": op["operator"], "value": op["value"]})
			item["filters"] = filters
			new_panels[idx] = item
			diff.append(
				{
					"i": item["i"],
					"title": item.get("title") or item["i"],
					"state": "will_change",
					"field": "filters",
					"op": kind,
				}
			)

		else:  # remove_item
			idx = _index(new_panels, op["i"], path)
			item = dict(new_panels[idx])
			item["removed"] = True
			new_panels[idx] = item
			diff.append(
				{
					"i": item["i"],
					"title": item.get("title") or item["i"],
					"state": "removed",
					"field": None,
					"op": kind,
				}
			)

	return new_panels, diff


__all__ = ["PATCH_OPS", "PatchError", "apply_patch", "normalise", "validate_patch"]
