# harvey-lab-drafting — closing the gap a better prompt cannot close

One rule, enforced before the memo is written, on a stock task from
Harvey's open-source Legal Agent Benchmark (LAB). LAB is unmodified. Not
affiliated with or endorsed by Harvey.

Current state, results, and known limits: **[STATUS.md](STATUS.md)**.

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

The hook counts the findings listed in the executive summary, states that
number as a fact, and Preflight's solver rules on it. Fewer than five and
the memorandum is not kept; the agent is told what is missing and revises.

**Scoped to one deliverable.** The rule governs `red-flag-memo.docx` and
nothing else. LAB's own C-036 is scoped the same way — its `deliverables`
field lists that file alone. An earlier version applied the rule to every
deliverable in the task, including `red-flag-tracker.xlsx`; a spreadsheet
has no executive summary, so it could never satisfy the rule, and the
guard reverted a legitimate deliverable four times in one run. A rule
about memoranda has nothing to say about a spreadsheet.

Everything else this repo can measure — addressing, issuing firm, matter
reference, cleared-items section, uncited red flags — is computed and
reported as advisory, and **gates nothing**. Earlier versions enforced
five rules and they worked. The demo makes a single claim now because a
single claim is easier to check.

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
3. **The count depended on someone else's pandoc flags.** An indented
   continuation line read as prose ending the list. LAB parses `.docx`
   with `pandoc --wrap=none`, which puts each item on one line, so this
   never fired — the count was right because of a flag in LAB's code, not
   because the counter was. Under ordinary wrapping the same conforming
   memo counted three instead of five, which would have blocked work that
   met the standard. The count now describes the document, not the
   parser.

## The guarantee: verify the artifact, not the command

Three runs escaped three different ways — a bash heredoc, then a
content-sniffing gap, then `pandoc` wrapped in `python3 -c`. Each fix
closed one spelling of "produce this file" and the agent found another,
not adversarially but because **the set of ways to write a file is not
enumerable**. `sh -c`, a Makefile, a script written then run, `xargs`, an
editor — there is no finite list.

So the guarantee no longer depends on recognising the command. Every tool
call is wrapped:

1. fingerprint the deliverables (bytes hash)
2. let LAB's executor run the call, whatever it is
3. fingerprint again — unchanged means nothing to do
4. if a deliverable changed: parse it **in the sandbox** via LAB's own
   `_read_and_parse`, count the findings, check with Preflight, record the
   receipt
5. non-compliant → restore the previous bytes (or delete if it did not
   exist) and return the block message instead of the tool's result

Route-independent by construction. A test asserts this by making a
deliverable appear from `make memo` — a command the guard has no rule for
— and confirming it is reverted.

**Zero LAB modifications.** This uses only what the wrapped executor
already exposes: `sandbox.exists/read_file/write_file/exec` and
`_read_and_parse`. Nothing in `harvey-labs` is patched.

It also removes a bug: the guard now reads the deliverable exactly as
LAB's grader does, so the checker cannot disagree with the judge about
the same document the way an earlier content-sniffing version did.

### Why "revert" is the right semantics here, and where it would not be

The standard is about what is **issued**. An associate hands a partner a
memo missing its executive summary list; the partner hands it back. The
draft existed — on a desk, in a drafts folder — and no control failed,
because the control is "this does not go out."

Reverting inside the tool call is that. The deliverable never survives to
be delivered, the agent cannot build on it, and the final artifact is
always verified because the last tool call is wrapped like every other.

This would be the **wrong** semantics for an exfiltration rule. If the
violation is that data left, a transmitted byte cannot be recalled and
prevention must come first — which is why the conduct demo
([harvey-lab-preflight](https://github.com/hshadab/harvey)) blocks before
the action rather than verifying after it. Different rule types need
different enforcement points, and that is a principled distinction rather
than a compromise.

The pre-checks below still run. They give the agent feedback while it is
drafting, which is far cheaper to act on than a rejection after
conversion — but they are the ergonomics, not the guarantee.

### A revert that fails is louder than a block

A run once delivered a memorandum the guard had blocked. `_revert` called
`sandbox.exec(["rm", "-f", path])`, but LAB's `Sandbox.exec` takes a
command **string**; the call raised `TypeError` and a bare
`except Exception: pass` swallowed it. The non-compliant `.docx` stayed on
disk, and the ledger recorded a successful block.

A receipt that says a file was stopped, sitting next to that file, is
worse than no receipt at all. So:

* `_revert` confirms the filesystem afterwards — `not exists()` after a
  delete, a byte comparison after a restore — and returns whether the
  revert actually happened
* a failed revert records `REVERT-FAILED` in the ledger and tells the
  agent the file must not be delivered
* there is no path where enforcement fails quietly

The test suite missed this because `FakeSandbox.exec` accepted a list.
A fake more permissive than the thing it fakes is not a test; it is a
second bug. `TestSandboxContract` now pins the fake's signatures to the
real `Sandbox` via `inspect.signature`.

## Every run ends by saying what is on disk

The deliverable of this system is *a conforming memorandum, or a visible
refusal with a reason* — never *silently absent*. So a run does not infer
its outcome from the ledger; it reads the artifact and says one of three
things:

| verdict | meaning |
|---|---|
| `DELIVERED` | a conforming deliverable exists |
| `REFUSED` | nothing was issued, and the run says so out loud |
| `ESCAPED` | a non-conforming deliverable survived — **the guarantee failed; do not use this run** |

Written to `final_state.json` and printed as a banner, on every exit path
including a crash. `runH_r1`'s first attempt died on an Anthropic 400 and
left a run directory with no verdict at all — the one state the contract
does not allow. An unreadable deliverable is `ESCAPED`, never a clean
refusal.

## Blocking is the product; compliance is a bonus

The claim is **not** "the guard makes the agent write better memos". That
is a statistical claim: it needs many runs, it is model-dependent, and it
expires at the next model upgrade. The claim is *this artifact was checked
against the firm's standard and did not leave the sandbox* — per-artifact,
with a receipt.

This is why a lower LAB score under enforcement is not a defect. A
refusal that produces nothing scores zero on the memo criteria and is
still the correct outcome; an associate who cannot meet the standard
hands the partner nothing, and the partner finds out.

One consequence worth stating: a control that only ever blocks is
indistinguishable from a broken control. Two runs showed the agent
reading a block as broken tooling and going off to
`strace` pandoc. So the standard is now stated in the system prompt
before work begins, the way a firm briefs an associate rather than
waiting to reject the draft.

**This changes what the agent knows, never what is enforced.** The guard
recomputes every fact host-side and Preflight decides independently, so a
run whose agent ignores the briefing is governed exactly as before.
`--no-briefing` reproduces the old behaviour. The briefing interpolates
`_MIN_EXEC_SUMMARY_FINDINGS`, so it cannot drift from the rule it
describes.

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

* **`bash` not governed at all** — blocked three times on `write`, the
  agent wrote the memo with a heredoc and shipped it. Same hole as
  [BATTLE-TEST-FINDINGS §6](https://github.com/hshadab/harvey/blob/main/BATTLE-TEST-FINDINGS.md),
  which this repo cites in its own docstrings and recreated anyway.
* **Keyword matching on code** — refused the agent's 50KB xlsx-builder
  **eight times**, because its openpyxl data strings contain "red flag" and
  "diligence". The memo was already compliant; the guard simply stopped
  the agent working.
* **Keyword matching on prose** — refused `response.md`, the agent's
  closing summary, twice. Prose about red flags, never a deliverable.

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

## Results

Run results, what is in flight, and known limits: **[STATUS.md](STATUS.md)**.

Verify a memo by hand with the parser enforcement uses, or you are
grading a different document — Word keeps list numbering in
`numbering.xml`, not in the paragraph text, so a hand-rolled XML strip
reports conforming memos as failures:

```bash
pandoc runs/<id>/output/red-flag-memo.docx -t markdown --wrap=none -o /tmp/m.md
PYTHONPATH=. python3 -c "from hook.drafting import exec_summary_findings; \
print(exec_summary_findings(open('/tmp/m.md').read()))"
```

## Layout

    policy/controls.md       the single rule (source for makeRules)
    policy/engagement.json   matter facts — advisory checks only
    hook/drafting.py         host-side counts; the only place facts are made
    hook/action_text.py      states the count as a number, one pathway
    hook/guard.py            DraftingGuard — wraps LAB's ToolExecutor
    hook/runner.py           run entry point; final_state verdict
    tests/                   77 offline tests, no network or API key
                             (also run in CI: .github/workflows/tests.yml)

## Run the tests

```bash
python3 -m unittest discover -s tests -v
```
