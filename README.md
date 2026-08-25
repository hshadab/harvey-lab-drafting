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

## Where it intercepts

The agent does not write `red-flag-memo.docx` directly — it writes
markdown and converts with `generate_from_md.py`. So a write is governed
whenever it carries memo content, whatever the filename, and `bash` is
governed on two pathways: a heredoc carrying the memo, and any command
producing a deliverable (permitted only after a compliant draft has been
approved).

That second part was learned the hard way. In `runD_r1` the guard skipped
`bash` entirely and the agent — blocked three times on `write` — wrote the
memo with a heredoc and shipped it anyway. Same hole as
[BATTLE-TEST-FINDINGS §6](https://github.com/hshadab/harvey/blob/main/BATTLE-TEST-FINDINGS.md)
in the conduct demo: cited in this repo's own docstrings, and recreated
regardless. `runD_r2` then tried both routes and was caught on each.

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
