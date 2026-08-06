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
import shutil
import tarfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict, List
from unittest import mock

import support
from rundesk import __version__
from rundesk.agents import directory
from rundesk.agents import migration as agent_migration
from rundesk.commands import update as the_update
from rundesk.core import config, paths
from rundesk.exits import FAILED, OK
from rundesk.gateways import standing
from rundesk.lifecycle import backups, migration, release, tree
from rundesk.skills import grants, library

A_STEP = '''
from pathlib import Path

def carry(data):
    (Path(data) / "carried").write_text("the step ran")
'''

#: An agent step: a table and a file together, which is what a step is handed both for.
AN_AGENT_STEP = '''
from pathlib import Path

def carry(conn, where):
    conn.execute('CREATE TABLE IF NOT EXISTS carried (one TEXT) STRICT')
    (Path(where) / "carried").write_text("the agent step ran")
'''

#: An agent step that cannot finish for one agent and finishes for every other. How "one that fails
#: does not stop the next" is proved rather than asserted.
AN_AGENT_STEP_THAT_FAILS_FOR_ONE = '''
from pathlib import Path

def carry(conn, where):
    if Path(where).name == "alpha":
        raise RuntimeError("this step could not finish")
    conn.execute('CREATE TABLE IF NOT EXISTS carried (one TEXT) STRICT')
    (Path(where) / "carried").write_text("the agent step ran")
'''

#: An agent step that cannot finish. An agent step and an install step do not take the same
#: arguments, so the install one from `support` would fail here for the wrong reason entirely.
AN_AGENT_STEP_THAT_FAILS = '''
def carry(conn, where):
    raise RuntimeError("this step could not finish")
'''

#: An agent step that refuses to run until the install's own step has landed. The order under test
#: is not a comment: an install step may reshape where an agent's things stand, and an agent step
#: run first would be run against a layout the release has not finished making.
AN_AGENT_STEP_THAT_NEEDS_THE_INSTALL_CARRIED = '''
from pathlib import Path

def carry(conn, where):
    if not (Path(where).parent.parent / "carried").exists():
        raise RuntimeError("the install's own step had not run yet")
    conn.execute('CREATE TABLE IF NOT EXISTS carried (one TEXT) STRICT')
    (Path(where) / "carried").write_text("the agent step ran")
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

    def an_archive(self, marker: str = "after", steps=None, agent_steps=None,
                   broken: bool = False, escaping_link: str = "") -> Path:
        """A release tarball, built on disk, exactly as one arrives from GitHub.

        `agent_steps` ship in the release beside the install's own, because that is the only way an
        agent step can reach an update at all: the settling is done by the release that landed, in
        an interpreter of its own, so a step written into *this* process never gets there.
        """
        inside = self.home / "release" / "rundesk-cli-v99"
        support.a_real_tree(inside, marker)
        for name, body in (steps or {}).items():
            (inside / "src" / "rundesk" / "lifecycle" / "steps" / f"{name}.py").write_text(body)
        for name, body in (agent_steps or {}).items():
            (inside / "src" / "rundesk" / "agents" / "steps" / f"{name}.py").write_text(body)

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
        # The guard's own words and the member it caught. Unpacking now goes through
        # `utils.archives`, which is the one place that check is written, so the sentence names where
        # it refused rather than the caller's word for it.
        self.assertIn("points outside", err)
        self.assertIn("escaped", err)
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
        self.assertIn("points outside", err)
        self.assertIn("escaped", err)
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


class CarryingTheAgentsForward(Updating):
    """The half nothing called. `carry_every` shipped, was tested, and was reached from nowhere.

    Driven end to end rather than against the helper, because the seam being closed is precisely the
    one between a release's agent steps and the command that is supposed to run them — and the
    settling happens in an interpreter of its own, so a case that patched something in this process
    would prove nothing about the update anybody runs.
    """

    def an_agent(self, name: str) -> Path:
        """A real agent, built the way `agents add` builds one, on the release installed now.

        Made by this checkout, which ships `0001` and nothing else, so an archive carrying a `0002`
        is an agent with a step waiting — which is the whole situation under test.
        """
        return directory.made(name, "anthropic")

    def carried(self, name: str) -> bool:
        return (paths.agents() / name / "carried").exists()

    def test_every_agent_is_carried_by_an_update(self):
        self.an_agent("alpha")
        self.an_agent("beta")

        code, out, err = self.update(archive=self.an_archive(agent_steps={"9999_x": AN_AGENT_STEP}))

        self.assertEqual(OK, code, err)
        self.assertTrue(self.carried("alpha"), "the release's agent step never ran for alpha")
        self.assertTrue(self.carried("beta"), "the release's agent step never ran for beta")
        self.assertIn("carrying alpha to 9999_x", out)

    def test_an_agent_made_before_the_rule_is_given_the_skill_every_agent_holds(self):
        # `directory.made` grants nothing — the floor is given by the command layer, which an agent
        # from an earlier release never went through, and by the sweep, which is this. Driven
        # through the whole command rather than against `grants.refreshed`, because the seam being
        # proved is that `rundesk update` reaches it at all.
        self.an_agent("alpha")
        self.assertIsNone(grants.holding("alpha", library.REQUIRED_SKILL))

        code, _out, err = self.update(archive=self.an_archive())

        self.assertEqual(OK, code, err)
        self.assertIsNotNone(grants.holding("alpha", library.REQUIRED_SKILL),
                             "the update did not give alpha the skill every agent holds")

    def test_how_far_each_agent_got_is_recorded_in_its_own_records(self):
        self.an_agent("alpha")
        self.update(archive=self.an_archive(agent_steps={"9999_x": AN_AGENT_STEP}))
        self.assertIn("9999_x", agent_migration.recorded(directory.records("alpha")))

    def test_an_agent_that_cannot_be_carried_does_not_stop_the_next(self):
        # Nineteen agents that are fine are not something to take down for the third one's sake.
        self.an_agent("alpha")
        self.an_agent("beta")

        self.update(archive=self.an_archive(
            agent_steps={"9999_x": AN_AGENT_STEP_THAT_FAILS_FOR_ONE}))

        self.assertFalse(self.carried("alpha"))
        self.assertTrue(self.carried("beta"), "one agent failing stopped the ones after it")

    def test_an_agent_that_could_not_be_carried_makes_the_update_non_zero(self):
        # An install whose agents are not carried is not a settled install, and `rundesk update` is
        # idempotent and safe to run again — which is the way out, and only exists if it is said.
        self.an_agent("alpha")
        self.an_agent("beta")

        code, _, err = self.update(archive=self.an_archive(
            agent_steps={"9999_x": AN_AGENT_STEP_THAT_FAILS_FOR_ONE}))

        self.assertEqual(FAILED, code)
        self.assertIn("alpha", err)
        self.assertNotIn("beta", err, "an agent that carried perfectly well was reported as failed")

    def test_the_installs_own_steps_run_before_any_agent_is_carried(self):
        # An install step may reshape where an agent's things stand. The agent step here refuses to
        # run until the install's has landed, so the wrong order is a failure rather than a comment.
        self.an_agent("alpha")

        code, _, err = self.update(archive=self.an_archive(
            steps={"0001_first": A_STEP},
            agent_steps={"9999_x": AN_AGENT_STEP_THAT_NEEDS_THE_INSTALL_CARRIED}))

        self.assertEqual(OK, code, err)
        self.assertTrue(self.carried("alpha"))

    def test_an_install_with_no_agents_carries_none_and_still_succeeds(self):
        # Nobody having added an agent is an answer, not a discovery that found nothing.
        code, _, err = self.update(archive=self.an_archive(agent_steps={"9999_x": AN_AGENT_STEP}))
        self.assertEqual(OK, code, err)

    def test_an_agent_already_on_this_release_is_not_carried_again(self):
        self.an_agent("alpha")
        self.update(archive=self.an_archive(agent_steps={"9999_x": AN_AGENT_STEP}))
        (paths.agents() / "alpha" / "carried").unlink()

        self.update(published="v99.0.1",
                    archive=self.an_archive(agent_steps={"9999_x": AN_AGENT_STEP}))

        self.assertFalse(self.carried("alpha"), "the agent step ran a second time")

    def test_an_update_that_found_nothing_newer_still_carries_the_agents(self):
        """The half-updated install, one level down: files landed, agents never carried.

        A machine that slept between the swap and the settle leaves this, and asking GitHub
        afterwards answers UP TO DATE for ever. Unless being current also carries the agents, the
        step the release shipped for them never runs and nothing ever says so.
        """
        self.an_agent("alpha")
        support.a_real_tree(paths.app(), "after")
        (paths.app() / "src" / "rundesk" / "agents" / "steps" / "9999_x.py").write_text(
            AN_AGENT_STEP)

        code, _, err = self.update(published=f"v{__version__}")

        self.assertEqual(OK, code, err)
        self.assertTrue(self.carried("alpha"),
                        "an install left half-updated never carried its agents")


class AFakeGateway:
    """Standing a gateway down and starting it again — recorded rather than done.

    Nothing here starts a launchd job or shells out to `launchctl`. What is under test is which
    gateways an update decides to touch and in which order, and that is entirely a question about
    the caller: the seam is a pair of calls, so a pair of lists is the whole of what has to be seen.

    Which agents it refuses for is named on the way in, so a case about a gateway that will not stop
    and a case about one that will not start again are the same object with a different argument.
    """

    def __init__(self, refusing_down=(), refusing_up=()):
        self.went_down: List[str] = []
        self.came_up: List[str] = []
        self._refusing_down = set(refusing_down)
        self._refusing_up = set(refusing_up)

    def down(self, name: str) -> str:
        if name in self._refusing_down:
            return "it would not stop"
        self.went_down.append(name)
        return ""

    def up(self, name: str) -> str:
        if name in self._refusing_up:
            return "it would not start"
        self.came_up.append(name)
        return ""


class TheGatewaySeam(support.Isolated):
    """Which gateways an update stands down before it carries, and which it starts again.

    `carried_every_agent` by name rather than through the command, because the settling runs in an
    interpreter of its own: a gateway held in this process is invisible to that one, and a seam
    passed in from this process could never reach it. The command's own behaviour is proved by
    `CarryingTheAgentsForward`; what is here is the decision.
    """

    def setUp(self):
        super().setUp()
        self.steps = self.home / "agent-steps"
        self.steps.mkdir(parents=True, exist_ok=True)
        shutil.copy2(agent_migration.STEPS / "0001_the_records_an_agent_keeps.py", self.steps)
        self.said: List[str] = []
        stepping = mock.patch.object(agent_migration, "STEPS", self.steps)
        stepping.start()
        self.addCleanup(stepping.stop)

    def an_agent(self, name: str) -> Path:
        """A real agent, carried onto whatever steps stand in the scratch directory right now."""
        return directory.made(name, "anthropic")

    def a_step_waiting(self) -> None:
        """One more step than every agent made so far has run."""
        (self.steps / "9999_x.py").write_text(AN_AGENT_STEP, encoding="utf-8")

    def a_gateway_for(self, name: str):
        """A gateway holding this agent's name, claimed the way a real one claims it.

        `standing.holding` and nothing else: the claim is the check, it is the kernel that answers,
        and no launchd job is anywhere near it.
        """
        return standing.holding(directory.where(name))

    def carrying(self, gateways=None) -> Dict[str, str]:
        return the_update.carried_every_agent(self.said.append, gateways)

    def carried(self, name: str) -> bool:
        return (paths.agents() / name / "carried").exists()

    def test_a_live_gateway_with_nothing_to_stand_it_down_stops_that_agent_being_carried(self):
        # Carrying an agent while its gateway holds the records open is the `database is locked`
        # failure. Named and refused rather than attempted, and never reported as carried.
        #
        # **Not what `rundesk update` does any more**: `settle` resolves something that can stand a
        # gateway down before it calls this, and `tests/test_seam.py` proves what that does. What is
        # left here is a caller inside this codebase that hands nothing in, which the type allows.
        self.an_agent("alpha")
        self.a_step_waiting()

        with self.a_gateway_for("alpha"):
            gone_wrong = self.carrying()

        self.assertIn("alpha", gone_wrong)
        self.assertIn("a gateway is running for it", gone_wrong["alpha"])
        self.assertFalse(self.carried("alpha"), "an agent was carried under a live gateway")

    def test_an_agent_whose_gateway_is_down_is_carried_beside_one_whose_is_not(self):
        self.an_agent("alpha")
        self.an_agent("beta")
        self.a_step_waiting()

        with self.a_gateway_for("alpha"):
            gone_wrong = self.carrying()

        self.assertEqual(["alpha"], sorted(gone_wrong))
        self.assertTrue(self.carried("beta"))

    def test_exactly_the_gateways_that_were_up_are_stood_down_and_started_again(self):
        self.an_agent("alpha")
        self.an_agent("beta")
        self.a_step_waiting()
        gateways = AFakeGateway()

        with self.a_gateway_for("alpha"):
            gone_wrong = self.carrying(gateways)

        self.assertEqual({}, gone_wrong)
        self.assertEqual(["alpha"], gateways.went_down)
        self.assertEqual(["alpha"], gateways.came_up,
                         "a gateway that was already stopped was started by an update")
        self.assertTrue(self.carried("alpha"))
        self.assertTrue(self.carried("beta"))

    def test_a_gateway_is_left_alone_when_that_agent_has_nothing_waiting(self):
        # The ordinary install: every agent already on this release. Standing somebody's gateway
        # down for an agent with nothing to carry is a cost paid for nothing, and refusing their
        # update because one is running is a failure that did not happen.
        self.an_agent("alpha")
        gateways = AFakeGateway()

        with self.a_gateway_for("alpha"):
            gone_wrong = self.carrying(gateways)

        self.assertEqual({}, gone_wrong)
        self.assertEqual([], gateways.went_down)

    def test_a_gateway_nobody_can_ask_about_is_not_read_as_one_that_is_not_running(self):
        # Three answers, not two. Reporting an agent nobody can ask about as offline is how a carry
        # happens under a live writer.
        support.not_as_root(self)
        self.an_agent("alpha")
        self.a_step_waiting()
        with self.a_gateway_for("alpha"):
            pass
        lock = directory.where("alpha") / standing.LOCK
        lock.chmod(0o000)
        self.addCleanup(lock.chmod, 0o600)

        gone_wrong = self.carrying(AFakeGateway())

        self.assertIn("alpha", gone_wrong)
        self.assertIn("nobody can tell", gone_wrong["alpha"])
        self.assertFalse(self.carried("alpha"))

    def test_a_gateway_that_would_not_stand_down_stops_that_agent_being_carried(self):
        self.an_agent("alpha")
        self.a_step_waiting()
        gateways = AFakeGateway(refusing_down=["alpha"])

        with self.a_gateway_for("alpha"):
            gone_wrong = self.carrying(gateways)

        self.assertIn("would not stand down", gone_wrong["alpha"])
        self.assertEqual([], gateways.came_up, "a gateway that never went down was started anyway")
        self.assertFalse(self.carried("alpha"))

    def test_a_gateway_that_was_stood_down_and_would_not_start_again_is_said_out_loud(self):
        # A gateway that was up and is now down is not a detail for a summary: the machine is not as
        # this update found it, and the update has to end non-zero saying so.
        self.an_agent("alpha")
        self.a_step_waiting()
        gateways = AFakeGateway(refusing_up=["alpha"])

        with self.a_gateway_for("alpha"):
            gone_wrong = self.carrying(gateways)

        self.assertIn("could not be started again", gone_wrong["alpha"])
        self.assertTrue(self.carried("alpha"), "the agent was not carried after all")

    def test_a_gateway_is_started_again_even_when_the_carry_failed(self):
        # The `finally` this rests on. A carry that died must still leave the machine as it found it.
        self.an_agent("alpha")
        (self.steps / "9999_x.py").write_text(AN_AGENT_STEP_THAT_FAILS, encoding="utf-8")
        gateways = AFakeGateway()

        with self.a_gateway_for("alpha"):
            gone_wrong = self.carrying(gateways)

        self.assertIn("alpha", gone_wrong)
        self.assertEqual(["alpha"], gateways.came_up,
                         "a carry that failed left the gateway it stood down lying stopped")

    def test_an_install_with_no_agents_touches_no_gateway_at_all(self):
        gateways = AFakeGateway()
        self.assertEqual({}, self.carrying(gateways))
        self.assertEqual(([], []), (gateways.went_down, gateways.came_up))

    def test_an_agent_whose_records_cannot_be_read_is_named_rather_than_passed_over(self):
        at = self.an_agent("alpha")
        (at / directory.RECORDS).write_bytes(b"this is not a database")

        gone_wrong = self.carrying(AFakeGateway())

        self.assertIn("alpha", gone_wrong)


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
