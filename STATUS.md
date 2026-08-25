# Status

Current state of the demo. Updated as runs land.

## Is it working?

Yes. A firm drafting rule is enforced automatically on Harvey LAB's own
task, every decision leaves a receipt, and nothing in `harvey-labs` is
modified.

## Results

Every run under the current architecture:

| Run | Model | Rule stated up front? | Blocked | Final state | Findings | LAB judge C-036 |
|---|---|---|---|---|---|---|
| `runG_r1` | sonnet-4-6 | no | 5 | `DELIVERED` | 5 | pass |
| `runH_r1` | sonnet-4-6 | yes | 0 | `DELIVERED` | 15 | pass |
| `runI_r1` | haiku-4-5 | no | 0 | `DELIVERED` | 7 | not scored |
| `runI_r2` | haiku-4-5 | no | 3 | `REFUSED` | — | not scored |
| `runI_r3` | haiku-4-5 | no | 2 | `REFUSED` | — | not scored |
| `runI_r4` | haiku-4-5 | no | 3 | `DELIVERED` | 5 | pass |

**13 blocks, 4 conforming deliveries, 2 refusals, 0 escapes.**

`ESCAPED` — a non-conforming deliverable surviving on disk — did not
occur. Every `DELIVERED` memo was re-checked by hand with the parser
below and conforms. Every `REFUSED` run has no `red-flag-memo.docx` on
disk at all.

The two refusals are the correct outcome, not a failure: the weaker model
could not meet the standard, so nothing was issued and the run says so.
Both still produced the tracker, which the rule does not govern.

Overall LAB scores where measured: `runG_r1` 38/50, `runH_r1` 35/50.

C-036 has passed in every run where the guard passed the memo as
conforming — four so far, against a historical unenforced rate of 11 of
18. Only runs under the current architecture are kept in `runs/`; scores
for the superseded ones remain in `harvey-labs/results/`.

In `runH_r1` the LAB judge counted 15 findings and this repo's checker
counted 15, independently, on the same document.

The overall scores read FAIL because LAB gates on all 50 criteria. That
number does not measure this system, which makes one claim about one
criterion.

## What the two configurations are for

Both are kept; they answer different questions.

* **Rule not stated** (`--no-briefing`) — the honest test of enforcement.
  The agent writes what it would naturally write, some of it fails, and
  the gate has something to catch. `runG_r1` produced five blocks.
* **Rule stated** — what a firm would actually do: state the house style
  rather than silently reject drafts. Produces few or no blocks.

A run with zero blocks cannot demonstrate that enforcement works, so
soak testing uses the unbriefed setting.

## Fixed (2026-08-25)

| Commit | Problem |
|---|---|
| `acecd04` | The rule governed `red-flag-tracker.xlsx`, which has no executive summary, so the guard destroyed a legitimate deliverable four times in one run |
| `626f356` | A revert failed silently and shipped a blocked memorandum while the ledger claimed it was stopped |
| `4f974d5` | No verdict at the end of a run; the finding count depended on LAB's pandoc flags rather than on the document |
| `f3dca86` | A crashed run left no verdict at all |
| `184372e` | README predated all of the above |

58 offline tests. Each fix is mutation-checked: reverting it fails the
suite.

## Known limits

* Six runs is still a small sample, and only three are scored by LAB's
  judge.
* `/v1/me` returns 403 on both auth headers, so the ICME credit balance
  cannot be read from here. Runs themselves work, so the key is valid.
* Three of the five bugs above were found by running the system, not by
  the tests. Assume more exist.

## Verifying a memo by hand

Use the parser enforcement uses, or you are grading a different document:

```bash
pandoc runs/<id>/output/red-flag-memo.docx -t markdown --wrap=none -o /tmp/m.md
PYTHONPATH=. python3 -c "from hook.drafting import exec_summary_findings; \
print(exec_summary_findings(open('/tmp/m.md').read()))"
```

A hand-rolled XML strip does not work. Word stores list numbering in
`numbering.xml`, not in the paragraph text, so it reports conforming
memos as failures.

## Note for upstream

LAB's Anthropic adapter does not use prompt caching, and runs re-send the
document set on every turn — `runG_r1` was 6.5M input tokens against 31K
output. Enabling caching would cut that substantially with identical
results. Not applied here: this demo's claim is zero modifications to
`harvey-labs`.
