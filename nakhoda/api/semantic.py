# Copyright (c) 2026, Nakhoda and contributors
# For license information, please see license.txt
"""The semantic layer as a surface: what is described, and what a curator changed.

Two inputs on `Nakhoda Semantic Model` reach the engine, and this module exposes
exactly those two:

  `synonyms` - words a person declares for a document. They enter retrieval's index
  as a term set weighted like the table's own name (`semantic/retrieval.py:CURATED`),
  and they are the only reason the three "revenue"/"sold" questions in the gold set
  resolve to `Sales Invoice`: nothing derivable from this schema says that word. Seven
  documents named takes measured recall from 37/40 to 40/40.

  `description` - prose the model reads instead of the generated sentence, once
  `curated` is set. It cannot change which tables are retrieved (selection happens
  before rendering), so the two halves stay separable: synonyms move answers, prose
  explains them.

Everything else on the row is derived and read-only here: grain, columns, row and
reporting counts, token cost. `curation.sync()` writes them on every `bench migrate`
and refuses to touch a row a curator has edited, which is why `save` sets `curated`
rather than a "locked" flag - the flag *is* the fact that a person wrote it.

`Nakhoda Metric` is not editable through this module. It is a named, permissioned
doctype with `field:metric_name` autoname and full Desk CRUD; a second half-editor
here would be a worse version of a screen the framework already ships. Its certified
names and synonyms do feed retrieval (see `curation._collect`), and `coverage()`
counts them, so the settings tab can say how many exist and link to them.
"""

from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils.background_jobs import is_job_enqueued

from nakhoda.semantic import curation

MODEL = curation.MODEL

#: One id for the whole pass, so RQ rejects a second concurrent regenerate. Not
#: per-doctype like the Data Store's: this job's unit of work is the site.
JOB_ID = "nakhoda-semantic-sync"

#: What `list_models` returns per row. Derived columns are here because the tab
#: ranks by them - a curator works down from the documents this site actually uses.
#: `description` is not: every row has one (generated if nobody wrote it), so it
#: separates nothing in a list, and 428 essays is not a payload a search box needs.
#: `synonyms` is, because it is short and it is exactly what a curator scans for.
LIST_FIELDS = [
	"name",
	"doctype_name",
	"label",
	"grain",
	"synonyms",
	"curated",
	"is_child",
	"row_count",
	"reporting_count",
	"empty_column_count",
	"token_cost",
	"generated_on",
]


def _require_admin() -> None:
	frappe.only_for(("Nakhoda Admin", "System Manager"))


@frappe.whitelist()
def coverage() -> dict[str, Any]:
	"""How much of this site has been described, and how much by hand.

	Readable by anyone who can ask a question: it is a count of rows, not their
	contents, and the settings tab shows it before deciding whether to offer the
	seeder.
	"""
	frappe.has_permission(MODEL, "read", throw=True)
	return curation.coverage()


@frappe.whitelist()
def list_models(search: str | None = None, curated_only: int | bool = 0) -> list[dict[str, Any]]:
	"""Described documents, the ones this site leans on first.

	Ordered by reporting count then rows - the same two site-derived signals
	retrieval prices as priors - so the first screen holds the documents whose
	description is worth writing. Search matches the DocType name and the label,
	not the prose: a curator looking for `Sales Invoice` is not searching essays.
	"""
	frappe.has_permission(MODEL, "read", throw=True)

	filters: dict[str, Any] = {}
	if int(curated_only or 0):
		filters["curated"] = 1

	or_filters = None
	if search and search.strip():
		needle = f"%{search.strip()}%"
		or_filters = {"doctype_name": ["like", needle], "label": ["like", needle]}

	return frappe.get_all(
		MODEL,
		fields=LIST_FIELDS,
		filters=filters,
		or_filters=or_filters,
		order_by="reporting_count desc, row_count desc, doctype_name asc",
	)


@frappe.whitelist()
def get_model(name: str) -> dict[str, Any]:
	"""One document's semantic row, with its columns.

	The child rows carry per-column synonyms, which are read by retrieval the same
	way the parent's are - a column nobody named `revenue` can still be found by it.
	"""
	frappe.has_permission(MODEL, "read", throw=True)

	doc = frappe.get_doc(MODEL, name)
	return {
		"name": doc.name,
		"doctype_name": doc.doctype_name,
		"label": doc.label,
		"grain": doc.grain,
		"description": doc.description,
		"synonyms": doc.synonyms,
		"curated": bool(doc.curated),
		"is_child": bool(doc.is_child),
		"parent_doctypes": doc.parent_doctypes,
		"row_count": doc.row_count,
		"reporting_count": doc.reporting_count,
		"empty_column_count": doc.empty_column_count,
		"token_cost": doc.token_cost,
		"generated_on": doc.generated_on,
		"fields": [
			{
				"fieldname": row.fieldname,
				"label": row.label,
				"fieldtype": row.fieldtype,
				"domain": row.domain,
				"join_target": row.join_target,
				"synonyms": row.synonyms,
				"empty": bool(row.empty),
			}
			for row in doc.fields
		],
	}


@frappe.whitelist()
def save_model(
	name: str,
	description: str | None = None,
	synonyms: str | None = None,
	field_synonyms: str | dict[str, str] | None = None,
) -> dict[str, Any]:
	"""Write the curated half of one row: prose, document synonyms, column synonyms.

	`curated` is not a parameter and is not set here. `NakhodaSemanticModel.validate`
	derives it from what the row now holds - a description that no longer matches its
	recorded checksum, or any synonym anywhere on it - which means clearing the fields
	hands the document back to the generator, and no caller can mark a row curated
	without curating it.

	Writes through `doc.save()`, so the controller's `on_update` drops the curated
	cache: a saved synonym changes retrieval on the next question, not after the next
	restart.
	"""
	_require_admin()

	doc = frappe.get_doc(MODEL, name)
	if description is not None:
		doc.description = description.strip()
	if synonyms is not None:
		doc.synonyms = synonyms.strip()

	if field_synonyms:
		owned: dict[str, str] = dict(
			frappe.parse_json(field_synonyms) if isinstance(field_synonyms, str) else field_synonyms
		)
		by_fieldname = {row.fieldname: row for row in doc.fields}
		# Validated before anything is applied: a payload naming one column that no
		# longer exists is a stale client, and half-writing it would leave the row
		# describing a schema nobody has.
		unknown = sorted(set(owned) - set(by_fieldname))
		if unknown:
			frappe.throw(
				_("{0} has no column {1}").format(doc.doctype_name, unknown[0]),
				title=_("Unknown Column"),
			)
		for fieldname, words in owned.items():
			by_fieldname[fieldname].synonyms = (words or "").strip()

	doc.save()
	return get_model(name)


@frappe.whitelist()
def regenerate(seed: int | bool = 0) -> dict[str, Any]:
	"""Re-derive the generated half of every row, preserving hand-written ones.

	Enqueued, not inline: seeding this site is 439 documents and 8,369 columns, and it
	measured 31s - under gunicorn's timeout, but not a spinner to hand a browser, and
	it grows with every DocType a site installs.

	The busy check is `is_job_enqueued` alone, and that is deliberately weaker than
	`api/data_store.py`'s: RQ forgets a job once a worker picks it up, so a second
	click mid-run will enqueue a second pass. Here that costs duplicated work and
	nothing else - `sync` is an upsert that preserves every hand-written field - which
	is not true of two concurrent writers of one DuckDB table, which is why that
	surface pays for a log row and this one does not.

	`seed` widens the pass from "every document already described" to "every document
	this site actually uses" (`curation.used_doctypes`). It is a separate flag rather
	than the default because seeding is a decision about what to curate, and a
	migration should not make it on a curator's behalf.
	"""
	_require_admin()

	if is_job_enqueued(JOB_ID):
		return {"queued": False, "reason": "in_progress"}

	names = curation.used_doctypes() if int(seed or 0) else None
	frappe.enqueue(
		"nakhoda.api.semantic.run_regenerate",
		queue="long",
		job_id=JOB_ID,
		doctypes=names,
	)
	return {"queued": True, "documents": len(names) if names is not None else None}


def run_regenerate(doctypes: list[str] | None = None) -> None:
	"""The enqueued half of `regenerate`. Never raises to the worker.

	A failure here leaves the previous rows intact - they are stale, not wrong - so
	it is logged and dropped rather than retried: the next `bench migrate` runs the
	same pass, and a curator's words were never at risk.
	"""
	try:
		done = curation.sync(doctypes)
		frappe.logger("nakhoda").info(f"semantic curation sync: {done}")
	except Exception:
		frappe.log_error(title="Nakhoda semantic curation sync failed")
