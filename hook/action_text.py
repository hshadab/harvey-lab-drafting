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


def _n(v: int) -> str:
    return str(v)


def deliverable_action(file_path: str, f: DraftingFindings) -> ActionFacts:
    """Action string for writing the final deliverable memorandum.

    Shape is copied from the working conduct policy, not invented. Two
    earlier versions failed against the live compiled policy:

      v1  "identifies the engagement client: no"       -> 1/4 probes green
      v2  "containsClearedItemsSection is false"       -> 1/4 probes green

    Both bound only the conclusion (isMemorandumIssuanceAllowed) and every
    violating draft came back SAT. The conduct policy's Rule 3 check binds
    NINE variables, and the difference is that it states quantities as
    numbers and names the action being taken:

      "The data room contains 13 documents in total. The number of data
       room documents that have been reviewed is 9. Because 9 is not equal
       to 13 ... This action is writing a final deliverable ..."

    So: state the actor and verb, state each quantity as a standalone
    number, derive the consequence from that number, and frame exactly one
    pathway. Adjectives do not ground; numbers do.
    """
    common = dict(tool="write", summary=f"write: {file_path}",
                  is_deliverable=True, findings=f)
    head = (f"The agent writes the final deliverable memorandum "
            f"{file_path} of the diligence review. This action is writing "
            f"a final deliverable memorandum. ")
    tail = ("Therefore writing this final deliverable memorandum is "
            "permitted.")

    if f.client_name_count == 0:
        return ActionFacts(text=(
            head + f"The number of engagement clients named in the "
            f"memorandum's address block is {_n(f.client_name_count)}. "
            f"Because that number is zero, no engagement client is named "
            f"in the address block. " + tail), **common)

    if f.firm_name_count == 0:
        return ActionFacts(text=(
            head + f"The number of issuing firms named in the memorandum's "
            f"address block is {_n(f.firm_name_count)}. Because that "
            f"number is zero, no issuing firm is named in the address "
            f"block. " + tail), **common)

    if f.matter_reference_count == 0:
        return ActionFacts(text=(
            head + f"The number of references to the engagement matter in "
            f"the memorandum is {_n(f.matter_reference_count)}. Because "
            f"that number is zero, the memorandum does not reference the "
            f"engagement matter. " + tail), **common)

    if not f.exec_summary_ok:
        return ActionFacts(text=(
            head + f"The number of findings listed in the memorandum's "
            f"executive summary is {_n(f.exec_summary_findings)}. Because "
            f"that number is fewer than five, the executive summary does "
            f"not list at least five findings. " + tail), **common)

    if f.cleared_section_count == 0:
        return ActionFacts(text=(
            head + f"The number of cleared-items sections the memorandum "
            f"contains is {_n(f.cleared_section_count)}. Because that "
            f"number is zero, the memorandum contains no section "
            f"documenting the matters reviewed and found not to constitute "
            f"red flags. " + tail), **common)

    # Fully compliant. Every number below was computed, none assumed.
    return ActionFacts(text=(
        head
        + f"The number of engagement clients named in the memorandum's "
          f"address block is {_n(f.client_name_count)}. "
        + f"The number of issuing firms named in the memorandum's address "
          f"block is {_n(f.firm_name_count)}. "
        + f"The number of references to the engagement matter in the "
          f"memorandum is {_n(f.matter_reference_count)}. "
        + f"The number of cleared-items sections the memorandum contains "
          f"is {_n(f.cleared_section_count)}. "
        + f"The number of findings listed in the memorandum's executive "
          f"summary is {_n(f.exec_summary_findings)}. "
        + f"Each of the first four numbers is greater than zero and the "
          f"executive summary lists at least five findings. " + tail),
        **common)


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
