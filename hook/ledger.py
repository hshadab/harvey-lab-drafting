"""The receipt ledger — one entry per intercepted tool call.

Written as JSONL during the run (crash-safe), consolidated to
ledger.json afterward, and rendered to a markdown table for the video
and the README.
"""

import json
from datetime import datetime, timezone
from pathlib import Path


class Ledger:
    def __init__(self, path: str | Path, append: bool = False):
        """One ledger per run. Truncates by default.

        This opened in "a" mode, which silently merged runs whenever a
        run id was reused: re-running runB_r1 appended to the previous
        runB_r1's ledger, producing a receipt trail describing two runs
        as one (observed 2026-08-17 — 47 stale entries plus 6 new). A
        receipt trail that does not correspond to a single run is worse
        than none, because it still looks authoritative. `seq` numbering
        also restarts at 1 per Ledger, so a merged file has duplicate
        sequence numbers.

        Pass append=True only to deliberately resume an interrupted run.
        """
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._f = open(self.path, "a" if append else "w", encoding="utf-8")
        self.entries: list[dict] = []

    def record(self, *, tool: str, summary: str, action_text: str,
               result: str, check_id: str | None = None,
               detail: str | None = None,
               verification_time_ms: float | None = None,
               proof_id: str | None = None, proof_url: str | None = None,
               proof_status: str | None = None) -> dict:
        """result: SAT | UNSAT | SKIPPED | OUTAGE-BLOCKED"""
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "seq": len(self.entries) + 1,
            "tool": tool,
            "summary": summary,
            "action_text": action_text,
            "result": result,
            "check_id": check_id,
            "detail": detail,
            "verification_time_ms": verification_time_ms,
            "proof_id": proof_id,
            "proof_url": proof_url,
            "proof_status": proof_status or ("pending" if proof_id else None),
        }
        self.entries.append(entry)
        self._f.write(json.dumps(entry) + "\n")
        self._f.flush()
        return entry

    def close(self):
        self._f.close()

    def __del__(self):
        try:
            self._f.close()
        except Exception:
            pass

    def consolidate(self, json_path: str | Path):
        counts = {}
        for e in self.entries:
            counts[e["result"]] = counts.get(e["result"], 0) + 1
        Path(json_path).write_text(json.dumps({
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "totals": counts,
            "entries": self.entries,
        }, indent=2), encoding="utf-8")


def load_entries(jsonl_path: str | Path) -> list[dict]:
    entries = []
    for line in Path(jsonl_path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            entries.append(json.loads(line))
    return entries


def render_markdown(entries: list[dict],
                    receipts_dir: str | Path | None = None) -> str:
    """Render the ledger as a markdown table.

    The proof column shows the proof id and, when its binary is present in
    `receipts_dir`, an `(archived)` marker — the on-disk ground truth.
    In-flight/transient states are not narrated: the ledger's job is to
    show that every action was checked (check_id + verdict) and which
    proofs are on hand. Reviewers mint and verify their own proof
    (verify_yourself.md), since archived proofs are single-use.
    """
    receipts = Path(receipts_dir) if receipts_dir else None
    lines = [
        "| # | action | result | check_id | time (ms) | proof |",
        "|---|--------|--------|----------|-----------|-------|",
    ]
    for e in entries:
        pid = e.get("proof_id")
        proof = "—"
        if pid:
            on_disk = (receipts and (receipts / f"{pid}.proof.bin").exists()) \
                or e.get("proof_status") == "consumed-by-download"
            proof = f"{pid} (archived)" if on_disk else pid
        result = e["result"]
        badge = {"SAT": "✅ SAT", "UNSAT": "🛑 UNSAT",
                 "SKIPPED": "· skipped", "OUTAGE-BLOCKED": "⚠️ outage"}.get(
                     result, result)
        summary = e["summary"].replace("|", "\\|")
        if len(summary) > 80:
            summary = summary[:80] + "…"
        ms = e.get("verification_time_ms")
        lines.append(
            f"| {e['seq']} | {summary} | {badge} | {e.get('check_id') or '—'} "
            f"| {ms if ms is not None else '—'} | {proof} |")
    return "\n".join(lines) + "\n"
