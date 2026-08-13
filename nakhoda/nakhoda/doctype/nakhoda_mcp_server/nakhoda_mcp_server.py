# Copyright (c) 2026, Nakhoda and contributors
# For license information, please see license.txt
"""A third-party MCP server an asker's questions may call tools on
(`12-build-plan.md` Phase 6). Registration is admin-only (`nakhoda_mcp_server.json`
permissions) precisely because `agent/plugins.py` trusts `command` / `url` on
this doctype as much as any other bench dependency - see that module's
docstring for the three gates (data reachability, catalog reachability,
approval provenance) this record feeds.
"""

from __future__ import annotations

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class NakhodaMCPServer(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		args: DF.SmallText | None
		command: DF.Data | None
		description: DF.SmallText | None
		enabled: DF.Check
		last_checked: DF.Datetime | None
		last_error: DF.SmallText | None
		space: DF.Link
		status: DF.Literal["Untested", "Reachable", "Unreachable"]
		timeout_seconds: DF.Int
		title: DF.Data
		transport: DF.Literal["Stdio", "Streamable HTTP"]
		url: DF.Data | None
	# end: auto-generated types

	def validate(self) -> None:
		if self.transport == "Stdio" and not self.command:
			frappe.throw(frappe._("Command is required for a Stdio server."))
		if self.transport == "Streamable HTTP" and not self.url:
			frappe.throw(frappe._("URL is required for a Streamable HTTP server."))

	@frappe.whitelist()
	def test_connection(self) -> dict[str, str]:
		"""Reachability, recorded as this doctype's own admin - never as the
		eventual asker, because no question has been asked yet. Reports the
		failure rather than raising it, matching `NakhodaDataSource.test_connection`."""
		import asyncio

		from nakhoda.agent import plugins

		try:
			tools = asyncio.run(plugins._list_tools_live(self, frappe.session.user))
			status = "Reachable"
			message = frappe._("Connected. {0} tool(s) found.").format(len(tools))
		except Exception as exc:
			status = "Unreachable"
			message = str(exc)
		self.db_set(
			{
				"status": status,
				"last_checked": now_datetime(),
				"last_error": "" if status == "Reachable" else message,
			},
			update_modified=False,
		)
		return {"status": status, "message": message}
