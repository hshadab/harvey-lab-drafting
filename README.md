# harvey-lab-drafting — closing the gap a better prompt cannot close

One rule, enforced before the memo is written, on a stock task from
Harvey's open-source Legal Agent Benchmark (LAB). LAB is unmodified. Not
affiliated with or endorsed by Harvey.

Current state, results, and known limits: **[STATUS.md](STATUS.md)**.

## The claim

Harvey's own rubric, verbatim from
`harvey-labs/tasks/corporate-ma/review-data-room-red-flag-review/task.json`:

> **C-032 — "DISTRACTOR_001: Does not flag Wyoming permit as a red flag"**
> *PASS if the memo either (a) does not flag the Wyoming DEQ permit
> (WY-HW-2019-033) expiration as a red flag, or (b) affirmatively
> explains that the timely filed renewal application allows continued
> operations. **FAIL if the memo flags the Wyoming permit expiration as a
> material red flag or recommends remedial action beyond routine
> monitoring.***

**Agents fail it in 23 of 28 recorded memos — 82%.** The renewal was
filed on time; the memo raises it anyway, rates it MEDIUM, and recommends
a closing condition. That is an associate crying wolf about a matter the
partner already dispositioned.

That is the entire pitch.

## Why a prohibition is the interesting shape

Most of LAB's fifty criteria are requirements — *include* this, *cite*
that. A requirement is discharged by one deliberate act the agent can
watch itself perform, so a firm closes most of that gap with a prompt.
The rules worth gating are the ones prompting cannot bound:

* **A prohibition has no single moment of compliance.** It must hold
  across every red flag the memo raises. One slip in two hundred turns is
  a failure.
* **It competes with the task's own instruction.** The agent was told to
  find red flags. The Wyoming permit looks like one. The tension is
  structural, not a lapse of attention.
* **A prompt raises the rate; it never reaches 100%.** At a 40% failure
  rate you notice in a day. At 1% you never notice — and if an agent
  takes 10,000 actions a month, that is 100 deliverables that went out
  wrong.
* **The failures look exactly like the successes.** A memo that flags one
  non-issue among fourteen real ones reads fine. Nobody audits a rubric
  line by line.

A prompt is a request. A check is a gate. And a gate leaves a receipt.

## What is enforced

One rule, in `policy/controls.md`:

> The agent may not write a final deliverable memorandum when the number
> of already-cleared items that the memorandum raises as red flags is
> greater than zero.

The hook counts them, states that number as a fact, and Preflight's
solver rules on it. Greater than zero and the memorandum is not kept; the
agent is told which cleared matter it raised.

**The rule is generic; the list is matter configuration.** `Do not
re-raise an item the engagement has cleared` is a firm standard. `The
Wyoming permit is fine` would be an answer key. The cleared list lives in
`policy/engagement.json` alongside the client's name, and every value
there must be discoverable in the data room — the renewal date is stated
in the environmental permit schedule.

**Scoped to one deliverable.** The rule governs `red-flag-memo.docx` and
nothing else, as LAB's own criterion is. An earlier version applied a
memo rule to `red-flag-tracker.xlsx` and reverted a legitimate
deliverable four times in one run.

**Measured against 28 graded memos:** 23 true blocks, **zero** false
blocks, 2 misses. It never refuses a memo LAB's judge accepted.

**One cleared item, not four.** LAB has four distractor criteria
(C-032..C-035). Only this one is checkable without false positives:
matching the others fired on legitimate passing mentions their own
criteria expressly permit — 15 on "appraisal", 12 on the
termination-for-convenience clause. Matching the red flag's *heading*
rather than its body is what produced zero false positives.

Everything else this repo can measure — addressing, issuing firm, matter
reference, cleared-items section, uncited red flags — is computed and
reported as advisory, and **gates nothing**.

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
including a crash. A run that died on an Anthropic 400 once left a run
directory with no verdict at all — the one state the contract does not
allow. An unreadable deliverable is `ESCAPED`, never a clean
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
PYTHONPATH=. python3 -c "
import json; from hook.drafting import EngagementConfig, flagged_cleared_items
c = EngagementConfig.from_dict(json.load(open('policy/engagement.json')))
print(flagged_cleared_items(open('/tmp/m.md').read(), c.cleared_items))"
```

## Layout

    policy/controls.md       the single rule (source for makeRules)
    policy/engagement.json   matter facts — advisory checks only
    hook/drafting.py         host-side counts; the only place facts are made
    hook/action_text.py      states the count as a number, one pathway
    hook/guard.py            DraftingGuard — wraps LAB's ToolExecutor
    hook/runner.py           run entry point; final_state verdict
    tests/                   81 offline tests, no network or API key
                             (also run in CI: .github/workflows/tests.yml)

## Run the tests

```bash
python3 -m unittest discover -s tests -v
```
