"""Every CLI flag must reach the object that acts on it.

runK_r1 blocked a conforming tracker four times because
--tracker-policy-id was parsed, recorded in config.json, and never passed
into GuardConfig. Every unit test passed: they built GuardConfig
directly and so exercised the class, not the wiring. Same shape as the
FakeSandbox gap -- the tests checked the part that was right.

This compares the runner's argparse flags against the GuardConfig fields
it populates, without a sandbox, an API key, or a container.
"""

import argparse
import ast
import unittest
from pathlib import Path

from hook.guard import GuardConfig
from hook.runner import parse_args

RUNNER = Path(__file__).resolve().parent.parent / "hook" / "runner.py"


def guardconfig_kwargs() -> set[str]:
    """The keyword names the runner passes to GuardConfig(...)."""
    tree = ast.parse(RUNNER.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "GuardConfig"):
            return {kw.arg for kw in node.keywords if kw.arg}
    raise AssertionError("no GuardConfig(...) call found in runner.py")


class TestPolicyFlagsReachTheGuard(unittest.TestCase):

    def test_tracker_policy_id_is_passed_to_guardconfig(self):
        self.assertIn("tracker_policy_id", guardconfig_kwargs(),
                      "--tracker-policy-id was parsed and written to "
                      "config.json but never passed to the guard, so the "
                      "tracker was checked against the memorandum policy")

    def test_policy_id_is_passed_to_guardconfig(self):
        self.assertIn("policy_id", guardconfig_kwargs())

    def test_every_policy_flag_has_a_matching_guardconfig_field(self):
        passed = guardconfig_kwargs()
        fields = set(GuardConfig.__dataclass_fields__)
        self.assertTrue(passed <= fields,
                        f"runner passes unknown GuardConfig fields: "
                        f"{sorted(passed - fields)}")

    def test_policy_flags_are_parsed(self):
        args = parse_args_from(["--model", "m", "--policy-id", "P",
                                "--tracker-policy-id", "T"])
        self.assertEqual(args.policy_id, "P")
        self.assertEqual(args.tracker_policy_id, "T")

    def test_tracker_policy_defaults_to_none_not_the_memo_policy(self):
        """Absent a tracker policy the tracker is ungoverned, never
        checked against another rule's policy."""
        args = parse_args_from(["--model", "m", "--policy-id", "P"])
        self.assertIsNone(args.tracker_policy_id)


def parse_args_from(argv):
    import sys
    old = sys.argv
    sys.argv = ["runner"] + argv
    try:
        return parse_args()
    finally:
        sys.argv = old


if __name__ == "__main__":
    unittest.main()
