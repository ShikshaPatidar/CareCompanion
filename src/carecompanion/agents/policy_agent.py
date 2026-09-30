"""The policy knowledge base: a versioned Foundry agent with file search (RAG)."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

from azure.ai.projects.models import FileSearchTool, PromptAgentDefinition

from carecompanion.agents.factory import AzureClients
from carecompanion.agents.prompts import PromptLibrary
from carecompanion.audit import AuditLog
from carecompanion.domain.errors import CareCompanionError
from carecompanion.telemetry import tracer

logger = logging.getLogger(__name__)
MAX_QUESTION_CHARS = 500


@dataclass(frozen=True, slots=True)
class IndexReport:
    vector_store_id: str
    files: tuple[str, ...]
    agent_name: str
    agent_version: str


class PolicyKnowledgeBase:
    def __init__(self, clients: AzureClients, prompts: PromptLibrary, agent_name: str) -> None:
        self._clients = clients
        self._prompts = prompts
        self._agent_name = agent_name
        self._store_name = f"{agent_name}-store"

    @property
    def agent_name(self) -> str:
        return self._agent_name

    def rebuild_index(self, directories: Sequence[Path]) -> IndexReport:
        """Replace the vector store and publish a new agent version that uses it."""
        files = sorted(p for d in directories for p in d.glob("*.md"))
        if not files:
            raise CareCompanionError(f"No .md policy files found in {[str(d) for d in directories]}")
        openai = self._clients.openai()

        self._delete_stores(openai)
        store = openai.vector_stores.create(name=self._store_name)
        for path in files:
            with path.open("rb") as fh:
                openai.vector_stores.files.upload_and_poll(vector_store_id=store.id, file=fh)
            logger.info("Indexed %s", path.name)

        agent = self._clients.project.agents.create_version(
            agent_name=self._agent_name,
            definition=PromptAgentDefinition(
                model=self._clients.model,
                instructions=self._prompts.render("policy_agent"),
                tools=[FileSearchTool(vector_store_ids=[store.id])],
            ),
        )
        return IndexReport(store.id, tuple(p.name for p in files), agent.name, str(agent.version))

    def ask(self, question: str) -> str:
        """One stateless policy question. A fresh conversation keeps answers independent."""
        client = self._clients.project.get_openai_client(agent_name=self._agent_name)
        conversation = client.conversations.create()
        response = client.responses.create(conversation=conversation.id, input=question[:MAX_QUESTION_CHARS])
        return response.output_text

    def delete_all(self) -> tuple[int, bool]:
        """Delete our vector stores and the agent. Returns (stores deleted, agent deleted)."""
        openai = self._clients.openai()
        stores = self._delete_stores(openai)
        try:
            self._clients.project.agents.delete(agent_name=self._agent_name)
            return stores, True
        except Exception as exc:  # the agent may never have been created
            logger.warning("Agent %s not deleted: %s", self._agent_name, exc)
            return stores, False

    def _delete_stores(self, openai) -> int:
        count = 0
        for store in list(openai.vector_stores.list()):
            if store.name == self._store_name:
                openai.vector_stores.delete(vector_store_id=store.id)
                count += 1
        return count


def build_policy_tool(kb: PolicyKnowledgeBase, audit: AuditLog) -> Callable[..., str]:
    def policy_lookup(
        question: Annotated[str, "The policy question in plain words, e.g. 'ICU visiting hours'"],
    ) -> str:
        """Search the hospital policy documents (visiting, charges, discharge, appointments).

        Returns what the documents say, with the policy number. Answer only from this.
        """
        with tracer.start_as_current_span("tool.policy_lookup"):
            try:
                answer = kb.ask(question)
            except Exception:
                logger.exception("Policy lookup failed")
                audit.record("tool_error", tool="policy_lookup", error="SERVICE_UNAVAILABLE")
                return json.dumps(
                    {
                        "error": "SERVICE_UNAVAILABLE",
                        "detail": "Policy search failed. Apologise and offer a callback.",
                    }
                )
            audit.record("tool_call", tool="policy_lookup", outcome="ok", question=audit.redact(question))
            return json.dumps({"source": "hospital_policy_documents", "answer": answer}, ensure_ascii=False)

    return policy_lookup
