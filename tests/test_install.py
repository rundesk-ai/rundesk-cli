"""Putting rundesk on a machine, and taking it off again.

Every case installs into a scratch root and links into a scratch bin directory, so nothing here can
reach the owner's own install or their PATH. The tree installed *from* is a small fake rather than
the checkout, because install hands off to the program it places — a stub launcher could not settle
an install, so every case that touches settling would pass without the handoff ever happening.

Run directly: `python3 tests/test_install.py`
"""

import os
import shutil
import subprocess
import unittest
from pathlib import Path

import support
from rundesk.core import config, paths
from rundesk.exits import FAILED, OK
from rundesk.lifecycle import tree

#: A launcher that cannot start, for proving an install refuses to report success it did not earn.
A_LAUNCHER_THAT_WILL_NOT_RUN = """#!/usr/bin/env python3
import sys
print("this program is broken", file=sys.stderr)
raise SystemExit(1)
"""


class Installing(support.Isolated):
    """A scratch tree to install from, and a scratch place to put the command."""

    def setUp(self):
        super().setUp()
        # The install gets a root of its own *below* the scratch root, so the tree it is installed
        # from and the bin directory it links into are not sitting inside the thing under test —
        # otherwise "the root is empty now" can never be true and the case proves nothing.
        self.root = self.home / "install"
        os.environ[paths.HOME_IS] = str(self.root)
        self.source = self.home / "source"
        self.bin = self.home / "bin"
        self.bin.mkdir(parents=True, exist_ok=True)
        self.given_a_tree(self.source)
        self.assertEqual(self.root, paths.home())

    def given_a_tree(self, at: Path, launcher: str = "", marker: str = "first") -> Path:
        """A real copy of the program — install hands off to what it places, so a stub cannot run."""
        support.a_real_tree(at, marker)
        if launcher:
            (at / "rundesk").write_text(launcher)
            (at / "rundesk").chmod(0o755)
        return at

    def install(self, **also):
        argv = ["install", "--source", str(self.source), "--bin-dir", str(self.bin)]
        for key, value in also.items():
            argv += [f"--{key.replace('_', '-')}", str(value)]
        return support.run(argv)


class AFreshInstall(Installing):

    def test_it_places_the_program_and_says_where(self):
        code, out, err = self.install()
        self.assertEqual(OK, code, err)
        self.assertTrue((paths.app() / "rundesk").is_file())
        self.assertIn(str(paths.app()), out)

    def test_it_makes_every_directory_an_install_keeps_things_in(self):
        self.install()
        for made in (paths.data(), paths.backups(), paths.projects()):
            self.assertTrue(made.is_dir(), f"{made} was not made")

    def test_it_puts_the_command_on_a_path(self):
        self.install()
        at = self.bin / "rundesk"
        self.assertTrue(at.is_symlink())
        self.assertEqual((paths.app() / "rundesk").resolve(), Path(os.readlink(at)).resolve())

    def test_it_writes_the_configuration_complete(self):
        self.install()
        settled = config.read(paths.data())
        self.assertEqual(set(config.INITIAL), set(settled))

    def test_it_stamps_the_migrations_without_running_them(self):
        # A fresh install has nothing to carry: the directories were made correctly a moment ago.
        from rundesk.lifecycle import migration
        self.install()
        self.assertEqual(migration.newest(), config.read(paths.data())["migration"])

    def test_it_records_when_the_version_arrived(self):
        self.install()
        self.assertRegex(config.read(paths.data())["last_updated_at"],
                         r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

    def test_installing_again_records_the_new_arrival(self):
        # An install really does place a program, so it really is a moment a version arrived.
        self.install()
        config.stated("last_updated_at", "1999-12-31T23:59:59Z", paths.data())
        self.install()
        self.assertNotEqual("1999-12-31T23:59:59Z", config.read(paths.data())["last_updated_at"])

    def test_a_program_that_will_not_run_is_never_reported_as_installed(self):
        # An installer that reports success without checking has told somebody their machine is
        # ready when it is not, and they find out later and somewhere else.
        self.given_a_tree(self.source, launcher=A_LAUNCHER_THAT_WILL_NOT_RUN)
        code, out, err = self.install()
        self.assertEqual(FAILED, code)
        self.assertIn("install: FAILED", err)
        self.assertNotIn("installed", out)

    def test_the_command_it_put_on_the_path_really_answers(self):
        # The link is the last thing that can be wrong and the first thing a person uses: a bad
        # target or a missing executable bit shows up here and nowhere earlier.
        #
        # `status` rather than `version`, for the same reason the installer proves itself with it:
        # `version` asks GitHub, and nothing in this file may leave the machine.
        self.install()
        ended = subprocess.run([str(self.bin / "rundesk"), "status"],
                               capture_output=True, text=True, stdin=subprocess.DEVNULL,
                               timeout=30)
        self.assertEqual(0, ended.returncode, ended.stderr)
        self.assertIn(str(self.root), ended.stdout)

    def test_proving_the_install_never_asks_what_is_published(self):
        # The installer proves the command it placed really answers. Which verb it proves with is
        # not a detail: `version` asks GitHub, so an installer proved with it turns every install —
        # and every case in this file — into a network call, and stalls on a network that is slow.
        #
        # The tree being installed from is booby-trapped rather than the check being inspected: if
        # the installed command consults what is published, it raises, and the install fails.
        asked = self.source / "src" / "rundesk" / "lifecycle" / "release.py"
        asked.write_text(asked.read_text() + (
            "\n\ndef latest_published():\n"
            "    raise AssertionError('proving the install asked what is published')\n"))
        code, _, err = self.install()
        self.assertEqual(OK, code, err)

    def test_it_refuses_a_root_that_must_not_be_one_before_writing_anything(self):
        os.environ["RUNDESK_HOME"] = str(Path.home())
        code, _, err = self.install()
        self.assertEqual(FAILED, code)
        self.assertIn("home directory", err)

    def test_it_refuses_a_source_that_is_not_rundesk(self):
        empty = self.home / "not-rundesk"
        empty.mkdir()
        code, _, err = support.run(
            ["install", "--source", str(empty), "--bin-dir", str(self.bin)])
        self.assertEqual(FAILED, code)
        self.assertIn("does not look like rundesk", err)
        self.assertFalse(paths.app().exists(), "a refused install left a program behind")


class InstallingOverAnInstall(Installing):

    def test_it_replaces_the_program(self):
        self.install()
        self.given_a_tree(self.source, marker="second")
        code, _, err = self.install()
        self.assertEqual(OK, code, err)
        self.assertEqual("second", (paths.app() / "README.md").read_text())

    def test_it_leaves_what_the_owner_stated(self):
        self.install()
        config.stated("update_enabled", False, paths.data())
        self.install()
        self.assertFalse(config.read(paths.data())["update_enabled"])

    def test_it_leaves_what_the_owner_keeps(self):
        self.install()
        theirs = paths.data() / "something-of-theirs"
        theirs.write_text("mine")
        self.install()
        self.assertEqual("mine", theirs.read_text())

    def test_it_takes_away_what_the_new_release_no_longer_ships(self):
        self.install()
        stale = paths.app() / "README.md"
        self.assertTrue(stale.exists())
        # A tree whose entries differ: what the new one ships replaces what is there by name.
        self.given_a_tree(self.source, marker="second")
        self.install()
        self.assertEqual("second", stale.read_text())

    def test_a_second_install_does_not_leave_staging_entries_behind(self):
        self.install()
        self.install()
        leftovers = [at.name for at in paths.app().iterdir()
                     if at.name.startswith(".") and
                     (at.name.endswith(".incoming") or at.name.endswith(".outgoing"))]
        self.assertEqual([], leftovers)


class PuttingTheCommandOnAPath(Installing):

    def test_it_refuses_to_write_over_a_command_belonging_to_something_else(self):
        theirs = self.bin / "rundesk"
        theirs.write_text("#!/bin/sh\necho not ours\n")
        theirs.chmod(0o755)
        code, _, err = self.install()
        self.assertEqual(FAILED, code)
        self.assertIn("will not write over it", err)
        self.assertEqual("#!/bin/sh\necho not ours\n", theirs.read_text())

    def test_it_refuses_a_link_pointing_at_another_program(self):
        elsewhere = self.home / "someone-elses-rundesk"
        elsewhere.write_text("#!/bin/sh\n")
        (self.bin / "rundesk").symlink_to(elsewhere)
        code, _, err = self.install()
        self.assertEqual(FAILED, code)
        self.assertIn("not this install", err)

    def test_it_replaces_its_own_link_without_complaining(self):
        self.install()
        code, _, err = self.install()
        self.assertEqual(OK, code, err)


class Uninstalling(Installing):

    def uninstall(self, *argv):
        """Removal driven exactly as a person runs it — **nothing is redirected**.

        This deliberately does not point `tree.BIN_DIRS` at the scratch directory. Doing so was
        hiding a real defect: the install links into whatever `--bin-dir` names, uninstall only knew
        the two usual places, and a real removal left a dangling link behind while reporting an
        ordinary success. Patching the search path made every case here agree with the bug.

        It is safe to leave alone because `tree.unlink` only removes a link that resolves into
        *this* install's own `app/`, and this install is under a temporary root.
        """
        return support.run(["uninstall", "--confirm", *argv])

    def unconfirmed(self, *argv):
        return support.run(["uninstall", *argv])

    def test_without_confirming_nothing_is_removed(self):
        self.install()
        code, _, err = self.unconfirmed()
        self.assertEqual(FAILED, code)
        self.assertTrue(paths.app().exists(), "an unconfirmed removal took the program")
        self.assertTrue((self.bin / "rundesk").is_symlink(), "an unconfirmed removal took the link")
        self.assertIn("nothing was removed", err)

    def test_without_confirming_it_says_what_it_would_take_and_what_it_would_keep(self):
        self.install()
        _, _, err = self.unconfirmed()
        self.assertIn(str(paths.app()), err)
        self.assertIn(str(paths.data()), err)
        self.assertIn(str(paths.backups()), err)
        self.assertIn("--confirm", err)

    def test_without_confirming_a_purge_says_the_data_would_go(self):
        self.install()
        _, _, plain = self.unconfirmed()
        _, _, purging = self.unconfirmed("--purge")
        self.assertIn("keep   " + str(paths.data()), plain)
        self.assertIn("everything rundesk kept", purging)
        self.assertIn("--confirm --purge", purging)

    def test_purge_without_confirming_still_removes_nothing(self):
        self.install()
        theirs = paths.data() / "something-of-theirs"
        theirs.write_text("mine")
        self.unconfirmed("--purge")
        self.assertTrue(theirs.exists(), "an unconfirmed purge took the owner's data")

    def test_it_leaves_no_command_behind(self):
        self.install()
        code, _, err = self.uninstall()
        self.assertEqual(OK, code, err)
        self.assertFalse((self.bin / "rundesk").is_symlink())

    def test_it_takes_the_program(self):
        self.install()
        self.uninstall()
        self.assertFalse(paths.app().exists())

    def test_it_keeps_what_the_owner_keeps_unless_asked_to_take_it(self):
        self.install()
        theirs = paths.data() / "something-of-theirs"
        theirs.write_text("mine")
        self.uninstall()
        self.assertTrue(theirs.exists(), "an ordinary removal took the owner's data")

    def test_a_purge_takes_the_data(self):
        self.install()
        (paths.data() / "something-of-theirs").write_text("mine")
        code, _, err = self.uninstall("--purge")
        self.assertEqual(OK, code, err)
        self.assertFalse(paths.data().exists())

    def test_copies_survive_removal_including_a_purge(self):
        # Not "not by default" — there is no argument to this command that reaches them.
        self.install()
        kept = paths.backups() / "a-copy"
        kept.write_text("a copy of what was kept")
        self.uninstall("--purge")
        self.assertTrue(kept.exists(), "a purge took the backups")
        self.assertEqual("a copy of what was kept", kept.read_text())

    def test_it_leaves_a_command_of_the_same_name_belonging_to_something_else(self):
        self.install()
        (self.bin / "rundesk").unlink()
        theirs = self.bin / "rundesk"
        theirs.write_text("#!/bin/sh\necho not ours\n")
        self.uninstall()
        self.assertTrue(theirs.exists(), "the uninstall took somebody else's command")

    def test_it_leaves_another_installs_link_alone(self):
        self.install()
        other = self.home / "other-app"
        other.mkdir()
        (other / "rundesk").write_text("#!/bin/sh\n")
        second = self.home / "bin2"
        second.mkdir()
        (second / "rundesk").symlink_to(other / "rundesk")
        was = tree.BIN_DIRS
        tree.BIN_DIRS = (str(second),)
        try:
            support.run(["uninstall", "--confirm"])
        finally:
            tree.BIN_DIRS = was
        self.assertTrue((second / "rundesk").is_symlink(), "another install's command was removed")

    def test_it_removes_the_link_wherever_the_install_put_it(self):
        # The defect this catches: the install links into whatever --bin-dir names, and a removal
        # that only knew the usual places left the link dangling and said it had removed everything.
        self.install()
        at = self.bin / "rundesk"
        self.assertTrue(at.is_symlink())
        self.uninstall()
        self.assertFalse(at.is_symlink(), f"{at} was left behind, dangling")
        self.assertFalse(at.exists())

    def test_where_the_command_went_is_written_down_by_the_install(self):
        self.install()
        self.assertEqual(str(self.bin / "rundesk"),
                         config.read(paths.data())["command_link"])

    def test_removing_something_never_installed_says_so_rather_than_failing(self):
        code, out, _ = self.uninstall()
        self.assertEqual(OK, code)
        self.assertIn("not installed", out)

    def test_it_refuses_to_delete_somebody_elses_checkout(self):
        self.install()
        (paths.app() / ".git").mkdir()
        code, _, err = self.uninstall()
        self.assertEqual(FAILED, code)
        self.assertIn("own work", err)
        self.assertTrue(paths.app().exists())

    def test_a_removal_that_did_not_happen_is_reported_as_a_failure(self):
        self.install()
        (paths.app() / ".git").mkdir()
        code, out, _ = self.uninstall()
        self.assertNotEqual(OK, code)
        self.assertNotIn("rundesk removed", out)

    def test_it_says_what_it_took_and_what_it_kept(self):
        self.install()
        _, out, _ = self.uninstall()
        self.assertIn("took", out)
        self.assertIn("kept", out)

    def test_a_purge_leaves_the_root_standing_over_what_it_may_not_take(self):
        # Backups survive every removal, and `projects/` holds the owner's own checkouts. So the
        # root remains after a purge — it is holding two things rundesk is not allowed to delete.
        self.install()
        self.uninstall("--purge")
        self.assertTrue(self.root.exists())
        self.assertFalse(paths.data().exists())
        self.assertTrue(paths.backups().exists())
        self.assertTrue(paths.projects().exists())

    def test_the_root_is_tidied_away_when_genuinely_nothing_is_left_in_it(self):
        self.install()
        shutil.rmtree(paths.backups())
        shutil.rmtree(paths.projects())
        self.uninstall("--purge")
        self.assertFalse(self.root.exists(), "the root was left standing over nothing")

    def test_an_ordinary_removal_leaves_the_root_holding_the_data(self):
        self.install()
        self.uninstall()
        self.assertTrue(self.root.exists())
        self.assertTrue(paths.data().exists())


if __name__ == "__main__":
    unittest.main()
