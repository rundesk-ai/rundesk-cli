"""The build runs one PR validation and keeps full, diagnosable coverage."""

from __future__ import annotations

import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "build.yml"
RUNNER = ROOT / ".knowledge" / "scripts" / "ci-suites"


class FastPullRequestFeedback(unittest.TestCase):
    def setUp(self):
        self.workflow = WORKFLOW.read_text(encoding="utf-8")
        self.runner = RUNNER.read_text(encoding="utf-8")

    def test_review_branches_are_not_built_by_both_push_and_pull_request(self):
        push = self.workflow.split("  pull_request:", 1)[0]
        self.assertIn("branches: [main]", push)
        self.assertIn("pull_request:", self.workflow)

    def test_pull_request_concurrency_follows_the_pull_request_not_its_merge_ref(self):
        self.assertIn("github.event.pull_request.number || github.ref", self.workflow)
        self.assertIn("cancel-in-progress: true", self.workflow)

    def test_every_suite_is_discovered_and_parallelism_is_bounded(self):
        self.assertIn('glob("test_*.py")', self.runner)
        workers = re.search(r"^WORKERS = (\d+)$", self.runner, re.MULTILINE)
        self.assertIsNotNone(workers)
        self.assertLessEqual(int(workers.group(1)), 6)
        timeout = re.search(
            r"^SUITE_TIMEOUT_SECONDS = (\d+)$", self.runner, re.MULTILINE
        )
        self.assertIsNotNone(timeout)
        self.assertLessEqual(int(timeout.group(1)), 180)

    def test_each_suite_keeps_its_own_log_and_names_failures(self):
        self.assertIn('f"{path.stem}.log"', self.runner)
        self.assertIn("::error title={name}", self.runner)
        self.assertIn("failed suites:", self.runner)
        self.assertIn("actions/upload-artifact@v4", self.workflow)
        self.assertIn("if: always()", self.workflow)

    def test_supported_test_and_install_matrix_remains(self):
        for value in (
            "{ os: ubuntu-latest, python: '3.9' }",
            "{ os: ubuntu-latest, python: '3.13' }",
            "{ os: macos-latest, python: '3.13' }",
            "os: [ubuntu-latest, macos-latest]",
        ):
            self.assertIn(value, self.workflow)

    def test_one_stable_check_collects_every_required_pr_job(self):
        self.assertIn("required-pr-gate:", self.workflow)
        self.assertIn("needs: [knowledge, tests, install-this-checkout]", self.workflow)


if __name__ == "__main__":
    unittest.main()
