"""Compile and battle-test the firm controls.

Subcommands:
  compile   POST /v1/makeRules with policy/controls.md (300 credits, ONE
            time — takes minutes). Saves policy/policy.json.
  scenarios List the battle-testing scenarios for review.
  feedback  Submit thumbs up/down on a scenario.
  refine    One in-place refinePolicy pass (policy_id unchanged).
  test      runPolicyTests — all saved scenarios must pass before any
            recorded run.

Usage:
  PREFLIGHT_API_KEY=... python -m scripts.compile_policy compile
  python -m scripts.compile_policy scenarios
  python -m scripts.compile_policy feedback --scenario-id S1 --verdict up
  python -m scripts.compile_policy refine
  python -m scripts.compile_policy test
"""

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from hook.preflight_client import PreflightClient  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
CONTROLS = REPO / "policy" / "controls.md"
POLICY_JSON = REPO / "policy" / "policy.json"


def rules_text() -> str:
    # Strip the markdown header and HTML comments; makeRules gets only
    # the rules.
    import re
    text = re.sub(r"<!--.*?-->", "", CONTROLS.read_text(encoding="utf-8"),
                  flags=re.DOTALL)
    lines = [ln for ln in text.splitlines()
             if ln.strip() and not ln.startswith("#")]
    return "\n".join(lines)


def saved_policy_id() -> str:
    if not POLICY_JSON.exists():
        raise SystemExit("policy/policy.json not found — run compile first")
    return json.loads(POLICY_JSON.read_text())["policy_id"]


def cmd_compile(client, _args):
    # makeRules costs 300 credits and there is no recovery endpoint: the
    # policy_id exists only in the stream. Log every event to disk AS IT
    # ARRIVES, before any parsing, so the id is recoverable by grep even
    # if the done event is malformed.
    LOG = REPO / "policy" / f"raw-makeRules-{int(datetime.now().timestamp())}.log"
    if POLICY_JSON.exists():
        raise SystemExit(
            f"{POLICY_JSON} already exists (policy_id="
            f"{saved_policy_id()}). Compiling again costs another 300 "
            f"credits and mints a NEW policy id. Delete the file first if "
            f"you really mean it.")
    text = rules_text()
    print("Compiling (makeRules, 300 credits, takes minutes)...\n")
    print(text, "\n")
    def _log(e):
        with open(LOG, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(e) + "\n")
            fh.flush()
        print(f"  [{e.get('step')}] {e.get('msg', '')}")

    done = client.make_rules(text, on_event=_log)
    policy_id = done.get("policy_id")
    if not policy_id:
        raise SystemExit(
            f"no policy_id in done event: {done}\n"
            f"The 300 credits are spent. Recover the id with:\n"
            f"  grep -o '\"policy_id\":\"[^\"]*\"' {LOG}")
    print(f"  (raw event log: {LOG})")
    POLICY_JSON.write_text(json.dumps({
        "policy_id": policy_id,
        "compiled_at": datetime.now(timezone.utc).isoformat(),
        "source_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "done_event": done,
    }, indent=2))
    print(f"\npolicy_id: {policy_id}  (saved to {POLICY_JSON})")


def cmd_scenarios(client, _args):
    print(json.dumps(client.get_scenarios(saved_policy_id()), indent=2))


def cmd_feedback(client, args):
    body = {"policy_id": saved_policy_id(),
            "scenario_id": args.scenario_id,
            "approved": args.verdict == "up"}
    if args.note:
        body["annotation"] = args.note
    print(json.dumps(client.submit_scenario_feedback(body), indent=2))


def cmd_refine(client, _args):
    print("Refining in place (policy_id unchanged)...")
    done = client.refine_policy(
        saved_policy_id(),
        on_event=lambda e: print(f"  [{e.get('step')}] {e.get('msg', '')}"))
    print(json.dumps(done, indent=2))


def cmd_test(client, _args):
    res = client.run_policy_tests(saved_policy_id())
    print(json.dumps(res, indent=2))


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("compile")
    sub.add_parser("scenarios")
    fb = sub.add_parser("feedback")
    fb.add_argument("--scenario-id", required=True)
    fb.add_argument("--verdict", choices=["up", "down"], required=True)
    fb.add_argument("--note")
    sub.add_parser("refine")
    sub.add_parser("test")
    args = p.parse_args()
    client = PreflightClient()
    {"compile": cmd_compile, "scenarios": cmd_scenarios,
     "feedback": cmd_feedback, "refine": cmd_refine,
     "test": cmd_test}[args.cmd](client, args)


if __name__ == "__main__":
    main()
