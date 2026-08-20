# Copyright (c) 2026, Nakhoda and contributors
# For license information, please see license.txt
"""PostgreSQL, ported from Insights'
`insights_data_source_v3/connectors/postgresql.py`.

Two ways in, as Insights has: a full connection string when the deployment
already has one (managed Postgres hands them out), or the field-by-field form.
"""

from __future__ import annotations

from typing import Any

import ibis

#: PostgreSQL's default port - see `mariadb.DEFAULT_PORT` for why a literal
#: zero from an untouched `Int` field must never reach the driver.
DEFAULT_PORT = 5432


def get_postgres_connection(data_source: Any) -> Any:
	"""Open `data_source`'s PostgreSQL.

	Insights passes its stored connection string through `quote_plus` before
	handing it to `ibis.connect`. That is percent-encoding an entire URI,
	`://` included, so a real DSN comes out unparseable - it only ever worked
	for strings that needed no quoting. The string is handed over as stored
	here; a credential inside it needs encoding by whoever wrote it, which is
	also true of every other client that reads a DSN.
	"""
	if data_source.connection_string:
		return ibis.connect(data_source.connection_string)

	password = data_source.get_password("password", raise_exception=False)
	port = int(data_source.port or DEFAULT_PORT)
	return ibis.postgres.connect(
		host=data_source.host,
		port=port,
		user=data_source.username,
		password=password,
		database=data_source.database_name,
		schema=data_source.get("schema") or None,
		sslmode="require" if data_source.use_ssl else None,
	)
