"""Composition root: the only place where concrete classes are chosen and wired together."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from datetime import date
from pathlib import Path

from carecompanion.app import CareCompanionApp
from carecompanion.audit import AuditLog
from carecompanion.config import Settings
from carecompanion.profile import HospitalProfile, load_profile
from carecompanion.safety import InputGuard, OutputGuard, SafetyMessages
from carecompanion.scheduling import SchedulingService
from carecompanion.scheduling.http_gateway import HttpSchedulingGateway
from carecompanion.scheduling.json_repository import (
    JsonAppointmentRepository,
    JsonPatientRepository,
)
from carecompanion.scheduling.ports import SchedulingGateway
from carecompanion.tools import CallbackQueue


def load_hospital(settings: Settings) -> HospitalProfile:
    return load_profile(settings.hospital_profile_path)


def build_audit(settings: Settings, name: str = "audit.jsonl") -> AuditLog:
    return AuditLog(settings.state_dir / name, log_content=settings.audit_log_content)


def build_local_gateway(
    settings: Settings,
    profile: HospitalProfile,
    *,
    state_path: Path | None = None,
    today=date.today,
) -> SchedulingService:
    return SchedulingService(
        patients=JsonPatientRepository(settings.data_dir / "patients.json"),
        appointments=JsonAppointmentRepository(
            seed_path=settings.data_dir / "appointments.json",
            state_path=state_path or settings.state_dir / "appointments.json",
        ),
        profile=profile,
        today=today,
    )


def build_gateway(
    settings: Settings,
    profile: HospitalProfile,
    *,
    state_path: Path | None = None,
    today=date.today,
) -> SchedulingGateway:
    """Use the .NET appointments service when configured, else the local JSON files."""
    if settings.appointments_api_url:
        return HttpSchedulingGateway(settings.appointments_api_url, settings.appointments_api_key)
    return build_local_gateway(settings, profile, state_path=state_path, today=today)


def build_guards(profile: HospitalProfile) -> tuple[InputGuard, OutputGuard]:
    messages = SafetyMessages.from_profile(profile)
    return InputGuard(messages), OutputGuard(profile.allowed_phone_digits(), messages.output_fallback)


@asynccontextmanager
async def create_app(
    settings: Settings,
    *,
    policy_agent_name: str | None = None,
    guardrails: bool = True,
    state_path: Path | None = None,
    audit: AuditLog | None = None,
    today=date.today,
) -> AsyncIterator[CareCompanionApp]:
    """Build the full assistant. An async context manager because MCP connections need it."""
    # Imported here so offline commands and tests never need the Azure packages.
    from agent_framework import MCPStreamableHTTPTool

    from carecompanion.agents.care_team import build_coordinator
    from carecompanion.agents.factory import AzureClients
    from carecompanion.agents.policy_agent import PolicyKnowledgeBase, build_policy_tool
    from carecompanion.agents.prompts import PromptLibrary
    from carecompanion.tools import build_callback_tool, build_scheduling_tools

    profile = load_hospital(settings)
    audit = audit or build_audit(settings)
    clients = AzureClients(settings)
    prompts = PromptLibrary(settings.prompts_dir, profile.prompt_variables())
    gateway = build_gateway(settings, profile, state_path=state_path, today=today)
    scheduling = build_scheduling_tools(gateway, audit)
    kb = PolicyKnowledgeBase(clients, prompts, policy_agent_name or settings.policy_agent_name)
    input_guard, output_guard = build_guards(profile)

    async with AsyncExitStack() as stack:
        override = None
        if settings.scheduling_mcp_url:  # experimental: tools served by our own MCP server
            headers = {"X-Api-Key": settings.appointments_api_key} if settings.appointments_api_key else None
            mcp_tool = MCPStreamableHTTPTool(
                name="scheduling-mcp", url=settings.scheduling_mcp_url, static_headers=headers
            )
            await stack.enter_async_context(mcp_tool)
            override = [mcp_tool]
        coordinator = build_coordinator(
            clients,
            prompts,
            scheduling,
            build_policy_tool(kb, audit),
            build_callback_tool(CallbackQueue(settings.state_dir / "callbacks.jsonl"), audit),
            scheduler_tools_override=override,
        )
        yield CareCompanionApp(coordinator, input_guard, output_guard, audit, guardrails_enabled=guardrails)
