"""What this deployment actually holds, as opposed to what its schema permits.

`model.py` publishes the schema and `retrieval.py` ranks it. Neither can see the two
facts below, because both are properties of the *site* rather than of the DocTypes,
and both were measured to decide questions the schema alone gets wrong.

## Emptiness

On this bench 8,535 of 12,893 columns hold no value in any row - 66% - and 690 of the
1,053 indexed tables hold no rows at all. A column that is empty everywhere cannot
appear in a correct answer, so every token spent describing it is a token taken from
a table the question needed. Pruning them is the difference between 29 and 37 of the
forty gold questions (`test_retrieval.test_pruning_earns_its_place`), and it does two
things at once: `Sales Invoice` costs 2,624 tokens instead of 4,351, so a gold pair
fits where it did not, and the false friends stop matching - a column nobody fills is
still full of words.

The two halves of that profile have very different prices, and only together do they
clear the gate. Tables with **no rows** are free: `row_counts()` already knows which
they are, and every column of a row-less table is empty by definition. Tables **with**
rows need a scan, and that half alone is 33/40 while the free half alone is 29/40.

So the scan is not optional, and it costs 68 seconds across the 388 tables here that
hold rows. `build_index()` runs on every question and already costs 5.2s, so this is
an artifact, not a lookup. A bounded sample was built and measured as the alternative:
it agreed with the exact answer almost everywhere (2 columns of 2,245 called empty
that were filled, no misses, same 37/40) but took **105 seconds** - `LIMIT` inside a
derived table materialises a temporary table per scan, so approximating cost more than
being exact. The exact answer is also the cheap one, which settles it.

It is refreshed where the design already promises the semantic model regenerates -
`bench migrate` - and daily after that, and it is written to the site's private files
as well as the cache because `bench clear-cache` is a normal thing to run and losing
this silently costs eight questions.

## Reporting

Which documents a business already measures is the strongest signal here that the
schema does not carry. `Sales Invoice` and `Purchase Invoice` are indistinguishable
by their columns; on this site 30 dashboard charts, number cards and reports point at
one of them and 21 at the other, and *that* is what the word "revenue" is asking
about. It took recall from 20/40 to 30/40, the single largest gain of any mechanism in
retrieval, and a line table inherits its document's count - a report built on a
document reads its lines - which is worth another five questions on its own.

Three indexed reads over small tables, 0.04s, so this is computed live and never
cached: a chart added this morning should count this morning.

## What is not here

A ledger-derived metric layer, built and rejected. `GL Entry` names the accounts a
business posts revenue and expenses to, so the words in those account names should in
principle bridge "revenue" to `Sales Invoice` where metadata cannot. Measured across
four account root types it earned **nothing** - 30/40 with it and without it - because
the vocabulary it recovers (`carriag`, `drawback`, `rodtep`) is the vocabulary of tax
treatment, not of the question a user asks. The remaining three failures all turn on
the word "revenue", which appears in the vocabulary of exactly zero tables on this
site; that gap is generated prose, which is `Nakhoda Semantic Model`'s job, not a
statistic this module can compute.
"""

from __future__ import annotations

import json

from nakhoda.semantic.model import HAS_COLUMN

#: Where the scan lands. Both stores hold the same JSON: the cache for speed, the file
#: so that clearing the cache costs a millisecond rather than eight questions.
CACHE_KEY = "nakhoda-empty-columns"
ARTIFACT = "nakhoda-empty-columns.json"

#: The DocTypes whose rows say "this business measures that document".
REPORTING_SOURCES = (
	("Dashboard Chart", "document_type"),
	("Number Card", "document_type"),
	("Report", "ref_doctype"),
)


def row_counts() -> dict[str, int]:
	"""Approximate row counts for every table on this site, in one query.

	`information_schema` is an estimate on InnoDB and that is fine: this decides
	whether a table is used at all, not how used it is.
	"""
	import frappe

	rows = frappe.db.sql(
		"""SELECT table_name, table_rows FROM information_schema.tables
		   WHERE table_schema = DATABASE() AND table_name LIKE 'tab%%'"""
	)
	return {name[3:]: int(count or 0) for name, count in rows}


def reporting_counts() -> dict[str, int]:
	"""How many charts, cards and reports on this site point at each DocType."""
	import frappe

	counts: dict[str, int] = {}
	for doctype, field in REPORTING_SOURCES:
		if not frappe.db.table_exists(doctype):
			continue
		for row in frappe.get_all(doctype, fields=[field], limit=0):
			target = row.get(field)
			if target:
				counts[target] = counts.get(target, 0) + 1
	return counts


def _columns(meta) -> list[str]:
	"""Fieldnames of this DocType that are really columns on its table.

	`HAS_COLUMN` is the same allow-list `model.describe()` renders from, so the profile
	can only ever prune a column the model would otherwise have been shown. Every name
	is then checked against the live table, because a field added since the last
	migration exists in the DocType and not yet in MariaDB.
	"""
	import frappe

	named = [
		f.fieldname
		for f in meta.fields
		if f.fieldname and not f.get("is_virtual") and f.fieldtype in HAS_COLUMN
	]
	return [c for c in named if frappe.db.has_column(meta.name, c)]


def _scan(name: str, columns: list[str]) -> list[str]:
	"""Which of these columns hold no value in any row, in one aggregate pass.

	Identifiers are interpolated because SQL cannot parameterise them, and they are
	safe by construction rather than by escaping: both the table and every column came
	out of `frappe.get_meta` and were confirmed present by `frappe.db.has_column`,
	which reads `information_schema`. No caller-supplied string reaches this query.

	Empty means NULL or the empty string. It deliberately does not mean zero: `0` is
	the answer to "how many returns" and a `Check` column of all zeroes is a fact
	about the business, not an unused field.
	"""
	import frappe

	filled = ", ".join(f"SUM(CASE WHEN `{c}` IS NULL OR `{c}` = '' THEN 0 ELSE 1 END)" for c in columns)
	row = frappe.db.sql(f"SELECT {filled} FROM `tab{name}`")[0]
	return [c for c, count in zip(columns, row, strict=True) if not int(count or 0)]


def build() -> dict[str, list[str]]:
	"""Scan the site. One query per table that holds rows; the rest come free.

	Ordered by row count so the expensive tables are done first: if this is ever
	interrupted the partial result is still the useful half.
	"""
	import frappe

	counts = row_counts()
	names = frappe.get_all("DocType", filters={"issingle": 0, "is_virtual": 0}, pluck="name")
	profile: dict[str, list[str]] = {}

	for name in sorted(names, key=lambda n: -counts.get(n, 0)):
		try:
			columns = _columns(frappe.get_meta(name))
			if not columns:
				continue
			profile[name] = columns if not counts.get(name) else _scan(name, columns)
		except Exception:
			# A table that cannot be read is a table this module has nothing to say
			# about; retrieval keeps every column of it rather than guessing.
			frappe.log_error(title=f"Nakhoda: could not profile {name}")
	return profile


def store(profile: dict[str, list[str]]) -> None:
	import frappe

	payload = json.dumps(profile)
	with open(frappe.get_site_path("private", "files", ARTIFACT), "w") as fh:
		fh.write(payload)
	frappe.cache.set_value(CACHE_KEY, payload)


def empty_columns() -> dict[str, frozenset[str]]:
	"""The profile, or nothing at all - never a scan.

	Returning `{}` on a site that has never built one is a real degradation, not a
	silent one: recall falls from 92.5% to 72.5%, `build_index` says so in the log,
	and `bench migrate` fixes it. The alternative - scanning inline - would put 68
	seconds in front of somebody's first question.
	"""
	import frappe

	payload = frappe.cache.get_value(CACHE_KEY)
	if payload is None:
		try:
			with open(frappe.get_site_path("private", "files", ARTIFACT)) as fh:
				payload = fh.read()
		except OSError:
			return {}
		frappe.cache.set_value(CACHE_KEY, payload)

	if isinstance(payload, bytes):
		payload = payload.decode()
	return {name: frozenset(columns) for name, columns in json.loads(payload).items()}


def refresh() -> dict[str, int]:
	"""Rebuild and store the profile. `bench migrate`, daily, or by hand."""
	profile = build()
	store(profile)
	return {"tables": len(profile), "empty_columns": sum(len(v) for v in profile.values())}
