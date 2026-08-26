# harvey-lab-drafting — closing the gap a better prompt cannot close

A firm rule, enforced automatically on an AI agent's work product, with a
receipt for every decision. Built on a stock task from Harvey's
open-source Legal Agent Benchmark (LAB). LAB is unmodified. Not
affiliated with or endorsed by Harvey.

Current state, results, and known limits: **[STATUS.md](STATUS.md)**.

## In plain English

Harvey's benchmark hands an AI agent a folder of deal documents and asks
it to write a memo listing the problems it found.

One of the things Harvey grades is whether the agent **avoids** raising a
non-issue. There is a Wyoming permit in the data room that looks expired,
but the renewal was filed on time, so it is not a problem. A memo that
writes it up as a red flag — rates it MEDIUM, recommends a closing
condition — is a junior lawyer crying wolf to a partner about a matter
the partner already settled.

**Every one of the 18 memos written without a drafting standard
enforced gets this wrong. 18 of 18.**

So this project puts a gate in front of the agent. Every time it tries to
produce the memo, our code reads the finished document and checks whether
that settled matter is being written up as a problem. If it is, the file
is deleted and the agent is told which matter it raised. Every decision —
allowed or refused — is checked by a solver and recorded with a receipt.

In the reference run the agent was refused four times before it produced
a memo that met the standard. Harvey's own grader then confirmed the
result independently.

### Why not just tell the agent in the prompt?

Because this kind of rule is not the kind a prompt closes.

A rule that says *include a summary* is finished by one deliberate act,
and the agent can see whether it did it. A rule that says *never raise
this matter* has no such moment. It has to hold across every red flag in
the memo, it pulls directly against the task's own instruction to find
red flags, and one slip is a failure.

The reference run shows it plainly: the agent fixed the memo, and then
**raised the same settled matter again later in the run** and had to be
blocked twice more. A one-time correction did not stick. A check that
runs on every attempt did.

## How it works, step by step

1. **The rule is written in English** in `policy/controls.md` and
   compiled once by Preflight into formal logic. The compiled policy has
   a variable for the number of already-cleared matters the memo raises,
   and a rule refusing the write when that number exceeds zero.
2. **The agent works normally** inside LAB's sandbox. Nothing in
   `harvey-labs` is modified; the guard is passed in through a seam LAB
   already exposes.
3. **After every tool call**, the guard checks whether the deliverable
   changed. If it did not, nothing happens.
4. **If it changed**, the guard reads the actual `.docx` through LAB's
   own parser, counts the cleared matters raised as red flags, and states
   that count as a plain fact.
5. **Preflight's solver rules on that fact.** Zero cleared matters →
   allowed. One or more → refused.
6. **On a refusal the file is removed**, and the agent is told which
   matter it raised — never how the check works, which would teach it to
   rename rather than fix.
7. **The run ends by reading what is on disk** and printing one of
   `DELIVERED`, `REFUSED`, or `ESCAPED`. `ESCAPED` means something
   non-conforming survived and the guarantee failed.

The receipt for every check lands in `runs/<id>/ledger.md`.

## Run it yourself

Needs a checkout of [harvey-labs](https://github.com/harveyai/harvey-labs),
an Anthropic key for the agent, and an ICME key for the checks.
`policy/policy.json` already holds a compiled policy id, so there is no
need to spend the 300 credits recompiling.

```bash
export ANTHROPIC_API_KEY=...      # the agent
export PREFLIGHT_API_KEY=...      # the checks

PYTHONPATH=. uv run --project ../harvey-labs python -m hook.runner \
    --lab-root ../harvey-labs \
    --model anthropic/claude-haiku-4-5 \
    --task corporate-ma/review-data-room-red-flag-review \
    --policy-id "$(python3 -c "import json;print(json.load(open('policy/policy.json'))['policy_id'])")" \
    --run-id myrun --no-briefing
```

The run ends by printing `DELIVERED`, `REFUSED` or `ESCAPED` and writing
`runs/myrun/final_state.json`. `runs/myrun/ledger.md` is the receipt for
every check.

Flags worth knowing:

* `--no-briefing` — do not state the standard in the system prompt. Use
  this when testing enforcement; a briefed agent mostly complies and the
  gate never fires.
* `--bare-blocks` — refuse without saying why. A test of whether
  enforcement holds when the agent is told nothing, not a deployment
  mode: measured, the agent does not recover from it (see STATUS).

A run costs roughly \$1 on `claude-haiku-4-5` and \$9 on
`claude-sonnet-4-6`; almost all of it is LAB re-sending the document set
each turn.

### Look at a recorded run instead — no keys, no cost

Five runs are committed under `runs/`. The reference one is `runR_r1`.

One of the five, `runM_r1`, reports `ESCAPED` — a memo that got past the
check. It is kept on purpose: it is the run that exposed a real defect
(the check matched a red flag's heading, so retitling an entry defeated
it), the fix is `4b105dd`, and the document is now a regression fixture.
[STATUS.md](STATUS.md) has the detail. Every run since is clean.

```bash
cat runs/runR_r1/final_state.json        # the verdict
grep verify: runs/runR_r1/ledger.md      # every check that ruled
```

Each row carries a `check_id` and a proof id, so a decision can be
re-verified against Preflight later:

```
| 22 | verify: red-flag-memo.docx | 🛑 UNSAT | fe131e55-… | 5874 | fd03d727-… |
| 27 | verify: red-flag-memo.docx | ✅ SAT   | 6aa199b2-… | 5202 | 18c192a4-… |
```

Its ledger shows four refusals and two passes. The interesting part is
the order — refused, refused, passed, **refused, refused**, passed. The
agent fixed the memo and then raised the settled matter again later in
the same run.

To read the delivered memo the way the check reads it:

```bash
pandoc runs/runR_r1/output/red-flag-memo.docx -t markdown --wrap=none -o /tmp/m.md
PYTHONPATH=. python3 -c "
import json; from hook.drafting import EngagementConfig, flagged_cleared_items
c = EngagementConfig.from_dict(json.load(open('policy/engagement.json')))
print(flagged_cleared_items(open('/tmp/m.md').read(), c.cleared_items))"
```

An empty list means no cleared matter was raised as a red flag. Anything
printed is a violation. Do not use a hand-rolled XML reader on the
`.docx` — Word keeps structure the plain text does not show, and it will
mislead you.

### Run the checks CI runs

```bash
python3 -m unittest discover -s tests -v          # 80 tests, no network
uv run --with pyflakes python -m pyflakes hook tests scripts
```

## Why this rule, and not a formatting rule

Harvey's rubric, verbatim from
`harvey-labs/tasks/corporate-ma/review-data-room-red-flag-review/task.json`:

> **C-032 — "DISTRACTOR_001: Does not flag Wyoming permit as a red flag"**
> *PASS if the memo either (a) does not flag the Wyoming DEQ permit
> (WY-HW-2019-033) expiration as a red flag, or (b) affirmatively
> explains that the timely filed renewal application allows continued
> operations. **FAIL if the memo flags the Wyoming permit expiration as a
> material red flag or recommends remedial action beyond routine
> monitoring.***

Most of LAB's fifty criteria are requirements — *include* this, *cite*
that. Those are the ones a prompt can mostly close, and measurement bears
it out: the criteria specific enough to check mechanically are the ones
agents already satisfy.

Prohibitions behave differently, and that is what makes this one worth
gating:

* **No single moment of compliance.** It must hold across every red flag
  the memo raises. One slip is a failure.
* **It competes with the task's own instruction.** The agent was told to
  find red flags. The Wyoming permit looks like one. The tension is
  structural, not a lapse of attention.
* **A prompt raises the rate; it never reaches 100%.** At a 40% failure
  rate you notice in a day. At 1% you never notice — and an agent taking
  10,000 actions a month sends out 100 bad deliverables.
* **The failures look exactly like the successes.** A memo that raises
  one non-issue among fourteen real ones reads fine. Nobody audits a
  rubric line by line.

A prompt is a request. A check is a gate. And a gate leaves a receipt.

## What this does not claim

The claim is **not** "the guard makes the agent write better memos".
That is statistical, model-dependent, and expires at the next model
upgrade. The claim is *this artifact was checked against the firm's
standard and did not leave the sandbox* — per-artifact, with a receipt.

So a lower LAB score under enforcement is not a defect. A refusal that
produces nothing scores zero on the memo criteria and is still the
correct outcome: an associate who cannot meet the standard hands the
partner nothing, and the partner finds out.

The gate makes the system **safe**; explaining the refusal makes it
**useful**. Both were measured separately — see
[STATUS.md](STATUS.md).

**Design details:** [DESIGN.md](DESIGN.md).

## Layout

    README.md                what this is, and how to run it
    DESIGN.md                how the guard works
    STATUS.md                measured results and known limits

    policy/controls.md       the single rule (source for makeRules)
    policy/engagement.json   matter facts, incl. the cleared-items list
    policy/policy.json       the compiled policy id
    hook/drafting.py         host-side facts; the only place facts are made
    hook/action_text.py      states those facts as testimony, one pathway
    hook/guard.py            DraftingGuard — wraps LAB's ToolExecutor
    hook/runner.py           run entry point; final_state verdict
    runs/                    recorded runs, ledgers and deliverables
    tests/                   80 offline tests, no network or API key
                             (also run in CI: .github/workflows/tests.yml)

