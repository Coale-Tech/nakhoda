# Copyright (c) 2026, Nakhoda and contributors
# For license information, please see license.txt
"""MariaDB / MySQL, ported from Insights'
`insights_data_source_v3/connectors/mariadb.py`.

Returns a raw ibis backend, not a `Connector`: the wrapper carries a cache
identity (see `__init__.py`) that only the caller who knows *which row* this
is can supply.
"""

from __future__ import annotations

import warnings
from collections.abc import Callable
from functools import wraps
from typing import Any

import ibis

#: MariaDB's default port. Named because an unwritten `Int` field reads `0`,
#: and `port=0` fails with "connection refused" rather than anything a user
#: could act on.
DEFAULT_PORT = 3306


def suppress_ibis_utc_warning(func: Callable) -> Callable:
	"""ibis 11 warns on every connect against a server that refuses
	`SET time_zone` - which is most managed MariaDB. Insights suppresses the
	same warning at the same place; without it a page that opens four
	connections logs four warnings that no reader can act on.
	"""

	@wraps(func)
	def wrapper(*args: Any, **kwargs: Any) -> Any:
		with warnings.catch_warnings():
			warnings.filterwarnings("ignore", message="Unable to set session timezone")
			return func(*args, **kwargs)

	return wrapper


@suppress_ibis_utc_warning
def get_mariadb_connection(data_source: Any) -> Any:
	"""Open `data_source`'s MariaDB.

	`ssl_mode="VERIFY_CA"` when the row asks for SSL, exactly as Insights does:
	`REQUIRED` would encrypt the wire while accepting any certificate, which
	buys nothing against the attacker SSL is for.
	"""
	password = data_source.get_password("password", raise_exception=False)
	port = int(data_source.port or DEFAULT_PORT)
	return ibis.mysql.connect(
		host=data_source.host,
		port=port,
		user=data_source.username,
		password=password,
		database=data_source.database_name,
		charset="utf8mb4",
		use_unicode=True,
		ssl_mode="VERIFY_CA" if data_source.use_ssl else "DISABLED",
	)
