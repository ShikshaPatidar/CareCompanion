"""Construct the real agents with fake endpoints. No network call is made.

This proves our tool signatures are compatible with the Agent Framework and that the
prompt/tool wiring builds, without needing Azure credentials.
"""

import pytest

pytestmark = pytest.mark.azure
pytest.importorskip("agent_framework")


def make_clients(settings):
    from dataclasses import replace

    from carecompanion.agents.factory import AzureClients

    fake = replace(
        settings,
        project_endpoint="https://example.services.ai.azure.com/api/projects/demo",
        resource_endpoint="https://example.cognitiveservices.azure.com/",
        model_deployment="gpt-5-mini",
    )
    return AzureClients(fake, need_resource_endpoint=True)


def test_coordinator_builds_with_specialists_and_tools(settings, profile, gateway, audit, tmp_path):
    from carecompanion.agents.care_team import build_coordinator
    from carecompanion.agents.policy_agent import PolicyKnowledgeBase, build_policy_tool
    from carecompanion.agents.prompts import PromptLibrary
    from carecompanion.tools import CallbackQueue, build_callback_tool, build_scheduling_tools

    clients = make_clients(settings)
    prompts = PromptLibrary(settings.prompts_dir, profile.prompt_variables())
    kb = PolicyKnowledgeBase(clients, prompts, "elmfield-policy-agent")
    coordinator = build_coordinator(
        clients,
        prompts,
        build_scheduling_tools(gateway, audit),
        build_policy_tool(kb, audit),
        build_callback_tool(CallbackQueue(tmp_path / "cb.jsonl"), audit),
    )
    assert coordinator.name == "CareCoordinator"
    assert coordinator.create_session() is not None


def test_policy_tool_is_safe_when_the_service_is_down(settings, profile, audit):
    import json

    from carecompanion.agents.policy_agent import PolicyKnowledgeBase, build_policy_tool
    from carecompanion.agents.prompts import PromptLibrary

    class Down(PolicyKnowledgeBase):
        def ask(self, question):
            raise RuntimeError("offline")

    kb = Down(make_clients(settings), PromptLibrary(settings.prompts_dir, {}), "x")
    result = json.loads(build_policy_tool(kb, audit)("visiting hours?"))
    assert result["error"] == "SERVICE_UNAVAILABLE"


def test_discharge_and_docs_modules_import():
    import carecompanion.agents.discharge_pipeline 
    import carecompanion.documents.extraction 
