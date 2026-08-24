"""Thin stdlib-only client for the Preflight API (api.icme.io/v1).

Auth via X-API-Key. JSON endpoints return dicts; SSE endpoints
(makeRules, refinePolicy) stream `data: {...}` lines and return the
final `done` event's payload.

Request/response field names follow the public quickstart:
  makeRules      {"policy": "..."}                  -> SSE, final event has policy_id
  checkItProd    {"policy_id": ..., "action": ...}  -> JSON: result SAT/UNSAT, check_id,
                                                       proof_id, verification_time_ms, ...
  verifyProof    {"proof_id": ...}                  -> JSON: valid, policy_hash,
                                                       claimed_result, verify_ms, used
Shapes for checkRelevance / explain / scenario endpoints are the same
policy_id+action pattern; confirm against live responses during the
Day 0 lifecycle test (scripts/day0_proof_lifecycle.py) before relying
on any field not listed above.
"""

import json
import os
import ssl
import time
import urllib.error
import urllib.request

DEFAULT_BASE = os.environ.get("PREFLIGHT_API_BASE", "https://api.icme.io/v1")

# Cloudflare in front of api.icme.io rejects Python-urllib's default
# User-Agent with a 403; any explicit product UA passes.
USER_AGENT = "lab-preflight/0.1"


class PreflightError(RuntimeError):
    """Base error for Preflight API failures."""


class PreflightUnreachable(PreflightError):
    """Network-level failure — the API could not be reached at all."""


class PreflightHTTPError(PreflightError):
    """Non-2xx HTTP response. 404 = proof not ready; 409 = proof consumed."""

    def __init__(self, status: int, body: bytes):
        self.status = status
        self.body = body
        try:
            self.payload = json.loads(body)
        except (ValueError, TypeError):
            self.payload = None
        super().__init__(f"HTTP {status}: {body[:500]!r}")


class PreflightClient:
    def __init__(self, api_key: str | None = None, base: str = DEFAULT_BASE,
                 timeout: float = 30.0):
        self.api_key = api_key or os.environ.get("PREFLIGHT_API_KEY")
        if not self.api_key:
            raise PreflightError(
                "No API key: pass api_key or set PREFLIGHT_API_KEY"
            )
        self.base = base.rstrip("/")
        self.timeout = timeout

    # ── low-level ──────────────────────────────────────────────────────

    def _request(self, method: str, path: str, body: dict | None = None,
                 raw: bool = False, timeout: float | None = None):
        url = f"{self.base}{path}"
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("X-API-Key", self.api_key)
        req.add_header("User-Agent", USER_AGENT)
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=timeout or self.timeout) as r:
                payload = r.read()
        except urllib.error.HTTPError as e:
            raise PreflightHTTPError(e.code, e.read()) from e
        except (urllib.error.URLError, TimeoutError, ssl.SSLError, OSError) as e:
            raise PreflightUnreachable(str(e)) from e
        if raw:
            return payload
        return json.loads(payload) if payload else {}

    def _sse(self, path: str, body: dict, timeout: float = 600.0,
             on_event=None) -> dict:
        """POST to an SSE endpoint; return the final done event's payload.

        Raises PreflightError if the stream ends with step=error or
        without a done event.
        """
        url = f"{self.base}{path}"
        req = urllib.request.Request(
            url, data=json.dumps(body).encode("utf-8"), method="POST")
        req.add_header("X-API-Key", self.api_key)
        req.add_header("User-Agent", USER_AGENT)
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "text/event-stream")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                for raw_line in r:
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if not line.startswith("data:"):
                        continue
                    try:
                        event = json.loads(line[5:].strip())
                    except ValueError:
                        continue
                    if on_event:
                        on_event(event)
                    step = event.get("step")
                    if step == "done":
                        return event
                    if step == "error":
                        raise PreflightError(f"SSE error event: {event}")
        except urllib.error.HTTPError as e:
            raise PreflightHTTPError(e.code, e.read()) from e
        except (urllib.error.URLError, TimeoutError, ssl.SSLError, OSError) as e:
            raise PreflightUnreachable(str(e)) from e
        raise PreflightError("SSE stream ended without a done event")

    # ── account / policy ──────────────────────────────────────────────

    def me(self) -> dict:
        return self._request("GET", "/me")

    def my_policies(self) -> dict:
        return self._request("GET", "/me/policies")

    def make_rules(self, policy_text: str, on_event=None) -> dict:
        """Compile plain-English rules. 300 credits. Takes minutes."""
        return self._sse("/makeRules", {"policy": policy_text},
                         timeout=900, on_event=on_event)

    def get_policy(self, policy_id: str) -> dict:
        return self._request("GET", f"/policy/{policy_id}")

    def get_scenarios(self, policy_id: str) -> dict:
        return self._request("GET", f"/policy/{policy_id}/scenarios")

    def submit_scenario_feedback(self, body: dict) -> dict:
        return self._request("POST", "/submitScenarioFeedback", body)

    def refine_policy(self, policy_id: str, on_event=None) -> dict:
        return self._sse("/refinePolicy", {"policy_id": policy_id},
                         timeout=900, on_event=on_event)

    def run_policy_tests(self, policy_id: str) -> dict:
        return self._request("POST", "/runPolicyTests",
                             {"policy_id": policy_id})

    # ── checks ────────────────────────────────────────────────────────

    def check_relevance(self, policy_id: str, action: str) -> dict:
        """Free pre-screen. Returns should_check true/false."""
        return self._request("POST", "/checkRelevance",
                             {"policy_id": policy_id, "action": action})

    def explain(self, policy_id: str, action: str) -> dict:
        """Free plain-English translation of a raw tool call."""
        return self._request("POST", "/explain",
                             {"policy_id": policy_id, "action": action})

    def check_it(self, policy_id: str, action: str) -> dict:
        """The enforcement check with proof generation. 1 credit, SSE;
        returns the done event (check_id, result, extracted, proof_id,
        proof_url, verification_time_ms, ar/llm/z3 sub-results)."""
        return self._sse("/checkIt", {"policy_id": policy_id,
                                      "action": action}, timeout=300)

    def check_it_prod(self, policy_id: str, action: str) -> dict:
        """Verdict-only check. 1 credit, plain JSON — NO check_id or
        proof_id in the live API (observed 2026-08-14), so the hook uses
        check_it() instead."""
        return self._request("POST", "/checkItProd",
                             {"policy_id": policy_id, "action": action})

    # ── proofs ────────────────────────────────────────────────────────

    def proof_meta(self, proof_id: str) -> dict:
        """Non-consuming metadata. 404 until the proof is ready."""
        return self._request("GET", f"/proof/{proof_id}")

    def proof_download(self, proof_id: str) -> bytes:
        """Download the proof binary. SINGLE-USE: consumes the proof."""
        return self._request("GET", f"/proof/{proof_id}/download", raw=True)

    def verify_proof(self, proof_id: str) -> dict:
        """Verify a proof. SINGLE-USE: consumes the proof. 409 if consumed."""
        return self._request("POST", "/verifyProof", {"proof_id": proof_id})

    def wait_for_proof(self, proof_id: str, poll_s: float = 5.0,
                       timeout_s: float = 120.0) -> dict:
        """Poll proof metadata until ready. Raises on timeout or 409."""
        deadline = time.monotonic() + timeout_s
        while True:
            try:
                return self.proof_meta(proof_id)
            except PreflightHTTPError as e:
                if e.status == 404:
                    if time.monotonic() >= deadline:
                        raise PreflightError(
                            f"proof {proof_id} not ready after {timeout_s}s"
                        ) from e
                    time.sleep(poll_s)
                    continue
                raise
