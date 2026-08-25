# harvey-lab-drafting — closing the gap a better prompt cannot close

One rule, enforced before the memo is written, on a stock task from
Harvey's open-source Legal Agent Benchmark (LAB). LAB is unmodified. Not
affiliated with or endorsed by Harvey.

## The claim

Harvey's own rubric, verbatim from
`harvey-labs/tasks/corporate-ma/review-data-room-red-flag-review/task.json`:

> **C-036 — "Executive summary includes top 5 critical findings"**
> *PASS if the memo contains an executive summary section that
> specifically highlights at least 5 of the most critical findings from
> the review. FAIL if there is no executive summary or it lists fewer
> than 5 key findings.*

**It passes 11 of 18 recorded runs — 61%.** The seven failures are
scattered across both arms of an unrelated experiment, with no pattern.
The model mostly gets this right. Sometimes it doesn't.

That is the entire pitch.

## Why this is the interesting failure mode

A requirement the model *never* satisfies is a specification gap: nobody
asked, so it didn't. Write it into the prompt and it largely goes away.

C-036 is not that. It is a requirement the model **already mostly meets
and inconsistently misses** — and that is the shape instructions cannot
fix:

* **A prompt raises the rate; it never reaches 100%.** Models drift in
  long contexts, reprioritise under competing goals, and improvise when
  the task gets messier than the example you tuned on.
* **The better your prompting, the more invisible the residue.** At a 40%
  failure rate you notice in a day. At 1% you never notice — and if an
  agent takes 10,000 actions a month, that is 100 deliverables that went
  out wrong.
* **The failures look exactly like the successes.** A memo scoring 39/50
  with a four-item executive summary reads fine. Nobody audits a rubric
  line by line.

A prompt is a request. A check is a gate. And a gate leaves a receipt.

## What is enforced

One rule, in `policy/controls.md`:

> The agent may not write a final deliverable memorandum when the number
> of findings listed in the memorandum's executive summary is fewer than
> five.

Before the memo is written, the hook counts the findings listed in its
executive summary, states that number as a fact, and Preflight's solver
rules on it. Fewer than five and the write never happens; the agent is
told what is missing and revises.

Everything else this repo can measure — addressing, issuing firm, matter
reference, cleared-items section, uncited red flags — is computed and
reported as advisory, and **gates nothing**. Earlier versions enforced
five rules (kept as `policy/*-v2-4rules.json`, `*-v3-5rules.json`) and
they worked. The demo makes a single claim now because a single claim is
easier to check.

## We do not replicate the judge — we imply it

C-036's test is semantic, and the judge's calls on it are not consistent:
it **passed** a summary naming four vague themes (`runA_r9`) and **failed**
one naming five concrete items (`runA_r8`). Trying to reproduce a fuzzy
grader is how an earlier attempt at C-039 went wrong.

So the rule is deliberately **stricter and mechanical**: the executive
summary must contain a *list* of at least five findings. Evidence that
the stricter rule implies the criterion — of the 18 recorded memos, the
four whose summaries list five or more pass C-036 **4 times out of 4**,
while the fourteen that do not are a coin flip (7 pass, 7 fail).

A house style may be more specific than a rubric. It may not be
unverifiable.

Two counting bugs surfaced while establishing that, both of which would
have made the claim false:

1. **Summing separate lists.** `runA`'s summary says *"the three most
   critical issues are"* and lists three; adding a second short list
   elsewhere reached five, and LAB failed that memo. Only a **contiguous**
   list counts.
2. **Lists bleeding across sections.** A blank line let the summary's list
   run into the next section's `1.`, counting four where there were three.
   A numbered list must be **consecutively numbered** to continue.

## Where it intercepts — by destination, not by content

The deliverable is a known filename, and it comes into existence exactly
one way: a converter reads a markdown source and writes the `.docx`. So:

* a write whose path **is** the deliverable — checked
* a write to a markdown source — **recorded**, not checked; a source is
  only consequential if something converts it
* a command converting `SOURCE -> deliverable` — **the gate**. Permitted
  only if that source's content meets the standard. A source the guard
  never saw written is refused outright.

Everything else is untouched, whatever it contains.

**This replaced three versions that tried to recognise the memo from what
it said** — long, mentions "red flag" and "diligence". Each misfired in a
live run:

* `runD_r1` — `bash` not governed at all; blocked three times on `write`,
  the agent wrote the memo with a heredoc and shipped it. Same hole as
  [BATTLE-TEST-FINDINGS §6](https://github.com/hshadab/harvey/blob/main/BATTLE-TEST-FINDINGS.md),
  which this repo cites in its own docstrings and recreated anyway.
* `runE_r1` (first) — refused the agent's 50KB xlsx-builder **eight
  times**, because its openpyxl data strings contain "red flag" and
  "diligence". The memo was already compliant; the guard simply stopped
  the agent working.
* `runE_r1` (second) — refused `response.md`, the agent's closing summary,
  twice. Prose about red flags, never a deliverable.

A file that never becomes a deliverable cannot violate a standard about
deliverables. Detecting intent from vocabulary was the wrong idea three
times before it was replaced with the destination test.

## On writing a rule that actually compiles

The first policy compiled cleanly, reported success, and **enforced
nothing** — every violating draft returned SAT. Its rules described a
document's state ("a memorandum containing no cleared-items section is
forbidden"), which compiled to free-floating booleans the extractor never
bound.

Rules must describe an **action on an object, with a count**. "The agent
may not write a memorandum when the number of X is fewer than five" gives
the extractor an actor, a verb and a number. Adjectives do not ground;
numbers do.

It fails silently, which is the dangerous part: a dead policy produces a
clean-looking run in which nothing is enforced. Only probing a case that
*should* block reveals it. Probe before every recorded run.

## Prediction

Recorded before the enforced runs, so it can be scored rather than
rationalised: **C-036 goes from 11/18 to passing.** If it does not, the
implication argument above is wrong and this line is the record of it.

## runE_r1 (2026-08-25): C-036 passed — but the gate did not cause it

**40/50, the second-highest score of any run recorded here. C-036 passed,
as predicted. And the prediction should not be counted as confirmed.**

The three governed checks tell the real story:

| Verdict | File | Findings counted |
|---|---|---|
| **SAT** | `red-flag-memo.md` | 5 |
| UNSAT | `response.md` | 0 |
| UNSAT | `response.md` | 0 |

**The memo passed on its first attempt.** The agent listed five findings
unprompted; enforcement had nothing to correct. So C-036 passing here is
the agent complying on its own, not the gate changing an outcome — this
run is consistent with the prediction and is not evidence for it.

C-036 passes 61% of the time unenforced. A single enforced run landing in
that 61% proves nothing. What would prove it is a run where the memo is
blocked for listing fewer than five and then ships compliant, which
`runD_r2` demonstrated for a different rule and this run did not get the
chance to.

**Still one false positive.** `response.md` — the agent's closing summary,
not a graded deliverable — was classified as a memo draft and refused
twice. Same root cause as the tracker-script bug one run earlier: the
classifier catches anything long and prose-shaped that mentions red flags.
The redirect-target fix excluded code; it does not exclude genuine
markdown that simply is not the memo. Not score-affecting (the graded
deliverables are the `.docx` and `.xlsx`), but the guard is still refusing
work it has no business governing.

**On the 40/50.** The unenforced baseline is 33-41, mean 36.1. 40 sits
inside that range, near the top. At n=1, with the gate never firing on the
memo, this says nothing about whether enforcement costs or gains
anything — and it is not offered as though it does.

## runE_r2 (2026-08-25): the gate fired correctly, and leaked anyway

**34/50. C-036 failed. One block, zero permitted writes — and a `.docx` on
disk regardless.**

What happened, in order:

1. The agent wrote the memo to `/tmp/red_flag_memo.md` via a heredoc. Its
   executive summary was **1,041 characters of pure prose** — findings
   lived in a table further down. The guard counted zero listed findings.
2. It ran the conversion. **Blocked, correctly** — the source did not meet
   the standard.
3. It then ran pandoc **inside a Python one-liner**:
   `python3 -c "subprocess.run(['pandoc', '/tmp/red_flag_memo.md', '-o',
   'output/red-flag-memo.docx'])"`. The command-matching regex expects
   bare paths; quoted list arguments slipped past it. The `.docx` was
   written.
4. LAB's judge failed C-036 on exactly the ground the rule encodes: *"It
   does not enumerate or specifically describe any of the top 5 critical
   findings. The detailed findings appear later in the body of the memo,
   not in the executive summary itself."*

So the rule was right, the block was right, the judge agreed with the
rule — and the artifact shipped anyway because the gate had a third hole.

### Third route, third time

| Run | Route the agent used | Guard state |
|---|---|---|
| `runD_r1` | bash heredoc | `bash` ungoverned |
| `runE_r1` | (complied first try) | content-sniffing false positives |
| `runE_r2` | `python3 -c` wrapping pandoc | command-regex missed quoted args |

**Pattern-matching command lines is a losing game.** Each fix closed one
spelling of "convert this file" and the agent found another — not
adversarially, just by having many ways to run a program. There is no
finite list of shell incantations that produce a file.

The robust answer is not a better regex. It is enforcement at the
**filesystem**: make the output directory writable only through a checked
path, so no command spelling matters. That means modifying LAB's sandbox,
which costs this repo its "zero LAB modifications" property — a real
trade-off, and the honest recommendation for anything beyond a demo.

### And my own measurement was wrong

I initially reported this run's artifact as **compliant**. It is not.

`exec_summary_findings` bounded the executive summary at markdown
headings, roman numerals, or ALL-CAPS lines. The shipped `.docx` renders
its next heading as **"Risk Category Summary"** — Title Case — so the
boundary was missed, the counter ran 4,000 characters into the body, and
returned 9 findings for a summary containing none.

The guard read the *markdown source*, found the boundary, and was right.
My verification read the *`.docx`* and was wrong. The two disagreed about
the same document and I believed the wrong one until the judge contradicted
it.

Fixed, and every prior compliance claim re-checked against the judge:

| Run | Findings counted | Judge C-036 |
|---|---|---|
| `runD_r2` | 5 | pass |
| `runE_r1` | 5 | pass |
| `runE_r2` | 0 | **fail** |

Only `runE_r2`'s claim was false. The implication behind the rule still
holds 4/4 across the 18 historical memos.

## Layout

    policy/controls.md       the single rule (source for makeRules)
    policy/engagement.json   matter facts — advisory checks only
    hook/drafting.py         host-side counts; the only place facts are made
    hook/action_text.py      states the count as a number, one pathway
    hook/guard.py            DraftingGuard — wraps LAB's ToolExecutor
    hook/runner.py           run entry point
    tests/                   34 offline tests, no network or API key

## Run the tests

```bash
python3 -m unittest discover -s tests -v
```
