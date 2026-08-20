"""Where the engine gets its tables from.

Several backends, one interface. The compiler never learns which it is
targeting - it is handed a `TableResolver` and returns an unexecuted ibis
expression, so the same pipeline runs against the DuckDB warehouse, straight
against the site's MariaDB, or against a Postgres somebody added, without
changing a line of it.

The site connection is deliberately the ordinary Frappe database user, not a
second superuser channel. Insights' ML surface opened one of those and then grew
17 endpoints behind it that never checked a permission (`00-REPORT.md` §6.5);
the connection being privileged is what made forgetting so expensive. Here the
privilege that matters is removed one layer up, in `permitted_resolver`, and the
connection carries no authority the caller did not already have.

External sources (`source_type == "External Database"`, ported from Insights'
`Insights Data Source v3`) are the exception that proves the rule: they *are* a
credential a user typed, so they are reachable only through a row whose write
permission is admin-only, they are opened read-only wherever the backend can
express it, and `engine/permissions.py` never claims to filter them - a foreign
database has no `tabDocPerm` to filter by, which is stated on the row itself
rather than left for a reader to discover.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import ibis
import ibis.expr.types as ir

from nakhoda.connectors.clickhouse import get_clickhouse_connection
from nakhoda.connectors.duckdb import get_duckdb_connection, get_local_duckdb_connection
from nakhoda.connectors.frappe_db import (
	get_frappedb_connection,
	get_frappedb_table_links,
	get_primary_data_source,
	get_sitedb_connection,
	is_frappe_db,
)
from nakhoda.connectors.mariadb import get_mariadb_connection
from nakhoda.connectors.postgresql import get_postgres_connection
from nakhoda.connectors.sqlite import get_sqlite_connection

if TYPE_CHECKING:
	import pandas as pd

__all__ = [
	"BACKENDS",
	"WAREHOUSE_FILE",
	"Connector",
	"external",
	"get_clickhouse_connection",
	"get_duckdb_connection",
	"get_frappedb_connection",
	"get_frappedb_table_links",
	"get_local_duckdb_connection",
	"get_mariadb_connection",
	"get_postgres_connection",
	"get_primary_data_source",
	"get_sitedb_connection",
	"get_sqlite_connection",
	"is_frappe_db",
	"site_db",
	"site_warehouse",
	"warehouse",
]

#: Filename of the per-site warehouse, under the site's private files.
WAREHOUSE_FILE = "nakhoda.duckdb"

#: `database_type` -> the function that opens it. A table rather than an
#: `if` chain because two other places need the same answer without importing
#: a driver: the doctype's `database_type` options, and `api/data_sources.py`
#: when it tells the UI which types this deployment can actually open.
#:
#: Insights also ships BigQuery and MSSQL connectors. Neither is here:
#: `google-cloud-bigquery` and `pyodbc` are not installed on this bench, so
#: offering the option could only ever produce an ImportError at connect time,
#: after the user had typed a credential into a form.
BACKENDS = {
	"MariaDB": get_mariadb_connection,
	"PostgreSQL": get_postgres_connection,
	"ClickHouse": get_clickhouse_connection,
	"DuckDB": get_duckdb_connection,
	"SQLite": get_sqlite_connection,
}


@dataclass(frozen=True)
class Connector:
	"""A backend plus the identity of the data in it.

	`identity` goes into the cache key. It is not decoration: the same compiled
	SQL means different rows against a different site or a stale warehouse, and
	a cache that cannot tell those apart serves one tenant's numbers to another.

	`describes_doctypes` says whether the tables in this backend are the ones
	`tabDocPerm` talks about. The site database and the warehouse hold copies of
	this site's DocTypes, so Frappe's row and column rules mean something there.
	A foreign schema has no such rules, and `engine.permissions.for_connector`
	reads this flag instead of guessing from a table name - see that function
	for why guessing would be worse than asking.
	"""

	backend: Any
	identity: str
	describes_doctypes: bool = True

	def resolve(self, table: str) -> ir.Table:
		"""The unfiltered table. Not for callers - wrap it in `for_connector`."""
		return self.backend.table(table)

	def execute(self, expr: ir.Expr) -> pd.DataFrame:
		return self.backend.execute(expr)

	def sql(self, expr: ir.Expr) -> str:
		return str(ibis.to_sql(expr, dialect=self.dialect))

	@property
	def dialect(self) -> str:
		return self.backend.name


def warehouse(path: str, *, read_only: bool = True) -> Connector:
	"""The site's DuckDB warehouse."""
	backend = ibis.duckdb.connect(path, read_only=read_only)
	return Connector(backend=backend, identity=f"duckdb:{path}")


def site_warehouse(*, read_only: bool = True) -> Connector:
	"""The warehouse for the current site."""
	import frappe

	path = frappe.get_site_path("private", "files", WAREHOUSE_FILE)
	return Connector(backend=ibis.duckdb.connect(path, read_only=read_only), identity=f"duckdb:{path}")


def site_db() -> Connector:
	"""The site's own database, through the site's own credentials.

	Cached on `frappe.local` for the life of the request: a connection costs a
	TCP handshake and an auth round trip, and one analysis touches several
	tables.

	Delegates to `frappe_db.get_sitedb_connection`, which is also what an
	external Frappe site goes through - one connect path for Frappe-shaped
	databases, so a replica setting or a charset fix lands on both.
	"""
	import frappe

	cached = getattr(frappe.local, "nakhoda_site_db", None)
	if cached is not None:
		return cached
	connector = Connector(backend=get_sitedb_connection(), identity=f"site:{frappe.local.site}")
	frappe.local.nakhoda_site_db = connector
	return connector


def external(data_source: Any, *, read_only: bool = True) -> Connector:
	"""Open a user-configured `Nakhoda Data Source` row.

	`identity` is the row name plus its modification stamp: re-pointing a
	source at a different host is a different dataset under an unchanged
	pipeline, and a cache keyed on the name alone would keep answering with
	the old server's numbers.

	`describes_doctypes=False` even when the remote database is Frappe-shaped.
	A remote `tabSales Invoice` is not this site's Sales Invoice: applying this
	site's `tabDocPerm` to another site's rows would filter by rules that were
	never written about them, and report a permission notice for a filter that
	means nothing. Access to an external source is the read permission on the
	source row - stated in `api/data_sources.py`, enforced by the doctype's own
	permissions, and not silently re-described as row-level filtering.
	"""
	import frappe

	connect = BACKENDS.get(data_source.database_type)
	if connect is None:
		# `frappe.throw` raises, but it is not typed `NoReturn`, so the call
		# below stays inside the branch that proved `connect` exists.
		frappe.throw(
			frappe._("{0} is not a database type this deployment can open.").format(
				data_source.database_type or "?"
			)
		)
		raise frappe.ValidationError

	if connect is get_duckdb_connection:
		backend = connect(data_source, read_only=read_only)
	else:
		backend = connect(data_source)

	return Connector(
		backend=backend,
		identity=f"source:{data_source.name}:{data_source.modified}",
		describes_doctypes=False,
	)
