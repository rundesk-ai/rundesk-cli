#!/usr/bin/env python3
"""What this install is made of, and putting it there.

Offline throughout, and **pip never runs**: `provision` takes the thing that runs a program
as an argument, so what is proved here is which decision was reached and what was left on
disk when it was — not that a package index was reachable on the day the suite ran.

Run: python3 tests/test_dependencies.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from rundesk import dependencies  # noqa: E402


class WithAnInstallOfItsOwn(unittest.TestCase):
    """Each case gets an install directory nothing else is looking at."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="rundesk-deps-"))
        self.addCleanup(shutil.rmtree, self.root, True)

    def needs(self, *lines: str) -> Path:
        """What this install declares. Never the real file: installing that would reach a
        network and take a minute, in a suite that must do neither."""
        at = self.root / "requirements.txt"
        at.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return at

    def holding(self, *installed: tuple) -> Path:
        """A virtualenv holding exactly these, written the way pip leaves them.

        Built by hand rather than by pip, which is the whole point: the shape on disk is
        what `installed` reads, so a case can put any version there in no time at all.
        """
        where = (self.root / ".venv" / "lib"
                 / f"python3.{sys.version_info.minor}" / "site-packages")
        where.mkdir(parents=True, exist_ok=True)
        for name, version in installed:
            info = where / f"{name}-{version}.dist-info"
            info.mkdir(exist_ok=True)
            (info / "METADATA").write_text(f"Name: {name}\nVersion: {version}\n",
                                           encoding="utf-8")
        return where


class WhatIsDeclaredTests(WithAnInstallOfItsOwn):
    def test_what_an_install_declares_is_read_with_its_version(self):
        self.needs("discord.py==2.7.1")
        one, = dependencies.declared(self.root)
        self.assertEqual("discord.py", one.name)
        self.assertEqual("==", one.how)
        self.assertEqual("2.7.1", one.wanted)

    def test_a_name_is_read_as_what_it_is_imported_under(self):
        # `discord.py` installs as `discord`, and a check that looked for the declared
        # spelling would report a working install as missing what it needs.
        self.needs("discord.py==2.7.1", "some-package==1.0")
        named = [one.imported for one in dependencies.declared(self.root)]
        self.assertEqual(["discord", "some_package"], named)

    def test_comments_and_blank_lines_are_not_requirements(self):
        self.needs("# what rundesk needs", "", "  ", "discord.py==2.7.1  # pinned")
        self.assertEqual(1, len(dependencies.declared(self.root)))

    def test_a_line_with_no_version_at_all_is_a_requirement_that_fits_anything(self):
        self.needs("discord.py")
        one, = dependencies.declared(self.root)
        self.assertIsNone(one.how)
        self.assertIsNone(one.why, "a line naming no version is not one that cannot be read")

    def test_nothing_declared_means_nothing_is_needed(self):
        # No requirements means no virtualenv is made at all (R-INS-3), so an absent file
        # is an ordinary state and never an error.
        self.assertEqual([], dependencies.declared(self.root))


class WhatCannotBeJudgedTests(WithAnInstallOfItsOwn):
    """R-GW-42 — a narrow answer with an honest refusal beats a broad guess.

    Satisfying a full specifier is PEP 440's problem, not this one. What matters is that
    what cannot be judged is *said*, because a requirement reported as fitting on the
    strength of a line nobody read is the same failure as not looking at all.
    """

    def test_a_comparison_this_does_not_understand_is_refused_rather_than_guessed_at(self):
        for line in ("discord.py~=2.7.1", "discord.py>2.0,<3.0", "discord.py!=2.0.0"):
            with self.subTest(line=line):
                self.needs(line)
                one, = dependencies.declared(self.root)
                self.assertIsNone(one.how, f"{line} was read as a comparison it is not")
                self.assertTrue(one.why, f"{line} was refused without saying why")

    def test_a_version_that_is_not_a_plain_release_is_refused_rather_than_compared(self):
        for line in ("discord.py==2.7.1rc1", "discord.py==2.*", "discord.py==2.7.1+local"):
            with self.subTest(line=line):
                self.needs(line)
                one, = dependencies.declared(self.root)
                self.assertIsNone(one.how)
                self.assertTrue(one.why)

    def test_a_requirement_that_cannot_be_checked_is_reported_and_never_passed_over(self):
        self.needs("discord.py~=2.7.1")
        self.holding(("discord.py", "2.7.1"))
        short = dependencies.unsatisfied(self.root)
        self.assertEqual(1, len(short), "a line nobody could read was called satisfied")
        self.assertIn("cannot be checked", short[0])


class WhatIsInstalledTests(WithAnInstallOfItsOwn):
    def test_what_is_installed_is_read_without_importing_any_of_it(self):
        self.holding(("discord.py", "2.7.1"))
        self.assertEqual({"discord-py": "2.7.1"}, dependencies.installed(self.root))

    def test_a_name_pip_spells_differently_is_still_the_same_name(self):
        # pip writes `discord_py-2.7.1.dist-info` for a package declared `discord.py`.
        self.holding(("discord_py", "2.7.1"))
        self.needs("discord.py==2.7.1")
        self.assertEqual([], dependencies.unsatisfied(self.root))

    def test_an_install_with_no_virtualenv_holds_nothing(self):
        self.assertEqual({}, dependencies.installed(self.root))
        self.assertIsNone(dependencies.site_packages(self.root))


class WhatDoesNotFitTests(WithAnInstallOfItsOwn):
    def test_the_version_that_was_declared_fits(self):
        self.needs("discord.py==2.7.1")
        self.holding(("discord.py", "2.7.1"))
        self.assertEqual([], dependencies.unsatisfied(self.root))

    def test_an_install_whose_virtualenv_no_longer_satisfies_what_is_declared_says_which(self):
        """R-GW-41 — the failure nothing used to catch. Asking only whether the name loads
        made 2.0.0 a perfect fit for a release that declares 2.7.1, so the new code ran
        against the old dependency and failed wherever the difference bit."""
        self.needs("discord.py==2.7.1")
        self.holding(("discord.py", "2.0.0"))
        short = dependencies.unsatisfied(self.root)
        self.assertEqual(1, len(short))
        self.assertIn("2.7.1", short[0], "it never said what was wanted")
        self.assertIn("2.0.0", short[0], "it never said what is there")

    def test_at_least_this_version_is_met_by_a_newer_one(self):
        self.needs("discord.py>=2.0.0")
        self.holding(("discord.py", "2.7.1"))
        self.assertEqual([], dependencies.unsatisfied(self.root))

    def test_at_least_this_version_is_not_met_by_an_older_one(self):
        self.needs("discord.py>=2.7.1")
        self.holding(("discord.py", "2.0.0"))
        self.assertEqual(1, len(dependencies.unsatisfied(self.root)))

    def test_a_version_is_compared_by_number_and_not_by_text(self):
        # "2.10.0" sorts before "2.9.0" as text and is after it as a version.
        self.needs("discord.py>=2.9.0")
        self.holding(("discord.py", "2.10.0"))
        self.assertEqual([], dependencies.unsatisfied(self.root))

    def test_a_version_written_shorter_is_the_same_version(self):
        self.needs("discord.py==2.7")
        self.holding(("discord.py", "2.7.0"))
        self.assertEqual([], dependencies.unsatisfied(self.root))

    def test_something_declared_and_never_installed_does_not_fit(self):
        self.needs("discord.py==2.7.1")
        self.holding(("something-else", "1.0.0"))
        short = dependencies.unsatisfied(self.root)
        self.assertEqual(1, len(short))
        self.assertIn("not installed", short[0])

    def test_nothing_declared_never_fails_to_fit(self):
        self.holding(("left-over", "1.0.0"))
        self.assertEqual([], dependencies.unsatisfied(self.root))


class Provisioning(WithAnInstallOfItsOwn):
    """Building the virtualenv, with the thing that runs a program passed in.

    The stand-in does exactly what the real one would leave behind and no more: a
    virtualenv directory and the `.dist-info` pip would write. A fake more generous than
    the real thing hides whole features, which this codebase has paid for twice.
    """

    def runner(self, lands=(), fails_at=None, why="it went wrong"):
        self.ran = []

        def run(command):
            self.ran.append(command)
            if fails_at and fails_at in " ".join(command):
                return why
            if command[1:3] == ["-m", "venv"]:
                self.holding(*lands)
            return None

        return run

    def test_what_an_install_needs_is_installed_and_then_checked(self):
        """R-UPD-27 — installed is not the same as usable, and the installer has said so
        since it was written. An update that skipped the check would leave a set of
        packages that cannot satisfy each other, found hours later inside a provider."""
        self.needs("discord.py==2.7.1")
        why = dependencies.provision(self.root, run=self.runner(lands=[("discord.py", "2.7.1")]))
        self.assertIsNone(why)
        did = [" ".join(one[1:]) for one in self.ran]
        self.assertIn("-m venv " + str(self.root / ".venv"), did)
        self.assertTrue(any("pip install" in one for one in did), "it installed nothing")
        installs = [one for one in did if "pip install" in one]
        self.assertTrue(
            all("-B -m pip" in one and "--no-cache-dir" in one and "--no-compile" in one
                for one in installs),
            "dependency installation writes a cache outside Rundesk's install")
        self.assertTrue(any("pip check" in one for one in did),
                        "it never asked whether what it installed fits together")

    def test_python_and_pip_scratch_stays_out_of_the_owners_home(self):
        seen = {}
        real = dependencies.subprocess.run

        def run(command, **options):
            seen.update(options["env"])
            return subprocess.CompletedProcess(command, 0, "", "")

        dependencies.subprocess.run = run
        self.addCleanup(setattr, dependencies.subprocess, "run", real)
        self.assertIsNone(dependencies._run(["python3", "-m", "pip", "--version"]))
        self.assertEqual("1", seen["PIP_NO_CACHE_DIR"])
        self.assertNotEqual(str(Path.home()), seen["PYTHONPYCACHEPREFIX"])

    def test_what_was_working_is_put_back_when_the_build_fails(self):
        """R-UPD-28 — the files have already landed by the time this runs, so a virtualenv
        left half built is an install with neither the old dependencies nor the new."""
        self.needs("discord.py==2.7.1")
        self.holding(("discord.py", "2.0.0"))
        was_there = dependencies.installed(self.root)

        why = dependencies.provision(
            self.root, run=self.runner(fails_at="pip install", why="no network"))
        self.assertIsNotNone(why)
        self.assertIn("no network", why)
        self.assertEqual(was_there, dependencies.installed(self.root),
                         "a failed build left the install without what it had")
        self.assertFalse((self.root / ".venv.outgoing").exists(),
                         "a failed build left its staging behind")

    def test_a_set_that_cannot_satisfy_itself_is_a_build_that_failed(self):
        self.needs("discord.py==2.7.1")
        why = dependencies.provision(
            self.root,
            run=self.runner(lands=[("discord.py", "2.7.1")], fails_at="pip check",
                            why="aiohttp 3.0 has requirement yarl<2"))
        self.assertIsNotNone(why)
        self.assertIn("do not fit together", why)

    def test_what_pip_reported_is_checked_against_what_actually_landed(self):
        # pip reporting success and the directory saying another version is exactly the
        # difference this exists to catch, so its word is not taken for it.
        self.needs("discord.py==2.7.1")
        why = dependencies.provision(self.root, run=self.runner(lands=[("discord.py", "2.0.0")]))
        self.assertIsNotNone(why, "pip said it worked and nothing looked")
        self.assertIn("not what is declared", why)

    def test_nothing_declared_makes_no_virtualenv_at_all(self):
        """R-INS-3 — no requirements means no virtualenv, which is the state to return to
        if a dependency ever stops earning its place."""
        self.needs("# nothing needed")
        self.assertIsNone(dependencies.provision(self.root, run=self.runner()))
        self.assertEqual([], self.ran, "it built a virtualenv for nothing")
        self.assertFalse((self.root / ".venv").exists())

    def test_a_release_that_stops_needing_something_leaves_it_behind_no_longer(self):
        # A dependency removed from requirements.txt used to stay in the virtualenv for
        # ever, and only removing rundesk cleared it.
        self.holding(("discord.py", "2.7.1"))
        self.needs("# nothing needed any more")
        self.assertIsNone(dependencies.provision(self.root, run=self.runner()))
        self.assertFalse((self.root / ".venv").exists(),
                         "an install went on carrying what no version of it asks for")

    def test_a_virtualenv_an_interrupted_attempt_set_aside_is_what_gets_put_back(self):
        """R-UPD-28 — `pip install` can run for minutes, which is a wide window to be
        killed in, and being killed there leaves `.venv` gone and `.venv.outgoing` holding
        the last one that worked. Running the update again is the documented way out, so
        the retry must not begin by destroying it: one that also fails would then have
        nothing to put back, and the install would end with no virtualenv at all — the
        release reverted underneath it and every gateway refusing to start.
        """
        self.needs("discord.py==2.7.1")
        # What a killed attempt leaves: nothing at `.venv`, the good one set aside.
        aside = self.root / ".venv.outgoing" / "lib" / f"python3.{sys.version_info.minor}"
        (aside / "site-packages").mkdir(parents=True)
        (aside / "site-packages" / "discord.py-2.7.1.dist-info").mkdir()

        why = dependencies.provision(
            self.root, run=self.runner(fails_at="pip install", why="no network"))

        self.assertIsNotNone(why)
        self.assertEqual({"discord-py": "2.7.1"}, dependencies.installed(self.root),
                         "a retry that failed destroyed the last virtualenv that worked")
        self.assertFalse((self.root / ".venv.outgoing").exists(),
                         "the copy was put back and something was still left aside")

    def test_a_build_that_worked_lets_go_of_what_it_replaced(self):
        self.needs("discord.py==2.7.1")
        self.holding(("discord.py", "2.0.0"))
        self.assertIsNone(
            dependencies.provision(self.root, run=self.runner(lands=[("discord.py", "2.7.1")])))
        self.assertFalse((self.root / ".venv.outgoing").exists(),
                         "a finished build kept the virtualenv it replaced")
        self.assertEqual({"discord-py": "2.7.1"}, dependencies.installed(self.root))


if __name__ == "__main__":
    unittest.main(verbosity=2)
