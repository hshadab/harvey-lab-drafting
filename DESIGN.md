# Design

How the guard works. For what it is and how to run it, see
[README.md](README.md); for measured results and current limits, see
[STATUS.md](STATUS.md).

## The rule

One rule, in `policy/controls.md`:

> The agent may not write a final deliverable memorandum when the number
> of already-cleared items that the memorandum raises as red flags is
> greater than zero.

The rule is generic. The list of cleared matters is engagement
configuration in `policy/engagement.json`, alongside the client and firm
names:

```json
"cleared_items": [
  {"name": "the Wyoming DEQ permit renewal (WY-HW-2019-033)",
   "pattern": "WY-HW-2019-033|wyoming[^.\n]{0,60}permit|..."}
]
```

That separation is deliberate. *Do not re-raise an item the engagement
has cleared* is a firm standard. *The Wyoming permit is fine* would be an
answer key. Every value in `engagement.json` must be discoverable in the
data room — the renewal date is stated in the environmental permit
schedule — which is the standing test for whether a value belongs there.

The rule maps to LAB's C-032, scoped as LAB scopes it: to
`red-flag-memo.docx` and nothing else.

## Where it intercepts

The guard wraps LAB's `ToolExecutor` and is passed to `run_agent()`
through a seam LAB already exposes. **Nothing in `harvey-labs` is
modified.** It uses only what the wrapped executor exposes:
`sandbox.exists/read_file/write_file/exec` and `_read_and_parse`.

Every tool call goes through the same four steps:

1. fingerprint the governed deliverable (bytes)
2. let LAB's executor run the call, whatever it is
3. fingerprint again — unchanged means nothing to do
4. if it changed, check it

This is route-independent by construction. The guard never has to
recognise *how* a file was produced, which matters because the set of
ways to write a file has no finite list: a converter, a helper script, a
shell heredoc, `python3 -c`, `make`, an editor. A test asserts the
property directly by making a deliverable appear from `make memo` — a
command the guard has no rule for — and confirming it is caught.

A cheaper pre-check also runs on commands the guard *does* recognise as
converting a source into the deliverable. It gives the agent feedback
before the file exists, which is easier to act on. It is ergonomics, not
the guarantee.

## What gets checked

When the deliverable changes, the guard:

1. reads it through LAB's own `_read_and_parse`, so the check sees
   exactly what LAB's grader sees. For `.docx` that runs
   `pandoc -t markdown --wrap=none` **inside the sandbox** — agent-written
   binaries are never parsed on the host.
2. splits the document into red-flag entries, excluding any
   items-reviewed-and-cleared section. A memo is *supposed* to discuss a
   cleared matter there, and LAB's criterion expressly permits it.
3. matches each entry — heading and body together — against the cleared
   patterns.
4. **If the document cannot be split into entries at all, the whole
   document is examined instead**, minus its cleared-items sections. A
   check that approves whatever it cannot parse is not a check.

Matching the whole entry rather than its heading matters: the heading is
the part the agent chooses, and an entry titled "Casper Facility Permit"
whose body discusses the Wyoming permit is the same violation. The
pattern carries its own precision instead — a bare place name is not
enough, because "Ramirez v. RES (D. Wyoming)" is a court, not a permit.

## What the solver is told

`hook/action_text.py` renders the computed facts as an action string.
Every sentence in it is a fact `hook/drafting.py` actually computed;
nothing is a stock assurance. The proof bakes in whatever the string
claims, so a template that asserted something unchecked would produce a
correct ruling on false testimony.

```
The agent writes the final deliverable memorandum red-flag-memo.docx of
the diligence review. This action is writing a final deliverable
memorandum. The number of already-cleared items that the memorandum
raises as red flags is 1. Because 1 is greater than zero, the memorandum
raises at least one already-cleared item as a red flag. Therefore
writing this final deliverable memorandum is permitted.
```

The last sentence is what makes the check meaningful: the action asserts
permission, and the solver tests whether that is consistent with the
rules. The compiled policy declares an integer for the count and a
boolean for the permission, and refuses the write when the count exceeds
zero.

Two conventions matter for the policy to compile into something that
enforces:

* **Action-shaped, with a count.** Give the extractor an actor, a verb,
  an object and a number. Rules phrased as properties of a document
  compile to free-floating booleans the extractor never binds, and the
  resulting policy permits everything while looking healthy.
* **One rule per policy.** The extractor defaults an integer it cannot
  find in the action text to zero, so a second rule's variable can be
  bound by an action that says nothing about it, and its conclusion can
  contradict the action's own. One standard, one policy, one set of
  variables.

## On a refusal

The deliverable does not survive. `_revert` restores the previous bytes,
or deletes the file if there was none, then **confirms the filesystem
afterwards** — `not exists()` after a delete, a byte comparison after a
restore — and returns whether the revert actually happened. A revert that
fails records `REVERT-FAILED` in the ledger and tells the agent the file
must not be delivered. There is no path where enforcement fails quietly.

The agent is told which cleared matter it raised, and never how the check
works. Naming the matter is what a partner would do; naming the mechanism
would teach renaming rather than fixing.

Reverting after the fact is the right semantics for a work-product
standard: the standard is about what is *issued*, and a rejected draft on
a desk breaks no control. It would be the wrong semantics for an
exfiltration rule, where a transmitted byte cannot be recalled and
prevention must come first.

## How a run ends

The deliverable of this system is *a conforming memorandum, or a visible
refusal with a reason* — never *silently absent*. A run does not infer
its outcome from the ledger; it reads the artifact:

| verdict | meaning |
|---|---|
| `DELIVERED` | a conforming deliverable exists |
| `REFUSED` | nothing was issued, and the run says so |
| `ESCAPED` | something non-conforming survived — **the guarantee failed** |

Written to `final_state.json` and printed as a banner on every exit path,
including a crash, where the detail line names the exception so a dropped
connection cannot be mistaken for an enforcement refusal. A deliverable
that cannot be read is `ESCAPED`, never a clean refusal.

## The receipt

`runs/<id>/ledger.md` records every check that ruled: the action, the
verdict, the `check_id`, the solver time, and the proof id. Decisions
are keyed on the deterministic solver result rather than the combined
verdict, because that is the computation the proof attests.

## Testing

80 offline tests, no network and no API key, run in CI on 3.10 and 3.12
along with `pyflakes`.

Two conventions worth keeping:

* **Fakes are pinned to the real classes.** `TestSandboxContract`
  compares `FakeSandbox`'s signatures to LAB's `Sandbox` via
  `inspect.signature`. A fake more permissive than the thing it fakes is
  not a test.
* **Wiring is tested, not just classes.** `tests/test_runner_wiring.py`
  parses `runner.py` and checks that every flag it accepts reaches the
  `GuardConfig(...)` call, because tests that construct `GuardConfig`
  directly exercise the class and never the wiring.

Documents that once defeated the check are kept as regression fixtures,
so the shapes that mattered cannot silently stop being covered.
