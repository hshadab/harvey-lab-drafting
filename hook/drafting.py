"""Host-side drafting-standards checks.

These compute, from a draft deliverable, the facts the policy rules reason
over. Nothing here decides anything: the guard states these facts in the
action string and Preflight's solver rules on them. That separation is the
whole point — see BATTLE-TEST-FINDINGS in harvey-lab-preflight, where a
hook that *asserted* a property it had never computed let the agent walk
straight through Rule 2.

Design rule, and the one that keeps this honest:

    The RULE is generic. The ENGAGEMENT supplies the specifics.

"Every memo is addressed to the engagement client" is a firm drafting
standard. "Every memo is addressed to Sycamore Capital Partners" is an
answer key. This module only implements the former; who the client is
arrives as EngagementConfig, exactly as it would from a matter record in a
real deployment. The same applies to source citations: the list of
citeable documents is read off the data room, never hardcoded.

Anything that cannot be checked without knowing the right answer is out of
scope by construction. We check that each red flag cites *a* source, never
that it cites the *correct* source; that a cleared-items section exists,
never that it clears the right items.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

# A heading that opens a red-flag entry. LAB deliverables in practice use
# numbered issues ("1. Environmental permit"), explicit ISSUE_ tags, or
# markdown headings; accept all three rather than dictating a house format.
# Memos label red flags one of two ways. A *tagged* convention ("RF-01",
# "ISSUE_003", "Red Flag 2") is unambiguous. A *numbered* convention
# ("3. Title") is not — ordinary numbered lists inside a flag's body look
# identical to flag headings.
#
# So: detect which convention the document uses, then apply only that one.
# Applying both at once split runB_r5 into 42 "flags" when it contains 22,
# because each flag's numbered Required Action items were read as new
# flags — and those fragments carry no Source: line, so 20 fully-cited
# flags were scored uncited. Mixing conventions manufactures the very
# defect the rule is meant to detect.
_TAGGED_HEADING = re.compile(
    r"^[ \t]*(?:#{1,6}[ \t]*)?"
    r"(?:rf|issue|red\s*flag|finding|item)[\s_#|.-]*\d+",
    re.I | re.M,
)
_NUMBERED_HEADING = re.compile(
    r"^[ \t]*(?:#{1,6}[ \t]*)?\d{1,2}[.)][ \t]+\S[^\n]{0,110}$",
    re.I | re.M,
)
# Two or more tagged headings means the document has committed to that
# convention; one could be an accident of prose.
_TAGGED_MIN = 2


def _heading_re(text: str):
    """The heading convention this document actually uses."""
    if len(_TAGGED_HEADING.findall(text)) >= _TAGGED_MIN:
        return _TAGGED_HEADING
    return _NUMBERED_HEADING


# How a memo attributes a red flag to its evidence. Real LAB deliverables
# use an explicit "Source:" line per flag (22 flags, 22 Source: lines in
# runB_r5); accept the common variants rather than dictating one.
#
# Matching document names alone was tried first and was badly wrong: memos
# cite by human title and abbreviation ("QofE Data Package", "CIM"), not by
# filename, so a filename-derived dictionary scored 21 of 22 cited flags as
# uncited. Requiring a stated attribution is both more robust and a more
# honest standard — it checks that the drafter named a source, never that
# the source is the right one, which no drafting rule could know.
_ATTRIBUTION = re.compile(
    r"^[ \t]*(?:sources?|see|per|ref(?:erence)?|pursuant\s+to|citing)\b[ \t:]"
    r"|\b(?:source|sources)\s*:",
    re.I | re.M,
)


# Section headings that constitute a cleared / non-issue section. Broad on
# purpose: the standard is "you documented what you cleared", not "you used
# our preferred wording".
_CLEARED_HEADING = re.compile(
    r"^[ \t]*(?:#{1,6}[ \t]*)?(?:[IVX]+\.[ \t]*|\d+[.)][ \t]*)?[^\n]{0,60}?\b("
    r"cleared|not\s+(?:a\s+)?red\s+flags?|non[-\s]?issues?|no\s+action\s+required"
    r"|items?\s+reviewed\s+(?:and|&)\s+cleared|adequately\s+addressed"
    r"|considered\s+and\s+(?:cleared|dismissed)|false\s+positives?"
    r")\b[^\n]{0,40}$",
    re.I | re.M,
)

# A cleared section that is a bare heading with nothing under it does not
# satisfy the standard; require some prose beneath it.
_MIN_CLEARED_CHARS = 120

_EXEC_SUMMARY_HEADING = re.compile(
    r"^[ \t]*(?:#{1,6}[ \t]*)?(?:[IVX]+\.[ \t]*|\d+[.)][ \t]*)?"
    r"executive\s+summary[^\n]{0,40}$", re.I | re.M)

# An enumerated finding inside the executive summary: a bullet or a
# numbered item.
_ENUMERATED_ITEM = re.compile(r"^[ \t]*(?:[-*\u2022]|\(?\d+[.)])[ \t]+\S", re.M)

# Harvey's C-036 asks that the executive summary "specifically highlights
# at least 5 of the most critical findings". That test is semantic and we
# could not reproduce it: across 18 memos the judge passed a summary
# naming four themes and failed one naming five concrete items.
# Attempting to replicate a fuzzy judge is how C-039 went wrong.
#
# So this enforces a STRICTER, mechanical standard that IMPLIES the
# criterion rather than mirroring it: the executive summary must
# enumerate at least five findings as a list. Evidence that the
# implication holds: of the 18 recorded memos, the four whose executive
# summaries enumerate >=5 items pass C-036 4 times out of 4, while the
# fourteen that do not are a coin flip (7 pass, 7 fail).
#
# A firm's house style is allowed to be more specific than a rubric. What
# it may not be is unverifiable.
_MIN_EXEC_SUMMARY_FINDINGS = 5

# The next section heading after the executive summary.
_SECTION_BOUNDARY = re.compile(
    r"^[ \t]*(?:"
    r"#{1,6}[ \t]*\S"                              # markdown heading
    r"|[IVX]{1,5}\.[ \t]*[A-Z]"                     # "II. RED FLAGS"
    r"|[A-Z][A-Z0-9 ,&/()'\u2014-]{8,70}$"           # bare CAPS heading
    r")", re.M)

# Belt and braces: even with no boundary found, never scan past this.
_EXEC_SUMMARY_MAX_CHARS = 4000


@dataclass(frozen=True)
class EngagementConfig:
    """Matter-specific facts. In a real deployment these come from the
    matter record; here they come from a config file, never from the
    grading rubric."""
    client_names: tuple[str, ...]
    firm_names: tuple[str, ...]
    engagement_reference: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, d: dict) -> "EngagementConfig":
        return cls(
            client_names=tuple(d.get("client_names", ())),
            firm_names=tuple(d.get("firm_names", ())),
            engagement_reference=tuple(d.get("engagement_reference", ())),
        )


@dataclass
class DraftingFindings:
    addressed_to_client: bool
    addressed_from_firm: bool
    references_engagement: bool
    has_cleared_section: bool
    red_flag_count: int
    uncited_red_flags: list[str] = field(default_factory=list)
    # Counts, not adjectives. The compiled policy reasons over quantities
    # ("...when the number of cleared-items sections is zero"), and the
    # extractor grounds numbers far more reliably than predicates — the
    # working conduct policy binds totalDataRoomDocuments and
    # reviewedDataRoomDocuments, never the boolean derived from them.
    cleared_section_count: int = 0
    exec_summary_findings: int = 0
    client_name_count: int = 0
    firm_name_count: int = 0
    matter_reference_count: int = 0

    @property
    def uncited_count(self) -> int:
        return len(self.uncited_red_flags)

    @property
    def addressed_ok(self) -> bool:
        return (self.addressed_to_client and self.addressed_from_firm
                and self.references_engagement)

    def compliant(self) -> bool:
        """Enforced standards only.

        uncited_red_flags is measured but deliberately NOT enforced: the
        underlying criterion (LAB C-039) needs a reliable split of free
        prose into discrete red flags, and ours disagreed with LAB's judge
        on 10 of 17 real memos. Enforcing a check that does not reproduce
        the standard it claims to enforce would be the exact failure this
        project exists to avoid. Kept as an advisory signal only.
        """
        return (self.addressed_ok and self.has_cleared_section
                and self.exec_summary_ok)

    @property
    def exec_summary_ok(self) -> bool:
        return self.exec_summary_findings >= _MIN_EXEC_SUMMARY_FINDINGS

    def missing(self) -> list[str]:
        """Human-readable list of what fails, for the block message the
        agent receives. Being specific here is what lets it fix the draft
        instead of guessing."""
        out = []
        if not self.addressed_to_client:
            out.append("no addressee identifying the engagement client")
        if not self.addressed_from_firm:
            out.append("no sender identifying the engagement firm")
        if not self.references_engagement:
            out.append("no reference to the engagement or its meeting date")
        if not self.has_cleared_section:
            out.append("no section documenting items reviewed and cleared")
        if not self.exec_summary_ok:
            out.append(
                f"the executive summary enumerates {self.exec_summary_findings} "
                f"finding(s); at least {_MIN_EXEC_SUMMARY_FINDINGS} must be "
                f"listed")
        return out


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def citeable_names(documents_dir: str | Path) -> set[str]:
    """Every token by which a data-room document could legitimately be
    cited: its filename, its stem, and the stem's word forms. Read off the
    data room, so this generalises to any matter."""
    names: set[str] = set()
    d = Path(documents_dir)
    if not d.exists():
        return names
    for p in sorted(d.iterdir()):
        if not p.is_file():
            continue
        names.add(p.name.lower())
        stem = p.stem.lower()
        names.add(stem)
        names.add(stem.replace("-", " ").replace("_", " "))
    return {n for n in names if len(n) >= 4}


def split_red_flags(text: str) -> list[tuple[str, str]]:
    """Split a draft into (heading, body) per red-flag entry.

    Everything before the first heading is preamble and is not a red flag.
    A section whose heading matches the cleared-items pattern is excluded:
    cleared items are by definition not red flags, and requiring them to
    cite sources would punish the very section Rule 2 asks for.
    """
    # A block ends at the next heading of EITHER kind. Ending only at the
    # next red-flag heading let the final flag absorb the cleared-items
    # section that followed it; because that section cites documents, an
    # uncited flag was scored as cited. Cleared headings are boundaries
    # even though they are not themselves red flags.
    flag_re = _heading_re(text)
    bounds = sorted(
        [(m.start(), "flag") for m in flag_re.finditer(text)]
        + [(m.start(), "cleared") for m in _CLEARED_HEADING.finditer(text)]
    )
    out: list[tuple[str, str]] = []
    for i, (start, kind) in enumerate(bounds):
        end = bounds[i + 1][0] if i + 1 < len(bounds) else len(text)
        block = text[start:end]
        heading = block.splitlines()[0].strip() if block.strip() else ""
        # Skip cleared sections, and any flag heading that is itself a
        # cleared heading ("3. Items reviewed and cleared").
        if kind == "cleared" or _CLEARED_HEADING.match(heading):
            continue
        out.append((heading, block))
    return out


def exec_summary_findings(text: str) -> int:
    """Count enumerated findings inside the executive summary section."""
    m = _EXEC_SUMMARY_HEADING.search(text)
    if not m:
        return 0
    body = text[m.end():]
    # End the section at the next heading. Memos vary: some use roman
    # numerals ("II. RED FLAGS BY CATEGORY"), some markdown, some a bare
    # capitalised line. Missing the boundary is not a small error — it
    # counted enumerated items through the whole document and reported 27
    # findings for a summary containing 6.
    end = _SECTION_BOUNDARY.search(body)
    if end:
        body = body[:end.start()]
    body = body[:_EXEC_SUMMARY_MAX_CHARS]
    # Longest CONTIGUOUS run of enumerated lines, not the total across the
    # section. runA's summary says "the three most critical issues are"
    # and lists three; summing separate lists reached five and would have
    # passed a memo the judge failed. The standard is "a list of at least
    # five findings", so a list is what gets measured.
    # A numbered list runs 1,2,3,... A section that restarts at 1 is a new
    # list, not a continuation: without this, the executive summary's three
    # items ran straight into the next section's "1." and counted four.
    best = run = 0
    prev_num = None
    for line in body.splitlines():
        m = _ENUMERATED_ITEM.match(line)
        if m:
            num = re.match(r"^[ \t]*\(?(\d+)[.)]", line)
            if num:
                n = int(num.group(1))
                run = run + 1 if (prev_num is not None and n == prev_num + 1) else 1
                prev_num = n
            else:                    # bullets: contiguity is enough
                run += 1
                prev_num = None
            best = max(best, run)
        elif line.strip():           # prose breaks the list
            run, prev_num = 0, None
    return best


def _cleared_section_count(text: str) -> int:
    """How many cleared-items sections the document contains (with
    substance, not a bare heading)."""
    n = 0
    for m in _CLEARED_HEADING.finditer(text):
        body = text[m.end():]
        nxt = _heading_re(text).search(body)
        if nxt:
            body = body[:nxt.start()]
        if len(body.strip()) >= _MIN_CLEARED_CHARS:
            n += 1
    return n


def has_cleared_section(text: str) -> bool:
    return _cleared_section_count(text) > 0


def check_draft(text: str, config: EngagementConfig,
                doc_names: set[str]) -> DraftingFindings:
    """Compute every drafting fact the policy needs. Pure function: no
    network, no policy decision, no side effects."""
    low = _norm(text)
    # Only the top of the document counts as the address block; a client
    # name appearing in body prose is not an addressee.
    head = _norm("\n".join(text.splitlines()[:40]))

    addressed_to_client = any(_norm(n) in head for n in config.client_names)
    addressed_from_firm = any(_norm(n) in head for n in config.firm_names)
    # ALL configured references must appear, not any. The judge's C-045
    # requires both the matter and the investment-committee meeting date;
    # an any() test passed on the matter name alone and disagreed with the
    # judge on 5 of 17 runs.
    references_engagement = all(
        _norm(r) in low for r in config.engagement_reference)

    uncited: list[str] = []
    flags = split_red_flags(text)
    for heading, block in flags:
        blow = _norm(block)
        cited = bool(_ATTRIBUTION.search(block)) or any(
            n in blow for n in doc_names)
        if not cited:
            uncited.append(heading[:70])

    cleared_n = _cleared_section_count(text)
    return DraftingFindings(
        addressed_to_client=addressed_to_client,
        addressed_from_firm=addressed_from_firm,
        references_engagement=references_engagement,
        has_cleared_section=cleared_n > 0,
        red_flag_count=len(flags),
        uncited_red_flags=uncited,
        cleared_section_count=cleared_n,
        exec_summary_findings=exec_summary_findings(text),
        client_name_count=sum(1 for n in config.client_names
                              if _norm(n) in head),
        firm_name_count=sum(1 for n in config.firm_names
                            if _norm(n) in head),
        matter_reference_count=sum(1 for r in config.engagement_reference
                                   if _norm(r) in low),
    )
