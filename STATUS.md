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
| `runI_r1` | haiku-4-5 | no | 0 | `DELIVERED` | 7 (categories) | **fail** |
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

### The rule had a hole, and the judge found it

`runI_r1` was scored and **failed C-036**. The guard had passed it.

Its summary bulleted seven risk categories — "Revenue & Customer
Concentration (3 flags)" — and numbered three actual findings. The guard
counted seven. The judge counted three: *"the executive summary only
calls out 3 as 'CRITICAL SEVERITY FLAGS'."*

This was a real defect in the rule, not the plumbing: a gate passing
work it should have stopped. Fixed — bullets no longer count, only
consecutively numbered items. `runI_r1`'s summary now counts 3 and would
be blocked.

Re-measured across all 25 scored memos with the corrected counter:

| | judge passes C-036 | judge fails C-036 |
|---|---|---|
| **guard passes** (5+ numbered) | 6 | **0** |
| **guard blocks** (fewer) | 9 | 10 |

Nine memos the judge accepted would be blocked by this rule. That is
by design — the judge accepts a prose summary and a house style need
not. What a house style may not do is pass work the rubric fails, and
that column is now zero.

The earlier "4 of 4" claim came from a sample of four memos and was too
small to see this.

Against a historical unenforced C-036 rate of 11 of 18. Only runs under
the current architecture are kept in `runs/`; scores for the superseded
ones remain in `harvey-labs/results/`.

In `runH_r1` the LAB judge counted 15 findings and this repo's checker
counted 15, independently, on the same document.

The overall scores read FAIL because LAB gates on all 50 criteria. That
number does not measure this system, which makes one claim about one
criterion.

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
  executive summary lists 3 findings; at least 5 must be listed"), so
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

* Six runs is still a small sample, and only three are scored by LAB's
  judge.
* **A run directory with no `final_state.json` must be read as
  unverified, exactly like `ESCAPED`.** The crash handler covers the
  *process* dying; it cannot cover the machine dying or a run being
  killed. Do not read a missing verdict as a clean refusal.
* The rule counts enumerated items and cannot tell a finding from a
  category heading — see the `runI_r1` note above.
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
