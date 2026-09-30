"""Check that a patient-friendly summary kept the facts and added nothing risky."""

from __future__ import annotations

import re
from dataclasses import dataclass

from carecompanion.documents.structured import DischargeRecord
from carecompanion.safety.guardrails import OutputGuard


@dataclass(frozen=True, slots=True)
class VerificationReport:
    passed: bool
    problems: tuple[str, ...]


def _dose_near_name(text: str, name: str, dose: str) -> bool:
    """True if the dose appears shortly after the medicine name (not just anywhere)."""
    flexible_dose = r"\s*".join(re.escape(part) for part in dose.split())
    pattern = re.escape(name) + r".{0,40}?(?<![\d.])" + flexible_dose
    return re.search(pattern, text, re.DOTALL) is not None


def verify_summary(
    summary: str, record: DischargeRecord, *, required_contact: str, output_guard: OutputGuard
) -> VerificationReport:
    problems: list[str] = []
    lowered = summary.lower()
    for med in record.medications:
        if med.name.lower() not in lowered:
            problems.append(f"missing medicine: {med.name}")
        if not _dose_near_name(lowered, med.name.lower(), med.dose.lower()):
            problems.append(f"missing or changed dose for {med.name}: {med.dose}")
    if required_contact not in summary:
        problems.append(f"missing contact line with {required_contact}")
    if "999" not in summary:
        problems.append("missing emergency number 999")
    decision = output_guard.check(summary)
    if not decision.ok:
        problems.append("output guard flagged: " + ", ".join(decision.issues))
    return VerificationReport(not problems, tuple(problems))
