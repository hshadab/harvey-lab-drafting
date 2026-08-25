# Status

Current state of the demo. Updated as runs land.

## Is it working?

Yes. A firm drafting rule is enforced automatically on Harvey LAB's own
task, every decision leaves a receipt, and nothing in `harvey-labs` is
modified.

## What is enforced

One rule, on one deliverable, in one policy:

> The memorandum may not raise, as a red flag, an item the engagement
> has already dispositioned as cleared.

This is LAB's **C-032**, and it is a **prohibition** rather than a
requirement. That is the whole reason it was chosen.

A requirement ("include five findings") is discharged by one deliberate
act the agent can watch itself perform, and a firm can close most of
that gap with a prompt. A prohibition has to hold across every red flag
the memo raises, it competes directly with the task's own instruction to
find red flags, and one slip is a failure. **Agents violate C-032 in 23
of 28 recorded memos — 82%.**

The rule is generic; the cleared list is matter configuration in
`policy/engagement.json`, exactly like the client's name. "Do not
re-raise an item the engagement has cleared" is a firm standard; "the
Wyoming permit is fine" would be an answer key. The underlying fact is
discoverable in the data room, which is that file's standing test.

Measured across the 28 graded memos:

| | judge fails C-032 | judge passes C-032 |
|---|---|---|
| **guard blocks** | 23 | **0** |
| **guard permits** | 2 | 3 |

Zero false blocks. It never refuses a memo the judge accepted.

**One cleared item, not four.** LAB has four distractor criteria
(C-032..C-035). Only this one is checkable without false positives:
matching the others fired on legitimate passing mentions their own
criteria expressly permit — 15 on "appraisal", 12 on the
termination-for-convenience clause. Matching the red flag's *heading*
rather than its body is what produced zero false positives.


## Results

No run has yet been recorded against this rule. `runM_r1` is the first.

Runs `runG` through `runK` enforced the previous rule (C-036, executive
summary) and are kept in `runs/` as history; their ledgers describe a
standard this repo no longer enforces. Across all nine, zero reached
`ESCAPED`.

What is measured for the current rule is offline, against the 28 graded
memos: 23 true blocks, zero false blocks, 2 misses.

## What the configurations are for

Two independent knobs, each changing only what the agent is told —
enforcement, the solver's facts, and the ledger are identical in every
combination.

**Before the work — is the rule stated up front?**

* **Rule not stated** (`--no-briefing`) — the honest test of enforcement.
  The agent writes what it would naturally write, some of it fails, and
  the gate has something to catch. `runG_r1` produced five blocks.
* **Rule stated** — what a firm would actually do: state the house style
  rather than silently reject drafts. Produces few or no blocks.

**At a block — is the agent told why?**

* **Bare block** (`--bare-blocks`) — the refusal names no missing
  element. This is the control arm: it shows the gate holds regardless
  of what the agent does with the news. Expect thrash — two earlier
  runs read unexplained blocks as broken tooling and went off to strace
  pandoc; the deliverable stayed governed the whole time.
* **Explained block** (default) — the refusal names the defect ("the
  names the cleared matter it raised), so
  the agent revises the memo and converges. This is the demo's product
  arm.

The planned head-to-head is both arms unbriefed: same model, same task,
same policy — one run shows blocking alone, the other shows
block-and-repair. A run with zero blocks cannot demonstrate that
enforcement works, so both arms use the unbriefed setting.

## Fixed (2026-08-25)

| Commit | Problem |
|---|---|
| `acecd04` | The rule governed `red-flag-tracker.xlsx`, which has no executive summary, so the guard destroyed a legitimate deliverable four times in one run |
| `626f356` | A revert failed silently and shipped a blocked memorandum while the ledger claimed it was stopped |
| `4f974d5` | No verdict at the end of a run; the finding count depended on LAB's pandoc flags rather than on the document |
| `f3dca86` | A crashed run left no verdict at all |
| `184372e` | README predated all of the above |
| `b540874` | An `edit` tool call testified about the fragment as if it were the document — false testimony, the §6 failure — and replaced the recorded source with the fragment; a bold `**Executive Summary**` heading (pandoc's rendering of a bold-paragraph heading) counted 0 findings and would have blocked a conforming memo; quoted conversion paths skipped the early gate |

81 offline tests. Each fix is mutation-checked: reverting it fails the
suite.

## Known limits

* **One cleared item, not four.** LAB has four distractor criteria
  (C-032..C-035); only this one is checkable without false positives.
  Enforcing the others would block memos their own criteria permit.
* The check matches a red flag's heading. A memo that raises a cleared
  matter without naming it in the heading would not be caught.
* Nine runs is still a small sample, and only four are scored by LAB's
  judge.
* **One rule, out of fifty criteria.** This shows the mechanism works on
  one standard. It does not show it generalises to rules that are harder
  to count.
* **A run directory with no `final_state.json` must be read as
  unverified, exactly like `ESCAPED`.** The crash handler covers the
  *process* dying; it cannot cover the machine dying or a run being
  killed. Do not read a missing verdict as a clean refusal.
* `/v1/me` returns 403 on both auth headers, so the ICME credit balance
  cannot be read from here. Runs themselves work, so the key is valid.
* Most of the bugs above were found by running or probing the system,
  not by the pre-existing tests. Assume more exist.
* The verdict-on-crash guarantee covers the runner process dying, not
  the machine dying (`runI_r2`). A run directory without
  `final_state.json` is unverified — treat it as `ESCAPED`.
* The rule counts an *enumeration*; an enumerated list of risk
  categories satisfies it just as a list of findings does (`runI_r1`).
  The stricter-rule-implies-criterion evidence in the README is about
  memos that enumerate findings; category-list summaries are a shape
  that evidence does not yet cover.

## Verifying a memo by hand

Use the parser enforcement uses, or you are grading a different document
— a hand-rolled XML strip misreads Word structure:

```bash
pandoc runs/<id>/output/red-flag-memo.docx -t markdown --wrap=none -o /tmp/m.md
PYTHONPATH=. python3 -c "
import json; from hook.drafting import EngagementConfig, flagged_cleared_items
c = EngagementConfig.from_dict(json.load(open('policy/engagement.json')))
print(flagged_cleared_items(open('/tmp/m.md').read(), c.cleared_items))"
```

Anything printed is a cleared matter the memo raised as a red flag.

## Note for upstream

LAB's Anthropic adapter does not use prompt caching, and runs re-send the
document set on every turn — `runG_r1` was 6.5M input tokens against 31K
output. Enabling caching would cut that substantially with identical
results. Not applied here: this demo's claim is zero modifications to
`harvey-labs`.
