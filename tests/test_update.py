"""Moving an install to a newer release, and what happens when that goes wrong.

Nothing here reaches the network. What is published arrives as `asking=` and the download arrives as
`fetching=`, both handed to `cli.main`, so every state — behind, current, unable to ask, a broken
archive, a failed swap — is driven against real files on disk with no GitHub anywhere near it.

Run directly: `python3 tests/test_update.py`
"""

import io
import os
import tarfile
import unittest
from pathlib import Path

import support
from rundesk import __version__
from rundesk.core import config, paths
from rundesk.exits import FAILED, OK
from rundesk.lifecycle import migration, release, tree

A_STEP = '''
from pathlib import Path

def carry(data):
    (Path(data) / "carried").write_text("the step ran")
'''



class Updating(support.Isolated):
    """An install already on disk, and an archive to move it to."""

    def setUp(self):
        super().setUp()
        self.root = self.home / "install"
        os.environ[paths.HOME_IS] = str(self.root)
        self.made_an_install()
        self.asked = []

    def made_an_install(self, marker: str = "before") -> None:
        """An install of the *real* product, because the update hands off to what it replaces it with.

        A fake tree cannot be used here: once the files are swapped, the release that landed is what
        settles the install, and a stub launcher cannot run migrations. So both the install and the
        release it moves to are copies of this checkout — which is also the only way this suite
        proves the handoff actually happens.
        """
        support.a_real_tree(paths.app(), marker)
        paths.data().mkdir(parents=True, exist_ok=True)
        config.write_fresh(paths.data())
        migration.stamp_without_running(paths.data())

    def an_archive(self, marker: str = "after", steps=None, broken: bool = False) -> Path:
        """A release tarball, built on disk, exactly as one arrives from GitHub."""
        inside = self.home / "release" / "rundesk-cli-v99"
        support.a_real_tree(inside, marker)
        for name, body in (steps or {}).items():
            (inside / "src" / "rundesk" / "lifecycle" / "steps" / f"{name}.py").write_text(body)

        at = self.home / "release.tar.gz"
        with tarfile.open(at, "w:gz") as held:
            if broken:
                escaping = tarfile.TarInfo("../escaped")
                escaping.size = 0
                held.addfile(escaping, io.BytesIO(b""))
            held.add(inside, arcname=inside.name)
        return at

    def fetching(self, archive: Path):
        def fetch(_url, into):
            self.asked.append(_url)
            into.write_bytes(archive.read_bytes())
        return fetch

    def update(self, *argv, published="v99.0.0", why=None, archive=None):
        return support.run_with(
            ["update", *argv],
            asking=lambda: (published, why),
            fetching=self.fetching(archive) if archive is not None else None)


class WhereThisInstallStands(Updating):

    def test_an_update_that_finds_nothing_newer_leaves_this_copy_alone(self):
        code, out, _ = self.update(published=f"v{__version__}")
        self.assertEqual(OK, code)
        self.assertIn("UP TO DATE", out)
        self.assertEqual("before", (paths.app() / "README.md").read_text())

    def test_being_unable_to_ask_stops_the_update_and_ends_unsuccessfully(self):
        code, out, err = self.update(published=None, why=release.UNREACHABLE)
        self.assertEqual(FAILED, code)
        self.assertIn("UNKNOWN", err)
        self.assertNotIn("UP TO DATE", out + err)
        self.assertEqual("before", (paths.app() / "README.md").read_text())

    def test_nothing_published_is_not_read_as_being_current(self):
        code, _, err = self.update(published=None, why=release.NOTHING_PUBLISHED)
        self.assertEqual(FAILED, code)
        self.assertIn("NO RELEASES", err)

    def test_a_published_version_that_is_not_shaped_like_one_is_refused(self):
        code, _, _ = self.update(published="whatever-this-is")
        self.assertEqual(OK, code)
        self.assertEqual("before", (paths.app() / "README.md").read_text())

    def test_it_takes_no_flags(self):
        from rundesk.exits import USAGE
        code, _, _ = support.run_with(["update", "--check"])
        self.assertEqual(USAGE, code, "update grew a flag it is not meant to have")

    def test_being_up_to_date_names_the_version_it_is_on(self):
        _, out, _ = self.update(published=f"v{__version__}")
        self.assertIn(__version__, out)
        self.assertIn("UP TO DATE", out)


class AnUpdateThatLands(Updating):

    def test_it_replaces_the_program(self):
        code, _, err = self.update(archive=self.an_archive())
        self.assertEqual(OK, code, err)
        self.assertEqual("after", (paths.app() / "README.md").read_text())

    def test_it_names_the_release_now_installed(self):
        _, out, _ = self.update(archive=self.an_archive())
        self.assertIn("v99.0.0", out)

    def test_it_leaves_what_the_owner_keeps(self):
        theirs = paths.data() / "something-of-theirs"
        theirs.write_text("mine")
        self.update(archive=self.an_archive())
        self.assertEqual("mine", theirs.read_text())

    def test_it_leaves_what_the_owner_stated(self):
        config.stated("update_enabled", False, paths.data())
        self.update(archive=self.an_archive())
        self.assertFalse(config.read(paths.data())["update_enabled"])

    def test_it_adds_a_configuration_value_the_newer_release_introduced(self):
        from rundesk.utils import jsonfile
        jsonfile.write(config.where(paths.data()), {"backup_enabled": False})
        self.update(archive=self.an_archive())
        settled = config.read(paths.data())
        self.assertFalse(settled["backup_enabled"])
        self.assertIn("update_time", settled)

    def test_it_records_when_the_new_version_arrived(self):
        self.update(archive=self.an_archive())
        self.assertRegex(config.read(paths.data())["last_updated_at"],
                         r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

    def test_an_update_that_found_nothing_newer_does_not_touch_it(self):
        # Otherwise the answer drifts to "just now" every time somebody merely checks for an update.
        #
        # Put back to a date nothing here could produce, rather than comparing two live readings:
        # both runs land inside the same second, so a case that ran it twice and compared would pass
        # even with the rule removed. It did.
        self.update(archive=self.an_archive())
        config.stated("last_updated_at", "1999-12-31T23:59:59Z", paths.data())

        self.update(published=f"v{__version__}")

        self.assertEqual("1999-12-31T23:59:59Z", config.read(paths.data())["last_updated_at"],
                         "an update that moved nothing rewrote when a version last arrived")

    def test_it_leaves_no_staging_entries_behind(self):
        self.update(archive=self.an_archive())
        leftovers = [at.name for at in paths.app().iterdir()
                     if at.name.endswith((".incoming", ".outgoing"))]
        self.assertEqual([], leftovers)


class AnUpdateThatDoesNotLand(Updating):

    def test_an_archive_that_is_not_rundesk_leaves_the_install_as_it_was(self):
        empty = self.home / "empty.tar.gz"
        with tarfile.open(empty, "w:gz") as held:
            nothing = self.home / "nothing"
            nothing.mkdir(exist_ok=True)
            held.add(nothing, arcname="nothing")
        code, _, err = self.update(archive=empty)
        self.assertEqual(FAILED, code)
        self.assertIn("NOT APPLIED", err)
        self.assertEqual("before", (paths.app() / "README.md").read_text())

    def test_an_archive_that_would_write_outside_the_download_is_refused(self):
        # An archive is somebody else's bytes, and an unpacker that trusts them writes wherever they
        # say. The standard library only started refusing this far above the floor here.
        code, _, err = self.update(archive=self.an_archive(broken=True))
        self.assertEqual(FAILED, code)
        self.assertIn("NOT APPLIED", err)
        self.assertFalse((self.home / "escaped").exists())

    def test_a_download_that_fails_leaves_the_install_as_it_was(self):
        def refuses(_url, _into):
            raise OSError("the network went away")
        code, _, err = support.run_with(["update"], asking=lambda: ("v99.0.0", None),
                                        fetching=refuses)
        self.assertEqual(FAILED, code)
        self.assertIn("NOT APPLIED", err)
        self.assertEqual("before", (paths.app() / "README.md").read_text())

    def test_nothing_is_fetched_when_the_install_is_already_current(self):
        self.update(published=f"v{__version__}", archive=self.an_archive())
        self.assertEqual([], self.asked)


class CarryingTheInstallForward(Updating):
    """The migration half — the reason an update is two tiers rather than a file copy."""

    def test_the_steps_the_new_release_ships_are_run(self):
        code, _, err = self.update(archive=self.an_archive(steps={"0001_first": A_STEP}))
        self.assertEqual(OK, code, err)
        self.assertTrue((paths.data() / "carried").exists(), "the release's step did not run")

    def test_how_far_the_install_got_is_recorded(self):
        self.update(archive=self.an_archive(steps={"0001_first": A_STEP}))
        self.assertEqual("0001_first", config.read(paths.data())["migration"])

    def test_the_steps_run_after_the_files_land(self):
        # A step is the new release's own code; running it before its files are there would run the
        # old release's steps and call the install carried.
        self.update(archive=self.an_archive(steps={"0001_first": A_STEP}))
        self.assertEqual("after", (paths.app() / "README.md").read_text())
        self.assertTrue((paths.data() / "carried").exists())

    def test_a_step_that_fails_is_reported_rather_than_passed_over(self):
        code, _, err = self.update(
            archive=self.an_archive(steps={"0001_broken": support.A_STEP_THAT_FAILS}))
        self.assertEqual(FAILED, code)
        self.assertIn("0001_broken", err)

    def test_an_update_interrupted_before_settling_is_finished_by_running_it_again(self):
        """The half-updated state: current code, and configuration and migrations from before it.

        A machine that slept between the file swap and the settle leaves exactly this. Asking GitHub
        afterwards answers UP TO DATE for ever, so unless being current also settles, the release's
        migration step never runs and the value it added is never written — and nothing ever says so.
        """
        # Exactly what a swap leaves behind: the new release's files in place, nothing settled.
        support.a_real_tree(paths.app(), "after")
        (paths.app() / "src" / "rundesk" / "lifecycle" / "steps" / "0001_first.py").write_text(A_STEP)
        self.assertIsNone(config.read(paths.data())["migration"])

        code, _, err = self.update(published=f"v{__version__}")

        self.assertEqual(OK, code, err)
        self.assertTrue((paths.data() / "carried").exists(),
                        "an install left half-updated was never carried forward")
        self.assertEqual("0001_first", config.read(paths.data())["migration"])

    def test_being_up_to_date_and_settled_runs_no_step_a_second_time(self):
        support.a_real_tree(paths.app(), "after")
        (paths.app() / "src" / "rundesk" / "lifecycle" / "steps" / "0001_first.py").write_text(A_STEP)
        self.update(published=f"v{__version__}")
        (paths.data() / "carried").unlink()
        self.update(published=f"v{__version__}")
        self.assertFalse((paths.data() / "carried").exists(), "the step ran a second time")

    def test_being_up_to_date_with_nothing_installed_settles_nothing(self):
        # Running from a checkout against a root that has no install: there is no release to settle.
        import shutil as _shutil
        _shutil.rmtree(paths.app())
        code, _, err = self.update(published=f"v{__version__}")
        self.assertEqual(OK, code, err)

    def test_an_update_with_no_steps_to_run_still_succeeds(self):
        code, _, err = self.update(archive=self.an_archive())
        self.assertEqual(OK, code, err)

    def test_a_step_already_applied_does_not_run_again(self):
        self.update(archive=self.an_archive(steps={"0001_first": A_STEP}))
        (paths.data() / "carried").unlink()
        self.update(published="v99.0.1", archive=self.an_archive(steps={"0001_first": A_STEP}))
        self.assertFalse((paths.data() / "carried").exists(), "the step ran a second time")


class StagingAndPuttingBack(support.Isolated):
    """`tree.replace` on its own — the swap every install and update rests on."""

    def setUp(self):
        super().setUp()
        self.app = self.home / "app"
        (self.app / "src" / "rundesk").mkdir(parents=True, exist_ok=True)
        (self.app / "rundesk").write_text("old")
        (self.app / "README.md").write_text("old")
        self.new = self.home / "new"
        (self.new / "src" / "rundesk").mkdir(parents=True, exist_ok=True)
        (self.new / "rundesk").write_text("new")
        (self.new / "README.md").write_text("new")

    def test_a_swap_that_works_replaces_every_entry(self):
        tree.replace(self.new, self.app)
        self.assertEqual("new", (self.app / "rundesk").read_text())
        self.assertEqual("new", (self.app / "README.md").read_text())

    def test_a_swap_that_fails_part_way_puts_back_what_was_there(self):
        was = os.rename
        seen = []

        def fails_on_the_second(a, b):
            seen.append(b)
            if len([one for one in seen if not str(one).endswith(".outgoing")]) == 2:
                raise OSError("the disk went away")
            return was(a, b)

        os.rename = fails_on_the_second
        try:
            with self.assertRaises(OSError):
                tree.replace(self.new, self.app)
        finally:
            os.rename = was

        self.assertEqual("old", (self.app / "rundesk").read_text())
        self.assertEqual("old", (self.app / "README.md").read_text())

    def test_a_source_that_is_not_rundesk_is_refused_before_anything_is_copied(self):
        empty = self.home / "empty"
        empty.mkdir()
        with self.assertRaises(tree.Refused):
            tree.replace(empty, self.app)
        self.assertEqual("old", (self.app / "rundesk").read_text())


if __name__ == "__main__":
    unittest.main()
