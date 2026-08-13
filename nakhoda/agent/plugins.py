# Copyright (c) 2026, Nakhoda and contributors
# For license information, please see license.txt
"""Client-side MCP: a `Nakhoda Space` can register third-party plugin
servers, and the agent can call their tools (`12-build-plan.md` Phase 6).
Three gates this file exists to keep, each tied to a real limitation found
by reading the installed SDK source rather than trusting its docs:

Gate A (data reachability) - a plugin must run under the *asker's*
permissions, never a service credential broader than them. MCP has no
built-in identity channel, so the asker's `frappe.session.user` is threaded
to every transport as a plugin-author contract: env `NAKHODA_ASKER` for
Stdio, header `X-Nakhoda-Asker` for Streamable HTTP. Whether a given plugin
honours that contract is the plugin's problem; whether Nakhoda ever sends a
wider credential than the asker's is this file's.

Gate B (catalog reachability) - `agents.mcp.server.MCPServer`'s own
`cache_tools_list` is one flag per server object with no user scoping
(verified against installed `agents 0.20.0`: `MCPServer._tools_list` has
no per-caller key). Never enable it. `list_tools` below keys its own cache
`(server, asker)` so one user's catalog can never leak into another's.

Gate C (approval provenance) - MRTR (2026-07-28's multi-round-trip flow,
verified against installed `mcp 2.0.0`): a tool call can return
`InputRequiredResult` instead of completing, carrying an `ElicitRequest`
the human must answer before the SAME call is retried with the answer and
the server's echoed `request_state`. `openai-agents 0.20.0` has no MRTR
support at all (`agents/mcp/server.py` never references `InputRequiredResult`
or `allow_input_required`) - the `_ElicitingMCPServer` classes below are a
thin subclass calling `ClientSession.call_tool(..., allow_input_required=True)`
directly, so a form-mode elicitation surfaces to this file instead of
hanging or silently failing. Only form-mode elicitation is handled: a
plugin asking for *sampling* (a model completion) or *roots* (filesystem
access) is declined outright, because Nakhoda's plugin agent is not in the
business of donating either capability to a third party. Every surfaced
elicitation is returned with `origin="PLUGIN"` - the inspector badge that
tells it apart from `FROM QUESTION` / `SEMANTIC MODEL` / `LINK GRAPH` /
`INJECTED` (`13-agent-design.md` §2.1) - so a plugin can never render a
prompt indistinguishable from Nakhoda's own.

One simplification, stated plainly rather than hidden: resuming an
elicitation does not resume the agent's exact conversation state (the
Agents SDK has no public hook for that mid-tool-call). It answers the one
paused tool call directly against the MCP session, then starts a fresh
top-level turn seeded with the original question plus that tool's result -
the same "ask again, now armed with the answer" shape Nakhoda's own
correction UI already uses for a re-run (`14-frontend-design.md`).
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

import frappe

#: How long one user's tool catalog for one server is trusted before a
#: fresh `list_tools` round trip (Gate B: scoped by (server, asker), never
#: global - a short TTL bounds staleness without reintroducing the SDK's
#: unscoped cache).
_CACHE_TTL = 300

#: How long a paused elicitation waits for its answer before the captured
#: call is dropped - long enough for a human to read one form, short
#: enough that a stale one can't resurface hours later.
_ELICIT_TTL = 600

#: Matches the typescript-sdk / csharp-sdk / go-sdk default for MRTR retry
#: rounds (`mcp.client._input_required.DEFAULT_INPUT_REQUIRED_MAX_ROUNDS`) -
#: reused rather than re-guessed.
_MAX_INPUT_ROUNDS = 10

#: Bounded like `13-agent-design.md` opening 5 recommends, but flat rather
#: than phase-budgeted until Phase 6 has a second data point to budget
#: against: one call to decide, a few to act, one to summarise.
DEFAULT_MAX_TURNS = 4


class PluginError(Exception):
	"""A plugin-turn-level failure the caller should treat as "no plugin
	answer", not surface raw - mirrors `providers.ModelError`'s contract."""


class _NeedsElicitation(Exception):
	"""Raised inside `_ElicitingMCPServer.call_tool` to unwind out of
	`Runner.run` the moment a plugin's tool call pauses on MRTR. Caught by
	`_run_live`/`_resume_live`; never escapes this module."""

	def __init__(
		self,
		elicit_id: str,
		server: str,
		tool: str,
		arguments: dict[str, Any],
		message: str,
		schema: dict[str, Any],
	):
		super().__init__(message)
		self.elicit_id = elicit_id
		self.server = server
		self.tool = tool
		self.arguments = arguments
		self.message = message
		self.schema = schema


@dataclass
class PendingElicitation:
	"""One MRTR form-mode elicitation, surfaced for the human to answer.
	`elicit_id` is the resume key; it is meaningless without the asker who
	owns it, so callers must also carry `user` back in on resume."""

	elicit_id: str
	server: str
	tool: str
	message: str
	schema: dict[str, Any]
	origin: str = "PLUGIN"


@dataclass
class ToolCall:
	"""One tool call the agent made and that ran - the transcript row Gate
	A/C are checked against. `origin` is always "PLUGIN": the inspector
	badge that tells this apart from `FROM QUESTION` / `SEMANTIC MODEL` /
	`LINK GRAPH` / `INJECTED` (`13-agent-design.md` §2.1)."""

	server: str
	tool: str
	args: dict[str, Any]
	result_summary: str
	origin: str = "PLUGIN"


@dataclass
class PluginResult:
	status: Literal["ok", "needs_elicitation", "no_tools", "error"]
	answer: str | None = None
	tool_calls: list[ToolCall] = field(default_factory=list)
	pending: PendingElicitation | None = None
	error: str | None = None


def _asker_env(user: str) -> dict[str, str]:
	return {"NAKHODA_ASKER": user}


def _asker_headers(user: str) -> dict[str, str]:
	return {"X-Nakhoda-Asker": user}


def enabled_servers(space: str | None) -> list[Any]:
	"""Every non-disabled `Nakhoda MCP Server` registered on this space, or
	`[]` for no space / no servers - the caller's signal to skip the whole
	plugin path and behave exactly as it did before Phase 6."""
	if not space:
		return []
	names = frappe.get_all(
		"Nakhoda MCP Server", filters={"space": space, "enabled": 1}, pluck="name", order_by="creation asc"
	)
	return [frappe.get_doc("Nakhoda MCP Server", name) for name in names]


def _elicit_form_params(request: Any) -> Any | None:
	"""An `ElicitRequest` in form mode, or `None` for anything else (URL-mode
	elicitation, sampling, roots) - the three shapes MRTR can embed that
	this file declines rather than proxy to a human (see module docstring)."""
	params = getattr(request, "params", None)
	if params is not None and getattr(params, "mode", None) == "form":
		return params
	return None


class _ElicitingMCPServer:
	"""Mixed into `MCPServerStdio`/`MCPServerStreamableHttp` below. Overrides
	`call_tool` to drive MRTR itself (`ClientSession.call_tool(...,
	allow_input_required=True)`) instead of the SDK's default, which has no
	MRTR support at all. `pending_answer`, when set, supplies exactly one
	`(tool_name, elicit key) -> ElicitResult` answer for a resumed call;
	anything else that needs elicitation still pauses."""

	pending_answer: tuple[str, Any] | None = None  # (elicit_id, ElicitResult)

	async def call_tool(
		self, tool_name: str, arguments: dict[str, Any] | None, meta: dict[str, Any] | None = None
	):
		from mcp_types import ElicitResult, ErrorData

		session = self.session  # type: ignore[attr-defined]
		if session is None:
			raise PluginError(f"{self.name} not connected")  # type: ignore[attr-defined]

		responses: dict[str, Any] | None = None
		request_state: str | None = None
		rounds = 0
		while True:
			result = await session.call_tool(
				tool_name,
				arguments,
				input_responses=responses,
				request_state=request_state,
				allow_input_required=True,
			)
			if getattr(result, "result_type", "complete") != "input_required":
				return result

			rounds += 1
			if rounds > _MAX_INPUT_ROUNDS:
				raise PluginError(f"{self.name}.{tool_name}: exceeded {_MAX_INPUT_ROUNDS} MRTR rounds")

			input_requests = result.input_requests or {}
			responses = {}
			unanswered_key = None
			unanswered_form = None
			for key, request in input_requests.items():
				form = _elicit_form_params(request)
				if form is None:
					responses[key] = ErrorData(
						code=-32000, message="plugin requested a capability Nakhoda does not offer"
					)
					continue
				if self.pending_answer is not None and self.pending_answer[0] == key:
					responses[key] = self.pending_answer[1]
					continue
				unanswered_key, unanswered_form = key, form

			if unanswered_key is not None:
				raise _NeedsElicitation(
					elicit_id=unanswered_key,
					server=self.name,  # type: ignore[attr-defined]
					tool=tool_name,
					arguments=arguments or {},
					message=unanswered_form.message,
					schema=unanswered_form.requested_schema.model_dump(by_alias=True, exclude_none=True)
					if hasattr(unanswered_form.requested_schema, "model_dump")
					else dict(unanswered_form.requested_schema),
				)
			request_state = result.request_state


def _build_server(doc: Any, user: str, pending_answer: tuple[str, Any] | None = None):
	"""One registered server, as an SDK client transport. `cache_tools_list`
	is always `False` (Gate B: `list_tools` below is the only cache, and it
	is scoped)."""
	from agents.mcp import MCPServerStdio, MCPServerStreamableHttp

	class ElicitingStdio(_ElicitingMCPServer, MCPServerStdio):
		pass

	class ElicitingHttp(_ElicitingMCPServer, MCPServerStreamableHttp):
		pass

	if doc.transport == "Stdio":
		args = [line.strip() for line in (doc.args or "").splitlines() if line.strip()]
		server = ElicitingStdio(
			name=doc.name,
			params={"command": doc.command, "args": args, "env": _asker_env(user)},
			cache_tools_list=False,
			client_session_timeout_seconds=doc.timeout_seconds or 10,
		)
	elif doc.transport == "Streamable HTTP":
		server = ElicitingHttp(
			name=doc.name,
			params={"url": doc.url, "headers": _asker_headers(user)},
			cache_tools_list=False,
			client_session_timeout_seconds=doc.timeout_seconds or 10,
		)
	else:
		raise PluginError(f"{doc.name}: unknown transport {doc.transport!r}")
	server.pending_answer = pending_answer
	return server


def _cache_key(server_name: str, user: str) -> str:
	return f"nakhoda:mcp:tools:{server_name}:{user}"


async def _list_tools_live(doc: Any, user: str) -> list[dict[str, Any]]:
	server = _build_server(doc, user)
	async with server:
		tools = await server.list_tools()
	return [{"name": t.name, "description": t.description or "", "server": doc.name} for t in tools]


def list_tools(space: str | None, user: str) -> list[dict[str, Any]]:
	"""Every tool on every enabled server for this space, as this user would
	see them (Gate B). Cached per `(server, user)`; never per server alone."""
	import asyncio

	out: list[dict[str, Any]] = []
	for doc in enabled_servers(space):
		key = _cache_key(str(doc.name), user)
		cached = frappe.cache().get_value(key)
		if cached is not None:
			out.extend(json.loads(cached))
			continue
		try:
			tools = asyncio.run(_list_tools_live(doc, user))
		except Exception as exc:
			frappe.log_error(f"MCP list_tools failed for {doc.name}: {exc}", "Nakhoda Plugin")
			continue
		frappe.cache().set_value(key, json.dumps(tools), expires_in_sec=_CACHE_TTL)
		out.extend(tools)
	return out


def _asker_model(model_name: str):
	"""The same `NAKHODA_AGENT_*`-namespaced client `providers.py` uses,
	wrapped for the Agents SDK - one client construction path, not two."""
	from agents import OpenAIChatCompletionsModel
	from openai import AsyncOpenAI

	client = AsyncOpenAI(
		api_key=os.environ["NAKHODA_AGENT_API_KEY"],
		base_url=os.environ.get("NAKHODA_AGENT_BASE_URL") or None,
	)
	return OpenAIChatCompletionsModel(model=model_name, openai_client=client)


def _make_agent(model_name: str, live_servers: list[Any], instructions: str | None = None):
	from agents import Agent

	return Agent(
		name="Nakhoda Plugin Agent",
		instructions=instructions
		or (
			"Answer the question using the available plugin tools if they help. "
			"If no tool is relevant, say so plainly - do not invent an answer."
		),
		model=_asker_model(model_name),
		mcp_servers=live_servers,
	)


def _extract_tool_calls(result: Any) -> list[ToolCall]:
	from agents import ToolCallItem, ToolCallOutputItem

	calls: dict[str, dict[str, Any]] = {}
	for item in result.new_items:
		if isinstance(item, ToolCallItem):
			raw = item.raw_item
			args_raw = raw.get("arguments") if isinstance(raw, dict) else getattr(raw, "arguments", None)
			try:
				args = json.loads(args_raw) if isinstance(args_raw, str) else (args_raw or {})
			except (TypeError, ValueError):
				args = {}
			server = getattr(item.tool_origin, "mcp_server_name", None) or "unknown"
			calls[item.call_id or item.tool_name] = {
				"server": server,
				"tool": item.tool_name or "unknown",
				"args": args,
				"result_summary": "",
			}
		elif isinstance(item, ToolCallOutputItem) and item.call_id in calls:
			calls[item.call_id]["result_summary"] = str(item.output)[:500]
	return [ToolCall(**c) for c in calls.values()]


def _elicit_cache_key(elicit_id: str, user: str) -> str:
	return f"nakhoda:mcp:elicit:{elicit_id}:{user}"


class _AsyncExitStackServers:
	"""Connects every server in the list, in order, and disconnects all of
	them (even the ones after a mid-list failure) on the way out."""

	def __init__(self, servers: list[Any]):
		self._servers = servers
		self._entered: list[Any] = []

	async def __aenter__(self) -> list[Any]:
		for s in self._servers:
			await s.__aenter__()
			self._entered.append(s)
		return self._entered

	async def __aexit__(self, *exc):
		for s in reversed(self._entered):
			await s.__aexit__(*exc)


async def _run_live(
	question: str,
	model_name: str,
	docs: list[Any],
	user: str,
	max_turns: int,
	*,
	space_docs: list[str],
	extra_instructions: str | None = None,
) -> PluginResult:
	from agents import MaxTurnsExceeded, Runner

	servers = [_build_server(doc, user) for doc in docs]
	try:
		async with _AsyncExitStackServers(servers) as live_servers:
			agent = _make_agent(model_name, live_servers, extra_instructions)
			try:
				result = await Runner.run(agent, question, max_turns=max_turns)
			except MaxTurnsExceeded:
				return PluginResult(
					status="error", error=f"exceeded {max_turns} turns without a final answer"
				)
	except _NeedsElicitation as pause:
		elicit_id = uuid.uuid4().hex
		frappe.cache().set_value(
			_elicit_cache_key(elicit_id, user),
			json.dumps(
				{
					"question": question,
					"model_name": model_name,
					"space_docs": space_docs,
					"server": pause.server,
					"tool": pause.tool,
					"key": pause.elicit_id,
				}
			),
			expires_in_sec=_ELICIT_TTL,
		)
		return PluginResult(
			status="needs_elicitation",
			pending=PendingElicitation(
				elicit_id=elicit_id,
				server=pause.server,
				tool=pause.tool,
				message=pause.message,
				schema=pause.schema,
			),
		)

	tool_calls = _extract_tool_calls(result)
	if not tool_calls:
		return PluginResult(status="no_tools")
	return PluginResult(status="ok", answer=result.final_output, tool_calls=tool_calls)


async def _answer_elicitation(doc: Any, user: str, tool: str, key: str, content: dict[str, Any]) -> str:
	"""Answers exactly the one paused tool call directly against the MCP
	session - not through `Runner.run`, since there is no in-flight agent
	turn left to resume it inside (see module docstring)."""
	from mcp_types import ElicitResult

	server = _build_server(doc, user, pending_answer=(key, ElicitResult(action="accept", content=content)))
	async with server:
		result = await server.call_tool(tool, None)
	texts = [getattr(block, "text", "") for block in getattr(result, "content", []) if hasattr(block, "text")]
	return "\n".join(t for t in texts if t) or json.dumps(getattr(result, "structured_content", None) or {})


def run(
	question: str,
	*,
	model_name: str,
	space: str | None,
	user: str,
	max_turns: int = DEFAULT_MAX_TURNS,
) -> PluginResult:
	"""One question, against every enabled plugin server on `space`, as
	`user`. Synchronous wrapper - `manager.ask()` has no async caller today
	and adding one is out of scope for introducing plugins. Returns
	`no_tools` immediately (no model call at all) when the space has no
	enabled servers, so a space without plugins pays nothing extra."""
	import asyncio

	import openai

	from nakhoda.agent import providers

	docs = enabled_servers(space)
	if not docs:
		return PluginResult(status="no_tools")
	try:
		return asyncio.run(
			_run_live(question, model_name, docs, user, max_turns, space_docs=[str(d.name) for d in docs])
		)
	except openai.RateLimitError as exc:
		raise providers.RateLimited(str(exc)) from exc
	except openai.APIError as exc:
		raise providers.ModelError(str(exc)) from exc


def resume_elicitation(
	elicit_id: str, content: dict[str, Any], *, user: str, max_turns: int = DEFAULT_MAX_TURNS
) -> PluginResult:
	"""Answer one paused elicitation with `content` (matching the schema in
	`PendingElicitation.schema`), then start a fresh top-level turn seeded
	with the original question and that tool's result. Only the `user` who
	owns the cached elicitation can resolve it - a different user's
	`elicit_id` guess reads as "expired or not found"."""
	import asyncio

	import openai

	from nakhoda.agent import providers

	async def _go() -> PluginResult:
		raw = frappe.cache().get_value(_elicit_cache_key(elicit_id, user))
		if raw is None:
			return PluginResult(status="error", error="elicitation expired or not found")
		frappe.cache().delete_value(_elicit_cache_key(elicit_id, user))
		payload = json.loads(raw)

		docs = [frappe.get_doc("Nakhoda MCP Server", name) for name in payload["space_docs"]]
		target_doc = next(d for d in docs if str(d.name) == payload["server"])
		tool_result = await _answer_elicitation(target_doc, user, payload["tool"], payload["key"], content)

		extra = (
			f"You already called the tool `{payload['tool']}` on server `{payload['server']}`, "
			f"which required additional input from the user. The user answered, and the tool "
			f"returned:\n\n{tool_result}\n\nUse this to answer the original question."
		)
		return await _run_live(
			payload["question"],
			payload["model_name"],
			docs,
			user,
			max_turns,
			space_docs=payload["space_docs"],
			extra_instructions=extra,
		)

	try:
		return asyncio.run(_go())
	except openai.RateLimitError as exc:
		raise providers.RateLimited(str(exc)) from exc
	except openai.APIError as exc:
		raise providers.ModelError(str(exc)) from exc
