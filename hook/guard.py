"""DraftingGuard — Preflight enforcement of drafting standards, wrapped
around LAB's ToolExecutor.

Composition, not patching: this wraps any object exposing LAB's
ToolExecutor interface (.execute(), .get_metrics(), .files_read) and
delegates everything else untouched, so not one line of harvey-labs is
modified. The agent loop receives it via run_agent()'s tool_executor.

WHERE THIS INTERCEPTS, and why it matters
-----------------------------------------
The agent does not write `red-flag-memo.docx` directly. It writes the memo
as markdown, then converts it with LAB's docx skill:

    write   memo_content.md          <- the memo actually exists here
    bash    generate_from_md.py memo_content.md output/red-flag-memo.docx

Checking only the final `.docx` would be too late to be useful: by then
the draft is finished and a block forces a full rewrite. Worse, the
converted file is a binary the guard would have to re-extract to read.

So a write is governed when it carries the *memo content*, whether or not
its filename is the deliverable — see `_is_draft`. That is the moment the
standard can be applied and the moment feedback is cheap to act on.

Flow per governed action:
  1. compute drafting facts host-side (hook/drafting.py) — the ONLY place
     facts are produced; nothing is assumed
  2. render an action string stating exactly those facts (action_text.py)
  3. checkIt — 1 credit, SSE verdict, receipt recorded
  4. UNSAT -> the write never happens; the agent is told which element is
     missing and revises
     SAT   -> delegate to the wrapped executor

Fail-closed: if the API is unreachable after bounded retries the action is
blocked and the outage is recorded, so no run contains a silent gap.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from hook import action_text as at
from hook.drafting import EngagementConfig, check_draft, citeable_names
from hook.ledger import Ledger
from hook.preflight_client import PreflightClient, PreflightUnreachable

# A write is a memo draft if it is long enough to be a memo and reads like
# one. Length alone is not enough (a data dump would qualify); a marker
# alone is not enough (a one-line note mentioning "memorandum" would).
_DRAFT_MIN_CHARS = 1200
_DRAFT_MARKERS = ("memorandum", "red flag", "diligence")


@dataclass
class GuardConfig:
    policy_id: str
    documents_dir: str
    deliverable_names: list[str]
    engagement: EngagementConfig
    ledger_path: str
    fail_closed: bool = True
    max_retries: int = 3
    retry_wait_s: float = 2.0
    proof_queue: list[str] = field(default_factory=list)


class DraftingGuard:
    def __init__(self, inner, client: PreflightClient, config: GuardConfig):
        self._inner = inner
        self._client = client
        self._cfg = config
        self._ledger = Ledger(config.ledger_path)
        self._doc_names = citeable_names(config.documents_dir)
        # Set once a draft passes. Generating the deliverable is permitted
        # only after this, so the conversion step cannot outrun the check.
        self._approved_draft = False

    def __getattr__(self, name):
        # Everything not overridden here is LAB's own behaviour.
        return getattr(self._inner, name)

    @property
    def ledger(self) -> Ledger:
        return self._ledger

    @property
    def proof_queue(self) -> list[str]:
        return self._cfg.proof_queue

    # ---- what counts as a governed action ------------------------------

    def _is_draft(self, path: str, content: str) -> bool:
        base = Path(path).name.lower()
        if any(base == d.lower() for d in self._cfg.deliverable_names):
            return True
        if len(content) < _DRAFT_MIN_CHARS:
            return False
        low = content.lower()
        return sum(m in low for m in _DRAFT_MARKERS) >= 2

    # ---- the seam -------------------------------------------------------

    def execute(self, tool_name: str, arguments: str | dict) -> str:
        args = arguments
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except ValueError:
                return self._inner.execute(tool_name, arguments)

        if tool_name == "bash":
            return self._bash(args, tool_name, arguments)

        if tool_name not in ("write", "edit"):
            self._ledger.record(
                tool=tool_name, summary=f"{tool_name}",
                action_text=f"{tool_name}", result="SKIPPED",
                detail="not a document write — no drafting rule applies")
            return self._inner.execute(tool_name, arguments)

        path = args.get("file_path") or args.get("path") or ""
        content = args.get("content") or args.get("new_string") or ""

        if not self._is_draft(path, content):
            self._ledger.record(
                tool=tool_name, summary=f"{tool_name}: {path}",
                action_text=f"{tool_name}: {path}", result="SKIPPED",
                detail="not the deliverable memorandum")
            return self._inner.execute(tool_name, arguments)

        findings = check_draft(content, self._cfg.engagement, self._doc_names)
        return self._govern(findings, f"{tool_name}: {path}", content,
                            tool_name, arguments)

    def _bash(self, args: dict, tool_name, arguments) -> str:
        """Govern shell commands that bring the deliverable into existence.

        The first version of this guard skipped bash entirely, reasoning
        that "a standard is a property of the document, and the document
        only exists at a write". That was wrong, and runD_r1 proved it in
        the most direct way available: blocked three times on `write`, the
        agent wrote the memo with a bash heredoc and converted it with
        `generate_from_md.py`. Zero permitted writes, a finished .docx on
        disk, and a ledger that looked respectable next to a deliverable
        missing its issuing firm.

        That is the same hole as BATTLE-TEST-FINDINGS §6 in the conduct
        demo — cited in this file's own docstring, and recreated anyway.

        Two pathways are governed here:
          1. a heredoc carrying memo content -> check that content
          2. a command producing a deliverable -> permitted only if a
             compliant draft was approved earlier in this run. The content
             lives in a sandbox file the guard cannot read, so the
             precondition is the enforceable thing.
        """
        cmd = args.get("command") or ""

        # (1) heredoc or redirect carrying the memo itself
        if self._is_draft("", cmd):
            findings = check_draft(cmd, self._cfg.engagement, self._doc_names)
            return self._govern(findings, "bash (memo content)", cmd,
                                tool_name, arguments)

        # (2) a command that produces a deliverable file
        names = [d.lower() for d in self._cfg.deliverable_names]
        if any(n in cmd.lower() for n in names):
            if self._approved_draft:
                self._ledger.record(
                    tool="bash", summary="bash: produce deliverable",
                    action_text="bash: produce deliverable", result="SKIPPED",
                    detail="a compliant draft was approved earlier in this run")
                return self._inner.execute(tool_name, arguments)
            self._ledger.record(
                tool="bash", summary="bash: produce deliverable",
                action_text=cmd[:400], result="UNSAT",
                detail="deliverable generated without an approved draft")
            return (
                "Blocked by firm drafting standards: this command produces "
                "the deliverable, but no draft meeting the issuing standard "
                "has been approved in this run. Write the memorandum with "
                "the `write` tool first so it can be checked, then generate "
                "the deliverable from the approved draft.")

        self._ledger.record(
            tool="bash", summary=f"bash: {cmd[:60]}",
            action_text=f"bash: {cmd[:60]}", result="SKIPPED",
            detail="shell command not producing a governed document")
        return self._inner.execute(tool_name, arguments)

    def _govern(self, findings, summary, action_src, tool_name, arguments):
        facts = at.deliverable_action(summary, findings)
        res = self._checked(facts)
        if res is None:
            self._ledger.record(tool=facts.tool, summary=summary,
                                action_text=facts.text, result="OUTAGE-BLOCKED",
                                detail="Preflight unreachable; fail-closed")
            return ("SecurityError: firm drafting-standards check "
                    "unavailable. This document was not written.")
        blocked, verdict, note = self._decide(res)
        self._ledger.record(
            tool=facts.tool, summary=summary, action_text=facts.text,
            result=verdict, detail=note or "",
            check_id=res.get("check_id"),
            proof_id=res.get("zk_proof_id") or res.get("proof_id"),
            verification_time_ms=res.get("verification_time_ms"))
        pid = res.get("zk_proof_id") or res.get("proof_id")
        if pid:
            self._cfg.proof_queue.append(pid)
        if blocked:
            return at.block_message(findings)
        self._approved_draft = True
        return self._inner.execute(tool_name, arguments)

    # ---- verdict --------------------------------------------------------

    @staticmethod
    def _decide(res: dict) -> tuple[bool, str, str | None]:
        """Key the decision on the deterministic solver.

        Same rationale as the conduct demo: z3 is the computation the
        zero-knowledge proof attests, and the AR layer has been observed
        to be non-deterministic across identical inputs. The AR verdict is
        recorded as advisory. Blocking on z3=UNSAT is safe in the
        direction that matters — UNSAT means no satisfying assignment
        exists for any value of an unbound variable.
        """
        z3 = res.get("z3_result")
        combined = res.get("result")
        detail = res.get("detail") or ""
        ar = res.get("ar_result")
        note = detail if not ar else f"{detail} [AR advisory: {ar}]"
        verdict = z3 if z3 in ("SAT", "UNSAT") else combined
        if verdict not in ("SAT", "UNSAT"):
            verdict = "UNSAT"          # fail closed on an unreadable verdict
            note = (note + " [unreadable verdict — fail-closed]").strip()
        return verdict == "UNSAT", verdict, note

    def _checked(self, facts: at.ActionFacts) -> dict | None:
        for attempt in range(self._cfg.max_retries):
            try:
                return self._client.check_it(self._cfg.policy_id, facts.text)
            except PreflightUnreachable:
                if attempt + 1 < self._cfg.max_retries:
                    time.sleep(self._cfg.retry_wait_s * (attempt + 1))
        return None

    def finish(self, ledger_json_path: str | Path):
        # Ledger exposes consolidate() + close(), not finish(). Getting
        # this wrong only failed at the END of a run, inside the finally
        # block, after ~20 minutes of agent work and ~12 credits — the
        # entire run was lost to a one-line typo. Covered by test_guard
        # now: any offline test that calls finish() would have caught it.
        self._ledger.consolidate(ledger_json_path)
        self._ledger.close()
