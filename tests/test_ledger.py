"""Offline tests for the receipt ledger. No network, no API key."""

import json
import tempfile
import unittest
from pathlib import Path

from hook.ledger import Ledger, load_entries, render_markdown


class TestLedger(unittest.TestCase):
    def setUp(self):
        self.path = Path(tempfile.mkdtemp()) / "ledger.jsonl"

    def _record(self, ledger, **over):
        base = dict(tool="write", summary="write: memo.md",
                    action_text="write: memo.md", result="SKIPPED")
        base.update(over)
        return ledger.record(**base)

    def test_reusing_a_run_id_truncates_rather_than_merging(self):
        """Append mode silently merged two runs into one receipt trail
        (observed 2026-08-17: 47 stale entries plus 6 new, with duplicate
        seq numbers). A fresh Ledger must start a fresh file."""
        first = Ledger(self.path)
        self._record(first)
        self._record(first)
        first.close()
        second = Ledger(self.path)
        self._record(second, summary="write: other.md")
        second.close()
        entries = load_entries(self.path)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["seq"], 1)

    def test_append_mode_resumes_deliberately(self):
        first = Ledger(self.path)
        self._record(first)
        first.close()
        resumed = Ledger(self.path, append=True)
        self._record(resumed)
        resumed.close()
        self.assertEqual(len(load_entries(self.path)), 2)

    def test_entries_are_flushed_as_written(self):
        """Crash-safety: the JSONL must be readable while the run is
        still going, not only after close()."""
        ledger = Ledger(self.path)
        self._record(ledger, result="UNSAT")
        entries = load_entries(self.path)   # ledger still open
        self.assertEqual(entries[0]["result"], "UNSAT")
        ledger.close()

    def test_consolidate_totals_match_entries(self):
        ledger = Ledger(self.path)
        self._record(ledger, result="SAT")
        self._record(ledger, result="SAT")
        self._record(ledger, result="UNSAT")
        out = self.path.parent / "ledger.json"
        ledger.consolidate(out)
        ledger.close()
        data = json.loads(out.read_text())
        self.assertEqual(data["totals"], {"SAT": 2, "UNSAT": 1})
        self.assertEqual(len(data["entries"]), 3)

    def test_markdown_escapes_pipes_and_truncates(self):
        ledger = Ledger(self.path)
        e = self._record(ledger, summary="bash: a | b " + "x" * 100)
        ledger.close()
        md = render_markdown([e])
        self.assertIn("a \\| b", md)
        self.assertIn("…", md)
        # The table must still parse as one row per entry.
        rows = [l for l in md.splitlines() if l.startswith("| 1 |")]
        self.assertEqual(len(rows), 1)


if __name__ == "__main__":
    unittest.main()
