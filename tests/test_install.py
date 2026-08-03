#!/usr/bin/env python3
"""Putting the command on a machine, and taking it off again.

The installer is shell, so it is tested by running it — into a throwaway PATH directory
with a throwaway HOME, so nothing here can touch the machine it runs on.

Run: python3 tests/test_install.py
"""

from __future__ import annotations

import json
import os
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

#: Everything here works on a **copy** of the checkout, made once for the whole file.
#:
#: This suite drives the real installer, and removing rundesk deletes the `.venv` beside the
#: script it was run from — correct for somebody uninstalling, and ruinous when the script it
#: was run from is the developer's own live install. Run against the checkout itself, this
#: file errored twice, failed once, and left a supervised gateway that refuses to start on
#: its next restart, because fitness finds the dependencies gone. A gate that cannot be run
#: twice is not a gate. The copy carries no history, which changes nothing: the installer
#: looks for history only under the directory it is installing *into*, never under itself.
CHECKOUT = Path(__file__).resolve().parent.parent
_working = tempfile.TemporaryDirectory(prefix="rundesk-checkout-")
# Resolved, like the path it stands in for. The installer reports where it is with `pwd -P`,
# and a job is only recognised as ours by comparing the two — so an unresolved temporary
# directory leaves every plist looking like somebody else's, on macOS alone.
REPO = Path(_working.name).resolve() / CHECKOUT.name
# Beyond git's own directory and build leavings: the untracked `ui/` and `site/` trees that
# stand beside `src/`. They are ~100 MB, `git status` reports the tree clean while they sit
# there, and carrying them into this copy took the suite from 92 seconds to past the gate's
# 180-second ceiling — a timeout that reads exactly like a regression in whatever was just
# changed, in a suite with nothing to do with it. **Only this copy reads the checkout**; every
# other one below is made from `REPO`, so stopping them here stops them everywhere.
shutil.copytree(CHECKOUT, REPO, ignore=shutil.ignore_patterns(
    ".git", "__pycache__", ".venv", "node_modules", "ui", "site", "dist"))
INSTALLER = REPO / "install.sh"


def installer(*args: str, home: Path, bindir: Path, cwd: Path | None = None,
              script: Path | None = None, extra_env: dict[str, str] | None = None,
              gh: Path | None = None, without_gh: bool = False) -> subprocess.CompletedProcess:
    """Run the installer somewhere it cannot reach the real machine."""
    # An agent running this suite carries the live install's RUNDESK_DATA_DIR and friends.
    # Overriding only the program and HOME still let a scratch uninstall take the live
    # built-in skills back out of their library. Begin with none of Rundesk's locations;
    # the scratch HOME and install below then derive every default downwards, while a case
    # may still opt into one explicit location through extra_env.
    isolated = {
        key: value for key, value in os.environ.items()
        if not key.startswith("RUNDESK_")
    }
    requested = dict(extra_env or {})
    inherited_path = requested.pop("PATH", isolated.get("PATH", ""))
    fake_tools = home / ".cache" / "rundesk-test-bin"
    fake_tools.mkdir(parents=True, exist_ok=True)
    launchctl = fake_tools / "launchctl"
    launchctl.write_text(
        "#!/bin/sh\n"
        "# Scratch installs own no live jobs; every mutation is accepted and every query\n"
        "# answers absent, which keeps this suite outside the real launchd domain.\n"
        "[ \"${1:-}\" = print ] && exit 1\n"
        "exit 0\n",
        encoding="utf-8",
    )
    launchctl.chmod(0o755)
    # A developer may be authenticated in GitHub CLI. No ordinary installer case may reach
    # that account merely because the suite inherited PATH. Default to an offline CLI whose
    # authentication check refuses; explicit cases pass their own stand-in or prove absence.
    if gh is None and not without_gh:
        unauthenticated = fake_tools / "gh"
        unauthenticated.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        unauthenticated.chmod(0o755)
    executable_path = f"{fake_tools}{os.pathsep}{inherited_path}"
    if gh is not None:
        executable_path = f"{gh.parent}{os.pathsep}{executable_path}"
    env = {
        **isolated,
        "HOME": str(home),
        "PATH": executable_path,
        "RUNDESK_BIN_DIR": str(bindir),
        "RUNDESK_INSTALL_DIR": str(home / ".rundesk"),
        "RUNDESK_JOBS_DIR": str(home / ".cache" / "rundesk-test-jobs"),
        # Never the real requirements file: installing it here would reach the network and
        # take a minute, in a suite that must do neither.
        "RUNDESK_REQUIREMENTS": str(home / "no-requirements.txt"),
        # The production default is GitHub. Installer tests prove the same complete
        # catalog path against a local repository and never depend on the network.
        "RUNDESK_DEFAULT_SKILLS_SOURCE": str(REPO / "tests" / "fixtures" / "default-catalog"),
        **requested,
    }
    return subprocess.run(
        ["bash", str(script or INSTALLER), *args],
        cwd=str(cwd or REPO), env=env, capture_output=True, text=True,
    )


class Sandbox(unittest.TestCase):
    def setUp(self):
        self._work = tempfile.TemporaryDirectory()
        self.root = Path(self._work.name)
        self.home = self.root / "home"
        self.bindir = self.root / "bin"
        self.home.mkdir()

    def tearDown(self):
        self._work.cleanup()

    def install(self, **kw) -> subprocess.CompletedProcess:
        return installer(home=self.home, bindir=self.bindir, **kw)

    def uninstall(self, *args: str, **kw) -> subprocess.CompletedProcess:
        return installer("--uninstall", *args, home=self.home, bindir=self.bindir, **kw)

    def fake_gh(self) -> Path:
        """An offline GitHub CLI seam whose authentication and API outcomes are explicit."""
        tool = self.root / "tools" / "gh"
        tool.parent.mkdir(exist_ok=True)
        tool.write_text(
            "#!/bin/sh\n"
            "printf '%s\\n' \"$*\" >> \"$RUNDESK_GH_LOG\"\n"
            "case \"${1:-} ${2:-}\" in\n"
            "  'auth status') exit \"${RUNDESK_GH_AUTH_EXIT:-1}\" ;;\n"
            "  'api --method') exit \"${RUNDESK_GH_API_EXIT:-0}\" ;;\n"
            "esac\n"
            "exit 2\n",
            encoding="utf-8",
        )
        tool.chmod(0o755)
        return tool

    def path_without_gh(self) -> str:
        """Only the ordinary commands a local install uses, with no GitHub CLI."""
        toolbox = self.root / "no-gh"
        toolbox.mkdir()
        for name in ("bash", "chmod", "cut", "dirname", "du", "grep", "ln", "mkdir",
                     "pwd", "python3", "readlink", "rmdir", "tr", "wc"):
            target = shutil.which(name)
            self.assertIsNotNone(target, f"the test machine has no {name}")
            (toolbox / name).symlink_to(target)
        return str(toolbox)


@unittest.skipUnless(shutil.which("launchctl"), "no supervisor on this machine to keep anything")
class RemovingWhatIsRunningTests(Sandbox):
    """Removing rundesk has to stop what it was keeping *before* deleting the command.

    Every other case here drives the installer's own shell. This one exists because the
    shell cannot catch it: an installer that simply stops calling the teardown still
    parses, still installs, still uninstalls, and silently leaves a supervised gateway
    running against a program that is no longer there.
    """

    def test_removing_rundesk_takes_away_the_jobs_it_left_behind(self):
        """R-RM-9"""
        jobs = self.root / "jobs"
        jobs.mkdir()
        self.install(extra_env={"RUNDESK_JOBS_DIR": str(jobs)})
        sys.path.insert(0, str(REPO / "src"))
        from rundesk import supervisor
        supervisor.write("left-running", REPO, self.root / "logs", str(jobs))
        self.assertTrue((jobs / "ai.rundesk.left-running.plist").exists())

        said = self.uninstall(extra_env={"RUNDESK_JOBS_DIR": str(jobs)})
        self.assertEqual(
            [], list(jobs.glob("*.plist")),
            f"uninstalling left a job behind, which the machine will keep trying to start:\n{said.stdout}{said.stderr}",
        )

    def test_removing_rundesk_refuses_while_a_gateway_is_still_running(self):
        """R-RM-9 — the refusal that was written and never reached.

        `stop_gateways` ended in `python3 … || echo "note: …"`, so the shell reported the
        echo's success rather than the command's failure: the guard could not fire, its
        message was unreachable, and uninstall deleted the command while a gateway it was
        keeping went on running — an agent nobody can reach, and the one thing that could
        have stopped it now gone.
        """
        sys.path.insert(0, str(REPO / "src"))
        from rundesk import gateway, supervisor
        jobs, run = self.root / "jobs", self.root / "run"
        jobs.mkdir()
        run.mkdir()
        where = {"RUNDESK_JOBS_DIR": str(jobs), "RUNDESK_RUN_DIR": str(run)}
        self.install(extra_env=where)
        supervisor.write("busy", REPO, self.root / "logs", str(jobs))
        # Held for real: the lock is what `standing` asks the kernel about, so this is a
        # gateway that is genuinely still running as far as everything here is concerned.
        # Its install is named rather than left to fall back on this checkout: claiming a
        # name asks whether the install fits, and this case is about removal, not fitness.
        holding = gateway.Gateway("busy", where=run, logs=self.root / "logs", root=self.root)
        holding.claim()
        self.addCleanup(holding.release)

        said = self.uninstall(extra_env=where)
        self.assertNotEqual(0, said.returncode, "it removed rundesk with a gateway still running")
        self.assertIn("still running", said.stdout + said.stderr)
        self.assertTrue(
            (self.bindir / "rundesk").exists(),
            "it took away the command while a gateway it was keeping was still running — "
            "which is the one thing that could have stopped it",
        )

    def test_removing_rundesk_leaves_a_job_written_by_something_else(self):
        """R-RM-3, R-RM-9 — someone else's agents are not ours to stand down."""
        jobs = self.root / "jobs"
        jobs.mkdir()
        theirs = jobs / "ai.rundesk.theirs.plist"
        with open(theirs, "wb") as file:
            plistlib.dump({"Label": "ai.rundesk.theirs",
                           "ProgramArguments": ["/somewhere/else/rundesk", "serve", "theirs"]}, file)
        self.install(extra_env={"RUNDESK_JOBS_DIR": str(jobs)})
        self.uninstall(extra_env={"RUNDESK_JOBS_DIR": str(jobs)})
        self.assertTrue(theirs.exists(), "it removed a job belonging to something else")

    def test_removing_a_scratch_install_leaves_another_installs_update_worker(self):
        """R-UPD-35, R-RM-9, R-RM-15 — reported (#129).

        Leaving the foreign worker was always right and is unchanged. What changed is what
        happened next: the refusal escaped as an exception, so the removal ended partway
        through and reported it as gateways that would not stop. Nothing on the machine
        said that, and a redirected install could not be removed at all on any machine
        that already had an ordinary one — which is every machine one is validated on.
        """
        jobs = self.root / "jobs"
        jobs.mkdir()
        self.install(extra_env={"RUNDESK_JOBS_DIR": str(jobs)})
        sys.path.insert(0, str(REPO / "src"))
        from rundesk import supervisor
        foreign = self.root / "foreign"
        foreign.mkdir()
        (foreign / "rundesk").write_text("#!/usr/bin/env python3\n")
        worker = supervisor.write_update_worker(
            foreign, self.root / "logs", str(jobs)
        )

        said = self.uninstall(extra_env={"RUNDESK_JOBS_DIR": str(jobs)})

        self.assertEqual(0, said.returncode,
                         "leaving another install's worker alone ended the removal")
        self.assertTrue(worker.exists(), "it removed another install's update worker")
        self.assertIn("another install of rundesk wrote it", said.stdout + said.stderr,
                      "it did not say what it deliberately left behind")
        self.assertFalse((self.bindir / "rundesk").exists(),
                         "the removal did not finish")


class WhatWasAskedForTests(Sandbox):
    """R-INS-17 — the installer answers for its own options before it touches anything.

    `--help` fell straight through to the install path: it provisioned dependencies,
    repointed the `rundesk` launcher at whatever checkout it was run from, and only then
    failed on a later step. Asking a program what it does is the one request that must
    never be able to change the machine, and every case here proves it by looking at the
    machine afterwards rather than at the exit code alone.
    """

    def untouched(self, said, *, expected: int):
        self.assertEqual(expected, said.returncode, said.stdout + said.stderr)
        self.assertFalse(
            (self.bindir / "rundesk").exists(),
            "the launcher was placed by a command that installs nothing",
        )
        self.assertFalse(
            (self.home / ".rundesk").exists(),
            "an install directory was made by a command that installs nothing",
        )

    def test_asking_the_installer_for_help_prints_usage_and_installs_nothing(self):
        said = installer("--help", home=self.home, bindir=self.bindir)
        self.untouched(said, expected=0)
        self.assertIn("Usage:", said.stdout)
        self.assertIn("--uninstall", said.stdout)

    def test_an_option_the_installer_does_not_know_is_refused_before_anything_changes(self):
        said = installer("--dry-run", home=self.home, bindir=self.bindir)
        self.untouched(said, expected=1)
        self.assertIn("unknown option '--dry-run'", said.stderr)

    def test_help_is_answered_even_when_something_destructive_follows_it(self):
        """`--help --uninstall` is somebody asking what this does; answering by removing
        rundesk would be the same failure wearing a second costume."""
        said = installer("--help", "--uninstall", home=self.home, bindir=self.bindir)
        self.untouched(said, expected=0)
        self.assertIn("Usage:", said.stdout)

    def test_an_unknown_option_after_uninstall_is_refused_rather_than_ignored(self):
        """`--uninstall --purgge` read as an ordinary uninstall and kept the data the owner
        had just asked to be rid of — a typo answered with a different command."""
        self.install()
        said = self.uninstall("--purgge")
        self.assertEqual(1, said.returncode, said.stdout + said.stderr)
        self.assertIn("unknown option '--purgge'", said.stderr)
        self.assertTrue(
            (self.bindir / "rundesk").exists(),
            "a refused option still removed the command",
        )


class CommunitySupportTests(Sandbox):
    """R-INS-21 — a new owner can support Rundesk without a separate manual step."""

    def install_with_gh(self, *, authenticated: bool = True,
                        api_succeeds: bool = True) -> tuple[subprocess.CompletedProcess, Path]:
        log = self.root / "gh.log"
        log.touch()
        done = self.install(
            gh=self.fake_gh(),
            extra_env={
                "RUNDESK_GH_LOG": str(log),
                "RUNDESK_GH_AUTH_EXIT": "0" if authenticated else "1",
                "RUNDESK_GH_API_EXIT": "0" if api_succeeds else "1",
            },
        )
        return done, log

    def test_a_fresh_install_with_authenticated_github_cli_stars_rundesk(self):
        done, log = self.install_with_gh()

        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(
            [
                "auth status --hostname github.com",
                "api --method PUT -H Content-Length: 0 /user/starred/rundesk-ai/rundesk-cli",
            ],
            log.read_text(encoding="utf-8").splitlines(),
        )
        self.assertIn("helped you support the Rundesk community", done.stdout)

    def test_installing_again_makes_no_second_star_request(self):
        first, log = self.install_with_gh()
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        requests_after_first = log.read_text(encoding="utf-8")
        self.assertEqual(2, len(requests_after_first.splitlines()))

        second, _ = self.install_with_gh()

        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        self.assertEqual(requests_after_first, log.read_text(encoding="utf-8"))
        self.assertNotIn("helped you support the Rundesk community", second.stdout)

    def test_an_install_without_github_cli_still_succeeds(self):
        done = self.install(
            without_gh=True,
            extra_env={"PATH": self.path_without_gh()},
        )

        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertNotIn("helped you support the Rundesk community", done.stdout)

    def test_an_install_without_github_authentication_does_not_star(self):
        done, log = self.install_with_gh(authenticated=False)

        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(
            ["auth status --hostname github.com"],
            log.read_text(encoding="utf-8").splitlines(),
        )
        self.assertNotIn("helped you support the Rundesk community", done.stdout)

    def test_a_failed_star_request_does_not_fail_the_install(self):
        done, log = self.install_with_gh(api_succeeds=False)

        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(2, len(log.read_text(encoding="utf-8").splitlines()))
        self.assertNotIn("helped you support the Rundesk community", done.stdout)


class InstallTests(Sandbox):
    def test_installing_needs_nothing_already_present_beyond_the_machines_own(self):
        # The whole reason this is Python: a machine with python3 — which macOS ships — has
        # everything. If the installer ever needs a package manager or a build step, this is
        # where that shows up.
        done = self.install()
        self.assertEqual(done.returncode, 0, done.stderr)

        # Read off what the installer actually demands, rather than grepping for names —
        # "pip" is a substring of "pipefail", which is how a check like that passes forever.
        required = set(re.findall(r"command -v (\S+)", INSTALLER.read_text()))
        self.assertEqual(
            required,
            {"python3", "curl", "tar", "launchctl"},
            "the installer requires something a stock machine may not have",
        )

    def test_an_install_refuses_to_report_success_until_the_command_it_installed_answers(self):
        # An installer that reports done and leaves something that cannot run is the worst of
        # both: nothing to debug, and a command on your PATH that fails.
        broken = self.root / "broken-checkout"
        shutil.copytree(REPO, broken, ignore=shutil.ignore_patterns(".git", "__pycache__"))
        (broken / "rundesk").write_text("#!/usr/bin/env python3\nraise SystemExit(9)\n")
        (broken / "rundesk").chmod(0o755)

        done = installer(home=self.home, bindir=self.bindir, cwd=broken, script=broken / "install.sh")

        self.assertNotEqual(done.returncode, 0, "it reported success having installed something that cannot run")
        self.assertIn("would not run", done.stdout + done.stderr)

    def test_installing_again_leaves_the_machine_as_it_was(self):
        first = self.install()
        target_after_first = (self.bindir / "rundesk").resolve()
        second = self.install()

        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual((self.bindir / "rundesk").resolve(), target_after_first)
        self.assertEqual(len(list(self.bindir.iterdir())), 1, "installing twice left two of something")

    def test_installing_schedules_daily_updates_for_the_configured_time(self):
        """R-UPD-42"""
        data = self.home / ".rundesk" / "data"
        data.mkdir(parents=True)
        (data / "config.json").write_text(
            '{"updates": {"at": "2:30"}}', encoding="utf-8"
        )
        done = self.install()
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        job = self.home / ".cache" / "rundesk-test-jobs" / \
            "ai.rundesk-automatic-update.plist"
        with open(job, "rb") as file:
            described = plistlib.load(file)
        self.assertEqual(
            {"Hour": 2, "Minute": 30}, described["StartCalendarInterval"]
        )
        self.assertEqual(["update", "--automatic"], described["ProgramArguments"][1:])

    def test_uninstalling_removes_the_daily_update_job(self):
        """R-UPD-42"""
        self.install()
        job = self.home / ".cache" / "rundesk-test-jobs" / \
            "ai.rundesk-automatic-update.plist"
        self.assertTrue(job.exists())
        gone = self.uninstall()
        self.assertEqual(gone.returncode, 0, gone.stdout + gone.stderr)
        self.assertFalse(job.exists())

    def test_a_fresh_install_then_uninstall_leaves_no_install_directory(self):
        """R-RM-8"""
        installed = self.install()
        self.assertEqual(installed.returncode, 0, installed.stdout + installed.stderr)
        gone = self.uninstall()
        self.assertEqual(gone.returncode, 0, gone.stdout + gone.stderr)
        self.assertFalse(
            (self.home / ".rundesk").exists(),
            "automatic update setup left an empty directory behind",
        )

    def test_a_fresh_install_includes_the_general_catalog_without_granting_it(self):
        """R-CAT-11 — the catalog is available by default, while grants stay explicit."""
        installed = self.install()
        self.assertEqual(installed.returncode, 0, installed.stdout + installed.stderr)
        data = self.home / ".rundesk" / "data"
        provenance = json.loads(
            (data / "catalogs" / "rundesk-skills" / "provenance.json").read_text()
        )
        self.assertTrue(provenance["seeded"])
        self.assertTrue((data / "skills" / "fixture-guidance").is_symlink())
        self.assertEqual([], list((data / "agents").glob("*/home/skills/fixture-guidance")))

    def test_an_install_refuses_a_default_catalog_name_owned_by_the_user(self):
        """R-CAT-5 — automatic seeding never turns a custom package into catalog content."""
        library = self.home / ".rundesk" / "data" / "skills"
        custom = library / "fixture-guidance"
        custom.mkdir(parents=True)
        page = custom / "SKILL.md"
        mine = "---\nname: fixture-guidance\ndescription: Mine.\n---\n"
        page.write_text(mine, encoding="utf-8")

        installed = self.install()

        self.assertEqual(1, installed.returncode)
        self.assertIn(
            "the skill fixture-guidance is already there and this catalog does not own it",
            installed.stdout + installed.stderr,
        )
        self.assertEqual(mine, page.read_text(encoding="utf-8"))
        self.assertFalse((self.home / ".rundesk" / "data" / "catalogs").exists())

    def test_the_installed_command_is_reachable_by_name_from_any_directory(self):
        self.install()
        elsewhere = self.root / "somewhere-else"
        elsewhere.mkdir()

        said = subprocess.run(
            ["rundesk", "version"], cwd=str(elsewhere), capture_output=True, text=True,
            env={**os.environ, "PATH": f"{self.bindir}:{os.environ['PATH']}", "HOME": str(self.home)},
        )

        self.assertEqual(said.returncode, 0, said.stderr)
        self.assertIn("rundesk", said.stdout)

    def test_installing_from_a_copy_of_the_source_uses_that_copy(self):
        # Development and installed use share one layout, so there is no second copy to drift.
        self.install()
        self.assertEqual((self.bindir / "rundesk").resolve(), (REPO / "rundesk").resolve())
        # The *program*, which is what a second copy would be. `data/` is beside it and is
        # expected: an install has a skills library whether its program is a checkout or a
        # download, and the whole point of the two names is that one of them is not the
        # other. Asserting the install directory was empty said "no second copy" and meant
        # "nothing here at all", which stopped being the same sentence the day data got a
        # name of its own.
        self.assertFalse((self.home / ".rundesk" / "app").exists(),
                         "it downloaded a second copy beside the checkout")


class RemovalTests(Sandbox):
    def test_removing_rundesk_leaves_no_command_behind(self):
        self.install()
        self.assertTrue((self.bindir / "rundesk").exists())

        gone = self.uninstall()

        self.assertEqual(gone.returncode, 0, gone.stderr)
        self.assertFalse((self.bindir / "rundesk").exists(), "the command is still on the PATH")

    def test_removing_rundesk_leaves_a_copy_of_the_source_alone(self):
        # A checkout is the owner's. Only a directory the installer made is its to delete.
        self.install()
        self.uninstall()
        self.assertTrue((REPO / "rundesk").exists(), "uninstalling deleted the checkout it was run from")
        self.assertTrue((REPO / "src" / "rundesk" / "cli.py").exists())

    def test_removing_rundesk_leaves_a_command_it_did_not_install(self):
        # Something else on this machine is called rundesk. Removing it would be this
        # installer breaking a tool that is none of its business.
        self.bindir.mkdir(parents=True, exist_ok=True)
        stranger = self.root / "someone-elses-rundesk"
        stranger.write_text("#!/usr/bin/env bash\necho not ours\n")
        stranger.chmod(0o755)
        (self.bindir / "rundesk").symlink_to(stranger)

        self.uninstall()

        self.assertTrue((self.bindir / "rundesk").exists(), "it removed a command it never installed")
        self.assertEqual((self.bindir / "rundesk").resolve(), stranger.resolve())

    def test_removing_rundesk_keeps_settings_unless_asked_to_take_them(self):
        settings = self.home / ".config" / "rundesk"
        settings.mkdir(parents=True)
        (settings / "kept.txt").write_text("mine\n")

        self.install()
        self.uninstall()
        self.assertTrue((settings / "kept.txt").exists(), "an ordinary uninstall took the owner's settings")

        self.install()
        purged = self.uninstall("--purge")
        self.assertEqual(purged.returncode, 0, purged.stderr)
        self.assertFalse(settings.exists(), "--purge left the settings behind")

    def test_removing_rundesk_keeps_the_values_every_program_was_given_unless_asked(self):
        """R-RM-16, R-SEC-26 — no backup holds these, so a purge that took them without
        saying so would be the one deletion an owner has no copy of anywhere. And an
        uninstall that left them while reporting everything gone would leave credentials
        on a machine somebody believes rundesk is off."""
        kept_at = self.home / ".config" / "rundesk" / "secrets"
        (kept_at / "values").mkdir(parents=True)
        (kept_at / "registry.json").write_text('{"version": 1, "secrets": {}}\n')
        (kept_at / "values" / "GITHUB_TOKEN").write_text("gh-secret\n")

        self.install()
        kept = self.uninstall()

        self.assertEqual(kept.returncode, 0, kept.stderr)
        self.assertTrue((kept_at / "values" / "GITHUB_TOKEN").exists(),
                        "an ordinary uninstall took the owner's credentials")
        self.assertIn("--purge", kept.stdout, "it never said how to take them")

        self.install()
        purged = self.uninstall("--purge")

        self.assertEqual(purged.returncode, 0, purged.stderr)
        self.assertFalse(kept_at.exists(), "--purge left the credentials behind")

    def test_a_purge_refuses_a_secrets_directory_it_did_not_write(self):
        """R-RM-16 — a purge deletes what it is pointed at outright, so a variable left at
        a home directory or a typo is somebody's whole tree. Recognised by what rundesk
        puts there rather than by the name, which anybody may choose."""
        somewhere = self.home / "not-rundesks"
        somewhere.mkdir(parents=True)
        (somewhere / "important.txt").write_text("mine\n")

        self.install()
        said = self.uninstall("--purge",
                              extra_env={"RUNDESK_SECRETS_DIR": str(somewhere)})

        self.assertNotEqual(0, said.returncode, "it purged a directory it never wrote")
        self.assertTrue((somewhere / "important.txt").exists())
        self.assertIn("Nothing has been removed", said.stdout + said.stderr)

    def test_removing_rundesk_keeps_what_the_gateways_wrote_unless_asked_to_take_it(self):
        """R-RM-10 — `rm -rf` on the install directory took the whole audit trail with the
        program, at the one moment an owner is most likely to want it: a reinstall after
        trouble. The command someone runs to fix the trouble was deleting the account of
        what the trouble was (R-GW-18)."""
        wrote = self.home / ".rundesk" / "data" / "logs"
        wrote.mkdir(parents=True)
        (wrote / "gateway.log").write_text("what happened\n")
        # The account of what a gateway never finished stands with its log, and is the one
        # thing beside it that is still a file rather than a row.
        (wrote / "gateway.interrupted.json").write_text('{"turn": {"ended": false}}\n')

        self.install()
        kept = self.uninstall()

        self.assertEqual(kept.returncode, 0, kept.stderr)
        self.assertEqual("what happened\n", (wrote / "gateway.log").read_text(),
                         "an ordinary uninstall took the gateway's log")
        self.assertTrue((wrote / "gateway.interrupted.json").exists(),
                        "it took the account of what never finished")
        self.assertIn("--purge", kept.stdout, "it never said how to take them")

    def test_removing_rundesk_keeps_every_agents_home(self):
        """R-AGT-3 — an agent's home is what its owner wrote in it: its rules, who it works
        for, what it has learned. Removing the program is not asking for that to go, and it
        sits under the install directory only because that is where rundesk keeps things."""
        home = self.home / ".rundesk" / "data" / "agents" / "ava" / "home"
        (home / "workspace").mkdir(parents=True)
        (home / "SOUL.md").write_text("what ava is for, in my own words\n")
        (self.home / ".rundesk" / "data" / "agents" / "ava" / "logs").mkdir(parents=True)

        self.install()
        kept = self.uninstall()

        self.assertEqual(kept.returncode, 0, kept.stderr)
        self.assertEqual("what ava is for, in my own words\n", (home / "SOUL.md").read_text(),
                         "an ordinary uninstall took an agent's home")
        self.assertTrue((home / "workspace").is_dir(), "it took the agent's workspace")

    def test_removing_rundesk_keeps_the_templates_an_owner_wrote(self):
        """R-RM-12 — a template an owner made their own is theirs, and removing the program
        is not asking for it to go (R-RM-4).

        Nothing in the installer was taught this. The templates stand among the agents, and
        everything beside the program is kept — so it holds by the shape of the layout
        rather than by a list of names, which is the whole reason the list went away.
        """
        mine = self.home / ".rundesk" / "data" / "agents" / ".templates" / "agent"
        mine.mkdir(parents=True)
        (mine / "SOUL.md").write_text("the words I wrote for every agent I make\n")

        self.install()
        kept = self.uninstall()

        self.assertEqual(kept.returncode, 0, kept.stderr)
        self.assertEqual("the words I wrote for every agent I make\n",
                         (mine / "SOUL.md").read_text(),
                         "an ordinary uninstall took a template its owner wrote")

    def test_purging_takes_the_templates_an_owner_wrote_as_well(self):
        """R-RM-12 — the other half, so "keeps it" cannot pass by never removing anything."""
        mine = self.home / ".rundesk" / "data" / "agents" / ".templates" / "agent"
        mine.mkdir(parents=True)
        (mine / "SOUL.md").write_text("mine\n")

        self.install()
        gone = self.uninstall("--purge")

        self.assertEqual(gone.returncode, 0, gone.stderr)
        self.assertFalse(mine.exists(), "a purge left the templates behind")

    def test_purging_takes_every_agents_home_as_well(self):
        """R-AGT-3 — the other half, so "keeps it" cannot pass by never removing anything."""
        agents = self.home / ".rundesk" / "data" / "agents"
        (agents / "ava" / "home").mkdir(parents=True)
        (agents / "ava" / "home" / "SOUL.md").write_text("mine\n")

        self.install()
        purged = self.uninstall("--purge")

        self.assertEqual(purged.returncode, 0, purged.stderr)
        self.assertFalse(agents.exists(), "--purge left an agent's home behind")

    def test_purging_takes_what_the_gateways_wrote_as_well(self):
        """R-RM-10 — the other half, so "keeps it" cannot pass by never removing anything."""
        wrote = self.home / ".rundesk" / "data" / "logs"
        wrote.mkdir(parents=True)
        (wrote / "gateway.log").write_text("what happened\n")

        self.install()
        purged = self.uninstall("--purge")

        self.assertEqual(purged.returncode, 0, purged.stderr)
        self.assertFalse(wrote.exists(), "--purge left the gateway logs behind")
        self.assertFalse((self.home / ".rundesk").exists(),
                         "--purge left the install directory behind")

    def test_removing_rundesk_that_was_never_installed_says_so(self):
        # Someone running uninstall twice, or on the wrong machine, has not done anything
        # wrong. Failing at them would read as though something broke.
        gone = self.uninstall()
        self.assertEqual(gone.returncode, 0, gone.stderr)
        self.assertIn("No rundesk symlink", gone.stdout + gone.stderr)

    def test_an_install_says_so_when_the_command_it_placed_is_not_reachable(self):
        # Installed into a directory nobody's PATH names is installed and invisible. The
        # install has to say which directory, and how to reach it.
        done = self.install()
        self.assertEqual(done.returncode, 0, done.stderr)
        said = done.stdout + done.stderr
        self.assertIn(str(self.bindir), said, "it did not name the directory it installed into")
        self.assertIn("PATH", said, "it installed somewhere unreachable and said nothing")

class DependencyTests(Sandbox):
    """What rundesk needs beyond the standard library, and where it is allowed to put it."""

    def needs(self, *lines: str) -> Path:
        """A requirements file for this test, so the real one is never installed here."""
        path = self.root / "requirements.txt"
        path.write_text("\n".join(lines) + "\n")
        return path

    def install_needing(self, requirements: Path, **kw) -> subprocess.CompletedProcess:
        env_extra = {"RUNDESK_REQUIREMENTS": str(requirements)}
        return installer(home=self.home, bindir=self.bindir,
                         **{**kw, "extra_env": env_extra})

    def checkout(self) -> Path:
        """A copy of the checkout for one test to work on.

        Every case here builds or removes the `.venv` beside the installer, and where that
        goes is decided from where the script sits. Sharing one tree between them means the
        case that asserts no virtualenv was made passes or fails on whichever case ran
        before it.
        """
        clone = self.root / "checkout"
        shutil.copytree(REPO, clone, ignore=shutil.ignore_patterns(".git", "__pycache__", ".venv"))
        return clone

    def installing_into(self, clone: Path, requirements: Path) -> subprocess.CompletedProcess:
        return self.install_needing(requirements, cwd=clone, script=clone / "install.sh")

    def test_nothing_needed_means_no_virtualenv_is_made_at_all(self):
        # The state to return to if a dependency ever stops earning its place: zero cost,
        # nothing to go stale, and an install that is a symlink and nothing else.
        clone = self.checkout()
        done = self.installing_into(clone, self.needs("# nothing needed", ""))
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertFalse((clone / ".venv").exists(), "a virtualenv was made for no dependencies")
        self.assertNotIn("installing what rundesk needs", done.stdout,
                         "the installer said it was installing dependencies it does not have")

    def test_what_rundesk_needs_goes_inside_its_own_install(self):
        # Never the machine's Python. Modern ones refuse to be written to anyway, and a tool
        # that makes its user reason about that has already lost them.
        #
        # Asked of `rundesk.dependencies`, which is where the installer and an update both
        # go for this now. Read off the commands it would actually run rather than off the
        # installer's text, because the words in a shell script are no longer where the
        # decision is made — and a check on text that no longer decides anything is a check
        # that passes for ever.
        sys.path.insert(0, str(REPO / "src"))
        from rundesk import dependencies

        root = self.root / "install"
        (root / "requirements.txt").parent.mkdir(parents=True, exist_ok=True)
        (root / "requirements.txt").write_text("some-package==1.0\n")
        ran = []
        dependencies.provision(root, run=lambda command: ran.append(command) or "stop here")

        built = [one for one in ran if one[1:3] == ["-m", "venv"]]
        self.assertEqual([str(root / ".venv")], [one[3] for one in built],
                         "the installer puts dependencies somewhere other than inside the install")
        outside = [one for one in ran if one[0] == sys.executable and "venv" not in one]
        self.assertEqual([], outside, "something was installed with the machine's own Python")

    def test_the_command_finds_what_was_installed_for_it(self):
        # Added to the path by the launcher rather than by activating anything, so the
        # command works from any shell with nothing sourced first.
        clone = self.checkout()
        venv = clone / ".venv"
        packages = venv / "lib" / f"python3.{sys.version_info.minor}" / "site-packages"
        packages.mkdir(parents=True)
        (packages / "pretend_dependency.py").write_text("WORKS = True\n")
        said = subprocess.run(
            [str(clone / "rundesk"), "version"], capture_output=True, text=True,
            env={**os.environ, "HOME": str(self.home)},
        )
        self.assertEqual(said.returncode, 0, said.stderr)
        found = subprocess.run(
            [str(clone / "rundesk"), "--version"], capture_output=True, text=True,
            env={**os.environ, "HOME": str(self.home)},
        )
        self.assertEqual(found.returncode, 0, found.stderr)
        # The path wiring itself, asked directly.
        imported = subprocess.run(
            ["python3", "-c",
             "import sys, pathlib; "
             f"sys.path[:0] = [str(p) for p in sorted(pathlib.Path({str(venv)!r}).glob('lib/python3.*/site-packages'))]; "
             "import pretend_dependency; print(pretend_dependency.WORKS)"],
            capture_output=True, text=True,
        )
        self.assertIn("True", imported.stdout, imported.stderr)

    def test_removing_rundesk_takes_back_the_skills_the_release_laid_down(self):
        """R-RM-7 — a built-in is the program's file, which is the whole of why an update may
        replace it without asking. So removal takes it: left behind it is a piece of rundesk
        on a machine somebody removed rundesk from."""
        made = self.home / ".rundesk" / "app"
        shutil.copytree(REPO, made, ignore=shutil.ignore_patterns(".git", "__pycache__", ".venv"))
        library = self.home / ".rundesk" / "data" / "skills"
        shipped = sorted(one.name for one in (REPO / "src" / "templates" / "skills").iterdir()
                         if (one / "SKILL.md").is_file())
        self.assertTrue(shipped, "the release ships no skills, so this proves nothing")
        for name in shipped:
            (library / name).mkdir(parents=True)
            (library / name / "SKILL.md").write_text(f"---\nname: {name}\n---\n")
            (library / name / ".rundesk-built-in").write_text("rundesk built-in\n")

        gone = installer("--uninstall", home=self.home, bindir=self.bindir,
                         cwd=made, script=made / "install.sh")

        self.assertEqual(gone.returncode, 0, gone.stderr)
        self.assertEqual([], [name for name in shipped if (library / name).exists()],
                         "a skill this release laid down was left on the machine")

    def test_a_redirected_uninstall_cannot_take_another_installs_data(self):
        """R-RM-12 — reported (#220).

        An agent inherits the live install's data and skill-library paths. Pointing only the
        installer at a scratch root must still make every removal helper act on that scratch
        install; otherwise validating an uninstall takes the live install's built-ins.
        """
        scratch = self.root / "scratch"
        made = scratch / "app"
        shutil.copytree(REPO, made, ignore=shutil.ignore_patterns(".git", "__pycache__", ".venv"))

        shipped = next(one.name for one in (REPO / "src" / "templates" / "skills").iterdir()
                       if (one / "SKILL.md").is_file())
        scratch_library = scratch / "data" / "skills"
        foreign_data = self.root / "existing" / "data"
        foreign_library = foreign_data / "skills"
        for library, words in ((scratch_library, "scratch\n"),
                               (foreign_library, "existing bytes must survive\n")):
            built_in = library / shipped
            built_in.mkdir(parents=True)
            (built_in / "SKILL.md").write_text(words, encoding="utf-8")
            (built_in / ".rundesk-built-in").write_text("rundesk built-in\n", encoding="utf-8")
        sys.path.insert(0, str(REPO / "src"))
        from rundesk import config
        configuration = json.dumps(config.INITIAL, indent=2) + "\n"
        (scratch / "data" / "config.json").write_text(configuration, encoding="utf-8")
        (foreign_data / "config.json").write_text(configuration, encoding="utf-8")
        foreign_before = {
            path.relative_to(foreign_data): path.read_bytes()
            for path in foreign_data.rglob("*") if path.is_file()
        }

        gone = installer(
            "--uninstall", home=self.home, bindir=self.bindir, cwd=made,
            script=made / "install.sh",
            extra_env={
                "RUNDESK_INSTALL_DIR": str(scratch),
                "RUNDESK_DATA_DIR": str(foreign_data),
                "RUNDESK_SKILL_LIBRARY": str(foreign_library),
            },
        )

        self.assertEqual(gone.returncode, 0, gone.stderr)
        self.assertFalse((scratch_library / shipped).exists(),
                         "the redirected install left its own built-in behind")
        self.assertFalse((scratch / "data" / "config.json").exists(),
                         "the redirected install left its own unchanged configuration behind")
        self.assertEqual(
            foreign_before,
            {path.relative_to(foreign_data): path.read_bytes()
             for path in foreign_data.rglob("*") if path.is_file()},
            "uninstalling the scratch install changed another install's data",
        )

    def test_removing_rundesk_leaves_a_skill_the_owner_wrote_themselves(self):
        """R-RM-7 — the other half, and the line that matters: the set taken back is the set
        this release ships, so a skill of their own is not a name it touches. The built-ins
        tell an owner to copy one under another name to make it theirs, and that promise is
        worth exactly as much as this case."""
        made = self.home / ".rundesk" / "app"
        shutil.copytree(REPO, made, ignore=shutil.ignore_patterns(".git", "__pycache__", ".venv"))
        library = self.home / ".rundesk" / "data" / "skills"
        (library / "mine").mkdir(parents=True)
        (library / "mine" / "SKILL.md").write_text("---\nname: mine\n---\n")

        gone = installer("--uninstall", home=self.home, bindir=self.bindir,
                         cwd=made, script=made / "install.sh")

        self.assertEqual(gone.returncode, 0, gone.stderr)
        self.assertTrue((library / "mine" / "SKILL.md").is_file(),
                        "removing rundesk took a skill the owner wrote")

    def test_removing_rundesk_from_a_machine_that_kept_nothing_leaves_no_directory(self):
        """R-RM-8 — the assertion the published-release job makes on a bare machine, and the
        one the library quietly broke: with the shipped skills left in it, `data/` was never
        empty, so the install directory could never go and an uninstall that said it had
        left nothing had left the lot."""
        made = self.home / ".rundesk" / "app"
        shutil.copytree(REPO, made, ignore=shutil.ignore_patterns(".git", "__pycache__", ".venv"))
        library = self.home / ".rundesk" / "data" / "skills"
        library.mkdir(parents=True)
        for name in sorted(one.name for one in (REPO / "src" / "templates" / "skills").iterdir()
                           if (one / "SKILL.md").is_file()):
            (library / name).mkdir()
            (library / name / "SKILL.md").write_text(f"---\nname: {name}\n---\n")
            (library / name / ".rundesk-built-in").write_text("rundesk built-in\n")

        gone = installer("--uninstall", home=self.home, bindir=self.bindir,
                         cwd=made, script=made / "install.sh")

        self.assertEqual(gone.returncode, 0, gone.stderr)
        self.assertFalse((self.home / ".rundesk").exists(),
                         "nothing of the owner's was there, so the directory should have gone")

    def test_removing_rundesk_takes_what_was_installed_for_it(self):
        clone = self.checkout()
        venv = clone / ".venv"
        venv.mkdir()
        (venv / "marker").write_text("x")
        self.installing_into(clone, self.needs("# nothing needed", ""))
        self.uninstall(cwd=clone, script=clone / "install.sh")
        self.assertFalse(venv.exists(), "uninstalling left the dependencies behind")

class EverythingNeededTests(unittest.TestCase):
    """An install has to leave a working command, not a nearly-working one."""

    def _declared(self) -> set[str]:
        """What this install declares, by the name it is imported under.

        Asked of `rundesk.dependencies`, which is what the installer, an update and
        `gateway.fitness` all read — rather than parsed a fourth time here. A hand-rolled
        copy agreed with it only for as long as `requirements.txt` held one plainly pinned
        line, and this case's whole job is catching an import nobody declared: a parser
        that quietly extracted a different name would fail for a reason that has nothing
        to do with what is being asserted, or pass when it should not.

        It also carried an alias table whose `discord_py` key could never be reached,
        because nothing in it ever turned `discord.py` into that spelling.
        """
        sys.path.insert(0, str(REPO / "src"))
        from rundesk import dependencies

        return {one.imported for one in dependencies.declared(REPO)}

    def test_everything_the_code_imports_is_the_standard_library_or_declared(self):
        # The failure this stops: an import added without a line in requirements.txt. The
        # install succeeds, the command is on the PATH, and it dies at the first use.
        import ast, sys, sysconfig

        stdlib = Path(sysconfig.get_paths()["stdlib"]).resolve()
        ours = {p.stem for p in (REPO / "src" / "rundesk").glob("*.py")} | {"rundesk"}
        declared = self._declared()

        undeclared = []
        for path in (REPO / "src").rglob("*.py"):
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    top = [a.name.split(".")[0] for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    top = [node.module.split(".")[0]]
                else:
                    continue
                for name in top:
                    if name in ours or name in declared or name in sys.builtin_module_names:
                        continue
                    spec = __import__("importlib.util", fromlist=["util"]).find_spec(name)
                    origin = getattr(spec, "origin", None)
                    if origin and origin != "built-in" and stdlib in Path(origin).resolve().parents:
                        continue
                    if spec is None or origin in (None, "built-in", "frozen"):
                        continue
                    undeclared.append(f"{path.relative_to(REPO)} imports {name}")

        self.assertEqual(undeclared, [], "imported but never declared, so an install would not provide it")

    def test_an_install_refuses_to_report_success_while_what_it_installed_does_not_fit_together(self):
        # pip will happily leave a set of packages that cannot satisfy each other. Installed
        # is not the same as usable, and the person finds out at the first turn otherwise.
        #
        # Driven rather than read: the check lives in `rundesk.dependencies` now, which is
        # what the installer calls and what an update calls, so the claim is proved by
        # watching a set that does not fit be refused — not by finding two words in a file.
        sys.path.insert(0, str(REPO / "src"))
        from rundesk import dependencies

        root = Path(tempfile.mkdtemp(prefix="rundesk-fits-"))
        self.addCleanup(shutil.rmtree, root, True)
        (root / "requirements.txt").write_text("some-package==1.0\n")

        def run(command):
            if "check" in command:
                return "some-package 1.0 has requirement other<2, but you have other 3"
            return None

        why = dependencies.provision(root, run=run)
        self.assertIsNotNone(why, "nothing verifies the dependencies fit together")
        self.assertIn("do not fit together", why,
                      "a broken dependency set fails without saying why")

class OneDirectoryTests(Sandbox):
    """Everything rundesk puts on a machine lives in one place the person owns."""

    def test_the_install_lives_under_the_persons_home(self):
        # `~/.rundesk`, the way other tools of this shape do it. Somewhere a person can find,
        # back up, and delete — not scattered through a system they did not choose.
        declared = re.search(r'INSTALL_DIR="\$\{RUNDESK_INSTALL_DIR:-([^}]+)\}"', INSTALLER.read_text())
        self.assertIsNotNone(declared, "the installer does not say where it installs")
        self.assertEqual(declared.group(1), "$HOME/.rundesk")

    def test_an_install_writes_nothing_outside_the_places_it_says(self):
        # The guarantee behind being removable: if an install scattered files, uninstalling
        # could not honestly claim to leave nothing behind.
        before = {p.name for p in self.home.iterdir()}
        done = self.install()
        self.assertEqual(done.returncode, 0, done.stderr)
        after = {p.name for p in self.home.iterdir()}

        self.assertLessEqual(
            after - before,
            {".rundesk", ".config", ".cache", ".local"},
            "an install left something in the person's home it never mentioned",
        )

    def test_the_installed_command_does_not_write_an_apple_python_cache(self):
        """The launcher suppresses bytecode before importing Rundesk's modules."""
        done = self.install()
        self.assertEqual(done.returncode, 0, done.stderr)
        ran = subprocess.run(
            [str(self.bindir / "rundesk"), "scripts", "--where"],
            env={**os.environ, "HOME": str(self.home),
                 "RUNDESK_INSTALL_DIR": str(self.home / ".rundesk")},
            capture_output=True, text=True,
        )
        self.assertEqual(ran.returncode, 0, ran.stderr)
        self.assertFalse((self.home / "Library" / "Caches" / "com.apple.python").exists(),
                         "running Rundesk wrote Apple Python's cache into the owner's home")

    def test_an_install_does_not_change_the_path_it_only_says_so(self):
        # Deliberate, for now: editing someone's shell profile behind their back is a change
        # to a file they own and did not ask us to touch (R-INS-9).
        done = self.install()
        said = done.stdout + done.stderr
        self.assertIn("export PATH=", said, "it did not say how to reach the command")
        for profile in (".zshrc", ".bashrc", ".bash_profile", ".profile"):
            self.assertFalse((self.home / profile).exists(), f"the install wrote to {profile}")

class WhatIsInstalledTests(unittest.TestCase):
    """Which rundesk a person gets when they have no copy of the source."""

    def test_an_install_without_a_checkout_takes_the_newest_release_not_the_branch(self):
        # Installing the branch hands someone a version that was never released — reporting a
        # number no release carries, which `rundesk update` would then offer to move them
        # *backwards* onto.
        script = INSTALLER.read_text()
        self.assertIn("releases/latest", script, "the installer does not ask what the newest release is")
        self.assertIn("/releases/download/$tag/", script,
                      "the installer never downloads a released tag")
        self.assertNotIn("archive/refs/heads/main", script,
                         "a failed release lookup can still install unreleased work")


class SaysWhatItIsDoingTests(Sandbox):
    """A person watching a terminal has no other way to tell working from hung.

    These are cheap assertions on wording, which is normally a smell. They are here because
    the alternative failure is invisible: a step goes quiet, nobody notices for a release,
    and the report is "it hangs" — for an installer that is piped into bash and an update
    that replaces the running program, that guess ends in Ctrl-C at the worst moment.
    """

    def test_an_install_says_what_it_is_doing_as_it_goes(self):
        done = self.install()
        self.assertEqual(done.returncode, 0, done.stderr)
        for said in ("installing rundesk", "linked", "checked that it runs"):
            self.assertIn(said, done.stdout, f"an install never said {said!r}")

    def test_an_install_says_where_it_is_putting_things(self):
        # Two paths matter to a person afterwards: what went on the PATH, and what it
        # points at. Both are named, so an install can be undone by hand if it has to be.
        done = self.install()
        self.assertIn(str(self.bindir / "rundesk"), done.stdout, "it never said what it put on the PATH")
        self.assertIn(str(REPO / "rundesk"), done.stdout, "it never said what that points at")

    def test_removing_rundesk_says_what_it_took_and_what_it_left(self):
        self.install()
        settings = self.home / ".config" / "rundesk"
        settings.mkdir(parents=True)

        gone = self.uninstall()

        self.assertIn("removing rundesk", gone.stdout, "removal began without saying so")
        self.assertIn(str(self.bindir / "rundesk"), gone.stdout, "it never said what it took")
        self.assertIn(str(settings), gone.stdout, "it never said the settings were left behind")
        self.assertIn("rundesk uninstalled", gone.stdout)

    def test_removing_nothing_does_not_report_having_removed_rundesk(self):
        # "rundesk uninstalled." after finding nothing reads as though something was there.
        gone = self.uninstall()
        self.assertEqual(gone.returncode, 0, gone.stderr)
        self.assertIn("nothing to remove", gone.stdout)
        self.assertNotIn("rundesk uninstalled", gone.stdout,
                         "it claimed to have uninstalled something it never found")


class WhatItWillNotDeleteTests(Sandbox):
    """Every test here is a bug that shipped. The installer runs `rm -rf` on a path a person
    can set, from a script people are told to pipe into bash."""

    def loose(self) -> Path:
        """install.sh on its own, with no source beside it — the `curl | bash` shape, which
        is the one that takes the download path and does the deleting."""
        alone = self.root / "loose"
        alone.mkdir(exist_ok=True)
        shutil.copy2(INSTALLER, alone / "install.sh")
        return alone

    def test_an_install_refuses_a_directory_too_important_to_be_one_programs(self):
        # RUNDESK_INSTALL_DIR is documented, and a typo that drops the last segment used to
        # be enough: pointing it at $HOME wiped the home directory and then reported that
        # rundesk was installed.
        treasure = self.home / "Documents"
        treasure.mkdir()
        (treasure / "thesis.txt").write_text("years of work")

        for target in (str(self.home), "/", "/opt", str(self.home) + "/"):
            with self.subTest(target=target):
                done = installer(home=self.home, bindir=self.bindir, cwd=self.loose(),
                                 script=self.loose() / "install.sh",
                                 extra_env={"RUNDESK_INSTALL_DIR": target})
                self.assertNotEqual(done.returncode, 0,
                                    f"the installer was willing to install into {target}")
                self.assertIn("error:", done.stderr.lower(),
                              f"installing into {target} failed without saying why")
                self.assertIn(target.rstrip("/") or "/", done.stderr,
                              f"the refusal did not name {target}")
        self.assertTrue((treasure / "thesis.txt").exists(),
                        "the installer deleted something it was refusing to install into")

    def test_an_install_refuses_to_replace_a_checkout_it_did_not_create(self):
        # A clone sitting at the install path was deleted, .git and all, by the download
        # path — because "is this a checkout" was answered by comparing paths.
        theirs = self.home / ".rundesk"
        theirs.mkdir(parents=True)
        (theirs / ".git").mkdir()
        (theirs / "MY-WORK.txt").write_text("uncommitted")

        done = installer(home=self.home, bindir=self.bindir, cwd=self.loose(),
                         script=self.loose() / "install.sh")

        self.assertNotEqual(done.returncode, 0, "the installer offered to replace a checkout")
        self.assertTrue((theirs / ".git").is_dir(), "the installer deleted a checkout's history")
        self.assertTrue((theirs / "MY-WORK.txt").exists(),
                        "the installer deleted a checkout's uncommitted work")

    def test_a_checkout_at_the_install_path_installs_itself_rather_than_downloading(self):
        # The other half of the same bug: a contributor who clones to ~/.rundesk should get
        # an install from that clone, not a download that replaces it.
        clone = self.home / ".rundesk"
        shutil.copytree(REPO, clone, ignore=shutil.ignore_patterns(".git", "__pycache__", ".venv"))
        (clone / ".git").mkdir()
        (clone / "MY-WORK.txt").write_text("uncommitted")

        done = installer(home=self.home, bindir=self.bindir, cwd=clone, script=clone / "install.sh")

        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("installing from this checkout", done.stdout)
        self.assertTrue((clone / "MY-WORK.txt").exists(), "installing from a clone destroyed it")
        self.assertEqual(os.readlink(self.bindir / "rundesk"), str(clone / "rundesk"))

    def test_removing_rundesk_leaves_a_checkout_where_it_stands(self):
        # Uninstall runs `rm -rf "$INSTALL_DIR"` too, and history is the thing that tells a
        # clone apart from a tree this installer unpacked.
        clone = self.home / ".rundesk"
        clone.mkdir(parents=True)
        (clone / ".git").mkdir()
        (clone / "MY-WORK.txt").write_text("uncommitted")

        gone = self.uninstall()

        self.assertEqual(gone.returncode, 0, gone.stderr)
        self.assertTrue((clone / "MY-WORK.txt").exists(), "uninstalling deleted a checkout")
        self.assertIn("left", gone.stdout.lower())

    def test_an_install_refuses_to_replace_a_command_of_the_same_name(self):
        # The removal path reads a link before removing it, so it never takes somebody
        # else's tool. The install path used to overwrite without looking.
        self.bindir.mkdir(parents=True)
        theirs = self.bindir / "rundesk"
        theirs.write_text("#!/bin/sh\necho a different rundesk\n")

        done = self.install()

        self.assertNotEqual(done.returncode, 0, "the installer overwrote another tool")
        self.assertEqual(theirs.read_text(), "#!/bin/sh\necho a different rundesk\n",
                         "the installer replaced a command it did not place")


class FakesTheFetch:
    """A download that answers from this machine, for the cases that drive the whole path.

    A mixin rather than a base case, so the classes that use it do not re-run each other's cases
    — and so the fake lives once. Nothing in this suite reaches the network (AGENTS.md), and for
    a shell script PATH is the seam a network call is passed through.
    """

    def fake_curl(self) -> Path:
        """A curl whose release reply and archive are local, with every request recorded."""
        bind = self.root / "fakebin"
        bind.mkdir(exist_ok=True)
        curl = bind / "curl"
        curl.write_text(
            "#!/bin/sh\n"
            "url=''\n"
            "out=''\n"
            "while [ $# -gt 0 ]; do\n"
            "  case \"$1\" in\n"
            "    -o) out=\"$2\"; shift ;;\n"
            "    http*) url=\"$1\" ;;\n"
            "  esac\n"
            "  shift\n"
            "done\n"
            "printf '%s\\n' \"$url\" >> \"$RUNDESK_REQUEST_LOG\"\n"
            "case \"$url\" in\n"
            "  https://api.github.com/*)\n"
            "    case \"$RUNDESK_LOOKUP_REPLY\" in\n"
            "      timeout) exit 28 ;;\n"
            "      forbidden|missing) exit 22 ;;\n"
            "      malformed) printf '%s\\n' 'not-json' > \"$out\" ;;\n"
            "      empty) printf '%s\\n' '{\"tag_name\":\"\"}' > \"$out\" ;;\n"
            "      valid) printf '{\"tag_name\":\"%s\"}\\n' \"${RUNDESK_LOOKUP_TAG:-v9.9.9}\" > \"$out\" ;;\n"
            "    esac\n"
            "    ;;\n"
            "  https://github.com/*/releases/download/*)\n"
            "    if [ \"${RUNDESK_COUNTED_ASSET_MISSING:-}\" = yes ]; then exit 22; fi\n"
            "    cp \"$RUNDESK_RELEASE_ARCHIVE\" \"$out\"\n"
            "    ;;\n"
            "  *) cp \"$RUNDESK_RELEASE_ARCHIVE\" \"$out\" ;;\n"
            "esac\n"
        )
        curl.chmod(0o755)
        return bind

    def release_archive(self) -> Path:
        source = self.root / "rundesk-cli-v9.9.9"
        shutil.copytree(REPO, source, ignore=shutil.ignore_patterns(".git", "__pycache__", ".venv"))
        tarball = self.root / "release.tar.gz"
        subprocess.run(["tar", "-czf", str(tarball), "-C", str(self.root), source.name], check=True)
        return tarball

    def attempt(
        self,
        reply: str,
        tarball: Path,
        counted_asset_missing: bool = False,
        tag: str = "v9.9.9",
    ):
        case = self.root / f"{reply}-{tag}"
        home, bindir, loose = case / "home", case / "bin", case / "loose"
        home.mkdir(parents=True)
        bindir.mkdir()
        loose.mkdir()
        shutil.copy2(INSTALLER, loose / "install.sh")
        install = home / ".rundesk"
        install.mkdir()
        marker = install / "existing-install.marker"
        marker.write_text("the released install")
        current = install / "rundesk"
        current.write_text("#!/bin/sh\necho 'the released install'\n")
        current.chmod(0o755)
        command = bindir / "rundesk"
        command.symlink_to(current)
        requests = case / "requests.txt"
        done = installer(
            home=home,
            bindir=bindir,
            cwd=loose,
            script=loose / "install.sh",
            extra_env={
                "PATH": f"{self.fake_curl()}{os.pathsep}{os.environ['PATH']}",
                "RUNDESK_LOOKUP_REPLY": reply,
                "RUNDESK_LOOKUP_TAG": tag,
                "RUNDESK_REQUEST_LOG": str(requests),
                "RUNDESK_RELEASE_ARCHIVE": str(tarball),
                "RUNDESK_COUNTED_ASSET_MISSING": "yes" if counted_asset_missing else "no",
            },
        )
        return done, marker, command, requests.read_text().splitlines()


class ReleaseLookupTests(FakesTheFetch, Sandbox):
    """A remote install changes nothing until it knows which release it is installing."""

    def test_release_lookup_failures_leave_the_existing_install_alone(self):
        """R-INS-15 — uncertainty is not permission to install unreleased work."""
        tarball = self.release_archive()
        for reply in ("timeout", "forbidden", "missing", "malformed", "empty"):
            with self.subTest(reply=reply):
                done, marker, command, requests = self.attempt(reply, tarball)
                self.assertNotEqual(done.returncode, 0, done.stdout)
                self.assertIn("could not determine the newest release", done.stderr)
                self.assertTrue(marker.exists(), "the failed lookup replaced the existing install")
                self.assertEqual(str(marker.parent / "rundesk"), os.readlink(command),
                                 "the failed lookup replaced the existing command")
                self.assertFalse(any("refs/heads/main" in request for request in requests),
                                 "the failed lookup requested unreleased work")
                # What this means, rather than how many calls it takes to mean it: nothing
                # was *downloaded*. Asked as a count of requests, it broke the day the
                # lookup learned to ask the website before the API — two ways of finding
                # the newest release, neither of which is fetching anything.
                self.assertFalse(any("archive/" in request for request in requests),
                                 "the failed lookup went on to download an archive")

    def test_a_valid_release_response_installs_only_its_exact_tag(self):
        """R-INS-15 — the tag returned by the release lookup is the archive installed."""
        done, marker, _, requests = self.attempt("valid", self.release_archive())
        self.assertEqual(done.returncode, 0, f"{done.stdout}\n{done.stderr}")
        self.assertFalse(marker.exists(), "the valid release did not replace the existing install")
        self.assertEqual(
            "https://github.com/rundesk-ai/rundesk-cli/releases/download/"
            "v9.9.9/rundesk-cli.tar.gz",
            requests[-1],
        )
        self.assertFalse(any("refs/heads/main" in request for request in requests))

    def test_a_remote_install_downloads_the_counted_release_asset_once(self):
        """R-INS-20 — one remote install contributes one public install delivery."""
        done, _, _, requests = self.attempt("valid", self.release_archive())
        self.assertEqual(done.returncode, 0, f"{done.stdout}\n{done.stderr}")
        deliveries = [
            request for request in requests
            if "/releases/download/" in request
        ]
        self.assertEqual(
            deliveries,
            [
                "https://github.com/rundesk-ai/rundesk-cli/releases/download/"
                "v9.9.9/rundesk-cli.tar.gz"
            ],
        )

    def test_a_release_from_before_the_counted_asset_still_installs(self):
        """The new bootstrap must remain compatible with every already-published release."""
        done, marker, _, requests = self.attempt(
            "valid",
            self.release_archive(),
            counted_asset_missing=True,
            tag="v0.22.3",
        )
        self.assertEqual(done.returncode, 0, f"{done.stdout}\n{done.stderr}")
        self.assertFalse(marker.exists(), "the legacy release did not replace the install")
        self.assertEqual(
            requests[-2:],
            [
                "https://github.com/rundesk-ai/rundesk-cli/releases/download/"
                "v0.22.3/rundesk-cli.tar.gz",
                "https://github.com/rundesk-ai/rundesk-cli/archive/refs/tags/"
                "v0.22.3.tar.gz",
            ],
        )

    def test_a_counted_release_never_falls_back_to_an_uncounted_download(self):
        """R-INS-20 — a failed counted delivery is a failed install, not hidden activity."""
        done, marker, _, requests = self.attempt(
            "valid",
            self.release_archive(),
            counted_asset_missing=True,
            tag="v0.22.4",
        )
        self.assertNotEqual(done.returncode, 0)
        self.assertTrue(marker.exists(), "the failed counted delivery replaced the install")
        self.assertEqual(
            requests[-1],
            "https://github.com/rundesk-ai/rundesk-cli/releases/download/"
            "v0.22.4/rundesk-cli.tar.gz",
        )
        self.assertFalse(
            any("archive/refs/tags/v0.22.4" in request for request in requests),
            "the counted release silently installed through an uncounted fallback",
        )


class WhereADownloadedProgramLands(FakesTheFetch, Sandbox):
    """R-INS-13, R-RM-12 — the layout every removal guarantee rests on.

    Driven through the whole download path with the fetch faked on PATH, because the alternative
    — leaving it to CI's real published install — cannot cover a change to the installer until a
    release already carries it, which is the wrong way round.
    """

    def test_a_downloaded_install_puts_the_program_in_its_own_directory(self):
        """R-INS-13 — what an uninstall removes is one directory, and nothing of the owner's is
        inside it. Beside the data, removal had to be told a list of names to spare."""
        done, marker, command, _ = self.attempt("valid", self.release_archive())
        self.assertEqual(done.returncode, 0, f"{done.stdout}\n{done.stderr}")
        install = marker.parent
        self.assertTrue((install / "app" / "rundesk").is_file(),
                        f"the program is not where an uninstall will look: {done.stdout}")
        self.assertFalse((install / "rundesk").exists(),
                         "the program was laid down beside the data again")
        self.assertEqual(str(install / "app" / "rundesk"), os.readlink(command),
                         "the command on PATH points at the older place")

    def test_installing_over_the_layout_from_before_leaves_what_the_owner_keeps(self):
        """R-INS-13 — the older program is taken out rather than left as a second rundesk beside
        the data, and what the owner keeps is not touched on the way. A stale `src/` there is the
        one a bare `python3 -` in the installer would find first."""
        case = self.root / "carried-forward"
        home, bindir, loose = case / "home", case / "bin", case / "loose"
        home.mkdir(parents=True)
        bindir.mkdir()
        loose.mkdir()
        shutil.copy2(INSTALLER, loose / "install.sh")
        install = home / ".rundesk"
        # The layout from before: the program directly in the install directory, with the
        # owner's things beside it.
        (install / "src" / "rundesk").mkdir(parents=True)
        (install / "rundesk").write_text("#!/bin/sh\necho old\n")
        (install / "rundesk").chmod(0o755)
        (install / "agents" / "ava").mkdir(parents=True)
        (install / "agents" / "ava" / "state.db").write_text("records\n")
        (install / "logs").mkdir()
        (install / "logs" / "ava.log").write_text("what happened\n")

        done = installer(
            home=home, bindir=bindir, cwd=loose, script=loose / "install.sh",
            extra_env={
                "PATH": f"{self.fake_curl()}{os.pathsep}{os.environ['PATH']}",
                "RUNDESK_LOOKUP_REPLY": "valid",
                "RUNDESK_REQUEST_LOG": str(case / "requests.txt"),
                "RUNDESK_RELEASE_ARCHIVE": str(self.release_archive()),
            },
        )

        self.assertEqual(done.returncode, 0, f"{done.stdout}\n{done.stderr}")
        self.assertTrue((install / "app" / "rundesk").is_file())
        self.assertFalse((install / "src").exists(), "the older program was left beside the data")
        for what, at in (("an agent's records", install / "agents" / "ava" / "state.db"),
                         ("what a gateway wrote", install / "logs" / "ava.log")):
            self.assertTrue(at.exists(), f"moving the program took {what}")


class OneInstructionTests(unittest.TestCase):
    """The single line a machine with nothing on it is given, and what has to hold for it to work.

    The instruction is published in four places and uses the stable bootstrap on the default
    branch. That bootstrap fetches the counted release asset, rather than itself being a second
    counted download for every first install.
    """

    #: Both the current bootstrap and the retired release-asset route. Recognizing only
    #: the current form let a stale instruction survive after releases stopped carrying it.
    PUBLISHED = re.compile(
        r"https://(?:raw\.githubusercontent\.com/[\w.-]+/[\w.-]+/main/"
        r"|github\.com/[\w.-]+/[\w.-]+/releases/latest/download/)install\.sh"
    )
    SLUG = re.compile(
        r"https://(?:raw\.githubusercontent\.com|github\.com)/"
        r"([\w.-]+/[\w.-]+)/"
    )

    SKIP = {".git", ".venv", "__pycache__", "node_modules"}

    def _gives_it(self) -> dict:
        """Every file in the repository that tells anyone how to install rundesk.

        Found rather than listed. The first version of this test hand-kept the four files it
        knew about — and the same commit added the URL to build.yml twice, outside the list,
        which is exactly the drift it was written to stop.
        """
        found = {}
        for path in sorted(REPO.rglob("*")):
            if not path.is_file() or self.SKIP & set(path.relative_to(REPO).parts):
                continue
            if path.stat().st_size > 1_000_000:
                continue
            hits = set(self.PUBLISHED.findall(path.read_text(encoding="utf-8", errors="ignore")))
            if hits:
                found[str(path.relative_to(REPO))] = hits
        return found

    def _published(self) -> set:
        gives_it = self._gives_it()
        self.assertTrue(gives_it, "nothing in the repository says how to install rundesk")
        return set().union(*gives_it.values())

    def test_the_one_instruction_names_the_same_thing_everywhere_it_is_given(self):
        # Every file that publishes the instruction has to publish the same one. Two of them
        # disagreeing sends somebody to a URL nothing serves, and both files look right.
        gives_it = self._gives_it()
        self.assertEqual(len(self._published()), 1,
                         "the install instruction differs between " + ", ".join(sorted(gives_it)))

    def test_the_one_instruction_points_at_the_repository_rundesk_updates_from(self):
        # An install from one repository that then updates from another is two products
        # wearing one name — and nothing on disk remembers where a copy came from, so the
        # only thing keeping them together is that both name the same repository.
        sys.path.insert(0, str(REPO / "src"))
        from rundesk import updater

        (published,) = self._published()
        found = self.SLUG.match(published)
        self.assertIsNotNone(found, "the published instruction has no repository")
        slug = found.group(1)
        declared = re.search(r'^REPO_SLUG="([^"]+)"', INSTALLER.read_text(), re.M)
        self.assertIsNotNone(declared, "the installer does not say which repository it installs from")
        self.assertEqual(declared.group(1), slug,
                         "the published instruction and the installer name different repositories")
        self.assertEqual(updater.REPO_SLUG, slug,
                         "the installer fetches from one repository and `rundesk update` from another")

    def test_the_installer_offers_no_way_to_point_it_at_another_repository(self):
        # It used to. `install.sh` honoured RUNDESK_REPO_SLUG while the updater hardcoded
        # its own, so installing from a fork gave a copy that updated itself from upstream
        # forever. Nothing set it, no requirement asked for it, and it could not be made
        # coherent without recording the origin somewhere on disk.
        self.assertNotIn("RUNDESK_REPO_SLUG", INSTALLER.read_text(),
                         "the installer can be pointed somewhere `rundesk update` will not follow")

    def test_a_release_serves_one_counted_program_archive(self):
        """R-INS-20, R-UPD-49 — installs and updates share one counted delivery."""
        workflow = (REPO / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
        attached = re.search(r"^\s*files:\s*(.+)$", workflow, re.M)
        self.assertIsNotNone(attached, "a release attaches no counted program archive")
        carried = {f.strip() for f in re.split(r"[,\n]", attached.group(1)) if f.strip()}
        self.assertEqual(carried, {"rundesk-cli.tar.gz"},
                         "a delivery must increment the public count exactly once")
        self.assertIn("git archive ", workflow,
                      "the release names an archive it never builds")
        self.assertIn(
            '--prefix="rundesk-cli-${GITHUB_REF_NAME}/"',
            workflow,
            "the release archive root is not one the installer accepts",
        )
        self.assertIn("gzip -9 > rundesk-cli.tar.gz", workflow,
                      "the release builds a differently named archive")

        installer = INSTALLER.read_text(encoding="utf-8")
        sys.path.insert(0, str(REPO / "src"))
        from rundesk import updater

        self.assertIn(
            "/releases/download/$tag/rundesk-cli.tar.gz",
            installer,
            "the remote installer does not fetch the counted release asset",
        )
        self.assertEqual(
            updater.ARCHIVE_URL,
            "https://github.com/rundesk-ai/rundesk-cli/releases/download/"
            "{tag}/rundesk-cli.tar.gz",
            "updates do not fetch the same counted release asset",
        )

    def test_the_readme_still_calls_the_public_delivery_count_installs(self):
        """Owner signoff: the public badge remains labelled installs."""
        readme = (REPO / "README.md").read_text(encoding="utf-8")
        self.assertIn(
            "img.shields.io/github/downloads/rundesk-ai/rundesk-cli/"
            "total?label=installs",
            readme,
        )


class DownloadedInstallTests(Sandbox):
    def test_removing_an_install_the_installer_made_takes_its_directory(self):
        # A downloaded install is a directory full of source with an install.sh in it —
        # indistinguishable from a clone, unless the one thing that tells them apart is
        # checked: whether it is the directory the installer was told to create.
        made = self.home / ".rundesk" / "app"
        shutil.copytree(REPO, made, ignore=shutil.ignore_patterns(".git", "__pycache__", ".venv"))
        (self.bindir).mkdir(parents=True, exist_ok=True)
        (self.bindir / "rundesk").symlink_to(made / "rundesk")

        gone = installer("--uninstall", home=self.home, bindir=self.bindir,
                         cwd=made, script=made / "install.sh")

        self.assertEqual(gone.returncode, 0, gone.stderr)
        self.assertFalse(made.exists(), "uninstalling left behind the directory the installer created")
        self.assertFalse((self.home / ".rundesk").exists(),
                         "nothing of the owner's was there, so the directory should have gone too")

    def test_removing_the_program_cannot_reach_what_the_owner_keeps(self):
        """R-RM-11 — not "remembers not to": the program has a directory of its own, so removal
        takes one path and there is nothing of the owner's inside it to spare. There was a list
        of names to keep, and a list is a thing that stops being true the day something is added
        beside it — `rm -rf "$INSTALL_DIR"` had already taken every gateway log once."""
        made = self.home / ".rundesk" / "app"
        shutil.copytree(REPO, made, ignore=shutil.ignore_patterns(".git", "__pycache__", ".venv"))
        theirs = self.home / ".rundesk"
        (theirs / "agents" / "ava" / "home").mkdir(parents=True)
        (theirs / "agents" / "ava" / "home" / "SOUL.md").write_text("mine\n")
        (theirs / "logs").mkdir()
        (theirs / "logs" / "ava.log").write_text("what happened\n")
        # Something nobody has thought of yet, which is the whole point: a keep-list would
        # not have this name in it.
        (theirs / "something-added-later").mkdir()
        (theirs / "something-added-later" / "kept.txt").write_text("also mine\n")

        gone = installer("--uninstall", home=self.home, bindir=self.bindir,
                         cwd=made, script=made / "install.sh")

        self.assertEqual(gone.returncode, 0, gone.stderr)
        self.assertFalse(made.exists(), "the program was left behind")
        self.assertEqual("mine\n", (theirs / "agents" / "ava" / "home" / "SOUL.md").read_text())
        self.assertEqual("what happened\n", (theirs / "logs" / "ava.log").read_text())
        self.assertEqual("also mine\n", (theirs / "something-added-later" / "kept.txt").read_text(),
                         "removal reached something no keep-list would have named")

    def test_purging_takes_what_the_owner_keeps_as_well(self):
        """R-RM-11 — the other half, so "cannot reach it" cannot pass by never removing it."""
        made = self.home / ".rundesk" / "app"
        shutil.copytree(REPO, made, ignore=shutil.ignore_patterns(".git", "__pycache__", ".venv"))
        theirs = self.home / ".rundesk"
        (theirs / "agents" / "ava").mkdir(parents=True)
        (theirs / "agents" / "ava" / "state.db").write_text("records\n")

        gone = installer("--uninstall", "--purge", home=self.home, bindir=self.bindir,
                         cwd=made, script=made / "install.sh")

        self.assertEqual(gone.returncode, 0, gone.stderr)
        self.assertFalse(theirs.exists(), "--purge left what the owner kept behind")

    def test_removing_rundesk_keeps_the_copies_it_took(self):
        """R-RM-14 — the copies are the thing somebody reaches for after removing rundesk,
        and an ordinary uninstall has never had any business with what the owner keeps."""
        made = self.home / ".rundesk" / "app"
        shutil.copytree(REPO, made, ignore=shutil.ignore_patterns(".git", "__pycache__", ".venv"))
        copies = self.home / ".rundesk" / "backups"
        copies.mkdir(parents=True)
        (copies / "rundesk-data-2026-07-27-040000Z.zip").write_text("a copy\n")

        gone = installer("--uninstall", home=self.home, bindir=self.bindir,
                         cwd=made, script=made / "install.sh")

        self.assertEqual(gone.returncode, 0, gone.stderr)
        self.assertEqual("a copy\n",
                         (copies / "rundesk-data-2026-07-27-040000Z.zip").read_text())

    def test_purging_keeps_the_copies_it_took(self):
        """R-RM-14 — **the one thing a purge does not take.** The whole reason somebody
        purges is that something is wrong, and that is the worst possible moment to delete
        the only copy of what they had. This used to be `rm -rf` over the install directory,
        which would have taken them."""
        made = self.home / ".rundesk" / "app"
        shutil.copytree(REPO, made, ignore=shutil.ignore_patterns(".git", "__pycache__", ".venv"))
        theirs = self.home / ".rundesk"
        (theirs / "data" / "agents" / "ava").mkdir(parents=True)
        (theirs / "data" / "agents" / "ava" / "state.db").write_text("records\n")
        copies = theirs / "backups"
        copies.mkdir()
        (copies / "rundesk-data-2026-07-27-040000Z.zip").write_text("a copy\n")

        gone = installer("--uninstall", "--purge", home=self.home, bindir=self.bindir,
                         cwd=made, script=made / "install.sh")

        self.assertEqual(gone.returncode, 0, gone.stderr)
        self.assertFalse((theirs / "data").exists(), "--purge left what the owner kept behind")
        self.assertFalse(made.exists(), "--purge left the program behind")
        self.assertEqual("a copy\n",
                         (copies / "rundesk-data-2026-07-27-040000Z.zip").read_text(),
                         "a purge took the copies with it")
        self.assertIn("backups", gone.stdout,
                      "it never said the copies had been kept")

    def test_removing_rundesk_says_the_copies_are_kept_rather_than_offering_to_purge_them(self):
        """R-RM-14 — listing them under "add --purge to delete them" would be a lie, and the
        one place an owner looks for how to be rid of one is the message that mentions it."""
        made = self.home / ".rundesk" / "app"
        shutil.copytree(REPO, made, ignore=shutil.ignore_patterns(".git", "__pycache__", ".venv"))
        copies = self.home / ".rundesk" / "backups"
        copies.mkdir(parents=True)
        (copies / "rundesk-data-2026-07-27-040000Z.zip").write_text("a copy\n")

        gone = installer("--uninstall", "--purge", home=self.home, bindir=self.bindir,
                         cwd=made, script=made / "install.sh")

        self.assertEqual(gone.returncode, 0, gone.stderr)
        self.assertIn("rundesk backups remove", gone.stdout,
                      "it kept them and never said how to be rid of one")

    def test_purging_refuses_rather_than_deleting_copies_kept_inside_the_data(self):
        """R-RM-14 — the one axis along which "backups always survive" could be broken, and
        it is a documented one: the backup directory is the one place an owner may point
        anywhere, which includes inside the data a purge deletes. Refused rather than worked
        around, because quietly keeping half the data would make a purge mean different
        things on different machines — and refused *before* anything is removed, or the
        message saying nothing was removed is itself untrue."""
        made = self.home / ".rundesk" / "app"
        shutil.copytree(REPO, made, ignore=shutil.ignore_patterns(".git", "__pycache__", ".venv"))
        theirs = self.home / ".rundesk"
        (theirs / "data" / "agents" / "ava").mkdir(parents=True)
        (theirs / "data" / "agents" / "ava" / "state.db").write_text("records\n")
        inside = theirs / "data" / "kept-here"
        inside.mkdir()
        (inside / "rundesk-data-2026-07-27-040000Z.zip").write_text("a copy\n")

        gone = installer("--uninstall", "--purge", home=self.home, bindir=self.bindir,
                         cwd=made, script=made / "install.sh",
                         extra_env={"RUNDESK_BACKUP_DIR": str(inside)})

        self.assertNotEqual(0, gone.returncode, "it purged anyway")
        self.assertEqual("a copy\n",
                         (inside / "rundesk-data-2026-07-27-040000Z.zip").read_text(),
                         "a purge deleted the copies it promised to keep")
        self.assertTrue((theirs / "data" / "agents" / "ava").exists(),
                        "it said nothing was removed and removed something")
        self.assertTrue(made.exists(), "it said nothing was removed and took the program")
        self.assertIn("RUNDESK_BACKUP_DIR", gone.stderr + gone.stdout,
                      "it refused without saying what to change")

    def test_taking_the_older_program_away_keeps_copies_standing_beside_it(self):
        """R-RM-14 — an install still on the layout from before `app/` can have copies beside
        it too, and the sweep that tidies that layout spares a fixed list of names. A list is
        safe only while nothing new is ever added next to it, and this is the something."""
        made = self.home / ".rundesk"
        shutil.copytree(REPO, made, ignore=shutil.ignore_patterns(".git", "__pycache__", ".venv"))
        copies = made / "backups"
        copies.mkdir()
        (copies / "rundesk-data-2026-07-27-040000Z.zip").write_text("a copy\n")

        gone = installer("--uninstall", home=self.home, bindir=self.bindir,
                         cwd=made, script=made / "install.sh")

        self.assertEqual(gone.returncode, 0, gone.stderr)
        self.assertFalse((made / "src").exists(), "the older program was left behind")
        self.assertEqual("a copy\n",
                         (copies / "rundesk-data-2026-07-27-040000Z.zip").read_text(),
                         "tidying the older layout took the copies with it")

    def test_removing_an_install_from_before_the_program_had_its_own_directory(self):
        """R-RM-8 — somebody updating and then removing would otherwise be left with the older
        rundesk still sitting beside their agents, and still on their PATH."""
        made = self.home / ".rundesk"
        shutil.copytree(REPO, made, ignore=shutil.ignore_patterns(".git", "__pycache__", ".venv"))
        (made / "agents" / "ava" / "home").mkdir(parents=True)
        (made / "agents" / "ava" / "home" / "SOUL.md").write_text("mine\n")

        gone = installer("--uninstall", home=self.home, bindir=self.bindir,
                         cwd=made, script=made / "install.sh")

        self.assertEqual(gone.returncode, 0, gone.stderr)
        self.assertFalse((made / "src").exists(), "the older program was left behind")
        self.assertFalse((made / "rundesk").exists())
        self.assertEqual("mine\n", (made / "agents" / "ava" / "home" / "SOUL.md").read_text(),
                         "taking the older program away took an agent with it")


class WhatAShippedProgramLooksForTheVirtualenvIn(unittest.TestCase):
    """R-INS-3, R-INS-4 — a program that ships with rundesk finds the install's own.

    An adapter is run with a built environment and almost no PATH, so nothing has put the
    virtualenv on its path: each one counts up from where it stands to find it. **That count
    is the thing that rots.** It was written for a tree in which the adapters lived one
    directory deeper, went on being written after they moved, and then looked *above* the
    install — so an owner adding a channel was told to run the installer that had already
    put the dependency exactly where it belonged, and nothing failed until they did.

    Read off the source rather than by running one, so an adapter that cannot run on this
    machine is still checked, and a new one is covered the day it lands.
    """

    #: `Path(__file__).resolve().parents[N]` — the count that has to match how deep the
    #: file actually stands, and the one thing a restructure silently invalidates.
    COUNTS = re.compile(r"parents\[(\d+)\]")

    def shipped(self) -> list:
        """Every program rundesk ships, whichever directory beside the core it stands in."""
        found = [one for where in ("providers", "channels")
                 for one in sorted((CHECKOUT / "src" / where).iterdir())
                 if one.is_file() and not one.name.startswith(".")]
        self.assertTrue(found, "this checkout ships no programs at all")
        return found

    def test_a_shipped_program_reaches_for_the_installs_own_virtualenv(self):
        for at in self.shipped():
            # Code, not prose. The comment beside one of these explains the count that was
            # wrong, and a check that read commentary would fail on the explanation.
            said = "\n".join(line for line in at.read_text(
                encoding="utf-8", errors="replace").splitlines()
                if not line.lstrip().startswith("#"))
            for count in self.COUNTS.findall(said):
                with self.subTest(program=at.name, count=count):
                    reached = at.resolve().parents[int(count)]
                    self.assertEqual(
                        CHECKOUT, reached,
                        f"{at.name} counts {count} directories up and lands on {reached}, "
                        f"which is not the install — it would look for the virtualenv, or "
                        f"anything else of the install's, outside it")

    def test_a_program_that_needs_a_dependency_says_where_it_looked(self):
        """R-INS-4 — nothing is ever left for a person to `pip install` by hand, so the one
        thing a refusal must carry is where it looked: an owner told only "not installed",
        by an install that installed it, has nowhere to go."""
        needing = [at for at in self.shipped()
                   if ".venv" in at.read_text(encoding="utf-8", errors="replace")]
        self.assertTrue(needing, "no shipped program reaches for the virtualenv at all")
        for at in needing:
            said = at.read_text(encoding="utf-8", errors="replace")
            with self.subTest(program=at.name):
                self.assertIn("looked in", said,
                              f"{at.name} refuses without saying where it looked")


if __name__ == "__main__":
    unittest.main(verbosity=2)
