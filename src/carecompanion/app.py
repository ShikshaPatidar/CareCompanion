"""Application service: guardrails -> coordinator agent -> guardrails, with audit and errors."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any, Protocol

from carecompanion.audit import AuditLog, current_session
from carecompanion.safety import InputGuard, OutputGuard
from carecompanion.telemetry import tracer

logger = logging.getLogger(__name__)
MAX_INPUT_CHARS = 2000


@dataclass(frozen=True, slots=True)
class Reply:
    text: str
    blocked: bool = False
    category: str | None = None
    issues: tuple[str, ...] = ()


@dataclass(slots=True)
class ChatSession:
    id: str
    agent_session: Any = None


class Assistant(Protocol):
    """What the CLI and the evaluator use. Anything with this shape can be evaluated."""

    def new_session(self) -> ChatSession: ...
    async def ask(self, session: ChatSession, text: str) -> Reply: ...


class CareCompanionApp:
    def __init__(
        self,
        coordinator: Any,
        input_guard: InputGuard,
        output_guard: OutputGuard,
        audit: AuditLog,
        *,
        guardrails_enabled: bool = True,
        error_message: str = "Sorry, something went wrong on my side. Please try again.",
    ) -> None:
        self._coordinator = coordinator
        self._input_guard = input_guard
        self._output_guard = output_guard
        self._audit = audit
        self._guardrails = guardrails_enabled
        self._error_message = error_message

    def new_session(self) -> ChatSession:
        return ChatSession(id=uuid.uuid4().hex[:8], agent_session=self._coordinator.create_session())

    async def ask(self, session: ChatSession, text: str) -> Reply:
        current_session.set(session.id)
        text = text.strip()
        if not text:
            return Reply("Sorry, I didn't catch that. How can I help?")
        if len(text) > MAX_INPUT_CHARS:
            self._audit.record("input_rejected", reason="too_long", chars=len(text))
            return Reply("That message is too long for me. Could you shorten it?")

        with tracer.start_as_current_span("carecompanion.ask") as span:
            if self._guardrails:
                decision = self._input_guard.check(text)
                if not decision.allowed:
                    span.set_attribute("guard.blocked", decision.category.value)
                    self._audit.record("guard_input", allowed=False, category=decision.category.value)
                    return Reply(decision.message, blocked=True, category=decision.category.value)
            self._audit.record("user_message", text=self._audit.redact(text))

            try:
                result = await self._coordinator.run(text, session=session.agent_session)
            except Exception:
                logger.exception("Coordinator run failed")
                self._audit.record("model_error")
                return Reply(self._error_message)
            reply_text = str(result)

            if self._guardrails:
                checked = self._output_guard.check(reply_text)
                if not checked.ok:
                    self._audit.record("guard_output", ok=False, issues=list(checked.issues))
                    return Reply(checked.text, blocked=True, category="output", issues=checked.issues)
            self._audit.record("assistant_reply", text=self._audit.redact(reply_text))
            return Reply(reply_text)
