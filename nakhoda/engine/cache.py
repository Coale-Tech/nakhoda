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
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
	import pandas as pd

#: Long enough that collisions are not a security question, short enough to read.
_DIGEST = 16

DEFAULT_TTL = 3600


def key(sql: str, identity: str) -> str:
	"""The cache key for a compiled query against a given backend."""
	digest = hashlib.sha256(f"{identity}\n{sql}".encode()).hexdigest()[:_DIGEST]
	return f"nakhoda:result:{digest}"


def _redis() -> Any:
	"""The site's redis handle.

	`frappe.cache` is typed `RedisWrapper | None` because it is `None` until
	`frappe.init` runs. Inside a request it never is, and asserting that once
	here is more honest than three call sites that each look like they might
	be calling `None`.
	"""
	import frappe

	handle: Any = frappe.cache
	return handle()


def get(cache_key: str) -> str | None:
	"""A stored value, or `None` when redis is unreachable.

	Every cache read in the app goes through here rather than through
	`frappe.cache()` directly. Not ceremony: a cache that raises is a cache
	that takes down the request it was meant to speed up, and "swallow the
	error" is a decision that should exist once, not at each call site.
	"""
	try:
		return _redis().get_value(cache_key)
	except Exception:
		return None


def put(cache_key: str, value: str, *, ttl: int = DEFAULT_TTL) -> None:
	try:
		_redis().set_value(cache_key, value, expires_in_sec=ttl)
	except Exception:
		pass


def drop(cache_key: str) -> None:
	"""Forget one entry. Called when the thing it described changed."""
	try:
		_redis().delete_value(cache_key)
	except Exception:
		pass


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
	stored = get(cache_key)
	if stored is not None:
		try:
			return pd.DataFrame(frappe.parse_json(stored))
		except Exception:
			pass

	result = compute()
	put(cache_key, frappe.as_json(result.to_dict(orient="records")), ttl=ttl)
	return result
