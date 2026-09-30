# Architecture

## Layers and dependency direction

```
cli.py / app.py            entry points
container.py               composition root (chooses concrete classes)
agents/  documents/        Azure + Agent Framework code (only place that imports them)
tools/  safety/  audit/    application logic the agents call
scheduling/                rules service + ports + adapters
domain/  profile.py        pure models and configuration
```
Dependencies point downwards only. `domain/` imports nothing else from the project. Nothing below
`agents/` imports Azure, which is why 114 tests run offline in under two seconds.

## Request flow (one user message)

1. `CareCompanionApp.ask` sets the session id and validates length.
2. **Input guard** (regex, deterministic): crisis, emergency, injection. A hit returns a fixed
   message from `safety/messages.py` and the model is never called.
3. **CareCoordinator** (Agent Framework) decides which tools to use:
   - `records_specialist` -> `find_patient` (id and name only)
   - `scheduling_specialist` -> `get_appointments`, `book_appointment`
   - `policy_lookup` -> versioned Foundry agent with file search over the policy documents
   - `request_callback` -> human hand-off queue
4. Tools call the `SchedulingGateway`. Business rules run there, never in a prompt.
5. **Output guard**: replaces replies containing phone numbers not in the hospital profile, or
   a US emergency number, with a safe fallback.
6. Every step is written to the audit log and emitted as OpenTelemetry spans.

## Two deployments of the same port

| | Local | Remote |
|---|---|---|
| Selected when | `APPOINTMENTS_API_URL` empty | `APPOINTMENTS_API_URL` set |
| Rules live in | `scheduling/service.py` | `services/appointments-api` (C#) |
| Storage | `var/appointments.json` (seed in `data/` untouched) | `var/dotnet-appointments.json` |

## Discharge pipeline

PDF -> Content Understanding (Markdown) -> model -> JSON -> **validated** `DischargeRecord` (one
retry) -> sequential agents write the summary -> `verify_summary` checks every medicine and dose,
the ward contact line, 999 and the output guard.

## Known limitations
- Regex guardrails over-trigger by design and miss creative phrasing; they are a floor, not a ceiling.
- No patient identity verification (date of birth check). A real system must add one before
  disclosing appointments.
- Single-instance locking in both scheduling implementations; a database is the next step.
- Sync HTTP calls inside tools briefly block the event loop; fine for a demo.
