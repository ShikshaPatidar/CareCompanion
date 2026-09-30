"""Deterministic guardrails that run before and after the model.

Why code and not just prompt rules: a prompt is a request, code is a guarantee. The
emergency check never depends on the model behaving. It deliberately errs on the side
of caution (see docs/decisions/0002-deterministic-safety-layer.md).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from carecompanion.safety.messages import SafetyMessages


class GuardCategory(StrEnum):
    EMERGENCY = "emergency"
    CRISIS = "crisis"
    INJECTION = "injection"


def _compile(patterns: list[str]) -> list[re.Pattern[str]]:
    return [re.compile(p, re.IGNORECASE) for p in patterns]


_CRISIS = _compile(
    [
        r"\bsuicid(e|al)\b",
        r"\b(kill|end)\s+(myself|my\s+life)\b",
        r"\bwant(ed)?\s+to\s+die\b",
        r"\bself[- ]?harm",
        r"\bhurt(ing)?\s+myself\b",
        r"\bno\s+reason\s+to\s+(live|go\s+on)\b",
    ]
)

_EMERGENCY = _compile(
    [
        r"\bchest\s+(pain|pressure|tightness)\b",
        r"\b(can'?t|cannot|unable\s+to|struggling\s+to|trouble|difficulty)\s+(breathe|breathing)\b",
        r"\bshort(ness)?\s+of\s+breath\b",
        r"\bsevere(ly)?\s+bleeding\b|\bbleeding\s+(heavily|badly|a\s+lot|won'?t\s+stop)\b",
        r"\b(having|had|suspected|signs?\s+of|symptoms?\s+of)\s+(a\s+)?stroke\b|\bstroke\s+symptoms?\b",
        r"\bface\s+(is\s+)?droop|\bslurred\s+speech\b",
        r"\b(unconscious|unresponsive|not\s+breathing|collapsed|passed\s+out|fainted|fainting)\b",
        r"\bchoking\b|\boverdos|\bseizure|\banaphyla|\bheart\s+attack\b",
        r"\bswelling\s+(of|in)\s+(\w+\s+)?(face|throat|tongue)\b",
    ]
)

_INJECTION = _compile(
    [
        r"\bignore\b.{0,30}\b(previous|prior|above|earlier|all|your|these|any)\b.{0,20}"
        r"\b(instructions|rules|prompt|guidelines)\b",
        r"\b(reveal|show|print|repeat|display)\b.{0,40}"
        r"\b(system\s+prompt|hidden\s+prompt|your\s+(instructions|rules|prompt))\b",
        r"\byou\s+are\s+now\b.{0,60}\b(unrestricted|no\s+rules|dan|jailbroken)\b",
        r"\bdeveloper\s+mode\b|\bjailbreak\b",
        r"\bpretend\b.{0,30}\bno\s+(rules|restrictions)\b",
    ]
)


@dataclass(frozen=True, slots=True)
class InputDecision:
    allowed: bool
    category: GuardCategory | None = None
    message: str = ""
    matched: str = ""


class InputGuard:
    """Screens a user message before it reaches the model."""

    def __init__(self, messages: SafetyMessages) -> None:
        self._messages = messages

    def check(self, text: str) -> InputDecision:
        # Order matters: crisis wording gets the most careful reply, then emergencies.
        for category, patterns, message in (
            (GuardCategory.CRISIS, _CRISIS, self._messages.crisis),
            (GuardCategory.EMERGENCY, _EMERGENCY, self._messages.emergency),
            (GuardCategory.INJECTION, _INJECTION, self._messages.injection),
        ):
            for pattern in patterns:
                found = pattern.search(text)
                if found:
                    return InputDecision(False, category, message, found.group(0))
        return InputDecision(True)


# ---- output ----------------------------------------------------------------------------------
_PHONE = re.compile(r"(?<![\d/-])(?:\+44|0)[\d\s\-()]{8,14}\d")
_FOREIGN = {
    "us_emergency_number": re.compile(r"\b911\b"),
    "us_style_phone": re.compile(r"\b555[-\s]?\d{4}\b"),
}


@dataclass(frozen=True, slots=True)
class OutputDecision:
    ok: bool
    issues: tuple[str, ...]
    text: str


class OutputGuard:
    """Screens the model's reply for things it must never say."""

    def __init__(self, allowed_phone_digits: set[str], fallback_message: str) -> None:
        self._allowed = allowed_phone_digits
        self._fallback = fallback_message

    def check(self, text: str) -> OutputDecision:
        issues: list[str] = []
        for match in _PHONE.finditer(text):
            digits = re.sub(r"\D", "", match.group(0))
            if digits.startswith("44"):
                digits = "0" + digits[2:]
            if len(digits) >= 10 and digits not in self._allowed:
                issues.append("unknown_phone_number")
        for name, pattern in _FOREIGN.items():
            if pattern.search(text):
                issues.append(name)
        if issues:
            return OutputDecision(False, tuple(dict.fromkeys(issues)), self._fallback)
        return OutputDecision(True, (), text)
