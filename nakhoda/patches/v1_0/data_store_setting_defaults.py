# Copyright (c) 2026, Nakhoda and contributors
# For license information, please see license.txt
"""Make the Data Store settings say on screen what the worker actually does.

Three fields, one symptom. A Frappe default is applied when a document is
*created*, and `Nakhoda Settings` is a Single that predates all three, so:

- `enable_data_store` had no `tabSingles` row at all, and a missing Check
  reads back as `0` (`BaseDocument.init_valid_columns`);
- `max_records_to_sync` / `max_memory_usage` had rows saying `0`, written by
  an earlier save of a form that did not yet render them.

Every reader already refuses to believe those zeroes -
`data_store_enabled()` goes through `setting_enabled()`, and the caps fall
back to `DEFAULT_ROW_LIMIT` / `DEFAULT_MEMORY_MB` - so imports were never
wrong. The settings page was: it reads the document API, gets the raw values,
and rendered `Enable` **off** over a store that was importing and `0` / `0`
over a worker copying a million rows with 512 MB. A control that disagrees
with the thing it names is worse than no control.

The two rules differ because the values do:

- The Check is filled only when its row is *missing*. `0` is a legal, load
  -bearing value there - an admin's explicit off - and re-running `migrate`
  must never overturn it.
- The Ints are filled when missing *or* zero. Zero is not a legal cap: a zero
  row limit would import nothing and a zero memory limit would make DuckDB
  refuse to run, which is why both readers override it and why
  `NakhodaSettings.validate` now rewrites it on save. Healing it here means
  an upgraded site is honest immediately, rather than the first time somebody
  happens to open the tab and press Save.

The defaults are literals rather than imports from
`nakhoda_settings.DEFAULT_ROW_LIMIT`: a patch has to keep meaning what it
meant when it ran, even if those constants later change. Same reason
`migrate_ai_provider_settings` keeps its own copy of the row-presence check.
"""

from __future__ import annotations

import frappe
from frappe.query_builder import DocType
from frappe.utils import cint

DOCTYPE = "Nakhoda Settings"

#: Fieldname -> (value to write, whether a stored zero also counts as unset).
DEFAULTS = {
	"enable_data_store": (1, False),
	"max_records_to_sync": (1_000_000, True),
	"max_memory_usage": (512, True),
}


def unwritten(fieldname: str) -> bool:
	"""Whether the Single has no row for `fieldname` at all - the one state
	`frappe.db.get_single_value` erases by casting a missing value to `0`."""
	singles = DocType("Singles")
	return not (
		frappe.qb.from_(singles)
		.select(singles.field)
		.where((singles.doctype == DOCTYPE) & (singles.field == fieldname))
		.limit(1)
		.run()
	)


def stored_zero(fieldname: str) -> bool:
	"""Whether the written value reads as zero. Formatted into a string first
	because `get_single_value` is typed as any scalar a Single may hold."""
	value = frappe.db.get_single_value(DOCTYPE, fieldname)
	return not cint(f"{value or 0}")


def execute() -> None:
	if not frappe.db.exists("DocType", DOCTYPE):
		return

	changed = False
	for fieldname, (default, heal_zero) in DEFAULTS.items():
		if unwritten(fieldname) or (heal_zero and stored_zero(fieldname)):
			frappe.db.set_single_value(DOCTYPE, fieldname, default)
			changed = True

	if changed:
		frappe.clear_cache(doctype=DOCTYPE)
