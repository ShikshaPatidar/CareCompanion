"""Turn discharge-note Markdown into validated structured data.

The model's JSON is untrusted input: it is parsed and validated, and one retry is allowed.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import date

from carecompanion.domain.errors import ExtractionError


@dataclass(frozen=True, slots=True)
class Medication:
    name: str
    dose: str
    schedule: str


@dataclass(frozen=True, slots=True)
class FollowUp:
    department: str
    timeframe: str


@dataclass(frozen=True, slots=True)
class DischargeRecord:
    patient_name: str
    discharge_date: date
    diagnosis: str
    medications: tuple[Medication, ...]
    follow_up: tuple[FollowUp, ...]
    warning_signs: tuple[str, ...]
    activity_limits: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return {
            "patient_name": self.patient_name,
            "discharge_date": self.discharge_date.isoformat(),
            "diagnosis": self.diagnosis,
            "medications": [asdict(m) for m in self.medications],
            "follow_up": [asdict(f) for f in self.follow_up],
            "activity_limits": list(self.activity_limits),
            "warning_signs": list(self.warning_signs),
        }


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


def _text(value, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ExtractionError(f"Field '{label}' must be a non-empty string")
    return value.strip()


def _text_list(value, label: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ExtractionError(f"Field '{label}' must be a list of strings")
    return tuple(v.strip() for v in value if v.strip())


def parse_discharge_json(raw: str) -> DischargeRecord:
    text = _FENCE.sub("", raw.strip())
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ExtractionError(f"Model did not return valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ExtractionError("Expected a JSON object")
    try:
        discharge_date = date.fromisoformat(_text(data.get("discharge_date"), "discharge_date"))
    except ValueError as exc:
        raise ExtractionError("discharge_date must be YYYY-MM-DD") from exc

    meds_raw = data.get("medications")
    if not isinstance(meds_raw, list) or not meds_raw:
        raise ExtractionError("Field 'medications' must be a non-empty list")
    medications = tuple(
        Medication(
            name=_text(m.get("name") if isinstance(m, dict) else None, "medications.name"),
            dose=_text(m.get("dose"), "medications.dose"),
            schedule=_text(m.get("schedule"), "medications.schedule"),
        )
        for m in meds_raw
    )
    follow_raw = data.get("follow_up") or []
    if isinstance(follow_raw, dict):  # tolerate a single object
        follow_raw = [follow_raw]
    follow_up = tuple(
        FollowUp(
            department=_text(f.get("department") if isinstance(f, dict) else None, "follow_up.department"),
            timeframe=_text(f.get("timeframe"), "follow_up.timeframe"),
        )
        for f in follow_raw
    )
    return DischargeRecord(
        patient_name=_text(data.get("patient_name"), "patient_name"),
        discharge_date=discharge_date,
        diagnosis=_text(data.get("diagnosis"), "diagnosis"),
        medications=medications,
        follow_up=follow_up,
        warning_signs=_text_list(data.get("warning_signs"), "warning_signs"),
        activity_limits=_text_list(data.get("activity_limits"), "activity_limits"),
    )


def extract_structured(
    openai_client, model: str, prompt: str, markdown: str, retries: int = 1
) -> DischargeRecord:
    """Ask the model for JSON and validate it, retrying once on a malformed reply."""
    last_error: ExtractionError | None = None
    for _ in range(retries + 1):
        response = openai_client.responses.create(model=model, input=prompt + markdown)
        try:
            return parse_discharge_json(response.output_text)
        except ExtractionError as exc:
            last_error = exc
    raise ExtractionError(f"Structured extraction failed after retry: {last_error}")
