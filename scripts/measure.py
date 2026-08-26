"""Re-measure the guard against every memo LAB's judge has scored.

Reproduces the table in STATUS.md. Needs a harvey-labs checkout with
scored runs under results/, and pandoc. No API key, no credits.

    python3 -m scripts.measure --lab-root ~/harvey-labs
"""

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from hook.drafting import EngagementConfig, flagged_cleared_items  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
CRITERION = "C-032"
# Run ids from this project. Everything else in results/ predates it.
GUARDED_PREFIX = __import__("re").compile(r"run[D-R](_|$)")


def as_markdown(docx: Path, out: Path) -> bool:
    """Read the .docx exactly as LAB's own parser does."""
    subprocess.run(["pandoc", str(docx), "-t", "markdown", "--wrap=none",
                    "-o", str(out)], capture_output=True)
    return out.exists()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lab-root", required=True)
    ap.add_argument("--engagement",
                    default=str(REPO / "policy" / "engagement.json"))
    args = ap.parse_args()

    cfg = EngagementConfig.from_dict(json.loads(
        Path(args.engagement).read_text()))
    results = Path(args.lab_root) / "results"
    if not results.is_dir():
        raise SystemExit(f"no scored runs under {results}")

    cells = {(True, True): 0, (True, False): 0,
             (False, True): 0, (False, False): 0}
    disagreements = []
    # A run produced under any version of this guard is evidence about
    # the CHECKER, never about the baseline rate. Quoting the combined
    # denominator as a violation rate would understate the unguarded rate
    # and count this project's own runs as if they were agent behaviour.
    unguarded_total = unguarded_fail = 0
    with tempfile.TemporaryDirectory() as tmp:
        for run in sorted(p.name for p in results.iterdir() if p.is_dir()):
            memo = results / run / "output" / "red-flag-memo.docx"
            scores = results / run / "scores.json"
            if not (memo.exists() and scores.exists()):
                continue
            verdicts = {c["id"]: c["verdict"] for c in
                        json.loads(scores.read_text())["criteria_results"]}
            if CRITERION not in verdicts:
                continue
            md = Path(tmp) / f"{run}.md"
            if not as_markdown(memo, md):
                continue
            blocks = bool(flagged_cleared_items(
                md.read_text(encoding="utf-8", errors="replace"),
                cfg.cleared_items))
            judge_fails = verdicts[CRITERION] != "pass"
            if not GUARDED_PREFIX.match(run):
                unguarded_total += 1
                unguarded_fail += judge_fails
            cells[(blocks, judge_fails)] += 1
            if blocks != judge_fails:
                disagreements.append((run, blocks, judge_fails))

    total = sum(cells.values())
    print(f"{total} memos scored by LAB's judge on {CRITERION}")
    print(f"of which {unguarded_total} were written with no drafting "
          f"standard enforced, and {unguarded_fail} of those violate it "
          f"(the baseline rate)\n")
    print(f"{'':16}{'judge fails':>14}{'judge passes':>14}")
    print(f"{'guard blocks':16}{cells[(True, True)]:>14}"
          f"{cells[(True, False)]:>14}")
    print(f"{'guard permits':16}{cells[(False, True)]:>14}"
          f"{cells[(False, False)]:>14}")
    print(f"\nfalse blocks: {cells[(True, False)]}   "
          f"misses: {cells[(False, True)]}")
    for run, blocks, judge_fails in disagreements:
        print(f"  {run}: guard {'blocks' if blocks else 'permits'}, "
              f"judge {'fails' if judge_fails else 'passes'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
