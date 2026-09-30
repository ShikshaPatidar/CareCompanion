"""Function tools the model can call. Thin adapters over the SchedulingGateway.

Design rules applied here:
  * Tools return JSON strings with stable keys, and never raise into the model.
  * Inputs are validated and length-limited; the model's arguments are untrusted.
  * Only the minimum data is returned (no phone numbers, dates of birth or notes).
  * Business rules live in the gateway, not here and not in prompts.
  * Every call is audited and traced.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated

from carecompanion.audit import AuditLog
from carecompanion.domain import BookingRequest
from carecompanion.domain.errors import GatewayError
from carecompanion.scheduling.ports import SchedulingGateway
from carecompanion.telemetry import tracer
from carecompanion.tools.handoff import CallbackQueue

MAX_MATCHES = 5
MIN_NAME_LENGTH = 3
_ID = re.compile(r"^[A-Za-z0-9-]{3,20}$")


def _clean(text: str, limit: int) -> str:
    return " ".join(str(text).split())[:limit]


def _json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False)


@dataclass(frozen=True, slots=True)
class SchedulingTools:
    find_patient: Callable[..., str]
    get_appointments: Callable[..., str]
    book_appointment: Callable[..., str]

    def as_list(self) -> list[Callable[..., str]]:
        return [self.find_patient, self.get_appointments, self.book_appointment]


def build_scheduling_tools(gateway: SchedulingGateway, audit: AuditLog) -> SchedulingTools:
    def find_patient(
        name: Annotated[str, "Patient's full or partial name, e.g. 'Whitfield' (min 3 letters)"],
    ) -> str:
        """Look up patients by name. Returns matching patient IDs and names only."""
        with tracer.start_as_current_span("tool.find_patient"):
            cleaned = _clean(name, 80)
            if len(cleaned) < MIN_NAME_LENGTH:
                audit.record("tool_call", tool="find_patient", outcome="name_too_short")
                return _json({"error": "NAME_TOO_SHORT", "detail": "Ask for the patient's full name."})
            try:
                matches = gateway.find_patients(cleaned)
            except GatewayError:
                return _unavailable(audit, "find_patient")
            audit.record("tool_call", tool="find_patient", outcome="ok", matches=len(matches))
            return _json(
                {
                    "count": len(matches),
                    "matches": [m.to_dict() for m in matches[:MAX_MATCHES]],
                    "note": "If there is more than one match, ask which patient is meant.",
                }
            )

    def get_appointments(
        patient_id: Annotated[str, "Patient ID from find_patient, e.g. 'PAT-1001'"],
    ) -> str:
        """Return all appointments on record for a patient ID."""
        with tracer.start_as_current_span("tool.get_appointments"):
            pid = _clean(patient_id, 20)
            if not _ID.match(pid):
                audit.record("tool_call", tool="get_appointments", outcome="bad_id")
                return _json({"error": "BAD_PATIENT_ID"})
            try:
                found = gateway.list_appointments(pid)
            except GatewayError:
                return _unavailable(audit, "get_appointments")
            if found is None:
                audit.record(
                    "tool_call", tool="get_appointments", patient_id=pid, outcome="patient_not_found"
                )
                return _json({"error": "PATIENT_NOT_FOUND"})
            audit.record("tool_call", tool="get_appointments", patient_id=pid, outcome="ok", count=len(found))
            return _json({"patientId": pid, "appointments": [a.to_dict() for a in found]})

    def book_appointment(
        patient_id: Annotated[str, "Patient ID from find_patient, e.g. 'PAT-1001'"],
        department: Annotated[str, "Department name, e.g. 'Cardiology' or 'blood test'"],
        preferred_day: Annotated[str, "Requested date in YYYY-MM-DD format"],
    ) -> str:
        """Book a new appointment. The system decides the time and enforces the booking rules.

        Always report the returned status honestly. Never claim a booking succeeded unless
        the status is 'booked'.
        """
        with tracer.start_as_current_span("tool.book_appointment") as span:
            request = BookingRequest(
                patient_id=_clean(patient_id, 20),
                department=_clean(department, 60),
                preferred_day=_clean(preferred_day, 20),
            )
            try:
                outcome = gateway.book(request)
            except GatewayError:
                return _unavailable(audit, "book_appointment")
            span.set_attribute("booking.status", outcome.status.value)
            audit.record(
                "tool_call",
                tool="book_appointment",
                patient_id=request.patient_id,
                outcome=outcome.status.value,
                reason_code=outcome.reason_code.value if outcome.reason_code else None,
                appointment_id=outcome.appointment.appointment_id if outcome.appointment else None,
            )
            return _json(outcome.to_dict())

    return SchedulingTools(find_patient, get_appointments, book_appointment)


def _unavailable(audit: AuditLog, tool: str) -> str:
    audit.record("tool_error", tool=tool, error="SERVICE_UNAVAILABLE")
    return _json(
        {
            "error": "SERVICE_UNAVAILABLE",
            "detail": "The scheduling system is not responding. Apologise and offer a callback.",
        }
    )


def build_callback_tool(queue: CallbackQueue, audit: AuditLog) -> Callable[..., str]:
    def request_callback(
        reason: Annotated[str, "Short, non-clinical reason a staff member should call back"],
        patient_id: Annotated[str, "Patient ID if known, otherwise an empty string"] = "",
    ) -> str:
        """Ask for a member of staff to call the person back (clinical questions, complaints,
        anything you cannot or should not handle yourself)."""
        with tracer.start_as_current_span("tool.request_callback"):
            ticket = queue.add(_clean(reason, 200), _clean(patient_id, 20))
            audit.record("tool_call", tool="request_callback", outcome="queued", ticket=ticket)
            return _json(
                {
                    "status": "queued",
                    "ticket": ticket,
                    "message": "A member of staff will contact the caller.",
                }
            )

    return request_callback
