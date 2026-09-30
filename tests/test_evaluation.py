from dataclasses import replace

import pytest

from carecompanion.app import Reply
from carecompanion.evaluation import (
    EvalReport,
    EvalRunner,
    GuardOnlyAssistant,
    compare_reports,
    grade,
    load_cases,
)


def test_all_cases_load_and_are_valid(settings):
    cases = load_cases(settings.project_root / "evaluation" / "cases.jsonl")
    assert len(cases) >= 30
    assert {c.suite for c in cases} == {"deterministic", "core", "injection"}


async def test_deterministic_suite_passes_offline(settings, guards, audit):
    cases = load_cases(settings.project_root / "evaluation" / "cases.jsonl", {"deterministic"})
    report = await EvalRunner(GuardOnlyAssistant(guards[0]), audit).run(cases, label="offline")
    failed = [(r.case_id, r.failures) for r in report.results if not r.passed]
    assert not failed, failed
    assert report.total == len(cases)


def events(*tools_and_outcomes):
    return [{"event": "tool_call", "tool": t, **({"outcome": o} if o else {})} for t, o in tools_and_outcomes]


def test_grade_text_checks():
    reply = [Reply("Call 999. The ICU opens at 11:00 am.")]
    assert grade({"contains_all": ["999", "11:00"], "not_contains_any": ["911"]}, reply, []) == []
    assert grade({"contains_any": ["banana"]}, reply, [])
    assert grade({"not_match": [r"\b11:00\b"]}, reply, [])


def test_grade_tool_and_booking_checks():
    ev = events(("find_patient", None), ("book_appointment", "duplicate"))
    reply = [Reply("x")]
    ok = {
        "tool_called": ["find_patient"],
        "tool_not_called": ["request_callback"],
        "booking_outcome": "duplicate",
        "no_booking": True,
    }
    assert grade(ok, reply, ev) == []
    assert grade({"no_booking": True}, reply, events(("book_appointment", "booked")))
    assert grade({"tool_called": ["policy_lookup"]}, reply, ev)


def test_grade_blocked_checks():
    blocked = [Reply("call 999", blocked=True, category="emergency")]
    assert grade({"blocked": True, "blocked_category": "emergency"}, blocked, []) == []
    assert grade({"blocked": False}, blocked, [])


async def test_report_roundtrip_and_comparison(settings, guards, audit, tmp_path):
    cases = load_cases(settings.project_root / "evaluation" / "cases.jsonl", {"deterministic"})
    report = await EvalRunner(GuardOnlyAssistant(guards[0]), audit).run(cases[:4], label="a")
    path = tmp_path / "r.json"
    report.save(path)
    loaded = EvalReport.load(path)
    assert loaded.passed == report.passed and loaded.total == 4
    worse = EvalReport.load(path)
    worse.results[0] = replace(worse.results[0], passed=False, failures=("forced",))
    text = compare_reports(loaded, worse)
    assert "BEFORE" in text and worse.results[0].case_id in text.split("Regressed:")[1]


def test_bad_case_files_are_rejected(tmp_path):
    from carecompanion.domain.errors import DataError

    f = tmp_path / "c.jsonl"
    f.write_text('{"id":"a","suite":"nope","category":"x","turns":["hi"]}\n')
    with pytest.raises(DataError):
        load_cases(f)
    f.write_text('{"id":"a","suite":"core","category":"x","turns":["hi"],"expect":{"bogus":1}}\n')
    with pytest.raises(DataError):
        load_cases(f)
