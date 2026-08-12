"""Retrieval: which tables a question needs, and what fits in the budget.

This ships with the semantic layer rather than after it, because on a real site the
layer does not fit in a prompt. Measured on the bench this app was built against:
1,011 non-single DocTypes render to 187,242 tokens. The context that scored 95.8%
was 7,843 tokens over 8 tables. So retrieval is not an optimisation - without it
there is no product, and `10-eval-methodology.md` §3 locates the residual risk of
the whole thesis here.

The budget and the table cap are not round numbers. They are the shape of the
context that was actually measured: send more tables than the benchmark sent, or
more tokens, and the 95.8% no longer describes what the model is being given. The
fixture those numbers came from is ERPNext-scale - its Sales Invoice is 2,406
tokens against this site's 3,201, the difference being local Custom Fields - so the
budget is a fair target rather than a generous one. Every gold pair fits inside it
with room to spare; each failure below was something else crowding them out.

Retrieval reads the same artifact the model reads, so the two cannot drift: a column
retrieval matched on is a column the model will see. Indexing labels, descriptions,
or anything `render()` drops would buy recall by matching text that is not there at
answer time.

## Ranking

Scoring is coverage, and it is deliberately not BM25. Schema linking is not document
retrieval: a table's length is its column count, which measures how much of the
business it models, not how wordy its author was. BM25's length normalisation
therefore inverts the signal - measured here, it ranked `Sales Invoice Reference`
(3 columns) above `Sales Invoice` (155) for every question about invoices, and
recall was 15/40. Coverage of the question took that to 24/40.

Evidence is weighted by where it was found, because the schema means different
things in different places:

  its **name** - the question usually says "invoice". Damped by the name's own
  length, so a four-word table matching one word cannot beat an exact hit.
  its **enum values** - `status  one of: Overdue | Paid | ...` is what makes "how
  many invoices are overdue" resolvable at all. Controlled vocabulary the schema
  commits to, and the domain the semantic layer exists to publish.
  its **columns** - weaker, and by far the most numerous.
  its **prose** - labels and descriptions, worth a fraction of the rest. This is
  free text written for someone reading a form, and it is where the false friends
  live: `Item.no_of_months` is labelled "No of Months (Revenue)", which made `Item`
  the top hit for every revenue question until prose was separated out.

## Usage

Lexical evidence alone cannot separate `Sales Invoice` from `Purchase Invoice`,
`POS Invoice`, `Delivery Note` and `Purchase Receipt` for "total revenue in company
currency, excluding returns" - measured, all five scored **identically**, and the
alphabetical tiebreak put Sales Invoice last and outside the budget.

What separates them is not language, it is the business: on this site Sales Invoice
holds 58,741 rows and POS Invoice holds **zero**. A table with no rows cannot answer
a question about what the company did, and spending 2,138 tokens describing an
unused module is worse than spending nothing. This is a fact about the deployment,
not about the benchmark, and every deployment has its own. It is the single largest
contributor here: removing it costs eighteen of the forty questions.

It is capped at one name-term's worth of evidence so it can only ever break a tie or
a near-tie, never outweigh a table that genuinely matches the words. That cap is
what keeps it safe: the largest tables on a live ERPNext site are `tabVersion`,
`__global_search` and `tabComment`, and they are never retrieved because they never
earn lexical evidence in the first place - `rank()` only returns tables that do.

## Packing

The remaining failure was structural. For "how many invoice line items are on issued
invoices", `Sales Invoice` ranked first correctly, then `POS Invoice` and
`Purchase Invoice` took 4,463 tokens between them and left no room for
`Sales Invoice Item` - the one table the question actually needed. Those two are not
additional evidence; they are *alternatives* to a table already chosen, near
duplicates of its column list.

So packing discounts a candidate by how much of its vocabulary is already present -
maximal marginal relevance, applied to prefer complements over duplicates - but only
against tables of the same kind. Vocabulary overlap alone does not mean duplication
in a normalised ERP, where a fact table denormalises the dimensions it points at;
see `_redundancy`.

Two structural rules sit on top, and neither is a tuning knob:

  A child table cannot be read without its parent. `parent` is an opaque key; the
  grain question ("revenue by item group") lives in the child, the filter ("issued
  invoices only") lives in the parent. Selecting one without the other cannot
  produce a correct query, so the closure is part of the candidate, not a bonus
  applied to it. A child whose parent is not indexable is dropped outright.

  Single DocTypes have no table. They are settings pages, excluded at index time
  rather than ranked and skipped.

## What is not here

Three mechanisms were built, measured and deleted: a weight on link-target words, a
currency-column bonus gated on a hand-written English money lexicon, and a bonus for
being joinable to an already-chosen table. Each was plausible, each survived casual
inspection, and none of them earned a question - deleting all three moved recall
from 90.0% to 92.5%. `test_each_mechanism_earns_its_place` is what found them, and
it now guards the six that remain. Nothing in this module reads a list of English
words; every signal is read off the schema.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

from nakhoda.semantic.model import describe, render

#: The context that measured 95.8%, in tokens and in tables. Retrieval may spend up
#: to what the benchmark spent and no more.
BUDGET = 7843
MAX_TABLES = 8

#: ~3.6 characters per token on rendered schema text, measured with `cl100k_base`
#: over all 1,011 DocTypes on the bench (678,907 chars / 187,242 tokens). Used so the
#: runtime never needs a tokeniser: `tiktoken` fetches its BPE files over the network
#: on first use, which a self-hosted BI tool cannot rely on. `test_retrieval` pins
#: this against the real tokeniser and fails if the estimate drifts.
CHARS_PER_TOKEN = 3.626

#: English function words plus the words every BI question is made of. Kept short on
#: purpose: a long hand-tuned list is a way of fitting the benchmark rather than the
#: language. Anything here would otherwise match hundreds of tables equally and only
#: add noise to the IDF.
STOPWORDS = frozenset(
	"""a an the and or but if of in on at to for from by with without as is are was were be been
	do does did how many much what which who whom whose when where why our we us their there
	that this these those it its all any each per some more most least top bottom show list give
	me tell find get count total sum number numbers value values across still ever so far not
	only just have has had can could would should""".split()
)


def stem(word: str) -> str:
	"""Fold a word to the form the index and the question can meet on.

	Light and Porter-shaped: plural, then participle, then a trailing `e`. The last
	step is what makes "invoiced" reach "invoice" - both land on `invoic` - and
	without it `Sales Invoice` earns no name evidence at all from "have we invoiced",
	which was one of the measured failures.

	Deliberately not a real stemmer. A real one also folds `paid`/`pay`, and `Paid`
	is a Select value on Sales Invoice while `pay` is not: the schema would start
	disagreeing with the words used to search it.
	"""
	if len(word) > 4 and word.endswith("ies"):
		word = word[:-3] + "y"
	elif len(word) > 3 and word.endswith("s") and not word.endswith(("ss", "us", "is")):
		word = word[:-1]

	if len(word) > 5 and word.endswith("ing"):
		word = word[:-3]
	elif len(word) > 4 and word.endswith("ed"):
		word = word[:-2]

	if len(word) > 4 and word.endswith("e"):
		word = word[:-1]
	return word


def terms(text: str) -> list[str]:
	"""Words worth matching on, from a question or from a schema."""
	words = re.split(r"[^a-z0-9]+", text.lower())
	return [stem(w) for w in words if len(w) > 1 and w not in STOPWORDS]


def estimate_tokens(text: str) -> int:
	return math.ceil(len(text) / CHARS_PER_TOKEN)


def _bucket(note: str) -> str:
	"""Which kind of evidence a note is, by the shapes `model._notes` emits.

	The split earns its keep: measured, the top hit for "gross revenue excluding any
	returns" was `Item`, because `no_of_months` is labelled "No of Months (Revenue)".
	Second was `Customer`, whose `custom_health_score` is *described* as being based
	on revenue. Neither can answer the question. Enum values and link targets are
	controlled vocabulary the schema commits to; labels and descriptions are prose
	written for a human reading a form, and prose is where false friends live.
	"""
	if note.startswith("-> "):
		return "link"
	if note.startswith("one of: "):
		return "enum"
	if note in ("boolean 0/1", "required"):
		return "skip"
	return "prose"


def _kind(meta) -> str:
	"""What sort of table this is, in the schema's own terms.

	Three, and Frappe declares all three. A `child` is a grain inside a document. A
	`transaction` is submittable: something the business did, on a date, that can be
	cancelled. Everything else is a `master` - the things transactions point at.
	Only tables of the same kind can be alternatives to each other.
	"""
	if meta.get("istable"):
		return "child"
	return "transaction" if meta.get("is_submittable") else "master"


@dataclass
class Table:
	"""One DocType, as something to rank and something to pay for.

	The term buckets are the kinds of evidence, kept apart because they are worth
	different amounts. Sets, not counts: a column mentioning "invoice" four times is
	not four times the evidence that this table answers about invoices.
	"""

	name: str
	tokens: int
	kind: str = "master"
	is_child: bool = False
	rows: int = 0
	parents: tuple[str, ...] = ()
	name_terms: frozenset[str] = frozenset()
	enum_terms: frozenset[str] = frozenset()
	column_terms: frozenset[str] = frozenset()
	prose_terms: frozenset[str] = frozenset()

	def requires(self) -> tuple[str, ...]:
		"""What must accompany this table for it to be usable at all."""
		return self.parents if self.is_child else ()

	@property
	def vocabulary(self) -> frozenset[str]:
		return self.name_terms | self.enum_terms | self.column_terms


class Index:
	"""A searchable, costed view of the semantic layer.

	Built from anything that answers `.get()` like a Frappe document - a live `Meta`
	or a DocType JSON off disk - so the gate can run against a fixed corpus and the
	site can run against itself, through one code path. `row_counts` is data, not a
	lookup, for the same reason.
	"""

	#: What a matched term is worth, by where it was found. Every weight here is
	#: load-bearing: `test_each_mechanism_earns_its_place` zeroes each in turn and
	#: requires recall to fall. Two that were here did not survive that test. A
	#: weight on link-target names cost a question rather than earning one - the
	#: column is already named `customer`, so the note only said it twice. A flat
	#: bonus for holding `base_*` currency columns, gated on a hand-written list of
	#: English money words, moved nothing at all: on a question about money most of
	#: the plausible tables hold money, and a bonus almost everyone gets is not a
	#: discriminator. Deleting it took the last English lexicon out of retrieval.
	NAME = 3.0
	ENUM = 1.5
	COLUMN = 1.0
	PROSE = 0.4

	#: Capped at `NAME`: usage is worth at most what one matched name word is worth.
	USAGE = 3.0

	#: How hard to discount a candidate for repeating what is already selected. At 1.0
	#: a perfect duplicate is worth nothing, which is the honest valuation.
	REDUNDANCY = 1.0

	#: How many ranked tables the greedy pass reconsiders. A bound on work, not on
	#: answers: at most `MAX_TABLES` come back, and nothing gains score during the
	#: pass - redundancy only takes away. Without it a question matching five hundred
	#: tables re-scores all five hundred on every pick, which is a quadratic cost for
	#: tables that were never going to win.
	SHORTLIST = 64

	#: The join graph is not here, and that is a finding rather than an omission.
	#: Scoring a table for being joinable to one already chosen is the obvious next
	#: mechanism - the plan called for it - and measured, it was worth exactly
	#: nothing: one question won, one lost. In an ERP the near-duplicates link to
	#: each other too (`POS Invoice` references `Sales Invoice` through
	#: `consolidated_invoice`), so adjacency promotes the alternative as readily as
	#: the complement. What the model needs the join graph for is writing the join,
	#: and it gets it where it belongs: rendered in the table description it reads.

	def __init__(self, metas, row_counts: dict[str, int] | None = None) -> None:
		self.tables: dict[str, Table] = {}
		counts = row_counts or {}
		child_of: dict[str, set[str]] = {}

		for meta in metas:
			name = meta.get("name")
			if not name or meta.get("issingle"):
				continue

			described = describe(meta)
			columns: set[str] = set()
			buckets: dict[str, set[str]] = {"enum": set(), "prose": set()}
			for column in described["columns"]:
				columns.update(terms(column["name"]))
				for note in column["notes"]:
					kind = _bucket(note)
					if kind in buckets:
						buckets[kind].update(terms(note))
			self.tables[name] = Table(
				name=name,
				tokens=estimate_tokens(render([described])),
				kind=_kind(meta),
				is_child=bool(meta.get("istable")),
				rows=max(0, int(counts.get(name, 0))),
				name_terms=frozenset(terms(name)),
				enum_terms=frozenset(buckets["enum"]),
				column_terms=frozenset(columns),
				prose_terms=frozenset(buckets["prose"]),
			)

			for f in meta.get("fields") or []:
				if f.get("fieldtype") in ("Table", "Table MultiSelect") and f.get("options"):
					child_of.setdefault(f.get("options"), set()).add(name)

		for child, parents in child_of.items():
			if child in self.tables:
				self.tables[child].parents = tuple(sorted(parents))

		# A child whose parent is not here cannot be joined to anything, so it cannot
		# answer anything. The case is real: `Payment Reconciliation Invoice` belongs
		# to a Single, and Singles have no table for its `parent` key to point at.
		# Left in, it was selected on two invoice questions as an orphan - budget
		# spent on rows no query can reach.
		for name in [n for n, t in self.tables.items() if t.is_child and not t.parents]:
			del self.tables[name]

		self.document_frequency = Counter()
		for table in self.tables.values():
			self.document_frequency.update(table.vocabulary)

		busiest = max((t.rows for t in self.tables.values()), default=0)
		self._usage_scale = math.log1p(busiest) or 1.0

	def _idf(self, term: str) -> float:
		n = len(self.tables)
		df = self.document_frequency.get(term, 0)
		return math.log(1 + (n - df + 0.5) / (df + 0.5))

	def usage(self, table: Table) -> float:
		"""0 for a table the business has never written to, 1 for its busiest."""
		return math.log1p(table.rows) / self._usage_scale

	def score(self, asked: set[str], table: Table) -> float:
		"""How much of the question this table can explain, and with what.

		The name is divided by the square root of its own length so that a long table
		name cannot win on a single shared word: `Sales Invoice` matching two of two
		beats `Sales Invoice Reference` matching two of three.
		"""
		named = sum(self._idf(t) for t in asked & table.name_terms)
		enumed = sum(self._idf(t) for t in asked & table.enum_terms)
		columned = sum(self._idf(t) for t in asked & table.column_terms)
		prosed = sum(self._idf(t) for t in asked & table.prose_terms)
		damping = math.sqrt(len(table.name_terms)) or 1.0
		lexical = (
			self.NAME * named / damping + self.ENUM * enumed + self.COLUMN * columned + self.PROSE * prosed
		)
		return lexical + self.USAGE * self.usage(table) if lexical else 0.0

	def rank(self, question: str) -> list[tuple[str, float]]:
		asked = set(terms(question))
		scored = ((t.name, self.score(asked, t)) for t in self.tables.values())
		return sorted((s for s in scored if s[1] > 0), key=lambda s: (-s[1], s[0]))

	def _redundancy(self, candidate: Table, chosen: list[str]) -> float:
		"""How much of this table repeats one already chosen. Jaccard, worst case.

		Only tables of the same kind can be redundant, and the schema says which kind
		each one is. Vocabulary overlap on its own does not mean duplication in a
		normalised ERP: a fact table denormalises the dimensions it references, so
		`Sales Invoice` carries `customer_name` and `territory`, and scoring that as
		repetition penalises `Customer` for being the thing the invoice points at.
		Same-kind overlap is different. `POS Invoice` and `Sales Invoice` are both
		submittable transactions with nearly the same columns because they are one
		shape of document for two business processes, and only one of them is the
		answer. Measured, exempting links instead of kinds made this worse: `POS
		Invoice` links to `Sales Invoice` through `consolidated_invoice`, so the
		exemption protected exactly the table it needed to suppress.
		"""
		worst = 0.0
		for name in chosen:
			other = self.tables[name]
			if other.kind != candidate.kind:
				continue
			union = len(candidate.vocabulary | other.vocabulary)
			if union:
				worst = max(worst, len(candidate.vocabulary & other.vocabulary) / union)
		return worst

	def select(self, question: str, budget: int = BUDGET, max_tables: int = MAX_TABLES) -> list[str]:
		"""The tables to put in front of a model, best first, inside the budget.

		Re-scored after every pick, because what a table is worth depends on what has
		already been chosen: less for repeating it, more for joining to it. Greedy,
		and it keeps going after something does not fit: one table being too expensive
		is no reason to drop a cheaper one below it.
		"""
		ranked = self.rank(question)[: self.SHORTLIST]
		if not ranked:
			return []

		remaining = dict(ranked)
		chosen: list[str] = []
		spent = 0

		while remaining and len(chosen) < max_tables:
			best, best_value = None, 0.0
			for name, base in remaining.items():
				redundant = self.REDUNDANCY * self._redundancy(self.tables[name], chosen)
				value = base * (1 - redundant)
				if value > best_value:
					best, best_value = name, value
			if best is None:
				break

			del remaining[best]
			addition = [n for n in (best, *self.tables[best].requires()) if n not in chosen]
			cost = sum(self.tables[n].tokens for n in addition if n in self.tables)
			if len(chosen) + len(addition) <= max_tables and spent + cost <= budget:
				chosen.extend(addition)
				spent += cost
				for n in addition:
					remaining.pop(n, None)

		return chosen

	def cost(self, names: list[str]) -> int:
		return sum(self.tables[n].tokens for n in names if n in self.tables)


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


def build_index(doctypes: list[str] | None = None) -> Index:
	"""The live path: index this site."""
	import frappe

	names = doctypes or frappe.get_all("DocType", filters={"issingle": 0}, pluck="name")
	return Index((frappe.get_meta(name) for name in names), row_counts=row_counts())


def prompt(question: str, index: Index, budget: int = BUDGET) -> str:
	"""The semantic layer for one question, inside the budget."""
	import frappe

	return render([describe(frappe.get_meta(name)) for name in index.select(question, budget)])
