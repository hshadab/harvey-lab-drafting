"""Offline unit tests for the drafting checks. No network, no API key.

Run: python3 -m unittest tests.test_drafting -v
"""

import unittest

from hook.action_text import block_message, deliverable_action
from hook.drafting import (EngagementConfig, check_draft,
                           exec_summary_findings, has_cleared_section,
                           split_red_flags)

CONFIG = EngagementConfig(
    client_names=("Sycamore Capital Partners", "Marcus Hahn"),
    firm_names=("Thornfield & Associates LLP", "Naomi Vance"),
    engagement_reference=("Project Ridgeline", "January 24, 2025"),
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


class TestExecSummary(unittest.TestCase):
    def test_five_listed_findings_satisfies_the_rule(self):
        f = check_draft(GOOD_HEAD + FLAGS + CLEARED, CONFIG, DOCS)
        self.assertGreaterEqual(f.exec_summary_findings, 5)
        self.assertTrue(f.exec_summary_ok)

    def test_three_findings_does_not(self):
        """runA listed exactly three and LAB failed it on C-036."""
        head = GOOD_HEAD.split("EXECUTIVE SUMMARY")[0] + (
            "EXECUTIVE SUMMARY\n\nThe three most critical issues are:\n"
            "1. DOE ceiling exhaustion.\n"
            "2. Unreconciled EBITDA discrepancy.\n"
            "3. Stale environmental assessment.\n\n")
        f = check_draft(head + FLAGS + CLEARED, CONFIG, DOCS)
        self.assertEqual(f.exec_summary_findings, 3)
        self.assertFalse(f.compliant())
        self.assertIn("executive summary", " ".join(f.missing()).lower())

    def test_separate_short_lists_do_not_add_up(self):
        """Summing lists across the section reached five on a memo whose
        own text said 'the three most critical issues' — and LAB failed
        it. Only a contiguous list counts."""
        split_lists = ("EXECUTIVE SUMMARY\n\nTop issues:\n1. a\n2. b\n3. c\n\n"
                       "Also noted:\n1. d\n2. e\n\n")
        head = GOOD_HEAD.split("EXECUTIVE SUMMARY")[0] + split_lists
        f = check_draft(head + FLAGS + CLEARED, CONFIG, DOCS)
        self.assertLess(f.exec_summary_findings, 5)


class TestCheckDraft(unittest.TestCase):
    def test_fully_compliant_draft_passes(self):
        f = check_draft(GOOD_HEAD + FLAGS + CLEARED, CONFIG, DOCS)
        self.assertTrue(f.addressed_ok)
        self.assertTrue(f.has_cleared_section)
        self.assertTrue(f.exec_summary_ok)
        self.assertTrue(f.compliant())

    def test_missing_address_block_is_advisory_not_enforced(self):
        """Addressing is measured and reported, but only the executive
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


class TestActionText(unittest.TestCase):
    def test_compliant_action_states_every_computed_fact(self):
        f = check_draft(GOOD_HEAD + FLAGS + CLEARED, CONFIG, DOCS)
        t = deliverable_action("red-flag-memo.docx", f).text
        self.assertIn("number of findings listed in the memorandum's "
                      "executive summary is", t)
        self.assertIn("at least five", t)
        # Never states a citation claim: not enforced, so not testified to.
        self.assertNotIn("cite", t.lower())

    def test_one_pathway_per_action(self):
        """Non-compliant drafts frame exactly one failing rule, so the
        solver always has a single claim to test."""
        f = check_draft(FLAGS, CONFIG, DOCS)
        t = deliverable_action("m.docx", f).text
        self.assertIn("executive summary", t)
        self.assertNotIn("address block", t)

    def test_never_asserts_an_uncomputed_property(self):
        """The §6 lesson from the conduct demo: no stock assurances."""
        f = check_draft(GOOD_HEAD + FLAGS, CONFIG, DOCS)  # no cleared section
        t = deliverable_action("m.docx", f).text
        self.assertIn("executive summary is 6", t)

    def test_block_message_names_the_defect(self):
        f = check_draft(FLAGS, CONFIG, DOCS)
        msg = block_message(f)
        self.assertIn("executive summary", msg)
        self.assertIn("at least 5", msg)


if __name__ == "__main__":
    unittest.main()


class TestWrappedListItems(unittest.TestCase):
    """The count must describe the DOCUMENT, not the parser's flags.

    LAB parses .docx with `pandoc -t markdown --wrap=none`. Drop that flag
    and pandoc wraps each item across indented continuation lines; the
    counter read those as prose and reported 3 findings for a summary
    listing 5. Enforcement was correct only because of a flag in someone
    else's code.
    """

    ITEMS = [
        "**DOE IDIQ Ceiling Exhaustion** --- the largest customer is "
        "projected to exhaust its contract ceiling.",
        "**EBITDA Overstatement** --- the CIM conflicts with the QoE "
        "data package by $1.0M.",
        "**Groundwater contamination** --- identified in the Phase II ESA.",
        "**Permit expiry** --- two permits lapse within nine months.",
        "**Wage-and-hour class action** --- pending in Utah state court.",
    ]

    def _summary(self, wrap_at=None):
        lines = ["## Executive Summary", "", "The five most critical:", ""]
        for i, item in enumerate(self.ITEMS, 1):
            if wrap_at is None:
                lines.append(f"{i}.  {item}")
            else:
                head, tail = item[:wrap_at], item[wrap_at:]
                lines.append(f"{i}.  {head}")
                lines.append(f"    {tail}")
        lines += ["", "## Detailed Findings", ""]
        return "\n".join(lines)

    def test_unwrapped_list_counts_five(self):
        self.assertEqual(exec_summary_findings(self._summary()), 5)

    def test_wrapped_list_counts_the_same_five(self):
        self.assertEqual(exec_summary_findings(self._summary(wrap_at=40)), 5,
                         "wrapping an item must not change how many "
                         "findings the summary lists")

    def test_prose_at_the_margin_still_ends_the_list(self):
        text = self._summary().replace(
            "## Detailed Findings",
            "These items are discussed below.\n\n1.  A later item.\n"
            "2.  Another later item.\n\n## Detailed Findings")
        self.assertEqual(exec_summary_findings(text), 5,
                         "a restarting list after prose is a new list")

    def test_bold_heading_is_recognised(self):
        """pandoc renders a .docx 'heading' that is really a bold
        paragraph as `**Executive Summary**` — python-docx-built memos
        produce this routinely. Missing it counted 0 findings and blocked
        a conforming memo."""
        text = ("MEMORANDUM\n\n**Executive Summary**\n\n"
                "1. a\n2. b\n3. c\n4. d\n5. e\n\nDetailed Findings\n")
        self.assertEqual(exec_summary_findings(text), 5)

    def test_underscore_and_numbered_bold_headings(self):
        for heading in ("__EXECUTIVE SUMMARY__", "**II. Executive Summary**",
                        "## **Executive Summary**", "## Executive Summary:"):
            text = (f"MEMORANDUM\n\n{heading}\n\n"
                    "1. a\n2. b\n3. c\n4. d\n5. e\n\nDetailed Findings\n")
            self.assertEqual(exec_summary_findings(text), 5, heading)

    def test_parenthesised_numbers_count(self):
        text = ("EXECUTIVE SUMMARY\n\n(1) a\n(2) b\n(3) c\n(4) d\n(5) e\n\n"
                "DETAILED FINDINGS\n")
        self.assertEqual(exec_summary_findings(text), 5)

    def test_no_executive_summary_counts_zero(self):
        self.assertEqual(
            exec_summary_findings("MEMO\n1. a\n2. b\n3. c\n4. d\n5. e\n"), 0)

    def test_bold_subheading_inside_summary_does_not_truncate(self):
        """A bold line inside the summary is a sub-label, not a section
        boundary; the list after it must still count."""
        text = ("## Executive Summary\n\n**Top Five Findings**\n\n"
                "1. a\n2. b\n3. c\n4. d\n5. e\n\n## Detailed Findings\n")
        self.assertEqual(exec_summary_findings(text), 5)

    def test_wrapped_prose_paragraph_is_not_a_finding(self):
        text = ("## Executive Summary\n\nWe identified fifteen (15) "
                "material red flags across six categories:\n"
                "    (1) Financial, (2) Environmental, (3) Commercial,\n"
                "    (4) Real Property, (5) Legal, (6) Human Capital.\n\n"
                "## Detailed Findings\n")
        self.assertLess(exec_summary_findings(text), 5,
                        "an inline count in prose is not an enumeration")


class TestCategoriesAreNotFindings(unittest.TestCase):
    """A bulleted risk category is not a finding.

    runI_r1's executive summary bulleted seven categories and numbered
    three findings. The guard counted seven and passed it; LAB's judge
    failed C-036, saying the summary "only calls out 3 as 'CRITICAL
    SEVERITY FLAGS'". Counting bullets made the mechanical rule stop
    implying the criterion it exists to imply.
    """

    RUNI_R1 = """# EXECUTIVE SUMMARY

Twenty (20) material red flags have been identified across the following risk categories:

• Revenue & Customer Concentration (3 flags)
• Debt & Financing (1 flag)
• Environmental & Regulatory (5 flags)
• Litigation & Claims (3 flags)
• Lease & Permit Issues (3 flags)
• Compensation & Labor (2 flags)
• Financial & Valuation (3 flags)

CRITICAL SEVERITY FLAGS (3):
1. DOE Contract Ceiling Exhaustion -- Potential $12.1M revenue decline
2. Debt Change-of-Control Prepayment -- $39.2M+ cash requirement
3. Salt Lake City Lease Assignment -- Risk of $16.2M revenue loss

# CRITICAL ISSUES REQUIRING IMMEDIATE ATTENTION
"""

    def test_seven_categories_and_three_findings_counts_three(self):
        self.assertEqual(exec_summary_findings(self.RUNI_R1), 3,
                         "categories must not be counted as findings")

    def test_that_memo_would_now_be_blocked(self):
        self.assertLess(exec_summary_findings(self.RUNI_R1), 5)

    def test_numbered_findings_still_count(self):
        text = ("# Executive Summary\n\n"
                "1. First finding.\n2. Second finding.\n3. Third finding.\n"
                "4. Fourth finding.\n5. Fifth finding.\n\n# Detail\n")
        self.assertEqual(exec_summary_findings(text), 5)

    def test_bullets_alone_never_satisfy_the_standard(self):
        text = ("# Executive Summary\n\n"
                + "".join(f"• Category {i}\n" for i in range(1, 9))
                + "\n# Detail\n")
        self.assertEqual(exec_summary_findings(text), 0)
