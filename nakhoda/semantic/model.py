"""The semantic layer: what the application already knows, written down for a model.

This is the differentiator. Every text-to-SQL tool starts from a warehouse schema and
tries to recover meaning that was thrown away at ingestion - which table is a child of
which, which rows are real transactions, which money column is comparable across rows.
Frappe never threw it away: `frappe.get_meta()` holds all of it. So the model is
derived, not authored, and it cannot drift from the application.

Measured before it was written, on 40 questions x 2 contexts x 3 model tiers:

    warehouse DDL only ............ 78.3%   execution accuracy
    this, derived from get_meta ... 95.8%   McNemar exact p = 1.9e-05

The harness is `nakhoda/tests/semantic_bench/`; `test_semantic.py` holds this module
to the artifact that produced those numbers.

One code path serves two callers. `frappe.get_meta("Sales Invoice")` returns a Meta
document and a DocType JSON file parses to a dict; both answer `.get(key)` the same
way, so the renderer cannot special-case the live path and quietly diverge from the
measured one. Runtime is still strictly richer: Meta arrives with Custom Fields and
Property Setters already merged, so a customer's own columns and relabelled fields
describe themselves with no extra work.
"""

# Which fieldtypes are backed by a column. This is `frappe.model.data_fieldtypes`,
# copied rather than imported: reading one tuple is not worth making this module -
# and the gate that checks it against the measured artifact - depend on frappe being
# importable, which needs its whole dependency tree. `test_semantic_live.py` asserts
# the two are equal on every bench run, so the copy is a pin, not a fork. If Frappe
# adds a fieldtype the assertion fails and names it.
#
# An allow-list, not a deny-list, and the difference is not academic: the artifact
# this replaces filtered by naming the layout fieldtypes it knew about, and so
# published `image_view VARCHAR` on Sales Invoice Item - an `Image` field, which is
# a widget that re-renders another column. A model asked for an image would have
# selected a column that does not exist. Deny-lists fail open on every fieldtype
# nobody thought of; this one fails closed.
#
# Frappe applies exactly this test in `Meta.get_valid_columns()`
# (`frappe/model/meta.py:231`), which is the authority on what the table has.
HAS_COLUMN = frozenset(
	{
		"Attach",
		"Attach Image",
		"Autocomplete",
		"Barcode",
		"Check",
		"Code",
		"Color",
		"Currency",
		"Data",
		"Date",
		"Datetime",
		"Duration",
		"Dynamic Link",
		"Float",
		"Geolocation",
		"HTML Editor",
		"Icon",
		"Int",
		"JSON",
		"Link",
		"Long Int",
		"Long Text",
		"Markdown Editor",
		"Password",
		"Percent",
		"Phone",
		"Rating",
		"Read Only",
		"Select",
		"Signature",
		"Small Text",
		"Text",
		"Text Editor",
		"Time",
	}
)

# Frappe's fieldtypes to the warehouse's types. DuckDB, because that is what the
# store is - not MariaDB's `decimal(21,9)` / `int(1)`, which describe the site DB.
# Anything in HAS_COLUMN but missing here is a column we keep and describe as text.
SQL_TYPE = {
	"Attach": "VARCHAR",
	"Attach Image": "VARCHAR",
	"Autocomplete": "VARCHAR",
	"Barcode": "VARCHAR",
	"Check": "TINYINT",
	"Code": "VARCHAR",
	"Color": "VARCHAR",
	"Currency": "DECIMAL(18,6)",
	"Data": "VARCHAR",
	"Date": "DATE",
	"Datetime": "TIMESTAMP",
	"Duration": "DOUBLE",
	"Dynamic Link": "VARCHAR",
	"Float": "DOUBLE",
	"Geolocation": "VARCHAR",
	"Icon": "VARCHAR",
	"Int": "BIGINT",
	"JSON": "VARCHAR",
	"Link": "VARCHAR",
	"Long Text": "VARCHAR",
	"Markdown Editor": "VARCHAR",
	"Password": "VARCHAR",
	"Percent": "DOUBLE",
	"Phone": "VARCHAR",
	"Rating": "DOUBLE",
	"Read Only": "VARCHAR",
	"Select": "VARCHAR",
	"Signature": "VARCHAR",
	"Small Text": "VARCHAR",
	"Text": "VARCHAR",
	"Text Editor": "VARCHAR",
	"Time": "TIME",
}

# A Select with more values than this is data, not a category. Listing 40 warehouse
# names teaches the model nothing and crowds out the tables.
MAX_SELECT_VALUES = 14

# Descriptions are written for humans reading a form and some run long. Enough to
# carry the meaning, not enough to bury the schema.
MAX_DESCRIPTION = 110

# Measured. These six rules are most of the 17.5-point gap: they are the facts a
# warehouse schema cannot state, and every one of them is a wrong answer if the model
# has to guess. Changing this text changes the accuracy the benchmark recorded, so
# re-run it if you touch this.
CONVENTIONS = """## Framework conventions (apply to every table)
- Each table `tab<DocType>` stores one DocType. Column `name` is the primary key.
- Tables flagged SUBMITTABLE below use `docstatus`: 0 = Draft, 1 = Submitted, 2 = Cancelled.
  Only docstatus = 1 rows are real business transactions. Drafts and cancelled rows
  must be excluded from any business figure unless explicitly asked for.
- There are NO database foreign keys. Relationships are declared as Link columns;
  a Link column holds the `name` primary key of the table it targets.
- CHILD tables hold row-level detail. They join to their parent through
  `parent` = parent table's `name`, filtered by `parenttype`.
- Columns prefixed `base_` are the same figure converted to company currency using
  `conversion_rate`. Non-prefixed money columns are in the transaction `currency`.
  Aggregating money across rows requires the `base_` column."""

HEADER = (
	"-- Database: DuckDB. Use double quotes for identifiers.\n"
	"-- Semantic model auto-derived from Frappe DocType metadata (frappe.get_meta)."
)


def _notes(field) -> list[str]:
	"""Everything true about a column that its name and type do not already say."""
	notes = []
	fieldname = field.get("fieldname")
	fieldtype = field.get("fieldtype")

	# The label, but only when it carries information the fieldname doesn't. Most
	# labels are the fieldname in title case; repeating those doubles the model's
	# length and teaches nothing.
	label = field.get("label")
	if label and label.lower().replace(" ", "_") != fieldname:
		notes.append(label)

	# The join. This is the line that replaces a foreign key.
	if fieldtype == "Link" and (target := field.get("options")):
		notes.append(f'-> "tab{target}".name')

	if fieldtype == "Select" and (options := field.get("options")):
		values = [v for v in str(options).split("\n") if v.strip()]
		if values and len(values) <= MAX_SELECT_VALUES:
			notes.append("one of: " + " | ".join(values))

	if fieldtype == "Check":
		notes.append("boolean 0/1")

	if description := field.get("description"):
		notes.append(description.strip().replace("\n", " ")[:MAX_DESCRIPTION])

	if field.get("reqd"):
		notes.append("required")

	return notes


def describe(meta) -> dict:
	"""One DocType as columns and the facts about them.

	Takes anything that answers `.get()` like a Frappe document: a live Meta, or the
	DocType JSON off disk.
	"""
	doctype = meta.get("name")
	is_child = bool(meta.get("istable"))

	flags = []
	if is_child:
		flags.append("CHILD")
	if meta.get("is_submittable"):
		flags.append("SUBMITTABLE")
	if meta.get("is_tree"):
		flags.append("TREE")

	# Frappe's own columns, which appear in no DocType's field list but exist in every
	# table. Without `docstatus` the model cannot exclude drafts; without
	# `parent`/`parenttype` it cannot join a child row to its document.
	columns = [{"name": "name", "type": "VARCHAR", "notes": ["primary key"]}]
	if meta.get("is_submittable"):
		columns.append({"name": "docstatus", "type": "TINYINT", "notes": ["0=Draft 1=Submitted 2=Cancelled"]})
	if is_child:
		columns.append({"name": "parent", "type": "VARCHAR", "notes": ["FK to parent document name"]})
		columns.append({"name": "parenttype", "type": "VARCHAR", "notes": ["parent DocType name"]})

	seen = {c["name"] for c in columns}
	for field in meta.get("fields") or []:
		fieldname, fieldtype = field.get("fieldname"), field.get("fieldtype")
		if not fieldname or fieldname in seen:
			continue
		if field.get("is_virtual"):
			# Computed on read, never written - `SELECT` cannot name it. India
			# Compliance ships several (`Purchase Receipt.gst_breakup_table`), and a
			# fieldtype in HAS_COLUMN does not save it: `is_virtual` overrides the
			# type and Frappe creates no column for it at all.
			continue
		if fieldtype not in HAS_COLUMN:
			continue
		seen.add(fieldname)
		columns.append(
			{
				"name": fieldname,
				"type": SQL_TYPE.get(fieldtype, "VARCHAR"),
				"notes": _notes(field),
			}
		)

	return {
		"doctype": doctype,
		"table": f"tab{doctype}",
		"flags": flags,
		"description": meta.get("description"),
		"columns": columns,
	}


def render(tables: list[dict]) -> str:
	"""The model as the text a language model reads."""
	out = [HEADER, "", CONVENTIONS, ""]
	for table in tables:
		flags = f"  [{', '.join(table['flags'])}]" if table["flags"] else ""
		out.append(f'### "{table["table"]}"  -- {table["doctype"]}{flags}')
		if table["description"]:
			out.append(f"-- {table['description']}")
		for column in table["columns"]:
			notes = f"  -- {'; '.join(column['notes'])}" if column["notes"] else ""
			out.append(f"  {column['name']}  {column['type']}{notes}")
		out.append("")
	return "\n".join(out)


def build(doctypes: list[str]) -> list[dict]:
	"""The live path. Meta arrives with Custom Fields and Property Setters merged."""
	import frappe

	return [describe(frappe.get_meta(doctype)) for doctype in doctypes]


def prompt(doctypes: list[str]) -> str:
	"""The semantic layer for these DocTypes, ready to put in front of a model."""
	return render(build(doctypes))
