"""Entry point for a drafting-standards run.

Drives LAB's own harness with DraftingGuard installed as the tool
executor. Zero LAB modifications: run_agent() takes tool_executor as a
parameter, so the guard is passed in rather than patched over anything.

Usage:
    PYTHONPATH=<this repo> uv run python -m hook.runner \
        --lab-root ~/harvey-labs \
        --model anthropic/claude-sonnet-4-6 \
        --policy-id <compiled drafting policy id> \
        --run-id runD_r1

No proof sweep here at all. The conduct demo added --no-proof-sweep after
ICME reported server-side rate limiting, and the end-of-run download burst
was the likeliest trigger; nothing in this demo's claims depends on
archived binaries, so it simply never downloads them. Proof ids stay in
the ledger.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def add_lab_to_path(lab_root: str):
    p = str(Path(lab_root).resolve())
    if p not in sys.path:
        sys.path.insert(0, p)


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--lab-root", default=os.environ.get("HARVEY_LABS_ROOT"))
    p.add_argument("--model", required=True)
    p.add_argument("--task",
                   default="corporate-ma/review-data-room-red-flag-review")
    p.add_argument("--policy-id",
                   default=os.environ.get("PREFLIGHT_POLICY_ID"))
    p.add_argument("--engagement",
                   default=str(REPO_ROOT / "policy" / "engagement.json"))
    p.add_argument("--run-id", default=None)
    p.add_argument("--max-turns", type=int, default=200)
    p.add_argument("--temperature", type=float, default=0.0)
    p.add_argument("--shell-timeout", type=int, default=60)
    p.add_argument("--reasoning-effort", default=None)
    p.add_argument("--skills", nargs="*", default=None)
    p.add_argument("--runs-dir", default=str(REPO_ROOT / "runs"))
    p.add_argument("--no-briefing", action="store_true",
                   help="do not state the standard up front; the agent "
                        "learns it only from blocks (enforcement is "
                        "unchanged)")
    p.add_argument("--bare-blocks", action="store_true",
                   help="blocks do not name the missing element — the "
                        "gate alone, no repair signal (enforcement and "
                        "the ledger are unchanged)")
    return p.parse_args()


def write_verdict(results_dir, verdict: dict) -> None:
    """Record the verdict and say it out loud. Both the clean path and the
    crash path go through here, so no run directory lacks a verdict."""
    (Path(results_dir) / "final_state.json").write_text(
        json.dumps(verdict, indent=2))
    banner = {
        "DELIVERED": "DELIVERED: conforming to the firm standard.",
        "REFUSED": "REFUSED: no conforming deliverable was produced. "
                   "Nothing was issued.",
        "ESCAPED": "ESCAPED: a NON-CONFORMING deliverable is on disk. "
                   "The guarantee FAILED -- do not deliver this run.",
    }[verdict["state"]]
    rule = "=" * 72
    print(f"\n{rule}\n  {banner}\n  {verdict['detail']}\n{rule}")


def final_state(guard) -> dict:
    """What is actually on disk when the run ends, established by reading
    it — not inferred from the ledger.

    runF_r2 ended with a blocked memorandum still in the output directory
    while the ledger recorded a successful block. A receipt that says a
    file was stopped, next to that file, is worse than no receipt. So the
    run ends by looking.

    Three outcomes, and only the first two are acceptable:
      DELIVERED  a conforming deliverable exists
      REFUSED    nothing was issued, and the run says so out loud
      ESCAPED    a non-conforming deliverable survived; the guarantee
                 failed and the run must not be used
    """
    from hook.drafting import check_draft
    from hook.guard import _OUTPUT_PATH

    name = guard.config.governed_deliverable
    path = f"{_OUTPUT_PATH}/{name}"
    try:
        if not guard.sandbox.exists(path):
            return {"state": "REFUSED", "deliverable": name,
                    "cleared_items_flagged": None,
                    "detail": f"{name} was never produced to the required "
                              f"standard, so nothing is being issued."}
        text = guard._read_and_parse(path)
        findings = check_draft(text, guard.config.engagement,
                               guard.doc_names)
        raised = findings.flagged_cleared_items
        if findings.no_cleared_items_flagged:
            return {"state": "DELIVERED", "deliverable": name,
                    "cleared_items_flagged": [],
                    "detail": f"{name} raises no already-cleared item as a "
                              f"red flag."}
        return {"state": "ESCAPED", "deliverable": name,
                "cleared_items_flagged": raised,
                "detail": f"{name} raises {len(raised)} already-cleared "
                          f"item(s) as red flags and is on disk anyway: "
                          f"{'; '.join(raised)}."}
    except Exception as exc:
        return {"state": "ESCAPED", "deliverable": name,
                "cleared_items_flagged": None,
                "detail": f"final state could not be established ({exc!r}); "
                          f"treat as unverified."}


def main():
    args = parse_args()
    if not args.lab_root:
        raise SystemExit("--lab-root or HARVEY_LABS_ROOT is required")
    if not args.policy_id:
        raise SystemExit("--policy-id or PREFLIGHT_POLICY_ID is required")

    add_lab_to_path(args.lab_root)

    # LAB imports (after sys.path setup).
    from harness.agent_loop import run_agent
    from harness.run import (DEFAULT_SKILLS, SYSTEM_PROMPT_PREAMBLE,
                             _load_env, create_adapter, load_skills,
                             load_task, setup_skill_scripts)
    from harness.tools import ToolExecutor, get_all_tool_definitions
    from sandbox.sandbox import DEFAULT_IMAGE, Sandbox

    from hook.drafting import EngagementConfig, standard_briefing
    from hook.guard import DraftingGuard, GuardConfig
    from hook.ledger import load_entries, render_markdown
    from hook.preflight_client import PreflightClient

    _load_env()
    client = PreflightClient()

    engagement = EngagementConfig.from_dict(
        json.loads(Path(args.engagement).read_text()))

    if args.run_id is None:
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        args.run_id = f"{ts}-{args.model.split('/')[-1].replace('.', '-')}"

    task = load_task(task_name=args.task)
    deliverables = list(task["config"].get("deliverables", {}).keys())

    results_dir = Path(args.runs_dir) / args.run_id
    output_dir = results_dir / "output"
    workspace_dir = results_dir / "workspace"
    output_dir.mkdir(parents=True, exist_ok=True)
    workspace_dir.mkdir(parents=True, exist_ok=True)

    sandbox = Sandbox(
        documents_dir=Path(task["docs_dir"]),
        output_dir=output_dir,
        workspace_dir=workspace_dir,
        image=DEFAULT_IMAGE,
        default_timeout=args.shell_timeout,
    )
    sandbox.start()
    print(f"Sandbox up (documents={sandbox.documents_dir})")

    adapter = create_adapter(model=args.model, temperature=args.temperature,
                             reasoning_effort=args.reasoning_effort)
    inner = ToolExecutor(sandbox=sandbox, shell_timeout=args.shell_timeout)

    guard = DraftingGuard(inner, client, GuardConfig(
        policy_id=args.policy_id,
        documents_dir=task["docs_dir"],
        engagement=engagement,
        ledger_path=str(results_dir / "ledger.jsonl"),
        explain_blocks=not args.bare_blocks,
    ))
    print(f"Drafting guard up: policy {args.policy_id}, "
          f"governs {guard.config.governed_deliverable} "
          f"(of {deliverables}), "
          f"client={engagement.client_names[:1]} firm={engagement.firm_names[:1]}")

    skill_names = DEFAULT_SKILLS if args.skills is None else args.skills
    system_prompt = SYSTEM_PROMPT_PREAMBLE
    if skill_names:
        system_prompt += load_skills(skill_names)
        setup_skill_scripts(skill_names, workspace_dir)
    # State the standard before the work starts, the way a firm briefs an
    # associate. --no-briefing reproduces the earlier behaviour where the
    # agent learns the rule only by being blocked; enforcement is
    # identical either way, since the guard recomputes every fact itself.
    if not args.no_briefing:
        system_prompt += standard_briefing(
            guard.config.governed_deliverable,
            engagement.cleared_items)

    (results_dir / "config.json").write_text(json.dumps({
        "model": args.model, "task": args.task, "run_id": args.run_id,
        "policy_id": args.policy_id,
        "engagement": args.engagement,
        "max_turns": args.max_turns, "temperature": args.temperature,
        "skills": skill_names,
        "briefing": not args.no_briefing,
        "explain_blocks": not args.bare_blocks,
        "started_at": datetime.now(timezone.utc).isoformat(),
    }, indent=2))

    verdict = {"state": "REFUSED", "detail": "run did not complete"}
    try:
        result = run_agent(
            adapter=adapter,
            system_prompt=system_prompt,
            user_prompt=task["instructions"],
            tool_executor=guard,
            tools=get_all_tool_definitions(),
            max_turns=args.max_turns,
            transcript_path=str(results_dir / "transcript.jsonl"),
        )
    except BaseException as exc:
        # A run that dies still has to say what is on disk. runH_r1 hit an
        # Anthropic 400 (out of credits) and left a run directory with no
        # verdict at all -- the one state the "conforming, or a visible
        # refusal" contract does not allow. The traceback still surfaces;
        # this just makes sure the artifact question is answered too.
        verdict = final_state(guard)
        verdict["detail"] = (f"run ended early ({type(exc).__name__}); "
                             + verdict["detail"])
        write_verdict(results_dir, verdict)
        raise
    finally:
        # While the sandbox is still up: LAB parses .docx INSIDE it on
        # purpose, so the final verdict uses the guard's own reader
        # rather than parsing an agent-written binary on the host.
        if verdict["state"] == "REFUSED" and \
                verdict["detail"] == "run did not complete":
            verdict = final_state(guard)
        sandbox.stop()
        guard.finish(results_dir / "ledger.json")

    (results_dir / "metrics.json").write_text(json.dumps({
        **{k: result[k] for k in ("turn_count", "input_tokens",
                                  "output_tokens", "wall_clock_seconds",
                                  "finished_cleanly")},
        **result["tool_metrics"],
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }, indent=2))

    entries = load_entries(results_dir / "ledger.jsonl")
    (results_dir / "ledger.md").write_text(render_markdown(entries),
                                           encoding="utf-8")
    sat = sum(1 for e in entries if e["result"] == "SAT")
    unsat = sum(1 for e in entries if e["result"] == "UNSAT")
    print(f"\nDrafting run complete: {results_dir}")
    print(f"  checks: {len(entries)}  SAT: {sat}  UNSAT (blocked): {unsat}")

    # The deliverable of this system is "a conforming memorandum, or a
    # visible refusal with a reason" -- never "silently absent". runF_r2
    # ended with a blocked file still on disk and nothing saying so, so
    # the final state is now established by inspecting the artifact
    # rather than inferred from the ledger.
    write_verdict(results_dir, verdict)

    print("\nScore it with LAB's own evaluator, e.g.:")
    print(f"  cd {args.lab_root} && uv run python -m evaluation.run_eval "
          f"--run-id <id> --task {args.task} --judge-model claude-sonnet-4-6")


if __name__ == "__main__":
    main()
