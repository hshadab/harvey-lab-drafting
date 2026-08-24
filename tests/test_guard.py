"""Offline tests for DraftingGuard. No network, no API key, no credits.

The Preflight client and LAB's ToolExecutor are both faked, so this
exercises the real decision path — which writes are governed, what the
solver is told, what happens on UNSAT and on an outage — without spending
anything. Everything here would otherwise only be discovered mid-run at
~$13 and ~50 credits a go.
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

COMPLIANT = (
    "MEMORANDUM\n"
    "To: Sycamore Capital Partners\nFrom: Thornfield & Associates LLP\n"
    "Re: Project Ridgeline diligence red flags\n\n"
    "1. Environmental permit not transferred\n"
    + "The permit was never transferred to the buyer entity. " * 30 + "\n\n"
    "Items reviewed and cleared\n"
    + "The Wyoming renewal was filed timely and is not a red flag. " * 6)

# Long enough to be governed on its own — the guard only governs writes
# that are plausibly the memo, so test data must clear that bar or the
# test silently exercises the skip path instead of the block path.
NO_CLEARED = COMPLIANT.split("Items reviewed and cleared")[0]
assert len(NO_CLEARED) > 1200, "test draft too short to be governed"


class FakeInner:
    """Stands in for LAB's ToolExecutor."""
    def __init__(self):
        self.calls = []

    def execute(self, tool_name, arguments):
        self.calls.append((tool_name, arguments))
        return "OK: executed"

    def get_metrics(self):
        return {"files_read": 13}


class FakeClient:
    def __init__(self, verdict="SAT", raises=False):
        self.verdict, self.raises = verdict, False if not raises else True
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
        deliverable_names=["red-flag-memo.docx"], engagement=CONFIG,
        ledger_path=str(Path(tmp) / "ledger.jsonl"),
        max_retries=1, retry_wait_s=0))
    return g, inner


class TestGoverning(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def test_markdown_draft_is_governed_even_though_not_the_deliverable(self):
        """The memo is written as .md and converted to .docx afterwards, so
        governing only the deliverable filename would intercept nothing."""
        c = FakeClient("SAT")
        g, inner = make_guard(c, self.tmp)
        g.execute("write", json.dumps(
            {"file_path": "memo_content.md", "content": COMPLIANT}))
        self.assertEqual(len(c.actions), 1, "draft was not checked")

    def test_short_scratch_note_is_not_governed(self):
        c = FakeClient("SAT")
        g, inner = make_guard(c, self.tmp)
        g.execute("write", json.dumps(
            {"file_path": "notes.md", "content": "todo: read the CIM"}))
        self.assertEqual(c.actions, [], "scratch note should not be checked")
        self.assertEqual(len(inner.calls), 1, "scratch note should execute")

    def test_reads_and_bash_are_never_governed(self):
        c = FakeClient("SAT")
        g, inner = make_guard(c, self.tmp)
        g.execute("read", json.dumps({"file_path": "cim.docx"}))
        g.execute("bash", json.dumps({"command": "ls"}))
        self.assertEqual(c.actions, [])
        self.assertEqual(len(inner.calls), 2)


class TestEnforcement(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def test_unsat_blocks_the_write_and_explains_why(self):
        c = FakeClient("UNSAT")
        g, inner = make_guard(c, self.tmp)
        out = g.execute("write", json.dumps(
            {"file_path": "memo_content.md", "content": NO_CLEARED}))
        self.assertEqual(inner.calls, [], "blocked write must not execute")
        self.assertIn("cleared", out.lower())
        self.assertIn("drafting standards", out.lower())

    def test_sat_delegates_to_lab(self):
        c = FakeClient("SAT")
        g, inner = make_guard(c, self.tmp)
        out = g.execute("write", json.dumps(
            {"file_path": "memo_content.md", "content": COMPLIANT}))
        self.assertEqual(len(inner.calls), 1)
        self.assertEqual(out, "OK: executed")

    def test_outage_fails_closed(self):
        c = FakeClient(raises=True)
        g, inner = make_guard(c, self.tmp)
        out = g.execute("write", json.dumps(
            {"file_path": "memo_content.md", "content": COMPLIANT}))
        self.assertEqual(inner.calls, [], "must not execute during outage")
        self.assertIn("unavailable", out.lower())

    def test_action_text_states_only_computed_facts(self):
        """A draft with no cleared section must never be described as
        having one — the §6 lesson from the conduct demo."""
        c = FakeClient("SAT")
        g, _ = make_guard(c, self.tmp)
        g.execute("write", json.dumps(
            {"file_path": "memo_content.md", "content": NO_CLEARED}))
        self.assertIn("cleared-items sections the memorandum contains is 0",
                      c.actions[0])

    def test_ledger_records_every_decision(self):
        c = FakeClient("SAT")
        g, _ = make_guard(c, self.tmp)
        g.execute("read", json.dumps({"file_path": "x"}))
        g.execute("write", json.dumps(
            {"file_path": "memo_content.md", "content": COMPLIANT}))
        lines = [json.loads(l) for l in
                 open(Path(self.tmp) / "ledger.jsonl") if l.strip()]
        self.assertEqual([e["result"] for e in lines], ["SKIPPED", "SAT"])
        self.assertEqual(lines[1]["check_id"], "chk-1")


if __name__ == "__main__":
    unittest.main()
