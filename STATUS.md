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

`runM_r1` (sonnet, unbriefed) — **the guard blocked four times and then
missed.** The entry that shipped was titled "RED FLAG 7 — Casper
Facility Permit", never saying Wyoming in its heading, while its body
said "The Wyoming hazardous waste permit … expired" and recommended
obtaining written acknowledgment from Wyoming DEQ. LAB's judge failed
C-032 on it.

The check matched the heading, and the heading is the part the agent
chooses. It now matches the whole entry. Whether the retitling was a
response to being blocked or an incidental rewording is not something
the transcript settles, and it does not matter: a check the agent can
defeat by renaming is not a check.

Both real documents are now regression fixtures — the renamed entry, and
the memo where "Ramirez v. RES (D. Wyoming)" is a court rather than a
permit. Reverting to heading-matching fails the suite.

Re-measured across the 28 graded memos plus `runM_r1`: **24 blocks, zero
false positives, 2 misses.**

Runs that enforced the previous rule have been deleted; their ledgers
described a standard this repo no longer has. They are in git history.

What is measured for the current rule is offline, against the 28 graded
memos: 23 true blocks, zero false blocks, 2 misses.

## What the configurations are for

Two independent knobs, each changing only what the agent is told —
enforcement, the solver's facts, and the ledger are identical in every
combination.

**Before the work — is the rule stated up front?**

* **Rule not stated** (`--no-briefing`) — the honest test of enforcement.
  The agent writes what it would naturally write, some of it fails, and
  the gate has something to catch.
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

Defects found in this system, in order. Each fix is mutation-checked:
reverting it fails the suite.

| Commit | Problem |
|---|---|
| `acecd04` | The rule governed `red-flag-tracker.xlsx`, a deliverable it could not apply to, and destroyed it four times in one run |
| `626f356` | A revert failed silently and shipped a blocked memorandum while the ledger claimed it was stopped |
| `4f974d5` | No verdict at the end of a run |
| `f3dca86` | A crashed run left no verdict at all |
| `b540874` | An `edit` tool call testified about the fragment as if it were the document — false testimony — and replaced the recorded source with the fragment; quoted conversion paths skipped the early gate |
| `f1a33b1` | Two standards in the repo, one of which enforced nothing |
| `4b105dd` | The check matched the red flag's heading, so retitling an entry defeated it; confirmed live in `runM_r1` |

77 offline tests.

## Known limits

* **One cleared item, not four.** LAB has four distractor criteria
  (C-032..C-035); only this one is checkable without false positives.
  Enforcing the others would block memos their own criteria permit.
* The check matches a red flag's whole entry, and the pattern carries
  its own precision. A memo that raises the cleared matter without using
  any of its names — no "Wyoming", no permit number, no "DEQ" — would
  still not be caught. Two of the 28 graded memos are misses for related
  reasons.
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
  the machine dying. A run directory without
  `final_state.json` is unverified — treat it as `ESCAPED`.

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
document set on every turn — one recorded run was 6.5M input tokens against 31K
output. Enabling caching would cut that substantially with identical
results. Not applied here: this demo's claim is zero modifications to
`harvey-labs`.
