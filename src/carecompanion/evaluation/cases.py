"""Evaluation cases live in evaluation/cases.jsonl: data, not code."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from carecompanion.domain.errors import DataError

KNOWN_CHECKS = {
    "blocked",
    "blocked_category",
    "contains_any",
    "contains_all",
    "not_contains_any",
    "not_match",
    "tool_called",
    "tool_not_called",
    "booking_outcome",
    "no_booking",
}
SUITES = {"deterministic", "core", "injection"}


@dataclass(frozen=True, slots=True)
class EvalCase:
    id: str
    suite: str
    category: str
    turns: tuple[str, ...]
    expect: dict = field(default_factory=dict)
    description: str = ""


def load_cases(path: Path, suites: set[str] | None = None) -> list[EvalCase]:
    cases: list[EvalCase] = []
    seen: set[str] = set()
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        try:
            raw = json.loads(line)
            case = EvalCase(
                id=raw["id"],
                suite=raw["suite"],
                category=raw["category"],
                turns=tuple(raw["turns"]),
                expect=raw.get("expect", {}),
                description=raw.get("description", ""),
            )
        except (json.JSONDecodeError, KeyError) as exc:
            raise DataError(f"{path}:{number}: invalid case ({exc})") from exc
        if case.suite not in SUITES:
            raise DataError(f"{path}:{number}: unknown suite {case.suite!r}")
        unknown = set(case.expect) - KNOWN_CHECKS
        if unknown:
            raise DataError(f"{path}:{number}: unknown checks {sorted(unknown)}")
        if case.id in seen:
            raise DataError(f"{path}:{number}: duplicate id {case.id!r}")
        seen.add(case.id)
        if suites is None or case.suite in suites:
            cases.append(case)
    return cases
