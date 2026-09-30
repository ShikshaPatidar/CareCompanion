"""Hospital profile: facts, contacts and scheduling rules loaded from config/hospital.toml."""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from datetime import time
from pathlib import Path
import difflib

from carecompanion.domain.errors import ConfigError


@dataclass(frozen=True, slots=True)
class Department:
    name: str
    location: str
    provider: str
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SchedulingPolicy:
    working_days: frozenset[int]
    open_time: time
    close_time: time
    slot_minutes: int
    max_days_ahead: int
    duplicate_window_days: int


@dataclass(frozen=True, slots=True)
class HospitalProfile:
    name: str
    contacts: dict[str, str]
    scheduling: SchedulingPolicy
    departments: tuple[Department, ...]

    def find_department(self, text: str) -> Department | None:
        """Match a department by name or alias, forgiving small differences in wording."""
        wanted = " ".join(text.lower().split())
        names = {n.lower(): d for d in self.departments for n in (d.name, *d.aliases)}
        if wanted in names:
            return names[wanted]
        # e.g. "Blood test (phlebotomy)" contains the alias "blood test"
        for name, dept in names.items():
            if len(name) >= 4 and len(wanted) >= 4 and (name in wanted or wanted in name):
                return dept
        close = difflib.get_close_matches(wanted, list(names), n=1, cutoff=0.8)
        return names[close[0]] if close else None

    def allowed_phone_digits(self) -> set[str]:
        """Digit-only forms of every phone number the assistant may quote."""
        allowed: set[str] = set()
        for value in self.contacts.values():
            digits = re.sub(r"\D", "", value)
            if digits:
                allowed.add(digits)
        return allowed

    def to_api_config(self) -> dict:
        """The subset of the profile the .NET appointments service needs (hospital.json)."""
        sched = self.scheduling
        return {
            "Hospital": {
                "Scheduling": {
                    "WorkingDays": sorted(sched.working_days),
                    "OpenTime": sched.open_time.strftime("%H:%M"),
                    "CloseTime": sched.close_time.strftime("%H:%M"),
                    "SlotMinutes": sched.slot_minutes,
                    "MaxDaysAhead": sched.max_days_ahead,
                    "DuplicateWindowDays": sched.duplicate_window_days,
                },
                "Departments": [
                    {
                        "Name": d.name,
                        "Location": d.location,
                        "Provider": d.provider,
                        "Aliases": list(d.aliases),
                    }
                    for d in self.departments
                ],
            }
        }

    def prompt_variables(self) -> dict[str, str]:
        """Values substituted into prompt templates as $hospital_name, $emergency, ..."""
        variables = {"hospital_name": self.name}
        variables.update(self.contacts)
        return variables


def _parse_time(value: str) -> time:
    try:
        hours, minutes = value.split(":")
        return time(int(hours), int(minutes))
    except ValueError as exc:
        raise ConfigError(f"Invalid time {value!r}; expected HH:MM") from exc


def load_profile(path: Path) -> HospitalProfile:
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"Cannot read hospital profile {path}: {exc}") from exc
    try:
        sched = raw["scheduling"]
        policy = SchedulingPolicy(
            working_days=frozenset(int(d) for d in sched["working_days"]),
            open_time=_parse_time(sched["open_time"]),
            close_time=_parse_time(sched["close_time"]),
            slot_minutes=int(sched["slot_minutes"]),
            max_days_ahead=int(sched["max_days_ahead"]),
            duplicate_window_days=int(sched["duplicate_window_days"]),
        )
        departments = tuple(
            Department(
                name=d["name"],
                location=d["location"],
                provider=d["provider"],
                aliases=tuple(d.get("aliases", [])),
            )
            for d in raw["departments"]
        )
        return HospitalProfile(
            name=raw["hospital"]["name"],
            contacts=dict(raw["contacts"]),
            scheduling=policy,
            departments=departments,
        )
    except KeyError as exc:
        raise ConfigError(f"Hospital profile {path} is missing key {exc}") from exc
