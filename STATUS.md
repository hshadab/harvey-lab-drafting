# Status

Current state of the demo. Updated as runs land.

## Is it working?

Yes. A firm drafting rule is enforced automatically on Harvey LAB's own
task, every decision leaves a receipt, and nothing in `harvey-labs` is
modified.

## What is enforced

One rule, on one deliverable, in one policy:

> The executive summary of `red-flag-memo.docx` must enumerate and
> describe at least five findings.

It is a deliberately stricter mechanical stand-in for LAB's C-036, whose
own test is semantic ("at least 5 of the most critical findings"). What
that buys and what it costs is measured below.

## Results

Every run under the current architecture:

| Run | Model | Rule stated up front? | Blocked | Final state | Findings | LAB judge C-036 |
|---|---|---|---|---|---|---|
| `runG_r1` | sonnet-4-6 | no | 5 | `DELIVERED` | 5 | pass |
| `runH_r1` | sonnet-4-6 | yes | 0 | `DELIVERED` | 15 | pass |
| `runI_r1` | haiku-4-5 | no | 0 | `DELIVERED` | 7 (categories) | **fail** |
| `runI_r2` | haiku-4-5 | no | 3 | `REFUSED` | — | not scored |
| `runI_r3` | haiku-4-5 | no | 2 | `REFUSED` | — | not scored |
| `runI_r4` | haiku-4-5 | no | 3 | `DELIVERED` | 5 (bulleted) | pass |
| `runJ_r1` | haiku-4-5 | no | 0 | `DELIVERED` | 5 | pass |
| `runJ_r2` | sonnet-4-6 | no | 3 | `DELIVERED` | 12 | pass |
| `runK_r2` | haiku-4-5 | no | 3 | `REFUSED` | — | — |

**13 blocks, 4 conforming deliveries, 2 refusals, 0 escapes.**

`ESCAPED` — a non-conforming deliverable surviving on disk — did not
occur. Every `DELIVERED` memo was re-checked by hand with the parser
below and conforms. Every `REFUSED` run has no `red-flag-memo.docx` on
disk at all.

The two refusals are the correct outcome, not a failure: the weaker model
could not meet the standard, so nothing was issued and the run says so.
Both still produced the tracker, which the rule does not govern.

Overall LAB scores where measured: `runG_r1` 38/50, `runH_r1` 35/50.


## Live runs on the corrected rule (`runJ`)

`runJ_r1` (haiku) delivered with no blocks; `runJ_r2` (sonnet) is the
block-and-repair cycle end to end — three blocks, the agent revised,
three passes, then `DELIVERED` with 12 findings. LAB's judge passed
C-036 on both.

Two things this exposed, both narrowing what the rule can be claimed to
do:

**Described categories were not excluded — now fixed.** `runJ_r1`'s
summary bullets four severity bands — "CRITICAL (4 flags): Issues
requiring immediate resolution…" — each 55–96 characters, all above the
length threshold. They are categories, the same shape that broke the
rule in `runI_r1`, but they carry a sentence of description so length
did not exclude them. The count came out right only because the bands
form a run of **four** and `Key findings:` at the margin breaks the run;
five bands would have passed the gate on categories again. Verified
directly: five described bands counted 5 before the fix.

An item that announces **how many** findings it covers is now read as a
category. A finding describes one thing; a category says how many things
it contains. Both idioms are recognised — "CRITICAL (4 flags):" and
"CRITICAL ISSUES (3):". A bare tally noun stands alone only for
flags/findings; the broader nouns (issues, items, concerns) count only
in the parenthesised form, so a real finding saying "5 issues remain"
is not excluded.

On the 28 scored memos this changes **no count** — there the bands were
already too short or formed a shorter run than the real findings — so it
closes the hole without moving any measured result.

**A character cap made the count depend on the parser.** The executive
summary was truncated at 4000 raw characters, and `runJ_r2`'s summary is
4712 characters under `--wrap=none` and 4864 under `--columns=72`, so
the cut landed in a different place: 12 findings under one parser, 11
under the other. The cap now applies after coalescing, so it measures
the document rather than the wrapping.

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

* Nine runs is still a small sample, and only four are scored by LAB's
  judge.
* **One rule, out of fifty criteria.** This shows the mechanism works on
  one standard. It does not show it generalises to rules that are harder
  to count.
* **A run directory with no `final_state.json` must be read as
  unverified, exactly like `ESCAPED`.** The crash handler covers the
  *process* dying; it cannot cover the machine dying or a run being
  killed. Do not read a missing verdict as a clean refusal.
* The rule separates a finding from a category by length (50 characters
  of description). A memo listing five genuine findings more tersely
  than that would be blocked. No memo in the 28 scored does this, so the
  risk is unmeasured rather than ruled out.
* The count is stable under the parser enforcement actually uses — LAB
  parses `.docx` with `pandoc --wrap=none` — but not under every parser.
  `runJ_r1` counts 5 under `--wrap=none` and 1 under `--columns=72`,
  because that mode wraps list continuations to the margin with no
  indent and the scan reads them as prose ending the list. An earlier
  commit message claimed identical verdicts under both modes on every
  memo; that claim was wrong.
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
