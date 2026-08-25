"""Every CLI flag must reach the object that acts on it.

A flag once reached config.json but never GuardConfig, so the guard ran
with a setting the run's own config claimed it had. Every unit test
passed: they build GuardConfig directly and so exercise the class, not
the wiring -- the same shape as the FakeSandbox gap.

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

    def test_policy_id_is_passed_to_guardconfig(self):
        self.assertIn("policy_id", guardconfig_kwargs())

    def test_every_policy_flag_has_a_matching_guardconfig_field(self):
        passed = guardconfig_kwargs()
        fields = set(GuardConfig.__dataclass_fields__)
        self.assertTrue(passed <= fields,
                        f"runner passes unknown GuardConfig fields: "
                        f"{sorted(passed - fields)}")

    def test_policy_flag_is_parsed(self):
        args = parse_args_from(["--model", "m", "--policy-id", "P"])
        self.assertEqual(args.policy_id, "P")


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
