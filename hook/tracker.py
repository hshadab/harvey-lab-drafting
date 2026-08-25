"""Column-structure check for the red flag tracker (LAB C-043).

This rule is enforced VERBATIM. Unlike the executive-summary rule, which
is a deliberately stricter mechanical stand-in for a semantic criterion,
C-043 states its own list and its own threshold:

    PASS if the tracker spreadsheet includes columns for: Issue Number,
    Risk Category, Description, Severity, Estimated Financial Exposure,
    Source Document(s), Recommended Action, and Status (or substantially
    equivalent column headers). FAIL if more than two of these columns
    are missing.

So the check is the criterion: read the header row, count how many of the
eight are absent, refuse at more than two. The only judgement left is
what "substantially equivalent" admits, and that is a small closed
vocabulary of column names rather than an open reading of prose.

MEASURED, 28 graded trackers: agrees with LAB's judge on 25. All three
disagreements run the same way -- the guard permits, the judge fails --
and in each the judge names exactly two missing columns while its own
criterion fails only at MORE than two. The judge does not apply the
threshold it states. This module applies it as written, which is the
point: the firm's standard is the text, and a check enforces the text
identically every time.

Reading happens through LAB's own in-sandbox parser (`parse-doc xlsx`,
pandas `to_string`), never host-side on an agent-written binary. pandas
takes the first row as the header, and real trackers carry title rows
above the headers, so the header row usually arrives as DATA. Hence
`missing_columns` scores every line and keeps the best -- which also
survives multi-sheet workbooks and a tracker whose headers sit at row 4.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# The eight columns C-043 names, each with the surface forms real
# trackers use for it. These came from reading the graded trackers and
# from the judge's own equivalences, e.g. it accepted "RF #" for Issue
# Number, "Red Flag Title" for Description, "Buyer Action Required" for
# Recommended Action.
REQUIRED_COLUMNS: dict[str, tuple[str, ...]] = {
    "Issue Number": (r"\bissue\s*(no|num|number|#)", r"\brf\s*#",
                     r"\bid\b", r"\bref\b", r"\bflag\s*(no|#)"),
    "Risk Category": (r"\bcategor", r"risk\s*type", r"\barea\b"),
    "Description": (r"\bdescri", r"red\s*flag", r"\btitle\b",
                    r"\bsummary\b", r"\bfinding\b"),
    "Severity": (r"\bseverit", r"\bpriorit", r"\brating\b",
                 r"risk\s*level"),
    "Estimated Financial Exposure": (r"\bexposur", r"\bfinancial\b",
                                     r"\bimpact\b", r"\bquantif",
                                     r"\bamount\b"),
    "Source Document(s)": (r"\bsource\b", r"\bdocument", r"\bcitation",
                           r"\breference"),
    "Recommended Action": (r"\brecommend", r"\baction\b", r"next\s*step",
                           r"\bmitigat", r"\bremediat"),
    "Status": (r"\bstatus\b", r"\bstate\b", r"\bowner\b", r"\bresolved\b"),
}

# "FAIL if more than two of these columns are missing" -- the criterion's
# own number, not one chosen here.
MAX_MISSING_COLUMNS = 2


@dataclass(frozen=True)
class TrackerFindings:
    """What the tracker's header row contains. Facts only, no verdict
    beyond the one C-043 states."""

    missing: tuple[str, ...]

    @property
    def missing_count(self) -> int:
        return len(self.missing)

    @property
    def columns_ok(self) -> bool:
        return self.missing_count <= MAX_MISSING_COLUMNS

    def describe_missing(self) -> str:
        return ", ".join(self.missing) if self.missing else "none"


def missing_columns(text: str) -> list[str]:
    """Which required columns the tracker's header row lacks.

    Scores every line and keeps the best match rather than assuming a
    header position: pandas treats row 1 as the header, and trackers
    routinely put a title and a subtitle above the real headers, so the
    header row arrives as data with the title occupying the header slot.
    """
    best: set[str] = set()
    for line in text.splitlines():
        low = line.lower()
        found = {name for name, pats in REQUIRED_COLUMNS.items()
                 if any(re.search(p, low) for p in pats)}
        if len(found) > len(best):
            best = found
    return sorted(set(REQUIRED_COLUMNS) - best)


def check_tracker(text: str) -> TrackerFindings:
    """Pure function: no network, no policy decision, no side effects."""
    return TrackerFindings(missing=tuple(missing_columns(text)))
