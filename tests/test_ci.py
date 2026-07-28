"""The build runs one PR validation and keeps full, diagnosable coverage."""

from __future__ import annotations

import importlib.machinery
import os
import pathlib
import re
import tempfile
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "build.yml"
RUNNER = ROOT / ".knowledge" / "scripts" / "ci-suites"
LOCAL_GATE = ROOT / ".knowledge" / "scripts" / "gate"


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
        self.assertIn("sharded(found, args.shards)", self.runner)
        self.assertIn("shard: [0, 1, 2, 3, 4, 5]", self.workflow)
        parallel = re.search(r"max-parallel: (\d+)", self.workflow)
        self.assertIsNotNone(parallel)
        self.assertLessEqual(int(parallel.group(1)), 12)
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

    def test_timeout_log_contains_thread_diagnostics(self):
        loader = importlib.machinery.SourceFileLoader("ci_suites", str(RUNNER))
        runner = loader.load_module()
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            script = root / "test_hangs.py"
            script.write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
            runner.LOGS = root / "logs"
            runner.LOGS.mkdir()
            runner.ROOT = root
            runner.SUITE_TIMEOUT_SECONDS = 0.1
            _name, _code, log, timed_out = runner.run(script)
            self.assertTrue(timed_out)
            self.assertIn("Current thread", log.read_text(encoding="utf-8"))

    def test_local_gate_timeout_names_check_and_contains_thread_diagnostics(self):
        loader = importlib.machinery.SourceFileLoader("local_gate", str(LOCAL_GATE))
        gate = loader.load_module()
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            script = root / "hangs.py"
            script.write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
            gate.ROOT = root
            gate.CHECK_TIMEOUT_SECONDS = 0.1
            passed, output, elapsed = gate.run(
                "the deliberate hanging check", [gate.PY, str(script)])
            self.assertFalse(passed)
            self.assertLess(elapsed, 6)
            self.assertIn("Current thread", output)
            self.assertIn("the deliberate hanging check exceeded 0.1 seconds", output)

    def test_local_gate_timeout_ends_a_stubborn_grandchild(self):
        loader = importlib.machinery.SourceFileLoader("local_gate_group", str(LOCAL_GATE))
        gate = loader.load_module()
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            child_pid = root / "child.pid"
            script = root / "hangs_with_child.py"
            script.write_text(
                "import pathlib, signal, subprocess, sys, time\n"
                "child = subprocess.Popen([sys.executable, '-c', "
                "\"import signal,time; signal.signal(signal.SIGABRT, signal.SIG_IGN); "
                "time.sleep(30)\"])\n"
                f"pathlib.Path({str(child_pid)!r}).write_text(str(child.pid))\n"
                "time.sleep(30)\n",
                encoding="utf-8",
            )
            gate.ROOT = root
            gate.CHECK_TIMEOUT_SECONDS = 0.1
            gate.ABORT_GRACE_SECONDS = 0.1
            passed, _output, elapsed = gate.run(
                "the process-tree check", [gate.PY, str(script)])
            self.assertFalse(passed)
            self.assertLess(elapsed, 2)
            pid = int(child_pid.read_text(encoding="utf-8"))
            for _ in range(100):
                try:
                    os.kill(pid, 0)
                except ProcessLookupError:
                    break
                time.sleep(0.01)
            else:
                self.fail(f"timed-out check left grandchild {pid} running")

    def test_each_suite_is_assigned_to_exactly_one_shard(self):
        loader = importlib.machinery.SourceFileLoader("ci_shards", str(RUNNER))
        runner = loader.load_module()
        found = sorted((ROOT / "tests").glob("test_*.py"))
        assigned = [path for group in runner.sharded(found, 6) for path in group]
        self.assertEqual(sorted(assigned), found)
        self.assertEqual(len(assigned), len(set(assigned)))

    def test_supported_test_and_install_matrix_remains(self):
        for value in (
            "target: ubuntu-3.9, os: ubuntu-latest, python: '3.9'",
            "target: ubuntu-3.13, os: ubuntu-latest, python: '3.13'",
            "target: macos-3.13, os: macos-latest, python: '3.13'",
            "os: [ubuntu-latest, macos-latest]",
        ):
            self.assertIn(value, self.workflow)

    def test_one_stable_check_collects_every_required_pr_job(self):
        self.assertIn("required-pr-gate:", self.workflow)
        self.assertIn("needs: [knowledge, tests, install-this-checkout]", self.workflow)

    def test_published_release_canary_does_not_race_tag_publication(self):
        condition = self.workflow.split("  install-published-release:", 1)[1]
        condition = condition.split("    timeout-minutes:", 1)[0]
        self.assertNotIn("refs/tags/", condition)


if __name__ == "__main__":
    unittest.main()
