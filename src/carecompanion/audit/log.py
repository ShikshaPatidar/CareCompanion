"""Append-only audit trail. One JSON object per line, easy to ship to a log store."""

from __future__ import annotations

import json
import threading
from contextvars import ContextVar
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Set by the app for each conversation turn so every event can be tied to a session.
current_session: ContextVar[str] = ContextVar("current_session", default="-")


class AuditLog:
    def __init__(self, path: Path | None = None, *, log_content: bool = False) -> None:
        self._path = path
        self._log_content = log_content
        self._lock = threading.Lock()
        self._events: list[dict[str, Any]] = []
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)

    def redact(self, text: str) -> str:
        """Message text is personal data: only its length is logged unless opted in."""
        return text if self._log_content else f"<{len(text)} chars>"

    def record(self, event: str, **fields: Any) -> None:
        entry = {
            "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
            "session": current_session.get(),
            "event": event,
            **fields,
        }
        with self._lock:
            self._events.append(entry)
            if self._path is not None:
                with self._path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def mark(self) -> int:
        """Position marker, so callers (the evaluator) can read only newer events."""
        with self._lock:
            return len(self._events)

    def since(self, marker: int) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._events[marker:])
