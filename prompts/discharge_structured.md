Extract these fields from the discharge note below and reply with JSON only (no code fences, no
commentary). Use only what the note says; use null for anything it does not state.
- patient_name (string)
- discharge_date (YYYY-MM-DD)
- diagnosis (string)
- medications (array of {name, dose, schedule})
- follow_up (array of {department, timeframe})
- activity_limits (array of strings)
- warning_signs (array of strings)

--- DISCHARGE NOTE ---
