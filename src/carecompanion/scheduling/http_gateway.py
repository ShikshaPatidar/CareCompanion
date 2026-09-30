"""SchedulingGateway over HTTP, for the .NET appointments service.

The wire contract is documented in docs/api-contract.md and implemented by
services/appointments-api. Expected outcomes (conflicts, validation failures)
are values, not exceptions; only unexpected failures raise GatewayError.
"""

from __future__ import annotations

import httpx

from carecompanion.domain import (
    Appointment,
    BookingOutcome,
    BookingRequest,
    PatientSummary,
    ReasonCode,
)
from carecompanion.domain.errors import GatewayError


class HttpSchedulingGateway:
    def __init__(
        self,
        base_url: str,
        api_key: str = "",
        client: httpx.Client | None = None,
        timeout: float = 10.0,
    ) -> None:
        headers = {"X-Api-Key": api_key} if api_key else {}
        self._client = client or httpx.Client(
            base_url=base_url,
            headers=headers,
            timeout=timeout,
            transport=httpx.HTTPTransport(retries=2),
        )

    def find_patients(self, name: str) -> list[PatientSummary]:
        response = self._send("GET", "/api/patients", params={"name": name})
        self._expect(response, {200})
        return [PatientSummary(id=p["id"], name=p["name"]) for p in response.json()]

    def list_appointments(self, patient_id: str) -> list[Appointment] | None:
        response = self._send("GET", f"/api/patients/{patient_id}/appointments")
        if response.status_code == 404:
            return None
        self._expect(response, {200})
        return [Appointment.from_dict(a) for a in response.json()]

    def book(self, request: BookingRequest) -> BookingOutcome:
        response = self._send(
            "POST",
            "/api/appointments",
            json={
                "patientId": request.patient_id,
                "department": request.department,
                "preferredDay": request.preferred_day,
            },
        )
        if response.status_code == 201:
            return BookingOutcome.booked(Appointment.from_dict(response.json()["appointment"]))
        body = self._problem(response)
        code = self._reason(body)
        if response.status_code == 409:
            existing = body.get("existingAppointment")
            if existing is None:
                raise GatewayError("Conflict response without existingAppointment")
            return BookingOutcome.duplicate(Appointment.from_dict(existing), body.get("detail", ""))
        if response.status_code in {404, 422}:
            return BookingOutcome.rejected(code, body.get("detail", ""))
        raise GatewayError(f"Unexpected status {response.status_code} from appointments service")

    # -- internals ---------------------------------------------------------------------------
    def _send(self, method: str, url: str, **kwargs) -> httpx.Response:
        try:
            return self._client.request(method, url, **kwargs)
        except httpx.HTTPError as exc:
            raise GatewayError(f"Appointments service unreachable: {exc}") from exc

    @staticmethod
    def _expect(response: httpx.Response, ok: set[int]) -> None:
        if response.status_code not in ok:
            raise GatewayError(f"Unexpected status {response.status_code} from appointments service")

    @staticmethod
    def _problem(response: httpx.Response) -> dict:
        try:
            body = response.json()
        except ValueError as exc:
            raise GatewayError("Appointments service returned a non-JSON error") from exc
        return body if isinstance(body, dict) else {}

    @staticmethod
    def _reason(body: dict) -> ReasonCode:
        try:
            return ReasonCode(body.get("code", ""))
        except ValueError as exc:
            raise GatewayError(f"Unknown reason code {body.get('code')!r}") from exc
