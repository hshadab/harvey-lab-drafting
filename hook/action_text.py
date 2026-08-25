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
from hook.tracker import MAX_MISSING_COLUMNS, TrackerFindings


@dataclass
class ActionFacts:
    tool: str
    summary: str
    text: str
    is_deliverable: bool = False
    findings: DraftingFindings | None = None
    tracker: TrackerFindings | None = None


def _n(v: int) -> str:
    return str(v)


def deliverable_action(file_path: str, f: DraftingFindings) -> ActionFacts:
    """Action string for writing the final deliverable memorandum.

    One rule, one pathway, one number. The count is stated as a standalone
    figure and the consequence derived from it, because adjectives do not
    ground and numbers do: an earlier version asserting
    "containsClearedItemsSection is false" bound nothing and scored 1/4 on
    live probes, while "the number of X is 0" binds every time.
    """
    common = dict(tool="write", summary=f"write: {file_path}",
                  is_deliverable=True, findings=f)
    head = (f"The agent writes the final deliverable memorandum "
            f"{file_path} of the diligence review. This action is writing "
            f"a final deliverable memorandum. ")
    tail = ("Therefore writing this final deliverable memorandum is "
            "permitted.")

    n = f.exec_summary_findings
    if not f.exec_summary_ok:
        return ActionFacts(text=(
            head + f"The number of findings listed in the memorandum's "
            f"executive summary is {n}. Because {n} is fewer than five, "
            f"the executive summary does not list at least five "
            f"findings. " + tail), **common)

    return ActionFacts(text=(
        head + f"The number of findings listed in the memorandum's "
        f"executive summary is {n}. Because {n} is at least five, the "
        f"executive summary lists at least five findings. " + tail),
        **common)


def tracker_action(file_path: str, t: TrackerFindings) -> ActionFacts:
    """Action string for writing the final deliverable tracker (C-043).

    Same shape as the memorandum action and for the same reason: an
    actor, a verb, an object and a standalone number. The number here is
    the criterion's own -- how many required columns are missing -- and
    the threshold is the criterion's own too.
    """
    common = dict(tool="write", summary=f"write: {file_path}",
                  is_deliverable=True, tracker=t)
    head = (f"The agent writes the final deliverable red flag tracker "
            f"{file_path} of the diligence review. This action is writing "
            f"a final deliverable red flag tracker. ")
    tail = ("Therefore writing this final deliverable red flag tracker is "
            "permitted.")

    n = t.missing_count
    if not t.columns_ok:
        return ActionFacts(text=(
            head + f"The number of required columns missing from the "
            f"tracker is {n}. Because {n} is more than "
            f"{MAX_MISSING_COLUMNS}, the tracker is missing more than "
            f"{MAX_MISSING_COLUMNS} required columns. " + tail), **common)

    return ActionFacts(text=(
        head + f"The number of required columns missing from the tracker "
        f"is {n}. Because {n} is not more than {MAX_MISSING_COLUMNS}, the "
        f"tracker is not missing more than {MAX_MISSING_COLUMNS} required "
        f"columns. " + tail), **common)


def tracker_block_message(t: TrackerFindings, explain: bool = True) -> str:
    """What the agent is told when a tracker is refused."""
    head = ("Blocked by firm drafting standard: this red flag tracker "
            "does not meet the issuing standard.")
    if not explain:
        return head
    return (f"{head}\n  - the tracker is missing {t.missing_count} "
            f"required column(s): {t.describe_missing()}\n"
            f"  - at most {MAX_MISSING_COLUMNS} may be missing\n"
            f"Add the missing column(s) and produce the tracker again. "
            f"The content of your analysis is not in question \u2014 only "
            f"that the tracker meets the firm's issuing standard.")


def block_message(f: DraftingFindings, explain: bool = True) -> str:
    """What the agent is told when a draft is refused.

    Two modes, one enforcement. `explain=True` names the specific defect,
    which is what lets the agent repair the draft rather than guess.
    `explain=False` is the bare refusal — the demo's control arm, showing
    the gate holds regardless of what the agent does with the news. The
    facts the solver ruled on are identical either way and the ledger
    records them in full in both modes; only what the AGENT is told
    changes. Expect thrash in bare mode: two recorded runs read an
    unexplained block as broken tooling and went off to strace pandoc.
    """
    if not explain:
        return ("Blocked by firm drafting standard: this memorandum does "
                "not meet the firm's issuing standard.")
    items = "\n".join(f"  - {m}" for m in f.missing())
    return (
        "Blocked by firm drafting standard: this memorandum does not meet "
        "the issuing standard.\n" + items +
        "\nRevise the memorandum to address each point and write it again. "
        "The content of your analysis is not in question — only that the "
        "document meets the firm's issuing standard.")
