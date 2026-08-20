# Copyright (c) 2026, Nakhoda and contributors
# For license information, please see license.txt
"""One row per `agent.manager.ask()` call - the audit trail invariant 8 in
`12-build-plan.md` names explicitly: prompt, tools, operations, SQL, rows,
tokens and cost, plus the tier used and the structural reason it was chosen.

Written by the manager with `ignore_permissions=True` - like `Error Log` or
`Activity Log`, a caller answering their own question should not also need
`create` on the log of it. `Nakhoda User` still reads their own rows
(`if_owner` in `nakhoda_agent_run.json`), so an answer's SQL stays reopenable
by whoever asked - the trust proposition `13-agent-design.md` §3 argues for.
Nothing here is submittable: it is a record, not an asset to approve.
"""

from __future__ import annotations

from frappe.model.document import Document


class NakhodaAgentRun(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		assumptions: DF.Code | None
		degradation_reason: DF.SmallText | None
		degraded: DF.Check
		error: DF.SmallText | None
		escalated: DF.Check
		escalation_reason: DF.SmallText | None
		execution_time: DF.Float
		matched_verified_query: DF.Link | None
		model: DF.Data | None
		operations: DF.Code | None
		question: DF.SmallText
		row_count: DF.Int
		space: DF.Link | None
		sql: DF.Code | None
		status: DF.Literal["ok", "error"]
		source: DF.Literal["generated", "verified"]
		thread_turn: DF.Link | None
		tier: DF.Literal["", "FAST", "BALANCED", "PREMIUM"]
		tier_reason: DF.SmallText | None
		user: DF.Link
	# end: auto-generated types
