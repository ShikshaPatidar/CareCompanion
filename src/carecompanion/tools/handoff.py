"""Human hand-off: when the assistant should not or cannot help, a person follows up."""

from __future__ import annotations

import json
import threading
from datetime import UTC, datetime
from pathlib import Path


class CallbackQueue:
    """A minimal queue backed by a JSONL file. Swap for a real ticketing system later."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()
        path.parent.mkdir(parents=True, exist_ok=True)

    def add(self, reason: str, patient_id: str = "") -> str:
        with self._lock:
            number = self._count() + 1
            ticket = f"CB-{datetime.now(UTC):%Y%m%d}-{number:04d}"
            entry = {
                "ticket": ticket,
                "created": datetime.now(UTC).isoformat(timespec="seconds"),
                "patientId": patient_id,
                "reason": reason,
                "status": "open",
            }
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return ticket

    def _count(self) -> int:
        if not self._path.exists():
            return 0
        with self._path.open(encoding="utf-8") as fh:
            return sum(1 for line in fh if line.strip())
