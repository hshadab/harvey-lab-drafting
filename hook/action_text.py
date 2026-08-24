"""Per-action strings for the drafting-standards policy.

The action string is testimony. Every sentence in it is a fact the solver
relies on and the proof bakes in, so this module states only what
hook/drafting.py actually computed — never a stock assurance.

That rule was learned the hard way in the conduct demo
(harvey-lab-preflight, BATTLE-TEST-FINDINGS §6): a template asserted "this
action reproduces no privileged material" as boilerplate, without ever
checking, and the solver ruled correctly on false testimony while the
agent walked a privileged quote through a shell heredoc. Preflight was not
wrong; the hook lied to it.

Style notes that matter for extraction, carried over from that build:
  * State each variable a rule needs as its own standalone sentence. A
    compressed phrase ("all 3 flags cite sources") packs two facts into
    one and the extractor may bind neither.
  * Frame ONE pathway per action. The compiled rules are implications, so
    a kitchen-sink string leaves the solver nothing to test.
"""

from __future__ import annotations

from dataclasses import dataclass

from hook.drafting import DraftingFindings


@dataclass
class ActionFacts:
    tool: str
    summary: str
    text: str
    is_deliverable: bool = False
    findings: DraftingFindings | None = None


def _addressing_sentences(f: DraftingFindings) -> str:
    return (
        f"The memorandum's address block identifies the engagement client: "
        f"{'yes' if f.addressed_to_client else 'no'}. "
        f"The memorandum's address block identifies the issuing firm: "
        f"{'yes' if f.addressed_from_firm else 'no'}. "
        f"The memorandum references the engagement matter: "
        f"{'yes' if f.references_engagement else 'no'}. ")


def _cleared_sentence(f: DraftingFindings) -> str:
    return (
        f"The memorandum contains a section documenting items reviewed and "
        f"cleared: {'yes' if f.has_cleared_section else 'no'}. ")


def deliverable_action(file_path: str, f: DraftingFindings) -> ActionFacts:
    """Action string for writing the final deliverable memorandum.

    Exactly one rule pathway is framed per call, in fixed precedence, so
    the solver always has a single claim to test. Precedence is by how
    mechanical the fix is: addressing first (one line to add), then the
    cleared section, then citations (needs work per flag).
    """
    common = dict(tool="write", summary=f"write: {file_path}",
                  is_deliverable=True, findings=f)
    head = (f"The agent issues {file_path}, the final deliverable "
            f"memorandum of the diligence review. ")

    if not f.addressed_ok:
        text = (head + _addressing_sentences(f)
                + "Therefore issuing this final deliverable memorandum is "
                  "permitted.")
        return ActionFacts(text=text, **common)

    if not f.has_cleared_section:
        text = (head + _cleared_sentence(f)
                + "Therefore issuing this final deliverable memorandum is "
                  "permitted.")
        return ActionFacts(text=text, **common)

    # Fully compliant. Every fact below was computed, none assumed.
    text = (
        head
        + _addressing_sentences(f)
        + _cleared_sentence(f)
        + "Therefore issuing this final deliverable memorandum is permitted.")
    return ActionFacts(text=text, **common)


def block_message(f: DraftingFindings) -> str:
    """What the agent is told when a draft is refused. Naming the specific
    defect is what lets it repair the draft rather than guess; a bare
    refusal produces thrash."""
    items = "\n".join(f"  - {m}" for m in f.missing())
    return (
        "Blocked by firm drafting standards: this memorandum does not meet "
        "the issuing standard.\n" + items +
        "\nRevise the memorandum to address each point and write it again. "
        "The content of your analysis is not in question — only that the "
        "document meets the firm's issuing standard.")
