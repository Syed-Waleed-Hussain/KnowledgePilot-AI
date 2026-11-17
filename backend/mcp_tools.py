"""Small, read-only MCP tools used by the local question workflow."""

import json
import logging
from time import perf_counter
from collections.abc import Callable
from typing import Any

from mcp import Client
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from backend import course_store

logger = logging.getLogger(__name__)


def _record(trace: list[dict[str, Any]] | None, step: str, status: str, started: float) -> None:
    event = {"step": step, "status": status, "duration_ms": round((perf_counter() - started) * 1000, 2)}
    if trace is not None:
        trace.append(event)
    logger.info("phase4_trace step=%s status=%s duration_ms=%.2f", step, status, event["duration_ms"])


def build_document_server(search_callback: Callable[..., list[dict[str, Any]]], *, trusted_user_id: str) -> MCPServer:
    """Create an in-process MCP server bound to this API process's RAG store."""
    server = MCPServer("KnowledgePilot local course documents")

    @server.tool()
    def search_course_documents(
        query: str, course_id: str, user_id: str, limit: int = 6,
        page: int | None = None,
    ) -> str:
        """Search indexed passages in one course owned by the signed-in user."""
        query = query.strip()
        if not query or len(query) > 3000:
            raise ToolError("Search query must contain 1 to 3000 characters.")
        if not course_id or len(course_id) > 100 or not user_id or len(user_id) > 200:
            raise ToolError("Course or user identifier is invalid.")
        if user_id != trusted_user_id or not course_store.course_exists(course_id, trusted_user_id):
            raise ToolError("Course unavailable or access denied.")
        bounded_limit = max(1, min(int(limit), 6))
        results = search_callback(
            query=query,
            course_id=course_id,
            user_id=user_id,
            limit=bounded_limit,
            page=page,
        )
        # MCP output contains only the minimum evidence required to answer.
        return json.dumps(results, ensure_ascii=False)

    return server


async def call_document_search(
    server: MCPServer,
    *,
    query: str,
    course_id: str,
    user_id: str,
    limit: int = 6,
    page: int | None = None,
    trace: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Call the MCP tool through the SDK's local in-memory protocol client."""
    # Legacy mode keeps the current in-process MCP server local while exercising
    # the SDK's JSON-RPC transport and initialize handshake (rather than its
    # newer direct-dispatch embedding shortcut).
    async with Client(server, mode="legacy", read_timeout_seconds=15) as client:
        started = perf_counter()
        try:
            available = await client.list_tools()
            names = {tool.name for tool in available.tools}
            if "search_course_documents" not in names:
                raise RuntimeError("The MCP server did not advertise the document search tool.")
            _record(trace, "mcp.tool_discovery", "ok", started)
        except Exception:
            _record(trace, "mcp.tool_discovery", "error", started)
            raise

        started = perf_counter()
        try:
            result = await client.call_tool(
                "search_course_documents",
                {
                    "query": query,
                    "course_id": course_id,
                    "user_id": user_id,
                    "limit": limit,
                    "page": page,
                },
            )
            if result.is_error:
                raise RuntimeError("The local MCP document search failed.")
            value = next((json.loads(block.text) for block in result.content if getattr(block, "text", None)), None)
            if not isinstance(value, list):
                raise RuntimeError("The local MCP tool returned an invalid result.")
            _record(trace, "mcp.search_course_documents", "ok", started)
            return value
        except Exception:
            _record(trace, "mcp.search_course_documents", "error", started)
            raise
