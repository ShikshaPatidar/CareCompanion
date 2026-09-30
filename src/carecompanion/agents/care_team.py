"""The care team: a coordinator agent that consults specialist agents (as in lab 6)."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from agent_framework import Agent

from carecompanion.agents.factory import AzureClients
from carecompanion.agents.prompts import PromptLibrary
from carecompanion.tools.hospital_tools import SchedulingTools


def build_coordinator(
    clients: AzureClients,
    prompts: PromptLibrary,
    scheduling: SchedulingTools,
    policy_tool: Callable[..., str],
    callback_tool: Callable[..., str],
    *,
    scheduler_tools_override: Sequence[Any] | None = None,
) -> Agent:
    """Assemble coordinator + specialists.

    scheduler_tools_override lets the scheduling specialist use a different tool source
    (for example our own MCP server) without changing anything else.
    """
    records = Agent(
        client=clients.chat_client(),
        name="RecordsSpecialist",
        description="Looks up patient records by name in the registry.",
        instructions=prompts.render("records_specialist"),
        tools=[scheduling.find_patient],
    )
    scheduler = Agent(
        client=clients.chat_client(),
        name="SchedulingSpecialist",
        description="Checks and books appointments for a known patient ID.",
        instructions=prompts.render("scheduling_specialist"),
        tools=list(scheduler_tools_override)
        if scheduler_tools_override is not None
        else [scheduling.get_appointments, scheduling.book_appointment],
    )
    return Agent(
        client=clients.chat_client(),
        name="CareCoordinator",
        instructions=prompts.render("coordinator"),
        tools=[
            records.as_tool(
                name="records_specialist",
                description="Look up a patient's ID by name.",
            ),
            scheduler.as_tool(
                name="scheduling_specialist",
                description="Check or book appointments for a patient ID.",
            ),
            policy_tool,
            callback_tool,
        ],
    )
