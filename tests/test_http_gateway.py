"""Contract tests: the Python client against a fake of the .NET service (docs/api-contract.md)."""

import httpx
import pytest

from carecompanion.domain import BookingRequest, BookingStatus, ReasonCode
from carecompanion.domain.errors import GatewayError
from carecompanion.scheduling.http_gateway import HttpSchedulingGateway

APPT = {
    "resourceType": "Appointment",
    "appointmentId": "APT-2008",
    "patientId": "PAT-1001",
    "department": "Phlebotomy (Blood Tests)",
    "provider": "Outpatient Phlebotomy",
    "datetime": "2026-10-06T09:00",
    "location": "Outpatients Block A, Level 1",
    "status": "confirmed",
}


def gateway_for(handler) -> HttpSchedulingGateway:
    client = httpx.Client(base_url="http://api", transport=httpx.MockTransport(handler))
    return HttpSchedulingGateway("http://api", client=client)


def test_find_patients_maps_results():
    def handler(request):
        assert request.url.path == "/api/patients" and request.url.params["name"] == "Priya"
        return httpx.Response(200, json=[{"id": "PAT-1004", "name": "Priya Nair"}])

    assert gateway_for(handler).find_patients("Priya")[0].name == "Priya Nair"


def test_unknown_patient_is_none():
    gw = gateway_for(lambda r: httpx.Response(404, json={"code": "PATIENT_NOT_FOUND"}))
    assert gw.list_appointments("PAT-0") is None


def test_booking_created():
    def handler(request):
        assert request.method == "POST"
        assert request.read() == (
            b'{"patientId":"PAT-1001","department":"blood test","preferredDay":"2026-10-06"}'
        )
        return httpx.Response(201, json={"appointment": APPT})

    out = gateway_for(handler).book(BookingRequest("PAT-1001", "blood test", "2026-10-06"))
    assert out.status is BookingStatus.BOOKED and out.appointment.appointment_id == "APT-2008"


def test_conflict_returns_duplicate_with_existing():
    body = {"code": "DUPLICATE_APPOINTMENT", "detail": "already booked", "existingAppointment": APPT}
    out = gateway_for(lambda r: httpx.Response(409, json=body)).book(
        BookingRequest("PAT-1001", "Cardiology", "2026-10-15")
    )
    assert out.status is BookingStatus.DUPLICATE and out.existing.appointment_id == "APT-2008"


@pytest.mark.parametrize("status", [404, 422])
def test_validation_failures_are_rejections(status):
    body = {"code": "NOT_A_WORKING_DAY", "detail": "Clinics run on weekdays only."}
    out = gateway_for(lambda r: httpx.Response(status, json=body)).book(
        BookingRequest("PAT-1001", "Cardiology", "2026-10-10")
    )
    assert out.reason_code is ReasonCode.NOT_A_WORKING_DAY


def test_server_error_raises_gateway_error():
    with pytest.raises(GatewayError):
        gateway_for(lambda r: httpx.Response(500, json={})).book(
            BookingRequest("PAT-1001", "Cardiology", "2026-10-15")
        )


def test_network_failure_raises_gateway_error():
    def handler(request):
        raise httpx.ConnectError("refused")

    with pytest.raises(GatewayError):
        gateway_for(handler).find_patients("Whitfield")
