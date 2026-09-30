"""One place that knows how to reach Foundry."""

from __future__ import annotations

from functools import cached_property

from azure.ai.projects import AIProjectClient
from azure.identity import AzureCliCredential, DefaultAzureCredential

from carecompanion.config import Settings


class AzureClients:
    def __init__(self, settings: Settings, *, need_resource_endpoint: bool = False) -> None:
        settings.require_foundry(need_resource_endpoint=need_resource_endpoint)
        self._settings = settings

    @property
    def model(self) -> str:
        return self._settings.model_deployment

    @cached_property
    def project(self) -> AIProjectClient:
        """Foundry project client (agents, vector stores, OpenAI-compatible calls)."""
        return AIProjectClient(
            endpoint=self._settings.project_endpoint,
            credential=DefaultAzureCredential(),
        )

    def chat_client(self):
        """A new Agent Framework chat client. Each agent gets its own."""
        from agent_framework.foundry import FoundryChatClient

        return FoundryChatClient(
            project_endpoint=self._settings.project_endpoint,
            model=self._settings.model_deployment,
            credential=AzureCliCredential(),
        )

    def openai(self):
        """OpenAI-compatible client routed through the project (stateless responses)."""
        return self.project.get_openai_client()
