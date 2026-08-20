# Copyright (c) 2026, Nakhoda and contributors
# For license information, please see license.txt
"""ClickHouse, ported from Insights'
`insights_data_source_v3/connectors/clickhouse.py`.
"""

from __future__ import annotations

from typing import Any

import ibis

#: ClickHouse's HTTP interface. 9000 is the native protocol, which is *not*
#: what ibis' clickhouse backend speaks, so a user copying the port out of a
#: server config would otherwise hit a silent protocol mismatch.
DEFAULT_PORT = 8123


def get_clickhouse_connection(data_source: Any) -> Any:
	"""Open `data_source`'s ClickHouse.

	`clickhouse_connect` is installed on this bench, so the ImportError guard
	Insights carries would never fire here - but a deployment that trimmed
	optional extras deserves the same one-line answer instead of a traceback
	through ibis' backend loader.
	"""
	try:
		import ibis.backends.clickhouse
	except ImportError as e:
		raise ImportError(
			"ClickHouse support needs the 'ibis-framework[clickhouse]' extra (clickhouse-connect)."
		) from e

	password = data_source.get_password("password", raise_exception=False)
	port = int(data_source.port or DEFAULT_PORT)
	return ibis.clickhouse.connect(
		host=data_source.host,
		port=port,
		user=data_source.username,
		password=password,
		database=data_source.database_name,
		client_name="nakhoda",
		secure=bool(data_source.use_ssl),
	)
