"""The result cache, keyed by the SQL that produced the result.

The key is a digest of the compiled SQL plus the backend's identity. That choice
does one thing worth stating plainly: **it makes cross-user leakage impossible
rather than merely forbidden.**

Permissions in this engine are not applied after the query - they compile into
it, because `permitted_resolver` wraps the table before the pipeline is built
(see `engine/permissions.py`). Two users with different User Permissions
therefore produce different SQL, so they cannot collide on a key. Two users with
*identical* permissions produce identical SQL, and sharing that entry is correct
- the rows are the same rows.

Compare the shape this replaces. A cache keyed by
`f"insights:ml_{report}:{filters}"` and filled behind a coarse `has_permission`
check hands the first caller's rows to every later caller who passes the same
check but has narrower User Permissions. That is not a hypothetical: it is what
`insights/api/ml/utils.py:cached_run` did, and the fix there was to append the
user to the key - a fix that works only for as long as everyone remembers to
apply it. Here there is nothing to remember.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
	import pandas as pd

#: Long enough that collisions are not a security question, short enough to read.
_DIGEST = 16

DEFAULT_TTL = 3600


def key(sql: str, identity: str) -> str:
	"""The cache key for a compiled query against a given backend."""
	digest = hashlib.sha256(f"{identity}\n{sql}".encode()).hexdigest()[:_DIGEST]
	return f"nakhoda:result:{digest}"


def cached(
	sql: str,
	identity: str,
	compute: Callable[[], pd.DataFrame],
	*,
	ttl: int = DEFAULT_TTL,
) -> pd.DataFrame:
	"""`compute()`, memoised against the SQL it will run.

	Falls through to `compute()` whenever the cache is unavailable or the stored
	payload cannot be read back. A cache is an optimisation; a query that cannot
	use one still has to answer.
	"""
	import frappe
	import pandas as pd

	cache_key = key(sql, identity)
	try:
		stored = frappe.cache().get_value(cache_key)
	except Exception:
		stored = None
	if stored is not None:
		try:
			return pd.DataFrame(frappe.parse_json(stored))
		except Exception:
			pass

	result = compute()
	try:
		frappe.cache().set_value(
			cache_key, frappe.as_json(result.to_dict(orient="records")), expires_in_sec=ttl
		)
	except Exception:
		pass
	return result
