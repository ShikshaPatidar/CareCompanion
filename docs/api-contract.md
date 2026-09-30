# Appointments API contract

The Python client (`scheduling/http_gateway.py`) and the .NET service
(`services/appointments-api`) agree on this contract. Both sides have tests for it:
`tests/test_http_gateway.py` (Python, against a fake) and `SchedulingServiceTests.cs` (.NET, rules).

**Authentication:** header `X-Api-Key: <secret>` on every `/api/*` call. `/health` is open.
If `Api__Key` is empty the service logs a warning and runs unauthenticated (local dev only).

| Method and path | Success | Failures |
|---|---|---|
| `GET /health` | `200 {"status":"ok"}` | |
| `GET /api/patients?name=` | `200 [{"id","name"}]` (id and name only) | `400 NAME_REQUIRED` |
| `GET /api/patients/{id}/appointments` | `200 [appointment]` | `404 PATIENT_NOT_FOUND` |
| `POST /api/appointments` | `201 {"appointment": {...}}` | `409`, `404`, `422`, `400` (below) |

`POST /api/appointments` body: `{"patientId","department","preferredDay"}` (`preferredDay` is `YYYY-MM-DD`).
The service chooses the time slot; the caller never does.

| Status | Body | When |
|---|---|---|
| 409 | `{"code":"DUPLICATE_APPOINTMENT","detail","existingAppointment":{...}}` | same patient and department within the duplicate window |
| 404 | `{"code":"PATIENT_NOT_FOUND","detail"}` | unknown patient |
| 422 | `{"code","detail"}` | `UNKNOWN_DEPARTMENT`, `BAD_DATE_FORMAT`, `DATE_NOT_IN_FUTURE`, `NOT_A_WORKING_DAY`, `TOO_FAR_AHEAD`, `NO_SLOT_AVAILABLE` |
| 400 | `{"code":"INVALID_REQUEST","detail"}` | missing fields |
| 401 | `{"code":"UNAUTHORIZED","detail"}` | bad or missing API key |

Appointment shape (same as `data/appointments.json`):
`{"resourceType":"Appointment","appointmentId":"APT-2008","patientId":"PAT-1001","department":"Cardiology",
"provider":"Dr. R. Bhatt","datetime":"2026-10-06T09:00","location":"Outpatients Block A, Clinic 3","status":"confirmed"}`

## Rules (identical on both sides)
Order of checks: patient exists, department known (name or alias), date format, date in the future,
weekday, within `MaxDaysAhead`, no duplicate within `DuplicateWindowDays`, first free slot.
Rule values come from `config/hospital.toml`, exported to `hospital.json` for the .NET side
(`carecompanion export-api-config`; a test fails if they drift apart).
