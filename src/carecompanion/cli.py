"""Command-line interface. Each command is a thin wrapper over the library."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

from carecompanion.config import Settings
from carecompanion.domain.errors import CareCompanionError

log = logging.getLogger("carecompanion")
DEFAULT_EVAL_DATE = "2026-09-28"


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="carecompanion", description="CareCompanion healthcare assistant")
    p.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("check", help="verify configuration, sign-in and model access")

    idx = sub.add_parser("index", help="build the policy knowledge base (vector store + agent)")
    idx.add_argument("--agent-name", help="override POLICY_AGENT_NAME")
    idx.add_argument(
        "--include-safety-fixture",
        action="store_true",
        help="also index the poisoned test document (use with a separate --agent-name)",
    )

    chat = sub.add_parser("chat", help="talk to the assistant")
    chat.add_argument("--policy-agent-name")
    chat.add_argument("--no-guardrails", action="store_true", help="disable deterministic guards")

    dis = sub.add_parser("discharge", help="discharge note: extract, structure, summarise, verify")
    dis.add_argument("--pdf", type=Path, help="defaults to data/discharge/discharge_note.pdf")

    mcp = sub.add_parser("mcp-serve", help="serve the scheduling tools over MCP")
    mcp.add_argument("--host", default="127.0.0.1")
    mcp.add_argument("--port", type=int, default=8765)

    ev = sub.add_parser("eval", help="run the evaluation suites")
    ev.add_argument("--suite", choices=["deterministic", "core", "injection", "all"], default="deterministic")
    ev.add_argument("--label", default="run")
    ev.add_argument("--today", default=DEFAULT_EVAL_DATE, help="frozen clock for booking rules")
    ev.add_argument("--policy-agent-name")
    ev.add_argument("--no-guardrails", action="store_true", help="baseline run without the guards")
    ev.add_argument("--out", type=Path, help="report path (default reports/<label>.json)")

    cmp_ = sub.add_parser("eval-compare", help="compare two evaluation reports")
    cmp_.add_argument("before", type=Path)
    cmp_.add_argument("after", type=Path)

    sub.add_parser("reset-data", help="restore appointments to the seed data")
    sub.add_parser("export-api-config", help="write hospital.json for the .NET appointments service")
    clean = sub.add_parser("cleanup", help="delete cloud objects this project created")
    clean.add_argument("--agent-name", action="append", help="repeatable; default is POLICY_AGENT_NAME")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    load_dotenv()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING, format="%(levelname)s %(name)s: %(message)s"
    )
    settings = Settings.from_env()
    try:
        return _dispatch(args, settings)
    except CareCompanionError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


def _dispatch(args: argparse.Namespace, settings: Settings) -> int:
    from carecompanion.telemetry import setup_telemetry

    setup_telemetry(settings)
    match args.command:
        case "check":
            return _check(settings)
        case "index":
            return _index(settings, args)
        case "chat":
            return asyncio.run(_chat(settings, args))
        case "discharge":
            return asyncio.run(_discharge(settings, args))
        case "mcp-serve":
            return _mcp_serve(settings, args)
        case "eval":
            return asyncio.run(_eval(settings, args))
        case "eval-compare":
            return _eval_compare(args)
        case "reset-data":
            return _reset(settings)
        case "export-api-config":
            return _export_api_config(settings)
        case "cleanup":
            return _cleanup(settings, args)
    return 1


# ---- commands ----------------------------------------------------------------------------------
def _check(settings: Settings) -> int:
    from carecompanion.agents.factory import AzureClients
    from carecompanion.container import load_hospital

    profile = load_hospital(settings)
    print(f"Hospital profile OK: {profile.name}, {len(profile.departments)} departments")
    clients = AzureClients(settings)
    response = clients.openai().responses.create(
        model=clients.model,
        input="In one sentence, what does a hospital care coordinator do?",
    )
    print("Model reply:", response.output_text)
    return 0


def _index(settings: Settings, args: argparse.Namespace) -> int:
    from carecompanion.agents.factory import AzureClients
    from carecompanion.agents.policy_agent import PolicyKnowledgeBase
    from carecompanion.agents.prompts import PromptLibrary
    from carecompanion.container import load_hospital

    profile = load_hospital(settings)
    prompts = PromptLibrary(settings.prompts_dir, profile.prompt_variables())
    name = args.agent_name or settings.policy_agent_name
    dirs = [settings.policies_dir]
    if args.include_safety_fixture:
        if name == settings.policy_agent_name:
            print(
                "Refusing to put the poisoned fixture into the normal agent. "
                "Pass --agent-name, e.g. elmfield-policy-agent-injtest.",
                file=sys.stderr,
            )
            return 2
        dirs.append(settings.safety_fixtures_dir)
    kb = PolicyKnowledgeBase(AzureClients(settings), prompts, name)
    report = kb.rebuild_index(dirs)
    print(f"Indexed {len(report.files)} files: {', '.join(report.files)}")
    print(f"Agent {report.agent_name} is now version {report.agent_version}")
    return 0


async def _chat(settings: Settings, args: argparse.Namespace) -> int:
    from carecompanion.container import create_app

    async with create_app(
        settings, policy_agent_name=args.policy_agent_name, guardrails=not args.no_guardrails
    ) as app:
        session = app.new_session()
        print("CareCompanion is ready. Type 'quit' to leave.")
        while True:
            try:
                text = input("\nYou: ").strip()
            except EOFError:
                break
            if text.lower() in {"quit", "exit"}:
                break
            reply = await app.ask(session, text)
            print(f"\nCareCompanion: {reply.text}")
    return 0


async def _discharge(settings: Settings, args: argparse.Namespace) -> int:
    from carecompanion.agents.discharge_pipeline import summarise_discharge_note
    from carecompanion.agents.factory import AzureClients
    from carecompanion.agents.prompts import PromptLibrary
    from carecompanion.container import build_guards, load_hospital
    from carecompanion.documents.extraction import extract_markdown
    from carecompanion.documents.structured import extract_structured
    from carecompanion.documents.verify import verify_summary

    profile = load_hospital(settings)
    clients = AzureClients(settings, need_resource_endpoint=True)
    prompts = PromptLibrary(settings.prompts_dir, profile.prompt_variables())
    pdf = args.pdf or settings.discharge_dir / "discharge_note.pdf"

    print(f"1/4 Extracting {pdf.name} with Content Understanding ...")
    markdown = extract_markdown(settings.resource_endpoint, pdf)
    print(f"2/4 Structuring with {clients.model} ...")
    record = extract_structured(
        clients.openai(), clients.model, prompts.raw("discharge_structured"), markdown
    )
    print(_json_dump(record.to_dict()))
    print("3/4 Writing the patient-friendly summary ...")
    summary = await summarise_discharge_note(clients, prompts, markdown)
    print("\n" + summary + "\n")
    print("4/4 Verifying the summary ...")
    _, output_guard = build_guards(profile)
    report = verify_summary(
        summary, record, required_contact=profile.contacts["ward_advice_line"], output_guard=output_guard
    )
    print("Verification:", "PASSED" if report.passed else "FAILED")
    for problem in report.problems:
        print(" -", problem)
    return 0 if report.passed else 1


async def _docs(settings: Settings, args: argparse.Namespace) -> int:
    from carecompanion.agents.docs_agent import ask_docs_helper
    from carecompanion.agents.factory import AzureClients
    from carecompanion.agents.prompts import PromptLibrary
    from carecompanion.container import load_hospital

    profile = load_hospital(settings)
    prompts = PromptLibrary(settings.prompts_dir, profile.prompt_variables())
    print(await ask_docs_helper(AzureClients(settings), prompts, args.question))
    return 0


def _mcp_serve(settings: Settings, args: argparse.Namespace) -> int:
    from carecompanion.container import build_audit, build_gateway, load_hospital
    from carecompanion.mcp_server.server import build_mcp_server

    profile = load_hospital(settings)
    server = build_mcp_server(
        build_gateway(settings, profile),
        build_audit(settings, "mcp-audit.jsonl"),
        host=args.host,
        port=args.port,
    )
    print(f"Serving scheduling tools at http://{args.host}:{args.port}/mcp  (Ctrl+C to stop)")
    server.run(transport="streamable-http")
    return 0


async def _eval(settings: Settings, args: argparse.Namespace) -> int:
    import tempfile

    from carecompanion.audit import AuditLog
    from carecompanion.container import build_guards, create_app, load_hospital
    from carecompanion.evaluation import EvalRunner, GuardOnlyAssistant, load_cases

    suites = {"deterministic", "core", "injection"} if args.suite == "all" else {args.suite}
    cases = load_cases(settings.project_root / "evaluation" / "cases.jsonl", suites)
    if not cases:
        print("No cases selected.", file=sys.stderr)
        return 2
    frozen = date.fromisoformat(args.today)
    metadata = {
        "suite": args.suite,
        "guardrails": not args.no_guardrails,
        "model": settings.model_deployment,
        "clock": args.today,
    }

    def show(result) -> None:
        mark = "PASS" if result.passed else "FAIL"
        print(f"  {mark}  {result.case_id:<22} {result.seconds:>6.1f}s")
        for failure in result.failures:
            print(f"        - {failure}")

    print(f"Running {len(cases)} cases ({args.suite}) ...")
    reports = []
    with tempfile.TemporaryDirectory() as tmp:
        for suite in sorted({c.suite for c in cases}):
            subset = [c for c in cases if c.suite == suite]
            audit = AuditLog(None)
            if suite == "deterministic":
                profile = load_hospital(settings)
                input_guard, _ = build_guards(profile)
                report = await EvalRunner(GuardOnlyAssistant(input_guard), audit).run(
                    subset, label=args.label, metadata=metadata, on_result=show
                )
            else:
                agent_name = args.policy_agent_name or (
                    f"{settings.policy_agent_name}-injtest" if suite == "injection" else None
                )
                async with create_app(
                    settings,
                    policy_agent_name=agent_name,
                    guardrails=not args.no_guardrails,
                    state_path=Path(tmp) / f"{suite}-appointments.json",
                    audit=audit,
                    today=lambda: frozen,
                ) as app:
                    report = await EvalRunner(app, audit).run(
                        subset, label=args.label, metadata=metadata, on_result=show
                    )
            reports.append(report)

    merged = reports[0]
    for extra in reports[1:]:
        merged.results.extend(extra.results)
    print(f"\nPassed {merged.passed}/{merged.total}")
    for category, (ok, total) in merged.by_category().items():
        print(f"  {category:<22}{ok}/{total}")
    out = args.out or settings.project_root / "reports" / f"{args.label}.json"
    merged.save(out)
    print(f"Report saved to {out}")
    return 0 if merged.passed == merged.total else 1


def _eval_compare(args: argparse.Namespace) -> int:
    from carecompanion.evaluation import EvalReport, compare_reports

    print(compare_reports(EvalReport.load(args.before), EvalReport.load(args.after)))
    return 0


def _reset(settings: Settings) -> int:
    for name in ("appointments.json", "callbacks.jsonl", "audit.jsonl"):
        (settings.state_dir / name).unlink(missing_ok=True)
    print("State cleared. Appointments will be re-seeded from data/appointments.json.")
    return 0


API_CONFIG_PATH = Path("services/appointments-api/src/Elmfield.Appointments.Api/hospital.json")


def _export_api_config(settings: Settings) -> int:
    from carecompanion.container import load_hospital

    target = settings.project_root / API_CONFIG_PATH
    target.write_text(_json_dump(load_hospital(settings).to_api_config()) + "\n", encoding="utf-8")
    print(f"Wrote {target}")
    return 0


def _cleanup(settings: Settings, args: argparse.Namespace) -> int:
    from carecompanion.agents.factory import AzureClients
    from carecompanion.agents.policy_agent import PolicyKnowledgeBase
    from carecompanion.agents.prompts import PromptLibrary
    from carecompanion.container import load_hospital

    profile = load_hospital(settings)
    prompts = PromptLibrary(settings.prompts_dir, profile.prompt_variables())
    clients = AzureClients(settings)
    names = args.agent_name or [settings.policy_agent_name, f"{settings.policy_agent_name}-injtest"]
    for name in names:
        stores, agent = PolicyKnowledgeBase(clients, prompts, name).delete_all()
        print(f"{name}: deleted {stores} vector store(s); agent deleted: {agent}")
    print("Now delete the resource group in the Azure portal to stop all charges.")
    return 0


def _json_dump(data: dict) -> str:
    import json

    return json.dumps(data, indent=2, ensure_ascii=False)
