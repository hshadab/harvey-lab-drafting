"""Offline unit tests for the drafting checks. No network, no API key.

Run: python3 -m unittest tests.test_drafting -v
"""

import unittest

from hook.action_text import block_message, deliverable_action
from hook.drafting import (EngagementConfig, check_draft, has_cleared_section,
                           split_red_flags)

CONFIG = EngagementConfig(
    client_names=("Sycamore Capital Partners", "Marcus Hahn"),
    firm_names=("Thornfield & Associates LLP", "Naomi Vance"),
    engagement_reference=("Project Ridgeline", "January 24, 2025"),
)

DOCS = {"cim.pdf", "cim", "quality-of-earnings.docx", "quality of earnings",
        "phase-ii-esa.pdf", "phase ii esa", "credit-agreement.docx",
        "credit agreement"}

GOOD_HEAD = (
    "MEMORANDUM\n"
    "To: Sycamore Capital Partners (Marcus Hahn)\n"
    "From: Thornfield & Associates LLP (Naomi Vance)\n"
    "Re: Project Ridgeline — diligence red flags\n"
    "For the investment committee meeting of January 24, 2025\n\n")

FLAGS = (
    "1. Environmental permit not transferred\n"
    "The Phase II ESA describes an unresolved transfer. See phase-ii-esa.pdf.\n\n"
    "2. Prepayment premium omitted\n"
    "Per the credit-agreement.docx, a 1% premium applies.\n\n")

CLEARED = (
    "Items reviewed and cleared\n"
    "The Wyoming permit renewal was filed timely before expiry and permits "
    "continued operation under standard renewal practice, so it is not a red "
    "flag. Customer concentration was reviewed against the CIM and is within "
    "the range disclosed.\n")


class TestSplitting(unittest.TestCase):
    def test_numbered_and_tagged_headings_both_split(self):
        self.assertEqual(len(split_red_flags(FLAGS)), 2)
        tagged = "ISSUE_001: Something\nbody\n\nISSUE_002: Other\nbody\n"
        self.assertEqual(len(split_red_flags(tagged)), 2)

    def test_preamble_is_not_a_red_flag(self):
        self.assertEqual(split_red_flags(GOOD_HEAD), [])

    def test_cleared_section_is_not_counted_as_a_red_flag(self):
        # Otherwise the cleared section would need citations, punishing the
        # very section the standard asks for.
        text = FLAGS + "3. Items reviewed and cleared\n" + CLEARED
        headings = [h for h, _ in split_red_flags(text)]
        self.assertTrue(all("cleared" not in h.lower() for h in headings))


class TestClearedSection(unittest.TestCase):
    def test_detected_with_substance(self):
        self.assertTrue(has_cleared_section(CLEARED))

    def test_bare_heading_with_no_body_does_not_count(self):
        self.assertFalse(has_cleared_section("Items reviewed and cleared\n"))

    def test_alternative_wordings_accepted(self):
        for heading in ("Non-issues", "Not red flags", "No action required",
                        "Matters considered and cleared"):
            body = heading + "\n" + "x" * 200
            self.assertTrue(has_cleared_section(body), heading)


class TestCheckDraft(unittest.TestCase):
    def test_fully_compliant_draft_passes(self):
        f = check_draft(GOOD_HEAD + FLAGS + CLEARED, CONFIG, DOCS)
        self.assertTrue(f.addressed_ok)
        self.assertTrue(f.has_cleared_section)
        self.assertEqual(f.uncited_count, 0)
        self.assertTrue(f.compliant())

    def test_missing_address_block_detected(self):
        f = check_draft(FLAGS + CLEARED, CONFIG, DOCS)
        self.assertFalse(f.addressed_to_client)
        self.assertFalse(f.addressed_from_firm)
        self.assertFalse(f.compliant())

    def test_client_named_only_in_body_is_not_an_addressee(self):
        body = ("MEMORANDUM\n" + "filler\n" * 60
                + "Sycamore Capital Partners was mentioned late.\n")
        f = check_draft(body, CONFIG, DOCS)
        self.assertFalse(f.addressed_to_client)

    def test_uncited_red_flags_are_measured_but_not_enforced(self):
        """C-039 is measured as an advisory signal only. Our split of prose
        into discrete red flags disagreed with LAB's judge on 10 of 17 real
        memos, so it does not gate compliance — see drafting.compliant()."""
        text = GOOD_HEAD + FLAGS + "3. Undocumented worry\nNo source named.\n" + CLEARED
        f = check_draft(text, CONFIG, DOCS)
        self.assertEqual(f.uncited_count, 1)
        self.assertIn("Undocumented", f.uncited_red_flags[0])
        self.assertTrue(f.compliant())      # advisory, not enforced
        self.assertNotIn("cite", " ".join(f.missing()).lower())

    def test_missing_cleared_section_detected(self):
        f = check_draft(GOOD_HEAD + FLAGS, CONFIG, DOCS)
        self.assertFalse(f.has_cleared_section)
        self.assertFalse(f.compliant())

    def test_all_engagement_references_required(self):
        """C-045 needs both the matter and the IC meeting date. an any()
        test passed on the matter name alone and disagreed with the judge
        on 5 of 17 runs."""
        partial = GOOD_HEAD.replace("January 24, 2025", "some other date")
        f = check_draft(partial + FLAGS + CLEARED, CONFIG, DOCS)
        self.assertFalse(f.references_engagement)
        self.assertFalse(f.compliant())

    def test_no_answer_key_dependence(self):
        """A draft citing a real document passes citation checks even if its
        analysis is nonsense. We check that a source is cited, never that
        the right conclusion was reached — the line that keeps this from
        being the rubric's answer key."""
        wrong = (GOOD_HEAD
                 + "1. The sky is falling\nSee cim.pdf for details.\n\n"
                 + CLEARED)
        f = check_draft(wrong, CONFIG, DOCS)
        self.assertTrue(f.compliant())


class TestActionText(unittest.TestCase):
    def test_compliant_action_states_every_computed_fact(self):
        f = check_draft(GOOD_HEAD + FLAGS + CLEARED, CONFIG, DOCS)
        t = deliverable_action("red-flag-memo.docx", f).text
        for fragment in ("addressedToEngagementClient is true",
                         "identifiesIssuingFirm is true",
                         "referencesEngagementMatter is true",
                         "containsClearedItemsSection is true"):
            self.assertIn(fragment, t)
        # Never states a citation claim: not enforced, so not testified to.
        self.assertNotIn("cite", t.lower())

    def test_one_pathway_per_action(self):
        """Non-compliant drafts frame exactly one failing rule, so the
        solver always has a single claim to test."""
        f = check_draft(FLAGS, CONFIG, DOCS)   # fails addressing AND cleared
        t = deliverable_action("m.docx", f).text
        self.assertIn("address block", t)
        self.assertNotIn("items reviewed and cleared", t)

    def test_never_asserts_an_uncomputed_property(self):
        """The §6 lesson from the conduct demo: no stock assurances."""
        f = check_draft(GOOD_HEAD + FLAGS, CONFIG, DOCS)  # no cleared section
        t = deliverable_action("m.docx", f).text
        self.assertIn("containsClearedItemsSection is false", t)
        self.assertNotIn("ClearedItemsSection is true", t)

    def test_block_message_names_each_defect(self):
        f = check_draft(FLAGS, CONFIG, DOCS)
        msg = block_message(f)
        self.assertIn("engagement client", msg)
        self.assertIn("cleared", msg)


if __name__ == "__main__":
    unittest.main()
