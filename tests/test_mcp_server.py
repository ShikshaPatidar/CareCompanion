import json

import pytest

pytest.importorskip("mcp")


async def test_server_exposes_the_three_scheduling_tools(gateway, audit):
    from carecompanion.mcp_server.server import build_mcp_server

    server = build_mcp_server(gateway, audit)
    names = {t.name for t in await server.list_tools()}
    assert names == {"find_patient", "get_appointments", "book_appointment"}


async def test_server_tools_enforce_the_same_rules(gateway, audit):
    from carecompanion.mcp_server.server import build_mcp_server

    server = build_mcp_server(gateway, audit)
    content = await server.call_tool(
        "book_appointment",
        {"patient_id": "PAT-1001", "department": "Cardiology", "preferred_day": "2026-10-15"},
    )
    text = content[0][0].text if isinstance(content, tuple) else content[0].text
    assert json.loads(text)["status"] == "duplicate"
