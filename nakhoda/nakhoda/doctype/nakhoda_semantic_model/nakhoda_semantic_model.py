# Copyright (c) 2026, Nakhoda and contributors
# For license information, please see license.txt
"""One DocType as the semantic layer describes it - half generated, half authored.

`semantic/model.py` derives everything a schema can state: columns, types, enum
domains, link targets. `semantic/profile.py` adds what the deployment holds: row
counts, reporting artifacts, columns nobody fills. Both are measured, and together
they take gold recall to 37/40 on this bench. This doctype exists for the other
three questions, which no statistic over this schema can reach: they ask about
"revenue" and "sold", and the stem `revenu` appears in zero table vocabularies on
this site. Deriving those words from the site's own chart and report titles was
tried and measured worse (0 recovered, 1 lost). Declared by hand on seven
documents, they take recall to 40/40.

So `synonyms` and `description` are the load-bearing fields here, and everything
under the Derivation section is evidence rather than input: `semantic/curation.py`
writes it on `bench migrate` and refuses to overwrite the two prose fields once a
person has touched them. `curated` is how it tells the difference, which is the
only judgement this controller makes.

Read by `semantic/curation.py:synonyms()` through a cache, so the two write hooks
below are not housekeeping: without them a curator's edit is invisible until the
cache expires, which is the kind of bug that gets blamed on the model.
"""

from __future__ import annotations

import hashlib

from frappe.model.document import Document


def checksum(text: str | None) -> str:
	"""The fingerprint `sync` records and `validate` compares against.

	Short on purpose - this distinguishes "a person edited this" from "the generator
	wrote it", a question with two answers, not a security boundary.
	"""
	return hashlib.sha256((text or "").encode()).hexdigest()[:16]


class NakhodaSemanticModel(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		from nakhoda.nakhoda.doctype.nakhoda_semantic_field.nakhoda_semantic_field import (
			NakhodaSemanticField,
		)

		curated: DF.Check
		description: DF.SmallText | None
		doctype_name: DF.Link
		empty_column_count: DF.Int
		fields: DF.Table[NakhodaSemanticField]
		generated_on: DF.Datetime | None
		grain: DF.Data | None
		is_child: DF.Check
		label: DF.Data | None
		parent_doctypes: DF.SmallText | None
		reporting_count: DF.Int
		row_count: DF.Int
		source_checksum: DF.Data | None
		synonyms: DF.SmallText | None
		token_cost: DF.Int
	# end: auto-generated types

	def validate(self) -> None:
		"""Decide whether this row is still the generator's or a person's now.

		Two ways to have curated a document, and both count: writing synonyms the
		schema lacks, or rewriting the description it was given. A field synonym
		counts too - it is read as evidence for this document exactly like the
		document's own, so a row curated only at the column level must not be
		reported as untouched.

		An *empty* description is not an edit, even though it fails the checksum: a
		curator deleting their sentence is asking for the generated one back, and the
		alternative reading strands the row - `sync` preserves what a curated row
		holds, so a document could be left describing itself with nothing, with no
		mechanical pass able to repair it.
		"""
		prose = (self.description or "").strip()
		edited = bool(prose) and bool(self.source_checksum) and self.source_checksum != checksum(prose)
		declared = bool((self.synonyms or "").strip())
		declared = declared or any((f.synonyms or "").strip() for f in self.fields)
		self.curated = 1 if (edited or declared) else 0

	def on_update(self) -> None:
		self._forget()

	def on_trash(self) -> None:
		self._forget()

	def _forget(self) -> None:
		"""Drop the curated-term cache retrieval reads.

		Imported here rather than at module level: `curation` imports `profile` and
		`model`, and a doctype controller is loaded by Frappe on every request that
		touches the doctype. Keeping the import inside the method keeps that graph
		acyclic and off the hot path.
		"""
		from nakhoda.semantic import curation

		curation.forget()
