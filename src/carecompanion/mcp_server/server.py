"""Serve the same audited, validated scheduling tools over the Model Context Protocol."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from carecompanion.audit import AuditLog
from carecompanion.scheduling.ports import SchedulingGateway
from carecompanion.tools import build_scheduling_tools


def build_mcp_server(
    gateway: SchedulingGateway, audit: AuditLog, *, host: str = "127.0.0.1", port: int = 8765
) -> FastMCP:
    server = FastMCP("elmfield-scheduling", host=host, port=port)
    tools = build_scheduling_tools(gateway, audit)
    for fn in tools.as_list():
        server.add_tool(fn, name=fn.__name__, description=fn.__doc__)
    return server
