"""The gateway process — run for real, because the guarantee is about what a process does.

Every case here starts an actual child in a scratch root and reads its actual exit code. Nothing
that stands in for a process can be `SIGKILL`ed, and nothing that stands in for an interpreter can
prove the one thing that matters most here: **that a gateway refusing to run exits `0`.** Under
`KeepAlive {"SuccessfulExit": false}` a non-zero exit is a request to be restarted, so a refusal
that exited `1` would turn a permanent condition into an endless loop that escalates into launchd's
exponential throttling and simply looks like a hang.

Every signal goes to a pid this suite started itself. Never a process group, never `0` and never
`1` — the build this replaces recorded `killpg` at group `0` taking out the test run and the shell
around it.

Waits are bounded and asked for rather than slept through: `support.waited_until`.

Run directly: `python3 tests/test_gateway_host.py`
"""

import datetime
import os
import shutil
import signal
import subprocess
import sys
import time
import unittest
from pathlib import Path
from typing import List, Optional, Tuple

import support
from rundesk import __version__
from rundesk.agents import directory, records
from rundesk.gateways import host, standing
from rundesk.utils import logs, programs

#: How a gateway is started here: the same handoff the job's shim performs, so what these cases run
#: is what launchd runs. Deliberately not `cli.main` — there is no verb for this, and inventing one
#: in a suite would prove something nothing else does.
#:
#: `BEAT_SECONDS` is settable because two of the guarantees below are about what the *loop* does and
#: not about what one pass through it does — a beat that stops landing, and a warning that is written
#: once rather than every fifteen seconds. Left at the real fifteen, proving either would cost the
#: suite a minute of sleeping; the constant is read on every pass, so lowering it changes when the
#: loop comes round and nothing else. Every case that is not about the loop leaves it alone.
A_GATEWAY = """
import sys
sys.path.insert(0, {src!r})
from rundesk.gateways import standing
standing.BEAT_SECONDS = {beat!r}
from rundesk.gateways.host import run
raise SystemExit(run({name!r}))
"""


class WithAnAgent(support.Isolated):
    """A scratch install with one real agent in it, and the means to host it for real."""

    #: How long a case waits on a real child. Generous, because the child imports the whole product
    #: and opens a database before it can answer, and short enough that a wedged run ends.
    PATIENCE = 20.0

    def setUp(self) -> None:
        super().setUp()
        self.name = "cole"
        self.at = directory.made(self.name, "claude")
        self.said = self.home / "gateway.out"
        self.started = []
        self.addCleanup(self.stop_everything)

    def stop_everything(self) -> None:
        """Stop only what this case started. Never a group, and never a pid nobody wrote down."""
        for child in self.started:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=self.PATIENCE)

    def hosting(self, name: Optional[str] = None, out: Optional[Path] = None,
                beat: float = standing.BEAT_SECONDS) -> subprocess.Popen:
        """Start a real gateway process, with its output captured the way launchd captures it.

        **The file is opened here and inherited there**, `O_APPEND`, which is the whole of how a
        supervisor hands a job its standard output: `xpcproxy` opens the path from the plist and
        `exec`s the program with the descriptor already in place. So a case that rotates the file
        underneath a gateway started this way is asking the same question launchd would.
        """
        where = out or self.said
        body = A_GATEWAY.format(src=str(support.CHECKOUT / "src"), name=name or self.name, beat=beat)
        with open(where, "ab") as writing:
            child = subprocess.Popen(
                [sys.executable, "-c", body],
                stdin=subprocess.DEVNULL, stdout=writing, stderr=subprocess.STDOUT,
                start_new_session=True)
        self.started.append(child)
        return child

    def ran(self, name: Optional[str] = None,
            out: Optional[Path] = None) -> Tuple[int, str]:
        """Start a gateway that is expected to refuse, and hand back `(exit code, what it said)`."""
        where = out or self.said
        child = self.hosting(name, where)
        self.assertTrue(support.waited_until(lambda: child.poll() is not None, self.PATIENCE),
                        f"it never ended. It said: {self.what_it_said(where)}")
        return child.returncode, self.what_it_said(where)

    def a_running_gateway(self, beat: float = standing.BEAT_SECONDS) -> subprocess.Popen:
        """A real gateway holding this agent's name, proven up before the case goes on.

        **Waited for by its recorded pid rather than by `ONLINE`**, and that is not fussiness: the
        claim comes first and the record is written inside it, so there is a real instant where the
        kernel says a gateway is up and the record beside it says nothing at all. `standing` is
        right about that — a gateway with no readable record is still online — and a case that
        stopped waiting there reads back `None` for the pid, on a loaded machine only.
        """
        child = self.hosting(beat=beat)
        self.assertTrue(
            support.waited_until(lambda: self.holder() == child.pid, self.PATIENCE),
            f"the gateway never came up. It said: {self.what_it_said()}")
        return child

    def holder(self) -> Optional[int]:
        """The pid of whatever holds this agent's name, or `None` while nothing does."""
        return standing.standing(self.at).pid

    def what_it_said(self, where: Optional[Path] = None) -> str:
        one = where or self.said
        return one.read_text(encoding="utf-8", errors="replace") if one.exists() else "nothing"

    def its_log(self) -> str:
        read = logs.tail(standing.logs_at(self.at), 50)
        return "\n".join(read.lines)


class TheVeryFirstThingItSays(WithAnAgent):
    """One line with a moment and a pid, before anything is parsed and before anything is read."""

    def test_it_says_what_pid_it_is_before_it_does_anything_else(self):
        # If `gateway.out` is empty while launchd says the job ran, the failure is upstream of this
        # code and belongs in the unified log. That one line is what turns "cannot tell" into
        # "look here" — so it has to land before the first thing that can fail.
        _code, said = self.ran(name="nobody-made-this-one")
        first = said.splitlines()[0]
        self.assertIn(f"pid {self.started[0].pid}", first)
        self.assertIn("nobody-made-this-one", first)
        self.assertIn(__version__, first)

    def test_the_moment_it_carries_is_the_shape_every_other_line_here_carries(self):
        # The same function as the log lines and the gateway's record, because these are read side
        # by side and two clocks would mean arithmetic on every comparison.
        _code, said = self.ran(name="nobody-made-this-one")
        self.assertTrue(said.startswith(f"[{logs.stamp()[:13]}"), said.splitlines()[0])

    def test_a_gateway_that_comes_up_says_it_too(self):
        self.a_running_gateway()
        self.assertIn(f"pid {self.started[0].pid}", self.what_it_said().splitlines()[0])


class WhatItRefusesToRunFor(WithAnAgent):
    """Every refusal, and every one of them exits `0` — see the module docstring for why."""

    def test_an_agent_that_is_not_there_says_so_and_exits_zero(self):
        code, said = self.ran(name="nobody-made-this-one")
        self.assertEqual(0, code, f"a refusal exited {code}, which asks launchd to restart it")
        self.assertIn("no agent called nobody-made-this-one", said)

    def test_a_directory_with_no_records_in_it_is_not_an_agent(self):
        # `state.db` is what makes a directory an agent. A half-made one exists and is not one.
        (self.home / "data" / "agents" / "half").mkdir(parents=True)
        code, said = self.ran(name="half")
        self.assertEqual(0, code)
        self.assertIn(directory.RECORDS, said)

    def test_an_agent_that_is_not_settled_onto_this_release_says_which_command_to_run(self):
        # Its records were written by an older rundesk and the steps that would carry it have not
        # run. Restarting would never fix that; `rundesk update` would.
        with records.writing(directory.records(self.name)) as conn:
            conn.execute("DELETE FROM migrations")
        code, said = self.ran()
        self.assertEqual(0, code)
        self.assertIn("not settled", said)
        self.assertIn("run: rundesk update", said)

    def test_a_second_gateway_stands_down_and_names_the_pid_that_has_the_name(self):
        # The claim *is* the check. Anything that asked first and started second has a gap another
        # gateway can arrive in — an ordinary `start` ended a live agent's whole process tree once.
        first = self.a_running_gateway()
        code, said = self.ran(out=self.home / "second.out")
        self.assertEqual(0, code)
        self.assertIn("already running", said)
        self.assertIn(str(first.pid), said)

    def test_a_refusal_that_raises_on_the_way_to_being_a_refusal_still_exits_zero(self):
        # The sharp edge stated as its own case. `directory.where` refuses a name that reaches
        # outside the agents directory, and an uncaught exception would exit 1 — which under
        # `SuccessfulExit: false` is a request to be restarted, for ever.
        somewhere = self.home / "not-an-agent"
        somewhere.mkdir()
        (self.home / "data" / "agents" / "reaching").symlink_to(somewhere)
        code, said = self.ran(name="reaching")
        self.assertEqual(0, code, "a refusal that raised exited non-zero")
        self.assertIn("could not be started", said)

    def test_records_that_cannot_be_read_at_all_still_exit_zero(self):
        directory.records(self.name).write_bytes(b"this is not a database")
        code, said = self.ran()
        self.assertEqual(0, code)
        self.assertIn("NOT RUNNING", said)

    def test_a_refusal_is_written_into_the_agents_own_log_as_well(self):
        # Two places, because they are read by two different people at two different moments:
        # `gateway.out` is what somebody explaining a job that will not start reaches for, and the
        # day file is where everything else this gateway ever said is.
        with records.writing(directory.records(self.name)) as conn:
            conn.execute("DELETE FROM migrations")
        self.ran()
        self.assertIn("gateway did not start", self.its_log())


class WhileItIsRunning(WithAnAgent):
    """The name is held by the kernel for exactly as long as the process lives."""

    def test_the_lock_is_held_while_it_lives_and_free_the_moment_it_is_gone(self):
        child = self.a_running_gateway()
        self.assertEqual(standing.ONLINE, standing.standing(self.at).how)
        self.assertEqual(child.pid, standing.standing(self.at).pid)

        os.kill(child.pid, signal.SIGTERM)               # a pid this case started, never a group
        child.wait(timeout=self.PATIENCE)
        self.assertEqual(standing.OFFLINE, standing.standing(self.at).how)

    def test_it_writes_down_what_it_is_and_says_so_in_its_own_log(self):
        child = self.a_running_gateway()
        said = standing.standing(self.at)
        self.assertEqual(child.pid, said.pid)
        self.assertFalse(said.stale, "a gateway that has just started has not missed a beat")
        self.assertTrue(support.waited_until(lambda: "gateway up for" in self.its_log(),
                                             self.PATIENCE), self.its_log())

    def test_the_name_it_holds_belongs_to_that_agents_directory_and_nowhere_else(self):
        self.a_running_gateway()
        self.assertTrue((self.at / standing.LOCK).is_file())
        self.assertTrue((self.at / standing.RECORD).is_file())


class HowItStops(WithAnAgent):
    """An orderly stop and a crash have to be different things in the log, or neither is readable."""

    def test_a_termination_request_brings_it_down_cleanly_and_exits_zero(self):
        # It has to land inside the job's `ExitTimeOut` too: a gateway that ignores SIGTERM makes
        # `bootout --wait` block for that whole window and then be SIGKILLed, which launchd calls
        # *languishing*.
        child = self.a_running_gateway()
        os.kill(child.pid, signal.SIGTERM)
        self.assertTrue(support.waited_until(lambda: child.poll() is not None, self.PATIENCE),
                        f"it did not stop. It said: {self.what_it_said()}")
        self.assertEqual(0, child.returncode)
        self.assertIn("gateway stopping", self.its_log())

    def test_a_hang_up_stops_it_the_same_way(self):
        # Python installs no handler for `SIGHUP`, so without one the kernel ends the process
        # outright — no exception, no `finally`, and nothing in the log to tell it from a crash.
        child = self.a_running_gateway()
        os.kill(child.pid, signal.SIGHUP)
        self.assertTrue(support.waited_until(lambda: child.poll() is not None, self.PATIENCE))
        self.assertEqual(0, child.returncode)
        self.assertIn("gateway stopping", self.its_log())

    def test_a_gateway_killed_outright_leaves_its_record_and_still_reads_as_offline(self):
        # Nothing runs on `SIGKILL`: no handler, no `finally`, no tidying. The record is still whole
        # on disk and the answer is still offline, because the answer was never the record's to give.
        child = self.a_running_gateway()
        os.kill(child.pid, signal.SIGKILL)
        self.assertTrue(support.waited_until(lambda: not programs.alive(child.pid), self.PATIENCE))
        child.wait(timeout=self.PATIENCE)

        self.assertTrue((self.at / standing.RECORD).is_file(),
                        "the record was cleaned up, so this proves nothing")
        self.assertEqual(standing.OFFLINE, standing.standing(self.at).how)
        self.assertNotIn("gateway stopping", self.its_log(),
                         "a gateway that was killed outright claimed to have stopped cleanly")

    def test_the_name_is_free_again_for_a_gateway_that_was_killed_outright(self):
        child = self.a_running_gateway()
        os.kill(child.pid, signal.SIGKILL)
        self.assertTrue(support.waited_until(lambda: not programs.alive(child.pid), self.PATIENCE))
        child.wait(timeout=self.PATIENCE)

        second = self.hosting(out=self.home / "second.out")
        self.assertTrue(support.waited_until(lambda: self.holder() == second.pid, self.PATIENCE),
                        "the name never came free. It said: "
                        f"{self.what_it_said(self.home / 'second.out')}")


class TheWindowBetweenTheClaimAndTheRecord(WithAnAgent):
    """A gateway is online the instant it holds the name, and the record arrives afterwards.

    Claiming the name and writing the record are deliberately two steps: the lock **is** the
    identity and the record is only a description of whoever holds it. So there is a real moment —
    short, and reachable by anybody running `status` at the wrong instant — where a gateway is
    `ONLINE` and has said nothing about itself yet.

    Pinned here because the obvious "fix" is wrong in a way that is hard to argue back from later.
    Making `standing` answer `OFFLINE` when the record is missing would have it say a running
    gateway is not running, which is the one answer this whole design exists to make impossible. And
    moving the record inside `holding` would put a write inside the claim, giving a start one more
    thing to fail at and one more way to hold a name it cannot describe.

    This case is also why the suite waits on the record rather than on `ONLINE`: a case that waited
    on the claim would be racing this window rather than avoiding it.
    """

    def test_a_gateway_that_has_not_written_its_record_yet_is_still_online(self):
        with standing.holding(self.at):
            how = standing.standing(self.at)

        self.assertEqual(standing.ONLINE, how.how)
        self.assertIsNone(how.pid, "a pid was invented for a gateway that has not said what it is")
        self.assertIsNone(how.stale, "a gateway with nothing to judge it by was judged")

    def test_the_record_is_what_arrives_second_and_never_what_decides(self):
        # The order, stated as a case: no record on disk while the name is already held.
        with standing.holding(self.at):
            self.assertFalse((self.at / standing.RECORD).exists())
            standing.write_record(self.at, "one", "9.9.9")
            self.assertEqual(os.getpid(), standing.standing(self.at).pid)


class WhatTheSupervisorCaptured(WithAnAgent):
    """`gateway.out` and `gateway.err` are appended to for ever by something that never rotates them.

    launchd opens both `O_CREAT|O_RDWR|O_APPEND` and never truncates, so in a crash loop every
    restart adds another traceback and nothing comes to sweep it. They are also the only account of a
    start that died before the gateway had a log of its own, so the gateway rotates them itself, at
    startup, by content — see `host`'s docstring for why a rename would be worse than the growth.

    Every case here starts a real gateway with a real descriptor on the real file, because what is
    being asked is what a process inheriting that descriptor does after the file moves underneath it.
    """

    def setUp(self) -> None:
        super().setUp()
        self.out, self.err = standing.captured(self.at)
        self.out.parent.mkdir(parents=True, exist_ok=True)
        self.aside = self.out.with_name(f"{self.out.name}.1")

    def a_capture_of(self, size: int, into: Optional[Path] = None, first: bytes = b"") -> Path:
        """A capture of about that many bytes, as a crash loop leaves one."""
        one = into or self.out
        line = b"Traceback (most recent call last): nobody read this\n"
        one.write_bytes(first + line * (max(0, size - len(first)) // len(line) + 1))
        return one

    def cannot_be_hosted(self) -> None:
        """Leave the agent in a state this release refuses to host, so a start refuses and exits.

        A refusal is the case that fills these files: a gateway refusing for a permanent reason is
        one launchd brings back and back, appending another sentence every time. It is also the only
        way to watch a *whole* start — up, rotate, say, exit — inside a case.
        """
        with records.writing(directory.records(self.name)) as conn:
            conn.execute("DELETE FROM migrations")

    def a_whole_start(self) -> str:
        """One start of a real gateway onto the real capture file. Hands back what is in it after."""
        code, said = self.ran(out=self.out)
        self.assertEqual(0, code, f"the start did not refuse cleanly. It said: {said}")
        return said

    def captures(self) -> List[str]:
        """Everything standing beside the live capture, by name."""
        return sorted(one.name for one in self.out.parent.iterdir()
                      if one.name.startswith(self.out.name))

    def test_a_capture_that_has_grown_past_the_threshold_is_moved_aside(self):
        self.a_capture_of(host.CAPTURE_OVER + 1)
        self.cannot_be_hosted()

        self.a_whole_start()

        self.assertTrue(self.aside.is_file(), "nothing was kept")
        self.assertIn(b"nobody read this", self.aside.read_bytes())
        self.assertLess(self.out.stat().st_size, 1024, "the live file was not emptied")

    def test_a_capture_that_is_still_small_is_left_exactly_where_it_is(self):
        # The guarantee that keeps a gateway `KeepAlive` brings back every thirty seconds from
        # rotating 2,880 times a day and rolling the evidence off the end within minutes.
        self.out.write_bytes(b"one earlier start said this\n")
        self.cannot_be_hosted()

        said = self.a_whole_start()

        self.assertFalse(self.aside.exists(), "it rotated a file that had barely anything in it")
        self.assertIn("one earlier start said this", said)

    def test_the_first_line_lands_in_the_live_file_even_when_the_rotation_took_it(self):
        # The whole worth of that line is that it is *in* `gateway.out`: an empty one beside a job
        # launchd says has run means the failure is upstream of this code. A rotation that carried
        # it off into `gateway.out.1` and left nothing behind would have destroyed exactly that.
        self.a_capture_of(host.CAPTURE_OVER + 1)
        self.cannot_be_hosted()

        said = self.a_whole_start()

        self.assertIn(f"pid {self.started[0].pid}", said.splitlines()[0])
        self.assertIn(__version__, said.splitlines()[0])

    def test_a_gateway_that_is_still_running_goes_on_writing_into_the_file_it_emptied(self):
        # The one that would be silently wrong if the rotation renamed instead of truncating: the
        # gateway holds the descriptor launchd opened, so a rename would have it spend its whole
        # life writing into `gateway.out.1` while the file everybody opens stayed empty.
        self.a_capture_of(host.CAPTURE_OVER + 1)

        child = self.hosting(out=self.out)
        self.assertTrue(support.waited_until(lambda: self.holder() == child.pid, self.PATIENCE),
                        f"the gateway never came up. It said: {self.what_it_said(self.out)}")

        self.assertIn(f"pid {child.pid}", self.what_it_said(self.out))
        self.assertLess(self.out.stat().st_size, 1024,
                        "the live file still holds everything, so nothing was rotated at all")
        self.assertIn(b"nobody read this", self.aside.read_bytes())

    def test_what_it_kept_holds_the_start_of_what_went_wrong_and_says_what_it_dropped(self):
        # The head and not the tail: the crash that started a loop is the one somebody is looking
        # for, and it is the one at the top of the file.
        self.a_capture_of(host.CAPTURE_OVER * 2, first=b"the first thing that ever went wrong\n")
        self.cannot_be_hosted()

        self.a_whole_start()

        kept = self.aside.read_bytes()
        self.assertTrue(kept.startswith(b"the first thing that ever went wrong"))
        self.assertIn(b"the rest is not here", kept)

    def test_what_went_to_standard_error_is_moved_aside_too(self):
        self.a_capture_of(host.CAPTURE_OVER + 1, into=self.err)
        self.cannot_be_hosted()

        self.a_whole_start()

        self.assertIn(b"nobody read this", self.err.with_name(f"{self.err.name}.1").read_bytes())
        self.assertEqual(0, self.err.stat().st_size)

    def test_a_gateway_restarted_over_and_over_never_leaves_more_than_it_keeps(self):
        # The months-scale case, run small: a crash loop that fills the file, is brought back, fills
        # it again, for as long as nobody is watching. What that may ever cost is fixed.
        self.cannot_be_hosted()
        for _start in range(host.CAPTURES_KEPT + 3):
            self.a_capture_of(host.CAPTURE_OVER + 1)
            self.a_whole_start()

        self.assertEqual([f"{self.out.name}.{which}" for which in range(1, host.CAPTURES_KEPT + 1)],
                         self.captures()[1:], f"it left {self.captures()}")
        self.assertLess(sum(one.stat().st_size for one in self.out.parent.iterdir()),
                        host.CAPTURE_OVER * (host.CAPTURES_KEPT + 2),
                        "what the captures cost is not bounded by the two numbers that decide it")

    def test_a_capture_it_cannot_move_aside_never_stops_it_refusing_cleanly(self):
        # Failing to *tidy* a log may never become failing to *exit*: a non-zero exit here is a
        # request to be restarted, and the condition would be exactly the same on the way back.
        support.not_as_root(self)
        self.a_capture_of(host.CAPTURE_OVER + 1)
        self.cannot_be_hosted()
        self.out.parent.chmod(0o500)
        self.addCleanup(self.out.parent.chmod, 0o700)

        code, _said = self.ran(out=self.out)

        self.assertEqual(0, code, "a refusal that could not rotate its capture exited non-zero")


class WhatItGoesOnDoingForMonths(WithAnAgent):
    """The loop, read as though this process has been in it since March.

    Nothing here is about coming up. Everything here is about the things that only appear once
    nobody has restarted the gateway in a long time: a beat that stops landing, a warning written
    every fifteen seconds for a week, a directory gaining a file a day for ever.
    """

    #: Fast enough that a case sees several passes of the loop without sleeping through the real
    #: fifteen seconds, and slow enough that it is still a loop and not a spin.
    QUICKLY = 0.2

    def several_more_beats(self) -> None:
        """Give the loop time to do the wrong thing, which is the only way to prove it does not.

        A guessed wait, and deliberately so: every other wait in this suite is for something to
        happen, and these two cases are about something that must *not* — a second warning, an exit.
        There is nothing to ask about, so the wait is a window rather than a question, and it is six
        passes of a loop the case has already made fast.
        """
        time.sleep(self.QUICKLY * 6)

    def a_day_file_from(self, days_ago: int) -> Path:
        """One of this gateway's own day files, from far enough back that it should be swept."""
        where = standing.logs_at(self.at)
        where.mkdir(parents=True, exist_ok=True)
        when = datetime.datetime.now().astimezone() - datetime.timedelta(days=days_ago)
        one = where / logs.named_for(when)
        one.write_text("[an older day] INFO:   gateway up\n", encoding="utf-8")
        return one

    def test_it_sweeps_the_days_it_no_longer_keeps(self):
        # A file a day, kept for ever, is the same unbounded growth as a capture nobody truncates —
        # reached slowly instead of quickly. `utils.logs` has always had the sweep; nothing called it.
        old = self.a_day_file_from(host.KEPT_DAYS + 1)
        recent = self.a_day_file_from(1)

        # Made fast, because the sweep is the loop's first pass and not a call before it — which is
        # what makes this case cover the wiring as well as the sweeping.
        self.a_running_gateway(beat=self.QUICKLY)

        self.assertTrue(support.waited_until(lambda: not old.exists(), self.PATIENCE),
                        f"the old day was kept. It said: {self.what_it_said()}")
        self.assertTrue(recent.exists(), "it swept a day it was told to keep")

    def test_it_sweeps_again_when_the_day_turns_rather_than_only_on_the_way_up(self):
        # The half of the sweep a running gateway proves nothing about: a gateway that is doing its
        # job is one nobody restarts, so a process up since March swept once, in March, and has been
        # gaining a file a day ever since. Driven directly rather than through a child, because the
        # only thing that would make a real one do this is waiting until midnight.
        where = standing.logs_at(self.at)
        old = self.a_day_file_from(host.KEPT_DAYS + 1)

        today = host._kept_the_days(where, "")           # the sweep on the way up

        self.assertFalse(old.exists(), "it did not sweep at all")
        again = self.a_day_file_from(host.KEPT_DAYS + 1)
        self.assertEqual(today, host._kept_the_days(where, today))
        self.assertTrue(again.exists(), "it swept twice in one day, which is a listing per beat")

        host._kept_the_days(where, "a day that has now turned")

        self.assertFalse(again.exists(), "the day turned and it never swept again")

    def test_a_beat_that_cannot_be_written_does_not_take_a_working_gateway_down(self):
        # A full disk, a volume gone read-only, a record taken away — none of them is a reason to
        # end a gateway that is hosting its agent, and all of them would be the same on the way back
        # from a restart. Letting it through would exit non-zero into an endless restart.
        child = self.a_running_gateway(beat=self.QUICKLY)
        (self.at / standing.RECORD).unlink()

        self.assertTrue(support.waited_until(lambda: "could not say it is still working"
                                             in self.its_log(), self.PATIENCE), self.its_log())
        self.assertIsNone(child.poll(), "a beat that failed took the whole gateway down")
        self.assertEqual(standing.ONLINE, standing.standing(self.at).how)

    def test_it_says_a_beat_stopped_landing_once_and_not_every_fifteen_seconds(self):
        # A log that grows with the beat is the growth it was meant to bound, arrived at from the
        # other side: a line every fifteen seconds for as long as a disk stays full is 5,760 a day.
        child = self.a_running_gateway(beat=self.QUICKLY)
        (self.at / standing.RECORD).unlink()
        self.assertTrue(support.waited_until(lambda: "could not say it is still working"
                                             in self.its_log(), self.PATIENCE), self.its_log())

        self.several_more_beats()
        self.assertIsNone(child.poll())

        self.assertEqual(1, self.its_log().count("could not say it is still working"),
                         f"it said it every time round the loop: {self.its_log()}")

    def test_a_beat_that_starts_landing_again_is_said_out_loud_as_well(self):
        # A warning nothing ever retracts is one somebody goes on believing.
        child = self.a_running_gateway(beat=self.QUICKLY)
        (self.at / standing.RECORD).unlink()
        self.assertTrue(support.waited_until(lambda: "could not say it is still working"
                                             in self.its_log(), self.PATIENCE), self.its_log())

        standing.write_record(self.at, self.name, __version__)

        self.assertTrue(support.waited_until(lambda: "still working again" in self.its_log(),
                                             self.PATIENCE), self.its_log())
        self.assertIsNone(child.poll())

    def test_a_gateway_whose_agent_was_taken_away_does_not_put_the_directory_back(self):
        # `_refused` has the same rule for the same reason: a directory invented by whatever is
        # complaining that it is missing is one that then looks half-made to everything else.
        child = self.a_running_gateway(beat=self.QUICKLY)
        shutil.rmtree(self.at)

        self.several_more_beats()

        self.assertIsNone(child.poll(), "it ended when its agent went away, which exits non-zero")
        self.assertFalse(self.at.exists(), "it made its agent's directory again to complain into")


class TheProcessNeverTalksToItsSupervisor(unittest.TestCase):
    """`host` may not import `job`, and that is checked rather than remembered."""

    def test_it_does_not_import_the_job_layer(self):
        # A gateway that could bootstrap, boot out or kick its own job could restart itself, and the
        # decision to keep a gateway running would sit inside the thing being kept running. It is
        # also what lets every case above run with launchd nowhere near it.
        said = (support.CHECKOUT / "src" / "rundesk" / "gateways" / "host.py").read_text()
        for one in ("import job", "gateways.job", "gateways import job"):
            with self.subTest(reaching=one):
                self.assertNotIn(one, said)

    def test_it_never_reaches_for_launchctl_either(self):
        said = (support.CHECKOUT / "src" / "rundesk" / "gateways" / "host.py").read_text()
        self.assertNotIn("launchctl", said)


if __name__ == "__main__":
    unittest.main()
