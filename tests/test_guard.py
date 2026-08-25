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
import tempfile
import unittest
from pathlib import Path

from hook.drafting import EngagementConfig
from hook.guard import DraftingGuard, GuardConfig
from hook.preflight_client import PreflightUnreachable

CONFIG = EngagementConfig(
    client_names=("Sycamore Capital Partners",),
    firm_names=("Thornfield & Associates LLP",),
    engagement_reference=("Project Ridgeline",),
)

FIVE = ("EXECUTIVE SUMMARY\n\nThe most significant concerns are:\n"
        "1. DOE ceiling exhaustion.\n2. Unreconciled EBITDA discrepancy.\n"
        "3. Stale environmental assessment.\n4. Lease consent never obtained.\n"
        "5. NLRB petition disclosed in a footnote.\n\n")
THREE = ("EXECUTIVE SUMMARY\n\nThe three most critical issues are:\n"
         "1. DOE ceiling exhaustion.\n2. Unreconciled EBITDA discrepancy.\n"
         "3. Stale environmental assessment.\n\n")

COMPLIANT = "MEMORANDUM\n\n" + FIVE + "1. Permit issue\n" + "detail. " * 200
SHORT = "MEMORANDUM\n\n" + THREE + "1. Permit issue\n" + "detail. " * 200

# The 50KB xlsx builder that runE_r1 refused eight times.
TRACKER_SCRIPT = ("cat > /tmp/build_tracker.py << 'PYEOF'\n"
                  "import openpyxl\n"
                  + "rows.append(('red flag', 'diligence finding'))\n" * 60
                  + "PYEOF")


class FakeInner:
    def __init__(self):
        self.calls = []

    def execute(self, tool_name, arguments):
        self.calls.append((tool_name, arguments))
        return "OK: executed"

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


def make_guard(client, tmp):
    inner = FakeInner()
    g = DraftingGuard(inner, client, GuardConfig(
        policy_id="pol-1", documents_dir=str(tmp),
        deliverable_names=["red-flag-memo.docx", "red-flag-tracker.xlsx"],
        engagement=CONFIG, ledger_path=str(Path(tmp) / "ledger.jsonl"),
        max_retries=1, retry_wait_s=0))
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
        self.assertIn("executive summary is 5", c.actions[0])
        self.assertEqual(len(inner.calls), 2)

    def test_conversion_from_short_source_is_blocked(self):
        c = FakeClient("UNSAT")
        g, inner = make_guard(c, self.tmp)
        write(g, "memo.md", SHORT)
        out = bash(g, "python generate_from_md.py memo.md "
                      "output/red-flag-memo.docx")
        self.assertEqual(len(inner.calls), 1, "only the source write ran")
        self.assertIn("executive summary", out.lower())
        self.assertIn("executive summary is 3", c.actions[0])

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
        self.assertIn("executive summary", out.lower())

    def test_writing_the_deliverable_directly_is_checked(self):
        c = FakeClient("UNSAT")
        g, inner = make_guard(c, self.tmp)
        out = write(g, "output/red-flag-memo.docx", SHORT)
        self.assertEqual(inner.calls, [])
        self.assertIn("executive summary", out.lower())


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
        self.assertIn("executive summary is 3", c.actions[0])
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
