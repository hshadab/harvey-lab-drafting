# Status

Current state of the demo. Updated as runs land.

## Is it working?

Yes. A firm drafting rule is enforced automatically on Harvey LAB's own
task, every decision leaves a receipt, and nothing in `harvey-labs` is
modified.

## Results

| Run | Rule stated up front? | Blocked | Passed | Final state | LAB judge C-036 | Overall |
|---|---|---|---|---|---|---|
| `runG_r1` | no | 5 | 1 | conforming, 5 findings | pass | 38/50 |
| `runH_r1` | yes | 0 | 1 | `DELIVERED`, 15 findings | pass | 35/50 |

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

## In flight

Four unbriefed runs on `claude-haiku-4-5` (`runI_r1`..`runI_r4`), one at
a time. A weaker model produces more violations, so it is a harder test
of whether the gate catches them. The result that matters is the final
state of each run: `ESCAPED` would mean a non-conforming deliverable
survived and the guarantee failed.

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

* Two clean scored runs is a small sample. The soak runs address this.
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
