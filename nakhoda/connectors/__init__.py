"""Where the engine gets its tables from.

Two backends, one interface. The compiler never learns which it is targeting -
it is handed a `TableResolver` and returns an unexecuted ibis expression, so the
same pipeline runs against the DuckDB warehouse or straight against the site's
MariaDB without changing a line of it.

The site connection is deliberately the ordinary Frappe database user, not a
second superuser channel. Insights' ML surface opened one of those and then grew
17 endpoints behind it that never checked a permission (`00-REPORT.md` §6.5);
the connection being privileged is what made forgetting so expensive. Here the
privilege that matters is removed one layer up, in `permitted_resolver`, and the
connection carries no authority the caller did not already have.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import ibis
import ibis.expr.types as ir

if TYPE_CHECKING:
	import pandas as pd

#: Filename of the per-site warehouse, under the site's private files.
WAREHOUSE_FILE = "nakhoda.duckdb"


@dataclass(frozen=True)
class Connector:
	"""A backend plus the identity of the data in it.

	`identity` goes into the cache key. It is not decoration: the same compiled
	SQL means different rows against a different site or a stale warehouse, and
	a cache that cannot tell those apart serves one tenant's numbers to another.
	"""

	backend: Any
	identity: str

	def resolve(self, table: str) -> ir.Table:
		"""The unfiltered table. Not for callers - wrap it in `permitted_resolver`."""
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
	"""The site's own MariaDB, through the site's own credentials.

	Cached on `frappe.local` for the life of the request: a connection costs a
	TCP handshake and an auth round trip, and one analysis touches several
	tables.
	"""
	import frappe

	cached = getattr(frappe.local, "nakhoda_site_db", None)
	if cached is not None:
		return cached
	conf = frappe.conf
	backend = ibis.mysql.connect(
		host=conf.get("db_host", "127.0.0.1"),
		port=int(conf.get("db_port") or 3306),
		user=conf.get("db_name"),
		password=conf.get("db_password"),
		database=conf.get("db_name"),
	)
	connector = Connector(backend=backend, identity=f"site:{frappe.local.site}")
	frappe.local.nakhoda_site_db = connector
	return connector
