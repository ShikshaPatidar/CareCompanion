"""Ports (interfaces) the rest of the app depends on. Implementations are swappable."""

from __future__ import annotations

from datetime import date
from typing import Protocol

from carecompanion.domain import (
    Appointment,
    BookingOutcome,
    BookingRequest,
    Patient,
    PatientSummary,
)


class PatientRepository(Protocol):
    def search_by_name(self, name: str) -> list[Patient]: ...
    def get(self, patient_id: str) -> Patient | None: ...


class AppointmentRepository(Protocol):
    def for_patient(self, patient_id: str) -> list[Appointment]: ...
    def for_department_on(self, department: str, day: date) -> list[Appointment]: ...
    def add(self, appointment: Appointment) -> None: ...
    def next_id(self) -> str: ...


class SchedulingGateway(Protocol):
    """What the assistant's tools talk to. Implemented locally and over HTTP.

    Business rules are enforced behind this boundary, never in a prompt.
    """

    def find_patients(self, name: str) -> list[PatientSummary]: ...

    def list_appointments(self, patient_id: str) -> list[Appointment] | None:
        """Appointments for a patient, or None if the patient does not exist."""
        ...

    def book(self, request: BookingRequest) -> BookingOutcome: ...
