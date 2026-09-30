import json

import pytest

from carecompanion.audit import AuditLog
from carecompanion.domain.errors import GatewayError
from carecompanion.tools import CallbackQueue, build_callback_tool, build_scheduling_tools


@pytest.fixture()
def tools(gateway, audit):
    return build_scheduling_tools(gateway, audit)


def call(fn, *args):
    return json.loads(fn(*args))


def test_find_patient_returns_minimal_data_only(tools):
    out = call(tools.find_patient, "Whitfield")
    assert out["matches"] == [{"id": "PAT-1001", "name": "Susan Whitfield"}]
    blob = json.dumps(out)
    assert "07700" not in blob and "1957" not in blob and "stent" not in blob


def test_find_patient_flags_ambiguity_and_short_names(tools):
    assert call(tools.find_patient, "Priya")["count"] == 2
    assert call(tools.find_patient, "Pr")["error"] == "NAME_TOO_SHORT"


def test_get_appointments_validates_ids(tools):
    assert call(tools.get_appointments, "PAT-1001")["appointments"][0]["department"] == "Cardiology"
    assert call(tools.get_appointments, "PAT-9999")["error"] == "PATIENT_NOT_FOUND"
    assert call(tools.get_appointments, "PAT-1001'; DROP")["error"] == "BAD_PATIENT_ID"


def test_book_reports_duplicate_and_is_audited(gateway, audit):
    tools = build_scheduling_tools(gateway, audit)
    out = call(tools.book_appointment, "PAT-1001", "Cardiology", "2026-10-15")
    assert out["status"] == "duplicate" and out["existingAppointment"]["appointmentId"] == "APT-2002"
    event = [e for e in audit.since(0) if e.get("tool") == "book_appointment"][0]
    assert event["outcome"] == "duplicate" and event["reason_code"] == "DUPLICATE_APPOINTMENT"


def test_booking_success_records_appointment_id(tools, audit):
    out = call(tools.book_appointment, "PAT-1001", "blood test", "2026-10-06")
    assert out["status"] == "booked"
    assert [e["appointment_id"] for e in audit.since(0) if e.get("outcome") == "booked"] == ["APT-2008"]


def test_gateway_failure_becomes_a_safe_error_not_an_exception(audit):
    class Broken:
        def find_patients(self, name):
            raise GatewayError("boom")

        def list_appointments(self, pid):
            raise GatewayError("boom")

        def book(self, request):
            raise GatewayError("boom")

    tools = build_scheduling_tools(Broken(), audit)
    assert call(tools.find_patient, "Whitfield")["error"] == "SERVICE_UNAVAILABLE"
    booking = call(tools.book_appointment, "PAT-1001", "Cardiology", "2026-10-20")
    assert booking["error"] == "SERVICE_UNAVAILABLE"
    assert all(e["event"] == "tool_error" for e in audit.since(0))


def test_tool_metadata_is_model_readable(tools):
    for fn in tools.as_list():
        assert fn.__doc__ and fn.__annotations__


def test_callback_queue_and_tool(tmp_path):
    audit = AuditLog(tmp_path / "audit.jsonl")
    request_callback = build_callback_tool(CallbackQueue(tmp_path / "cb.jsonl"), audit)
    first = json.loads(request_callback("complaint about parking", "PAT-1001"))
    second = json.loads(request_callback("billing question"))
    assert first["ticket"].endswith("-0001") and second["ticket"].endswith("-0002")
    assert len((tmp_path / "cb.jsonl").read_text().splitlines()) == 2


def test_audit_redacts_message_text_by_default(tmp_path):
    assert AuditLog(None).redact("my secret") == "<9 chars>"
    assert AuditLog(None, log_content=True).redact("my secret") == "my secret"
