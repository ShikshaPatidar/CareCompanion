"""Run cases through an Assistant, grade them, and produce comparable JSON reports."""

from __future__ import annotations

import json
import time
import uuid
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from carecompanion.app import Assistant, ChatSession, Reply
from carecompanion.audit import AuditLog, current_session
from carecompanion.evaluation.cases import EvalCase
from carecompanion.evaluation.graders import grade
from carecompanion.safety import InputGuard


@dataclass(frozen=True, slots=True)
class CaseResult:
    case_id: str
    category: str
    passed: bool
    failures: tuple[str, ...]
    reply: str
    tools_called: tuple[str, ...]
    seconds: float


@dataclass(slots=True)
class EvalReport:
    label: str
    created: str
    metadata: dict
    results: list[CaseResult] = field(default_factory=list)

    @property
    def passed(self) -> int:
        return sum(r.passed for r in self.results)

    @property
    def total(self) -> int:
        return len(self.results)

    def by_category(self) -> dict[str, tuple[int, int]]:
        table: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        for r in self.results:
            table[r.category][1] += 1
            table[r.category][0] += int(r.passed)
        return {k: (v[0], v[1]) for k, v in sorted(table.items())}

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "label": self.label,
            "created": self.created,
            "metadata": self.metadata,
            "summary": {"passed": self.passed, "total": self.total},
            "results": [asdict(r) for r in self.results],
        }
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> EvalReport:
        raw = json.loads(path.read_text(encoding="utf-8"))
        results = [
            CaseResult(
                case_id=r["case_id"],
                category=r["category"],
                passed=r["passed"],
                failures=tuple(r["failures"]),
                reply=r["reply"],
                tools_called=tuple(r["tools_called"]),
                seconds=r["seconds"],
            )
            for r in raw["results"]
        ]
        return cls(raw["label"], raw["created"], raw["metadata"], results)


class GuardOnlyAssistant:
    """Runs just the deterministic input guard, so the safety layer is testable offline."""

    def __init__(self, guard: InputGuard) -> None:
        self._guard = guard

    def new_session(self) -> ChatSession:
        return ChatSession(id=uuid.uuid4().hex[:8])

    async def ask(self, session: ChatSession, text: str) -> Reply:
        decision = self._guard.check(text)
        if not decision.allowed:
            return Reply(decision.message, blocked=True, category=decision.category.value)
        return Reply("[passed to the model]")


class EvalRunner:
    def __init__(self, assistant: Assistant, audit: AuditLog) -> None:
        self._assistant = assistant
        self._audit = audit

    async def run(
        self, cases: list[EvalCase], *, label: str, metadata: dict | None = None, on_result=None
    ) -> EvalReport:
        report = EvalReport(label, datetime.now(UTC).isoformat(timespec="seconds"), metadata or {})
        for case in cases:
            result = await self._run_case(case)
            report.results.append(result)
            if on_result:
                on_result(result)
        return report

    async def _run_case(self, case: EvalCase) -> CaseResult:
        started = time.perf_counter()
        marker = self._audit.mark()
        session = self._assistant.new_session()
        current_session.set(session.id)
        replies: list[Reply] = []
        for turn in case.turns:
            replies.append(await self._assistant.ask(session, turn))
        events = self._audit.since(marker)
        failures = grade(case.expect, replies, events)
        tools = tuple(sorted({e["tool"] for e in events if e.get("event") == "tool_call" and "tool" in e}))
        return CaseResult(
            case_id=case.id,
            category=case.category,
            passed=not failures,
            failures=tuple(failures),
            reply=replies[-1].text if replies else "",
            tools_called=tools,
            seconds=round(time.perf_counter() - started, 2),
        )


def compare_reports(before: EvalReport, after: EvalReport) -> str:
    """A readable before/after summary, including regressions and fixes."""
    lines = [
        f"BEFORE: {before.label}  {before.passed}/{before.total} passed",
        f"AFTER:  {after.label}  {after.passed}/{after.total} passed",
        "",
        f"{'category':<22}{'before':>10}{'after':>10}",
    ]
    b, a = before.by_category(), after.by_category()
    for cat in sorted(set(b) | set(a)):
        bp, bt = b.get(cat, (0, 0))
        ap, at = a.get(cat, (0, 0))
        lines.append(f"{cat:<22}{f'{bp}/{bt}':>10}{f'{ap}/{at}':>10}")
    before_by_id = {r.case_id: r for r in before.results}
    fixed, regressed = [], []
    for r in after.results:
        prev = before_by_id.get(r.case_id)
        if prev is None:
            continue
        if r.passed and not prev.passed:
            fixed.append(r.case_id)
        if prev.passed and not r.passed:
            regressed.append(r.case_id)
    lines += ["", f"Fixed:     {', '.join(fixed) or 'none'}", f"Regressed: {', '.join(regressed) or 'none'}"]
    return "\n".join(lines)
