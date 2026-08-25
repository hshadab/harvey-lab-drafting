"""C-043 is enforced verbatim, so the tests check the criterion's own
words: eight named columns, "FAIL if more than two are missing".
"""

import unittest

from hook.action_text import tracker_action, tracker_block_message
from hook.tracker import (MAX_MISSING_COLUMNS, REQUIRED_COLUMNS,
                          check_tracker, missing_columns)

# How LAB actually presents a tracker: `parse-doc xlsx` runs pandas
# read_excel + to_string, and real trackers carry title rows above the
# headers, so pandas takes the TITLE as the header and the real header
# row arrives as data.
WITH_TITLE_ROWS = """=== Sheet: Red Flag Tracker ===
                PROJECT RIDGELINE - DUE DILIGENCE RED FLAG TRACKER  Unnamed: 1  Unnamed: 2
                Ridgeline Environmental Services, Inc.  NaN  NaN
                NaN  NaN  NaN
                ID  Category  Red Flag Description  Severity  Source Document(s)  Financial Exposure  Recommended Action  Status
                RF-01  Financial / QoE  EBITDA Discrepancy  HIGH  CIM Sec. VI.B  8000000  Reconcile  Open
"""

HEADERS_FIRST = """=== Sheet: Red Flags ===
 ID  Category  Red Flag Description  Financial Impact  Severity  Status  Recommended Action
 RF-001  Revenue  DOE contract concentration  $12.1M  CRITICAL  Active  Engage DOE
"""


def sheet(*headers):
    return ("=== Sheet: Red Flag Tracker ===\n "
            + "  ".join(headers) + "\n RF-01  x  y\n")


class TestColumnDetection(unittest.TestCase):
    def test_all_eight_present(self):
        self.assertEqual(missing_columns(WITH_TITLE_ROWS), [])

    def test_header_row_found_below_title_rows(self):
        """pandas puts the title in the header slot; the real header row
        arrives as data. Scoring every line finds it anyway."""
        self.assertTrue(check_tracker(WITH_TITLE_ROWS).columns_ok)

    def test_headers_on_the_first_row_also_work(self):
        missing = missing_columns(HEADERS_FIRST)
        self.assertNotIn("Severity", missing)
        self.assertNotIn("Status", missing)

    def test_the_judges_own_equivalences_are_accepted(self):
        """LAB's judge passed a tracker using exactly these headers."""
        text = sheet("RF #", "Category", "Red Flag Title", "Severity",
                     "Quantified Exposure / Impact", "Source Document(s)",
                     "Buyer Action Required", "Status")
        self.assertEqual(missing_columns(text), [])

    def test_an_empty_sheet_is_missing_everything(self):
        self.assertEqual(len(missing_columns("=== Sheet: Blank ===\n")),
                         len(REQUIRED_COLUMNS))


class TestTheThreshold(unittest.TestCase):
    """The criterion's number, not one chosen here: FAIL if MORE THAN
    two columns are missing."""

    def _drop(self, *drop):
        keep = {"Issue Number": "ID", "Risk Category": "Category",
                "Description": "Red Flag Description",
                "Severity": "Severity",
                "Estimated Financial Exposure": "Financial Exposure",
                "Source Document(s)": "Source Document(s)",
                "Recommended Action": "Recommended Action",
                "Status": "Status"}
        for d in drop:
            keep.pop(d)
        return check_tracker(sheet(*keep.values()))

    def test_none_missing_passes(self):
        self.assertTrue(self._drop().columns_ok)

    def test_exactly_two_missing_passes(self):
        t = self._drop("Status", "Source Document(s)")
        self.assertEqual(t.missing_count, 2)
        self.assertTrue(t.columns_ok, "the criterion fails only at MORE "
                                      "than two")

    def test_three_missing_is_refused(self):
        t = self._drop("Status", "Source Document(s)", "Severity")
        self.assertEqual(t.missing_count, 3)
        self.assertFalse(t.columns_ok)

    def test_threshold_is_the_criterions_own(self):
        self.assertEqual(MAX_MISSING_COLUMNS, 2)


class TestTrackerTestimony(unittest.TestCase):
    """The action string states only what was computed, as a standalone
    number — the discipline Rule 1 needed to compile at all."""

    def test_permitted_action_states_the_count(self):
        t = check_tracker(WITH_TITLE_ROWS)
        facts = tracker_action("red-flag-tracker.xlsx", t)
        self.assertIn("The number of required columns missing from the "
                      "tracker is 0.", facts.text)
        self.assertIn("is not more than 2", facts.text)
        self.assertIn("permitted", facts.text)

    def test_refused_action_states_the_count(self):
        t = check_tracker(sheet("ID", "Category", "Description"))
        facts = tracker_action("red-flag-tracker.xlsx", t)
        self.assertIn(f"missing from the tracker is {t.missing_count}.",
                      facts.text)
        self.assertIn("is more than 2", facts.text)

    def test_testimony_never_mentions_an_executive_summary(self):
        t = check_tracker(WITH_TITLE_ROWS)
        text = tracker_action("red-flag-tracker.xlsx", t).text
        self.assertNotIn("executive summary", text.lower())

    def test_block_message_names_the_missing_columns(self):
        t = check_tracker(sheet("ID", "Category", "Description"))
        msg = tracker_block_message(t)
        self.assertIn("Severity", msg)
        self.assertIn("Status", msg)

    def test_bare_block_withholds_the_reason(self):
        t = check_tracker(sheet("ID"))
        msg = tracker_block_message(t, explain=False)
        self.assertNotIn("Severity", msg)
        self.assertIn("does not meet the issuing standard", msg)


if __name__ == "__main__":
    unittest.main()
