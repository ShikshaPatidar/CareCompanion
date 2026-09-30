"""JSON-file repositories. Seed data in data/ is read-only; changes go to var/."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import threading
from datetime import date
from pathlib import Path

from carecompanion.domain import Appointment, Patient
from carecompanion.domain.errors import DataError


def _read_json_list(path: Path) -> list[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DataError(f"Cannot read {path}: {exc}") from exc
    if not isinstance(data, list):
        raise DataError(f"{path} must contain a JSON list")
    return data


class JsonPatientRepository:
    def __init__(self, path: Path) -> None:
        try:
            self._patients = [Patient.from_dict(p) for p in _read_json_list(path)]
        except (KeyError, ValueError) as exc:
            raise DataError(f"Malformed patient record in {path}: {exc}") from exc

    def search_by_name(self, name: str) -> list[Patient]:
        needle = " ".join(name.lower().split())
        if not needle:
            return []
        return [p for p in self._patients if needle in p.name.lower()]

    def get(self, patient_id: str) -> Patient | None:
        return next((p for p in self._patients if p.id == patient_id), None)


class JsonAppointmentRepository:
    """Loads seed data once, then persists every change to a separate state file."""

    def __init__(self, seed_path: Path, state_path: Path) -> None:
        self._state_path = state_path
        self._lock = threading.Lock()
        if not state_path.exists():
            state_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(seed_path, state_path)
        try:
            self._items = [Appointment.from_dict(a) for a in _read_json_list(state_path)]
        except (KeyError, ValueError) as exc:
            raise DataError(f"Malformed appointment record in {state_path}: {exc}") from exc

    def for_patient(self, patient_id: str) -> list[Appointment]:
        with self._lock:
            found = [a for a in self._items if a.patient_id == patient_id]
        return sorted(found, key=lambda a: a.starts_at)

    def for_department_on(self, department: str, day: date) -> list[Appointment]:
        with self._lock:
            return [a for a in self._items if a.department == department and a.starts_at.date() == day]

    def add(self, appointment: Appointment) -> None:
        with self._lock:
            self._items.append(appointment)
            self._persist()

    def next_id(self) -> str:
        with self._lock:
            numbers = [
                int(a.appointment_id.split("-")[1])
                for a in self._items
                if a.appointment_id.startswith("APT-") and a.appointment_id[4:].isdigit()
            ]
        return f"APT-{max(numbers, default=2000) + 1}"

    def _persist(self) -> None:
        """Atomic write: a crash mid-write never leaves a half-written file."""
        payload = json.dumps([a.to_dict() for a in self._items], indent=2)
        fd, tmp = tempfile.mkstemp(dir=self._state_path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(payload)
            os.replace(tmp, self._state_path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
