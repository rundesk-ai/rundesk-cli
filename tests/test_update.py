"""Moving an install to a newer release, and what happens when that goes wrong.

Nothing here reaches the network. What is published arrives as `asking=` and the download arrives as
`fetching=`, both handed to `cli.main`, so every state — behind, current, unable to ask, a broken
archive, a failed swap — is driven against real files on disk with no GitHub anywhere near it.

**And the code behind that seam is driven too.** Replacing `asking=` proves what a command does with
each answer; it says nothing about the code that produces one. That code — the only place in the
product that reads a GitHub response — had never run under test at all, hidden by how well the seam
worked. `AskingGitHubForReal` drives it with the standard library's own `urlopen` replaced instead,
one layer further down, and still leaves nothing able to reach the network.

Run directly: `python3 tests/test_update.py`
"""

import contextlib
import io
import os
import tarfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

import support
from rundesk import __version__
from rundesk.core import config, paths
from rundesk.exits import FAILED, OK
from rundesk.lifecycle import backups, migration, release, tree

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

    def an_archive(self, marker: str = "after", steps=None, broken: bool = False,
                   escaping_link: str = "") -> Path:
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
            if escaping_link:
                held.addfile(self.a_link_out(escaping_link))
            held.add(inside, arcname=inside.name)
        return at

    def a_link_out(self, kind: str) -> tarfile.TarInfo:
        """A link member, nested one directory deep, whose target really lands outside the download.

        The two kinds need different targets to escape, and that asymmetry *is* the defect. A
        symlink is resolved against its own directory, so from `<release>/src/` it takes three `..`
        to get out of the download. A hard link is resolved by `tarfile` against the extraction root
        itself, so one `..` is already outside — while the old guard, measuring it from the member's
        directory like a symlink, saw it land harmlessly inside the release tree.
        """
        member = tarfile.TarInfo("rundesk-cli-v99/src/escaped")
        member.size = 0
        if kind == "symlink":
            member.type = tarfile.SYMTYPE
            member.linkname = "../../../escaped-out-of-the-download"
        else:
            member.type = tarfile.LNKTYPE
            member.linkname = "../escaped-out-of-the-download"
        return member

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
        from rundesk.utils import files
        files.write_json(config.where(paths.data()), {"backup_enabled": False})
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

    def test_an_archive_whose_symlink_points_outside_the_download_is_refused(self):
        code, _, err = self.update(archive=self.an_archive(escaping_link="symlink"))
        self.assertEqual(FAILED, code)
        self.assertIn("points outside the download", err)
        self.assertEqual("before", (paths.app() / "README.md").read_text())

    def test_an_archive_whose_hard_link_points_outside_the_download_is_refused(self):
        # The branch that had no test at all, and was wrong. A symlink's target is resolved against
        # the link's own directory; a hard link's is resolved by `tarfile` against the extraction
        # root. Measuring a hard link the first way made `../x` look like it landed inside the
        # release tree when it really lands beside the download — so the link was created pointing
        # at a real file outside it, and `tree.place` then copies that file's contents into `app/`
        # as though the release had shipped it. One `..` and one directory of nesting is enough.
        code, _, err = self.update(archive=self.an_archive(escaping_link="hardlink"))
        self.assertEqual(FAILED, code)
        # The guard's own words, not merely "it failed": measured the wrong way this member sails
        # through the check and the update dies later for an unrelated reason, which is the same
        # exit code and tells nobody the escape was caught.
        self.assertIn("points outside the download", err)
        self.assertEqual("before", (paths.app() / "README.md").read_text())

    def test_an_api_answer_that_is_not_an_object_is_unreachable_rather_than_a_traceback(self):
        # `said.get` on a list or on `null` raises out of the one function whose whole job is to
        # come back with one of three states rather than fall over, and nothing up the chain
        # catches it — the command would end in a traceback instead of saying UNKNOWN.
        import contextlib
        import io as _io
        import json as _json
        import urllib.request

        from rundesk.lifecycle import release

        @contextlib.contextmanager
        def answering(body):
            def opened(*_args, **_named):
                return contextlib.closing(_io.BytesIO(_json.dumps(body).encode()))
            with mock.patch.object(urllib.request, "urlopen", opened):
                yield

        for body in ([], None, "a string", 7):
            with self.subTest(body=body):
                with answering(body):
                    self.assertEqual((None, release.UNREACHABLE), release._asked_of_the_api())

    def test_a_copy_is_taken_before_any_step_touches_the_data(self):
        # The way back from a step that does not finish, and the reason there are no down-steps.
        config.stated("backup_enabled", True, paths.data())
        code, out, _ = self.update(archive=self.an_archive(steps={"0001_first": A_STEP}))
        self.assertEqual(OK, code)
        self.assertIn("kept", out)
        self.assertEqual(1, len(backups.kept(paths.backups())),
                         "no copy was taken before carrying")

    def test_no_copy_is_taken_when_the_owner_keeps_none(self):
        # An owner who turned copies off should not be surprised by one appearing.
        config.stated("backup_enabled", False, paths.data())
        self.update(archive=self.an_archive(steps={"0001_first": A_STEP}))
        self.assertEqual([], backups.kept(paths.backups()))

    def test_no_copy_is_taken_when_there_is_nothing_to_carry(self):
        # An ordinary update that changes no data leaves no copy behind every time.
        config.stated("backup_enabled", True, paths.data())
        self.update(archive=self.an_archive())
        self.assertEqual([], backups.kept(paths.backups()))

    def test_a_copy_that_could_not_be_taken_does_not_stop_the_carrying(self):
        # An install left un-migrated is its own kind of broken, so this is said and carried on.
        #
        # Driven against the helper rather than through `update`: an install settles in an
        # interpreter of its own by design, so a replacement made in *this* one would never reach
        # it — the first version of this case passed for that reason rather than for a good one.
        from rundesk.commands import update as the_update
        config.stated("backup_enabled", True, paths.data())
        steps = self.home / "steps"
        steps.mkdir(parents=True, exist_ok=True)
        (steps / "0001_first.py").write_text(A_STEP)

        with mock.patch.object(migration, "STEPS", steps):
            with mock.patch.object(the_update.backups, "save",
                                   side_effect=OSError("the disk filled")):
                said = the_update._kept_before_carrying()

        self.assertEqual("", said, "a copy that could not be taken must not stop the carrying")

    def test_the_copy_is_named_when_a_step_does_not_finish(self):
        config.stated("backup_enabled", True, paths.data())
        code, _, err = self.update(
            archive=self.an_archive(steps={"0001_first": support.A_STEP_THAT_FAILS}))
        self.assertEqual(FAILED, code)
        self.assertIn("as it was before this is the copy", err)

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


class AskingGitHubForReal(support.Isolated):
    """`latest_published` and `_asked_of_the_api` — the code the `asking=` seam has been hiding.

    Every other case in this suite replaces `asking=` with a closure, which is exactly right for
    proving what a *command* does with each answer. The cost, unnoticed until it was measured, is
    that the code which produces those answers — the only code in the product that reads a GitHub
    response — had never once run under test.

    So this drives the real functions with `urlopen` replaced instead. Nothing leaves the machine:
    the seam being replaced here is the standard library's, one layer lower down.
    """

    def setUp(self):
        super().setUp()
        self.asked = []

    def answering(self, url_landed_on=None, body=None, raising=None):
        """Stand in for `urlopen`, as either a redirect that landed somewhere or a JSON body."""
        def opened(request, *_args, **_named):
            self.asked.append(request.full_url)
            if raising is not None:
                raise raising
            return contextlib.closing(_AnAnswer(url_landed_on, body))
        return mock.patch.object(urllib.request, "urlopen", opened)

    def test_the_tag_is_read_off_the_redirect(self):
        with self.answering(url_landed_on="https://github.com/o/r/releases/tag/v1.2.3"):
            self.assertEqual(("v1.2.3", None), release.latest_published())

    def test_a_trailing_slash_on_the_redirect_is_not_the_tag(self):
        with self.answering(url_landed_on="https://github.com/o/r/releases/tag/v1.2.3/"):
            self.assertEqual(("v1.2.3", None), release.latest_published())

    def test_nothing_published_is_told_apart_from_unreachable(self):
        gone = urllib.error.HTTPError("u", 404, "Not Found", {}, None)
        with self.answering(raising=gone):
            self.assertEqual((None, release.NOTHING_PUBLISHED), release.latest_published())

    def test_nothing_published_is_settled_at_the_first_ask_and_not_asked_again(self):
        # A 404 on "latest" is an answer, not a failure to get one, so there is nothing for the
        # second way of asking to add. Without this the branch is untestable by its result alone:
        # the API 404s too, so removing the short-circuit gives the same answer by a longer road.
        gone = urllib.error.HTTPError("u", 404, "Not Found", {}, None)

        def opened(request, *_args, **_named):
            self.asked.append(request.full_url)
            if len(self.asked) == 1:
                raise gone
            return contextlib.closing(_AnAnswer(None, '{"tag_name": "v1.0.0"}'))

        with mock.patch.object(urllib.request, "urlopen", opened):
            self.assertEqual((None, release.NOTHING_PUBLISHED), release.latest_published())
        self.assertEqual(1, len(self.asked), "it asked a second time after a settled answer")

    def test_being_unable_to_reach_it_is_never_a_version(self):
        for why in (urllib.error.URLError("no route"), OSError("refused"), ValueError("odd")):
            with self.subTest(why=type(why).__name__):
                with self.answering(raising=why):
                    tag, said = release.latest_published()
                self.assertIsNone(tag)
                self.assertEqual(release.UNREACHABLE, said)

    def test_a_redirect_that_does_not_end_in_a_version_falls_back_to_the_api(self):
        # The reason there are two ways of asking at all.
        landed = ["https://github.com/o/r/releases", '{"tag_name": "v4.5.6"}']

        def opened(request, *_args, **_named):
            self.asked.append(request.full_url)
            return contextlib.closing(_AnAnswer(landed[0], landed[1])
                                      if len(self.asked) == 1
                                      else _AnAnswer(None, landed[1]))
        with mock.patch.object(urllib.request, "urlopen", opened):
            self.assertEqual(("v4.5.6", None), release.latest_published())
        self.assertEqual(2, len(self.asked), "it never asked the second way")

    def test_the_api_says_nothing_published_for_a_404_and_unreachable_for_anything_else(self):
        for code, wanted in ((404, release.NOTHING_PUBLISHED), (500, release.UNREACHABLE),
                             (403, release.UNREACHABLE)):
            with self.subTest(code=code):
                why = urllib.error.HTTPError("u", code, "no", {}, None)
                with self.answering(raising=why):
                    self.assertEqual((None, wanted), release._asked_of_the_api())

    def test_the_api_giving_a_tag_that_is_not_a_version_is_unreachable_not_current(self):
        # The rule the whole module exists for: being unable to get an answer is never a quiet
        # form of being up to date.
        with self.answering(body='{"tag_name": "nightly"}'):
            self.assertEqual((None, release.UNREACHABLE), release._asked_of_the_api())

    def test_a_body_that_is_not_json_at_all_is_unreachable(self):
        with self.answering(body="<html>rate limited</html>"):
            self.assertEqual((None, release.UNREACHABLE), release._asked_of_the_api())

    def test_it_asks_the_repository_this_release_belongs_to(self):
        with self.answering(url_landed_on="https://github.com/o/r/releases/tag/v1.2.3"):
            release.latest_published()
        self.assertIn(release.REPO, self.asked[0])


class _AnAnswer:
    """What `urlopen` hands back: something with a final URL and a body, closeable."""

    def __init__(self, landed, body):
        self._landed = landed
        self._body = body or ""

    def geturl(self):
        return self._landed

    def read(self):
        return self._body.encode("utf-8")

    def close(self):
        pass


class WhereAReleaseIsFetchedFrom(support.Isolated):
    """`archive_url` and `release_url` — built on every update and asserted on by nothing."""

    def test_the_archive_is_asked_for_by_tag(self):
        # Every update case replaces `fetching=` with a stub that ignores the URL, so a typo in
        # the template would run green for ever and 404 the first time somebody really updated.
        built = release.archive_url("v9.9.9")
        self.assertIn(release.REPO, built)
        self.assertIn("v9.9.9", built)
        self.assertTrue(built.startswith("https://"), built)

    def test_the_notes_are_named_for_a_version_and_only_for_a_version(self):
        self.assertIn("v9.9.9", release.release_url("v9.9.9"))
        self.assertIsNone(release.release_url("nightly"))
        self.assertIsNone(release.release_url(None))


if __name__ == "__main__":
    unittest.main()
