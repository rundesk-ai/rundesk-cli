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
from unittest import mock

import support
from rundesk.commands import automatic_updates
from rundesk.core import config, paths
from rundesk.exits import FAILED, OK
from rundesk.lifecycle import tree
from rundesk.skills import catalogs, library

#: A launcher that cannot start, for proving an install refuses to report success it did not earn.
A_LAUNCHER_THAT_WILL_NOT_RUN = """#!/usr/bin/env python3
import sys
print("this program is broken", file=sys.stderr)
raise SystemExit(1)
"""


class TheBootstrapInstaller(support.Isolated):
    """The shell entry point parses every argument before it hands over to the product."""

    def setUp(self):
        super().setUp()
        self.checkout = self.home / "checkout"
        (self.checkout / "src" / "rundesk").mkdir(parents=True)
        shutil.copy2(support.CHECKOUT / "install.sh", self.checkout / "install.sh")
        self.state = self.home / "installed-state"
        self.state.mkdir()
        self.kept = {
            "files": "the installed program",
            "jobs": "the loaded launch job",
            "gateways": "the running gateway",
            "version": "0.46.0",
        }
        for name, value in self.kept.items():
            (self.state / name).write_text(value)
        (self.checkout / "rundesk").write_text(
            "#!/usr/bin/env python3\n"
            "import os\n"
            "import sys\n"
            "from pathlib import Path\n"
            "state = Path(os.environ['INSTALLER_TEST_STATE'])\n"
            "for name in ('files', 'jobs', 'gateways', 'version'):\n"
            "    (state / name).write_text('changed')\n"
            "print('\\n'.join(sys.argv[1:]))\n"
        )
        (self.checkout / "rundesk").chmod(0o755)
        self.bin = self.home / "bin"

    def installer(self, *argv):
        environment = os.environ.copy()
        environment["RUNDESK_BIN_DIR"] = str(self.bin)
        environment["INSTALLER_TEST_STATE"] = str(self.state)
        return subprocess.run(
            ["bash", str(self.checkout / "install.sh"), *argv],
            cwd=self.checkout, env=environment, stdin=subprocess.DEVNULL,
            capture_output=True, text=True, timeout=30,
        )

    def assert_state_was_not_changed(self):
        self.assertEqual(
            self.kept,
            {name: (self.state / name).read_text() for name in self.kept},
        )

    def test_help_prints_usage_and_changes_nothing(self):
        for option in ("--help", "-h"):
            with self.subTest(option=option):
                ended = self.installer(option)

                self.assertEqual(0, ended.returncode, ended.stderr)
                self.assertIn("Usage:", ended.stdout)
                self.assertIn("rundesk uninstall --confirm [--purge]", ended.stdout)
                self.assertEqual("", ended.stderr)
                self.assert_state_was_not_changed()

    def test_every_unsupported_argument_is_refused_with_usage_before_handoff(self):
        for argv in (("--unknown",), ("-x",), ("uninstall",), ("--help", "--unknown")):
            with self.subTest(argv=argv):
                ended = self.installer(*argv)

                self.assertEqual(2, ended.returncode)
                self.assertIn("unsupported", ended.stderr)
                self.assertIn("Usage:", ended.stderr)
                self.assertEqual("", ended.stdout)
                self.assert_state_was_not_changed()

    def test_no_argument_keeps_the_checkout_install_handoff_compatible(self):
        ended = self.installer()

        self.assertEqual(0, ended.returncode, ended.stderr)
        self.assertEqual(
            ["install", "--source", str(self.checkout), "--bin-dir", str(self.bin)],
            ended.stdout.splitlines(),
        )


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

    def test_a_fresh_install_has_the_catalog_this_release_ships(self):
        # The catalog stands at `src/skills`, and nothing enumerates it: `tree` copies `src/` whole
        # minus a blocklist, so it rides along by *not being excluded*. That is a guarantee held by
        # an omission, which is the kind that goes quietly wrong — so it is asserted from the far
        # end, on an install that really ran, rather than trusted.
        code, _out, err = self.install()
        self.assertEqual(OK, code, err)
        shipped = paths.app() / "src" / catalogs.SHIPPED_IN
        self.assertTrue((shipped / library.MANIFEST).is_file(),
                        f"{shipped} was not carried into the release")
        self.assertTrue((shipped / "managing-rundesk" / library.DECLARED).is_file())
        self.assertIn(library.BUNDLED, library.known())
        self.assertTrue(library.held(library.BUNDLED))

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

    def test_an_installed_launcher_selects_its_own_root_when_home_is_missing(self):
        self.install()
        fake_home = self.home / "default-home"
        environment = os.environ.copy()
        environment.pop(paths.HOME_IS, None)
        environment["HOME"] = str(fake_home)
        ended = subprocess.run([str(self.bin / "rundesk"), "status"],
                               capture_output=True, text=True, env=environment,
                               stdin=subprocess.DEVNULL, timeout=30)
        self.assertEqual(0, ended.returncode, ended.stderr)
        self.assertIn(str(self.root), ended.stdout)
        self.assertNotIn(str(fake_home / ".rundesk"), ended.stdout)

    def test_an_explicit_home_override_still_wins_over_the_launcher_root(self):
        self.install()
        override = self.home / "override"
        environment = os.environ.copy()
        environment[paths.HOME_IS] = str(override)
        ended = subprocess.run([str(self.bin / "rundesk"), "status"],
                               capture_output=True, text=True, env=environment,
                               stdin=subprocess.DEVNULL, timeout=30)
        self.assertEqual(0, ended.returncode, ended.stderr)
        self.assertIn(str(override), ended.stdout)
        self.assertNotIn(f"home        {self.root}", ended.stdout)

    def test_a_provider_turn_identity_keeps_a_rebuilt_shell_on_its_own_install(self):
        """A provider shell may restore live HOME and COMMAND, but not the turn's identity.

        The provider's command runtime is outside Rundesk's process. If it rebuilds those two
        variables from the owner's login environment, an agent in a scratch install must still
        reach its own command rather than silently operating on the live install.
        """
        self.install()
        agent_home = self.root / "data" / "agents" / "ava" / "home"
        agent_home.mkdir(parents=True)
        environment = os.environ.copy()
        environment[paths.HOME_IS] = str(Path.home() / ".rundesk")
        environment["RUNDESK_COMMAND"] = str(Path.home() / ".local" / "bin" / "rundesk")
        environment["RUNDESK_CWD"] = str(agent_home)
        environment["RUNDESK_AGENT"] = "ava"
        environment["RUNDESK_RUN"] = "1"
        ended = subprocess.run([str(self.bin / "rundesk"), "status"],
                               capture_output=True, text=True, env=environment,
                               stdin=subprocess.DEVNULL, timeout=30)
        self.assertEqual(0, ended.returncode, ended.stderr)
        self.assertIn(str(self.root), ended.stdout)
        self.assertNotIn(str(Path.home() / ".rundesk"), ended.stdout)

    def test_the_checkout_launcher_applies_the_same_turn_identity_guard(self):
        """The guard is needed before an installed command is copied to a scratch root too."""
        self.install()
        agent_home = self.root / "data" / "agents" / "ava" / "home"
        agent_home.mkdir(parents=True)
        environment = os.environ.copy()
        environment[paths.HOME_IS] = str(Path.home() / ".rundesk")
        environment["RUNDESK_COMMAND"] = str(Path.home() / ".local" / "bin" / "rundesk")
        environment["RUNDESK_CWD"] = str(agent_home)
        environment["RUNDESK_AGENT"] = "ava"
        environment["RUNDESK_RUN"] = "1"
        ended = subprocess.run([str(support.CHECKOUT / "rundesk"), "status"],
                               capture_output=True, text=True, env=environment,
                               stdin=subprocess.DEVNULL, timeout=30)
        self.assertEqual(0, ended.returncode, ended.stderr)
        self.assertIn(str(self.root), ended.stdout)
        self.assertNotIn(str(Path.home() / ".rundesk"), ended.stdout)

    def test_a_checkout_turn_without_an_installed_app_keeps_its_scratch_root(self):
        """A checkout runner still has an agent home to identify its scratch install by."""
        agent_home = self.root / "data" / "agents" / "ava" / "home"
        agent_home.mkdir(parents=True)
        environment = os.environ.copy()
        environment[paths.HOME_IS] = str(Path.home() / ".rundesk")
        environment["RUNDESK_COMMAND"] = str(Path.home() / ".local" / "bin" / "rundesk")
        environment["RUNDESK_CWD"] = str(agent_home)
        environment["RUNDESK_AGENT"] = "ava"
        environment["RUNDESK_RUN"] = "1"
        ended = subprocess.run([str(support.CHECKOUT / "rundesk"), "status"],
                               capture_output=True, text=True, env=environment,
                               stdin=subprocess.DEVNULL, timeout=30)
        self.assertEqual(0, ended.returncode, ended.stderr)
        self.assertIn(str(self.root), ended.stdout)
        self.assertNotIn(str(Path.home() / ".rundesk"), ended.stdout)

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

    def test_it_refuses_before_removing_the_program_if_a_queued_worker_will_not_stop(self):
        self.install()
        one = automatic_updates.coordinator()
        self.assertTrue(automatic_updates.shim_of(one).exists())
        with mock.patch.object(automatic_updates, "updates_stopped",
                               side_effect=automatic_updates.CouldNotStop("worker still active")):
            code, _, err = self.uninstall()

        self.assertEqual(FAILED, code)
        self.assertIn("queued update worker", err)
        self.assertTrue(paths.app().exists())
        self.assertTrue(automatic_updates.shim_of(one).exists())

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


class WhatLooksLikeARundeskTree(support.Isolated):
    """`tree.is_rundesk` — the one definition behind both questions that ask it.

    An install asks it of the directory it is copying *from*; an update asks it of what came out of a
    downloaded archive. One definition because if the marker ever changes, the call site nobody
    remembers is the one that goes on trusting a directory it should not.
    """

    def test_a_real_tree_is_one(self):
        self.assertTrue(tree.is_rundesk(support.a_real_tree(self.home / "a-tree")))

    def test_a_tree_with_no_launcher_is_not(self):
        at = support.a_real_tree(self.home / "a-tree")
        (at / "rundesk").unlink()
        self.assertFalse(tree.is_rundesk(at))

    def test_a_tree_with_no_source_is_not(self):
        at = support.a_real_tree(self.home / "a-tree")
        shutil.rmtree(at / "src")
        self.assertFalse(tree.is_rundesk(at))

    def test_a_launcher_that_is_a_directory_is_not_a_launcher(self):
        at = support.a_real_tree(self.home / "a-tree")
        (at / "rundesk").unlink()
        (at / "rundesk").mkdir()
        self.assertFalse(tree.is_rundesk(at))

    def test_somewhere_that_is_not_there_at_all_is_not(self):
        self.assertFalse(tree.is_rundesk(self.home / "never-made"))


class WhenAPurgeCannotFinish(Uninstalling):
    """A removal that did not happen must never report success — the rule this command exists for.

    Every purge case here succeeds, so the branch that turns a `data/` it could not remove into a
    failure had never run. Somebody believing their machine is clean when it is not is the whole
    damage this command is written to prevent.
    """

    def test_a_purge_that_could_not_take_the_data_is_reported_as_a_failure(self):
        if os.geteuid() == 0:
            self.skipTest("root may remove from a directory with no write permission")
        self.install()
        held = paths.data() / "held"
        held.mkdir(parents=True, exist_ok=True)
        (held / "a-file").write_text("the owner's")
        held.chmod(0o500)
        self.addCleanup(held.chmod, 0o700)

        code, out, err = self.uninstall("--confirm", "--purge")

        self.assertEqual(FAILED, code)
        self.assertNotIn("rundesk removed", out)
        self.assertIn("could not be removed", err)
        self.assertTrue(paths.data().exists(), "it said it failed and took the data anyway")


class WhenSettlingCannotEvenStart(Installing):
    """An install must not hand somebody a stack trace, whatever is in the way.

    Settling runs in an interpreter of its own, and whatever it writes to its error stream is the
    only account of what went wrong — so anything escaping it uncaught arrived verbatim, internal
    paths and all, on the line beginning `install: FAILED —`.
    """

    def test_a_file_where_a_directory_belongs_is_said_in_one_sentence(self):
        # An ordinary precondition: something left behind by an interrupted run, or a slip.
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "data").write_text("not a directory")

        code, _, err = self.install()

        self.assertEqual(FAILED, code)
        self.assertNotIn("Traceback", err)
        self.assertNotIn("NOT APPLIED", err, "the subprocess's own prefix was forwarded whole")
        self.assertIn("File exists", err)
        # A worded failure, not an exception's repr. Reducing a traceback to its last line hides
        # the stack but still leaves `FileExistsError:` in front of the message — which is how you
        # tell "settle caught this and said it" from "settle let it out and something tidied up
        # after the fact".
        self.assertNotIn("FileExistsError", err)

    def test_a_failure_is_reported_once_and_not_under_two_names(self):
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "data").write_text("not a directory")
        code, _, err = self.install()
        self.assertEqual(FAILED, code)
        self.assertEqual(1, err.count("FAILED"), f"said more than once: {err!r}")


class WhenASwapCannotBeUndone(support.Isolated):
    """`tree.HalfReplaced` — the worst thing this product can say, and nothing proved it said it.

    Its own exception because there is no clever recovery left: the install is neither the release
    it was nor the one it was becoming. Both `install` and `update` carry a branch for it, and
    until now nothing ever drove one.
    """

    def test_a_swap_that_cannot_be_put_back_says_the_install_must_be_made_again(self):
        app = self.home / "app"
        support.a_real_tree(app, "before")
        fresh = support.a_real_tree(self.home / "fresh", "after")
        really = os.rename

        def never_puts_anything_back(src, dst):
            # Fails the swap, and then fails the undo as well — the only route to `HalfReplaced`.
            if str(src).endswith(".incoming") or ".outgoing" in str(src):
                raise OSError("the filesystem went away")
            return really(src, dst)

        with mock.patch.object(tree.os, "rename", side_effect=never_puts_anything_back):
            with self.assertRaises(tree.HalfReplaced) as half:
                tree.replace(fresh, app)

        self.assertIn("must be installed again", str(half.exception))

    def test_an_install_that_half_replaced_the_tree_reports_it_rather_than_crashing(self):
        # The command layer's own branch for it, which was equally unproven.
        source = support.a_real_tree(self.home / "source", "after")
        with mock.patch.object(tree, "place",
                               side_effect=tree.HalfReplaced("it is part-replaced")):
            code, _, err = support.run_with(["install", "--source", str(source),
                                             "--bin-dir", str(self.home / "bin")])
        self.assertEqual(FAILED, code)
        self.assertIn("part-replaced", err)


class WhereTheCommandGoesWhenNobodySays(support.Isolated):
    """`tree._a_bin_dir` — what a real `curl | bash` install uses, and what no test ever ran.

    Every case here passes `--bin-dir`, because `AGENTS.md` requires it: an install with none
    writes into a real directory on somebody's PATH. That safety rule is exactly why the code
    deciding *which* real directory had never been exercised.
    """

    def test_it_takes_the_first_one_it_can_write_to(self):
        first, second = self.home / "first", self.home / "second"
        first.mkdir()
        second.mkdir()
        with mock.patch.object(tree, "BIN_DIRS", (str(first), str(second))):
            self.assertEqual(first, tree._a_bin_dir())

    def test_it_passes_over_one_it_cannot_write_to(self):
        if os.geteuid() == 0:
            self.skipTest("root may write to a directory with no write permission")
        first, second = self.home / "first", self.home / "second"
        first.mkdir(mode=0o500)
        self.addCleanup(first.chmod, 0o700)
        second.mkdir()
        with mock.patch.object(tree, "BIN_DIRS", (str(first), str(second))):
            self.assertEqual(second, tree._a_bin_dir())

    def test_it_passes_over_one_that_is_not_there(self):
        second = self.home / "second"
        second.mkdir()
        with mock.patch.object(tree, "BIN_DIRS", (str(self.home / "never-made"), str(second))):
            self.assertEqual(second, tree._a_bin_dir())

    def test_with_nowhere_writable_it_names_the_last_rather_than_nothing(self):
        # A path that does not exist yet is still an answer — `link` makes the directory. Returning
        # nothing here would make the installer fail where it could have succeeded.
        one, two = self.home / "one", self.home / "two"
        with mock.patch.object(tree, "BIN_DIRS", (str(one), str(two))):
            self.assertEqual(two, tree._a_bin_dir())


if __name__ == "__main__":
    unittest.main()
