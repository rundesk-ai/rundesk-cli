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

import contextlib
import datetime
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import unittest
from pathlib import Path
from typing import List, Optional, Tuple
from unittest import mock

import support
from rundesk import __version__
from rundesk.agents import directory, records
from rundesk.channels import arriving, hosting
from rundesk.channels import files as arrivals
from rundesk.channels import kept as channels
from rundesk.core import config, paths, secrets
from rundesk.delegations import kept as delegations_kept
from rundesk.exits import OK
from rundesk.gateways import host, job, maintenance, standing
from rundesk.providers import kept as turns_kept
from rundesk.providers import protocol
from rundesk.schedules import firing, kept
from rundesk.skills import catalogs, grants, library
from rundesk.utils import locking, logs, programs

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
import contextlib, os, sys
sys.path.insert(0, {src!r})
from rundesk.gateways import awake, maintenance, standing
standing.BEAT_SECONDS = {beat!r}
from rundesk.gateways.host import run


@contextlib.contextmanager
def no_machine_assertion():
    # The focused awake suite owns the one real macOS boundary check. These ninety-odd host cases
    # prove gateway process behavior, and starting a real OS helper in every one only loads the
    # machine and makes an unrelated test depend on the platform it happened to run on.
    yield None


awake.while_running = no_machine_assertion
if os.environ.get("RUNDESK_TEST_REENTER"):
    def fresh(_name):
        from pathlib import Path
        Path(os.environ["RUNDESK_TEST_REENTER_PROOF"]).write_text("fresh")
        os.execv(sys.executable, [sys.executable, "-c", os.environ["RUNDESK_TEST_GATEWAY_BODY"]])
    maintenance.fresh = fresh
raise SystemExit(run({name!r}))
"""

#: A channel adapter that connects and writes down everything it is asked to deliver, so a case can
#: read what a real gateway really said to a real platform. The same shape
#: `tests/test_channels_hosting.py` uses, kept here rather than imported: what is being proved there
#: is the hosting and what is being proved here is the wiring, and a suite that borrowed the other's
#: fixture would go red for a reason that had nothing to do with it.
AN_ADAPTER = """#!/usr/bin/env python3
import json, os, signal, sys
if "--capabilities" in sys.argv:
    print(json.dumps({"stream": True, "max_text": 2000})); raise SystemExit(0)
# **Goodbye is said on the protocol, not by vanishing on the signal**, which is what an adapter
# holding a connection to a platform has to do — and what makes the last thing a gateway says
# provable here at all. `_asked_to_stop` writes `{"do": "stop"}` and does *not* wait for it, so an
# adapter that died where the signal landed would race every notice sent in the same breath.
# Nothing can outlive its gateway by doing this: `programs.stop` escalates to `SIGKILL`.
signal.signal(signal.SIGTERM, signal.SIG_IGN)
settings = json.loads(os.environ.get("RUNDESK_SETTINGS") or "{}")
print(json.dumps({"say": "ready", "as": "a-bot"}), flush=True)
for line in sys.stdin:
    try:
        record = json.loads(line)
    except ValueError:
        continue
    if record.get("do") == "stop":
        break
    if record.get("do") == "deliver":
        with open(settings["heard"], "a") as writing:
            writing.write(record.get("place", "") + " :: " + record.get("text", "") + "\\n")
"""

#: One whose platform says no to everything: every delivery comes back a `failed` carrying a reason
#: rather than a receipt. A rate limit and a permission the bot was never granted are the two that
#: really happen, and both arrive in exactly this shape.
AN_ADAPTER_THAT_IS_REFUSED = """#!/usr/bin/env python3
import json, os, signal, sys
if "--capabilities" in sys.argv:
    print(json.dumps({"stream": True, "max_text": 2000})); raise SystemExit(0)
signal.signal(signal.SIGTERM, signal.SIG_IGN)
print(json.dumps({"say": "ready", "as": "a-bot"}), flush=True)
for line in sys.stdin:
    try:
        record = json.loads(line)
    except ValueError:
        continue
    if record.get("do") == "stop":
        break
    if record.get("do") == "deliver":
        print(json.dumps({"say": "failed", "id": record.get("id"),
                          "why": "would not take it: 429 Too Many Requests"}), flush=True)
"""


#: One that will not connect without its credential and never says what it was. `78` is `EX_CONFIG`,
#: which is what a missing token is — so a gateway that failed to resolve one has an adapter that
#: dies rather than one that connects anonymously, and the notified channel simply never says
#: anything. That silence is the assertion, and it costs no value being written anywhere.
#: A value long enough that `secrets.hinted` would show three characters of each end, so a case
#: asserting the whole thing appears nowhere is asserting something that could fail.
A_BOT_TOKEN = "MTIzNDU2Nzg5-coles-own-bot-token"

AN_ADAPTER_THAT_NEEDS_ITS_CREDENTIAL = """#!/usr/bin/env python3
import json, os, signal, sys
if "--capabilities" in sys.argv:
    print(json.dumps({"stream": True, "max_text": 2000})); raise SystemExit(0)
signal.signal(signal.SIGTERM, signal.SIG_IGN)
settings = json.loads(os.environ.get("RUNDESK_SETTINGS") or "{}")
if not os.environ.get("DISCORD_BOT_TOKEN"):
    sys.stderr.write("no credential reached this adapter\\n")
    raise SystemExit(78)
print(json.dumps({"say": "ready", "as": "a-bot"}), flush=True)
for line in sys.stdin:
    try:
        record = json.loads(line)
    except ValueError:
        continue
    if record.get("do") == "stop":
        break
    if record.get("do") == "deliver":
        with open(settings["heard"], "a") as writing:
            writing.write(record.get("place", "") + " :: " + record.get("text", "") + "\\n")
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
                beat: float = standing.BEAT_SECONDS, refreshing: bool = False) -> subprocess.Popen:
        """Start a real gateway process, with its output captured the way launchd captures it.

        **The file is opened here and inherited there**, `O_APPEND`, which is the whole of how a
        supervisor hands a job its standard output: `xpcproxy` opens the path from the plist and
        `exec`s the program with the descriptor already in place. So a case that rotates the file
        underneath a gateway started this way is asking the same question launchd would.
        """
        where = out or self.said
        body = A_GATEWAY.format(src=str(support.CHECKOUT / "src"), name=name or self.name, beat=beat)
        environment = os.environ.copy()
        if refreshing:
            environment["RUNDESK_TEST_REENTER"] = "1"
            environment["RUNDESK_TEST_REENTER_PROOF"] = str(self.home / "reentered")
            environment["RUNDESK_TEST_GATEWAY_BODY"] = body
        with open(where, "ab") as writing:
            child = subprocess.Popen(
                [sys.executable, "-c", body],
                stdin=subprocess.DEVNULL, stdout=writing, stderr=subprocess.STDOUT,
                start_new_session=True, env=environment)
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


class AutomaticUpkeepOnTheGatewayBeat(WithAnAgent):
    """The real host loop carries a due usage window through settlement exactly once."""

    def setUp(self) -> None:
        super().setUp()
        records.stated(directory.records(self.name), {"provider_name": support.A_STAND_IN})
        conversation = arriving.recorded(
            self.name, "terminal", self.name, "owner", "start").conversation
        for offset in range(7):
            at = datetime.datetime(2026, 7, 1 + offset, 12, tzinfo=datetime.timezone.utc)
            turn = turns_kept.add_turn(
                self.name, {"conversation_id": conversation, "provider_name": "standin",
                            "access_mode": protocol.ACCESS_WORK}, when=at)
            turns_kept.finish_turn(self.name, turn, turns_kept.DONE, when=at)

    def upkeep_turns(self) -> List[dict]:
        """Every automatic upkeep turn in this agent's durable records."""
        try:
            with records.reading(directory.records(self.name)) as conn:
                return [dict(one) for one in conn.execute(
                    "SELECT id, turn_status FROM turns WHERE schedule_name = ? ORDER BY id",
                    (kept.UPKEEP,)).fetchall()]
        except records.Unreadable:
            return []

    def upkeep_outcome(self) -> Optional[str]:
        """The protected row's settlement, or ``None`` before it exists or settles."""
        try:
            with records.reading(directory.records(self.name)) as conn:
                row = conn.execute(
                    "SELECT last_outcome FROM schedules WHERE name = ?", (kept.UPKEEP,)).fetchone()
        except records.Unreadable:
            return None
        return str(row["last_outcome"]) if row and row["last_outcome"] else None

    def test_the_first_beat_starts_settles_and_does_not_repeat_one_due_window(self):
        child = self.a_running_gateway(beat=0.05)
        self.assertTrue(support.waited_until(
            lambda: self.upkeep_outcome() == kept.DONE, self.PATIENCE),
            f"upkeep never settled. Gateway log: {self.its_log()}")
        self.assertEqual([turns_kept.DONE],
                         [one["turn_status"] for one in self.upkeep_turns()])

        time.sleep(0.3)

        self.assertEqual(1, len(self.upkeep_turns()), "a later beat repeated the same usage window")
        self.assertIsNone(child.poll(), "the gateway ended while carrying automatic upkeep")


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


class StartingWhileAnUpdateOwnsTheInstall(WithAnAgent):
    """The cross-process barrier: no old imported gateway may claim during an update."""

    def test_it_waits_then_refreshes_before_claiming_the_agent(self):
        with locking.only_one(paths.gateway_transition_lock(), "the test update"):
            child = self.hosting(refreshing=True)
            self.assertTrue(support.waited_until(
                lambda: "this process is pid" in self.what_it_said(), 2.0), self.what_it_said())
            time.sleep(0.1)
            self.assertIsNone(self.holder(), "the gateway claimed its agent inside the update")
            self.assertIsNone(child.poll(), "the blocked gateway exited instead of waiting")

        self.assertTrue(support.waited_until(
            lambda: (self.home / "reentered").is_file(), self.PATIENCE), self.what_it_said())
        self.assertTrue(support.waited_until(
            lambda: self.holder() == child.pid, self.PATIENCE), self.what_it_said())


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

    def taken_away(self, at: Path) -> None:
        """Remove a directory a live gateway is still writing into, and prove it went.

        **`shutil.rmtree` is two steps and a running gateway fits between them.** It walks the tree
        unlinking as it goes and then `rmdir`s what is left, so a beat, a log line or a swept day
        landing in that window leaves the directory not empty and the call raises `ENOTEMPTY` — the
        case going red in its own setup, before the guarantee it exists for has been asked about at
        all. Measured on the 3.9 floor with eight suites running at once.

        So the removal is asked for until it takes, which is the same shape as every other wait in
        this suite: a condition asked about rather than a window slept through. It cannot hide the
        thing the case is *for* — that a gateway does not put its agent's directory back is proved by
        the assertion after the beats that follow, and a gateway which really did rebuild it would
        rebuild it there too.
        """
        def gone() -> bool:
            shutil.rmtree(at, ignore_errors=True)
            return not at.exists()
        self.assertTrue(support.waited_until(gone, self.PATIENCE),
                        f"{at} could not be taken away: something is writing into it faster than "
                        f"it can be removed")

    def a_day_file_from(self, days_ago: int) -> Path:
        """One of this gateway's own day files, from far enough back that it should be swept."""
        where = standing.logs_at(self.at)
        where.mkdir(parents=True, exist_ok=True)
        when = datetime.datetime.now().astimezone() - datetime.timedelta(days=days_ago)
        one = where / logs.named_for(when)
        one.write_text("[an older day] INFO:   gateway up\n", encoding="utf-8")
        return one

    def an_arrival_from(self, days_ago: int, kind: str = "discord") -> Path:
        """One day's worth of what came in through a channel, from that many days ago."""
        when = datetime.datetime.now() - datetime.timedelta(days=days_ago)
        at = arrivals.arrived_at(self.name, kind, f"m{days_ago}", when)
        at.mkdir(parents=True, exist_ok=True)
        (at / "report.csv").write_text("one,two\n", encoding="utf-8")
        return at

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

        today = host._kept_the_days(self.name, where, "")   # the sweep on the way up

        self.assertFalse(old.exists(), "it did not sweep at all")
        again = self.a_day_file_from(host.KEPT_DAYS + 1)
        self.assertEqual(today, host._kept_the_days(self.name, where, today))
        self.assertTrue(again.exists(), "it swept twice in one day, which is a listing per beat")

        host._kept_the_days(self.name, where, "a day that has now turned")

        self.assertFalse(again.exists(), "the day turned and it never swept again")

    def test_it_sweeps_what_arrived_through_a_channel_on_the_same_beat_it_sweeps_its_own_days(self):
        # Arrivals are the other thing here that gains a directory a day with nobody having decided
        # to keep it, and this loop is the only thing that will ever remove one — `channels.files`
        # has always had the sweep and nothing called it, which is exactly how the day files began.
        where = standing.logs_at(self.at)
        old = self.an_arrival_from(arrivals.KEPT_DAYS + 1)
        recent = self.an_arrival_from(1)

        host._kept_the_days(self.name, where, "")

        self.assertFalse(old.exists(), "a day of arrivals older than any are kept was left standing")
        self.assertTrue(recent.exists(), "it swept a day of arrivals it was told to keep")

    def test_a_channel_directory_it_cannot_read_never_stops_it_sweeping_or_ends_the_gateway(self):
        # Tidying may not end a gateway, and this one walks a directory a stranger's adapter writes
        # into. `_kept_the_days` answers with the day whatever happened, because what it answers is
        # what stops the loop doing the arithmetic every fifteen seconds.
        support.not_as_root(self)
        where = standing.logs_at(self.at)
        old = self.a_day_file_from(host.KEPT_DAYS + 1)
        directory.channels(self.name).mkdir(parents=True, exist_ok=True)
        directory.channels(self.name).chmod(0o000)
        self.addCleanup(directory.channels(self.name).chmod, 0o700)

        today = host._kept_the_days(self.name, where, "")

        self.assertEqual(logs.named_for(datetime.datetime.now()), today)
        self.assertFalse(old.exists(), "an unreadable channel directory stopped the day files being "
                                       "swept at all")

    def a_turn_with_records(self, old: int, recent: int) -> int:
        """One turn carrying records from long ago and records from today."""
        conversation = arriving.asked_at_a_terminal(self.name, "what changed?").conversation
        turn = turns_kept.add_turn(self.name, {"conversation_id": conversation,
                                               "provider_name": "a-stand-in",
                                               "access_mode": "read"})
        long_ago = (datetime.datetime.now(datetime.timezone.utc)
                    - datetime.timedelta(days=host.KEPT_DAYS + 16))
        for n in range(old):
            turns_kept.add_turn_record(self.name, turn, "tool", {"n": n}, when=long_ago)
        for n in range(recent):
            turns_kept.add_turn_record(self.name, turn, "tool", {"n": n})
        return turn

    def test_it_sweeps_what_turns_did_on_the_same_beat(self):
        """`turn_records_days` was configurable, documented, and read by nothing at all — which is
        worse than not offering it, because somebody who set it believed they had bounded
        something."""
        turn = self.a_turn_with_records(old=5, recent=2)
        where = standing.logs_at(self.at)
        where.mkdir(parents=True, exist_ok=True)

        host._kept_the_days(self.name, where, "")

        self.assertEqual(2, len(turns_kept.list_turn_records(self.name, turn)),
                         "what turns did grew without bound however the setting was set")

    def test_the_turn_and_what_was_said_are_never_swept_with_it(self):
        """A turn's own row is the ledger and what was said is the owner's history."""
        turn = self.a_turn_with_records(old=3, recent=0)
        where = standing.logs_at(self.at)
        where.mkdir(parents=True, exist_ok=True)

        host._kept_the_days(self.name, where, "")

        self.assertEqual(turn, turns_kept.get_turn(self.name, turn)["id"])
        self.assertTrue(arriving.conversations(self.name), "a conversation was swept away")

    def test_records_it_cannot_sweep_never_end_the_gateway(self):
        """Tidying may not end a gateway — the same rule the day files are swept under."""
        self.a_turn_with_records(old=1, recent=0)
        where = standing.logs_at(self.at)
        where.mkdir(parents=True, exist_ok=True)
        directory.records(self.name).write_text("this is prose, not a database", encoding="utf-8")

        self.assertEqual(logs.named_for(datetime.datetime.now()),
                         host._kept_the_days(self.name, where, ""))

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
        first = json.loads((self.at / standing.RECORD).read_text(encoding="utf-8"))["since_boot"]

        def a_later_beat_landed() -> bool:
            try:
                now = json.loads(
                    (self.at / standing.RECORD).read_text(encoding="utf-8"))["since_boot"]
                return float(now) > float(first)
            except (OSError, KeyError, TypeError, ValueError):
                return False

        # Holding the gateway lock proves the process was admitted, not that startup settlement
        # has finished. Taking the records away during that settlement tests a startup crash rather
        # than this case's long-running loop. A later beat can land only after settlement and one
        # whole pass through that loop.
        self.assertTrue(support.waited_until(a_later_beat_landed, self.PATIENCE),
                        f"the gateway never finished starting. It said: {self.what_it_said()}")
        self.taken_away(self.at)

        self.several_more_beats()

        self.assertIsNone(
            child.poll(),
            "it ended when its agent went away, which exits non-zero. Captured output:\n"
            + self.what_it_said())
        self.assertFalse(self.at.exists(), "it made its agent's directory again to complain into")


class TheScheduleItHosts(WithAnAgent):
    """A real gateway, a real schedule, and the child it really starts.

    Driven through the same gateway process every other case here uses, because the guarantees are
    about what the *loop* does: when it first looks at the clock, and what it takes down with it.
    `tests/test_schedules_firing.py` proves everything the firing itself promises; what is here is
    only the wiring, which is the part no unit case can see.
    """

    #: A beat long enough that a schedule firing inside it cannot have waited for one. The whole
    #: point of the case below: with the look after the sleep, nothing happens for this long.
    A_LONG_BEAT = 30.0

    #: And one short enough that a case about what the log *says* is not sitting out a beat waiting
    #: for the reaping. What a firing came to is written on the look after it finished, so the
    #: outcome arrives within one beat of the work ending — which is the design, not a delay to
    #: engineer around.
    A_SHORT_BEAT = 1.0

    def given(self, name: str = "tick", command: str = "/bin/echo it ran") -> None:
        kept.added(self.name, name, {"cron": "* * * * *", "command": command})

    def fired(self, name: str = "tick") -> bool:
        return kept.one(self.name, name)["last_fired_for"] is not None

    def test_a_gateway_looks_at_the_clock_as_soon_as_it_has_its_name(self):
        # **Not one interval later.** A schedule is due in one stated minute, so a gateway that
        # waited a whole beat before its first look lost every occurrence due in the last fifteen
        # seconds of the minute it started in — which is exactly the moment a machine restarts one.
        # The beat here is thirty seconds, so a firing that lands promptly cannot have waited for it.
        self.given()
        started = time.monotonic()
        self.a_running_gateway(beat=self.A_LONG_BEAT)
        self.assertTrue(support.waited_until(self.fired, self.PATIENCE),
                        f"it never fired. It said: {self.its_log()}")
        self.assertLess(time.monotonic() - started, self.A_LONG_BEAT,
                        "the first look waited for a beat, so a firing due in that window is lost")

    def test_the_beat_still_waits_before_saying_anything(self):
        # The other half, and it is the opposite decision: saying a gateway is working before it has
        # done any work is a report with nothing behind it. Looking at the clock first must not have
        # moved the beat forward with it.
        self.given()
        child = self.a_running_gateway(beat=self.A_LONG_BEAT)
        self.assertTrue(support.waited_until(self.fired, self.PATIENCE))
        how = standing.standing(self.at)
        self.assertEqual(child.pid, how.pid)
        self.assertFalse(how.stale, "a gateway that has only just come up already reads as wedged")

    def test_a_gateway_says_in_its_own_log_that_a_schedule_ran_and_what_it_came_to(self):
        # The whole reason somebody opens this file: it ran, it finished, or it failed and why.
        self.given(command="/bin/sh -c 'echo the work happened; exit 0'")
        self.a_running_gateway(beat=self.A_SHORT_BEAT)
        self.assertTrue(support.waited_until(
            lambda: "completed" in self.its_log(), self.PATIENCE),
            f"it never said what became of the schedule. It said: {self.its_log()}")
        said = self.its_log()
        self.assertIn("schedule tick is due for", said)
        self.assertIn("schedule tick started as pid", said)
        self.assertIn("the work happened", said)

    def test_a_schedule_that_failed_says_why_in_the_gateways_own_log(self):
        self.given(command="/bin/sh -c 'echo it went wrong >&2; exit 3'")
        self.a_running_gateway(beat=self.A_SHORT_BEAT)
        self.assertTrue(support.waited_until(
            lambda: "failed with exit 3" in self.its_log(), self.PATIENCE),
            f"a failure was never reported. It said: {self.its_log()}")
        self.assertIn("it went wrong", self.its_log())

    def test_an_orderly_stop_takes_the_work_a_schedule_started_with_it(self):
        # A child is in a session of its own, so launchd's group-wide cleanup of this job cannot
        # reach it: if the gateway does not stop it, nothing ever will.
        self.given(command="/bin/sh -c 'while true; do sleep 0.05; done'")
        child = self.a_running_gateway(beat=self.A_LONG_BEAT)
        # **Waited for by the line the gateway writes, not by the lock.** The lock is taken by the
        # gateway *before* it spawns — that is what stops two of them starting one schedule — so it
        # goes to "running" a moment before there is anything to stop, and a case that signalled
        # there was signalling a gateway that had not taken hold of the work yet. It failed one run
        # in five on the 3.9 floor and never on a current interpreter, which is exactly the shape of
        # a race nobody notices until CI does.
        self.assertTrue(support.waited_until(
            lambda: "started as pid" in self.its_log(), self.PATIENCE),
            f"the work never started. It said: {self.its_log()}")

        child.send_signal(signal.SIGTERM)
        self.assertTrue(support.waited_until(lambda: child.poll() is not None, self.PATIENCE))

        self.assertTrue(support.waited_until(
            lambda: not firing.still_running(self.name, "tick"), self.PATIENCE),
            "the gateway stopped and left the work it started running with nobody holding it")
        self.assertEqual(kept.STOPPED, kept.one(self.name, "tick")["last_outcome"])

    def test_a_second_stop_arriving_during_the_shutdown_does_not_crash_the_gateway(self):
        # **The window this work opened.** Before schedules there was nothing on the `ExitStack` to
        # unwind, so a second signal during shutdown had nothing to interrupt. Now the unwind stops
        # every child a schedule started and may spend up to `STOPPING_WITHIN` seconds doing it — and
        # `Stopped` is a `BaseException` precisely so `firing`'s guards cannot swallow it, so a
        # second `SIGTERM` in that window escaped `run` entirely. Exit non-zero under
        # `KeepAlive {SuccessfulExit: false}` is *bring it back*, so a clean stop became the endless
        # restart this module is arranged to make unreachable — and the children not yet reached were
        # left running with nothing holding them.
        self.given(command="/bin/sh -c 'trap \"\" TERM; while true; do sleep 0.05; done'")
        child = self.a_running_gateway(beat=self.A_LONG_BEAT)
        self.assertTrue(support.waited_until(
            lambda: "started as pid" in self.its_log(), self.PATIENCE),
            f"the work never started. It said: {self.its_log()}")

        child.send_signal(signal.SIGTERM)
        # **Waited for, and the wait is what gives this case teeth.** Sent immediately, the second
        # signal lands while the gateway is still inside its own `except Stopped` and is caught
        # exactly as the first was — the case then passes with the guard deleted, which is how it
        # first read. The line below is written *after* the handlers have been stood down, so seeing
        # it means the shutdown proper has begun; and the child ignores `SIGTERM`, so the stop that
        # follows spends seconds asking, waiting, and only then telling. That is the window.
        self.assertTrue(support.waited_until(
            lambda: "gateway stopping for" in self.its_log(), self.PATIENCE),
            f"it never began stopping. It said: {self.its_log()}")
        for _again in range(3):
            if child.poll() is None:
                child.send_signal(signal.SIGTERM)

        self.assertTrue(support.waited_until(lambda: child.poll() is not None, self.PATIENCE),
                        f"it never ended. It said: {self.its_log()}")
        self.assertEqual(OK, child.returncode,
                         "a gateway asked to stop twice exited non-zero, which launchd reads as a "
                         f"request to be restarted. It said: {self.its_log()}")

    def test_a_schedule_that_could_not_run_never_takes_the_gateway_down(self):
        # Under `KeepAlive {SuccessfulExit: false}` a non-zero exit is a request to be restarted, so
        # a firing that ended the process would be a permanent condition turned into a loop.
        self.given(command="/no/such/program at all")
        child = self.a_running_gateway(beat=1.0)
        self.assertTrue(support.waited_until(
            lambda: "did not start" in self.its_log(), self.PATIENCE),
            f"it never tried. It said: {self.its_log()}")
        self.assertIsNone(child.poll(), "a schedule that could not run ended the gateway")


class TheChannelsItHosts(WithAnAgent):
    """A real gateway, a real channel, and the adapter it really starts.

    The second tenant, wired through the same gateway process every other case here uses.
    `tests/test_channels_hosting.py` proves everything hosting an adapter promises on its own; what
    is here is only what a *supervised process* adds — that a channel cannot stop a gateway starting,
    that what leaves through one really leaves, and that a stop takes the adapter with it.
    """

    #: Short enough that a case is not sitting out a beat waiting for the loop to come round, and
    #: long enough to still be a loop. The adapters are started on the loop's first pass, so most
    #: cases here would be answered on any beat at all; the schedule cases need several passes.
    A_SHORT_BEAT = 1.0

    def setUp(self) -> None:
        super().setUp()
        # `paths.code()` answers with the checkout when the scratch root has no installed tree, and
        # a case writing an adapter would then write one into the repository. Made here for the same
        # reason `tests/test_channels_hosting.py` makes it.
        (self.home / "app" / "src").mkdir(parents=True, exist_ok=True)
        self.adapters = paths.code() / "channels"
        self.adapters.mkdir(parents=True, exist_ok=True)
        self.heard = self.home / "heard.txt"

    def an_adapter(self, kind: str = "discord", body: str = AN_ADAPTER) -> Path:
        at = self.adapters / kind
        at.write_text(body, encoding="utf-8")
        at.chmod(0o755)
        return at

    def a_channel(self, kind: str = "discord", told: bool = True, needing: Tuple[str, ...] = ()
                  ) -> None:
        channels.added(self.name, kind, {
            "describes": kind, "allowed": json.dumps(["2207"]),
            "secret_names": json.dumps(list(needing)),
            "settings": json.dumps({"heard": str(self.heard)})})
        if told:
            channels.telling(self.name, kind, "1180")

    def was_heard(self) -> str:
        """Everything the adapter was really asked to deliver, as the adapter itself saw it."""
        return self.heard.read_text(encoding="utf-8") if self.heard.exists() else ""

    def several_beats(self) -> None:
        """A window rather than a question, for the two cases about something that must *not* happen.

        The same shape and the same reasoning as `WhatItGoesOnDoingForMonths.several_more_beats`:
        there is nothing to wait *for* when what is being proved is a silence, so the wait is a few
        passes of a loop the case has already made fast.
        """
        time.sleep(self.A_SHORT_BEAT * 3)

    def a_hosted_channel(self, body: str = AN_ADAPTER) -> hosting.Watching:
        """The adapter hosted in *this* process, so a case can call `_told` and read its answer.

        Every other case here drives a real gateway subprocess, which is what proves supervision.
        These two are about what one function answers, and its answer cannot be read across a fork.
        """
        self.an_adapter(body=body)
        self.a_channel()
        where = standing.logs_at(self.at)
        watching = hosting.looked(self.name, where, hosting.Watching({}, {}, {}))
        self.addCleanup(hosting.stopping, self.name, where, watching, 4.0)
        self.assertTrue(support.waited_until(
            lambda: hosting.connected(watching, "discord"), self.PATIENCE),
            "the adapter never connected")
        return watching

    def where_it_logs(self):
        return standing.logs_at(self.at)

    def test_a_notice_the_platform_refused_is_not_reported_as_told(self):
        # **`TOLD` meant *written to a pipe*, and a caller deciding whether to write something down
        # read it as *a person saw this*.** The goodbye is the measured case: it waits a round trip
        # precisely because the adapter is signalled a moment later, and a platform refusing it came
        # back indistinguishable from one that took it — so a gateway could report that it had said
        # farewell when the words were refused.
        watching = self.a_hosted_channel(body=AN_ADAPTER_THAT_IS_REFUSED)
        self.assertEqual(host.REFUSED,
                         host._told(self.name, self.where_it_logs(), watching, host.WENT_DOWN,
                                    landed_within=3.0))

    def test_a_notice_nobody_refused_is_still_told(self):
        # Silence goes on reading as landed: an adapter is free to acknowledge nothing at all, and
        # this one does exactly that. Treating *nothing said* as a refusal would report a failure
        # for every whole adapter that simply does not answer.
        #
        # A short ceiling on purpose. This one is waiting for something that never arrives, so the
        # whole of it is spent — and every second of it is a second the rest of this file's
        # `waited_until` ceilings are competing with on a loaded runner.
        watching = self.a_hosted_channel()
        self.assertEqual(host.TOLD,
                         host._told(self.name, self.where_it_logs(), watching, host.WENT_DOWN,
                                    landed_within=0.5))

    def test_a_refused_notice_is_said_once_and_not_twice(self):
        # A caller that hands a list in is going to say what it makes of the refusal — the scheduled
        # report says which files it then went without — so this saying it as well would be two
        # accounts of one refusal. Said here only when nobody asked.
        watching = self.a_hosted_channel(body=AN_ADAPTER_THAT_IS_REFUSED)
        asked_for: List[str] = []
        self.assertEqual(host.REFUSED,
                         host._told(self.name, self.where_it_logs(), watching, host.WENT_DOWN,
                                    landed_within=3.0, refusals=asked_for))
        self.assertEqual(1, len(asked_for), "the caller that asked for the reason never got it")
        self.assertNotIn("the notice for", self.its_log(),
                         "a refusal somebody asked for was announced a second time as well")

        # Asked of this sentence and not of the reason, which `hosting._refused` already writes for
        # every refusal either way — an assertion on "429" alone would stay green with the whole of
        # this branch deleted.
        host._told(self.name, self.where_it_logs(), watching, host.WENT_DOWN, landed_within=2.0)
        self.assertIn(f"the notice for {self.name} was refused", self.its_log(),
                      "a refusal nobody asked for reached nobody at all")

    def test_a_gateway_starts_the_adapter_for_a_configured_channel(self):
        self.an_adapter()
        self.a_channel()
        self.a_running_gateway(beat=self.A_SHORT_BEAT)
        self.assertTrue(support.waited_until(
            lambda: "channel discord: started as pid" in self.its_log(), self.PATIENCE),
            f"no adapter was ever started. It said: {self.its_log()}")
        self.assertTrue(support.waited_until(
            lambda: hosting.still_running(self.name, "discord"), self.PATIENCE),
            "the claim was never taken, so nothing is holding this channel")

    def test_a_gateway_that_came_up_says_so_through_the_channel_that_is_told_things(self):
        # Not into the log — a person who wanted to know their gateway is back is not reading a file
        # on the machine it is running on. The one channel marked `notified` is where it lands.
        self.an_adapter()
        self.a_channel()
        self.a_running_gateway(beat=self.A_SHORT_BEAT)
        self.assertTrue(support.waited_until(lambda: host.CAME_UP in self.was_heard(),
                                             self.PATIENCE),
                        f"nobody was told. It said: {self.its_log()}")
        self.assertIn("1180 ::", self.was_heard(), "it went somewhere other than the told place")
        # **A colour and a word, and nothing under it.** A version and a process id are what
        # somebody debugging wants and they are in the log, where debugging is done; on a channel
        # they are noise arriving in the middle of a conversation.
        self.assertNotIn(__version__, self.was_heard())
        self.assertNotIn(str(self.name) + " on", self.was_heard())

    def test_a_gateway_returning_from_an_update_names_and_links_the_installed_release(self):
        self.an_adapter()
        self.a_channel()
        notes = f"https://github.com/rundesk-ai/rundesk-cli/releases/tag/v{__version__}"
        maintenance.installed(self.at, __version__, notes)

        self.a_running_gateway(beat=self.A_SHORT_BEAT)

        expected = maintenance.INSTALLED.format(version=__version__, notes=notes)
        self.assertTrue(support.waited_until(lambda: expected in self.was_heard(), self.PATIENCE),
                        f"nobody was told. It said: {self.its_log()}")
        self.assertNotIn(host.CAME_UP, self.was_heard())
        self.assertFalse((self.at / maintenance.MARKER).exists())

    def test_an_agent_that_tells_nobody_anything_is_a_gateway_that_says_nothing(self):
        # `delivery.notice` answers `None`, which is an ordinary answer rather than a failure: an
        # agent with no notified channel is one somebody configured to be quiet.
        self.an_adapter()
        self.a_channel(told=False)
        child = self.a_running_gateway(beat=self.A_SHORT_BEAT)
        self.assertTrue(support.waited_until(
            lambda: "channel discord: started as pid" in self.its_log(), self.PATIENCE),
            f"no adapter was ever started. It said: {self.its_log()}")

        self.several_beats()

        self.assertEqual("", self.was_heard(), "it told a channel nobody marked as the told one")
        self.assertIsNone(child.poll(), "having nobody to tell ended the gateway")

    def test_a_gateway_asked_to_stop_says_so_through_the_channel_before_it_goes(self):
        # It has to leave *before* the stack unwinds, because unwinding it is what closes the
        # adapter the notice leaves through.
        self.an_adapter()
        self.a_channel()
        child = self.a_running_gateway(beat=self.A_SHORT_BEAT)
        self.assertTrue(support.waited_until(lambda: host.CAME_UP in self.was_heard(),
                                             self.PATIENCE), self.its_log())

        os.kill(child.pid, signal.SIGTERM)
        self.assertTrue(support.waited_until(lambda: child.poll() is not None, self.PATIENCE))

        self.assertTrue(support.waited_until(
            lambda: host.WENT_DOWN in self.was_heard(), self.PATIENCE),
            f"it went down without telling anybody. It heard: {self.was_heard()}")
        self.assertEqual(OK, child.returncode)

    def test_a_credential_of_this_agents_own_survives_a_full_stop_and_start(self):
        # **The release gate for per-agent credentials, asked of a supervised process.** Everything
        # about resolution is proved in `tests/test_channels_credentials.py` and
        # `tests/test_channels_hosting.py`; what only this can prove is that a whole gateway going
        # away and a whole new one coming up resolves it again — the adapter here exits `EX_CONFIG`
        # without a token, so a second gateway that failed to resolve one is a notified channel that
        # never says a word.
        #
        # Only the agent's own name is set. The install-wide one holds nothing at all, so nothing
        # here can pass on the fallback.
        secrets.stated("DISCORD_BOT_TOKEN__COLE", A_BOT_TOKEN)
        self.an_adapter(body=AN_ADAPTER_THAT_NEEDS_ITS_CREDENTIAL)
        self.a_channel(needing=("DISCORD_BOT_TOKEN",))

        first = self.a_running_gateway(beat=self.A_SHORT_BEAT)
        self.assertTrue(support.waited_until(lambda: host.CAME_UP in self.was_heard(),
                                             self.PATIENCE),
                        f"the notified channel never connected. It said: {self.its_log()}")

        os.kill(first.pid, signal.SIGTERM)
        self.assertTrue(support.waited_until(lambda: first.poll() is not None, self.PATIENCE))
        self.assertTrue(support.waited_until(
            lambda: not hosting.still_running(self.name, "discord"), self.PATIENCE),
            "the adapter outlived the gateway that started it")
        self.heard.unlink()

        self.a_running_gateway(beat=self.A_SHORT_BEAT)
        self.assertTrue(support.waited_until(lambda: host.CAME_UP in self.was_heard(),
                                             self.PATIENCE),
                        f"the notified channel never reconnected. It said: {self.its_log()}")

    def test_a_gateway_returning_from_an_update_reconnects_on_the_agents_own_credential(self):
        # **The update handoff carries no credential, and must not need to.** What crosses between
        # the old gateway and the new one is a small intent file beside the agent; the sealed store
        # is under `data/`, which an update never touches. So the returning release resolves the
        # value again from nothing but the store — and the proof is that a channel whose adapter
        # exits `EX_CONFIG` without a token still reaches the notified place.
        secrets.stated("DISCORD_BOT_TOKEN__COLE", A_BOT_TOKEN)
        self.an_adapter(body=AN_ADAPTER_THAT_NEEDS_ITS_CREDENTIAL)
        self.a_channel(needing=("DISCORD_BOT_TOKEN",))
        notes = f"https://github.com/rundesk-ai/rundesk-cli/releases/tag/v{__version__}"
        maintenance.installed(self.at, __version__, notes)

        self.a_running_gateway(beat=self.A_SHORT_BEAT)

        expected = maintenance.INSTALLED.format(version=__version__, notes=notes)
        self.assertTrue(support.waited_until(lambda: expected in self.was_heard(), self.PATIENCE),
                        f"the channel never came back after an update. It said: {self.its_log()}")
        self.assertNotIn(A_BOT_TOKEN, self.was_heard() + self.its_log() + self.what_it_said())

    def test_nothing_a_gateway_writes_anywhere_holds_the_credential_it_resolved(self):
        # Read out of every place a value could leak from a supervised run: the process output a
        # supervisor captures, the agent's own day log, the adapter's error file, and what really
        # went out through the channel.
        secrets.stated("DISCORD_BOT_TOKEN__COLE", A_BOT_TOKEN)
        self.an_adapter(body=AN_ADAPTER_THAT_NEEDS_ITS_CREDENTIAL)
        self.a_channel(needing=("DISCORD_BOT_TOKEN",))
        self.a_running_gateway(beat=self.A_SHORT_BEAT)
        self.assertTrue(support.waited_until(lambda: host.CAME_UP in self.was_heard(),
                                             self.PATIENCE), self.its_log())

        errors = hosting.errors_of(self.name, "discord")
        written = "".join([
            self.what_it_said(), self.its_log(), self.was_heard(),
            errors.read_text(encoding="utf-8", errors="replace") if errors.exists() else "",
            json.dumps(channels.one(self.name, "discord")),
        ])
        self.assertNotIn(A_BOT_TOKEN, written)
        # And the value is not copied under a second name either — one place keeps it, and
        # `channels.credentials` resolves rather than duplicates.
        self.assertEqual(["DISCORD_BOT_TOKEN__COLE"],
                         [one for one in secrets.names() if one.startswith("DISCORD_BOT_TOKEN")])

    def test_a_gateway_stood_down_for_an_update_uses_the_maintenance_notice(self):
        self.an_adapter()
        self.a_channel()
        child = self.a_running_gateway(beat=self.A_SHORT_BEAT)
        self.assertTrue(support.waited_until(lambda: host.CAME_UP in self.was_heard(),
                                             self.PATIENCE), self.its_log())
        maintenance.installing(self.at, "0.37.0")

        os.kill(child.pid, signal.SIGTERM)
        self.assertTrue(support.waited_until(lambda: child.poll() is not None, self.PATIENCE))

        self.assertTrue(support.waited_until(
            lambda: maintenance.INSTALLING in self.was_heard(), self.PATIENCE),
            f"it went down without the update notice. It heard: {self.was_heard()}")
        self.assertNotIn(host.WENT_DOWN, self.was_heard())
        self.assertFalse((self.at / maintenance.MARKER).exists())

    def test_a_schedule_that_failed_is_told_and_one_that_worked_is_not(self):
        # **The restraint is the guarantee.** A notice for every successful nightly job is how
        # somebody learns to ignore the channel, and the one they then miss is this one — so the
        # case asserts the silence as hard as it asserts the sentence, with a schedule that really
        # did complete standing beside the one that really did fail.
        self.an_adapter()
        self.a_channel()
        kept.added(self.name, "good", {"cron": "* * * * *", "command": "/bin/echo it worked"})
        kept.added(self.name, "bad", {"cron": "* * * * *",
                                      "command": "/bin/sh -c 'echo it went wrong >&2; exit 3'"})
        self.a_running_gateway(beat=self.A_SHORT_BEAT)

        self.assertTrue(support.waited_until(
            lambda: "schedule bad failed with exit 3" in self.was_heard(), self.PATIENCE),
            f"a failing schedule told nobody. It heard: {self.was_heard()}. "
            f"It said: {self.its_log()}")
        self.assertIn("schedule good completed", self.its_log(),
                      "the schedule that worked never finished, so its silence proves nothing")
        self.assertNotIn("schedule good", self.was_heard(),
                         "a schedule that worked perfectly was announced to a person")

    def test_a_channel_whose_adapter_is_not_installed_never_stops_a_gateway_starting(self):
        # **Nothing about a channel is in `_may_not_run`.** A platform that is down, a credential
        # that has expired, an adapter somebody never installed — every one of those is a condition
        # a gateway should be up and complaining about, and a refusal here would take an agent's
        # whole gateway away over a misconfiguration in one of its channels.
        self.a_channel()                                 # and deliberately no adapter written
        child = self.a_running_gateway(beat=self.A_SHORT_BEAT)

        self.assertTrue(support.waited_until(
            lambda: "channel discord: did not start" in self.its_log(), self.PATIENCE),
            f"it never even tried. It said: {self.its_log()}")
        self.several_beats()
        self.assertIsNone(child.poll(), "a channel that could not start ended the gateway")
        self.assertEqual(standing.ONLINE, standing.standing(self.at).how)

    def test_an_orderly_stop_takes_the_adapter_it_started_with_it(self):
        # An adapter is in a session of its own, so launchd's group-wide cleanup of this job cannot
        # reach it either: if the gateway does not stop it, nothing ever will and the next gateway
        # finds the channel claimed by something nobody can account for.
        self.an_adapter()
        self.a_channel()
        child = self.a_running_gateway(beat=self.A_SHORT_BEAT)
        # **Waited for by the line the gateway writes, not by the claim** — the same race
        # `TheScheduleItHosts` records, and it bites harder here. The claim is taken *before* the
        # adapter is spawned, so `still_running` answers yes for the instant the gateway itself
        # holds it and there is nothing yet to stop; a case that signalled there raised `Stopped`
        # inside `_started`, and the gateway went down having taken hold of nothing at all.
        self.assertTrue(support.waited_until(
            lambda: "channel discord: started as pid" in self.its_log(), self.PATIENCE),
            f"the adapter never came up. It said: {self.its_log()}")

        os.kill(child.pid, signal.SIGTERM)
        self.assertTrue(support.waited_until(lambda: child.poll() is not None, self.PATIENCE))

        self.assertIn("stopped with this gateway", self.its_log())
        self.assertFalse(hosting.still_running(self.name, "discord"),
                         "the gateway stopped and left its adapter running with nobody holding it")

    def a_grant(self, name: str) -> Path:
        """A skill standing in this agent's own directory. Made by hand, because what the loop
        watches is the directory and not the command that usually writes it — which is the whole
        reason it watches rather than being told."""
        stands = grants.where(self.name) / name
        stands.mkdir(parents=True, exist_ok=True)
        (stands / library.DECLARED).write_text(
            f"---\nname: {name}\ndescription: Something. Use when something.\n---\n",
            encoding="utf-8")
        return stands

    def test_a_skill_the_agent_gained_is_told_through_the_channel_that_is_told_things(self):
        self.an_adapter()
        self.a_channel()
        self.a_grant("jira")                       # held before it starts, so the first look is quiet
        child = self.a_running_gateway(beat=self.A_SHORT_BEAT)
        self.assertTrue(support.waited_until(lambda: host.CAME_UP in self.was_heard(),
                                             self.PATIENCE))

        self.a_grant("writing-plans")

        self.assertTrue(
            support.waited_until(
                lambda: "🧩 Skill granted — `writing-plans`" in self.was_heard(), self.PATIENCE),
            f"nothing was said about it. It heard: {self.was_heard()}")
        self.assertIn("1180 ::", self.was_heard())
        self.assertIsNone(child.poll(), "the gateway went down saying it")

    def test_a_skill_the_agent_lost_is_told_the_same_way(self):
        self.an_adapter()
        self.a_channel()
        self.a_grant("jira")
        self.a_running_gateway(beat=self.A_SHORT_BEAT)
        self.assertTrue(support.waited_until(lambda: host.CAME_UP in self.was_heard(),
                                             self.PATIENCE))

        shutil.rmtree(grants.where(self.name) / "jira")

        self.assertTrue(
            support.waited_until(lambda: "🗑️ Skill revoked — `jira`" in self.was_heard(),
                                 self.PATIENCE),
            f"nothing was said about it. It heard: {self.was_heard()}")

    def test_a_first_look_after_an_upgrade_announces_nothing(self):
        # Two grants already standing and nothing written down: the gateway comes up, says so, and
        # says nothing whatever about skills the agent has held all along.
        self.an_adapter()
        self.a_channel()
        self.a_grant("jira")
        self.a_grant("writing-plans")

        child = self.a_running_gateway(beat=self.A_SHORT_BEAT)
        self.assertTrue(support.waited_until(lambda: host.CAME_UP in self.was_heard(),
                                             self.PATIENCE))
        self.several_beats()

        self.assertNotIn("Skill", self.was_heard())
        self.assertIsNone(child.poll())

    def test_a_change_is_told_once_however_many_beats_pass(self):
        # The rule this loop shares with every other one here: none of them may say the same thing
        # every fifteen seconds.
        self.an_adapter()
        self.a_channel()
        self.a_grant("jira")
        self.a_running_gateway(beat=self.A_SHORT_BEAT)
        self.assertTrue(support.waited_until(lambda: host.CAME_UP in self.was_heard(),
                                             self.PATIENCE))
        self.a_grant("writing-plans")
        self.assertTrue(support.waited_until(
            lambda: "writing-plans" in self.was_heard(), self.PATIENCE))

        self.several_beats()

        self.assertEqual(1, self.was_heard().count("🧩 Skill granted — `writing-plans`"))

    def test_an_agent_that_tells_nobody_anything_hears_nothing_about_its_skills(self):
        self.an_adapter()
        self.a_channel(told=False)
        self.a_grant("jira")
        child = self.a_running_gateway(beat=self.A_SHORT_BEAT)
        self.several_beats()

        self.a_grant("writing-plans")
        self.several_beats()

        self.assertEqual("", self.was_heard())
        self.assertIsNone(child.poll(), "the gateway went down over having nobody to tell")


class WhatItMayDo(WithAnAgent):
    """The loop that says when this agent gains or loses a skill.

    Driven directly, the way `_kept_the_days` is: what these prove is the carrier and the file, and
    a real gateway is the wrong instrument for "and then it wrote nothing".
    """

    def setUp(self) -> None:
        super().setUp()
        self.where = standing.logs_at(self.at)
        library.where().mkdir(parents=True, exist_ok=True)
        catalogs.place_bundled()

    def a_channel(self) -> None:
        """A channel this agent is told things through, with no adapter running for it."""
        channels.added(self.name, "discord", {
            "describes": "discord", "allowed": json.dumps(["2207"])})
        channels.telling(self.name, "discord", "1180")

    def a_skill(self, name: str) -> None:
        """A grant standing in the agent's own directory, made the way every grant is."""
        source = library.tree(library.BUNDLED) / library.INSIDE / library.REQUIRED_SKILL
        stands = grants.where(self.name)
        stands.mkdir(parents=True, exist_ok=True)
        (stands / name).symlink_to(os.path.relpath(source, stands))

    def look(self, knew=None):
        return host._told_what_changed(self.name, self.where, hosting.Watching({}, {}, {}), knew)

    def test_a_first_look_says_nothing_at_all(self):
        # Otherwise the one startup after an upgrade announces every skill the agent already holds
        # as newly gained — a paragraph of noise in somebody's chat for no change at all.
        #
        # **Asserted on whether anything was *said*, not on what came back.** Both answers are the
        # same tuple, so a case reading only the carrier cannot tell a quiet first look from one that
        # announced everything — which is how this case was first written and why it proved nothing.
        self.a_skill("jira")
        with mock.patch.object(host, "_told", return_value=host.TOLD) as told:
            self.assertEqual(("jira",), self.look())
        told.assert_not_called()

    def test_a_skill_granted_and_revoked_between_two_looks_leaves_nothing_to_say(self):
        # Worked out afresh against what was last *said*, never accumulated.
        self.assertEqual(("jira",), self.look(("jira",)))

    def test_the_lines_it_composes_name_the_skill_and_say_which_way_it_went(self):
        self.assertEqual(["🧩 Skill granted — `b`", "🗑️ Skill revoked — `a`"],
                         host._what_changed(("a",), ("b",)))

    def test_several_changes_at_once_are_one_message(self):
        # A catalog update that retires six skills is one change to what this agent can do, not six
        # notifications.
        said = host._what_changed(("a", "b"), ("c", "d", "e"))
        self.assertEqual(5, len(said))
        self.assertTrue(said[0].startswith("🧩"), "gains are not first")

    def test_a_change_waits_for_a_surface_rather_than_being_lost(self):
        # A notified channel with no adapter up. Nothing is offered to it at all, and nothing is
        # written down, so the change is still owed after a restart.
        #
        # **The gate is asked before `_told`, and that is the point being pinned.** `hosting.told`
        # answers `False` only when there is no child; an adapter that has been started and has not
        # authenticated takes the write into its pipe and answers `True`, so a change offered before
        # the gate is a change nobody ever sees and the record says it was told.
        self.a_channel()
        self.a_skill("jira")
        with mock.patch.object(host, "_told", return_value=host.TOLD) as told:
            self.assertEqual((), self.look(()),
                             "a change nobody could be told was carried forward as said")
        told.assert_not_called()

    def test_an_agent_that_tells_nobody_anything_still_tracks_what_it_may_do(self):
        # There is no channel and there never will be until somebody marks one, so the baseline
        # tracks quietly — otherwise an owner who adds a channel in November is greeted by every
        # grant they made since March.
        self.a_skill("jira")
        self.assertEqual(("jira",), self.look(()))

    def test_a_home_that_is_not_there_is_not_an_agent_that_lost_every_skill(self):
        # Absent is not empty. And the write must not put the directory back: `files.write_json`
        # makes the directory it writes into.
        shutil.rmtree(grants.where(self.name), ignore_errors=True)
        self.assertEqual(("jira",), self.look(("jira",)))
        self.assertFalse(grants.where(self.name).exists(), "it put the agent's directory back")

    def test_grants_that_cannot_be_read_change_nothing_and_never_raise(self):
        # Nothing in this loop may exit non-zero: launchd would bring the gateway straight back into
        # the same condition.
        support.not_as_root(self)
        self.a_skill("jira")
        grants.where(self.name).chmod(0o000)
        self.addCleanup(grants.where(self.name).chmod, 0o755)
        self.assertEqual(("jira",), self.look(("jira",)))


class TheStopFitsInsideWhatTheJobAllows(unittest.TestCase):
    """The one number this module shares with the layer above it, and cannot import.

    `host` may not import `job` — a process never talks to its own supervisor — so the budget a
    shutdown has and the `ExitTimeOut` the job hands it are two constants that have to agree with
    nothing forcing them to. Above it, launchd `SIGKILL`s the gateway partway through stopping its
    children and every one of them is orphaned still holding its lock.
    """

    def test_a_gateways_stop_budget_leaves_room_inside_the_jobs_exit_timeout(self):
        self.assertLess(host.STOPPING_WITHIN, job.EXIT_TIMEOUT,
                        "a gateway may spend longer stopping its children than launchd allows it "
                        "to live, which orphans every one of them")

    def test_the_budget_is_not_so_small_that_nothing_can_be_stopped_in_it(self):
        self.assertGreater(host.STOPPING_WITHIN, firing.STOPPING_LEAST)

    def test_every_tenant_that_stops_children_is_given_a_share_rather_than_the_whole_budget(self):
        # **The arithmetic that reads as correct at every line and takes forty seconds.** Two things
        # this gateway hosts have children to stop, and handing each the whole of `STOPPING_WITHIN`
        # spends it twice against an `ExitTimeOut` of twenty-five — after which launchd `SIGKILL`s
        # the gateway partway through the second one and orphans every child it never reached.
        #
        # Counted off the teardown stack rather than asserted as a number, because the way this goes
        # wrong is a *third* tenant being registered by somebody who never read this file.
        said = (support.CHECKOUT / "src" / "rundesk" / "gateways" / "host.py").read_text()
        self.assertEqual(host.STOPPING_SHARES, said.count("held.callback("),
                         "a tenant was added to the shutdown without the budget being divided "
                         "again — every share here is now larger than the gateway's whole window")

    def test_each_share_is_still_enough_to_stop_a_child_with(self):
        # Divided too far is the same failure from the other side: a share below what either tenant
        # will spend per child is a budget that stopped bounding anything.
        each = host.STOPPING_WITHIN / host.STOPPING_SHARES
        self.assertGreater(each, firing.STOPPING_LEAST)
        self.assertGreater(each, hosting.STOPPING_LEAST)

    def test_a_request_to_stop_is_not_something_a_generic_guard_can_swallow(self):
        # `Stopped` is raised from a signal handler, so it lands wherever the interpreter happens to
        # be — including inside `schedules.firing`, whose whole contract is that no ordinary failure
        # may end a gateway and which therefore guards its work with `suppress(Exception)`. Derived
        # from `Exception` the request was eaten there, the signal was spent, and the gateway went
        # back to sleep unstoppable short of a second `SIGTERM` — inside a twenty-five second window
        # after which launchd `SIGKILL`s it. This is why `KeyboardInterrupt` is a `BaseException`.
        self.assertFalse(issubclass(host.Stopped, Exception),
                         "a stop a generic `except Exception` can swallow is a gateway that cannot "
                         "be stopped from inside a guarded call")
        with self.assertRaises(host.Stopped):
            with contextlib.suppress(Exception):
                raise host.Stopped("asked to stop")


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


#: One that answers a delivery the way a real platform's adapter does — with what the platform then
#: called the message — and writes down whether rundesk asked it to be posted as a reply. Both are
#: needed here: the acknowledgement is the only moment rundesk can learn the id, and the `reply_to`
#: is the whole of what makes a report arrive underneath the notice rather than loose in a room.
AN_ADAPTER_THAT_NAMES_WHAT_IT_POSTED = """#!/usr/bin/env python3
import json, os, signal, sys
if "--capabilities" in sys.argv:
    print(json.dumps({"stream": True, "max_text": 2000})); raise SystemExit(0)
signal.signal(signal.SIGTERM, signal.SIG_IGN)
settings = json.loads(os.environ.get("RUNDESK_SETTINGS") or "{}")
print(json.dumps({"say": "ready", "as": "a-bot"}), flush=True)
posted = 0
for line in sys.stdin:
    try:
        record = json.loads(line)
    except ValueError:
        continue
    if record.get("do") == "stop":
        break
    if record.get("do") == "deliver":
        posted += 1
        named = "msg-%d" % posted
        with open(settings["heard"], "a") as writing:
            writing.write(json.dumps({"place": record.get("place", ""),
                                      "text": record.get("text", ""),
                                      "files": record.get("files", []),
                                      "reply_to": record.get("reply_to"),
                                      "external_id": named}) + "\\n")
        print(json.dumps({"say": "delivered", "id": record.get("id"),
                          "external_id": named}), flush=True)
"""


class WhatAScheduledRunSaysOnASurface(TheChannelsItHosts):
    """R-SCH-46. The clock's work, reaching the place its owner already looks.

    Work that ran at three in the morning is no use in an account nobody opens until they think to.
    So a run that somebody will be shown the answer to says when it begins, and its report arrives
    underneath that notice — one message at the start, one at the end, and nothing in between.
    """

    def a_stand_in_brain(self) -> str:
        """A real provider adapter on this install, so a scheduled turn genuinely answers."""
        records.stated(directory.records(self.name), {"provider_name": support.A_STAND_IN})
        return support.A_STAND_IN

    def what_was_posted(self) -> List[dict]:
        """Every delivery the adapter really took, as objects, oldest first."""
        if not self.heard.exists():
            return []
        return [json.loads(one) for one in self.heard.read_text(encoding="utf-8").splitlines()
                if one.strip()]

    def of_a_schedule(self) -> List[dict]:
        """Only what was posted about the schedule, so the gateway's own hello is not counted."""
        return [one for one in self.what_was_posted()
                if host.CAME_UP not in one["text"] and host.WENT_DOWN not in one["text"]]

    def a_gateway_running_one_schedule(self, prompt: str = "Post the weekday client update."):
        """A gateway whose channel is **already connected** before its schedule comes due.

        The order is the case's whole setup and not a convenience. A schedule is read off the
        records on every beat, so adding the row after the adapter has said `ready` is what puts the
        run in the ordinary condition — a gateway that has been up for a while. Added before, the
        first beat fires it while the adapter is still importing its platform's library, and what
        this class is about would be tested against a gateway that had nobody to talk to.
        """
        self.an_adapter(body=AN_ADAPTER_THAT_NAMES_WHAT_IT_POSTED)
        self.a_channel()
        self.a_stand_in_brain()
        child = self.a_running_gateway(beat=self.A_SHORT_BEAT)
        self.assertTrue(support.waited_until(
            lambda: "channel discord: connected" in self.its_log(), self.PATIENCE),
            f"the adapter never connected. It said: {self.its_log()}")
        kept.added(self.name, "weekday-client-update", {"cron": "* * * * *", "prompt": prompt})
        return child

    def test_it_says_it_has_begun_the_moment_the_run_starts(self):
        self.a_gateway_running_one_schedule()
        self.assertTrue(support.waited_until(
            lambda: any("Working on 'weekday-client-update'" in one["text"]
                        for one in self.of_a_schedule()), self.PATIENCE),
            f"nobody was told the run had begun. It heard: {self.what_was_posted()}. "
            f"It said: {self.its_log()}")

    def test_the_words_are_the_ones_rundesk_promises(self):
        self.a_gateway_running_one_schedule()
        self.assertTrue(support.waited_until(lambda: len(self.of_a_schedule()) >= 1,
                                             self.PATIENCE), self.its_log())
        self.assertEqual("💻 Working on 'weekday-client-update' — I will report back when it "
                         "is done.", self.of_a_schedule()[0]["text"])

    def test_the_answer_comes_back_as_a_reply_to_that_notice(self):
        """The whole point of announcing through a seam that answers: a report arriving twenty
        minutes later beside answers to other questions, anchored to nothing, is worse than none."""
        self.a_gateway_running_one_schedule()
        self.assertTrue(support.waited_until(lambda: len(self.of_a_schedule()) >= 2,
                                             self.PATIENCE),
            f"the run never reported. It heard: {self.what_was_posted()}. "
            f"It said: {self.its_log()}")
        began, reported = self.of_a_schedule()[0], self.of_a_schedule()[1]
        self.assertEqual(began["external_id"], reported["reply_to"],
                         "the report did not quote the notice that said the run had begun")

    def test_what_is_reported_is_what_the_agent_answered(self):
        """Not that a process exited zero. What an owner wants at six in the morning is what the
        agent found."""
        self.a_gateway_running_one_schedule()
        self.assertTrue(support.waited_until(lambda: len(self.of_a_schedule()) >= 2,
                                             self.PATIENCE), self.its_log())
        said = self.of_a_schedule()[1]["text"]
        self.assertIn("Post the weekday client update.", said,
                      f"the report was not the agent's own answer: {said!r}")

    def test_an_initial_turn_that_delegated_does_not_post_before_its_review(self):
        began = datetime.datetime(2026, 8, 4, 9, 0, tzinfo=datetime.timezone.utc)
        landed = arriving.recorded_for_a_schedule(
            self.name, "nightly", "review overnight work", when=began, invocation="run-1")
        turn = turns_kept.add_turn(self.name, {
            "conversation_id": landed.conversation, "schedule_name": "nightly",
            "provider_name": support.A_STAND_IN, "access_mode": protocol.ACCESS_WORK,
        }, when=began)
        delegations_kept.made(
            self.name, "del-nightly-aabbcc", "trace", landed.conversation, turn, now=began)

        with mock.patch.object(host, "_told") as told:
            host._Notices(
                self.name, standing.logs_at(self.at),
                lambda: hosting.Watching({}, {}, {})).reported(
                    "nightly", "msg-1", "done", config.moment_of(began))

        told.assert_not_called()

    def test_a_fast_delegation_reviewed_inside_the_initial_turn_reports_normally(self):
        began = datetime.datetime(2026, 8, 4, 9, 0, tzinfo=datetime.timezone.utc)
        landed = arriving.recorded_for_a_schedule(
            self.name, "nightly", "review overnight work", when=began, invocation="run-1")
        turn = turns_kept.add_turn(self.name, {
            "conversation_id": landed.conversation, "schedule_name": "nightly",
            "provider_name": support.A_STAND_IN, "access_mode": protocol.ACCESS_WORK,
        }, when=began)
        delegations_kept.made(
            self.name, "del-nightly-aabbcc", "trace", landed.conversation, turn, now=began)
        result = arriving.said_by_rundesk_into(
            self.name, landed.conversation, "trace returned", when=began,
            external_id="delegation-result:del-nightly-aabbcc:answer-1")
        arriving.handled_by_turn(self.name, landed.conversation, (result.message,), turn)
        arriving.said_by_agent_into(
            self.name, landed.conversation, "Reviewed final report.", turn=turn, when=began)

        with mock.patch.object(host, "_told") as told:
            host._Notices(
                self.name, standing.logs_at(self.at),
                lambda: hosting.Watching({}, {}, {})).reported(
                    "nightly", "msg-1", "done", config.moment_of(began))

        told.assert_called_once()
        self.assertEqual("Reviewed final report.", told.call_args.args[3])

    def test_a_run_posts_only_a_notice_and_a_report_and_never_its_activity(self):
        """A scheduled turn runs in a process of its own that holds no channel, so there is nothing
        for its working notes to be posted through. The property is where the work runs rather than
        a filter somebody has to maintain — and this is what proves it stays that way.

        **Asserted as a shape rather than as a count.** This schedule is due every minute, so a run
        can begin while the case is still looking; counting messages would then go red for a gateway
        behaving perfectly. What must hold however many times it fires is that every single thing
        reaching the surface is either a notice or an answer to one — never a line about a tool that
        was run, a file that was read, or a thought.
        """
        self.a_gateway_running_one_schedule()
        self.assertTrue(support.waited_until(lambda: len(self.of_a_schedule()) >= 2,
                                             self.PATIENCE), self.its_log())
        self.assertTrue(support.waited_until(
            lambda: "schedule weekday-client-update completed" in self.its_log(), self.PATIENCE),
            f"the run never finished. It said: {self.its_log()}")
        self.several_beats()

        notices = {one["external_id"] for one in self.of_a_schedule()
                   if one["text"].startswith("💻 Working on")}
        self.assertTrue(notices, "nothing ever said a run had begun")
        for one in self.of_a_schedule():
            with self.subTest(said=one["text"][:40]):
                self.assertTrue(one["external_id"] in notices or one["reply_to"] in notices,
                                f"something that was neither a notice nor an answer to one "
                                f"reached the surface: {one['text']!r}")

    def test_it_all_lands_in_the_place_the_agent_is_told_things(self):
        self.a_gateway_running_one_schedule()
        self.assertTrue(support.waited_until(lambda: len(self.of_a_schedule()) >= 2,
                                             self.PATIENCE), self.its_log())
        self.assertEqual({"1180"}, {one["place"] for one in self.of_a_schedule()})

    def test_a_run_that_failed_never_reports_the_last_run_s_answer_as_its_own(self):
        """**The real `_Notices`, against a real database.** A schedule that answered on Monday and
        failed on Tuesday without saying anything must not report Monday's legacy answer as its own.
        Reported unbounded, the old report goes out under Tuesday's notice and Tuesday's failure is
        never mentioned: an answer nobody earned, reported as fact."""
        self.an_adapter(body=AN_ADAPTER_THAT_NAMES_WHAT_IT_POSTED)
        self.a_channel()
        monday = datetime.datetime(2026, 8, 3, 9, 0, tzinfo=datetime.timezone.utc)
        arriving.said_by_agent(self.name, arriving.FROM_SCHEDULE, "nightly",
                               "Monday's report: all clear.", when=monday)
        logs_at = standing.logs_at(self.at)
        watching = hosting.looked(self.name, logs_at, hosting.Watching({}, {}, {}))
        self.addCleanup(hosting.stopping, self.name, logs_at, watching, 4.0)
        self.assertTrue(support.waited_until(
            lambda: hosting.connected(watching, "discord"), self.PATIENCE))

        notices = host._Notices(self.name, logs_at, lambda: watching)
        notices.reported("nightly", "msg-1", "failed",
                         config.moment_of(datetime.datetime(2026, 8, 4, 9, 0,
                                                            tzinfo=datetime.timezone.utc)))

        self.assertTrue(support.waited_until(lambda: len(self.what_was_posted()) >= 1,
                                             self.PATIENCE), "nothing was reported at all")
        said = self.what_was_posted()[-1]["text"]
        self.assertNotIn("Monday's report", said,
                         "a failed run reported an earlier run's answer as its own")
        self.assertIn("failed", said)

    def test_a_run_that_did_answer_reports_that_answer(self):
        """The bound may not be so tight that a run's own answer falls outside it — the case above
        would pass just as well against a `reported` that never reads the records at all."""
        self.an_adapter(body=AN_ADAPTER_THAT_NAMES_WHAT_IT_POSTED)
        self.a_channel()
        began = datetime.datetime(2026, 8, 4, 9, 0, tzinfo=datetime.timezone.utc)
        arriving.said_by_agent(self.name, arriving.FROM_SCHEDULE, "nightly", "Tuesday's report.",
                               when=datetime.datetime(2026, 8, 4, 9, 5,
                                                      tzinfo=datetime.timezone.utc))
        logs_at = standing.logs_at(self.at)
        watching = hosting.looked(self.name, logs_at, hosting.Watching({}, {}, {}))
        self.addCleanup(hosting.stopping, self.name, logs_at, watching, 4.0)
        self.assertTrue(support.waited_until(
            lambda: hosting.connected(watching, "discord"), self.PATIENCE))

        host._Notices(self.name, logs_at, lambda: watching).reported(
            "nightly", "msg-1", "done", config.moment_of(began))

        self.assertTrue(support.waited_until(lambda: len(self.what_was_posted()) >= 1,
                                             self.PATIENCE), "nothing was reported at all")
        self.assertIn("Tuesday's report.", self.what_was_posted()[-1]["text"])

    def test_a_scheduled_reports_local_link_is_attached_without_exposing_the_path(self):
        self.an_adapter(body=AN_ADAPTER_THAT_NAMES_WHAT_IT_POSTED)
        self.a_channel()
        at = self.home / "reports" / "Quarterly Preview.pdf"
        at.parent.mkdir(parents=True)
        at.write_bytes(b"a small pdf")
        began = datetime.datetime(2026, 8, 4, 9, 0, tzinfo=datetime.timezone.utc)
        arriving.said_by_agent(
            self.name, arriving.FROM_SCHEDULE, "nightly",
            f"Report: [the PDF](<file://{str(at).replace(' ', '%20')}>)",
            when=datetime.datetime(2026, 8, 4, 9, 5, tzinfo=datetime.timezone.utc))
        logs_at = standing.logs_at(self.at)
        watching = hosting.looked(self.name, logs_at, hosting.Watching({}, {}, {}))
        self.addCleanup(hosting.stopping, self.name, logs_at, watching, 4.0)
        self.assertTrue(support.waited_until(
            lambda: hosting.connected(watching, "discord"), self.PATIENCE))

        host._Notices(self.name, logs_at, lambda: watching).reported(
            "nightly", "msg-1", "done", config.moment_of(began))

        self.assertTrue(support.waited_until(lambda: self.what_was_posted(), self.PATIENCE))
        posted = self.what_was_posted()[-1]
        self.assertEqual(["Quarterly-Preview.pdf"],
                         [one["name"] for one in posted["files"]])
        self.assertNotIn("file://", posted["text"])
        self.assertNotIn(str(at), posted["text"])

    def test_a_scheduled_artifact_refused_by_the_adapter_falls_back_to_text(self):
        self.a_channel()
        at = self.home / "reports" / "preview.png"
        at.parent.mkdir(parents=True)
        at.write_bytes(b"pixels")
        began = datetime.datetime(2026, 8, 4, 9, 0, tzinfo=datetime.timezone.utc)
        arriving.said_by_agent(
            self.name, arriving.FROM_SCHEDULE, "nightly", f"Result: [preview]({at})",
            when=datetime.datetime(2026, 8, 4, 9, 5, tzinfo=datetime.timezone.utc))
        calls = []
        told = host._told
        self.addCleanup(setattr, host, "_told", told)

        def refusing(name, where, watching, saying, landed_within=0.0, answering=None,
                     sending=(), refusals=None):
            calls.append({"text": saying, "within": landed_within,
                          "sending": tuple(sending), "answering": answering})
            if sending and refusals is not None:
                refusals.append("the file changed after approval")
            return host.TOLD

        host._told = refusing
        host._Notices(
            self.name, standing.logs_at(self.at),
            lambda: hosting.Watching({}, {}, {})).reported(
                "nightly", "msg-1", "done", config.moment_of(began))

        self.assertEqual(2, len(calls))
        self.assertGreater(calls[0]["within"], 0)
        self.assertTrue(calls[0]["sending"])
        self.assertFalse(calls[1]["sending"])
        self.assertIn("Could not attach: preview.png", calls[1]["text"])
        self.assertNotIn(str(at), calls[1]["text"])

    def test_a_long_scheduled_report_retries_only_its_refused_final_piece(self):
        self.a_channel()
        at = self.home / "reports" / "preview.png"
        at.parent.mkdir(parents=True)
        at.write_bytes(b"pixels")
        began = datetime.datetime(2026, 8, 4, 9, 0, tzinfo=datetime.timezone.utc)
        said = "BEGIN\n" + "x" * 5000 + f"\nEND [preview]({at})"
        arriving.said_by_agent(
            self.name, arriving.FROM_SCHEDULE, "nightly", said,
            when=datetime.datetime(2026, 8, 4, 9, 5, tzinfo=datetime.timezone.utc))
        calls = []
        told = host._told
        self.addCleanup(setattr, host, "_told", told)

        def refusing(name, where, watching, saying, landed_within=0.0, answering=None,
                     sending=(), refusals=None):
            calls.append({"text": saying, "answering": answering})
            if sending and refusals is not None:
                refusals.append("the file changed after approval")
            return host.TOLD

        host._told = refusing
        host._Notices(
            self.name, standing.logs_at(self.at),
            lambda: hosting.Watching({}, {}, {})).reported(
                "nightly", "msg-1", "done", config.moment_of(began))

        self.assertEqual(2, len(calls))
        self.assertIn("BEGIN", calls[0]["text"])
        self.assertNotIn("BEGIN", calls[1]["text"])
        self.assertIn("END preview", calls[1]["text"])
        self.assertEqual("msg-1", calls[0]["answering"])
        self.assertIsNone(calls[1]["answering"])

    def test_a_schedule_that_starts_a_program_says_neither(self):
        """It has no answer to report, so promising to report back is a promise rundesk does not
        keep — and a successful program stays as quiet as it always did."""
        self.an_adapter(body=AN_ADAPTER_THAT_NAMES_WHAT_IT_POSTED)
        self.a_channel()
        kept.added(self.name, "tick", {"cron": "* * * * *", "command": "/bin/echo it worked"})
        self.a_running_gateway(beat=self.A_SHORT_BEAT)
        self.assertTrue(support.waited_until(
            lambda: "schedule tick completed" in self.its_log(), self.PATIENCE),
            f"the schedule never ran, so its silence proves nothing. It said: {self.its_log()}")
        self.several_beats()
        self.assertEqual([], self.of_a_schedule(),
                         f"a program schedule reached the surface: {self.of_a_schedule()}")


if __name__ == "__main__":
    unittest.main()
