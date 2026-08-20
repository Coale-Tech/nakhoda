# Copyright (c) 2026, Nakhoda and contributors
# For license information, please see license.txt
"""What a person knows about this business that its schema does not say.

`model.py` publishes the schema, `profile.py` publishes what the deployment holds,
and between them they carry retrieval to 37/40 on this bench's gold set. The three
questions they cannot reach ask for "revenue" and "sold" - and the stem `revenu`
appears in **zero** table vocabularies on this site. There is nothing to derive.

Two cheaper mechanisms were built and measured before this one, and both were
deleted (see `retrieval.py` - "What is not here"): a GL-account-derived vocabulary,
because the words those accounts carry are `carriag` and `drawback`; and the titles
of the site's own charts, cards and reports, which recovered nothing and lost a
question, because `revenu` lives only on `GL Entry`'s charts. Declared by hand on
seven documents the same words take recall to **40/40**, and zeroing the weight
returns it to exactly 37/40. That measurement is what this module exists to serve.

## What is evidence, and what is documentation

Only `synonyms` are scored - on the document and on its columns, and from a
*certified* `Nakhoda Metric`, its name and its own synonyms. A metric's
`definition` is not: it is prose written for a person, and prose is why `PROSE`
is weighted 0.4 in `retrieval.py` while curated terms sit at 3.0. A curator who
writes a paragraph should not thereby outvote the schema.

`description` is documentation with one mechanical job: `sync` records its checksum
so `NakhodaSemanticModel.validate` can tell an edited row from a generated one, and
`context()` renders a curated description to the model in place of the DocType's own.
It never changes which tables are selected.

## Why a cache and not an artifact

`profile.py` writes a file because its input costs 68 seconds to compute. This
module's input is three indexed reads over rows that carry text - on this site, a
handful - so a cold cache costs a millisecond and the write hooks on both doctypes
drop it. No file, no `bench migrate` dependency, no way for a curator's edit to be
invisible until something expires.
"""

from __future__ import annotations

import json
from typing import Any

from nakhoda.semantic.model import describe, render
from nakhoda.semantic.profile import empty_columns, reporting_counts, row_counts
from nakhoda.semantic.retrieval import estimate_tokens

#: One entry holding both halves, because both come from the same three queries.
CACHE_KEY = "nakhoda-curation"

MODEL = "Nakhoda Semantic Model"
FIELD = "Nakhoda Semantic Field"
METRIC = "Nakhoda Metric"


def _collect() -> dict[str, dict[str, str]]:
	"""The curated layer as two flat maps, in three queries over non-empty rows.

	Reads nothing when the doctypes have not been migrated yet: this is called from
	`build_index()`, which must keep answering questions on a site mid-install.
	"""
	import frappe

	synonyms: dict[str, list[str]] = {}
	descriptions: dict[str, str] = {}

	if not frappe.db.table_exists(MODEL):
		return {"synonyms": {}, "descriptions": {}}

	for row in frappe.get_all(MODEL, fields=["doctype_name", "synonyms", "description", "curated"]):
		if (row.synonyms or "").strip():
			synonyms.setdefault(row.doctype_name, []).append(row.synonyms)
		if row.curated and (row.description or "").strip():
			descriptions[row.doctype_name] = row.description.strip()

	for row in frappe.get_all(FIELD, filters={"synonyms": ["!=", ""]}, fields=["parent", "synonyms"]):
		synonyms.setdefault(row.parent, []).append(row.synonyms)

	if frappe.db.table_exists(METRIC):
		metrics = frappe.get_all(
			METRIC, filters={"certified": 1}, fields=["document", "metric_name", "synonyms"]
		)
		for row in metrics:
			# The name and its synonyms, never the definition: see the module docstring.
			words = [row.metric_name] + ([row.synonyms] if (row.synonyms or "").strip() else [])
			synonyms.setdefault(row.document, []).extend(words)

	return {
		"synonyms": {name: " ".join(words) for name, words in synonyms.items()},
		"descriptions": descriptions,
	}


def _cached() -> dict[str, dict[str, str]]:
	"""Both maps, from cache when it is warm. Stores JSON like `profile.py` does."""
	import frappe

	payload = frappe.cache.get_value(CACHE_KEY)
	if payload is None:
		collected = _collect()
		frappe.cache.set_value(CACHE_KEY, json.dumps(collected))
		return collected

	if isinstance(payload, bytes):
		payload = payload.decode()
	return json.loads(payload)


def synonyms() -> dict[str, str]:
	"""Curated business words per document, as the text retrieval tokenises."""
	return _cached()["synonyms"]


def descriptions() -> dict[str, str]:
	"""Hand-written descriptions per document, for the prompt to render."""
	return _cached()["descriptions"]


def forget() -> None:
	"""Drop the cache. Called by both writable doctypes' `on_update` / `on_trash`.

	A stale curated index is not a rendering bug: it silently changes which tables a
	question retrieves, so the invalidation lives with the doctypes rather than in a
	scheduled sweep.
	"""
	import frappe

	frappe.cache.delete_value(CACHE_KEY)


def _own_doctypes() -> set[str]:
	"""This app's own tables, which nobody curates.

	Excluded from seeding for two reasons, one product and one structural. A curator
	opening this tab wants `Sales Invoice`, not the fifteen bookkeeping tables the
	analytics tool keeps about itself. And `Nakhoda Semantic Model` cannot have a row
	named after itself at all: `autoname` is `field:doctype_name`, and Frappe refuses
	a docname equal to its doctype name (`naming.py`, "Name of {0} cannot be {0}").

	Nothing is hidden from the model by this: `build_index()` indexes every non-single
	DocType from `get_meta`, so a question about queries still reaches `Nakhoda Query`
	with its generated description. Only the curated layer stops here.
	"""
	import frappe

	modules = frappe.get_all("Module Def", filters={"app_name": "nakhoda"}, pluck="name")
	if not modules:
		return set()
	return set(frappe.get_all("DocType", filters={"module": ["in", modules]}, pluck="name"))


def used_doctypes() -> list[str]:
	"""The documents worth modelling: ones this site writes to, or measures.

	The same two site-derived signals retrieval already prices as priors, reused
	here for a different purpose - deciding what a curator should be shown. Seeding
	all 1,053 DocTypes would bury the 450 that hold a row or carry a chart under six
	hundred empty shells, and make the pass pay for rows nobody will read.
	"""
	counts = row_counts()
	reports = reporting_counts()
	mine = _own_doctypes()
	names = (set(counts) | set(reports)) - mine
	live = [n for n in names if counts.get(n, 0) > 0 or reports.get(n, 0) > 0]
	return sorted(live, key=lambda n: (-reports.get(n, 0), -counts.get(n, 0), n))


def _grain(meta) -> str:
	"""What one row of this table is, in a sentence, from the flags alone."""
	label = (meta.get("name") or "").lower()
	if meta.get("istable"):
		return f"one {label} line, joined to its document by `parent`"
	if meta.get("is_submittable"):
		return f"one {label}, a draft until `docstatus` = 1"
	return f"one {label} record"


def _generated_description(meta, described: dict) -> str:
	"""The description `sync` writes, and the checksum it records.

	The DocType's own description when it has one - that is a sentence somebody
	already wrote about this document - and otherwise the shape, which is at least
	true. Neither is a business definition; that is what a curator is for, and
	`curated` is how this module stops overwriting one.
	"""
	own = (meta.get("description") or "").strip()
	if own:
		return own
	kind = (
		"child table" if meta.get("istable") else ("transaction" if meta.get("is_submittable") else "master")
	)
	return f"{meta.get('name')}: a {kind} with {len(described['columns'])} readable columns."


def _domain(column: dict) -> str:
	"""The column's own controlled vocabulary, as `describe()` already rendered it.

	Enum options and link targets arrive in `notes` as prose; keeping them verbatim
	means a curator reads exactly what the model reads, which is the point of the
	whole surface.
	"""
	return "; ".join(column["notes"])


def _link_target(field) -> str | None:
	"""The DocType a Link column points at, as a name a `Link` field can hold.

	Read off the schema rather than parsed back out of `describe()`'s rendered note
	(`-> "tabCustomer".name`): the note is a sentence for a model, and turning it
	back into a doctype name would be string surgery on prose. `Dynamic Link` is
	excluded because its `options` names a *fieldname* holding the target doctype,
	which is not a doctype - storing it would make the row lie and fail validation.
	"""
	import frappe

	if not field or field.fieldtype != "Link" or not field.options:
		return None
	return field.options if frappe.db.exists("DocType", field.options) else None


def _parents() -> dict[str, set[str]]:
	"""Which documents each child table hangs off, for every child, in two queries.

	`Index` derives this per-meta while it builds; doing the same here would be one
	`get_meta` per DocType on the site. Custom Fields are read separately because a
	child table added by customisation is still a parent.
	"""
	import frappe

	out: dict[str, set[str]] = {}
	table_types = ("Table", "Table MultiSelect")
	for doctype in ("DocField", "Custom Field"):
		rows = frappe.get_all(
			doctype,
			filters={"fieldtype": ["in", table_types], "options": ["!=", ""]},
			fields=["parent" if doctype == "DocField" else "dt as parent", "options"],
		)
		for row in rows:
			out.setdefault(row.options, set()).add(row.parent)
	return out


def sync(doctypes: list[str] | None = None) -> dict[str, int]:
	"""Upsert semantic rows from the live site, preserving everything hand-written.

	`None` means every document that already has a row - which is what
	`after_migrate` wants: a migration is when columns appear and disappear, so the
	generated halves go stale, but a migration is no reason to model a thousand new
	documents. Seeding the used set is an explicit act (`api/semantic.py:regenerate`
	with `used_doctypes()`), because it is the curator who decides what to curate.

	Returns what it did, not what it saw: `preserved` counts rows whose prose this
	call deliberately left alone.
	"""
	import frappe

	from nakhoda.nakhoda.doctype.nakhoda_semantic_model.nakhoda_semantic_model import checksum

	names = doctypes if doctypes is not None else frappe.get_all(MODEL, pluck="doctype_name")
	counts = row_counts()
	reports = reporting_counts()
	unfilled = empty_columns()
	parents = _parents()
	stamp = frappe.utils.now_datetime()

	done = {"created": 0, "updated": 0, "preserved": 0}

	for name in names:
		if not frappe.db.exists("DocType", name):
			continue
		meta = frappe.get_meta(name)
		if meta.get("issingle") or meta.get("is_virtual"):
			continue

		described = describe(meta)
		empty = unfilled.get(name) or frozenset()
		# Looked up by field rather than `frappe.db.exists(MODEL, name)`: that call
		# returns the name unchecked whenever docname equals doctype name ("single
		# always exists (!)", database.py:1275), which for a doctype named after a
		# doctype is a live trap rather than a hypothetical one.
		existing = frappe.db.get_value(MODEL, {"doctype_name": name}, "name")

		if existing:
			doc = frappe.get_doc(MODEL, str(existing))
			done["updated"] += 1
		else:
			doc = frappe.new_doc(MODEL)
			doc.doctype_name = name
			done["created"] += 1

		generated = _generated_description(meta, described)
		if doc.get("curated"):
			# A person has written here. The statistics below are still refreshed -
			# they are measurements, not opinions - but the prose is theirs.
			done["preserved"] += 1
		else:
			doc.description = generated
			doc.grain = _grain(meta)
			doc.source_checksum = checksum(generated)

		doc.label = meta.get("name")
		doc.is_child = 1 if meta.get("istable") else 0
		doc.parent_doctypes = ", ".join(sorted(parents.get(name, ())))
		doc.row_count = int(counts.get(name, 0))
		doc.reporting_count = int(reports.get(name, 0))
		doc.empty_column_count = len(empty)
		doc.token_cost = estimate_tokens(render([described]))
		doc.generated_on = stamp

		# Frappe's child-table diffing deletes and rebuilds rows on save, so the
		# curated half has to be carried across by hand. Keyed by fieldname because
		# that is what a curator was looking at when they wrote it.
		kept = {f.fieldname: f.synonyms for f in doc.get("fields") or [] if (f.synonyms or "").strip()}
		doc.set("fields", [])
		for column in described["columns"]:
			field = meta.get_field(column["name"])
			doc.append(
				"fields",
				{
					"fieldname": column["name"],
					"label": field.label if field else None,
					"fieldtype": column["type"],
					"domain": _domain(column),
					"join_target": _link_target(field),
					"synonyms": kept.get(column["name"]),
					"empty": 1 if column["name"] in empty else 0,
				},
			)

		if existing:
			doc.save(ignore_permissions=True)
		else:
			doc.insert(ignore_permissions=True)

	forget()
	return done


def coverage() -> dict[str, Any]:
	"""What the settings tab reports: how much of this site has been described."""
	import frappe

	modelled = frappe.get_all(MODEL, fields=["curated", "synonyms"])
	metrics = frappe.get_all(METRIC, fields=["certified"])
	with_synonyms = sum(1 for row in modelled if (row.synonyms or "").strip())
	return {
		"used": len(used_doctypes()),
		"modelled": len(modelled),
		"curated": sum(1 for row in modelled if row.curated),
		"with_synonyms": with_synonyms,
		"metrics": len(metrics),
		"certified_metrics": sum(1 for row in metrics if row.certified),
	}
