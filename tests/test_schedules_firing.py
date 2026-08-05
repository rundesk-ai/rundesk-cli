"""Starting what a schedule names, keeping hold of it, and saying what became of it.

**Real programs, real locks, real process groups.** A stand-in for a child would prove nothing about
the one property this whole design rests on — that a firing killed outright never looks like one
still running — because that property belongs to the kernel and not to this code. So every case here
starts something with `/bin/sh`, takes a real `flock` where it needs one, and takes away whatever it
started however the case ended.

Nothing here goes near launchd or a gateway process. `firing` is handed the directory to log into,
which is exactly what lets these cases be a few seconds of real work rather than a supervisor.

Run directly: `python3 tests/test_schedules_firing.py`
"""

import contextlib
import datetime
import fcntl
import os
import shutil
import signal
import unittest
from pathlib import Path
from unittest import mock

import support
from rundesk.agents import directory, records
from rundesk.schedules import due, firing, kept
from rundesk.utils import logs, programs

#: How long a case will wait for a child to do something before calling it a failure. Generous,
#: because it is a real fork and exec on a machine that may be loaded, and a ceiling rather than a
#: sleep so an ordinary run is through in hundredths.
PATIENCE = 20.0

#: A program that finishes at once, one that fails, and one that does not stop by itself.
SAYS_SOMETHING = "/bin/echo"
FAILS = "/bin/sh -c 'echo it went wrong >&2; exit 3'"
NEVER_ENDS = "/bin/sh -c 'while true; do sleep 0.05; done'"


class Firing(support.Isolated):
    """One agent with real records, and whatever its schedules started."""

    def setUp(self):
        super().setUp()
        self.agent = "cole"
        directory.made(self.agent, "claude")
        self.where = directory.where(self.agent) / directory.LOGS
        self.started = []
        self.addCleanup(self.take_away_whatever_this_case_started)

    def take_away_whatever_this_case_started(self):
        """End only the process ids this case itself started, and never a group it read somewhere.

        Registered at acquisition rather than left to a `tearDown`, which does not run when `setUp`
        itself fails — and a case that failed while starting something is exactly the one that would
        leave a `while true` loop behind on somebody's machine.

        Through `programs.stop` rather than a raw `killpg`, because that is also what *settles* the
        child: a signal alone leaves the standard library holding a wrapper that still believes it
        owns a running program, which surfaces as a `ResourceWarning` flood at interpreter exit and
        would drown the one line a reader of this suite is looking for.
        """
        for pid in self.started:
            with contextlib.suppress(OSError):
                programs.stop(pid, gently_for=0.2, firmly_for=2.0)

    def given(self, name, command=SAYS_SOMETHING + " ran", cron="* * * * *", **also):
        kept.added(self.agent, name, dict({"cron": cron, "command": command}, **also))
        return name

    def look(self, at=None, watching=None, **also):
        """One look at the clock, at a moment of the case's choosing."""
        watching = watching if watching is not None else firing.Watching({}, {})
        after = firing.looked(self.agent, self.where, watching,
                              moment=at or datetime.datetime(2026, 8, 5, 9, 0), **also)
        self.started.extend(one.pid for one in after.running.values() if one.pid)
        return after

    def said(self):
        """Every line in this agent's log today, as one string."""
        found = logs.kept(self.where)
        return "".join(one.read_text(encoding="utf-8") for one in found)

    def outcome_of(self, name):
        return kept.one(self.agent, name)["last_outcome"]

    def waited_for_an_outcome(self, name, wanted=None):
        """Wait for a firing to be written down, looking again each time to give it the chance."""
        def landed():
            self.look(watching=self.watching)
            found = self.outcome_of(name)
            return found is not None and (wanted is None or found == wanted)
        return support.waited_until(landed, PATIENCE)


class WhatIsDueIsStarted(Firing):

    def test_a_schedule_that_is_due_starts_what_it_names(self):
        self.given("tick")
        after = self.look()
        self.assertIn("tick", after.running)
        self.assertTrue(after.running["tick"].mine)
        self.assertIsNotNone(after.running["tick"].pid)

    def test_only_what_is_due_is_started(self):
        self.given("tick", cron="* * * * *")
        self.given("nine", cron="0 9 * * *")
        after = self.look(at=datetime.datetime(2026, 8, 5, 10, 30))
        self.assertEqual(["tick"], sorted(after.running))

    def test_a_schedule_that_is_off_is_never_started(self):
        self.given("tick", enabled=0)
        self.assertEqual({}, self.look().running)

    def test_the_same_minute_is_started_once_however_often_the_clock_is_examined(self):
        # The guarantee the whole durable claim exists for. Looked at three times inside one minute,
        # with the state thrown away between looks the way a restart throws it away.
        self.given("tick")
        at = datetime.datetime(2026, 8, 5, 9, 0)
        first = self.look(at=at)
        self.assertEqual(["tick"], sorted(first.running))
        for _again in range(2):
            self.assertEqual({}, self.look(at=at).running,
                             "a fresh gateway started the same minute again")

    def test_a_minute_later_is_a_new_occurrence(self):
        self.given("tick")
        self.look(at=datetime.datetime(2026, 8, 5, 9, 0))
        after = self.look(at=datetime.datetime(2026, 8, 5, 9, 1))
        self.assertEqual(["tick"], sorted(after.running))

    def test_that_a_schedule_fired_is_written_down_before_it_is_run(self):
        self.given("tick")
        self.look()
        self.assertEqual("2026-08-05 09:00", kept.one(self.agent, "tick")["last_fired_for"])

    def test_a_firing_that_could_not_be_written_down_starts_nothing(self):
        # Better not to run than to run twice: work that visibly happened with nothing recording it
        # repeats on the way back up, which is what writing it first is for.
        #
        # **The records are made to fail at the claim and nowhere else.** Corrupting the database
        # instead reads well and proves nothing: `looked` reads the rows *before* it claims
        # anything, so it would refuse at that first step and this case would go green with the
        # guard under test never having run. Measured by breaking the guard and watching this stay
        # green, which is how it was found.
        self.given("tick")
        with mock.patch.object(kept, "claimed", side_effect=OSError("the disk filled")):
            after = self.look()
        self.assertEqual({}, after.running)
        self.assertFalse(firing.record_of(self.agent, "tick").exists(),
                         "a firing was written down after all")
        self.assertIn("could not have its firing written down", self.said())

    def test_the_environment_a_started_program_gets_names_where_this_install_is(self):
        # A schedule's program may itself be `rundesk`, and it has to read the same install the
        # gateway starting it reads. The old build left one variable out of the job and the command
        # line and the gateway stopped agreeing about what a schedule was.
        given = firing.the_environment()
        self.assertEqual(str(self.home), given["RUNDESK_HOME"])
        self.assertNotIn("RUNDESK_APP", given)

    def test_what_a_schedule_names_is_never_handed_to_a_shell(self):
        self.assertEqual(["/bin/echo", "a b", "c"], firing.argv_of("/bin/echo 'a b' c"))
        self.assertEqual([], firing.argv_of("/bin/echo 'unbalanced"))


class WhatBecameOfIt(Firing):
    """The three words, and the exit code behind two of them."""

    def setUp(self):
        super().setUp()
        self.watching = firing.Watching({}, {})

    def test_a_program_that_finished_happily_is_completed(self):
        self.given("tick")
        self.watching = self.look(watching=self.watching)
        self.assertTrue(self.waited_for_an_outcome("tick"), self.said())
        self.assertEqual(kept.COMPLETED, self.outcome_of("tick"))

    def test_a_program_that_disagreed_is_failed_with_its_exit_code(self):
        self.given("bad", command=FAILS)
        self.watching = self.look(watching=self.watching)
        self.assertTrue(self.waited_for_an_outcome("bad"), self.said())
        self.assertEqual(kept.FAILED, self.outcome_of("bad"))
        self.assertIn("failed with exit 3", self.said())

    def test_a_program_that_was_never_on_the_machine_is_not_counted_as_a_failing_exit(self):
        # It never started, so there is no exit code — and reporting one would say it ran and
        # disagreed, which is a different fact about the machine leading somewhere else.
        self.given("gone", command="/no/such/program --please")
        self.look()
        self.assertEqual(kept.FAILED, self.outcome_of("gone"))
        said = self.said()
        self.assertIn("did not start", said)
        self.assertNotIn("exit", said)

    def test_when_a_firing_is_over_its_record_is_taken_away(self):
        self.given("tick")
        self.watching = self.look(watching=self.watching)
        self.assertTrue(self.waited_for_an_outcome("tick"), self.said())
        self.assertFalse(firing.record_of(self.agent, "tick").exists())

    def test_the_outcome_survives_being_read_back(self):
        self.given("tick")
        self.watching = self.look(watching=self.watching)
        self.assertTrue(self.waited_for_an_outcome("tick"), self.said())
        self.assertIsNotNone(kept.one(self.agent, "tick")["last_run_at"])


class WhatTheLogSays(Firing):
    """It ran, it finished, or it failed and why — the three lines somebody investigates with."""

    def setUp(self):
        super().setUp()
        self.watching = firing.Watching({}, {})

    def test_a_firing_says_it_is_due_and_says_what_it_started(self):
        self.given("tick")
        self.look()
        said = self.said()
        self.assertIn("schedule tick is due for 2026-08-05 09:00", said)
        self.assertIn("schedule tick started as pid", said)
        self.assertIn("/bin/echo ran", said)

    def test_a_firing_that_finished_says_so_and_says_how_long_as_an_upper_bound(self):
        # **Under, never exactly.** A gateway notices a child finished on the beat *after* it did,
        # so the figure is the age of the firing when it was noticed rather than how long the work
        # took. Measured on a real run: an `/bin/echo` taking milliseconds was reported as having
        # taken fifteen seconds, and somebody sizing a backup window would read that and believe it.
        self.given("tick")
        self.watching = self.look(watching=self.watching)
        self.assertTrue(self.waited_for_an_outcome("tick"), self.said())
        self.assertRegex(self.said(), r"schedule tick completed in under \d")

    def test_a_firing_that_failed_says_why_and_carries_what_the_program_wrote(self):
        # The whole reason a person opens this file. A failure with no output beside it is a failure
        # they have to reproduce by hand before they can start.
        self.given("bad", command=FAILS)
        self.watching = self.look(watching=self.watching)
        self.assertTrue(self.waited_for_an_outcome("bad"), self.said())
        said = self.said()
        self.assertIn("schedule bad failed with exit 3", said)
        self.assertIn("it went wrong", said)

    def test_what_a_run_wrote_is_this_runs_and_not_the_whole_history_of_the_file(self):
        # Read from where this run began, because the output file is appended to across every run:
        # reading from the top would put last week's output under today's failure.
        output = firing.output_of(self.agent, "bad")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text("something from last week\n", encoding="utf-8")
        self.given("bad", command=FAILS)
        self.watching = self.look(watching=self.watching)
        self.assertTrue(self.waited_for_an_outcome("bad"), self.said())
        self.assertNotIn("last week", self.said())

    def test_a_schedule_nobody_can_understand_is_said_and_the_others_still_run(self):
        self.given("good")
        directory.records(self.agent)  # the bad row goes in under the CHECKs, so straight to SQL
        with records.writing(directory.records(self.agent)) as conn:
            conn.execute("UPDATE schedules SET cron = 'not a cron' WHERE name = 'good'")
            conn.execute("INSERT INTO schedules (name, cron, command, created_at) "
                         "VALUES ('fine', '* * * * *', '/bin/echo hi', '2026-01-01T00:00:00Z')")
        after = self.look()
        self.assertIn("schedule good cannot be understood", self.said())
        self.assertEqual(["fine"], sorted(after.running))

    def test_a_schedule_nobody_can_understand_is_said_once_and_not_every_beat(self):
        # A bad cron does not fix itself, so a line every fifteen seconds is a log that grows without
        # bound in the act of reporting something that is not going to change.
        self.given("good")
        with records.writing(directory.records(self.agent)) as conn:
            conn.execute("UPDATE schedules SET cron = 'not a cron' WHERE name = 'good'")
        watching = self.look()
        watching = self.look(watching=watching)
        watching = self.look(watching=watching)
        self.assertEqual(1, self.said().count("schedule good cannot be understood"))

    def test_records_nobody_can_read_are_said_once_and_nothing_runs(self):
        self.given("tick")
        directory.records(self.agent).write_bytes(b"this is not a database")
        watching = self.look()
        watching = self.look(watching=watching)
        self.assertEqual({}, watching.running)
        self.assertEqual(1, self.said().count("no schedule can run"))

    def test_a_gateway_whose_agent_was_taken_away_does_not_put_the_directory_back(self):
        # `logs.note` makes the directory it writes into, so complaining that an agent is gone would
        # leave something that looks like a half-made agent standing where it used to be.
        self.given("tick")
        at = directory.where(self.agent)
        shutil.rmtree(at)
        self.look()
        self.assertFalse(at.exists())


class OneAtATime(Firing):
    """A schedule does not begin again while what it started last time is still running."""

    def setUp(self):
        super().setUp()
        self.watching = firing.Watching({}, {})

    def test_a_second_firing_is_refused_while_the_first_is_still_running(self):
        self.given("slow", command=NEVER_ENDS)
        first = self.look(at=datetime.datetime(2026, 8, 5, 9, 0))
        self.assertEqual(["slow"], sorted(first.running))
        self.assertTrue(support.waited_until(
            lambda: firing.still_running(self.agent, "slow"), PATIENCE), self.said())
        # A whole new gateway, remembering nothing — which is what makes the lock the guard rather
        # than anything held in this process.
        after = self.look(at=datetime.datetime(2026, 8, 5, 9, 1))
        self.assertEqual({}, after.running)

    def test_a_firing_refused_for_still_running_is_reported_rather_than_passed_over(self):
        # A schedule quietly skipping every time because the last run never ended looks exactly like
        # one that is working.
        self.given("slow", command=NEVER_ENDS)
        self.look(at=datetime.datetime(2026, 8, 5, 9, 0))
        self.assertTrue(support.waited_until(
            lambda: firing.still_running(self.agent, "slow"), PATIENCE), self.said())
        self.look(at=datetime.datetime(2026, 8, 5, 9, 1))
        self.assertIn("skipped: what it started last time is still running", self.said())

    def test_a_refused_firing_still_claims_its_minute_so_it_is_said_once_not_every_beat(self):
        self.given("slow", command=NEVER_ENDS)
        self.look(at=datetime.datetime(2026, 8, 5, 9, 0))
        self.assertTrue(support.waited_until(
            lambda: firing.still_running(self.agent, "slow"), PATIENCE), self.said())
        at = datetime.datetime(2026, 8, 5, 9, 1)
        self.look(at=at)
        self.look(at=at)
        self.assertEqual(1, self.said().count("skipped: what it started last time"))

    def test_the_lock_a_firing_holds_is_the_childs_and_is_dropped_when_the_child_tree_ends(self):
        # The property everything rests on, and it belongs to the kernel: the descriptor is passed
        # to the child, so the claim lives exactly as long as the work and is released however it
        # ends — including a kill that lets no tidying code run anywhere.
        self.given("slow", command=NEVER_ENDS)
        after = self.look()
        pid = after.running["slow"].pid
        self.assertTrue(support.waited_until(
            lambda: firing.still_running(self.agent, "slow"), PATIENCE))
        os.killpg(os.getpgid(pid), signal.SIGKILL)
        self.assertTrue(support.waited_until(
            lambda: not firing.still_running(self.agent, "slow"), PATIENCE),
            "the lock outlived the child tree that was holding it")

    def test_a_schedule_that_has_never_fired_is_not_shown_as_running(self):
        self.given("tick")
        self.assertFalse(firing.still_running(self.agent, "tick"))
        self.assertFalse(firing.lock_of(self.agent, "tick").exists(),
                         "asking whether a firing is running created its lock file")


class ComingUpAfterAGatewayThatIsGone(Firing):
    """What a previous gateway left, and the only honest word for it."""

    def test_a_firing_whose_gateway_is_gone_and_whose_work_is_over_is_stopped(self):
        self.given("tick")
        firing.record_of(self.agent, "tick").parent.mkdir(parents=True, exist_ok=True)
        firing.record_of(self.agent, "tick").write_text(
            '{"schedule": "tick", "fired_for": "2026-08-05 09:00", "from_byte": 0, "pid": 999999}',
            encoding="utf-8")
        watching = firing.settled(self.agent, self.where)
        self.assertEqual({}, watching.running)
        self.assertEqual(kept.STOPPED, self.outcome_of("tick"))
        self.assertIn("was interrupted: the gateway that started it is gone", self.said())
        self.assertFalse(firing.record_of(self.agent, "tick").exists())

    def test_a_firing_still_running_under_a_gone_gateway_is_adopted_and_not_started_again(self):
        self.given("slow", command=NEVER_ENDS)
        started = self.look()                          # the "previous" gateway starts it
        self.assertTrue(support.waited_until(
            lambda: firing.still_running(self.agent, "slow"), PATIENCE), self.said())
        del started

        watching = firing.settled(self.agent, self.where)     # a fresh one comes up
        self.assertEqual(["slow"], sorted(watching.running))
        self.assertFalse(watching.running["slow"].mine,
                         "a child of a gone gateway was claimed as this one's to reap")
        self.assertIn("was already running when this gateway came up", self.said())
        after = self.look(at=datetime.datetime(2026, 8, 5, 9, 1), watching=watching)
        self.assertNotIn("started as pid", self.said().split("already running")[1])
        self.assertEqual(["slow"], sorted(after.running))

    def test_an_adopted_firing_that_ends_is_stopped_because_nobody_can_say_what_it_came_to(self):
        # Not a failure. A status belongs to the parent, and work that may well have finished
        # perfectly is never written down as having failed.
        self.given("slow", command=NEVER_ENDS)
        started = self.look()
        pid = started.running["slow"].pid
        self.assertTrue(support.waited_until(
            lambda: firing.still_running(self.agent, "slow"), PATIENCE))
        watching = firing.settled(self.agent, self.where)
        os.killpg(os.getpgid(pid), signal.SIGKILL)
        self.assertTrue(support.waited_until(
            lambda: not firing.still_running(self.agent, "slow"), PATIENCE))
        watching = self.look(at=datetime.datetime(2026, 8, 5, 9, 30), watching=watching)
        self.assertEqual(kept.STOPPED, self.outcome_of("slow"))
        self.assertIn("nobody can say what it came to", self.said())

    def test_coming_up_with_nothing_left_behind_is_not_a_failure(self):
        self.assertEqual(firing.Watching({}, {}), firing.settled(self.agent, self.where))


class GoingDown(Firing):
    """The stop has to fit inside what the job gives it."""

    def test_a_stop_takes_the_child_tree_with_it_and_says_so(self):
        self.given("slow", command=NEVER_ENDS)
        watching = self.look()
        pid = watching.running["slow"].pid
        self.assertTrue(support.waited_until(
            lambda: firing.still_running(self.agent, "slow"), PATIENCE))

        firing.stopping(self.agent, self.where, watching, within=10.0)

        self.assertFalse(programs.alive(pid))
        self.assertEqual({}, watching.running)
        self.assertEqual(kept.STOPPED, self.outcome_of("slow"))
        self.assertIn("was stopped with this gateway", self.said())

    def test_work_that_finished_before_the_shutdown_is_reaped_rather_than_signalled(self):
        # Two things, and the second is why this is not a nicety. It gets its real outcome instead of
        # `stopped`, which would be a worse answer than the one available. And nothing signals a
        # process that has gone: a pid whose leader was collected no longer resolves to a group,
        # `programs.stop` then treats the pid *as* the group id, and process ids are reused — so a
        # gateway going down was seen asking the kernel to end a group that had nothing to do with
        # it. It was refused, which is luck rather than design.
        self.given("tick")
        watching = self.look()
        self.assertTrue(support.waited_until(
            lambda: not firing.still_running(self.agent, "tick"), PATIENCE))

        firing.stopping(self.agent, self.where, watching, within=10.0)

        self.assertEqual(kept.COMPLETED, self.outcome_of("tick"))
        self.assertEqual({}, watching.running)
        self.assertNotIn("was stopped with this gateway", self.said())
        self.assertNotIn("would not stop", self.said())

    def test_a_stop_with_nothing_running_does_nothing_at_all(self):
        watching = firing.Watching({}, {})
        self.assertEqual(watching, firing.stopping(self.agent, self.where, watching, within=10.0))

    def test_a_firing_this_gateway_did_not_start_is_left_to_finish(self):
        # Its process group was never ours to signal, and ending a stranger's program on the way out
        # is worse than leaving it running.
        self.given("slow", command=NEVER_ENDS)
        started = self.look()
        pid = started.running["slow"].pid
        self.assertTrue(support.waited_until(
            lambda: firing.still_running(self.agent, "slow"), PATIENCE))
        adopted = firing.settled(self.agent, self.where)

        firing.stopping(self.agent, self.where, adopted, within=10.0)

        self.assertTrue(programs.alive(pid), "a gateway stopped a child that was not its own")


class TheKindNoCommandCanSpell(Firing):
    """A schedule that asks an agent, which this release records and cannot run."""

    def a_prompt_schedule(self, name="review"):
        kept.added(self.agent, name, {"cron": "* * * * *", "agent_prompt": "review the queue",
                                      "agent_provider": "claude"})
        return name

    def test_the_clock_decides_it_exactly_as_it_decides_any_other(self):
        one = due.understood(kept.one(self.agent, self.a_prompt_schedule()))
        self.assertTrue(due.due_at(one, datetime.datetime(2026, 8, 5, 9, 0)))

    def test_it_is_refused_in_one_line_and_written_down_as_failed(self):
        # Never silently passed over: a schedule that is skipped every time looks exactly like one
        # that is working, and this one will never work until there is a provider process.
        self.a_prompt_schedule()
        after = self.look()
        self.assertEqual({}, after.running)
        self.assertEqual(kept.FAILED, self.outcome_of("review"))
        self.assertIn("nothing in this release runs a provider", self.said())

    def test_it_claims_its_minute_so_the_refusal_is_said_once_per_occurrence(self):
        self.a_prompt_schedule()
        at = datetime.datetime(2026, 8, 5, 9, 0)
        self.look(at=at)
        self.look(at=at)
        self.assertEqual(1, self.said().count("nothing in this release runs a provider"))

    def test_a_runner_handed_in_is_used_and_nothing_else_changes(self):
        # The seam the provider process arrives at, driven by a stand-in of exactly its shape. When
        # something can start a turn, this is the whole of what has to be written.
        self.a_prompt_schedule()

        class ATurn:
            def __init__(self):
                self.asked = []

            def start(self, one, agent, holding):
                self.asked.append((one.name, one.prompt, agent))
                return programs.start(["/bin/echo", "a turn"],
                                      log=firing.output_of(agent, one.name),
                                      holding=(holding,))

        runner = ATurn()
        after = self.look(asking=runner)
        self.assertEqual([("review", "review the queue", self.agent)], runner.asked)
        self.assertEqual(["review"], sorted(after.running))

    def test_running_one_by_hand_is_refused_in_words_rather_than_by_a_traceback(self):
        self.a_prompt_schedule()
        with self.assertRaises(firing.NoRunner):
            firing.by_hand(self.agent, "review", waiting=PATIENCE)


class RunningOneByHand(Firing):
    """A person checking their own work, which must not be how a schedule stops happening."""

    def test_it_runs_and_hands_back_everything_the_program_said(self):
        self.given("tick", command="/bin/echo hello there")
        ran = firing.by_hand(self.agent, "tick", waiting=PATIENCE, where=self.where)
        self.assertIsNone(ran.trouble)
        self.assertEqual(0, ran.code)
        self.assertIn("hello there", ran.out)

    def test_it_leaves_the_minute_it_next_falls_due_alone(self):
        # Testing a schedule must not be how you stop it from happening.
        self.given("tick")
        firing.by_hand(self.agent, "tick", waiting=PATIENCE, where=self.where)
        self.assertIsNone(kept.one(self.agent, "tick")["last_fired_for"])

    def test_a_single_moment_is_never_used_up_by_running_one_by_hand(self):
        kept.added(self.agent, "once", {"run_at": "2026-08-05T09:00", "command": SAYS_SOMETHING})
        firing.by_hand(self.agent, "once", waiting=PATIENCE, where=self.where)
        one = due.understood(kept.one(self.agent, "once"))
        self.assertFalse(one.used)
        self.assertTrue(due.due_at(one, datetime.datetime(2026, 8, 5, 9, 0)))

    def test_it_writes_down_what_became_of_it_because_it_did_run(self):
        self.given("bad", command=FAILS)
        firing.by_hand(self.agent, "bad", waiting=PATIENCE, where=self.where)
        self.assertEqual(kept.FAILED, self.outcome_of("bad"))
        self.assertIn("run by hand failed", self.said())

    def test_it_cannot_start_a_second_copy_of_work_a_gateway_is_already_doing(self):
        # Which the build this replaces could not prevent: its guard lived inside the gateway
        # process, so a terminal knew nothing about it.
        self.given("slow", command=NEVER_ENDS)
        self.look()
        self.assertTrue(support.waited_until(
            lambda: firing.still_running(self.agent, "slow"), PATIENCE))
        with self.assertRaises(firing.Occupied):
            firing.by_hand(self.agent, "slow", waiting=PATIENCE, where=self.where)

    def test_a_schedule_that_is_not_there_says_so(self):
        with self.assertRaises(records.NotThere):
            firing.by_hand(self.agent, "missing", waiting=PATIENCE)

    def test_what_it_wrote_goes_into_the_same_file_the_clocks_runs_write_to(self):
        # One place to look, whether the clock started it or a person did.
        self.given("tick", command="/bin/echo by hand")
        firing.by_hand(self.agent, "tick", waiting=PATIENCE, where=self.where)
        self.assertIn("by hand",
                      firing.output_of(self.agent, "tick").read_text(encoding="utf-8"))


class WhatCollectingAChildAnswers(support.Isolated):
    """`programs.collected` — three answers, and the third is not a failure."""

    def test_a_child_that_is_still_running_is_not_over(self):
        pid = programs.start(["/bin/sh", "-c", "sleep 5"], log=self.home / "out")
        self.addCleanup(lambda: programs.stop(pid, gently_for=1.0))
        self.assertEqual(programs.Collected(False, None), programs.collected(pid))

    def test_a_child_that_finished_answers_with_its_exit_code(self):
        pid = programs.start(["/bin/sh", "-c", "exit 7"], log=self.home / "out")
        self.assertTrue(support.waited_until(
            lambda: programs.collected(pid).over, 10.0))

    def test_a_process_that_was_never_ours_is_over_with_nothing_to_read(self):
        # Not a failure: a status belongs to the parent, and this one belongs to somebody else.
        self.assertEqual(programs.Collected(True, None), programs.collected(os.getppid()))

    def test_a_child_started_while_a_signal_is_blocked_can_still_be_stopped(self):
        # **Measured, and it cost a working stop.** `firing` holds off `SIGTERM` for the few
        # instructions between starting a child and writing down that it started one — and a blocked
        # signal *mask* is inherited across `fork` and across `exec`, unlike a disposition. So every
        # child started in that moment was a program nothing could terminate: a `/bin/sh` survived
        # `SIGTERM`, and a gateway stopping its work waited out its whole patience before resorting
        # to `SIGKILL`. `subprocess`'s own `restore_signals` does not cover this.
        before = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGTERM})
        try:
            pid = programs.start(["/bin/sh", "-c", "while true; do sleep 0.05; done"],
                                 log=self.home / "out")
        finally:
            signal.pthread_sigmask(signal.SIG_SETMASK, before)
        self.addCleanup(lambda: programs.stop(pid, gently_for=0.2, firmly_for=2.0))

        os.killpg(os.getpgid(pid), signal.SIGTERM)

        self.assertTrue(support.waited_until(lambda: not programs.alive(pid), 5.0),
                        "the child inherited a blocked SIGTERM and cannot be stopped politely")

    def test_a_descriptor_handed_to_a_child_keeps_a_lock_alive_for_the_childs_whole_life(self):
        # The mechanism `firing` rests on, proved on its own: the parent lets go of its copy and the
        # claim stays taken, because it belongs to the open file description and not to a process.
        lock = self.home / "held.lock"
        held = os.open(lock, os.O_CREAT | os.O_RDWR, 0o600)
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        pid = programs.start(["/bin/sh", "-c", "sleep 5"], log=self.home / "out", holding=(held,))
        self.addCleanup(lambda: programs.stop(pid, gently_for=1.0))
        os.close(held)                                   # the parent lets go; the child has not

        asked = os.open(lock, os.O_RDONLY)
        self.addCleanup(os.close, asked)
        with self.assertRaises(OSError):
            fcntl.flock(asked, fcntl.LOCK_EX | fcntl.LOCK_NB)

        programs.stop(pid, gently_for=2.0)
        self.assertTrue(support.waited_until(lambda: _takeable(lock), 10.0),
                        "the lock outlived the child tree holding it")


def _takeable(lock: Path) -> bool:
    """Whether nobody is holding this lock, asked without keeping it."""
    asked = os.open(lock, os.O_RDONLY)
    try:
        fcntl.flock(asked, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False
    finally:
        os.close(asked)


if __name__ == "__main__":
    unittest.main()
