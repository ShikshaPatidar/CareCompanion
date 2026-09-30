"""Scheduling rules. The single place where 'can this be booked?' is decided."""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import date, datetime, timedelta

from carecompanion.domain import (
    Appointment,
    AppointmentStatus,
    BookingOutcome,
    BookingRequest,
    PatientSummary,
    ReasonCode,
)
from carecompanion.profile import Department, HospitalProfile
from carecompanion.scheduling.ports import AppointmentRepository, PatientRepository

_ISO_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class SchedulingService:
    """Local implementation of the SchedulingGateway port."""

    def __init__(
        self,
        patients: PatientRepository,
        appointments: AppointmentRepository,
        profile: HospitalProfile,
        today: Callable[[], date] = date.today,
    ) -> None:
        self._patients = patients
        self._appointments = appointments
        self._profile = profile
        self._today = today  # injected so tests never depend on the real date

    # -- queries -----------------------------------------------------------------------------
    def find_patients(self, name: str) -> list[PatientSummary]:
        return [p.summary() for p in self._patients.search_by_name(name)]

    def list_appointments(self, patient_id: str) -> list[Appointment] | None:
        if self._patients.get(patient_id) is None:
            return None
        return self._appointments.for_patient(patient_id)

    # -- booking -----------------------------------------------------------------------------
    def book(self, request: BookingRequest) -> BookingOutcome:
        patient = self._patients.get(request.patient_id)
        if patient is None:
            return BookingOutcome.rejected(ReasonCode.PATIENT_NOT_FOUND, "No patient with that ID exists.")

        department = self._profile.find_department(request.department)
        if department is None:
            known = ", ".join(d.name for d in self._profile.departments)
            return BookingOutcome.rejected(
                ReasonCode.UNKNOWN_DEPARTMENT, f"Unknown department. Available: {known}."
            )

        day_or_rejection = self._validate_day(request.preferred_day)
        if isinstance(day_or_rejection, BookingOutcome):
            return day_or_rejection
        day = day_or_rejection

        duplicate = self._find_duplicate(request.patient_id, department, day)
        if duplicate is not None:
            window = self._profile.scheduling.duplicate_window_days
            return BookingOutcome.duplicate(
                duplicate,
                f"The patient already has a {department.name} appointment within "
                f"{window} days of the requested date.",
            )

        start = self._first_free_slot(request.patient_id, department, day)
        if start is None:
            return BookingOutcome.rejected(
                ReasonCode.NO_SLOT_AVAILABLE, f"No free slots in {department.name} on that day."
            )

        appointment = Appointment(
            appointment_id=self._appointments.next_id(),
            patient_id=request.patient_id,
            department=department.name,
            provider=department.provider,
            starts_at=start,
            location=department.location,
            status=AppointmentStatus.CONFIRMED,
        )
        self._appointments.add(appointment)
        return BookingOutcome.booked(appointment)

    # -- helpers -----------------------------------------------------------------------------
    def _validate_day(self, raw: str) -> date | BookingOutcome:
        text = raw.strip()
        if not _ISO_DAY.match(text):
            return BookingOutcome.rejected(
                ReasonCode.BAD_DATE_FORMAT, "Dates must be in the format YYYY-MM-DD."
            )
        try:
            day = date.fromisoformat(text)
        except ValueError:
            return BookingOutcome.rejected(ReasonCode.BAD_DATE_FORMAT, "That is not a real date.")

        policy = self._profile.scheduling
        today = self._today()
        if day <= today:
            return BookingOutcome.rejected(
                ReasonCode.DATE_NOT_IN_FUTURE, "Appointments must be booked for a future date."
            )
        if day.isoweekday() not in policy.working_days:
            return BookingOutcome.rejected(ReasonCode.NOT_A_WORKING_DAY, "Clinics run on weekdays only.")
        if day > today + timedelta(days=policy.max_days_ahead):
            return BookingOutcome.rejected(
                ReasonCode.TOO_FAR_AHEAD,
                f"Appointments can be booked up to {policy.max_days_ahead} days ahead.",
            )
        return day

    def _find_duplicate(self, patient_id: str, department: Department, day: date) -> Appointment | None:
        window = timedelta(days=self._profile.scheduling.duplicate_window_days)
        nearby = [
            a
            for a in self._appointments.for_patient(patient_id)
            if a.is_active and a.department == department.name and abs(a.starts_at.date() - day) <= window
        ]
        if not nearby:
            return None
        return min(nearby, key=lambda a: abs(a.starts_at.date() - day))

    def _first_free_slot(self, patient_id: str, department: Department, day: date) -> datetime | None:
        policy = self._profile.scheduling
        taken_by_department = {
            a.starts_at for a in self._appointments.for_department_on(department.name, day) if a.is_active
        }
        taken_by_patient = {a.starts_at for a in self._appointments.for_patient(patient_id) if a.is_active}
        slot = datetime.combine(day, policy.open_time)
        close = datetime.combine(day, policy.close_time)
        step = timedelta(minutes=policy.slot_minutes)
        while slot + step <= close:
            if slot not in taken_by_department and slot not in taken_by_patient:
                return slot
            slot += step
        return None
