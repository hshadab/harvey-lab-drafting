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


def _addr_client(f) -> str:
    if f.addressed_to_client:
        return ("The memorandum's address block identifies the engagement "
                "client by name; addressedToEngagementClient is "
                "true. ")
    return ("The memorandum's address block does not identify the "
            "engagement client by name; "
            "addressedToEngagementClient is false. ")


def _addr_firm(f) -> str:
    if f.addressed_from_firm:
        return ("The memorandum's address block identifies the issuing firm "
                "by name; identifiesIssuingFirm is true. ")
    return ("The memorandum's address block does not identify the issuing "
            "firm by name; identifiesIssuingFirm is false. ")


def _matter(f) -> str:
    if f.references_engagement:
        return ("The memorandum references the engagement matter; "
                "referencesEngagementMatter is true. ")
    return ("The memorandum does not reference the engagement matter; "
            "referencesEngagementMatter is false. ")


def _cleared(f) -> str:
    if f.has_cleared_section:
        return ("The memorandum contains a section documenting the items "
                "that were reviewed and cleared; "
                "containsClearedItemsSection is true. ")
    return ("The memorandum contains no section documenting the items that "
            "were reviewed and cleared; "
            "containsClearedItemsSection is false. ")


def deliverable_action(file_path: str, f: DraftingFindings) -> ActionFacts:
    """Action string for issuing the final deliverable memorandum.

    Framing follows the conduct demo's finding §3 the hard way. A first
    version stated facts as "identifies the engagement client: no" and the
    solver returned SAT on drafts that plainly violate the rules — the
    compiled rules are pure implications, so the base system is always
    satisfiable and a check only returns UNSAT when the string frames ONE
    pathway and binds the variable that pathway's rule tests. Live probes
    on the compiled policy: 3 of 3 correct after this rewrite, 1 of 3
    before it.

    So each fact is stated twice — once in plain language, once as a named
    boolean the extractor can bind — and exactly one failing pathway is
    framed per action.

    The names below are NOT invented: they are copied verbatim from the
    compiled policy's SMT (policy/compiled_policy.json, fetched from
    GET /v1/policy/<id>). A first attempt used descriptive names of our own
    (memorandumContainsClearedItemsSection and friends); the extractor
    bound none of them, returned only {"isMemorandumIssuanceAllowed": true},
    and every violating draft came back SAT — the base system is satisfiable
    when nothing constrains it. Read the compiled SMT and use its exact
    vocabulary; do not guess it.
    """
    common = dict(tool="write", summary=f"write: {file_path}",
                  is_deliverable=True, findings=f)
    head = (f"The agent issues {file_path}, the final deliverable "
            f"memorandum of the diligence review. This action is issuing a "
            f"final deliverable memorandum. ")
    tail = ("Therefore issuing this final deliverable memorandum is "
            "permitted.")

    if not f.addressed_to_client:
        return ActionFacts(text=head + _addr_client(f) + tail, **common)
    if not f.addressed_from_firm:
        return ActionFacts(text=head + _addr_firm(f) + tail, **common)
    if not f.references_engagement:
        return ActionFacts(text=head + _matter(f) + tail, **common)
    if not f.has_cleared_section:
        return ActionFacts(text=head + _cleared(f) + tail, **common)

    # Fully compliant. Every fact below was computed, none assumed.
    return ActionFacts(
        text=head + _addr_client(f) + _addr_firm(f) + _matter(f)
        + _cleared(f) + tail, **common)


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
