# harvey-lab-drafting — enforcing a firm's drafting standards before the memo is issued

Companion to [harvey-lab-preflight](https://github.com/hshadab/harvey)
(conduct enforcement — privilege). Same machinery, different question.

That demo asks: *can you stop an agent doing something a firm forbids?*
This one asks: **can you guarantee a property of the work product instead
of grading it afterwards?**

Built on Harvey's open-source Legal Agent Benchmark (LAB), MIT licensed,
unmodified. Not affiliated with or endorsed by Harvey.

## The idea

LAB grades a diligence memo against 50 criteria *after* the agent
finishes. Some of those criteria are **structural** — properties of the
document, checkable without knowing any right answers. Those can be
enforced *before* the deliverable is written, which turns a hoped-for
property into a guaranteed one.

| Standard enforced here | Memos failing it (of 17 recorded) |
|---|---|
| Addressed to the engagement client, from the issuing firm, referencing the matter | **7 / 17** |
| Contains a section recording what was reviewed and cleared | **17 / 17** |

Not because the agent can't do these. Because nobody asked, and it didn't
infer them. A firm's drafting standards live in a style guide, not in the
task prompt — which is exactly the gap a policy layer is for.

Corroboration for the second one: LAB's C-032 asks the memo *not* to flag
a permit whose renewal was timely filed, and that fails 17/17 too. The
agent flags it. That item is precisely what belongs in a cleared-items
section — the same missing habit, showing up twice in the rubric.

### One criterion we deliberately do not chase

LAB's **C-045** wants the memo addressed to the right parties *and*
referencing "the January 24, 2025 investment committee meeting." That date
appears **nowhere in the 13 data room documents** — only inside
`task.json`'s own criteria. Verify it yourself:

```bash
cd ~/harvey-labs/tasks/corporate-ma/review-data-room-red-flag-review
for f in documents/*.docx; do pandoc "$f" -t plain | grep -il "january 24, 2025"; done   # no hits
grep -c "January 24, 2025" task.json                                                     # 1
```

No agent can reference a date absent from its inputs, which is why C-045
reads 0/17 and always will. So this repo enforces the **achievable half**
— addressed to the client, from the firm, naming the matter — and lets the
criterion keep failing. Building a demo whose headline win is "we passed
an unsatisfiable criterion" would be worthless.

That has a useful consequence for reading the results: after enforcement,
memos will be correctly addressed **and C-045 will still fail**. That gap
is the cleanest available demonstration that the criterion, not the agent,
is the broken part.

## Whose rule is this?

The rules in `policy/controls.md` are written as generic firm drafting
standards. **The rule is generic; the engagement supplies the specifics.**

"Every memo is addressed to the engagement client" is a drafting standard.
"Every memo is addressed to Sycamore Capital Partners" is an answer key.
`hook/drafting.py` implements only the former; who the client is arrives
through `EngagementConfig`, exactly as it would from a matter record in a
real deployment.

The line held throughout: enforce **structure**, never **content**. We
check that a cleared-items section exists — never that it clears the right
items. Anything requiring the answer key is out of scope by construction,
and `tests/test_drafting.py::test_no_answer_key_dependence` pins that: a
memo whose analysis is nonsense still passes, because the standard is
about the document, not the diligence.

## What we could not enforce — and why that matters

LAB's **C-039** ("each red flag cites a specific source document") looked
like the best target of all: structural in appearance, and failing in 8 of
17 runs. It is not in the shipped policy.

Enforcing it needs a reliable split of free prose into discrete red flags.
Three implementations were tried against 17 real memos:

1. Match data-room **filenames** — memos cite by human title and
   abbreviation ("QofE Data Package", "CIM"), so 21 of 22 correctly-cited
   flags scored as uncited.
2. Add **source-attribution lines** (`Source:`, `See`, `Per`) — better,
   but numbered *Required Action* items inside each flag were read as new
   flags, splitting a 22-flag memo into 42 fragments, most without a
   `Source:` line.
3. Detect the document's own **heading convention** first — fixed the one
   memo it was tuned on, and still disagreed with LAB's judge on 10 of 17.

Meanwhile the two shipped checks agree with LAB's judge **17 out of 17**
on both criteria.

So C-039 is measured and reported as an advisory signal, and deliberately
excluded from `compliant()`. Enforcing a check that does not reproduce the
standard it claims to enforce is precisely the failure this project exists
to avoid — a hook that asserts a property it has not honestly computed is
how the conduct demo's Rule 2 got bypassed
([BATTLE-TEST-FINDINGS §6](https://github.com/hshadab/harvey/blob/main/BATTLE-TEST-FINDINGS.md)).

**The general finding: not every rubric criterion is enforceable
pre-action.** Some need semantic judgement a host-side check cannot make
honestly. Knowing which is which is the engineering, and a demo that
claimed all 50 were enforceable would be lying.

## How it works

1. The agent drafts the memo inside LAB's own harness, unmodified.
2. Before the deliverable is written, `hook/drafting.py` computes the
   facts the rules need — nothing more, nothing assumed.
3. `hook/action_text.py` states each computed fact as a standalone
   sentence and frames exactly one rule pathway.
4. Preflight's solver rules on those facts and returns a receipt.
5. On a block, the agent is told **which element is missing** and revises.
   A bare refusal produces thrash; a specific one produces a fix.

## Status: enforcing correctly, first run pending

Policy **`0a0dc635-3fc2-4cd8-87fc-6bfa0064a45a`** compiled and probed
**4/4 green** — every violating draft is blocked, the compliant one is
permitted:

| Probe | Expected | Solver | Extracted |
|---|---|---|---|
| compliant memo | SAT | SAT | clients 1, firms 2, matter 1, cleared 1 |
| no cleared-items section | UNSAT | **UNSAT** | all four counts bound |
| no address block | UNSAT | **UNSAT** | all four counts bound |
| no matter reference | UNSAT | **UNSAT** | all four counts bound |

### It took two compiles, and the difference is the lesson

Version 1 (`e32fce7b`, kept as `policy/*-v1-inert.json`) phrased rules as
**properties of a document**: *"a memorandum containing no cleared-items
section is forbidden."* It compiled to five variables — four free-floating
`Bool`s and a conclusion. The extractor bound **only the conclusion** on
every check, so nothing constrained the system, and all three violating
probes returned SAT. Valid SMT, faithful to the English, completely inert.

Version 2 phrases the same standards as **actions with counts**: *"the
agent may not write a final deliverable memorandum when the number of
cleared-items sections is zero."* Same five variables — but now `Int`
counts rather than `Bool` adjectives:

    numClearedItemsSections              Int
    numEngagementClientsInAddressBlock   Int
    numIssuingFirmsInAddressBlock        Int
    numReferencesToEngagementMatter      Int
    isWriteFinalDeliverableMemorandumAllowed  Bool

And the action text states each quantity as a standalone number
("The number of cleared-items sections the memorandum contains is 0")
rather than asserting an adjective. All four now bind.

**Adjectives do not ground; numbers do.** Two action-text rewrites against
version 1 both scored 1/4 — the problem was never the variable names, it
was that there was nothing quantitative for the extractor to attach to.

**And it fails silently.** The bad compile reported success, returned SAT
on every check, and would have produced a clean-looking run in which
nothing was ever enforced. Only an adversarial probe of a case that
*should* block revealed it. That is the whole argument for the recording
gate: ~12 credits caught a dead policy twice before any run was spent
against it.

### Predictions, recorded before the first run

* **C-041 (cleared-items section) goes 0/17 to passing** — +1 of 50, and
  it may drag **C-032** (the Wyoming permit distractor, also 0/17) with
  it, since that item is what belongs in a cleared-items section.
* **C-045 stays failing** by design — its IC meeting date is unobtainable
  from the data room. If it passes, our reading is wrong and this is the
  record of that.
* Addressing improves on the 7 of 17 memos that currently lack it.
* If block-and-revise costs more elsewhere than it gains, that is the
  finding and it goes here.

## Layout

    policy/controls.md      the drafting standards (source for makeRules)
    policy/engagement.json  matter facts — what keeps the rules generic
    hook/guard.py           DraftingGuard — wraps LAB's ToolExecutor
    hook/runner.py          run entry point (no proof sweep, by design)
    hook/drafting.py        host-side checks — the only place facts are computed
    hook/action_text.py     per-action strings; states only what was computed
    hook/preflight_client.py, hook/ledger.py   shared with harvey-lab-preflight
    tests/test_drafting.py  check logic — offline, no network or API key
    tests/test_guard.py     guard wiring — faked client + executor

## Run the tests

```bash
python3 -m unittest discover -s tests -v
```
