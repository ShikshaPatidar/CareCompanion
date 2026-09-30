from datetime import date, datetime

import pytest

from carecompanion.domain import BookingRequest, BookingStatus, ReasonCode

WHITFIELD, ADEYEMI, RAHMAN = "PAT-1001", "PAT-1002", "PAT-1003"
FROZEN = date(2026, 9, 28)


def book(gateway, patient, department, day):
    return gateway.book(BookingRequest(patient, department, day))


def test_finds_patients_returning_only_id_and_name(gateway):
    found = gateway.find_patients("whitfield")
    assert [p.to_dict() for p in found] == [{"id": WHITFIELD, "name": "Susan Whitfield"}]


def test_ambiguous_name_returns_all_matches(gateway):
    assert {p.name for p in gateway.find_patients("Priya")} == {"Priya Nair", "Priya Nayar"}


def test_blank_name_returns_nothing(gateway):
    assert gateway.find_patients("   ") == []


def test_unknown_patient_has_no_appointment_list(gateway):
    assert gateway.list_appointments("PAT-9999") is None


def test_lists_appointments_in_date_order(gateway):
    days = [a.starts_at for a in gateway.list_appointments(ADEYEMI)]
    assert days == sorted(days) and len(days) == 2


def test_books_first_free_slot_and_persists(gateway):
    outcome = book(gateway, WHITFIELD, "blood test", "2026-10-06")
    assert outcome.status is BookingStatus.BOOKED
    assert outcome.appointment.department == "Phlebotomy (Blood Tests)"
    assert outcome.appointment.starts_at == datetime(2026, 10, 6, 9, 0)
    assert outcome.appointment.appointment_id == "APT-2008"
    assert any(a.appointment_id == "APT-2008" for a in gateway.list_appointments(WHITFIELD))


def test_second_booking_on_same_day_takes_next_slot(gateway):
    book(gateway, WHITFIELD, "blood test", "2026-10-06")
    second = book(gateway, "PAT-1004", "blood test", "2026-10-06")
    assert second.appointment.starts_at == datetime(2026, 10, 6, 9, 30)


def test_slot_skips_a_time_the_patient_is_already_busy(gateway):
    first = book(gateway, WHITFIELD, "blood test", "2026-10-06")
    second = book(gateway, WHITFIELD, "General Medicine", "2026-10-06")
    assert first.appointment.starts_at.hour == 9 and first.appointment.starts_at.minute == 0
    assert second.appointment.starts_at == datetime(2026, 10, 6, 9, 30)


def test_duplicate_within_window_is_refused_with_existing_appointment(gateway):
    outcome = book(gateway, WHITFIELD, "Cardiology", "2026-10-15")
    assert outcome.status is BookingStatus.DUPLICATE
    assert outcome.reason_code is ReasonCode.DUPLICATE_APPOINTMENT
    assert outcome.existing.appointment_id == "APT-2002"
    assert len(gateway.list_appointments(WHITFIELD)) == 1  # nothing was added


def test_same_department_outside_window_is_allowed(gateway):
    assert book(gateway, WHITFIELD, "Cardiology", "2026-11-30").status is BookingStatus.BOOKED


@pytest.mark.parametrize(
    ("patient", "department", "day", "code"),
    [
        ("PAT-9999", "Cardiology", "2026-10-20", ReasonCode.PATIENT_NOT_FOUND),
        (WHITFIELD, "Dentistry", "2026-10-20", ReasonCode.UNKNOWN_DEPARTMENT),
        (WHITFIELD, "Phlebotomy", "20/10/2026", ReasonCode.BAD_DATE_FORMAT),
        (WHITFIELD, "Phlebotomy", "2026-02-30", ReasonCode.BAD_DATE_FORMAT),
        (WHITFIELD, "Phlebotomy", "2026-09-28", ReasonCode.DATE_NOT_IN_FUTURE),
        (WHITFIELD, "Phlebotomy", "2020-01-01", ReasonCode.DATE_NOT_IN_FUTURE),
        (WHITFIELD, "Phlebotomy", "2026-10-10", ReasonCode.NOT_A_WORKING_DAY),  # Saturday
        (WHITFIELD, "Phlebotomy", "2027-06-01", ReasonCode.TOO_FAR_AHEAD),
    ],
)
def test_rejections_carry_a_reason_code(gateway, patient, department, day, code):
    outcome = book(gateway, patient, department, day)
    assert outcome.status is BookingStatus.REJECTED
    assert outcome.reason_code is code


def test_no_slot_when_the_day_is_full(settings, profile, tmp_path):
    from dataclasses import replace

    from carecompanion.container import build_local_gateway

    one_slot = replace(profile, scheduling=replace(profile.scheduling, slot_minutes=450))
    gw = build_local_gateway(settings, one_slot, state_path=tmp_path / "a.json", today=lambda: FROZEN)
    assert book(gw, WHITFIELD, "Physiotherapy", "2026-12-01").status is BookingStatus.BOOKED
    full = book(gw, ADEYEMI, "Physiotherapy", "2026-12-01")
    assert full.reason_code is ReasonCode.NO_SLOT_AVAILABLE


def test_input_is_not_trusted_for_date_format_injection(gateway):
    out = book(gateway, WHITFIELD, "Cardiology", "2026-10-20; DROP TABLE")
    assert out.reason_code is ReasonCode.BAD_DATE_FORMAT
