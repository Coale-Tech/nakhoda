# Copyright (c) 2026, Nakhoda and contributors
# For license information, please see license.txt
"""DuckDB files, ported from Insights'
`insights_data_source_v3/connectors/duckdb.py`.

Distinct from `site_warehouse()` in this package's `__init__`: that is *the*
per-site warehouse the Data Store imports into, at a fixed path. These are
sources somebody added - a `.duckdb` file under the site's private files, or a
remote/DuckLake URL - which the deployment reads and never writes.
"""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlparse

import frappe
import ibis
from frappe.utils import get_files_path


def get_duckdb_connection(data_source: Any, read_only: bool = True) -> Any:
	"""Open `data_source`'s DuckDB file, or attach it over HTTP."""
	name = data_source.name or frappe.scrub(data_source.title)
	db_name = data_source.database_name

	if db_name.startswith("http"):
		db = ibis.duckdb.connect()
		sql = get_http_secret(data_source, name, db_name)
		if sql:
			db.raw_sql(sql)
		attach_url = f"ducklake:{db_name}" if data_source.is_ducklake else db_name
		# Remote attachments are read-only regardless of the argument: the
		# caller is reading somebody else's lake, and DuckDB would otherwise
		# try to take a write lock over HTTP.
		db.attach(attach_url, name, read_only=True)
		db.raw_sql(f'USE "{name}"')
		return db

	return get_local_duckdb_connection(db_name, read_only=read_only)


def get_local_duckdb_connection(db_name: str, read_only: bool = True) -> Any:
	"""A `.duckdb` file under the site's private files.

	Created empty when absent, as Insights does: `read_only=True` against a
	missing path raises inside DuckDB, and a source somebody just added has
	nothing in it yet.
	"""
	path = os.path.join(os.path.realpath(get_files_path(is_private=1)), f"{db_name}.duckdb")

	if not os.path.exists(path):
		ibis.duckdb.connect(path).disconnect()

	return ibis.duckdb.connect(path, read_only=read_only)


def get_http_secret(data_source: Any, name: str, db_name: str) -> str | None:
	"""`CREATE SECRET` carrying this source's HTTP headers, or `None`.

	Insights interpolates header keys and values straight into the statement
	and escapes only the scope, so a header value containing a quote ends the
	string literal and everything after it is parsed as SQL. DuckDB has no
	bind parameters in `CREATE SECRET`, so both sides are escaped here instead
	of trusting the field: it is admin-only, but "admin-only" is an access
	control, not an argument for leaving an injection in place.
	"""
	headers = data_source.get("http_headers") or {}
	if not headers:
		return None

	try:
		parsed = urlparse(db_name)
		scope = f"{parsed.scheme}://{parsed.netloc}"
		secret_name = f"http_auth_{frappe.scrub(name)}"

		parsed_headers = frappe.parse_json(headers) if isinstance(headers, str) else headers
		pairs = ", ".join(f"'{_quote(k)}': '{_quote(v)}'" for k, v in parsed_headers.items())

		return f"""
			CREATE OR REPLACE SECRET {secret_name} (
				TYPE HTTP,
				SCOPE '{_quote(scope)}',
				EXTRA_HTTP_HEADERS MAP {{ {pairs} }}
			);
		"""
	except Exception as e:
		# Logged without the headers themselves: they are the credential.
		frappe.log_error(title="Nakhoda: could not build DuckDB HTTP secret", message=str(e))
		return None


def _quote(value: Any) -> str:
	"""Escape a SQL single-quoted literal the way SQL itself does."""
	return str(value).replace("'", "''")
