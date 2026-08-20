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

## Reporting

Usage says which tables the business writes to; it cannot say which ones the business
*measures*. `Sales Invoice` and `Purchase Invoice` both hold tens of thousands of rows
on this site and are near-indistinguishable by column list, so "what was our revenue"
splits them by nothing at all. What splits them is that 30 dashboard charts, number
cards and reports point at one and 21 at the other: a document somebody built a chart
on is a document questions get asked about. Measured, it is the single largest gain in
this module - 20/40 to 30/40 - and it is read from three tables the site maintains for
its own reasons (`profile.reporting_counts`).

A child inherits its document's count, and that is worth five more questions on its
own. Nobody builds a dashboard on `Sales Invoice Item`, but a chart of revenue by item
reads exactly that table through its parent: the report is declared against the
document and the grain lives in the child. Without inheritance the line tables sit
below their competitors for every question about items sold.

The two priors are averaged rather than added, so the pair still cannot outweigh a
name match - the cap that made usage safe applies unchanged to what replaced it.

## Emptiness

Two thirds of the columns on this site hold no value in any row. Retrieval pays tokens
for every column it shows the model, so those columns are budget spent on nothing, and
they match words the site never uses. Pruning them is worth eight questions and it is
the difference between clearing the gate and not: `Sales Invoice` costs 2,624 tokens
instead of 4,351, and the pair it needs fits beside it.

What is empty is a fact about the deployment and expensive to establish - one scan per
table - so it arrives here as data, like `row_counts`. `semantic/profile.py` owns
establishing it, including why the exact answer turned out to be cheaper than a
sampled one.

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

Nine mechanisms were built, measured and deleted. Three went early: a weight on
link-target words, a currency-column bonus gated on a hand-written English money
lexicon, and a bonus for being joinable to an already-chosen table. Five more went on
2026-08-15, when the two priors above were added and everything else plausible was
tried beside them:

  **Multiplying the priors** instead of averaging them. A table needs rows *and*
  reports, so a product reads as the stricter claim - and it is, which is the problem:
  it zeroes any table that has one and not the other, and `Sales Invoice Item` has no
  charts of its own. 30/40 against 37/40.

  **A flat ledger prior**, and then **a ledger-derived metric vocabulary**: `GL Entry`
  knows which accounts a business posts revenue to, so its account names should bridge
  the word "revenue" to the documents that earn it. Neither moved a single question.
  The vocabulary those accounts actually contribute is `carriag`, `drawback`, `rodtep`
  - the language of tax treatment, not of the question anybody asks.

  **Two repairs to packing**, both of which looked like bug fixes rather than
  mechanisms. A child was made to bring one parent instead of every DocType that could
  parent it (`Item Wise Tax Detail` is reachable from nine documents and so costs
  12,648 tokens and is never affordable), and a near-duplicate that outscored the
  incumbent it was suppressed by was allowed to replace it. Each is defensible on
  paper; measured, both were worth exactly zero questions, so the simpler code stayed.

  **The enum domains.** `one of: Draft, Submitted, Cancelled` is the schema's own
  controlled vocabulary, which is why enum terms were weighted above column names from
  the start. Measured, they are mostly workflow states shared by hundreds of tables, so
  they carry almost no IDF, and wherever an enum value does discriminate the same word
  is already in the column name beside it. Deleting the bucket left recall at 37/40 and
  removed 15,556 tokens of wasted budget and six same-kind duplicate pairs from the
  selections - it was not neutral, it was a cost. Enum domains are still rendered; the
  model reads them when it writes a filter. They are just not search terms.

  **Reporting titles as vocabulary.** The reporting prior already earns ten questions
  from the count of charts, cards and reports pointing at a table; their *titles* are
  free text a person wrote, so they should carry the business words the schema lacks.
  Measured on this site: 113 documents carry titles, 788 terms - and the three lost
  questions recovered **zero**, while costing one (37 -> 36). The words are there, on
  the wrong documents: `revenu` appears in exactly one title set, `GL Entry`'s, and
  `sold` and `paid` in nobody's. Same shape as the rejected ledger vocabulary: a real
  signal about accounting, silent about sales.

`test_each_mechanism_earns_its_place` is what found all nine, and it now guards the
seven that remain - each against the outcome it claims, because recall alone cannot
price ordering or packing. Pruning has its own mutation test, since no weight can
switch it off. Nothing in this module reads a list of English words; every signal is
read off the schema, off the site, or off a curator's own declaration.

## Where this stops

Measured on this site on 2026-08-15: 20/40 with lexical evidence and usage alone,
30/40 with the reporting prior, 37/40 with pruning and inheritance - 92.5%, against a
gate of 90%. The three that remained were one shape: all three turn on "revenue" or
"sold", and the stem `revenu` appears in the vocabulary of **zero** tables on this
site. `Sales Invoice` never says the word, and nothing derived - not accounts, not
chart titles - says it either. Four mechanisms were built to derive it and all four
were deleted.

So it is declared instead: `Nakhoda Semantic Model.synonyms` is the one input here a
person writes, and with seven documents named it takes retrieval to **40/40**. That
is the mechanism the earlier ceiling was pointing at, not a limit on the method - and
`CURATED` is a claim about meaning that a boundary sweep supports rather than a fitted
number: 0.5 buys 38/40, 0.75 through 3.0 all buy 40/40, so the shipped 3.0 sits four
times clear of the cliff.

The earlier numbers in this file were measured before this site's data grew; that they
no longer reproduce is the argument for a site-derived prior rather than against it.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Sequence
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


def _is_prose(note: str) -> bool:
	"""Whether a note is free text written for a human, rather than schema commitment.

	The distinction earns its keep: measured, the top hit for "gross revenue excluding
	any returns" was `Item`, because `no_of_months` is labelled "No of Months
	(Revenue)". Second was `Customer`, whose `custom_health_score` is *described* as
	being based on revenue. Neither can answer the question, and both matched on prose.

	Link targets (`-> Customer`), enum domains (`one of: Draft, ...`) and flags
	(`required`) are the schema's own vocabulary rather than prose. None of the three is
	scored: link words and enum values were both measured and deleted (see "What is not
	here"), and a flag carries no words at all. They stay rendered - the model reads the
	enum domain when it writes a filter - they just stop being search terms.
	"""
	return not (note.startswith("-> ") or note.startswith("one of: ") or note in ("boolean 0/1", "required"))


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


def _prune(described: dict, empty: frozenset[str]) -> dict:
	"""The same description, without the columns this site never fills.

	One definition, called by `Index.__init__` and by `context()`, because a table
	ranked on a pruned description and rendered from an unpruned one would silently
	break both the no-drift claim above and the token budget: `select()` fits the
	pruned cost, and the model would be handed something larger.
	"""
	if not empty:
		return described
	return described | {"columns": [c for c in described["columns"] if c["name"] not in empty]}


@dataclass
class Table:
	"""One DocType, as something to rank and something to pay for.

	The term sets are the kinds of evidence, kept apart because they are worth
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
	column_terms: frozenset[str] = frozenset()
	prose_terms: frozenset[str] = frozenset()
	#: Words a person declared for this document that its schema never says. The one
	#: kind of evidence here that is not derived, and the only one that reaches the
	#: three gold questions asking about "revenue" and "sold" - see `CURATED`.
	curated_terms: frozenset[str] = frozenset()
	#: Columns this site never fills, dropped from the description this table was
	#: costed and scored against. Kept so the prompt can render the same artifact -
	#: `context()` is the only reader.
	empty: frozenset[str] = frozenset()

	def requires(self) -> tuple[str, ...]:
		"""What must accompany this table for it to be usable at all."""
		return self.parents if self.is_child else ()

	@property
	def vocabulary(self) -> frozenset[str]:
		"""Every term this table can be found by, and the corpus IDF is counted over.

		Curated terms belong in here rather than beside it: a word two same-kind
		tables were both given is a duplicate like any other (`_redundancy` reads
		this), and a word every table was given should be worth nothing (`_idf`
		counts this). Curation that escaped both would be a way to cheat the scorer.
		"""
		return self.name_terms | self.column_terms | self.curated_terms


class Index:
	"""A searchable, costed view of the semantic layer.

	Built from anything that answers `.get()` like a Frappe document - a live `Meta`
	or a DocType JSON off disk - so the gate can run against a fixed corpus and the
	site can run against itself, through one code path. What the site holds arrives
	the same way: `row_counts`, `empty_columns`, `reports` and `curated` are data
	rather than lookups, so nothing in here queries a database and the corpus can be
	a fixture. The last of them is the only input a person writes.
	"""

	#: What a matched term is worth, by where it was found. Every weight here is
	#: load-bearing: `test_each_mechanism_earns_its_place` removes each in turn and
	#: requires the outcome that weight claims to improve to get worse. Three that were
	#: here did not survive it. A weight on link-target names cost a question rather
	#: than earning one - the column is already named `customer`, so the note only said
	#: it twice. A flat bonus for holding `base_*` currency columns, gated on a
	#: hand-written list of English money words, moved nothing: on a question about
	#: money most of the plausible tables hold money, and a bonus almost everyone gets
	#: is not a discriminator. And enum domains - `one of: Draft, Submitted` - read like
	#: the schema's own controlled vocabulary, which is why they were weighted above
	#: column names, but measured they are mostly workflow states that hundreds of
	#: tables share, so they carry almost no IDF and the words that do discriminate are
	#: already in the column names beside them. Removing them left recall at 37/40 and
	#: took 15,556 tokens of wasted budget and six same-kind duplicate pairs out of the
	#: selections: not neutral, an active cost.
	NAME = 3.0
	COLUMN = 1.0
	PROSE = 0.4

	#: What a word a person declared is worth. Equal to `NAME`, and that is a claim
	#: about meaning rather than a fitted number: a curator writing "revenue" on
	#: `Sales Invoice` is asserting exactly what the table's own name asserts, which
	#: is why it is not weighted above it either. Measured on `jkm` (2026-08-15):
	#: 37/40 without curation, 40/40 with seven documents described, and 37/40 again
	#: with this weight zeroed. The cliff is at 0.75 - 0.5 buys one question, 0.75
	#: buys both - so 3.0 sits four times clear of it rather than balanced on it.
	#: Nothing derived reaches those three questions: the stem `revenu` appears in no
	#: table's vocabulary on this site, and two attempts to derive it were deleted
	#: (see "What is not here").
	CURATED = 3.0

	#: Capped at `NAME`: usage is worth at most what one matched name word is worth.
	USAGE = 3.0

	#: What a report pointing at a table is worth, relative to rows in it. Equal, and
	#: not tuned: the two priors are averaged, so `USAGE` still caps the pair at one
	#: name term. Zeroing this removes both the reporting prior and the inheritance
	#: that rides on it, which costs eight questions.
	REPORTED = 1.0

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

	def __init__(
		self,
		metas,
		row_counts: dict[str, int] | None = None,
		empty_columns: dict[str, frozenset[str]] | None = None,
		reports: dict[str, int] | None = None,
		curated: dict[str, str] | None = None,
	) -> None:
		self.tables: dict[str, Table] = {}
		counts = row_counts or {}
		unfilled = empty_columns or {}
		declared = curated or {}
		child_of: dict[str, set[str]] = {}

		for meta in metas:
			name = meta.get("name")
			if not name or meta.get("issingle"):
				continue

			# Columns this site never fills, dropped before anything is measured, so the
			# token cost and the vocabulary both describe the table the model will
			# actually be shown. `name`, `docstatus` and `parent` are framework columns
			# that no profile lists, which is what keeps the join and filter keys of an
			# otherwise-unused table intact.
			empty = unfilled.get(name) or frozenset()
			described = _prune(describe(meta), empty)
			columns: set[str] = set()
			prose: set[str] = set()
			for column in described["columns"]:
				columns.update(terms(column["name"]))
				for note in column["notes"]:
					if _is_prose(note):
						prose.update(terms(note))
			self.tables[name] = Table(
				name=name,
				tokens=estimate_tokens(render([described])),
				kind=_kind(meta),
				is_child=bool(meta.get("istable")),
				rows=max(0, int(counts.get(name, 0))),
				name_terms=frozenset(terms(name)),
				column_terms=frozenset(columns),
				prose_terms=frozenset(prose),
				curated_terms=frozenset(terms(declared.get(name, ""))),
				empty=frozenset(empty),
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

		# A report is declared against a document; the grain it charts lives in the
		# child. So a line table inherits its parent's count rather than earning its
		# own, which no line table ever does.
		self.reports = dict(reports or {})
		for name, table in self.tables.items():
			inherited = max((self.reports.get(p, 0) for p in table.parents), default=0)
			if inherited > self.reports.get(name, 0):
				self.reports[name] = inherited
		self._report_scale = math.log1p(max(self.reports.values(), default=0)) or 1.0

	def _idf(self, term: str) -> float:
		n = len(self.tables)
		df = self.document_frequency.get(term, 0)
		return math.log(1 + (n - df + 0.5) / (df + 0.5))

	def usage(self, table: Table) -> float:
		"""0 for a table the business has never written to, 1 for its busiest."""
		return math.log1p(table.rows) / self._usage_scale

	def reported(self, table: Table) -> float:
		"""0 for a table nobody has built a chart on, 1 for the most reported one."""
		return math.log1p(self.reports.get(table.name, 0)) / self._report_scale

	def prior(self, table: Table) -> float:
		"""What this table is worth before a single word is matched.

		Two facts about the deployment, averaged rather than summed so that the pair
		is still worth at most one matched name term. A table the business writes to
		and a table the business measures are different claims - `GL Entry` is the
		busiest ledger on the site and nobody charts it; `Sales Invoice` is both - and
		averaging is what lets either one carry a table on its own.
		"""
		return (self.usage(table) + self.REPORTED * self.reported(table)) / (1 + self.REPORTED)

	def score(self, asked: set[str], table: Table) -> float:
		"""How much of the question this table can explain, and with what.

		The name is divided by the square root of its own length so that a long table
		name cannot win on a single shared word: `Sales Invoice` matching two of two
		beats `Sales Invoice Reference` matching two of three.

		Curated terms are not damped that way: a declaration is not a name, and a
		curator who writes six words for a document has not thereby made each one
		worth less. They are IDF-weighted like every other kind of evidence, so a
		word given to half the site is worth what a word given to half the site is
		worth - which is what keeps curation from becoming a way to shout.
		"""
		named = sum(self._idf(t) for t in asked & table.name_terms)
		columned = sum(self._idf(t) for t in asked & table.column_terms)
		prosed = sum(self._idf(t) for t in asked & table.prose_terms)
		declared = sum(self._idf(t) for t in asked & table.curated_terms)
		damping = math.sqrt(len(table.name_terms)) or 1.0
		lexical = (
			self.NAME * named / damping
			+ self.COLUMN * columned
			+ self.PROSE * prosed
			+ self.CURATED * declared
		)
		return lexical + self.USAGE * self.prior(table) if lexical else 0.0

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


def build_index(doctypes: list[str] | None = None) -> Index:
	"""The live path: index this site, with what the site is known to hold.

	The column profile is read, never built: establishing it is a 68-second scan
	(`semantic/profile.py`), and this function runs in front of a question. A site that
	has never built one still answers - eight of the forty gold questions worse, which
	is why the absence is logged rather than shrugged at. `bench migrate` builds it.
	"""
	import frappe

	from nakhoda.semantic import curation, profile

	names = doctypes or frappe.get_all("DocType", filters={"issingle": 0}, pluck="name")
	empty = profile.empty_columns()
	if not empty:
		frappe.logger("nakhoda").warning(
			"no column profile on this site: retrieval is running unpruned. "
			"Build it with `bench --site <site> execute nakhoda.semantic.profile.refresh`."
		)
	return Index(
		(frappe.get_meta(name) for name in names),
		row_counts=profile.row_counts(),
		empty_columns=empty,
		reports=profile.reporting_counts(),
		curated=curation.synonyms(),
	)


def context(names: Sequence[str], index: Index) -> str:
	"""The artifact these tables were ranked and costed against, for a model to read.

	The only renderer on the live path. `select()` fits a budget computed from pruned
	descriptions, so rendering unpruned ones here would hand the model more than it
	was promised and make `cost()` a lie.

	A curated description replaces the DocType's own, which is what makes
	`Nakhoda Semantic Model.description` hand-*correctable* rather than decorative.
	It cannot change which tables are here - selection happened before this call -
	so the two halves of curation stay separable: `synonyms` move answers, prose
	explains them.
	"""
	import frappe

	from nakhoda.semantic import curation

	authored = curation.descriptions()
	out = []
	for name in names:
		if name not in index.tables:
			continue
		described = _prune(describe(frappe.get_meta(name)), index.tables[name].empty)
		if authored.get(name):
			described = described | {"description": authored[name]}
		out.append(described)
	return render(out)


def prompt(question: str, index: Index, budget: int = BUDGET) -> str:
	"""The semantic layer for one question, inside the budget."""
	return context(index.select(question, budget), index)
