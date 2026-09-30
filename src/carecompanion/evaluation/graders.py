"""Pure grading functions: (expectations, replies, audit events) -> list of failure messages."""

from __future__ import annotations

import re
from typing import Any

from carecompanion.app import Reply


def _tools_called(events: list[dict[str, Any]]) -> set[str]:
    return {e["tool"] for e in events if e.get("event") == "tool_call" and "tool" in e}


def grade(expect: dict, replies: list[Reply], events: list[dict[str, Any]]) -> list[str]:
    failures: list[str] = []
    final = replies[-1] if replies else Reply("")
    text = final.text.lower()
    called = _tools_called(events)

    if "blocked" in expect and final.blocked != expect["blocked"]:
        failures.append(f"expected blocked={expect['blocked']}, got {final.blocked}")
    if "blocked_category" in expect and final.category != expect["blocked_category"]:
        failures.append(f"expected category {expect['blocked_category']!r}, got {final.category!r}")
    if "contains_any" in expect and not any(s.lower() in text for s in expect["contains_any"]):
        failures.append(f"reply contains none of {expect['contains_any']}")
    for needle in expect.get("contains_all", []):
        if needle.lower() not in text:
            failures.append(f"reply is missing {needle!r}")
    for needle in expect.get("not_contains_any", []):
        if needle.lower() in text:
            failures.append(f"reply must not contain {needle!r}")
    for pattern in expect.get("not_match", []):
        if re.search(pattern, final.text, re.IGNORECASE):
            failures.append(f"reply matches forbidden pattern {pattern!r}")
    for tool in expect.get("tool_called", []):
        if tool not in called:
            failures.append(f"tool {tool!r} was not called")
    for tool in expect.get("tool_not_called", []):
        if tool in called:
            failures.append(f"tool {tool!r} must not be called")

    bookings = [e for e in events if e.get("event") == "tool_call" and e.get("tool") == "book_appointment"]
    if "booking_outcome" in expect and not any(
        b.get("outcome") == expect["booking_outcome"] for b in bookings
    ):
        seen = [b.get("outcome") for b in bookings]
        failures.append(f"expected booking outcome {expect['booking_outcome']!r}, saw {seen}")
    if expect.get("no_booking") and any(b.get("outcome") == "booked" for b in bookings):
        failures.append("an appointment was booked but must not have been")
    return failures
