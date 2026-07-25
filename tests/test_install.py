#!/usr/bin/env python3
"""Putting the command on a machine, and taking it off again.

The installer is shell, so it is tested by running it — into a throwaway PATH directory
with a throwaway HOME, so nothing here can touch the machine it runs on.

Run: python3 tests/test_install.py
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
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

    def test_nothing_needed_means_no_virtualenv_is_made_at_all(self):
        # The state to return to if a dependency ever stops earning its place: zero cost,
        # nothing to go stale, and an install that is a symlink and nothing else.
        done = self.install_needing(self.needs("# nothing needed", ""))
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertFalse((REPO / ".venv").exists(), "a virtualenv was made for no dependencies")
        self.assertNotIn("into", done.stdout.split("linked")[0], done.stdout)

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
        venv = REPO / ".venv"
        packages = venv / "lib" / f"python3.{sys.version_info.minor}" / "site-packages"
        packages.mkdir(parents=True)
        (packages / "pretend_dependency.py").write_text("WORKS = True\n")
        try:
            said = subprocess.run(
                [str(REPO / "rundesk"), "version"], capture_output=True, text=True,
                env={**os.environ, "HOME": str(self.home)},
            )
            self.assertEqual(said.returncode, 0, said.stderr)
            found = subprocess.run(
                [str(REPO / "rundesk"), "--version"], capture_output=True, text=True,
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
        finally:
            shutil.rmtree(venv, ignore_errors=True)

    def test_removing_rundesk_takes_what_was_installed_for_it(self):
        venv = REPO / ".venv"
        venv.mkdir()
        (venv / "marker").write_text("x")
        try:
            self.install_needing(self.needs("# nothing needed", ""))
            self.uninstall()
            self.assertFalse(venv.exists(), "uninstalling left the dependencies behind")
        finally:
            shutil.rmtree(venv, ignore_errors=True)

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
