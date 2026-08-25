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
import shlex
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import re

from hook import action_text as at
from hook.drafting import EngagementConfig, check_draft, citeable_names
from hook.ledger import Ledger

try:                                    # LAB's output mount
    from sandbox.sandbox import OUTPUT_PATH as _OUTPUT_PATH
except Exception:                       # offline tests run without LAB
    _OUTPUT_PATH = "/workspace/output"
from hook.preflight_client import PreflightClient, PreflightUnreachable

# Governance is by DESTINATION, not by content.
#
# Three earlier versions tried to recognise the memo from what it said —
# long, mentions "red flag" and "diligence" — and each misfired. runE_r1
# refused the agent's 50KB xlsx-builder eight times because its openpyxl
# data strings contain those words, and refused response.md twice because
# it is prose about red flags. Both had already been established as not
# the deliverable.
#
# The deliverable is a known filename. It comes into existence exactly one
# way: a converter reads a markdown source and writes the .docx. So:
#
#   * a write whose path IS the deliverable            -> check the content
#   * a write to a markdown file                       -> remember the content
#   * a command converting SOURCE -> deliverable       -> permitted only if
#                                                         SOURCE was approved
#
# Nothing else is governed, whatever it contains. A file that never becomes
# a deliverable cannot violate a standard about deliverables.

# `... generate_from_md.py SRC OUT`, `pandoc SRC -o OUT`, `... SRC > OUT`.
# Paths may be quoted (`pandoc "memo.md" -o "out.docx"`); the quote sits
# outside the filename character class, so it is skipped explicitly.
_CONVERSION = re.compile(
    r"(?P<src>[^\s'\";|&]+\.(?:md|markdown|txt))['\"]?"  # the source file
    r"(?:\s+(?:-o|--output)?\s*)['\"]?"                   # optional -o
    r"(?P<out>[^\s'\";|&]+\.docx)"                       # the deliverable
    r"|(?P<out2>[^\s'\";|&]+\.docx)['\"]?[^\n]*?"
    r"(?P<src2>[^\s'\";|&]+\.(?:md|markdown|txt))",
    re.I)

# `cat > FILE << 'EOF' ... EOF` — captures the target and the body.
_HEREDOC_WRITE = re.compile(
    r">>?\s*(?P<target>[^\s|;&]+)\s*<<\s*'?\"?(?P<tag>\w+)'?\"?\n"
    r"(?P<body>.*?)\n\s*(?P=tag)",
    re.S)


@dataclass
class GuardConfig:
    policy_id: str
    documents_dir: str
    engagement: EngagementConfig
    ledger_path: str
    # Which deliverable this standard applies to. LAB's C-036 is itself
    # scoped this way ("deliverables": ["red-flag-memo.docx"]), and the
    # rule must be too: runF_r1 applied the executive-summary standard to
    # red-flag-tracker.xlsx, a spreadsheet that can never contain an
    # executive summary, and reverted the tracker four times running. A
    # rule about memoranda has nothing to say about a spreadsheet.
    governed_deliverable: str = "red-flag-memo.docx"
    # LAB's C-043 governs the tracker: "FAIL if more than two of these
    # columns are missing". That criterion states its own list and its
    # own threshold, so unlike the executive-summary rule it is enforced
    # verbatim rather than through a stricter stand-in. Scoped to the
    # tracker for the same reason Rule 1 is scoped to the memorandum.
    # Whether a block names the missing element. True is what a firm
    # would do; False is the demo's control arm — the gate alone, no
    # repair signal. Enforcement and the ledger are identical either way.
    explain_blocks: bool = True
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
        # Markdown sources seen this run, by basename. A conversion is
        # checked against the content of its source.
        self._sources: dict[str, str] = {}

    # ---- artifact verification (route-independent) ----------------------

    def _sandbox(self):
        return getattr(self._inner, "sandbox", None)

    def _deliverable_paths(self) -> list[str]:
        """Only the deliverable this standard governs.

        runF_r1 applied the executive-summary rule to
        red-flag-tracker.xlsx, a spreadsheet that can never contain an
        executive summary, and reverted it four times. LAB's C-036 is
        itself scoped to red-flag-memo.docx.
        """
        return [f"{_OUTPUT_PATH}/{self._cfg.governed_deliverable}"]

    def _facts_for(self, name: str, text: str):
        """The rule for this deliverable and its block message."""
        f = check_draft(text, self._cfg.engagement, self._doc_names)
        return (at.deliverable_action(name, f),
                at.block_message(f, self._cfg.explain_blocks))

    def _snapshot(self) -> dict[str, bytes | None]:
        """Current bytes of each deliverable, or None if absent."""
        sb = self._sandbox()
        if sb is None:
            return {}
        out: dict[str, bytes | None] = {}
        for path in self._deliverable_paths():
            try:
                out[path] = sb.read_file(path) if sb.exists(path) else None
            except Exception:
                out[path] = None
        return out

    def _revert(self, path: str, previous: bytes | None) -> bool:
        """Put `path` back the way it was. True only if that is confirmed.

        A revert that fails is the guarantee failing, so this verifies the
        filesystem afterwards rather than trusting the call. runF_r2
        shipped a blocked memorandum because this used
        sb.exec(["rm", "-f", path]) -- LAB's Sandbox.exec takes a command
        STRING, the call raised TypeError, and a bare `except: pass`
        swallowed it. The blocked .docx stayed on disk and was delivered.
        Never silently; a failed revert is louder than a block.
        """
        sb = self._sandbox()
        if sb is None:
            return False
        try:
            if previous is None:
                sb.exec(f"rm -f {shlex.quote(path)}")
                return not sb.exists(path)
            sb.write_file(path, previous)
            return sb.read_file(path) == previous
        except Exception as exc:
            print(f"REVERT FAILED for {path}: {exc!r}", file=sys.stderr)
            return False

    def _revert_or_alarm(self, tool_name: str, path: str,
                         previous: bytes | None) -> str | None:
        """Revert, and if that fails say so instead of implying success."""
        if self._revert(path, previous):
            return None
        name = Path(path).name
        self._ledger.record(
            tool=tool_name, summary=f"revert-failed: {name}",
            action_text=f"revert {name}", result="REVERT-FAILED",
            detail="deliverable was non-compliant and could NOT be removed")
        return (f"SecurityError: {name} is non-compliant and the guard "
                f"could not remove it. Delete {path} yourself before "
                f"doing anything else; it must not be delivered.")

    def _verify_artifacts(self, before: dict[str, bytes | None],
                          tool_name: str) -> str | None:
        """Check any deliverable this call changed. Returns a block message
        if one is non-compliant, having reverted it; None otherwise.

        This is the enforcement point that does not depend on recognising
        the command. runD_r1 escaped through a bash heredoc, runE_r2
        through pandoc wrapped in `python3 -c`; both changed the file, so
        both are caught here regardless of spelling.

        The standard is about what is ISSUED, not about whether a bad
        draft ever existed — an associate's rejected draft sat on a desk
        too. So a non-compliant deliverable is reverted within the same
        tool call and never survives to be delivered. Note this is the
        right semantics for a work-product standard and the WRONG
        semantics for an exfiltration rule, where a transmitted byte
        cannot be recalled and prevention must come first.
        """
        after = self._snapshot()
        for path, now in after.items():
            if now is None or now == before.get(path):
                continue              # unchanged or removed
            name = Path(path).name
            try:
                text = self._inner._read_and_parse(path)
            except Exception as exc:
                alarm = self._revert_or_alarm(tool_name, path,
                                              before.get(path))
                self._ledger.record(
                    tool=tool_name, summary=f"verify: {name}",
                    action_text=f"verify: {name}", result="UNSAT",
                    detail=f"deliverable unreadable ({exc}); reverted")
                return alarm or (
                    f"Blocked by firm drafting standard: {name} could "
                    f"not be read for checking, so it was not kept.")

            facts, block_text = self._facts_for(name, text)
            res = self._checked(facts)
            if res is None:
                alarm = self._revert_or_alarm(tool_name, path,
                                              before.get(path))
                self._ledger.record(
                    tool=tool_name, summary=f"verify: {name}",
                    action_text=facts.text, result="OUTAGE-BLOCKED",
                    detail="Preflight unreachable; deliverable reverted")
                return alarm or (
                    "SecurityError: firm drafting-standards check "
                    f"unavailable; {name} was not kept.")

            blocked, verdict, note = self._decide(res)
            self._ledger.record(
                tool=tool_name, summary=f"verify: {name}",
                action_text=facts.text, result=verdict, detail=note or "",
                check_id=res.get("check_id"),
                proof_id=res.get("zk_proof_id") or res.get("proof_id"),
                verification_time_ms=res.get("verification_time_ms"))
            pid = res.get("zk_proof_id") or res.get("proof_id")
            if pid:
                self._cfg.proof_queue.append(pid)

            if blocked:
                alarm = self._revert_or_alarm(tool_name, path,
                                              before.get(path))
                if alarm:
                    return alarm
                tail = (f"\n\n{name} was not kept. Revise and produce it "
                        f"again." if self._cfg.explain_blocks
                        else f"\n\n{name} was not kept.")
                return block_text + tail
        return None

    def __getattr__(self, name):
        # Everything not overridden here is LAB's own behaviour.
        return getattr(self._inner, name)

    @property
    def config(self) -> GuardConfig:
        return self._cfg

    @property
    def doc_names(self) -> set[str]:
        return self._doc_names

    @property
    def ledger(self) -> Ledger:
        return self._ledger

    @property
    def proof_queue(self) -> list[str]:
        return self._cfg.proof_queue

    # ---- what counts as a governed action ------------------------------

    def _is_deliverable(self, path: str) -> bool:
        return (Path(path).name.lower()
                == self._cfg.governed_deliverable.lower())

    @staticmethod
    def _is_source(path: str) -> bool:
        return Path(path).suffix.lower() in (".md", ".markdown", ".txt")

    # ---- the seam -------------------------------------------------------

    def execute(self, tool_name: str, arguments: str | dict) -> str:
        """Every tool call is verified against the deliverables afterwards.

        The pre-checks below still run — they give the agent feedback at
        the moment it drafts, which is cheaper to act on than a rejection
        after conversion. But they are no longer what makes the guarantee.
        The guarantee is _verify_artifacts: whatever the command was, if a
        deliverable changed and does not meet the standard, it is reverted
        before the agent sees a result.
        """
        before = self._snapshot()
        result = self._execute_inner(tool_name, arguments)
        blocked = self._verify_artifacts(before, tool_name)
        return blocked if blocked is not None else result

    def _execute_inner(self, tool_name: str, arguments: str | dict) -> str:
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

        if tool_name == "edit":
            return self._edit(args, path, tool_name, arguments)

        content = args.get("content") or ""

        # Writing the deliverable itself: check it.
        if self._is_deliverable(path):
            findings = check_draft(content, self._cfg.engagement,
                                   self._doc_names)
            return self._govern(findings, f"{tool_name}: {path}", path,
                                tool_name, arguments)

        # Writing a markdown source: remember it. Not governed — a source
        # file is only consequential if something converts it, and that
        # conversion is where the gate sits.
        if self._is_source(path) and content:
            self._sources[Path(path).name] = content
            self._ledger.record(
                tool=tool_name, summary=f"{tool_name}: {path}",
                action_text=f"{tool_name}: {path}", result="SKIPPED",
                detail="source file recorded; checked if converted")
            return self._inner.execute(tool_name, arguments)

        self._ledger.record(
            tool=tool_name, summary=f"{tool_name}: {path}",
            action_text=f"{tool_name}: {path}", result="SKIPPED",
            detail="does not become a deliverable")
        return self._inner.execute(tool_name, arguments)

    def _edit(self, args: dict, path: str, tool_name, arguments) -> str:
        """An edit carries a FRAGMENT, and a fragment must never be
        testified about as if it were the document.

        The first version fed new_string through the same path as a full
        write: editing one word of a compliant memo produced the action
        string "the number of findings listed in the executive summary is
        0" — false testimony about a memo that lists five, the exact §6
        failure this repo's own docstrings warn about. The solver would
        have blocked a conforming document, and worse, the recorded source
        was REPLACED by the fragment, so every later conversion was judged
        against a one-line string.

        So an edit is never pre-checked. On the deliverable itself,
        _verify_artifacts reads the real resulting file after the call —
        that is the guarantee, and it needs no guess about what the edit
        produced. On a recorded source, the edit is applied to the record
        (the same replacement the tool performs) so the record keeps
        matching the file; an edit this method cannot mirror drops the
        record instead, and a later conversion of that source is refused
        as unseen rather than judged against stale text.
        """
        name = Path(path).name
        old = args.get("old_string") or ""
        new = args.get("new_string") or ""

        if self._is_source(path) and name in self._sources:
            stored = self._sources[name]
            if old and old in stored:
                self._sources[name] = stored.replace(old, new, 1)
                detail = "source record updated with the edit"
            else:
                del self._sources[name]
                detail = ("edit could not be mirrored; source record "
                          "dropped — a conversion must rewrite it first")
            self._ledger.record(
                tool=tool_name, summary=f"{tool_name}: {path}",
                action_text=f"{tool_name}: {path}", result="SKIPPED",
                detail=detail)
            return self._inner.execute(tool_name, arguments)

        self._ledger.record(
            tool=tool_name, summary=f"{tool_name}: {path}",
            action_text=f"{tool_name}: {path}", result="SKIPPED",
            detail=("edit carries a fragment, not a document; the result "
                    "is verified after execution"
                    if self._is_deliverable(path)
                    else "does not become a deliverable"))
        return self._inner.execute(tool_name, arguments)

    def _bash(self, args: dict, tool_name, arguments) -> str:
        """Govern shell commands by what they produce.

        Two pathways, both keyed on destination rather than vocabulary:

        1. A heredoc writing a markdown source — recorded, not checked.
           The source only matters if something converts it.
        2. A command converting SOURCE -> deliverable — the gate. The
           source's content is checked here, so the .docx cannot come into
           existence from a draft that does not meet the standard.

        This is what closes the runD_r1 bypass without the false positives
        that content-sniffing produced: a script or a summary file is
        untouched because neither becomes a deliverable.
        """
        cmd = args.get("command") or ""

        # (1) heredoc writing a source file — record it
        for m in _HEREDOC_WRITE.finditer(cmd):
            target, body = m.group("target").strip("'\""), m.group("body")
            if self._is_source(target):
                self._sources[Path(target).name] = body
            elif self._is_deliverable(target):
                findings = check_draft(body, self._cfg.engagement,
                                       self._doc_names)
                return self._govern(findings, f"bash: write {target}",
                                    target, tool_name, arguments)

        # (2) a conversion producing the deliverable — the gate
        m = _CONVERSION.search(cmd)
        if m:
            src = (m.group("src") or m.group("src2") or "")
            out = (m.group("out") or m.group("out2") or "")
            if self._is_deliverable(out):
                body = self._sources.get(Path(src).name)
                if body is None:
                    self._ledger.record(
                        tool="bash", summary=f"bash: convert {src} -> {out}",
                        action_text=cmd[:400], result="UNSAT",
                        detail="source content unknown to the guard")
                    return (
                        "Blocked by firm drafting standard: this command "
                        f"produces {out} from {src}, but {src} was never "
                        "written through a channel this check can see. "
                        "Write the memorandum with the `write` tool, then "
                        "convert it.")
                findings = check_draft(body, self._cfg.engagement,
                                       self._doc_names)
                return self._govern(findings, f"bash: convert {src} -> {out}",
                                    out, tool_name, arguments)

        self._ledger.record(
            tool="bash", summary=f"bash: {cmd[:60]}",
            action_text=f"bash: {cmd[:60]}", result="SKIPPED",
            detail="does not produce a deliverable")
        return self._inner.execute(tool_name, arguments)

    def _govern(self, findings, summary, action_src, tool_name, arguments):
        # Testimony names the deliverable, not the command that produced
        # it: "bash: convert memo.md -> output/red-flag-memo.docx" is a
        # ledger summary, and stuffing it into the action string made the
        # solver reason about a sentence containing an arrow. The command
        # stays in `summary` for the ledger.
        facts = at.deliverable_action(Path(action_src).name, findings)
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
            return at.block_message(findings,
                                    explain=self._cfg.explain_blocks)
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
                return self._client.check_it(self._cfg.policy_id,
                                             facts.text)
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
