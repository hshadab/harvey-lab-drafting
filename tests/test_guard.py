"""Offline tests for DraftingGuard. No network, no API key, no credits.

The Preflight client and LAB's ToolExecutor are both faked, so the real
decision path is exercised without spending anything.

These cover the DESTINATION model: the guard governs what becomes the
deliverable, not what looks like prose about red flags. Three earlier
content-sniffing versions each produced false positives in live runs — a
50KB xlsx-builder script and the agent's response.md were both refused
despite neither ever becoming a deliverable.
"""

import json
import sys
import os
import inspect
import shlex
import tempfile
import unittest
from pathlib import Path

from hook.drafting import EngagementConfig
from hook import runner
from hook.drafting import standard_briefing
from hook.guard import DraftingGuard, GuardConfig
from hook.preflight_client import PreflightUnreachable

CONFIG = EngagementConfig(
    client_names=("Sycamore Capital Partners",),
    firm_names=("Thornfield & Associates LLP",),
    engagement_reference=("Project Ridgeline",),
    cleared_items=(("the Wyoming DEQ permit renewal",
                    "WY-HW-2019-033|wyoming"),),
)

# Items are DESCRIBED, not merely named: an enumerated item shorter than
# _MIN_ITEM_CHARS is a category label, not a finding (see runI_r1).
_ITEMS = (
    "DOE ceiling exhaustion threatens the largest customer relationship.",
    "Unreconciled EBITDA discrepancy between the CIM and the QofE pack.",
    "Stale environmental assessment with no vapour intrusion work done.",
    "Salt Lake City lease assignment consent was never obtained at all.",
    "NLRB union election petition disclosed only in a buried footnote.",
)
FIVE = ("EXECUTIVE SUMMARY\n\nThe most significant concerns are:\n"
        + "".join(f"{i}. {t}\n" for i, t in enumerate(_ITEMS, 1)) + "\n")
THREE = ("EXECUTIVE SUMMARY\n\nThe three most critical issues are:\n"
         + "".join(f"{i}. {t}\n" for i, t in enumerate(_ITEMS[:3], 1)) + "\n")

# The enforced standard is a PROHIBITION: the memo may not raise, as a
# red flag, an item the engagement has already cleared. COMPLIANT raises
# real issues only; SHORT raises the cleared Wyoming permit as RF-04.
_REAL_FLAGS = ("1. DOE contract ceiling exhaustion\n" + "detail. " * 60
               + "\n2. EBITDA reconciliation discrepancy\n"
               + "detail. " * 60 + "\n")
_CLEARED_AS_FLAG = ("3. Wyoming DEQ permit WY-HW-2019-033 expiry\n"
                    + "detail. " * 60 + "\n")

COMPLIANT = "MEMORANDUM\n\n" + FIVE + _REAL_FLAGS
SHORT = "MEMORANDUM\n\n" + FIVE + _REAL_FLAGS + _CLEARED_AS_FLAG

# The 50KB xlsx builder that runE_r1 refused eight times.
TRACKER_SCRIPT = ("cat > /tmp/build_tracker.py << 'PYEOF'\n"
                  "import openpyxl\n"
                  + "rows.append(('red flag', 'diligence finding'))\n" * 60
                  + "PYEOF")


class FakeSandbox:
    """Stands in for LAB's Sandbox: a dict of path -> bytes.

    Every method here mimics the REAL signature, and rejects anything the
    real Sandbox would reject. The previous version accepted a list from
    exec(); the real Sandbox takes a command string, so 41 tests passed
    against an API that does not exist and runF_r2 shipped a blocked
    memorandum. A fake that is more permissive than the thing it fakes is
    not a test, it is a second bug. TestSandboxContract below pins these
    signatures to the real class so the two cannot drift again.
    """
    def __init__(self):
        self.files: dict[str, bytes] = {}
        self.execs: list[str] = []

    def exists(self, path):
        return path in self.files

    def read_file(self, path):
        return self.files[path]

    def write_file(self, path, content):
        self.files[path] = content if isinstance(content, bytes) else content.encode()

    def exec(self, command, **kw):
        if not isinstance(command, str):
            raise TypeError(
                "Sandbox.exec takes a command string, not "
                f"{type(command).__name__}")
        self.execs.append(command)
        parts = shlex.split(command)
        if parts[:2] == ["rm", "-f"]:
            for target in parts[2:]:
                self.files.pop(target, None)
        return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()


class FakeInner:
    """Stands in for LAB's ToolExecutor.

    `writes` lets a test make a tool call produce a deliverable by a route
    the guard cannot recognise from the command — which is the whole point
    of verifying the artifact instead of the command.
    """
    def __init__(self, writes=None):
        self.calls = []
        self.sandbox = FakeSandbox()
        self._writes = writes or {}

    def execute(self, tool_name, arguments):
        self.calls.append((tool_name, arguments))
        for path, content in self._writes.pop(tool_name, {}).items():
            self.sandbox.write_file(path, content)
        return "OK: executed"

    def _read_and_parse(self, path):
        return self.sandbox.files[path].decode()

    def get_metrics(self):
        return {"files_read": 13}


class FakeClient:
    def __init__(self, verdict="SAT", raises=False):
        self.verdict, self.raises = verdict, raises
        self.actions = []

    def check_it(self, policy_id, action):
        if self.raises:
            raise PreflightUnreachable("offline")
        self.actions.append(action)
        return {"result": self.verdict, "z3_result": self.verdict,
                "ar_result": self.verdict, "detail": "test",
                "check_id": "chk-1", "zk_proof_id": "prf-1",
                "verification_time_ms": 5}


def make_guard(client, tmp, writes=None, explain_blocks=True):
    inner = FakeInner(writes)
    g = DraftingGuard(inner, client, GuardConfig(
        policy_id="pol-1", documents_dir=str(tmp),
        engagement=CONFIG, ledger_path=str(Path(tmp) / "ledger.jsonl"),
        max_retries=1, retry_wait_s=0, explain_blocks=explain_blocks))
    return g, inner


def bash(g, cmd):
    return g.execute("bash", json.dumps({"command": cmd}))


def write(g, path, content):
    return g.execute("write", json.dumps({"file_path": path,
                                          "content": content}))


class TestNotGoverned(unittest.TestCase):
    """Things that never become a deliverable are never checked."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def test_tracker_builder_script_is_untouched(self):
        c = FakeClient("UNSAT")
        g, inner = make_guard(c, self.tmp)
        bash(g, TRACKER_SCRIPT)
        self.assertEqual(c.actions, [], "script must not be checked")
        self.assertEqual(len(inner.calls), 1, "script must execute")

    def test_response_md_is_untouched(self):
        """runE_r1 refused this twice. It is not a deliverable."""
        c = FakeClient("UNSAT")
        g, inner = make_guard(c, self.tmp)
        write(g, "response.md", "# Summary of red flags\n" + "prose. " * 400)
        self.assertEqual(c.actions, [])
        self.assertEqual(len(inner.calls), 1)

    def test_reads_and_ordinary_commands_are_untouched(self):
        c = FakeClient("SAT")
        g, inner = make_guard(c, self.tmp)
        g.execute("read", json.dumps({"file_path": "cim.docx"}))
        bash(g, "ls -la && cat notes.txt")
        self.assertEqual(c.actions, [])
        self.assertEqual(len(inner.calls), 2)

    def test_writing_a_source_is_recorded_not_checked(self):
        c = FakeClient("UNSAT")
        g, inner = make_guard(c, self.tmp)
        write(g, "memo.md", SHORT)
        self.assertEqual(c.actions, [], "a source alone is not consequential")
        self.assertEqual(len(inner.calls), 1)


class TestTheGate(unittest.TestCase):
    """The deliverable cannot come into existence from a bad source."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def test_conversion_from_compliant_source_is_permitted(self):
        c = FakeClient("SAT")
        g, inner = make_guard(c, self.tmp)
        write(g, "memo.md", COMPLIANT)
        bash(g, "python generate_from_md.py memo.md output/red-flag-memo.docx")
        self.assertEqual(len(c.actions), 1, "conversion must be checked")
        self.assertIn("raises as red flags is 0", c.actions[0])
        self.assertEqual(len(inner.calls), 2)

    def test_conversion_from_short_source_is_blocked(self):
        c = FakeClient("UNSAT")
        g, inner = make_guard(c, self.tmp)
        write(g, "memo.md", SHORT)
        out = bash(g, "python generate_from_md.py memo.md "
                      "output/red-flag-memo.docx")
        self.assertEqual(len(inner.calls), 1, "only the source write ran")
        self.assertIn("cleared", out.lower())
        self.assertIn("raises as red flags is 1", c.actions[0])

    def test_conversion_from_unseen_source_is_blocked(self):
        """The bypass: a source the guard never saw written."""
        c = FakeClient("SAT")
        g, inner = make_guard(c, self.tmp)
        out = bash(g, "pandoc /tmp/smuggled.md -o output/red-flag-memo.docx")
        self.assertEqual(inner.calls, [], "unknown source must not convert")
        self.assertIn("never written through a channel", out)

    def test_heredoc_source_then_conversion_is_gated(self):
        """runD_r1's escape: write the memo with a heredoc, convert it."""
        c = FakeClient("UNSAT")
        g, inner = make_guard(c, self.tmp)
        bash(g, "cat > memo.md << 'EOF'\n" + SHORT + "\nEOF")
        out = bash(g, "python generate_from_md.py memo.md "
                      "output/red-flag-memo.docx")
        self.assertEqual(len(inner.calls), 1, "conversion must not run")
        self.assertIn("cleared", out.lower())

    def test_writing_the_deliverable_directly_is_checked(self):
        c = FakeClient("UNSAT")
        g, inner = make_guard(c, self.tmp)
        out = write(g, "output/red-flag-memo.docx", SHORT)
        self.assertEqual(inner.calls, [])
        self.assertIn("cleared", out.lower())


DELIVERABLE = "/workspace/output/red-flag-memo.docx"


class TestRuleScope(unittest.TestCase):
    """A rule about memoranda has nothing to say about a spreadsheet.

    runF_r1 applied the executive-summary standard to red-flag-tracker.xlsx
    and reverted the tracker four times. LAB's own C-036 is scoped to
    red-flag-memo.docx; the rule is now scoped the same way.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def test_the_tracker_is_not_governed(self):
        """A rule about memoranda has nothing to say about a spreadsheet.

        runF_r1 applied the executive-summary rule to
        red-flag-tracker.xlsx and reverted the tracker four times. LAB's
        C-036 is scoped to red-flag-memo.docx; so is this.
        """
        tracker = "/workspace/output/red-flag-tracker.xlsx"
        c = FakeClient("UNSAT")
        g, inner = make_guard(c, self.tmp,
                              writes={"bash": {tracker: b"PK\x03\x04xlsx"}})
        out = bash(g, "python build_tracker.py")
        self.assertEqual(c.actions, [], "the tracker must not be checked")
        self.assertEqual(out, "OK: executed")
        self.assertIn(tracker, inner.sandbox.files,
                      "an ungoverned tracker must survive")

    def test_writing_the_tracker_directly_is_not_governed(self):
        c = FakeClient("UNSAT")
        g, inner = make_guard(c, self.tmp)
        write(g, "red-flag-tracker.xlsx", "rows " * 400)
        self.assertEqual(c.actions, [])
        self.assertEqual(len(inner.calls), 1)


class TestArtifactVerification(unittest.TestCase):
    """The guarantee. Route-independent: the command is never inspected.

    runD_r1 escaped through a bash heredoc and runE_r2 through pandoc
    wrapped in `python3 -c`. Both changed the deliverable, so both are
    caught here whatever the command looked like.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def test_unrecognised_route_producing_a_bad_deliverable_is_reverted(self):
        c = FakeClient("UNSAT")
        g, inner = make_guard(c, self.tmp,
                              writes={"bash": {DELIVERABLE: SHORT.encode()}})
        out = g.execute("bash", json.dumps({"command": "make memo"}))
        self.assertIn("cleared", out.lower())
        self.assertNotIn(DELIVERABLE, inner.sandbox.files,
                         "non-compliant deliverable must not survive")

    def test_unrecognised_route_producing_a_good_deliverable_is_kept(self):
        c = FakeClient("SAT")
        g, inner = make_guard(c, self.tmp,
                              writes={"bash": {DELIVERABLE: COMPLIANT.encode()}})
        out = g.execute("bash", json.dumps({"command": "make memo"}))
        self.assertEqual(out, "OK: executed")
        self.assertIn(DELIVERABLE, inner.sandbox.files)

    def test_a_previously_good_deliverable_is_restored_not_deleted(self):
        c = FakeClient("SAT")
        g, inner = make_guard(c, self.tmp,
                              writes={"bash": {DELIVERABLE: COMPLIANT.encode()}})
        g.execute("bash", json.dumps({"command": "make memo"}))
        c.verdict = "UNSAT"
        inner._writes = {"bash": {DELIVERABLE: SHORT.encode()}}
        g.execute("bash", json.dumps({"command": "make memo again"}))
        self.assertEqual(inner.sandbox.files[DELIVERABLE], COMPLIANT.encode(),
                         "the last compliant version must be restored")

    def test_calls_that_change_nothing_are_not_checked(self):
        c = FakeClient("SAT")
        g, inner = make_guard(c, self.tmp)
        g.execute("read", json.dumps({"file_path": "cim.docx"}))
        self.assertEqual(c.actions, [], "no artifact changed, no check")

    def test_outage_during_verification_reverts(self):
        c = FakeClient(raises=True)
        g, inner = make_guard(c, self.tmp,
                              writes={"bash": {DELIVERABLE: COMPLIANT.encode()}})
        out = g.execute("bash", json.dumps({"command": "make memo"}))
        self.assertIn("unavailable", out.lower())
        self.assertNotIn(DELIVERABLE, inner.sandbox.files)


class TestFailureModes(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def test_outage_fails_closed(self):
        c = FakeClient(raises=True)
        g, inner = make_guard(c, self.tmp)
        write(g, "memo.md", COMPLIANT)
        out = bash(g, "pandoc memo.md -o output/red-flag-memo.docx")
        self.assertEqual(len(inner.calls), 1, "conversion must not run")
        self.assertIn("unavailable", out.lower())

    def test_action_text_states_only_computed_facts(self):
        c = FakeClient("SAT")
        g, _ = make_guard(c, self.tmp)
        write(g, "memo.md", SHORT)
        bash(g, "pandoc memo.md -o output/red-flag-memo.docx")
        self.assertIn("raises as red flags is 1", c.actions[0])
        self.assertNotIn("is at least five", c.actions[0])

    def test_ledger_records_every_decision(self):
        c = FakeClient("SAT")
        g, _ = make_guard(c, self.tmp)
        g.execute("read", json.dumps({"file_path": "x"}))
        write(g, "memo.md", COMPLIANT)
        bash(g, "pandoc memo.md -o output/red-flag-memo.docx")
        lines = [json.loads(l) for l in
                 open(Path(self.tmp) / "ledger.jsonl") if l.strip()]
        self.assertEqual([e["result"] for e in lines],
                         ["SKIPPED", "SKIPPED", "SAT"])
        self.assertEqual(lines[-1]["check_id"], "chk-1")

    def test_finish_consolidates_the_ledger(self):
        """Teardown only runs at the end of a real run; a wrong method name
        here destroyed a complete 20-minute run before this existed."""
        c = FakeClient("SAT")
        g, _ = make_guard(c, self.tmp)
        write(g, "memo.md", COMPLIANT)
        out = Path(self.tmp) / "ledger.json"
        g.finish(out)
        self.assertTrue(out.exists())
        self.assertIn("totals", json.loads(out.read_text()))


if __name__ == "__main__":
    unittest.main()


class TestSandboxContract(unittest.TestCase):
    """Pin FakeSandbox's signatures to the real LAB Sandbox.

    This is the test that was missing. runF_r2 delivered a memorandum the
    guard had blocked, because _revert called
    sb.exec(["rm", "-f", path]) while LAB's Sandbox.exec takes a command
    string. The fake accepted the list, every test passed, and a bare
    `except Exception: pass` hid the TypeError at runtime. Comparing the
    fake to the real class closes that gap without importing a sandbox or
    starting a container.
    """

    def _real(self):
        lab = os.environ.get("HARVEY_LABS_ROOT",
                             str(Path.home() / "harvey-labs"))
        if not (Path(lab) / "sandbox" / "sandbox.py").exists():
            self.skipTest(f"harvey-labs not found at {lab}")
        if lab not in sys.path:
            sys.path.insert(0, lab)
        from sandbox.sandbox import Sandbox
        return Sandbox

    def test_fake_matches_real_signatures(self):
        real = self._real()
        for meth in ("exec", "read_file", "write_file", "exists"):
            got = list(inspect.signature(
                getattr(FakeSandbox, meth)).parameters)
            want = list(inspect.signature(
                getattr(real, meth)).parameters)
            self.assertEqual(
                got[1], want[1],
                f"FakeSandbox.{meth} first argument is {got[1]!r} but the "
                f"real Sandbox.{meth} takes {want[1]!r}")

    def test_real_exec_takes_a_string(self):
        real = self._real()
        ann = inspect.signature(real.exec).parameters["command"].annotation
        self.assertEqual(ann, "str",
                         "guard._revert builds a shell string; if this "
                         "changes, _revert must change with it")


class TestRevertIsVerified(unittest.TestCase):
    """A revert that fails must be louder than a block, never silent."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.memo = "/workspace/output/red-flag-memo.docx"

    def test_blocked_deliverable_is_actually_gone(self):
        c = FakeClient("UNSAT")
        g, inner = make_guard(c, self.tmp,
                              writes={"bash": {self.memo: b"memo bytes"}})
        out = bash(g, "cp /tmp/test-out.docx $OUTPUT_DIR/red-flag-memo.docx")
        self.assertIn("was not kept", out)
        self.assertNotIn(self.memo, inner.sandbox.files,
                         "a blocked memo must not survive on disk")
        self.assertEqual(inner.sandbox.execs, ["rm -f " + self.memo])

    def test_revert_failure_is_reported_not_swallowed(self):
        c = FakeClient("UNSAT")
        g, inner = make_guard(c, self.tmp,
                              writes={"bash": {self.memo: b"memo bytes"}})

        def stubborn(command, **kw):       # deletion silently does nothing
            inner.sandbox.execs.append(command)
            return type("R", (), {"returncode": 1})()
        inner.sandbox.exec = stubborn

        out = bash(g, "cp /tmp/x.docx $OUTPUT_DIR/red-flag-memo.docx")
        self.assertIn("could not remove", out)
        self.assertIn("SecurityError", out)
        entries = [json.loads(l) for l
                   in open(g.ledger.path, encoding="utf-8")]
        self.assertTrue(any(e["result"] == "REVERT-FAILED" for e in entries),
                        "a failed revert must appear in the ledger")

    def test_revert_restores_previous_bytes_when_one_existed(self):
        c = FakeClient("UNSAT")
        g, inner = make_guard(c, self.tmp,
                              writes={"bash": {self.memo: b"memo bytes"}})
        inner.sandbox.files[self.memo] = b"PRIOR-GOOD"
        bash(g, "cp /tmp/x.docx $OUTPUT_DIR/red-flag-memo.docx")
        self.assertEqual(inner.sandbox.files[self.memo], b"PRIOR-GOOD")


GOOD_SUMMARY = """MEMORANDUM

Executive Summary

1. Unexplained $1.0M revenue discrepancy in the Q3 QoE package.
2. Phase II ESA identifies groundwater contamination at the Ogden site.
3. Customer concentration: top two accounts are 41% of revenue.
4. Two operating permits expire within nine months of closing.
5. Pending wage-and-hour class action in Utah state court.

Detailed Findings
"""

BAD_SUMMARY = """MEMORANDUM

Executive Summary

We identified fifteen (15) material red flags across six risk categories.

Detailed Findings
"""


class TestFinalState(unittest.TestCase):
    """The run must end by LOOKING at the artifact, not by trusting the
    ledger. runF_r2's ledger recorded a successful block while the blocked
    file sat in the output directory.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.memo = "/workspace/output/red-flag-memo.docx"

    def _verdict(self, contents):
        g, inner = make_guard(FakeClient("SAT"), self.tmp)
        if contents is not None:
            inner.sandbox.files[self.memo] = contents.encode()
        return runner.final_state(g)

    def test_conforming_deliverable_is_DELIVERED(self):
        v = self._verdict(GOOD_SUMMARY)
        self.assertEqual(v["state"], "DELIVERED")
        self.assertEqual(v["exec_summary_findings"], 5)

    def test_absent_deliverable_is_REFUSED_out_loud(self):
        v = self._verdict(None)
        self.assertEqual(v["state"], "REFUSED")
        self.assertIn("nothing is being issued", v["detail"])

    def test_nonconforming_deliverable_on_disk_is_ESCAPED(self):
        v = self._verdict(BAD_SUMMARY)
        self.assertEqual(v["state"], "ESCAPED",
                         "a blocked file left on disk must be reported as "
                         "a failed guarantee, never as a clean refusal")
        self.assertEqual(v["exec_summary_findings"], 0)
        self.assertIn("on disk anyway", v["detail"])

    def test_unreadable_deliverable_is_never_silently_clean(self):
        g, inner = make_guard(FakeClient("SAT"), self.tmp)
        inner.sandbox.files[self.memo] = b"x"

        def boom(path):
            raise RuntimeError("corrupt docx")
        inner._read_and_parse = boom
        v = runner.final_state(g)
        self.assertEqual(v["state"], "ESCAPED")


class TestStandardBriefing(unittest.TestCase):
    """Stating the standard changes what the agent KNOWS, never what is
    ENFORCED."""

    def test_briefing_quotes_the_enforced_threshold(self):
        from hook.drafting import _MIN_EXEC_SUMMARY_FINDINGS
        text = standard_briefing("red-flag-memo.docx")
        self.assertIn(str(_MIN_EXEC_SUMMARY_FINDINGS), text)
        self.assertIn("red-flag-memo.docx", text)

    def test_briefing_does_not_relax_enforcement(self):
        """A briefed agent that ignores the briefing is still blocked."""
        c = FakeClient("UNSAT")
        g, inner = make_guard(c, tempfile.mkdtemp(),
                              writes={"bash": {
                                  "/workspace/output/red-flag-memo.docx":
                                  BAD_SUMMARY.encode()}})
        out = bash(g, "cp /tmp/x.docx $OUTPUT_DIR/red-flag-memo.docx")
        self.assertIn("was not kept", out)


class TestEditTool(unittest.TestCase):
    """An edit carries a fragment. A fragment must never be testified
    about as if it were the document: the first version fed new_string
    through the full-write path, so editing one word of a compliant memo
    produced "the number of findings ... is 0" — false testimony — and
    REPLACED the recorded source with the fragment, so every later
    conversion was judged against a one-line string.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def edit(self, g, path, old, new):
        return g.execute("edit", json.dumps(
            {"file_path": path, "old_string": old, "new_string": new}))

    def test_edited_source_converts_against_the_edited_document(self):
        c = FakeClient("SAT")
        g, inner = make_guard(c, self.tmp)
        write(g, "memo.md", COMPLIANT)
        self.edit(g, "memo.md", "DOE contract ceiling exhaustion",
                  "DOE contract ceiling exhaustion risk")
        bash(g, "pandoc memo.md -o output/red-flag-memo.docx")
        self.assertEqual(len(c.actions), 1)
        self.assertIn("raises as red flags is 0", c.actions[0],
                      "testimony must describe the document, not the "
                      "edit fragment")

    def test_edit_that_adds_a_cleared_item_blocks_the_conversion(self):
        """The edit is mirrored onto the recorded source, so the
        conversion is judged on the edited document."""
        c = FakeClient("UNSAT")
        g, inner = make_guard(c, self.tmp)
        write(g, "memo.md", COMPLIANT)
        self.edit(g, "memo.md", "2. EBITDA reconciliation discrepancy",
                  "2. EBITDA reconciliation discrepancy\n\n"
                  "3. Wyoming DEQ permit WY-HW-2019-033 expiry")
        out = bash(g, "pandoc memo.md -o output/red-flag-memo.docx")
        self.assertIn("raises as red flags is 1", c.actions[0])
        self.assertIn("cleared", out.lower())

    def test_unmirrorable_edit_drops_the_record_instead_of_guessing(self):
        c = FakeClient("SAT")
        g, inner = make_guard(c, self.tmp)
        write(g, "memo.md", COMPLIANT)
        self.edit(g, "memo.md", "text that is not in the source", "x")
        out = bash(g, "pandoc memo.md -o output/red-flag-memo.docx")
        self.assertEqual(c.actions, [], "stale text must not be testified")
        self.assertIn("never written through a channel", out)

    def test_edit_on_the_deliverable_is_not_pre_checked(self):
        """The fragment is not the document; _verify_artifacts reads the
        real result afterwards, so no pre-check (and no false testimony)
        is needed."""
        c = FakeClient("UNSAT")
        g, inner = make_guard(c, self.tmp)
        inner.sandbox.files[DELIVERABLE] = COMPLIANT.encode()
        out = self.edit(g, "output/red-flag-memo.docx", "x", "y")
        self.assertEqual(out, "OK: executed")
        self.assertEqual(len(inner.calls), 1, "the edit must execute")

    def test_edit_producing_a_bad_deliverable_is_still_reverted(self):
        """No pre-check does not mean no check: the artifact the edit
        actually produced is verified and reverted like any other route."""
        c = FakeClient("UNSAT")
        g, inner = make_guard(c, self.tmp,
                              writes={"edit": {DELIVERABLE: SHORT.encode()}})
        inner.sandbox.files[DELIVERABLE] = COMPLIANT.encode()
        out = self.edit(g, "output/red-flag-memo.docx", "a", "b")
        self.assertIn("was not kept", out)
        self.assertEqual(inner.sandbox.files[DELIVERABLE], COMPLIANT.encode(),
                         "the compliant version must be restored")


class TestConversionSpellings(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def test_quoted_paths_are_still_the_gate(self):
        c = FakeClient("SAT")
        g, inner = make_guard(c, self.tmp)
        write(g, "memo.md", COMPLIANT)
        bash(g, 'pandoc "memo.md" -o "output/red-flag-memo.docx"')
        self.assertEqual(len(c.actions), 1, "quoting must not skip the gate")

    def test_testimony_names_the_deliverable_not_the_command(self):
        c = FakeClient("SAT")
        g, inner = make_guard(c, self.tmp)
        write(g, "memo.md", COMPLIANT)
        bash(g, "pandoc memo.md -o output/red-flag-memo.docx")
        self.assertIn("red-flag-memo.docx", c.actions[0])
        self.assertNotIn("->", c.actions[0],
                         "the command belongs in the ledger, not in the "
                         "action string the solver reasons over")


class TestBareBlocks(unittest.TestCase):
    """The demo's control arm: the gate alone, no repair signal.

    Enforcement and the ledger are IDENTICAL to the explained mode — the
    solver rules on the same facts and the receipt records them in full.
    The only difference is what the agent is told.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def test_bare_block_does_not_name_the_defect(self):
        c = FakeClient("UNSAT")
        g, inner = make_guard(c, self.tmp, explain_blocks=False)
        write(g, "memo.md", SHORT)
        out = bash(g, "pandoc memo.md -o output/red-flag-memo.docx")
        self.assertIn("Blocked by firm drafting standard", out)
        self.assertNotIn("cleared for this engagement", out.lower(),
                         "bare mode must not name the missing element")
        self.assertNotIn("Wyoming", out)
        self.assertEqual(len(inner.calls), 1, "conversion must not run")

    def test_bare_mode_enforces_identically_and_reverts(self):
        c = FakeClient("UNSAT")
        g, inner = make_guard(c, self.tmp, explain_blocks=False,
                              writes={"bash": {DELIVERABLE: SHORT.encode()}})
        out = bash(g, "make memo")
        self.assertIn("was not kept", out)
        self.assertNotIn("cleared for this engagement", out.lower())
        self.assertNotIn(DELIVERABLE, inner.sandbox.files,
                         "bare mode must revert exactly like explained mode")

    def test_bare_mode_ledger_still_records_the_full_facts(self):
        """What changes is what the AGENT is told; the receipt does not
        get vaguer."""
        c = FakeClient("UNSAT")
        g, _ = make_guard(c, self.tmp, explain_blocks=False)
        write(g, "memo.md", SHORT)
        bash(g, "pandoc memo.md -o output/red-flag-memo.docx")
        self.assertIn("raises as red flags is 1", c.actions[0],
                      "the solver must still rule on the real count")
        entries = [json.loads(l) for l
                   in open(g.ledger.path, encoding="utf-8") if l.strip()]
        unsat = [e for e in entries if e["result"] == "UNSAT"]
        self.assertTrue(any("raises as red flags is 1" in e["action_text"]
                            for e in unsat))

    def test_explained_mode_is_the_default_and_names_the_defect(self):
        c = FakeClient("UNSAT")
        g, _ = make_guard(c, self.tmp)
        write(g, "memo.md", SHORT)
        out = bash(g, "pandoc memo.md -o output/red-flag-memo.docx")
        self.assertIn("Wyoming", out)
        self.assertIn("cleared for this engagement", out)


class TestDecideFailsClosed(unittest.TestCase):
    def test_garbage_verdict_blocks(self):
        blocked, verdict, note = DraftingGuard._decide(
            {"result": "PROBABLY_FINE", "z3_result": None, "detail": ""})
        self.assertTrue(blocked)
        self.assertEqual(verdict, "UNSAT")
        self.assertIn("fail-closed", note)

    def test_z3_overrides_a_disagreeing_combined_result(self):
        blocked, verdict, _ = DraftingGuard._decide(
            {"result": "SAT", "z3_result": "UNSAT", "detail": ""})
        self.assertTrue(blocked)
        self.assertEqual(verdict, "UNSAT")


class TestVerdictIsAlwaysRecorded(unittest.TestCase):
    """No run directory may lack a verdict.

    runH_r1 died on an Anthropic 400 (out of credits) and left a run with
    no final_state.json -- "silently absent", the one outcome the
    conforming-or-visible-refusal contract does not allow.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def test_every_state_writes_a_file_and_a_banner(self):
        for state in ("DELIVERED", "REFUSED", "ESCAPED"):
            with self.subTest(state=state):
                d = Path(tempfile.mkdtemp())
                runner.write_verdict(d, {"state": state, "detail": "x",
                                         "deliverable": "red-flag-memo.docx",
                                         "exec_summary_findings": 0})
                written = json.loads(
                    (d / "final_state.json").read_text())
                self.assertEqual(written["state"], state)

    def test_unknown_state_is_not_silently_accepted(self):
        with self.assertRaises(KeyError):
            runner.write_verdict(Path(tempfile.mkdtemp()),
                                 {"state": "PROBABLY_FINE", "detail": ""})
