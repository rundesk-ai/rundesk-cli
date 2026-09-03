"""Where agents meet the lifecycle that shipped before them, in the places no suite owns.

The lifecycle of the command — install, update, removal, the copies — was written and proved before
`data/` held an agent, and every suite that covers it was written then too. The cases here are the
ones that fall between those suites: they are about a command that already existed meeting a
directory that did not, and there is no file either of them belongs in.

Carrying agents on an update lives in `test_update.py`, beside the command that does it, and copies
that hold an agent live in `test_backups.py`. What is left, and what is here, is **removal** — and
now the other half of the same meeting: **the gateway that hosts an agent, stood down by a command
that has to move `data/` and started again afterwards.**

Those cases are here rather than in either of the two suites they touch, for the reason this file
exists at all: what is under test is one command reaching the *other* command's answer. `update` and
`backups restore` each prove their own decisions against a stand-in seam; what neither can prove on
its own is that the thing they are handed really stops and starts a gateway, because that is
`commands.gateways`, and that suite knows nothing about a restore.

**`launchctl` is never run.** The supervisor is a stand-in throughout — but one that makes the world
change the way launchd does, taking and letting go of the agent's real lock as it answers, so a
gateway "coming up" here is the kernel's answer and not a flag a case set. Nothing reaches the
network.

Run directly: `python3 tests/test_seam.py`
"""

import contextlib
import io
import shutil
import unittest
from pathlib import Path
from typing import Dict
from unittest import mock

import support
from rundesk.agents import directory
from rundesk.agents import migration as agent_migration
from rundesk.commands import update as the_update
from rundesk.commands.gateways import Cycled
from rundesk.core import config, paths
from rundesk.exits import FAILED, OK
from rundesk.gateways import job, standing
from rundesk.lifecycle import backups, migration

#: An agent step that leaves something behind, so "this agent was carried" is a file on the disk
#: rather than a record this suite would have to trust. The same shape `test_update.py` uses.
AN_AGENT_STEP = '''
from pathlib import Path

def carry(conn, where):
    conn.execute('CREATE TABLE IF NOT EXISTS carried (one TEXT) STRICT')
    (Path(where) / "carried").write_text("the agent step ran")
'''


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
        arguments = ["uninstall", "--confirm", *argv]
        if "--purge" in argv and "--root" not in argv:
            arguments += ["--root", str(paths.home())]
        return support.run_with(arguments, **collaborators)

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


class ALaunchdWhereGatewaysReallyRun(support.ASupervisor):
    """A stand-in supervisor that makes the world change the way launchd's answers say it did.

    **The lock is real, and that is the whole value of this class.** `support.ASupervisor` records
    what it was asked and answers what a case wants, which is everything `commands.gateways` needed
    while what it was proving was its own decisions. It is not enough here: what these cases are
    about is whether a gateway is really gone by the time a restore replaces `data/`, and whether one
    is really back afterwards, and only the kernel can say that. So a `bootout` that answers success
    lets go of the agent's own `gateway.lock`, and a `bootstrap` that answers success takes it —
    through `standing.holding`, which is what a gateway itself uses.

    **Conditioned on the answer, never on the call.** A `bootout` this case made answer `1` is a job
    launchd would not take back, and the gateway behind it is still running; a stand-in that let go
    anyway would let a command that misread a refusal go on passing.

    `launchctl` is not run and no launchd job exists. What is being stood in for is the one thing a
    suite may not have: a supervisor that really starts and stops things in somebody's login session.
    """

    def __init__(self, **answers: object) -> None:
        super().__init__(**answers)
        self.holding: Dict[str, contextlib.ExitStack] = {}

    def running(self, name: str) -> None:
        """Take this agent's name, the way a gateway holds it for the whole of its life.

        The claim itself, and never through a `place` — a case may have asked bootstrapping to fail,
        and a gateway that could not be put up in the first place would leave that case proving
        nothing about what happens to one that is running.
        """
        held = contextlib.ExitStack()
        held.enter_context(standing.holding(directory.where(name)))
        self.holding[name] = held

    def let_go(self, name: str) -> None:
        held = self.holding.pop(name, None)
        if held is not None:
            held.close()

    def let_go_of_everything(self) -> None:
        """Drop every lock this stand-in holds, however a case ended."""
        for name in list(self.holding):
            self.let_go(name)

    def take_back(self, label: str) -> support.programs.Ran:
        said = super().take_back(label)
        if said.trouble is None and (said.code == 0 or said.code in job.ALREADY_GONE):
            self.let_go(_the_agent_in(label))
        return said

    def end(self, label: str) -> support.programs.Ran:
        said = super().end(label)
        if said.trouble is None and said.code in (0, *job.ALREADY_GONE):
            self.let_go(_the_agent_in(label))
        return said

    def place(self, plist: Path) -> support.programs.Ran:
        said = super().place(plist)
        if said.trouble is None and said.code == 0:
            self.running(_the_agent_in(Path(plist).stem))
        return said


def _the_agent_in(label: str) -> str:
    """Which agent a label is for. `ai.rundesk.<fingerprint>.gateway.<agent>` — the last part."""
    return label.rsplit(".", 1)[-1]


class WithGatewaysThatReallyStartAndStop(AnInstallWithAgentsInIt):
    """The two guards `support.run_with` puts around a command, for cases that reach past one.

    A restore is driven through `cli.main` and inherits them. `settle` cannot be: it is reached only
    in an interpreter of its own, so no case can drive it the way a person runs it, and these cases
    call it by name. What the harness would have been providing is exactly two things — every plist
    a command writes lands in the scratch root, and nothing reaches the real `launchctl` — and both
    are put back here rather than left out.
    """

    def a_supervisor(self, **answers) -> ALaunchdWhereGatewaysReallyRun:
        """A stand-in launchd whose answers really take and free the agents' names."""
        by = ALaunchdWhereGatewaysReallyRun(**answers)
        self.addCleanup(by.let_go_of_everything)
        return by

    def plists_in_the_scratch_root(self):
        """`job.job` with the plists kept under the scratch root, as `support.run_with` patches it.

        Reached for rather than written out again: the one answer to *where does a suite's plist go*
        lives beside the harness that patches it in, and a second copy here would be a second answer
        to the one question where getting it wrong writes into the owner's real login items.
        """
        return mock.patch.object(job, "job", support._in_the_scratch_root)

    def the_supervisor_it_finds(self, by):
        """`job.Launchd` replaced with this case's stand-in, for the code that resolves its own.

        `update.settle` builds what it stands gateways down with, because the process that ran the
        update cannot hand an object across the process boundary the settling happens on the far
        side of. So the way to drive that resolution is to replace what it resolves *to* — which is
        the same attribute `support.run_with` replaces with something that raises.
        """
        return mock.patch.object(job, "Launchd", lambda: by)


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
        with backups._opened_copy(paths.backups(), name) as copied:
            self.assertTrue((copied / "agents" / "alpha" / directory.RECORDS).is_file(),
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


class WhatStandsAGatewayDownAndStartsItAgain(WithGatewaysThatReallyStartAndStop):
    """`commands.gateways.Cycled` on its own — the thing an update and a restore are handed.

    Both of those commands were written around a seam and proved against a stand-in for it, which
    proves what they decide and nothing at all about what happens when the seam is real. These are
    the cases in between: the name really comes free, a gateway really holds it afterwards, and what
    comes back when either of those did not happen is a sentence and never an exception.
    """

    def asking(self, doing):
        """Ask the seam for one verb, and hand back what it answered and what it said out loud."""
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), \
                self.plists_in_the_scratch_root():
            trouble = doing()
        return trouble, out.getvalue(), err.getvalue()

    def test_nothing_can_build_one_that_reaches_the_owners_own_launchd(self):
        # The supervisor is the argument and there is no default, and that is the whole of the
        # isolation: a default bound here is a real `Launchd` reached by any caller that forgot to
        # pass one — a suite included, against jobs that keep somebody's real work running.
        with self.assertRaises(TypeError):
            Cycled()

    def test_standing_a_live_gateway_down_really_frees_the_name(self):
        # The kernel's answer and not the stand-in's: what a restore needs is the name free, and
        # `bootout` reporting success is exactly the thing this product refuses to read as proof.
        by = self.a_supervisor()
        by.running("alpha")

        trouble, out, _err = self.asking(lambda: Cycled(by).down("alpha"))

        self.assertEqual("", trouble)
        self.assertEqual(standing.OFFLINE, standing.standing(directory.where("alpha")).how)
        self.assertIn("gateway stopped for alpha", out)

    def test_starting_one_again_really_puts_a_gateway_back_on_the_name(self):
        by = self.a_supervisor()

        trouble, out, _err = self.asking(lambda: Cycled(by).up("alpha"))

        self.assertEqual("", trouble)
        self.assertEqual(standing.ONLINE, standing.standing(directory.where("alpha")).how)
        self.assertIn("gateway started for alpha", out)
        self.assertTrue(job.plist_of(self.the_job_for("alpha")).is_file(),
                        "a gateway was reported started with no job behind it")

    def test_a_gateway_that_will_not_stop_answers_a_sentence_and_leaves_it_running(self):
        # Everything the caller sees about it: one sentence to put inside its own, and the detail
        # printed by the verb itself. A stop that failed must also not have stopped anything.
        by = self.a_supervisor(bootout=support.ran(1, err="launchd said no"))
        by.running("alpha")

        trouble, _out, err = self.asking(lambda: Cycled(by).down("alpha"))

        self.assertIn("rundesk gateways stop alpha", trouble)
        self.assertIn("could not be taken back", err)
        self.assertEqual(standing.ONLINE, standing.standing(directory.where("alpha")).how)

    def test_a_gateway_that_will_not_start_answers_a_sentence_naming_the_other_verb(self):
        by = self.a_supervisor(bootstrap=support.ran(1, err="launchd said no"))

        trouble, _out, err = self.asking(lambda: Cycled(by).up("alpha"))

        self.assertIn("rundesk gateways start alpha", trouble)
        self.assertIn("was not placed", err)
        self.assertEqual(standing.OFFLINE, standing.standing(directory.where("alpha")).how)

    def test_a_name_that_is_not_an_agent_is_a_sentence_rather_than_something_that_raises(self):
        # The seam's contract, and the reason it is a sentence at all: an update names this agent
        # and carries the next one, and a restore starts again what it stood down from a `finally`,
        # where a raise would replace whatever the restore itself had answered.
        by = self.a_supervisor()

        trouble, _out, err = self.asking(lambda: Cycled(by).up("nobody"))

        self.assertIn("rundesk gateways start nobody", trouble)
        self.assertIn("nobody is not an agent on this install", err)

    def test_the_filesystem_failing_under_a_start_is_a_sentence_and_not_a_traceback(self):
        # The two things the verbs below do not word for themselves. A restore starts its gateways
        # again from a `finally` and `cli.main` has no catch-all, so a raise here would replace
        # whatever the restore had answered and reach whoever typed the command as a stack trace.
        by = self.a_supervisor()

        with mock.patch.object(job, "place", side_effect=OSError("the disk filled")):
            trouble, _out, _err = self.asking(lambda: Cycled(by).up("alpha"))

        self.assertIn("could not be run at all", trouble)
        self.assertIn("the disk filled", trouble)
        self.assertIn("rundesk gateways start alpha", trouble)

    def test_a_name_that_reaches_outside_where_agents_are_kept_is_a_sentence_too(self):
        by = self.a_supervisor()

        trouble, _out, _err = self.asking(lambda: Cycled(by).down("../elsewhere"))

        self.assertIn("could not be run at all", trouble)
        self.assertIn("does not stand where agents are kept", trouble)


class TheGatewaysARestoreCycles(WithGatewaysThatReallyStartAndStop):
    """`rundesk backups restore --confirm` on a machine with a gateway up, end to end.

    Driven through `cli.main`, which is what builds the seam, so what is under test is the wiring
    and not a seam a case handed in. The refusal this replaced was real and honest — a restore
    renames `data/` aside and a copy into its place, and a lock lives on the inode, so a gateway
    that lived through one holds a descriptor nothing can reach while a second gateway takes the
    name — and what is proved here is that the same guarantee now costs a stop and a start instead
    of a refusal.
    """

    def setUp(self):
        super().setUp()
        (paths.data() / "marker.txt").write_text("what was there before")
        self.copy = backups.save(paths.data(), paths.backups())
        (paths.data() / "marker.txt").write_text("changed since the copy")

    def restore(self, by):
        return support.run_with(["backups", "restore", self.copy, "--confirm"], supervising=by)

    def the_data_says(self) -> str:
        return (paths.data() / "marker.txt").read_text()

    def test_a_gateway_that_is_up_is_stood_down_and_started_again_rather_than_refused(self):
        by = self.a_supervisor()
        by.running("alpha")

        code, out, err = self.restore(by)

        self.assertEqual(OK, code, err)
        self.assertIn("stood the gateway for alpha down", out)
        self.assertIn("started the gateway for alpha again", out)
        self.assertEqual("what was there before", self.the_data_says())
        self.assertEqual(standing.ONLINE, standing.standing(directory.where("alpha")).how,
                         "the restore left the agent with no gateway holding its name")

    def test_the_gateway_it_started_holds_the_file_that_is_really_there_now(self):
        # The whole point of standing it down: a gateway that lived through the swap holds a
        # descriptor on an inode nothing can reach, and the name it once had is free for a second
        # gateway to take. What is holding it afterwards has to be a claim on the restored file.
        by = self.a_supervisor()
        by.running("alpha")

        self.restore(by)

        with self.assertRaises(standing.Taken):
            with standing.holding(directory.where("alpha")):
                pass

    def test_a_gateway_the_owner_had_already_stopped_is_never_started_by_a_restore(self):
        # Exactly the ones that were up: the list starts empty and only a gateway this command
        # really stood down goes into it, so a restore cannot leave a machine running something
        # somebody had deliberately stopped.
        by = self.a_supervisor()
        by.running("alpha")

        code, out, err = self.restore(by)

        self.assertEqual(OK, code, err)
        self.assertNotIn("beta", out)
        self.assertEqual(standing.OFFLINE, standing.standing(directory.where("beta")).how)

    def test_a_gateway_that_would_not_stand_down_stops_the_restore_and_names_it(self):
        # A restore is one operation over the whole of `data/`, so an agent whose name could not be
        # freed is not something to report beside a success — the swap would orphan its lock anyway.
        by = self.a_supervisor(bootout=support.ran(1, err="launchd said no"))
        by.running("alpha")

        code, _out, err = self.restore(by)

        self.assertEqual(FAILED, code)
        self.assertIn("the gateway for alpha would not stand down", err)
        self.assertIn("rundesk gateways stop alpha", err)
        self.assertIn("nothing was restored", err)
        self.assertEqual("changed since the copy", self.the_data_says())

    def test_what_the_seam_says_about_a_gateway_that_would_not_come_back_is_what_is_printed(self):
        # A gateway that was up and is now down is not a detail for a summary: the restore worked
        # and the machine was left in a state nobody asked for, so it ends non-zero saying both.
        by = self.a_supervisor(bootstrap=support.ran(1, err="launchd said no"))
        by.running("alpha")

        code, _out, err = self.restore(by)

        self.assertEqual(FAILED, code)
        self.assertIn("could not be started again", err)
        self.assertIn("rundesk gateways start alpha", err)
        self.assertEqual("what was there before", self.the_data_says(),
                         "the restore itself is reported as not having happened")


class TheGatewaysAnUpdateCycles(WithGatewaysThatReallyStartAndStop):
    """`update.settle` carrying an agent whose gateway is up, with nothing handed in to do it.

    **`settle` and not `cmd_update`, because that is where the seam is resolved and why.** The
    settling is done by the release that has just landed, in an interpreter of its own — so the
    process somebody typed `rundesk update` into has a process boundary between it and this work,
    and cannot hand an object across one. What it resolves is replaced instead, which is the same
    attribute the harness replaces with something that raises.

    A gateway holding an agent's records open while a step rewrites them is the `database is locked`
    failure, and this used to be an agent **named and not carried** with the update ending non-zero.
    """

    def setUp(self):
        super().setUp()
        self.steps = self.home / "agent-steps"
        self.steps.mkdir(parents=True, exist_ok=True)
        # **Every real step, not the first of them.** The agents above were made before this patch
        # took effect, so their `migrations` rows name every step this release ships — and a fake
        # directory holding only `0001` makes each of them read as carried *ahead* of the product,
        # which is a refusal rather than the carry these cases are about. Copied wholesale so that
        # the next real step to land does not break this suite the way `0002` did.
        for step in agent_migration.STEPS.glob("[0-9]*.py"):
            shutil.copy2(step, self.steps)
        stepping = mock.patch.object(agent_migration, "STEPS", self.steps)
        stepping.start()
        self.addCleanup(stepping.stop)
        # One more step than either agent has run, so both have something waiting and neither is
        # left alone as an agent already on this release would be. Numbered above every real one,
        # because a step below an agent's high-water mark is refused as back-filled.
        (self.steps / "9999_x.py").write_text(AN_AGENT_STEP, encoding="utf-8")

    def settling(self, by):
        """Settle this install the way the release that just landed does, and say what happened."""
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), \
                self.plists_in_the_scratch_root(), self.the_supervisor_it_finds(by):
            code = the_update.settle()
        return code, out.getvalue(), err.getvalue()

    def carried(self, name: str) -> bool:
        return (paths.agents() / name / "carried").exists()

    def test_an_agent_with_a_gateway_up_is_carried_rather_than_named_and_left(self):
        by = self.a_supervisor()
        by.running("alpha")

        code, out, err = self.settling(by)

        self.assertEqual(OK, code, err)
        self.assertTrue(self.carried("alpha"), "the agent whose gateway was up was never carried")
        self.assertIn("stood the gateway for alpha down", out)
        self.assertIn("started the gateway for alpha again", out)
        self.assertEqual(standing.ONLINE, standing.standing(directory.where("alpha")).how)

    def test_a_gateway_the_owner_had_already_stopped_is_never_started_by_an_update(self):
        by = self.a_supervisor()
        by.running("alpha")

        code, out, err = self.settling(by)

        self.assertEqual(OK, code, err)
        self.assertTrue(self.carried("beta"))
        self.assertNotIn("gateway for beta", out)
        self.assertEqual(standing.OFFLINE, standing.standing(directory.where("beta")).how)

    def test_a_gateway_that_would_not_stand_down_leaves_that_agent_named_and_not_carried(self):
        # The refusal that is still right: carrying under a live writer is the failure this exists
        # to prevent, and the agent beside it is carried anyway.
        by = self.a_supervisor(bootout=support.ran(1, err="launchd said no"))
        by.running("alpha")

        code, _out, err = self.settling(by)

        self.assertEqual(FAILED, code)
        self.assertIn("its gateway would not stand down", err)
        self.assertIn("rundesk gateways stop alpha", err)
        self.assertFalse(self.carried("alpha"), "an agent was carried under a live gateway")
        self.assertTrue(self.carried("beta"), "one agent's gateway stopped another being carried")


if __name__ == "__main__":
    unittest.main()
