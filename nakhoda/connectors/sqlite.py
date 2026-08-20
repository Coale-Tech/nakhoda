# Copyright (c) 2026, Nakhoda and contributors
# For license information, please see license.txt
"""SQLite files, ported from Insights'
`insights_data_source_v3/connectors/sqlite.py`.
"""

from __future__ import annotations

import os
from typing import Any

import ibis
from frappe.utils import get_files_path


def get_sqlite_connection(data_source: Any) -> Any:
	"""Open `data_source`'s SQLite file, under the site's private files.

	Insights builds the absolute path and then calls `.lstrip("/")` on it,
	handing ibis a path relative to whatever the worker's cwd happens to be -
	the bench directory for a web request, something else for a background job.
	The absolute path is passed through here, and `ibis.sqlite.connect` is
	named explicitly rather than letting `ibis.connect` guess a backend from
	the file extension.
	"""
	path = os.path.join(
		os.path.realpath(get_files_path(is_private=1)),
		f"{data_source.database_name}.sqlite",
	)
	return ibis.sqlite.connect(path)
