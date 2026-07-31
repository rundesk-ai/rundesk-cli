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
        self.assertIn("actions/upload-artifact@v7", self.workflow)
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
            # Leave enough time for a loaded macOS runner to start the fixture and write
            # the grandchild handshake. The check is about ending an existing process
            # tree, not whether a fresh Python interpreter starts within 100 ms.
            gate.CHECK_TIMEOUT_SECONDS = 1
            gate.ABORT_GRACE_SECONDS = 0.1
            passed, _output, elapsed = gate.run(
                "the process-tree check", [gate.PY, str(script)])
            self.assertFalse(passed)
            self.assertLess(elapsed, 3)
            self.assertTrue(child_pid.is_file(), "the fixture never spawned its grandchild")
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
        self.assertIn(
            "needs: [knowledge, tests, install-this-checkout, upgrade-existing-install]",
            self.workflow,
        )

    def test_ci_checks_the_published_install_archive_once(self):
        activity = self.workflow.split("  verify-published-install-archive:", 1)[1]
        activity = activity.split(
            "  # ------------------------------------------------------------------ the knowledge base", 1
        )[0]
        asset = (
            "https://github.com/rundesk-ai/rundesk-cli/releases/latest/download/"
            "rundesk-cli.tar.gz"
        )
        self.assertEqual(
            activity.count(asset),
            1,
            "the published install archive check must fetch the artifact once",
        )
        self.assertEqual(
            activity.count('curl -fsSL "$asset" -o "$archive"'),
            1,
            "the published install archive check fetched the artifact more than once",
        )
        self.assertIn('tar -tzf "$archive"', activity)
        self.assertNotIn("matrix:", activity, "CI activity was multiplied by a test matrix")
        installer = (ROOT / "install.sh").read_text(encoding="utf-8")
        cutoff = re.search(r'^COUNTED_DELIVERY_SINCE="([^"]+)"$', installer, re.MULTILINE)
        self.assertIsNotNone(cutoff)
        self.assertIn(f'ARCHIVE_REQUIRED_SINCE: "{cutoff.group(1)}"', activity)
        self.assertIn("the published install archive is missing or invalid", activity)

    def test_the_installed_dependency_runs_the_discord_footer_regression(self):
        installed = self.workflow.split("  install-this-checkout:", 1)[1]
        installed = installed.split("  # ------------------------------------------------------------------ upgrading", 1)[0]
        self.assertIn(
            ".venv/bin/python tests/test_discord.py "
            "WhatOneTurnLooksLike.test_the_footer_omits_cache_writes_the_seam_hands_over",
            installed,
            "CI never runs the footer regression with discord.py installed",
        )

    def test_ci_builds_and_installs_the_exact_release_archive(self):
        installed = self.workflow.split("  install-this-checkout:", 1)[1]
        installed = installed.split("  # ------------------------------------------------------------------ upgrading", 1)[0]
        release = (ROOT / ".github" / "workflows" / "release.yml").read_text(
            encoding="utf-8"
        )
        command = (
            'git archive --format=tar --prefix="rundesk-cli-${GITHUB_REF_NAME}/" '
            '"$GITHUB_SHA" |'
        )
        self.assertIn(command, release)
        self.assertIn(command, installed)
        self.assertIn(
            '"$archive_root/install.sh" --uninstall',
            installed,
            "CI installs the release archive but never proves it can be removed",
        )

    def test_every_pull_request_verifies_fresh_installs_and_upgrades_from_the_latest_release(self):
        """R-INS-16"""
        self.assertIn("install-this-checkout:", self.workflow)
        upgrade = self.workflow.split("  upgrade-existing-install:", 1)[1]
        self.assertIn("git describe --tags --abbrev=0 HEAD^", upgrade)
        self.assertIn("updater._copy_over", upgrade)
        self.assertIn('update --after-replacing ""', upgrade)
        self.assertIn("owner-kept.txt", upgrade)
        self.assertIn("serve existing", upgrade)

    def test_install_gates_use_the_local_default_catalog_fixture(self):
        """R-INS-16 — GitHub's anonymous API quota cannot decide whether a PR passes."""
        source = (
            "RUNDESK_DEFAULT_SKILLS_SOURCE: "
            "${{ github.workspace }}/tests/fixtures/default-catalog"
        )
        fresh = self.workflow.split("  install-this-checkout:", 1)[1]
        fresh = fresh.split("  # ------------------------------------------------------------------ upgrading", 1)[0]
        upgrade = self.workflow.split("  upgrade-existing-install:", 1)[1]
        upgrade = upgrade.split(
            "  # ------------------------------------------------------------------ installing what is published", 1
        )[0]
        self.assertIn(source, fresh)
        self.assertIn(source, upgrade)

    def test_every_workflow_pins_one_major_of_each_action_it_shares(self):
        """Build and release both check out and set Python up, and the two drifting apart
        is how a release job goes on running a runtime the build stopped exercising. Every
        action here was forced onto Node 24 by the runner while the workflows still asked
        for the Node 20 majors, and nothing said so but an annotation nobody opened.

        Read off the files rather than compared with a list of expected versions: a list of
        action versions kept beside the workflows is a second copy that disagrees with them
        the first time one is bumped."""
        used = {}
        for path in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
            for action, major in re.findall(
                r"uses:\s*([\w.-]+/[\w.-]+)@v(\d+)", path.read_text(encoding="utf-8")
            ):
                used.setdefault(action, {}).setdefault(major, []).append(path.name)
        self.assertTrue(used, "no workflow names an action at all")
        for action, majors in sorted(used.items()):
            self.assertEqual(
                1, len(majors),
                f"{action} is pinned at {sorted(majors)} across {sorted(used[action])}",
            )

    def test_published_release_canary_does_not_race_tag_publication(self):
        condition = self.workflow.split("  install-published-release:", 1)[1]
        condition = condition.split("    timeout-minutes:", 1)[0]
        self.assertNotIn("refs/tags/", condition)


if __name__ == "__main__":
    unittest.main()
