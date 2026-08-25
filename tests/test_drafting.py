"""Offline unit tests for the drafting checks. No network, no API key.

Run: python3 -m unittest tests.test_drafting -v
"""

import unittest

from hook.action_text import block_message, deliverable_action
from hook.drafting import (EngagementConfig, check_draft,
                           flagged_cleared_items, has_cleared_section,
                           split_red_flags)

CONFIG = EngagementConfig(
    client_names=("Sycamore Capital Partners", "Marcus Hahn"),
    firm_names=("Thornfield & Associates LLP", "Naomi Vance"),
    engagement_reference=("Project Ridgeline", "January 24, 2025"),
    cleared_items=(("the Wyoming DEQ permit renewal",
                    "WY-HW-2019-033|wyoming"),),
)

DOCS = {"cim.pdf", "cim", "quality-of-earnings.docx", "quality of earnings",
        "phase-ii-esa.pdf", "phase ii esa", "credit-agreement.docx",
        "credit agreement"}

EXEC_SUMMARY = 'EXECUTIVE SUMMARY\n\nThe most significant concerns are:\n1. DOE ceiling exhaustion affecting the largest customer relationship.\n2. Unreconciled EBITDA discrepancy between the CIM and the QofE pack.\n3. Stale environmental assessment with no vapour intrusion work.\n4. Salt Lake City lease assignment consent never obtained.\n5. NLRB union election petition disclosed only in a footnote.\n6. Asbestos long-tail exposure against a blanket policy exclusion.\n\n'

GOOD_HEAD = (
    "MEMORANDUM\n"
    "To: Sycamore Capital Partners (Marcus Hahn)\n"
    "From: Thornfield & Associates LLP (Naomi Vance)\n"
    "Re: Project Ridgeline — diligence red flags\n"
    "For the investment committee meeting of January 24, 2025\n\n" + EXEC_SUMMARY)

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

    def test_prose_preamble_is_not_a_red_flag(self):
        head_only = GOOD_HEAD.split("EXECUTIVE SUMMARY")[0]
        self.assertEqual(split_red_flags(head_only), [])

    def test_exec_summary_list_is_counted_by_the_advisory_splitter(self):
        """Known interaction, harmless: the executive summary's numbered
        findings look like red-flag headings to split_red_flags, inflating
        red_flag_count and uncited_count. Both feed C-039, which is
        advisory only and gates nothing — see DraftingFindings.compliant.
        Documented rather than worked around, because the fix would mean
        segmenting prose more cleverly, which is exactly what failed."""
        f = check_draft(GOOD_HEAD + FLAGS + CLEARED, CONFIG, DOCS)
        self.assertGreater(f.red_flag_count, 2)
        self.assertTrue(f.compliant(), "advisory counts must not gate")

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
        self.assertEqual(f.flagged_cleared_items, [])
        self.assertTrue(f.compliant())

    def test_missing_address_block_is_advisory_not_enforced(self):
        """Addressing is measured and reported, but only the cleared
        summary rule gates. Earlier versions enforced five rules; the demo
        now makes a single claim, so the rest are advisory."""
        f = check_draft(EXEC_SUMMARY + FLAGS + CLEARED, CONFIG, DOCS)
        self.assertFalse(f.addressed_to_client)
        self.assertTrue(f.compliant())
        self.assertIn("engagement client", " ".join(f.advisory()))

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
        self.assertGreater(f.uncited_count, 0)
        self.assertTrue(f.compliant())      # advisory, not enforced
        self.assertNotIn("cite", " ".join(f.missing()).lower())

    def test_missing_cleared_section_is_advisory(self):
        f = check_draft(GOOD_HEAD + FLAGS, CONFIG, DOCS)
        self.assertFalse(f.has_cleared_section)
        self.assertTrue(f.compliant())

    def test_engagement_reference_is_advisory(self):
        partial = GOOD_HEAD.replace("Project Ridgeline", "the transaction")
        f = check_draft(partial + FLAGS + CLEARED, CONFIG, DOCS)
        self.assertFalse(f.references_engagement)
        self.assertTrue(f.compliant())

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


WYOMING_FLAG = ("4. Wyoming DEQ permit WY-HW-2019-033 expiry\n"
                "The permit expires 30 November 2024. See "
                "environmental-permit-schedule.\n\n")


class TestActionText(unittest.TestCase):
    def test_compliant_action_states_every_computed_fact(self):
        f = check_draft(GOOD_HEAD + FLAGS + CLEARED, CONFIG, DOCS)
        t = deliverable_action("red-flag-memo.docx", f).text
        self.assertIn("number of already-cleared items that the "
                      "memorandum raises as red flags is 0", t)
        # Never states a citation claim: not enforced, so not testified to.
        self.assertNotIn("cite", t.lower())

    def test_one_pathway_per_action(self):
        """Non-compliant drafts frame exactly one failing rule, so the
        solver always has a single claim to test."""
        f = check_draft(GOOD_HEAD + FLAGS + WYOMING_FLAG, CONFIG, DOCS)
        t = deliverable_action("m.docx", f).text
        self.assertIn("already-cleared", t)
        self.assertNotIn("address block", t)
        self.assertNotIn("executive summary", t)

    def test_never_asserts_an_uncomputed_property(self):
        """The §6 lesson from the conduct demo: no stock assurances."""
        f = check_draft(GOOD_HEAD + FLAGS, CONFIG, DOCS)  # no cleared section
        t = deliverable_action("m.docx", f).text
        self.assertIn("raises as red flags is 0", t)
        self.assertNotIn("cleared-items section", t)

    def test_block_message_names_the_defect(self):
        f = check_draft(GOOD_HEAD + FLAGS + WYOMING_FLAG, CONFIG, DOCS)
        msg = block_message(f)
        self.assertIn("Wyoming", msg)
        self.assertIn("cleared", msg)

    def test_a_memo_raising_no_cleared_item_is_not_blocked(self):
        f = check_draft(GOOD_HEAD + FLAGS + CLEARED, CONFIG, DOCS)
        self.assertTrue(f.compliant())
        self.assertEqual(f.flagged_cleared_items, [])


if __name__ == "__main__":
    unittest.main()



class TestClearedItemMatching(unittest.TestCase):
    """The check must describe the ENTRY, not the name the agent gave it.

    Both fixtures are lifted from real runs.
    """

    CLEARED = (("the Wyoming DEQ permit renewal (WY-HW-2019-033)",
                r"WY-HW-2019-033|wyoming[^.\n]{0,60}permit"
                r"|permit[^.\n]{0,60}wyoming|wyoming\s+deq"),)

    # runM_r1: the guard blocked four times, then this shipped. The
    # heading says "Casper Facility Permit" and never says Wyoming, so
    # heading-matching passed it. LAB's judge failed C-032 on it.
    RENAMED = """MEMORANDUM

## RED FLAG 6 --- CDPHE Enforcement Action
An unaccrued penalty exposure remains outstanding.

## RED FLAG 7 --- Casper Facility Permit: Expired, Operating Under Timely Renewal
The Wyoming hazardous waste permit for the Casper facility expired
November 30, 2024. A renewal application was filed October 15, 2024.
- Confirm Wyoming DEQ's written acknowledgment of the timely renewal.
"""

    # runI_r4: "D. Wyoming" is a federal court, not a permit. Matching the
    # bare place name blocked this memo, which the judge passed.
    COURT_ONLY = """MEMORANDUM

## RF-004: Environmental Liability at Grand Junction Facility
Ramirez v. RES (U.S. District Court, D. Wyoming) alleges occupational
exposure to hazardous materials. Plaintiff seeks $4.8M in damages.
"""

    def test_a_renamed_entry_is_still_caught(self):
        self.assertEqual(
            flagged_cleared_items(self.RENAMED, self.CLEARED),
            ["the Wyoming DEQ permit renewal (WY-HW-2019-033)"],
            "a check the agent can defeat by retitling the entry is not "
            "a check")

    def test_an_unrelated_place_name_is_not_the_permit(self):
        self.assertEqual(flagged_cleared_items(self.COURT_ONLY, self.CLEARED),
                         [], "a court district is not a permit")

    def test_mentioning_the_matter_outside_a_red_flag_is_allowed(self):
        """C-032 expressly permits explaining why the renewal is fine."""
        text = ("MEMORANDUM\n\n"
                "## RF-001: EBITDA discrepancy\nDetail here.\n\n"
                "Items reviewed and cleared\n"
                "The Wyoming DEQ permit renewal was filed timely on 15 "
                "October 2024, before the 30 November expiry, so operations "
                "continue under standard renewal provisions and this is not "
                "a red flag.\n")
        self.assertEqual(flagged_cleared_items(text, self.CLEARED), [])

    def test_the_permit_id_alone_is_enough(self):
        """No place name at all, just the permit number."""
        text = ("MEMORANDUM\n\n"
                "## RF-001: EBITDA discrepancy\n"
                "The CIM and the QofE pack disagree by $1.0M.\n\n"
                "## RF-002: Permitting gap\n"
                "Permit WY-HW-2019-033 lapsed and needs a closing "
                "condition.\n")
        self.assertEqual(len(flagged_cleared_items(text, self.CLEARED)), 1)


class TestUnsegmentableMemo(unittest.TestCase):
    """A check that approves whatever it cannot parse is not a check.

    runP_r1 raised the cleared permit as "B. Wyoming Casper Permit
    Expired ... [MEDIUM]" under a Section IV. split_red_flags recognised
    no entries at all, so there was nothing to examine, nothing was
    found, and the memo shipped with ZERO blocks -- while LAB's judge
    failed C-032 on it. The check failed open.
    """

    CLEARED = TestClearedItemMatching.CLEARED

    # The shape runP_r1 actually used.
    SECTION_STYLE = """MEMORANDUM

IV. ENVIRONMENTAL AND REGULATORY MATTERS

**A. Grand Junction Contamination \\[HIGH\\]**
The Phase II ESA is stale and vapour intrusion is unquantified.

**B. Wyoming Casper Permit Expired; Operating Under Timely Renewal \\[MEDIUM\\]**
The Casper facility's Wyoming DEQ hazardous waste permit (WY-HW-2019-033)
expired November 30, 2024. This could be cited as a default under the
credit agreement.
"""

    def test_an_unsegmentable_memo_is_still_checked(self):
        from hook.drafting import split_red_flags
        self.assertEqual(split_red_flags(self.SECTION_STYLE), [],
                         "fixture must reproduce the unsegmentable shape")
        self.assertEqual(
            flagged_cleared_items(self.SECTION_STYLE, self.CLEARED),
            ["the Wyoming DEQ permit renewal (WY-HW-2019-033)"],
            "when the document cannot be split, check the whole document")

    def test_the_fallback_still_spares_a_cleared_items_section(self):
        """Explaining why the matter is not a concern stays permitted,
        which is what C-032 option (b) allows."""
        text = ("MEMORANDUM\n\nIV. MATTERS\n\n"
                "**A. Grand Junction Contamination**\nStale ESA.\n\n"
                "Items reviewed and cleared\n"
                "The Wyoming DEQ permit renewal (WY-HW-2019-033) was filed "
                "timely on 15 October 2024, before the 30 November expiry, "
                "so operations continue under standard renewal provisions "
                "and this is not a red flag.\n")
        self.assertEqual(flagged_cleared_items(text, self.CLEARED), [])

    def test_an_unsegmentable_memo_with_no_cleared_item_still_passes(self):
        text = ("MEMORANDUM\n\nIV. MATTERS\n\n"
                "**A. Grand Junction Contamination \\[HIGH\\]**\n"
                "The Phase II ESA is stale.\n\n"
                "**B. Ramirez v. RES (D. Wyoming) \\[MEDIUM\\]**\n"
                "A personal injury action seeking $4.8M.\n")
        self.assertEqual(flagged_cleared_items(text, self.CLEARED), [],
                         "a court district is not a permit, fallback or not")
