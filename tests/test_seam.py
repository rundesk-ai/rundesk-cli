"""Where agents meet the lifecycle that shipped before them, in the places no suite owns.

The lifecycle of the command — install, update, removal, the copies — was written and proved before
`data/` held an agent, and every suite that covers it was written then too. The cases here are the
ones that fall between those suites: they are about a command that already existed meeting a
directory that did not, and there is no file either of them belongs in.

Carrying agents on an update lives in `test_update.py`, beside the command that does it, and copies
that hold an agent live in `test_backups.py`. What is left, and what is here, is **removal**.

Nothing here places a launchd job or runs `launchctl`, and nothing reaches the network.

Run directly: `python3 tests/test_seam.py`
"""

import unittest
from pathlib import Path

import support
from rundesk.agents import directory
from rundesk.core import config, paths
from rundesk.exits import FAILED, OK
from rundesk.gateways import job, standing
from rundesk.lifecycle import backups, migration


class AnInstallWithAgentsInIt(support.Isolated):
    """A scratch install of the real product, with real agents standing in its data directory."""

    def setUp(self):
        super().setUp()
        support.a_real_tree(paths.app())
        paths.data().mkdir(parents=True, exist_ok=True)
        config.write_fresh(paths.data())
        migration.stamp_without_running(paths.data())
        self.agents = [self.an_agent("alpha"), self.an_agent("beta")]

    def an_agent(self, name: str) -> Path:
        """A real agent, built the way `agents add` builds one."""
        return directory.made(name, "anthropic")

    def uninstall(self, *argv, **collaborators):
        """Removal driven exactly as a person runs it — **nothing is redirected**.

        The search for the command link is left alone for `test_install.py`'s reason: `tree.unlink`
        only removes a link that resolves into *this* install's own `app/`, and this install stands
        under a temporary root, so nothing on a real PATH is ever a candidate. Redirecting it would
        make these cases agree with a bug rather than with the product.
        """
        return support.run_with(["uninstall", "--confirm", *argv], **collaborators)

    def still_there(self):
        return sorted(one.name for one in self.agents if one.is_dir())

    def the_job_for(self, name: str) -> job.Job:
        """This install's job for one agent, with its plist kept where the harness keeps them.

        `paths.home() / "LaunchAgents"` and never the owner's own directory — the same answer
        `support.run_with` patches `job.job` to give, written here because these cases have to reach
        the files *outside* a command run.
        """
        return job.job(name, directory.where(name), paths.home(), paths.home() / "LaunchAgents")

    def given_a_job_on_disk(self, name: str) -> job.Job:
        """The plist and shim a placed gateway leaves behind, without asking launchd for anything."""
        one = self.the_job_for(name)
        job.plist_of(one).parent.mkdir(parents=True, exist_ok=True)
        job.plist_of(one).write_bytes(b"<plist/>")
        job.shim_of(one).write_text("#!/bin/sh\n")
        return one


class RemovingAnInstallThatHasAgents(AnInstallWithAgentsInIt):
    """What `uninstall` does today with agents present, and only what it does today.

    Deliberately narrow. Whether a removal should first take away the jobs that host those agents is
    being wired elsewhere, and a case that asserted the finished behaviour here would be a case that
    claims a guarantee nothing has built yet — which is the one thing this product refuses to do.
    """

    def test_a_purge_takes_every_agent_away_with_the_data(self):
        # `data/` is what the owner accumulated, and an agent is the largest thing in it.
        code, _, err = self.uninstall("--purge")
        self.assertEqual(OK, code, err)
        self.assertEqual([], self.still_there())
        self.assertFalse(paths.agents().exists())

    def test_a_purge_leaves_no_records_behind_anywhere_under_the_root(self):
        # Named rather than swept is the rule the removal is written to, and a database keeps two
        # sidecars — so "the agent directory is gone" and "nothing of that agent is left" are two
        # different claims and this is the second one.
        self.uninstall("--purge")
        self.assertEqual([], sorted(paths.home().rglob(directory.RECORDS)))

    def test_a_removal_that_keeps_the_data_keeps_every_agent(self):
        code, out, err = self.uninstall()
        self.assertEqual(OK, code, err)
        self.assertEqual(["alpha", "beta"], self.still_there())
        self.assertIn(str(paths.data()), out)

    def test_nothing_confirming_takes_no_agent(self):
        code, _, err = support.run(["uninstall", "--purge"])
        self.assertEqual(FAILED, code)
        self.assertEqual(["alpha", "beta"], self.still_there())
        self.assertIn("nothing was removed", err)

    def test_a_copy_holding_agents_survives_a_purge(self):
        # A copy is worth nothing if the thing that takes the product away takes the copies too, and
        # now the thing a copy holds is somebody's agents.
        name = backups.save(paths.data(), paths.backups())

        self.uninstall("--purge")

        self.assertEqual([name], backups.kept(paths.backups()))
        self.assertTrue((paths.backups() / name / "agents" / "alpha" / directory.RECORDS).is_file(),
                        "a purge took the agents inside the copies with it")

    def test_a_purge_says_it_took_the_data_and_kept_the_copies(self):
        backups.save(paths.data(), paths.backups())
        _, out, _ = self.uninstall("--purge")
        self.assertIn(f"took   {paths.data()}", out)
        self.assertIn(str(paths.backups()), out)


class RemovingAnInstallWhileAGatewayIsRunning(AnInstallWithAgentsInIt):
    """The gap between "every job is taken back" and "no gateway is running".

    **`rundesk gateways run <agent>` is a documented foreground verb with no launchd job at all.**
    So `job.remove` finds nothing to take back — `bootout` answers `ALREADY_GONE`, which is correctly
    read as success — every check the removal made was satisfied, and it went on to take `app/` and,
    with `--purge`, `data/`, while that process was alive holding the real lock and about to have its
    database deleted underneath it.

    The lock is real here and taken through `standing.holding`, the way a gateway takes it. No
    launchd job is placed and `launchctl` is never run.
    """

    def test_a_removal_is_refused_while_a_gateway_is_holding_an_agent(self):
        with standing.holding(directory.where("alpha")):
            code, _out, err = self.uninstall()

        self.assertEqual(FAILED, code)
        self.assertIn("a gateway is running for alpha", err)
        self.assertIn("rundesk gateways stop alpha", err)
        self.assertTrue(paths.app().is_dir(), "the program was removed under a live gateway")
        self.assertEqual(["alpha", "beta"], self.still_there())

    def test_a_purge_is_refused_too_and_the_database_survives_it(self):
        # The worst version: `--purge` deletes `data/`, which is the database that gateway is
        # writing to, while it is writing to it.
        with standing.holding(directory.where("alpha")):
            code, _out, _err = self.uninstall("--purge")

        self.assertEqual(FAILED, code)
        self.assertTrue(directory.records("alpha").is_file())
        self.assertEqual(["alpha", "beta"], self.still_there())

    def test_it_says_where_a_gateway_with_no_job_behind_it_is_stopped(self):
        # The one thing a person in this position needs: the verb that started it has no launchd job
        # to take back, so nothing on the command line stops it and the terminal it is in does.
        with standing.holding(directory.where("alpha")):
            _code, _out, err = self.uninstall()
        self.assertIn("rundesk gateways run", err)

    def test_every_agent_that_is_up_is_named_and_never_only_the_first(self):
        # A refusal naming one at a time is a command somebody runs four times.
        with standing.holding(directory.where("alpha")):
            with standing.holding(directory.where("beta")):
                _code, _out, err = self.uninstall()
        self.assertIn("running for alpha", err)
        self.assertIn("running for beta", err)

    def test_nobody_being_able_to_ask_is_not_a_quiet_form_of_not_running(self):
        # Three answers, not two. A lock that cannot be opened may well be held, and taking an
        # install away under one is exactly what this refuses.
        support.not_as_root(self)
        lock = directory.where("alpha") / standing.LOCK
        lock.write_bytes(b"")
        lock.chmod(0o000)
        self.addCleanup(lock.chmod, 0o600)

        code, _out, err = self.uninstall()

        self.assertEqual(FAILED, code)
        self.assertIn("nobody can tell whether a gateway is running for alpha", err)
        self.assertIn("not a quiet form of offline", err)
        self.assertTrue(paths.app().is_dir())

    def test_the_description_names_a_gateway_that_has_to_be_stopped_first(self):
        # Said while somebody is deciding, not after they have typed the confirmation for a removal
        # that was never going to run.
        with standing.holding(directory.where("alpha")):
            code, _out, err = support.run(["uninstall"])
        self.assertEqual(FAILED, code)
        self.assertIn("rundesk gateways stop alpha", err)
        self.assertIn("nothing was removed", err)

    def test_an_install_with_no_gateway_running_is_removed_exactly_as_before(self):
        # The guard must cost the ordinary case nothing at all.
        code, out, err = self.uninstall()
        self.assertEqual(OK, code, err)
        self.assertIn("rundesk removed", out)


class WhenOnlyTheOverrideRecordCouldNotBeCleared(AnInstallWithAgentsInIt):
    """`job.remove` answering after it has already taken the job back — and what that used to stop.

    That function boots the job out, deletes the plist and deletes the shim, and only then asks
    launchd to make the override record inert. All of the removal can succeed and that last call
    fail, and it answers a sentence for it. The removal read **any** sentence as a hard stop, so for
    that agent it reported "nothing further was removed" while the plist and the shim genuinely were
    gone — and **every agent alphabetically after it never had its job touched at all**, for a reason
    that had nothing to do with them.
    """

    def an_install_that_will_not_clear_an_override(self):
        """A supervisor that takes every job back and refuses every `enable`."""
        return support.ASupervisor(enable=support.ran(1, err="the override store is read-only"))

    def test_the_agents_after_it_still_have_their_jobs_taken_back(self):
        first, second = self.given_a_job_on_disk("alpha"), self.given_a_job_on_disk("beta")

        code, out, err = self.uninstall(supervising=self.an_install_that_will_not_clear_an_override())

        self.assertEqual(OK, code, err)
        self.assertFalse(job.plist_of(second).exists(),
                         "beta's job was never touched because alpha's override would not clear")
        self.assertFalse(job.shim_of(second).exists())
        self.assertFalse(job.plist_of(first).exists())
        self.assertIn(first.label, out)
        self.assertIn(second.label, out)

    def test_what_is_left_to_finish_by_hand_is_said_for_every_agent(self):
        self.given_a_job_on_disk("alpha")
        self.given_a_job_on_disk("beta")

        _code, _out, err = self.uninstall(
            supervising=self.an_install_that_will_not_clear_an_override())

        self.assertIn("launchctl enable", err)
        self.assertEqual(2, err.count("could not be made inert"), err)

    def test_a_job_that_could_not_be_taken_back_still_stops_the_removal(self):
        # The distinction has to cut both ways: a bootout that failed means the job may still be
        # loaded, and carrying on would take away the program it points at.
        self.given_a_job_on_disk("alpha")

        code, _out, err = self.uninstall(
            supervising=support.ASupervisor(bootout=support.ran(1, err="launchd said no")))

        self.assertEqual(FAILED, code)
        self.assertIn("could not be taken back", err)
        self.assertIn("nothing further was removed", err)
        self.assertTrue(paths.app().is_dir())

    def test_the_two_answers_really_are_different_sentences_from_job_remove(self):
        """The phrase `uninstall` tells them apart by, asserted against the function that words it.

        `commands.uninstall` matches a substring of somebody else's message, which is safe only for
        as long as that message says it. This drives `job.remove` itself into both outcomes, so a
        rewording there goes red here rather than quietly turning every override failure back into a
        hard stop that skips every agent after it.
        """
        from rundesk.commands import uninstall

        one = self.given_a_job_on_disk("alpha")
        took_it_back = job.remove(one, self.an_install_that_will_not_clear_an_override())
        would_not = job.remove(self.given_a_job_on_disk("beta"),
                               support.ASupervisor(bootout=support.ran(1, err="launchd said no")))

        self.assertIn(uninstall.TAKEN_BACK_ANYWAY, took_it_back)
        self.assertNotIn(uninstall.TAKEN_BACK_ANYWAY, would_not)
        self.assertFalse(job.plist_of(one).exists(),
                         "the files really do come off the disk before that answer is given")


if __name__ == "__main__":
    unittest.main()
