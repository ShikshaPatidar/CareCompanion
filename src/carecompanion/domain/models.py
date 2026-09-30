"""Domain model. Pure data and no I/O, so it is trivial to test and reuse."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import Any


class AppointmentStatus(StrEnum):
    CONFIRMED = "confirmed"
    PENDING = "pending"
    CANCELLED = "cancelled"


class BookingStatus(StrEnum):
    BOOKED = "booked"
    DUPLICATE = "duplicate"
    REJECTED = "rejected"


class ReasonCode(StrEnum):
    """Machine-readable reasons, so callers (and the model) never parse prose."""

    PATIENT_NOT_FOUND = "PATIENT_NOT_FOUND"
    UNKNOWN_DEPARTMENT = "UNKNOWN_DEPARTMENT"
    BAD_DATE_FORMAT = "BAD_DATE_FORMAT"
    DATE_NOT_IN_FUTURE = "DATE_NOT_IN_FUTURE"
    NOT_A_WORKING_DAY = "NOT_A_WORKING_DAY"
    TOO_FAR_AHEAD = "TOO_FAR_AHEAD"
    DUPLICATE_APPOINTMENT = "DUPLICATE_APPOINTMENT"
    NO_SLOT_AVAILABLE = "NO_SLOT_AVAILABLE"


@dataclass(frozen=True, slots=True)
class Patient:
    """Full registry record. Never handed to the model; see PatientSummary."""

    id: str
    name: str
    birth_date: date
    phone: str
    primary_care_provider: str
    notes: str

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Patient:
        return cls(
            id=raw["id"],
            name=raw["name"],
            birth_date=date.fromisoformat(raw["birthDate"]),
            phone=raw.get("phone", ""),
            primary_care_provider=raw.get("primaryCareProvider", ""),
            notes=raw.get("notes", ""),
        )

    def summary(self) -> PatientSummary:
        return PatientSummary(id=self.id, name=self.name)


@dataclass(frozen=True, slots=True)
class PatientSummary:
    """The minimum the assistant needs to identify a patient (data minimisation)."""

    id: str
    name: str

    def to_dict(self) -> dict[str, str]:
        return {"id": self.id, "name": self.name}


@dataclass(frozen=True, slots=True)
class Appointment:
    appointment_id: str
    patient_id: str
    department: str
    provider: str
    starts_at: datetime
    location: str
    status: AppointmentStatus

    @property
    def is_active(self) -> bool:
        return self.status is not AppointmentStatus.CANCELLED

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Appointment:
        return cls(
            appointment_id=raw["appointmentId"],
            patient_id=raw["patientId"],
            department=raw["department"],
            provider=raw["provider"],
            starts_at=datetime.fromisoformat(raw["datetime"]),
            location=raw["location"],
            status=AppointmentStatus(raw["status"]),
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "resourceType": "Appointment",
            "appointmentId": self.appointment_id,
            "patientId": self.patient_id,
            "department": self.department,
            "provider": self.provider,
            "datetime": self.starts_at.strftime("%Y-%m-%dT%H:%M"),
            "location": self.location,
            "status": self.status.value,
        }


@dataclass(frozen=True, slots=True)
class BookingRequest:
    patient_id: str
    department: str
    preferred_day: str  # raw text; validated by the service, never trusted


@dataclass(frozen=True, slots=True)
class BookingOutcome:
    status: BookingStatus
    appointment: Appointment | None = None
    existing: Appointment | None = None
    reason_code: ReasonCode | None = None
    detail: str = ""

    @classmethod
    def booked(cls, appointment: Appointment) -> BookingOutcome:
        return cls(BookingStatus.BOOKED, appointment=appointment)

    @classmethod
    def duplicate(cls, existing: Appointment, detail: str) -> BookingOutcome:
        return cls(
            BookingStatus.DUPLICATE,
            existing=existing,
            reason_code=ReasonCode.DUPLICATE_APPOINTMENT,
            detail=detail,
        )

    @classmethod
    def rejected(cls, code: ReasonCode, detail: str) -> BookingOutcome:
        return cls(BookingStatus.REJECTED, reason_code=code, detail=detail)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"status": self.status.value}
        if self.reason_code:
            out["reasonCode"] = self.reason_code.value
        if self.detail:
            out["detail"] = self.detail
        if self.appointment:
            out["appointment"] = self.appointment.to_dict()
        if self.existing:
            out["existingAppointment"] = self.existing.to_dict()
        return out
