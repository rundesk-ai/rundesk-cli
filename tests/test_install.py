#!/usr/bin/env python3
"""Putting the command on a machine, and taking it off again.

The installer is shell, so it is tested by running it — into a throwaway PATH directory
with a throwaway HOME, so nothing here can touch the machine it runs on.

Run: python3 tests/test_install.py
"""

from __future__ import annotations

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
shutil.copytree(CHECKOUT, REPO, ignore=shutil.ignore_patterns(".git", "__pycache__", ".venv"))
INSTALLER = REPO / "install.sh"


def installer(*args: str, home: Path, bindir: Path, cwd: Path | None = None,
              script: Path | None = None, extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    """Run the installer somewhere it cannot reach the real machine."""
    env = {
        **os.environ,
        "HOME": str(home),
        "RUNDESK_BIN_DIR": str(bindir),
        "RUNDESK_INSTALL_DIR": str(home / ".rundesk"),
        # Never the real requirements file: installing it here would reach the network and
        # take a minute, in a suite that must do neither.
        "RUNDESK_REQUIREMENTS": str(home / "no-requirements.txt"),
        **(extra_env or {}),
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
        from rundesk_cli import supervisor
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
        from rundesk_cli import gateway, supervisor
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
            {"python3", "curl", "tar"},
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
        self.assertFalse((self.home / ".rundesk").exists(), "it downloaded a second copy beside the checkout")


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
        self.assertTrue((REPO / "src" / "rundesk_cli" / "cli.py").exists())

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

    def test_removing_rundesk_keeps_what_the_gateways_wrote_unless_asked_to_take_it(self):
        """R-RM-10 — `rm -rf` on the install directory took the whole audit trail with the
        program, at the one moment an owner is most likely to want it: a reinstall after
        trouble. The command someone runs to fix the trouble was deleting the account of
        what the trouble was (R-GW-18)."""
        wrote = self.home / ".rundesk" / "logs"
        scheduled = self.home / ".rundesk" / "schedules"
        for made in (wrote, scheduled):
            made.mkdir(parents=True)
        (wrote / "gateway.log").write_text("what happened\n")
        (scheduled / "gateway.json").write_text('[{"name": "nightly"}]\n')
        (scheduled / "gateway.ran.json").write_text('{"nightly": {"outcome": "finished"}}\n')

        self.install()
        kept = self.uninstall()

        self.assertEqual(kept.returncode, 0, kept.stderr)
        self.assertEqual("what happened\n", (wrote / "gateway.log").read_text(),
                         "an ordinary uninstall took the gateway's log")
        self.assertTrue((scheduled / "gateway.json").exists(), "it took the owner's schedules")
        self.assertTrue((scheduled / "gateway.ran.json").exists(),
                        "it took the account of what the schedules did")
        self.assertIn("--purge", kept.stdout, "it never said how to take them")

    def test_removing_rundesk_keeps_every_agents_home(self):
        """R-AGT-3 — an agent's home is what its owner wrote in it: its rules, who it works
        for, what it has learned. Removing the program is not asking for that to go, and it
        sits under the install directory only because that is where rundesk keeps things."""
        home = self.home / ".rundesk" / "agents" / "ava" / "home"
        (home / "workspace").mkdir(parents=True)
        (home / "SOUL.md").write_text("what ava is for, in my own words\n")
        (self.home / ".rundesk" / "agents" / "ava" / "schedules").mkdir(parents=True)

        self.install()
        kept = self.uninstall()

        self.assertEqual(kept.returncode, 0, kept.stderr)
        self.assertEqual("what ava is for, in my own words\n", (home / "SOUL.md").read_text(),
                         "an ordinary uninstall took an agent's home")
        self.assertTrue((home / "workspace").is_dir(), "it took the agent's workspace")

    def test_purging_takes_every_agents_home_as_well(self):
        """R-AGT-3 — the other half, so "keeps it" cannot pass by never removing anything."""
        agents = self.home / ".rundesk" / "agents"
        (agents / "ava" / "home").mkdir(parents=True)
        (agents / "ava" / "home" / "SOUL.md").write_text("mine\n")

        self.install()
        purged = self.uninstall("--purge")

        self.assertEqual(purged.returncode, 0, purged.stderr)
        self.assertFalse(agents.exists(), "--purge left an agent's home behind")

    def test_purging_takes_what_the_gateways_wrote_as_well(self):
        """R-RM-10 — the other half, so "keeps it" cannot pass by never removing anything."""
        wrote = self.home / ".rundesk" / "logs"
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
        self.assertIn(".venv", (REPO / "install.sh").read_text())
        installed_into = re.findall(r"python3 -m venv \"([^\"]+)\"", (REPO / "install.sh").read_text())
        self.assertEqual(installed_into, ['$REPO_ROOT/.venv'],
                         "the installer puts dependencies somewhere other than inside the install")

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
        names = set()
        for line in (REPO / "requirements.txt").read_text().split("\n"):
            line = line.split("#")[0].strip()
            if line:
                names.add(re.split(r"[=<>!\[ ]", line)[0].lower().replace("-", "_"))
        return names

    def test_everything_the_code_imports_is_the_standard_library_or_declared(self):
        # The failure this stops: an import added without a line in requirements.txt. The
        # install succeeds, the command is on the PATH, and it dies at the first use.
        import ast, sys, sysconfig

        stdlib = Path(sysconfig.get_paths()["stdlib"]).resolve()
        ours = {p.stem for p in (REPO / "src" / "rundesk_cli").glob("*.py")} | {"rundesk_cli"}
        declared = self._declared()
        # discord.py installs as `discord`; a package name is not always its module name.
        aliases = {"discord.py": "discord", "discord_py": "discord"}
        declared |= {aliases[d] for d in list(declared) if d in aliases}

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
        installer_text = (REPO / "install.sh").read_text()
        self.assertIn("pip check", installer_text, "nothing verifies the dependencies fit together")
        self.assertIn("do not fit together", installer_text, "a broken dependency set fails without saying why")

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
        # *backwards* onto. The branch is the fallback for a repository with no release yet.
        script = INSTALLER.read_text()
        self.assertIn("releases/latest", script, "the installer does not ask what the newest release is")
        self.assertIn("archive/refs/tags/", script, "the installer never downloads a released tag")
        branch = script.index("archive/refs/heads/main")
        tags = script.index("archive/refs/tags/")
        self.assertLess(tags, branch, "the branch is preferred over the released tag")
        self.assertIn("no release published yet", script, "a repository with no release could not be installed")


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


class NoReleaseYetTests(Sandbox):
    """The branch that runs when the release lookup comes back with nothing."""

    def fake_curl(self, tarball: Path) -> Path:
        """A curl that fails the way the real one does on a repository with no releases, and
        serves a prepared archive for anything else. Offline, so the suite stays offline."""
        bind = self.root / "fakebin"
        bind.mkdir(exist_ok=True)
        curl = bind / "curl"
        curl.write_text(
            "#!/bin/sh\n"
            "out=''\n"
            "for a in \"$@\"; do case \"$a\" in https://api.github.com/*) exit 22;; esac; done\n"
            "while [ $# -gt 0 ]; do case \"$1\" in -o) out=\"$2\"; shift;; esac; shift; done\n"
            f"[ -n \"$out\" ] && cp {tarball} \"$out\"\n"
        )
        curl.chmod(0o755)
        return bind

    def test_a_release_lookup_that_fails_falls_back_instead_of_dying_silently(self):
        # `set -e` aborts on a failing assignment and `-o pipefail` fails the pipeline
        # whenever curl does, so this fallback was unreachable: a repository with no
        # releases, or a rate limit, killed the install on exit 56 having printed nothing.
        source = self.root / "rundesk-cli-main"
        shutil.copytree(REPO, source, ignore=shutil.ignore_patterns(".git", "__pycache__", ".venv"))
        tarball = self.root / "main.tar.gz"
        subprocess.run(["tar", "-czf", str(tarball), "-C", str(self.root), source.name], check=True)

        loose = self.root / "loose"
        loose.mkdir()
        shutil.copy2(INSTALLER, loose / "install.sh")
        done = installer(home=self.home, bindir=self.bindir, cwd=loose, script=loose / "install.sh",
                         extra_env={"PATH": f"{self.fake_curl(tarball)}{os.pathsep}{os.environ['PATH']}"})

        self.assertEqual(done.returncode, 0,
                         f"a repository with no releases could not be installed:\n{done.stdout}\n{done.stderr}")
        self.assertIn("no release published yet", done.stdout)
        answered = subprocess.run([str(self.bindir / "rundesk"), "version"],
                                  capture_output=True, text=True)
        self.assertEqual(answered.returncode, 0, answered.stderr)


class OneInstructionTests(unittest.TestCase):
    """The single line a machine with nothing on it is given, and what has to hold for it to work.

    The instruction is published in four places and resolves only because the release workflow
    attaches that exact file. Nothing coupled the two, so deleting one line from `release.yml`
    would have turned every documented instruction into a 404 with the whole gate still green.
    """

    #: `https://github.com/<slug>/releases/latest/download/<asset>`
    PUBLISHED = re.compile(r"https://github\.com/([\w.-]+/[\w.-]+)/releases/latest/download/([\w.-]+)")

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
        from rundesk_cli import updater

        (slug, _asset), = self._published()
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

    def test_a_release_serves_the_file_the_one_instruction_asks_for(self):
        # `releases/latest/download/<asset>` resolves only if the release carries that asset.
        # Drop it from the workflow and every instruction above becomes a 404.
        (_slug, asset), = self._published()
        workflow = (REPO / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
        attached = re.search(r"^\s*files:\s*(.+)$", workflow, re.M)
        self.assertIsNotNone(attached, "a release attaches no files, so the install instruction 404s")
        carried = {f.strip() for f in re.split(r"[,\n]", attached.group(1)) if f.strip()}
        self.assertIn(asset, carried,
                      f"the instruction downloads {asset}, which no release attaches")


class DownloadedInstallTests(Sandbox):
    def test_removing_an_install_the_installer_made_takes_its_directory(self):
        # A downloaded install is a directory full of source with an install.sh in it —
        # indistinguishable from a clone, unless the one thing that tells them apart is
        # checked: whether it is the directory the installer was told to create.
        made = self.home / ".rundesk"
        shutil.copytree(REPO, made, ignore=shutil.ignore_patterns(".git", "__pycache__", ".venv"))
        (self.bindir).mkdir(parents=True, exist_ok=True)
        (self.bindir / "rundesk").symlink_to(made / "rundesk")

        gone = installer("--uninstall", home=self.home, bindir=self.bindir,
                         cwd=made, script=made / "install.sh")

        self.assertEqual(gone.returncode, 0, gone.stderr)
        self.assertFalse(made.exists(), "uninstalling left behind the directory the installer created")


if __name__ == "__main__":
    unittest.main(verbosity=2)
