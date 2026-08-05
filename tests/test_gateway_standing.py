"""Whether a gateway is online, and the one case the whole design exists for.

**A gateway that was killed outright must never look alive.** Everything else here follows from
that: the record is still whole on disk after a `SIGKILL` — nothing got to tidy it up — and the
answer is still `offline`, because the answer was never the record's to give.

The cases that matter are driven with real child processes rather than with anything standing in for
one. The guarantee is about what the *kernel* does when a process ends, and nothing that pretends to
be a process can be `SIGKILL`ed.

Every signal here is sent to a pid this suite started itself. Never a process group, and never `0`
or `1`: the build this replaces recorded `killpg` at group `0` — the caller's own group — taking out
the test run and the shell around it, and group `1` on Linux meaning every process the user may
signal, which ended the machine running it.

Run directly: python3 tests/test_gateway_standing.py
"""

import datetime
import fcntl
import json
import os
import signal
import sys
import time
import unittest

import support
from rundesk.gateways import standing
from rundesk.utils import files, programs

#: A gateway of the shape a real one will have: it claims the agent's name, records itself, says it
#: is up, and then holds the name until it is told to let go — or until something takes it away.
#:
#: It has a ceiling of its own as well as being stopped in a cleanup. A child that can outlive its
#: suite is a child that is still holding a lock when the next run starts.
A_GATEWAY = """
import sys, time
sys.path.insert(0, {src!r})
from pathlib import Path
from rundesk.gateways import standing

agent = Path({agent!r})
with standing.holding(agent):
    standing.write_record(agent, "one", "9.9.9")
    Path({ready!r}).write_text("up")
    ceiling = time.monotonic() + 60
    while time.monotonic() < ceiling and not Path({go!r}).exists():
        time.sleep(0.02)
"""


class WithAnAgentDirectory(support.Isolated):
    """A scratch agent directory, and the means to put a real gateway in it."""

    #: How long these cases wait for a real gateway before calling it a failure. Longer than a case
    #: waiting on a bare `python3 -c` needs, because this child imports the product before it can
    #: claim anything, and shorter than the child's own sixty-second ceiling so the suite is what
    #: gives up first.
    PATIENCE = 10.0

    def setUp(self):
        super().setUp()
        self.agent = self.home / "agents" / "one"
        self.agent.mkdir(parents=True)
        self.ready = self.home / "it-is-up"
        self.go = self.home / "let-go"
        self.said = self.home / "what-the-child-said.log"
        self.started = []
        self.addCleanup(self.stop_everything)

    def stop_everything(self):
        """Stop only what this case started. Never a group, and never a pid nobody wrote down."""
        for pid in self.started:
            programs.stop(pid, 0.5, 1.0)

    def a_running_gateway(self) -> int:
        """A real child holding this agent's name, proven up before the case goes on."""
        body = A_GATEWAY.format(
            src=str(support.CHECKOUT / "src"), agent=str(self.agent),
            ready=str(self.ready), go=str(self.go))
        pid = programs.start([sys.executable, "-c", body], self.said)
        self.started.append(pid)
        self.assertTrue(
            support.waited_until(self.ready.exists, self.PATIENCE),
            f"the gateway never came up. It said: {self.what_the_child_said()}")
        return pid

    def what_the_child_said(self) -> str:
        return self.said.read_text() if self.said.exists() else "nothing"

    def record_says(self, **what) -> None:
        """Change the record under a gateway's feet, the way time and corruption do."""
        said = json.loads((self.agent / standing.RECORD).read_text())
        said.update(what)
        (self.agent / standing.RECORD).write_text(json.dumps(said))


class HoldingAnAgentsName(WithAnAgentDirectory):
    """`holding` — the claim that is also the check, because asking first leaves a gap."""

    def test_it_keeps_the_name_for_the_length_of_the_block(self):
        # The gap is the whole reason this exists: `standing()` saying offline and a caller acting
        # on it are two decisions, and a gateway can claim the name between them. An ordinary
        # `start` ended a live agent's whole process tree that way.
        with standing.holding(self.agent):
            self.assertEqual(standing.ONLINE, standing.standing(self.agent).how)

    def test_a_second_claim_is_refused_while_the_first_holds_it(self):
        with standing.holding(self.agent):
            with self.assertRaises(standing.Taken) as refused:
                with standing.holding(self.agent):
                    pass
        self.assertIn(str(self.agent), str(refused.exception))

    def test_the_name_comes_free_once_the_first_lets_go(self):
        with standing.holding(self.agent):
            pass
        with standing.holding(self.agent):
            self.assertEqual(standing.ONLINE, standing.standing(self.agent).how)

    def test_it_is_let_go_of_even_when_the_block_raised(self):
        # A gateway that fails on the way up must not leave the agent unstartable for ever.
        with self.assertRaises(RuntimeError):
            with standing.holding(self.agent):
                raise RuntimeError("the gateway fell over")
        self.assertEqual(standing.OFFLINE, standing.standing(self.agent).how)

    def test_it_never_takes_the_lock_file_away_when_it_lets_go(self):
        # A lock lives on the inode, not on the name. Unlinking hands the name away: the next claim
        # makes a fresh inode and locks that one, and two gateways then answer as one identity.
        with standing.holding(self.agent):
            pass
        self.assertTrue((self.agent / standing.LOCK).is_file(),
                        "the lock file was removed, which is how two gateways come to share a name")

    def test_it_makes_the_directory_it_locks_in(self):
        fresh = self.home / "agents" / "never-made"
        with standing.holding(fresh):
            self.assertEqual(standing.ONLINE, standing.standing(fresh).how)

    def test_a_name_a_real_gateway_holds_is_refused_to_this_one(self):
        # In another process, which is the case that matters: `flock` is per open file description,
        # so a second claim conflicts either way — but the one a start actually meets is this one.
        self.a_running_gateway()
        with self.assertRaises(standing.Taken):
            with standing.holding(self.agent):
                pass


class WhetherAGatewayIsOnline(WithAnAgentDirectory):
    """`standing` — online, offline, and the third answer that is not a quiet form of offline."""

    def test_an_agent_nothing_has_ever_run_for_is_offline(self):
        how = standing.standing(self.agent)
        self.assertEqual(standing.OFFLINE, how.how)
        self.assertIsNone(how.pid)
        self.assertIsNone(how.stale)

    def test_asking_the_question_does_not_write_anything(self):
        # A question that writes is a question that fails on a read-only disk — and leaving a lock
        # file in an agent's directory because somebody ran `status` is state nobody asked for.
        standing.standing(self.agent)
        self.assertEqual([], list(self.agent.iterdir()))

    def test_a_real_gateway_reads_as_online_with_its_own_pid(self):
        pid = self.a_running_gateway()
        how = standing.standing(self.agent)
        self.assertEqual(standing.ONLINE, how.how)
        self.assertEqual(pid, how.pid)
        self.assertFalse(how.stale, "a gateway that has just started has not missed a beat")

    def test_a_gateway_that_finished_normally_is_offline(self):
        pid = self.a_running_gateway()
        self.go.write_text("let go")
        self.assertTrue(support.waited_until(lambda: not programs.alive(pid), self.PATIENCE),
                        f"it never exited. It said: {self.what_the_child_said()}")
        self.assertEqual(standing.OFFLINE, standing.standing(self.agent).how)

    def test_a_gateway_killed_outright_never_looks_alive(self):
        # The headline. Nothing gets to run on `SIGKILL`: no handler, no `finally`, no tidying up.
        # The record it wrote is still whole on disk — and the answer is still offline, because the
        # answer was never the record's to give. A pid file would say this agent is up, and its pid
        # is a number that now belongs to something else.
        pid = self.a_running_gateway()
        os.kill(pid, signal.SIGKILL)                     # a pid this case started, never a group
        self.assertTrue(support.waited_until(lambda: not programs.alive(pid), self.PATIENCE))

        self.assertTrue((self.agent / standing.RECORD).is_file(),
                        "the record was cleaned up, so this proves nothing")
        how = standing.standing(self.agent)
        self.assertEqual(standing.OFFLINE, how.how, "a killed gateway looked alive")
        self.assertIsNone(how.pid, "it handed back a pid off a dead gateway's record")

    def test_a_lock_that_cannot_be_opened_is_not_an_offline_one(self):
        # Unreadable is not a quiet form of not-running. Reported as offline, this is how a second
        # gateway gets started beside a first one that is working perfectly well.
        support.not_as_root(self)
        self.addCleanup(self.agent.chmod, 0o700)
        self.agent.chmod(0o000)

        how = standing.standing(self.agent)
        self.assertEqual(standing.CANNOT_TELL, how.how)
        self.assertIn(standing.LOCK, how.why, "it did not say which file it could not open")
        self.assertIsNone(how.pid)

    def test_two_people_asking_at_once_do_not_read_each_other_as_a_gateway(self):
        # The question is asked with a *shared* lock. An exclusive probe conflicts with another
        # probe, so two `status` commands at the same moment would each read the other as the
        # gateway and report an agent that is not running as online.
        (self.agent / standing.LOCK).touch()
        somebody_else = os.open(self.agent / standing.LOCK, os.O_RDONLY)
        self.addCleanup(os.close, somebody_else)
        fcntl.flock(somebody_else, fcntl.LOCK_SH | fcntl.LOCK_NB)

        self.assertEqual(standing.OFFLINE, standing.standing(self.agent).how)

    def test_nothing_in_the_record_is_trusted_while_nobody_holds_the_lock(self):
        # The record outlives its gateway by design. A pid read off one whose process is gone is a
        # pid that now belongs to something else, and signalling it kills a stranger's program.
        files.write_json(self.agent / standing.RECORD,
                         {"name": "one", "pid": 424242, "since_boot": time.monotonic()})
        how = standing.standing(self.agent)
        self.assertEqual(standing.OFFLINE, how.how)
        self.assertIsNone(how.pid)

    def test_a_gateway_with_no_readable_record_is_still_online(self):
        # The kernel said so, and nothing the record does changes that. It simply has nothing to say
        # about itself — which is `None` rather than a pid and a verdict nothing measured.
        with standing.holding(self.agent):
            (self.agent / standing.RECORD).write_text("{not json at all")
            how = standing.standing(self.agent)
        self.assertEqual(standing.ONLINE, how.how)
        self.assertIsNone(how.pid)
        self.assertIsNone(how.stale)

    def test_a_record_with_no_record_in_it_at_all_is_still_online(self):
        with standing.holding(self.agent):
            files.write_json(self.agent / standing.RECORD, ["not", "a", "record"])
            self.assertEqual(standing.ONLINE, standing.standing(self.agent).how)

    def test_a_pid_nobody_may_act_on_is_never_handed_back(self):
        # `0` is the caller's own process group and `1` is init. A record holding either — corrupt,
        # truncated, or edited by hand — is a record that would have somebody signal the machine.
        for said in (0, 1, -5, True, "12", None, 3.5):
            with self.subTest(pid=said):
                with standing.holding(self.agent):
                    files.write_json(self.agent / standing.RECORD,
                                     {"pid": said, "since_boot": time.monotonic()})
                    self.assertIsNone(standing.standing(self.agent).pid)


class WhetherAGatewayIsWedged(WithAnAgentDirectory):
    """`stale` — up and doing nothing is a different report from up and working."""

    def test_a_gateway_that_has_just_beaten_is_not_wedged(self):
        with standing.holding(self.agent):
            standing.write_record(self.agent, "one", "9.9.9")
            self.assertFalse(standing.standing(self.agent).stale)

    def test_a_gateway_that_has_missed_three_beats_is_wedged(self):
        # Holding the lock while writing nothing is a process that is up and doing no work, which is
        # the state a person most needs told — and the one a plain up/down answer cannot express.
        with standing.holding(self.agent):
            standing.write_record(self.agent, "one", "9.9.9")
            self.record_says(since_boot=time.monotonic() - standing.WEDGED_AFTER - 1)
            how = standing.standing(self.agent)
        self.assertEqual(standing.ONLINE, how.how, "a wedged gateway is still a running one")
        self.assertTrue(how.stale)

    def test_one_missed_beat_is_not_a_wedged_gateway(self):
        # A slow disk or a loaded machine is not a gateway that has stopped working.
        with standing.holding(self.agent):
            standing.write_record(self.agent, "one", "9.9.9")
            self.record_says(since_boot=time.monotonic() - standing.BEAT_SECONDS - 1)
            self.assertFalse(standing.standing(self.agent).stale)

    def test_a_clock_that_moved_does_not_make_a_working_gateway_look_wedged(self):
        # The wall clock moves in both directions — a laptop waking, an NTP correction — so an age
        # taken from it can be negative or hours out. Both timestamps here are for a person to read,
        # and neither decides anything: with a fresh monotonic reading this gateway is healthy
        # however wrong the dates beside it are.
        for when in ("2999-01-01T00:00:00Z", "1970-01-01T00:00:00Z"):
            with self.subTest(when=when):
                with standing.holding(self.agent):
                    standing.write_record(self.agent, "one", "9.9.9")
                    self.record_says(started_at=when, beat_at=when,
                                     since_boot=time.monotonic())
                    self.assertFalse(standing.standing(self.agent).stale,
                                     "staleness was read off a wall clock")

    def test_staleness_is_not_reported_when_there_is_nothing_to_measure(self):
        # `None`, not `False`. A gateway with no monotonic reading beside it is up, and answering
        # "not wedged" would be a report of health that nothing measured.
        for said in ({}, {"since_boot": "a while ago"}, {"since_boot": True}):
            with self.subTest(record=said):
                with standing.holding(self.agent):
                    files.write_json(self.agent / standing.RECORD, said)
                    self.assertIsNone(standing.standing(self.agent).stale)

    def test_the_beat_is_fifteen_seconds_and_three_missed_ones_are_wedged(self):
        # The numbers are what turn "it went quiet" into "it has stopped", so they are written down
        # rather than left to whatever the constants happen to drift to.
        self.assertEqual(15.0, standing.BEAT_SECONDS)
        self.assertEqual(3, standing.MISSED_BEATS)
        self.assertEqual(standing.BEAT_SECONDS * standing.MISSED_BEATS, standing.WEDGED_AFTER)


class WhatAGatewayWritesDownAboutItself(WithAnAgentDirectory):
    """`write_record` and `write_beat` — the account beside the lock, which decides nothing."""

    def read_back(self) -> dict:
        how, said = files.read_json(self.agent / standing.RECORD)
        self.assertEqual(files.READ, how)
        return said

    def test_the_record_says_what_this_gateway_is(self):
        with standing.holding(self.agent):
            standing.write_record(self.agent, "one", "9.9.9")
        said = self.read_back()
        self.assertEqual("one", said["name"])
        self.assertEqual("9.9.9", said["version"])
        self.assertEqual(os.getpid(), said["pid"])
        self.assertIsInstance(said["since_boot"], float)

    def test_the_times_it_writes_are_the_machines_own_clock_and_carry_their_offset(self):
        # The same shape a log line carries, and for the reader's sake rather than the machine's:
        # `status` says how long a gateway has been up and the next thing anybody does is open that
        # gateway's log. Two clocks there would mean arithmetic on every comparison.
        #
        # The offset is what makes local safe. Across a daylight-saving fall-back one wall-clock time
        # happens twice, and it is only the offset that tells the two apart.
        with standing.holding(self.agent):
            standing.write_record(self.agent, "one", "9.9.9")
        said = self.read_back()
        for which in ("started_at", "beat_at"):
            with self.subTest(field=which):
                moment = datetime.datetime.fromisoformat(said[which])
                self.assertIsNotNone(moment.utcoffset(), f"{which} carries no offset")
                self.assertEqual(said[which], moment.isoformat(sep=" ", timespec="seconds"))

    def test_a_record_and_a_log_line_agree_about_what_time_it_is(self):
        # Stated as its own case because it is a promise between two modules, and the kind that
        # drifts silently: either one could be changed on its own and nothing else would notice.
        from rundesk.utils import logs
        with standing.holding(self.agent):
            standing.write_record(self.agent, "one", "9.9.9")
            logs.note(standing.logs_at(self.agent), "up")

        recorded = self.read_back()["started_at"]
        written = logs.tail(standing.logs_at(self.agent), 1).lines[0]
        self.assertTrue(written.startswith(f"[{recorded[:16]}"),
                        f"the record says {recorded} and the log says {written}")

    def test_the_record_is_renamed_into_place_rather_than_written_in_pieces(self):
        # Half a JSON document is not a smaller record, it is an unreadable one — and a reader
        # arriving mid-write is the ordinary case for a file written every fifteen seconds.
        with standing.holding(self.agent):
            standing.write_record(self.agent, "one", "9.9.9")
        left = [one.name for one in self.agent.iterdir() if files.staged(one.name)]
        self.assertEqual([], left, "a half-written record was left behind")

    def test_a_beat_says_it_is_still_there_without_changing_what_it_is(self):
        # Everything else is carried across rather than re-stated, so a beat can never come to
        # disagree with the record about which gateway this is.
        with standing.holding(self.agent):
            standing.write_record(self.agent, "one", "9.9.9")
            first = self.read_back()
            self.record_says(since_boot=first["since_boot"] - 60, beat_at="1970-01-01T00:00:00Z")

            standing.write_beat(self.agent)

        beaten = self.read_back()
        self.assertEqual(first["name"], beaten["name"])
        self.assertEqual(first["pid"], beaten["pid"])
        self.assertEqual(first["version"], beaten["version"])
        self.assertEqual(first["started_at"], beaten["started_at"],
                         "a beat rewrote when the gateway started")
        self.assertGreater(beaten["since_boot"], first["since_boot"] - 60)
        self.assertNotEqual("1970-01-01T00:00:00Z", beaten["beat_at"])

    def test_a_beat_makes_a_wedged_gateway_healthy_again(self):
        with standing.holding(self.agent):
            standing.write_record(self.agent, "one", "9.9.9")
            self.record_says(since_boot=time.monotonic() - standing.WEDGED_AFTER - 1)
            self.assertTrue(standing.standing(self.agent).stale)

            standing.write_beat(self.agent)

            self.assertFalse(standing.standing(self.agent).stale)

    def test_a_beat_with_no_record_to_beat_in_is_refused(self):
        # Written anyway, it would invent a gateway with no name and no pid — and whoever asked
        # would be told a beat had landed.
        with self.assertRaises(standing.Unrecorded) as refused:
            standing.write_beat(self.agent)
        self.assertIn(files.MISSING, str(refused.exception))

    def test_a_beat_will_not_write_over_a_record_it_could_not_read(self):
        # Losing the pid and the name of a gateway that *is* running, in the act of reporting it
        # healthy, is the worst of both.
        (self.agent / standing.RECORD).write_text("{half a record")
        with self.assertRaises(standing.Unrecorded) as refused:
            standing.write_beat(self.agent)
        self.assertIn(files.UNREADABLE, str(refused.exception))
        self.assertEqual("{half a record", (self.agent / standing.RECORD).read_text())

    def test_json_that_is_not_a_record_is_not_beaten_in_either(self):
        files.write_json(self.agent / standing.RECORD, ["not", "a", "record"])
        with self.assertRaises(standing.Unrecorded):
            standing.write_beat(self.agent)


class TheRecordOutlivesTheGateway(WithAnAgentDirectory):
    """The combination that proves the whole design: a record on disk and an offline answer."""

    def test_the_record_of_a_killed_gateway_is_intact_and_says_nothing_about_now(self):
        pid = self.a_running_gateway()
        said_while_up = json.loads((self.agent / standing.RECORD).read_text())
        self.assertEqual(pid, said_while_up["pid"])

        os.kill(pid, signal.SIGKILL)                     # a pid this case started, never a group
        self.assertTrue(support.waited_until(lambda: not programs.alive(pid), self.PATIENCE))

        self.assertEqual(said_while_up,
                         json.loads((self.agent / standing.RECORD).read_text()),
                         "something tidied the record up, and nothing is meant to")
        self.assertEqual(standing.OFFLINE, standing.standing(self.agent).how)

    def test_the_name_is_free_the_moment_the_holder_is_gone(self):
        # No sweep, no timeout, nothing to clean up: the kernel dropped the lock as it took the
        # process apart, so the next start has the name immediately.
        pid = self.a_running_gateway()
        os.kill(pid, signal.SIGKILL)
        self.assertTrue(support.waited_until(lambda: not programs.alive(pid), self.PATIENCE))

        self.assertTrue(support.waited_until(
            lambda: standing.standing(self.agent).how == standing.OFFLINE, self.PATIENCE))
        with standing.holding(self.agent):
            pass


class WhereAGatewaysOwnAccountStands(WithAnAgentDirectory):
    """The two files launchd captures, which are the only account of a start that never came up."""

    def test_the_supervisors_capture_stands_with_the_gateways_own_logs(self):
        # In the same directory as the day files a working gateway writes, because whoever is
        # explaining a gateway that says offline and shows nothing in its own log is looking in one
        # place, not two.
        out, err = standing.captured(self.agent)
        self.assertEqual(standing.logs_at(self.agent), out.parent)
        self.assertEqual(standing.logs_at(self.agent), err.parent)
        self.assertEqual(self.agent / "logs" / "gateway.out", out)
        self.assertEqual(self.agent / "logs" / "gateway.err", err)

    def test_nothing_here_writes_them(self):
        # They are the supervisor's. A rundesk that created them would be hiding the one difference
        # between "it never started" and "it started and said nothing".
        with standing.holding(self.agent):
            standing.write_record(self.agent, "one", "9.9.9")
        for which in standing.captured(self.agent):
            with self.subTest(file=which.name):
                self.assertFalse(which.exists())

    def test_a_gateways_logs_stand_below_its_own_directory(self):
        # Given rather than derived, like everything else here: nothing in this layer reads where
        # the agents are, so a gateway can be stood up in a scratch directory.
        self.assertEqual(self.agent / "logs", standing.logs_at(self.agent))


if __name__ == "__main__":
    unittest.main()
