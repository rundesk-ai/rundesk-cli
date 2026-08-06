"""Keeping a channel's adapter running: the claim, the thread on its stream, and the stop.

Real programs, real locks, real process groups, real threads. A stand-in for a child would prove
nothing about the two properties this whole design rests on — that the claim outlives the gateway
because the child holds it, and that a talkative adapter cannot wedge the loop because nothing on
the loop is doing the reading.

`hosting` calls itself a sibling of `schedules.firing`, *proven against a supervisor that can be
killed at any moment*, and this file carried none of what proved it. Three of `firing`'s techniques
are here now, because each of them was learned the expensive way:

**Every signal goes to a pid this suite started, and a group only once it is certainly the child's
own.** `start_new_session=True` calls `setsid()` *after* the fork, so asking for a child's group
inside that window answers with this test runner's — see `ended_outright`.

**Whatever a case starts is taken away however the case ends**, registered at acquisition rather
than left to a `tearDown` that does not run when `setUp` fails. Both halves: `hosting.stopping`
deliberately leaves an *adopted* adapter alone, so a case that adopted one would otherwise leave a
real program running on somebody's machine.

**A guarantee is only proven by a case that goes red when the code is removed.** Three here did not
— a talkative adapter that only asserted a dict entry still existed, a restart hold-off nothing
touched, and a dying adapter's last words nothing read — and each is now written the other way
round.

Run directly: `python3 tests/test_channels_hosting.py`
"""

import contextlib
import fcntl
import json
import os
import signal
import time
import unittest

import support
from rundesk.agents import directory
from rundesk.channels import arriving, delivery, hosting, kept
from rundesk.channels import files as arrivals
from rundesk.core import paths
from rundesk.utils import programs

#: How long a case will wait for a real child to do something. Generous, because it is a real fork
#: and exec on a machine that may be loaded, and a ceiling rather than a sleep so an ordinary run is
#: through in hundredths. `firing`'s number, for the same reason.
PATIENCE = 20.0

#: An adapter that connects, echoes anything it is told to deliver, and can be made to say things.
#: **Everything rundesk says to it is written down**, whole and unread, because half of what this
#: file proves is what goes *out* through the pipe — a mark on a message that has arrived, and the
#: files a delivery carries.
AN_ADAPTER = """#!/usr/bin/env python3
import json, os, sys, time
if "--capabilities" in sys.argv:
    print(json.dumps({"stream": True, "max_text": 2000})); raise SystemExit(0)
settings = json.loads(os.environ.get("RUNDESK_SETTINGS") or "{}")
print(json.dumps({"say": "ready", "as": "a-bot"}), flush=True)
for said in (settings.get("saying") or "").split("|"):
    if said.strip():
        print(said, flush=True)
for line in sys.stdin:
    try:
        record = json.loads(line)
    except ValueError:
        continue
    with open(settings["told"], "a") as writing:
        writing.write(line if line.endswith("\\n") else line + "\\n")
    if record.get("do") == "stop":
        break
    if record.get("do") == "deliver":
        print(json.dumps({"say": "delivered", "id": record.get("id"),
                          "external_id": "8841"}), flush=True)
        with open(settings["heard"], "a") as writing:
            writing.write(record.get("text", "") + "\\n")
"""

#: One that fetches the way a real adapter does: into the directory rundesk hands it, under a name
#: of no consequence, and then says where it put it. `RUNDESK_CHANNEL_HOME` is read without a
#: fallback on purpose — an adapter with nowhere to put what it downloads has nothing to report, and
#: a default of the working directory is how a file comes to land wherever the gateway was started.
AN_ADAPTER_THAT_FETCHES = """#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
into = Path(os.environ["RUNDESK_CHANNEL_HOME"]) / "fetched" / "8841"
into.mkdir(parents=True, exist_ok=True)
(into / "0").write_bytes(b"one,two\\n")
print(json.dumps({"say": "ready"}), flush=True)
print(json.dumps({"say": "arrived", "conversation": "1180", "user": "2207",
                  "text": "have a look", "external_id": "8841",
                  "attachments": [{"name": "report.csv", "at": str(into / "0"), "bytes": 8}]}),
      flush=True)
for line in sys.stdin:
    try:
        if json.loads(line).get("do") == "stop":
            break
    except ValueError:
        continue
"""

#: One that says its configuration is what is wrong and exits `78` — `EX_CONFIG`, the code an
#: adapter uses for a failure no restart can fix. A revoked token is the real case.
AN_ADAPTER_THAT_CANNOT_COME_RIGHT = """#!/usr/bin/env python3
import json, sys
print(json.dumps({"say": "note", "level": "error",
                  "text": "Discord refused the token (HTTP 401)"}), flush=True)
sys.stderr.write("the token in DISCORD_BOT_TOKEN is no longer accepted\\n")
raise SystemExit(78)
"""

#: One that says several times what a pipe holds and then **answers**, which is the whole of what a
#: full pipe would take away. Every one of the four thousand is a record `_heard` recognises and does
#: nothing with, so what proves the drain kept up is the last line rather than four thousand entries
#: in a day's log — the log is not what is being measured here.
A_TALKATIVE_ADAPTER = """#!/usr/bin/env python3
import json, os, sys
settings = json.loads(os.environ.get("RUNDESK_SETTINGS") or "{}")
print(json.dumps({"say": "ready"}), flush=True)
for nth in range(4000):
    print(json.dumps({"say": "counting", "nth": nth, "pad": "x" * 64}), flush=True)
print(json.dumps({"say": "note", "level": "info", "text": "I said the whole of it"}), flush=True)
for line in sys.stdin:
    try:
        record = json.loads(line)
    except ValueError:
        continue
    if record.get("do") == "stop":
        break
    if record.get("do") == "deliver":
        with open(settings["heard"], "a") as writing:
            writing.write(record.get("text", "") + "\\n")
"""

#: One that says more in one line than is ever read at once, **and never ends the line**. The whole
#: of the first defect this file was written for: `for line in stdout` is `readline()` with no size,
#: so nothing is refused until the entire run is already in memory — measured at 735MB of resident
#: memory for a 300MB run, after which the kernel ends the gateway and nothing is logged anywhere.
#:
#: It writes and then waits, so there is no newline coming: a reader that is not bounded has
#: nothing to say and never will.
A_SHOUTING_ADAPTER = """#!/usr/bin/env python3
import json, sys
print(json.dumps({"say": "ready"}), flush=True)
sys.stdout.write("x" * (3 * 1024 * 1024))
sys.stdout.flush()
for line in sys.stdin:
    if '"stop"' in line:
        break
"""

#: The same, three times over and each run ended, then something worth hearing. For the *second*
#: half of it: a program in this state produces a line per megabyte, so the complaint is said once,
#: and what follows a discarded run is still heard.
A_SHOUTING_ADAPTER_THAT_GOES_ON = """#!/usr/bin/env python3
import json, sys
print(json.dumps({"say": "ready"}), flush=True)
for _ in range(3):
    sys.stdout.write("x" * (2 * 1024 * 1024) + "\\n")
    sys.stdout.flush()
print(json.dumps({"say": "note", "level": "info", "text": "I said the whole of it"}), flush=True)
for line in sys.stdin:
    if '"stop"' in line:
        break
"""

#: One that writes a byte that is not text at all, and then goes on speaking the protocol. A real
#: adapter reaches this by relaying somebody's message from a platform that is not as strict about
#: encoding as it claims, and one byte used to be the permanent end of the channel: the
#: `UnicodeDecodeError` is raised *inside* the read, past the guard around one record, so the thread
#: ended for good while the adapter went on holding its claim and receiving messages.
AN_ADAPTER_THAT_SAYS_SOMETHING_UNDECODABLE = """#!/usr/bin/env python3
import json, sys
print(json.dumps({"say": "ready"}), flush=True)
sys.stdout.buffer.write(b'{"say": "note", "text": "\\xff\\xfe not text"}\\n')
sys.stdout.buffer.flush()
print(json.dumps({"say": "note", "level": "info", "text": "still listening"}), flush=True)
for line in sys.stdin:
    if '"stop"' in line:
        break
"""

#: One that stops saying anything and goes on running, which is what an adapter whose reader has
#: gone looks like from outside: the claim is still held, `programs.collected` never sees it exit,
#: and nothing arrives through it ever again.
#: `os.close(1)` as well as closing the stream, because the two are not the same thing: CPython
#: builds the standard streams over a `FileIO` with `closefd=False`, so closing `sys.stdout` flushes
#: and closes the wrapper and leaves the descriptor — and the reader on the far side goes on
#: waiting, which is a slower version of the very state this case is about.
AN_ADAPTER_THAT_CLOSES_ITS_MOUTH = """#!/usr/bin/env python3
import json, os, sys, time
print(json.dumps({"say": "ready"}), flush=True)
sys.stdout.close()
os.close(1)
time.sleep(600)
"""

#: One that will not start at all.
A_BROKEN_ADAPTER = """#!/usr/bin/env python3
import sys
sys.stderr.write("ModuleNotFoundError: No module named discord\\n")
raise SystemExit(1)
"""

#: One that complains at length and then dies, for proving its last words reach the agent's log —
#: and that only the bounded tail of them does. Far more lines than `SAID_AT_MOST`, so a copy that
#: was not bounded would put the whole of it under a day somebody came to read.
A_DYING_ADAPTER = """#!/usr/bin/env python3
import json, sys
print(json.dumps({"say": "ready"}), flush=True)
for nth in range(200):
    sys.stderr.write("line %d of what went wrong\\n" % nth)
sys.stderr.flush()
raise SystemExit(2)
"""


def ended_outright(case, pid: int, how: int) -> None:
    """Kill a child and everything it started, once it is certainly in a group of its own.

    **Never `killpg(getpgid(pid))` on its own, which is what this exists to stop.** A child started
    with `start_new_session=True` calls `setsid()` *after* the fork, so there is a real window in
    which the parent has the pid and the child is still in the *parent's* process group — and asking
    for its group inside that window answers with this test runner's own, which a signal would then
    take out along with everything else running in it. The build this replaces recorded `killpg` at
    group `0` doing exactly that.

    So the group is only ever signalled once it is the child's own — `getpgid(pid) == pid` is what
    proves the `setsid` has happened, because a session leader leads a group of its own id.

    The same helper `tests/test_schedules_firing.py` has, and written out rather than imported: a
    suite that imports another suite is one that goes red for a reason in a file it is not about.
    """
    case.assertTrue(support.waited_until(lambda: _leads_its_own_group(pid), PATIENCE),
                    f"{pid} never became a session leader, so its group is not safe to signal")
    os.killpg(pid, how)


def _leads_its_own_group(pid: int) -> bool:
    """Whether this child has its own process group yet, which is what `setsid` gives it."""
    try:
        return os.getpgid(pid) == pid
    except OSError:
        return False


class Hosting(support.Isolated):

    def setUp(self):
        super().setUp()
        self.agent = "cole"
        directory.made(self.agent, "claude")
        self.where = directory.logs(self.agent)
        # `paths.code()` answers with the checkout when the scratch root has no installed tree, and
        # a case writing an adapter would then write it into the repository. See test_channels_adapters.
        (paths.home() / "app" / "src").mkdir(parents=True, exist_ok=True)
        self.adapters = paths.code() / "channels"
        self.adapters.mkdir(parents=True, exist_ok=True)
        self.heard = self.home / "heard.txt"
        self.told = self.home / "told.txt"
        self.started = []
        self.pids = []
        self.addCleanup(self.stop_everything)

    def stop_everything(self):
        """Take away whatever this case started, however the case ended.

        **Both halves.** `hosting.stopping` is the product's own stop and it deliberately leaves an
        *adopted* adapter alone — its group was never that process's to signal — so a case that
        adopted one, or one whose adapter was let go of before the case ended, would leave a real
        program running on somebody's machine. Every pid this case saw is ended by id, never by a
        group read off something, which is `firing`'s rule and the reason its suite has one.

        Registered at acquisition rather than left to a `tearDown`, which does not run when `setUp`
        itself fails — and a case that failed while starting something is exactly the one that would
        leave a child behind.
        """
        for watching in self.started:
            hosting.stopping(self.agent, self.where, watching, 4.0)
        for pid in self.pids:
            with contextlib.suppress(OSError):
                programs.stop(pid, gently_for=0.2, firmly_for=2.0)

    def an_adapter(self, kind="discord", body=AN_ADAPTER):
        at = self.adapters / kind
        at.write_text(body, encoding="utf-8")
        at.chmod(0o755)
        return at

    def a_channel(self, kind="discord", allowed=("2207",), told=False, saying=""):
        kept.added(self.agent, kind, {
            "describes": kind, "allowed": json.dumps(list(allowed)),
            "settings": json.dumps({"saying": saying, "heard": str(self.heard),
                                    "told": str(self.told)})})
        if told:
            kept.telling(self.agent, kind, "1180")

    def a_staged_file(self, kind="discord", message="8841", named="0", body=b"one,two\n"):
        """A file where the adapter would have put what it fetched: inside its own directory.

        Written before anything starts, because what is being proved is what rundesk does with a
        path an adapter reported and not how a real platform is downloaded from.
        """
        at = hosting.at(self.agent, kind) / "fetched" / message / named
        at.parent.mkdir(parents=True, exist_ok=True)
        at.write_bytes(body)
        return at

    def what_it_was_told(self):
        """Every record rundesk wrote to the adapter, as objects, oldest first."""
        if not self.told.exists():
            return []
        return [json.loads(line) for line in self.told.read_text(encoding="utf-8").splitlines()
                if line.strip()]

    def a_message_arrived(self, **also):
        """The settings line that makes the adapter announce one message on its way up."""
        said = {"say": "arrived", "conversation": "1180", "user": "2207",
                "text": "what changed today?", "external_id": "8841"}
        said.update(also)
        return json.dumps(said)

    def hosting_now(self):
        watching = hosting.looked(self.agent, self.where, hosting.Watching({}, {}, {}))
        self.started.append(watching)
        self.remember(watching)
        return watching

    def looked_again(self, watching):
        """One more pass of the gateway's loop, keeping hold of anything it started this time."""
        hosting.looked(self.agent, self.where, watching)
        self.remember(watching)
        return watching

    def remember(self, watching):
        """Write down every pid this case has seen, so the cleanup can end it by id."""
        self.pids.extend(one.pid for one in watching.running.values()
                         if one.pid and one.pid not in self.pids)

    def told_lines(self):
        """Every record the adapter was handed, as it was handed them."""
        if not self.told.exists():
            return []
        return [one for one in self.told.read_text().splitlines() if one.strip()]

    def said_in_the_log(self):
        found = sorted(self.where.glob("*.log"))
        return "".join(one.read_text(encoding="utf-8") for one in found)


class StartingOne(Hosting):

    def test_an_adapter_is_started_for_a_configured_channel(self):
        self.an_adapter()
        self.a_channel()
        watching = self.hosting_now()
        self.assertIn("discord", watching.running)
        self.assertTrue(watching.running["discord"].mine)

    def test_nothing_is_started_for_an_agent_with_no_channels(self):
        self.an_adapter()
        self.assertEqual({}, self.hosting_now().running)

    def test_the_claim_is_held_by_the_child_rather_than_by_this_process(self):
        # The property everything else rests on: the descriptor is passed down, so the claim lives
        # exactly as long as the child and the kernel drops it however that ends.
        self.an_adapter()
        self.a_channel()
        self.hosting_now()
        self.assertTrue(support.waited_until(
            lambda: hosting.still_running(self.agent, "discord"), 5.0))

    def test_a_second_gateway_will_not_start_a_second_adapter_beside_the_first(self):
        self.an_adapter()
        self.a_channel()
        self.hosting_now()
        support.waited_until(lambda: hosting.still_running(self.agent, "discord"), 5.0)
        with self.assertRaises(hosting.Occupied):
            with hosting.claiming(self.agent, "discord"):
                pass

    def test_a_channel_whose_adapter_is_not_installed_does_not_end_the_gateway(self):
        self.a_channel()
        watching = self.hosting_now()
        self.assertEqual({}, watching.running)
        self.assertIn("discord", watching.waiting, "it was not held off before trying again")

    def test_an_adapter_that_will_not_run_is_said_and_held_off(self):
        self.an_adapter(body=A_BROKEN_ADAPTER)
        self.a_channel()
        watching = self.hosting_now()
        support.waited_until(lambda: not watching.running, 5.0)
        hosting.looked(self.agent, self.where, watching)
        self.assertIn("discord", watching.waiting)

    def test_asking_whether_a_channel_is_running_never_makes_its_lock(self):
        # A channel nobody has started must not be given a claim by the act of asking about one.
        self.a_channel()
        self.assertFalse(hosting.still_running(self.agent, "discord"))
        self.assertFalse(hosting.lock_of(self.agent, "discord").exists())


class ListeningToOne(Hosting):

    def test_what_it_says_when_it_connects_reaches_the_agents_log(self):
        self.an_adapter()
        self.a_channel()
        self.hosting_now()
        self.assertTrue(support.waited_until(
            lambda: "channel discord: connected" in self.said_in_the_log(), 5.0))

    def test_a_message_from_somebody_allowed_is_recorded(self):
        self.an_adapter()
        self.a_channel(allowed=("2207",), saying=json.dumps({
            "say": "arrived", "conversation": "1180", "user": "2207",
            "text": "what changed today?", "external_id": "8841"}))
        self.hosting_now()
        self.assertTrue(support.waited_until(
            lambda: len(arriving.conversations(self.agent)) == 1, 5.0))
        landed = arriving.conversations(self.agent)[0]
        self.assertEqual("what changed today?",
                         arriving.messages(self.agent, landed["id"])[0]["body"])

    def test_a_message_from_a_stranger_is_neither_recorded_nor_answered(self):
        # Silence is the answer on purpose: replying to tell somebody they are a stranger confirms
        # the agent is listening and spends the owner's tokens doing it. Nothing is written down
        # either, because a record of it is something an agent could later be asked to read.
        self.an_adapter()
        self.a_channel(allowed=("2207",), saying=json.dumps({
            "say": "arrived", "conversation": "1180", "user": "9999", "text": "let me in"}))
        self.hosting_now()
        support.waited_until(lambda: "connected" in self.said_in_the_log(), 5.0)
        self.assertEqual([], arriving.conversations(self.agent))
        self.assertNotIn("9999", self.said_in_the_log())

    def test_a_message_that_is_only_a_file_is_still_a_message(self):
        # Requiring text dropped it in total silence — not recorded, not logged, nothing said —
        # for somebody who was on the allow list.
        at = self.a_staged_file()
        self.an_adapter()
        self.a_channel(allowed=("2207",), saying=self.a_message_arrived(
            text="", attachments=[{"name": "report.csv", "at": str(at), "bytes": 8}]))
        self.hosting_now()
        self.assertTrue(support.waited_until(
            lambda: len(arriving.conversations(self.agent)) == 1, 5.0))
        landed = arriving.conversations(self.agent)[0]
        self.assertIn("report.csv", arriving.messages(self.agent, landed["id"])[0]["body"])

    def test_a_message_with_neither_words_nor_files_is_nothing_to_record(self):
        self.an_adapter()
        self.a_channel(allowed=("2207",), saying=json.dumps({
            "say": "arrived", "conversation": "1180", "user": "2207", "text": ""}))
        self.hosting_now()
        support.waited_until(lambda: "connected" in self.said_in_the_log(), 5.0)
        self.assertEqual([], arriving.conversations(self.agent))

    def test_something_that_is_not_a_record_does_not_stop_it_listening(self):
        self.an_adapter()
        self.a_channel(saying="this is not json|" + json.dumps(
            {"say": "note", "level": "warning", "text": "still here"}))
        self.hosting_now()
        self.assertTrue(support.waited_until(
            lambda: "still here" in self.said_in_the_log(), 5.0))

    def test_a_talkative_adapter_does_not_wedge_anything(self):
        # A pipe holds 64KB and this says several times that. Nothing on the gateway's loop is
        # doing the reading, so the loop keeps answering while the thread drains.
        #
        # **It used to assert only that the dict entry was still there**, which is true with the
        # drain thread deleted outright: the adapter blocks at 64KB, the loop is untouched, and the
        # case went green over a child that was wedged for ever. Measured that way, by taking the
        # thread out and watching it stay green. Both assertions below are false unless the draining
        # really happened — the last thing an adapter says arrives only after everything before it,
        # and a program blocked writing into a full pipe never reaches its own stdin loop to answer
        # anything at all.
        self.an_adapter(body=A_TALKATIVE_ADAPTER)
        self.a_channel()
        watching = self.hosting_now()
        for _ in range(3):
            self.looked_again(watching)
        self.assertIn("discord", watching.running, "the loop lost the adapter it was hosting")

        self.assertTrue(support.waited_until(
            lambda: "I said the whole of it" in self.said_in_the_log(), PATIENCE),
            "the last of what a talkative adapter said never arrived, so the drain either stopped "
            f"or fell behind. It said: {self.said_in_the_log()[-500:]}")
        self.assertTrue(hosting.told(self.agent, self.where, watching, "discord", "1180",
                                     ["are you still there"]))
        self.assertTrue(support.waited_until(
            lambda: self.heard.exists() and "are you still there" in self.heard.read_text(),
            PATIENCE),
            "an adapter that had said far more than a pipe holds could not answer, which is the "
            "deadlock a thread per adapter exists to make unreachable")


class HowMuchOfALineIsHeld(Hosting):
    """A line is read a bounded amount at a time, which is what `LINE_AT_MOST` claims to promise.

    It did not. `for line in stdout` is `TextIOWrapper.readline()` with no size, which pulls bytes
    until it meets a newline or the end of the stream; the length was checked afterwards, by which
    time the whole of it was already held. An adapter writing 300MB with no newline took this
    process from 17MB to 735MB, the kernel ended the gateway outright — which logs nothing anywhere,
    because a `SIGKILL` lets no code run — launchd brought it back, and the channel did it again.
    """

    def test_a_line_that_never_ends_is_refused_while_it_is_still_arriving(self):
        # **The whole of the fix, and the only assertion that can see it.** The adapter writes three
        # megabytes and no newline, ever: with an unbounded read there is nothing to say and never
        # will be — the reader sits inside one `readline` holding everything that has arrived, which
        # is exactly the growth being refused. A bounded read has an answer within a megabyte.
        self.an_adapter(body=A_SHOUTING_ADAPTER)
        self.a_channel()
        self.hosting_now()
        self.assertTrue(support.waited_until(
            lambda: "said more in one line than is read at once" in self.said_in_the_log(),
            PATIENCE),
            "an adapter writing without ever ending a line was never refused, so what it is saying "
            "is being held in this process")

    def test_it_is_said_once_and_what_follows_is_still_heard(self):
        # Two things one case can prove and neither is the same as the last one. A program in this
        # state produces a line per megabyte, so a complaint per line is the unbounded growth
        # arriving in the log instead of in memory. And the run that was thrown away has to be
        # thrown away *whole*: what is left of it is not a record, and the tail of a discarded line
        # read as one would be a warning per megabyte by the other road.
        self.an_adapter(body=A_SHOUTING_ADAPTER_THAT_GOES_ON)
        self.a_channel()
        self.hosting_now()
        self.assertTrue(support.waited_until(
            lambda: "I said the whole of it" in self.said_in_the_log(), PATIENCE),
            f"what an adapter said after an over-long line went nowhere. It said: "
            f"{self.said_in_the_log()[-500:]}")

        said = self.said_in_the_log()
        self.assertEqual(1, said.count("said more in one line"),
                         "an adapter that never ends a line was complained about once per line, "
                         "which is the growth this bound exists to prevent")
        self.assertNotIn("said something that is not a record", said,
                         "part of a discarded line was read as a record of its own")


class WhenItSaysSomethingThatIsNotText(Hosting):

    def test_one_byte_that_is_not_text_is_not_the_end_of_the_channel(self):
        # **Raised inside the read, so the guard around one record cannot catch it.** It escaped
        # the loop, the outer handler wrote one line, and the thread ended for good — while the
        # adapter went on holding its claim, so nothing reaped it, nothing restarted it, and
        # `channels list` went on printing `connected (pid N)` for a channel receiving nothing.
        self.an_adapter(body=AN_ADAPTER_THAT_SAYS_SOMETHING_UNDECODABLE)
        self.a_channel()
        self.hosting_now()
        self.assertTrue(support.waited_until(
            lambda: "still listening" in self.said_in_the_log(), PATIENCE),
            f"a single byte that is not text ended the channel. It said: "
            f"{self.said_in_the_log()[-500:]}")
        self.assertNotIn("stopped listening to it", self.said_in_the_log())


class WhenNothingIsReadingIt(Hosting):
    """An adapter that is running is not an adapter that is working.

    `hosting` was written as a sibling of `schedules.firing` and took its policy that adopted work
    is never signalled — right for a firing, which is bounded work that finishes on its own, and
    wrong for a program that *runs for months and is listened to*. What it left was an adapter
    nothing could end: no thread reading it, its claim held, every gateway after it adopting it
    again, and `gateways stop`, `gateways restart`, `channels remove` and `agents remove` all
    reporting success over a program still connected to a platform.
    """

    def test_one_that_stopped_saying_anything_is_ended_and_started_again(self):
        # The claim is still held, so `programs.collected` never sees it exit and nothing here would
        # ever restart it — a channel that reads as connected and receives nothing for as long as
        # the gateway lives.
        self.an_adapter(body=AN_ADAPTER_THAT_CLOSES_ITS_MOUTH)
        self.a_channel()
        watching = self.hosting_now()
        was = watching.running["discord"].pid
        self.assertTrue(support.waited_until(
            lambda: not watching.running["discord"].listening.is_alive(), PATIENCE),
            "the adapter never stopped being read, so there is nothing to notice")

        self.assertTrue(support.waited_until(
            lambda: "discord" not in self.looked_again(watching).running, PATIENCE),
            f"an adapter nothing was reading was left running. It said: {self.said_in_the_log()}")

        self.assertFalse(programs.alive(was), "it was let go of and never stopped")
        self.assertIn("nothing was reading it", self.said_in_the_log())
        watching.waiting["discord"] = time.monotonic() - hosting.AGAIN_AFTER - 1
        self.looked_again(watching)
        self.assertIn("discord", watching.running, "nothing took the place of the one that was "
                                                   "ended, so the channel is down for good")

    def test_an_adopted_one_is_ended_because_nothing_here_can_read_it(self):
        # Its stdout is a pipe whose only reader died with the gateway that made it, so every
        # message it receives goes nowhere. Adopted first — nothing may start a second adapter
        # beside one holding the claim — and ended on the very next pass.
        self.an_adapter()
        self.a_channel()
        first = self.hosting_now()
        support.waited_until(lambda: hosting.still_running(self.agent, "discord"), PATIENCE)

        was = first.running["discord"].pid
        fresh = hosting.settled(self.agent, self.where)
        self.started.append(fresh)
        self.remember(fresh)
        self.assertIn("discord", fresh.running, "a live adapter was not seen at all")
        self.assertFalse(fresh.running["discord"].mine)

        self.looked_again(fresh)

        self.assertNotIn("discord", fresh.running,
                         "an adapter nothing could read was hosted as though it were working")
        self.assertFalse(programs.alive(was),
                         "the adapter this gateway could not read was left running")
        fresh.waiting["discord"] = time.monotonic() - hosting.AGAIN_AFTER - 1
        self.looked_again(fresh)
        self.assertIn("discord", fresh.running, "the channel was ended and never started again")
        self.assertTrue(fresh.running["discord"].mine)
        self.assertNotEqual(was, fresh.running["discord"].pid)

    def test_one_whose_process_was_never_written_down_is_said_rather_than_signalled(self):
        # The one state with no command behind it: a gateway killed between claiming a channel and
        # writing down the pid leaves a live adapter nothing can name. Signalling the number in the
        # record anyway is how a stranger's program is ended, so it is refused — and said, because
        # the honest report of a state nothing can resolve is the state and not silence.
        self.a_channel()
        self.a_claim_nobody_will_let_go_of()
        hosting.record_of(self.agent, "discord").write_text('{"pid": null}', encoding="utf-8")

        watching = hosting.settled(self.agent, self.where)
        hosting.looked(self.agent, self.where, watching)

        self.assertIn("nothing recorded which process it is", self.said_in_the_log())
        self.assertIn("discord", watching.running,
                      "a second adapter would have been started beside one still holding the claim")
        self.assertTrue(hosting.still_running(self.agent, "discord"))

    def a_claim_nobody_will_let_go_of(self):
        """This case's own `flock` on a channel's lock, standing in for an adapter nothing can name.

        A real lock rather than a stand-in, because the whole discipline being proved is that the
        kernel is what says somebody is there. Let go by a cleanup registered the moment it is held,
        which is `firing`'s rule: a case that fails while taking something must still give it back.
        """
        at = hosting.lock_of(self.agent, "discord")
        at.parent.mkdir(parents=True, exist_ok=True)
        held = os.open(str(at), os.O_CREAT | os.O_RDWR, 0o600)
        self.addCleanup(self.let_go_of, held)
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return held

    @staticmethod
    def let_go_of(held):
        with contextlib.suppress(OSError):
            os.close(held)


class WhatWasAttached(Hosting):
    """The adapter fetches, because it holds the credential; rundesk decides where it lands.

    Both halves of this were built in the build this replaces and both had been lost here: the
    adapter reported a name and a URL and downloaded nothing, and `channels.files` had the whole
    landing path built and tested with no record ever reaching it.
    """

    def landed_files(self, kind="discord", message="8841"):
        at = arrivals.arrived_at(self.agent, kind, message)
        return sorted(at.iterdir()) if at.is_dir() else []

    def the_body(self):
        landed = arriving.conversations(self.agent)[0]
        return arriving.messages(self.agent, landed["id"])[0]["body"]

    def test_a_file_the_adapter_fetched_lands_where_the_agent_can_read_it(self):
        at = self.a_staged_file(body=b"one,two\n")
        self.an_adapter()
        self.a_channel(saying=self.a_message_arrived(
            text="have a look", attachments=[{"name": "report v2.csv", "at": str(at),
                                              "bytes": 8}]))
        self.hosting_now()
        self.assertTrue(support.waited_until(
            lambda: len(arriving.conversations(self.agent)) == 1, PATIENCE),
            f"nothing was recorded. It said: {self.said_in_the_log()}")

        self.assertEqual(1, len(self.landed_files()), "the file the adapter fetched never landed")
        where = self.landed_files()[0]
        self.assertEqual(b"one,two\n", where.read_bytes())
        self.assertNotIn(" ", where.name, "a platform's name was written down unflattened")
        self.assertIn(str(where), self.the_body(),
                      "the agent was told a file arrived and not where it stands")
        self.assertFalse(at.exists(), "the channel kept a second copy of what it fetched")

    def test_the_adapter_is_told_where_it_may_put_what_it_fetches(self):
        # End to end and through the environment, because the two halves have to agree about one
        # directory: the adapter writes into `RUNDESK_CHANNEL_HOME` and `files.landed` will take a
        # file from nowhere else. The adapter here reads it with no fallback, so an unset variable
        # is a channel that says nothing at all rather than one that quietly writes somewhere odd.
        self.an_adapter(body=AN_ADAPTER_THAT_FETCHES)
        self.a_channel()
        self.hosting_now()

        self.assertTrue(support.waited_until(
            lambda: len(arriving.conversations(self.agent)) == 1, PATIENCE),
            f"nothing arrived. It said: {self.said_in_the_log()}")
        self.assertEqual(1, len(self.landed_files()))
        self.assertEqual(b"one,two\n", self.landed_files()[0].read_bytes())

    def test_one_that_did_not_arrive_whole_is_not_offered_to_the_agent(self):
        # A download that succeeded is not a file that arrived: a fetch cut off part way leaves a
        # readable file of the wrong length, and naming it would promise something behind it.
        at = self.a_staged_file(body=b"half of")
        self.an_adapter()
        self.a_channel(saying=self.a_message_arrived(
            text="have a look", attachments=[{"name": "report.csv", "at": str(at),
                                              "bytes": 4096}]))
        self.hosting_now()
        self.assertTrue(support.waited_until(
            lambda: len(arriving.conversations(self.agent)) == 1, PATIENCE))

        self.assertEqual([], self.landed_files())
        self.assertNotIn("report.csv", self.the_body())
        self.assertIn("have a look", self.the_body(),
                      "one file that could not be taken in lost the words that came with it")
        self.assertIn("not what was sent", self.said_in_the_log())

    def test_a_path_outside_the_channels_own_directory_is_never_taken(self):
        # An adapter is a program rundesk starts, and one naming somewhere else entirely would
        # otherwise have rundesk copy that file into the agent's reach and then delete it.
        elsewhere = self.home / "outside" / "secrets.txt"
        elsewhere.parent.mkdir(parents=True, exist_ok=True)
        elsewhere.write_bytes(b"not yours")
        self.an_adapter()
        self.a_channel(saying=self.a_message_arrived(
            text="have a look", attachments=[{"name": "x.txt", "at": str(elsewhere), "bytes": 9}]))
        self.hosting_now()
        self.assertTrue(support.waited_until(
            lambda: len(arriving.conversations(self.agent)) == 1, PATIENCE))

        self.assertEqual([], self.landed_files())
        self.assertTrue(elsewhere.exists(), "a file it refused to take was removed anyway")

    def test_nothing_a_stranger_attached_is_ever_fetched_from(self):
        at = self.a_staged_file()
        self.an_adapter()
        self.a_channel(allowed=("2207",), saying=json.dumps({
            "say": "arrived", "conversation": "1180", "user": "9999", "text": "let me in",
            "external_id": "8841", "attachments": [{"name": "x", "at": str(at), "bytes": 8}]}))
        self.hosting_now()
        support.waited_until(lambda: "connected" in self.said_in_the_log(), PATIENCE)
        self.assertEqual([], arriving.conversations(self.agent))
        self.assertEqual([], self.landed_files())
        self.assertTrue(at.exists(), "a stranger's message reached the filesystem")


class MarkingWhatArrived(Hosting):
    """The one turn state that needs no turn: a message arriving is the whole of the event.

    Nothing in this build ever sent `{"do": "state"}`, so every mark the adapter can put up —
    four of them, and a typing indicator — was written, tested and unreachable.
    """

    def test_a_message_from_somebody_allowed_is_marked_as_seen(self):
        self.an_adapter()
        self.a_channel(saying=self.a_message_arrived())
        self.hosting_now()
        self.assertTrue(support.waited_until(
            lambda: any(one.get("do") == "state" for one in self.what_it_was_told()), PATIENCE),
            f"nothing was ever sent to mark it. It said: {self.said_in_the_log()}")

        marked = next(one for one in self.what_it_was_told() if one.get("do") == "state")
        self.assertEqual(hosting.SEEN, marked["state"])
        self.assertEqual("1180", marked["place"])
        self.assertEqual("8841", marked["external_id"],
                         "the mark named something other than the message that asked for it")

    def test_a_stranger_is_never_marked(self):
        # A mark is the agent visibly attending to somebody it is about to ignore, in a room full
        # of people, and it confirms that it is listening.
        self.an_adapter()
        self.a_channel(allowed=("2207",), saying=json.dumps({
            "say": "arrived", "conversation": "1180", "user": "9999", "text": "let me in",
            "external_id": "8841"}))
        self.hosting_now()
        support.waited_until(lambda: "connected" in self.said_in_the_log(), PATIENCE)
        self.assertEqual([], [one for one in self.what_it_was_told()
                              if one.get("do") == "state"])

    def test_a_message_with_no_id_of_its_own_is_not_marked(self):
        # There is nothing on that platform to put a mark on, and a `state` naming no message is a
        # record the adapter can do nothing with.
        self.an_adapter()
        self.a_channel(saying=json.dumps({"say": "arrived", "conversation": "1180",
                                          "user": "2207", "text": "hello"}))
        self.hosting_now()
        self.assertTrue(support.waited_until(
            lambda: len(arriving.conversations(self.agent)) == 1, PATIENCE))
        self.assertEqual([], [one for one in self.what_it_was_told()
                              if one.get("do") == "state"])


class TalkingToOne(Hosting):

    def test_something_sent_reaches_the_adapter(self):
        self.an_adapter()
        self.a_channel(told=True)
        watching = self.hosting_now()
        self.assertTrue(hosting.told(self.agent, self.where, watching, "discord", "1180",
                                     ["the daily report"]))
        self.assertTrue(support.waited_until(
            lambda: self.heard.exists() and "the daily report" in self.heard.read_text(), 5.0))

    def test_an_answer_quotes_what_it_answers_and_marks_it_done(self):
        # The ✅ the owner asked for, and it needs no provider: *answered* is a fact about delivery,
        # known the moment the adapter acknowledges it.
        self.an_adapter()
        self.a_channel(told=True)
        watching = self.hosting_now()
        self.assertTrue(hosting.told(self.agent, self.where, watching, "discord", "1180",
                                     ["here is the report"], answering="8841"))
        self.assertTrue(support.waited_until(
            lambda: any(json.loads(one).get("do") == "state"
                        for one in self.told_lines()), 5.0),
            "no state record followed the delivery")
        marked = [json.loads(one) for one in self.told_lines()
                  if json.loads(one).get("do") == "state"]
        self.assertEqual("done", marked[0]["state"])
        self.assertEqual("8841", marked[0]["external_id"])
        delivered = [json.loads(one) for one in self.told_lines()
                     if json.loads(one).get("do") == "deliver"]
        self.assertEqual("8841", delivered[0]["reply_to"])

    def test_commentary_neither_quotes_nor_marks_anything(self):
        # Thinking and tool activity are not answers. A thread of quoted replies is unreadable, and
        # marking a message done for each of them says the turn finished several times.
        self.an_adapter()
        self.a_channel(told=True)
        watching = self.hosting_now()
        hosting.told(self.agent, self.where, watching, "discord", "1180", ["reading files.py"])
        self.assertTrue(support.waited_until(
            lambda: any(json.loads(one).get("do") == "deliver" for one in self.told_lines()), 5.0))
        time.sleep(0.5)
        for one in self.told_lines():
            record = json.loads(one)
            self.assertNotIn("reply_to", record)
            self.assertNotEqual("state", record.get("do"))

    def test_an_answer_split_in_pieces_quotes_once(self):
        # One answer is one answer. Quoting the same message four times is four notifications.
        self.an_adapter()
        self.a_channel(told=True)
        watching = self.hosting_now()
        hosting.told(self.agent, self.where, watching, "discord", "1180",
                     ["first", "second", "third"], answering="8841")
        self.assertTrue(support.waited_until(
            lambda: len([one for one in self.told_lines()
                         if json.loads(one).get("do") == "deliver"]) == 3, 5.0))
        quoted = [json.loads(one) for one in self.told_lines()
                  if json.loads(one).get("do") == "deliver" and "reply_to" in json.loads(one)]
        self.assertEqual(1, len(quoted))
        self.assertEqual("first", quoted[0]["text"])

    def test_sending_to_a_channel_that_is_not_running_says_so_rather_than_raising(self):
        watching = hosting.Watching({}, {}, {})
        self.assertFalse(hosting.told(self.agent, self.where, watching, "discord", "1180", ["x"]))

    def test_a_delivery_carries_the_files_it_was_approved_to_carry(self):
        # `files.approved` had no caller at all: the whole outbound path was built, its refusals
        # tested, and no record ever reached the adapter with a file on it.
        at = directory.home(self.agent) / "chart.png"
        at.parent.mkdir(parents=True, exist_ok=True)
        at.write_bytes(b"a picture")
        self.an_adapter()
        self.a_channel(told=True)
        watching = self.hosting_now()
        carrying = delivery.carried(self.agent, [str(at)])

        self.assertTrue(hosting.told(self.agent, self.where, watching, "discord", "1180",
                                     ["here it is"], carrying.files))

        self.assertTrue(support.waited_until(
            lambda: any(one.get("files") for one in self.what_it_was_told()), PATIENCE),
            "a delivery that was asked to carry a file carried nothing")
        sent = next(one for one in self.what_it_was_told() if one.get("files"))["files"][0]
        self.assertEqual({"name", "at", "bytes", "sha256"}, set(sent))
        self.assertEqual(str(at), sent["at"])
        self.assertEqual(9, sent["bytes"], "the far side was given nothing to check the size against")

    def test_files_go_with_the_last_piece_and_never_with_every_one(self):
        # A platform hangs an attachment under the message it came with, so a file on each piece is
        # the same file posted three times.
        at = directory.home(self.agent) / "chart.png"
        at.parent.mkdir(parents=True, exist_ok=True)
        at.write_bytes(b"a picture")
        self.an_adapter()
        self.a_channel(told=True)
        watching = self.hosting_now()
        carrying = delivery.carried(self.agent, [str(at)])

        hosting.told(self.agent, self.where, watching, "discord", "1180",
                     ["first", "second", "third"], carrying.files)

        self.assertTrue(support.waited_until(
            lambda: len([one for one in self.what_it_was_told()
                         if one.get("do") == "deliver"]) == 3, PATIENCE))
        delivered = [one for one in self.what_it_was_told() if one.get("do") == "deliver"]
        self.assertEqual([False, False, True], [bool(one.get("files")) for one in delivered])


class WhatAPreviousGatewayLeft(Hosting):

    def test_one_still_connected_is_adopted_rather_than_started_again(self):
        self.an_adapter()
        self.a_channel()
        self.hosting_now()
        support.waited_until(lambda: hosting.still_running(self.agent, "discord"), 5.0)

        fresh = hosting.settled(self.agent, self.where)
        self.started.append(fresh)
        self.assertIn("discord", fresh.running)
        self.assertFalse(fresh.running["discord"].mine,
                         "an adapter this process did not start was claimed as its own")

    def test_an_adopted_one_is_stopped_with_this_gateway(self):
        # **This asserted the opposite, and asserting it is what kept the defect.** `stopping`
        # filtered to `one.mine`, so an adapter adopted from a gateway that is gone was skipped on
        # that shutdown and on every shutdown after it — each new gateway adopting it again, nothing
        # anywhere signalling it, and `gateways stop`, `gateways restart`, `channels remove` and
        # `agents remove` all reporting success over a program still connected as this agent. The
        # claim is a `flock` held by that very process, so the kernel is what vouches for the pid
        # before anything is signalled, which is the same discipline `gateways.standing` keeps.
        self.an_adapter()
        self.a_channel()
        self.hosting_now()
        support.waited_until(lambda: hosting.still_running(self.agent, "discord"), PATIENCE)
        fresh = hosting.settled(self.agent, self.where)
        self.started.append(fresh)

        hosting.stopping(self.agent, self.where, fresh, 4.0)

        self.assertTrue(support.waited_until(
            lambda: not hosting.still_running(self.agent, "discord"), PATIENCE),
            "an adapter this gateway adopted was left running by the shutdown, and nothing else "
            "will ever signal it")
        self.assertIn("stopped with this gateway", self.said_in_the_log())

    def test_a_record_left_by_an_adapter_that_is_gone_is_cleared(self):
        self.a_channel()
        hosting.record_of(self.agent, "discord").parent.mkdir(parents=True, exist_ok=True)
        hosting.record_of(self.agent, "discord").write_text('{"pid": 999999}', encoding="utf-8")
        hosting.settled(self.agent, self.where)
        self.assertFalse(hosting.record_of(self.agent, "discord").exists())


class WhenOneStops(Hosting):
    """What happens between an adapter dying and the next one taking its place.

    Two guarantees, and the whole suite passed with either of them deleted. The hold-off is what
    stands between a platform that is refusing us and a start every fifteen seconds for as long as
    it goes on refusing; the tail of what the adapter wrote is the only account anybody gets of
    *why* it died, and it was going nowhere.
    """

    def a_crashed_adapter(self, body=A_BROKEN_ADAPTER):
        """One channel whose adapter started, died, and has been reaped. Hands back the watching.

        Reaped by looking again rather than by waiting on the pid: a child that has exited on its
        own is a zombie until somebody takes its status, and a zombie answers every question about
        whether it is alive exactly as a running program does.
        """
        self.an_adapter(body=body)
        self.a_channel()
        watching = self.hosting_now()
        self.assertIn("discord", watching.running, "nothing was started, so nothing can crash")
        self.assertTrue(support.waited_until(
            lambda: "discord" not in self.looked_again(watching).running, PATIENCE),
            f"the adapter never stopped. It said: {self.said_in_the_log()}")
        return watching

    def test_one_that_has_just_crashed_is_not_started_again_on_the_very_next_pass(self):
        # **`AGAIN_AFTER`, and the whole suite passed with the guard deleted.** Without it a channel
        # whose platform is down, or whose adapter is not installed, is a fork and an exec every
        # time the gateway comes round — which is a machine hammering somebody who is refusing it,
        # and a log gaining a start and a death every fifteen seconds for as long as it lasts.
        watching = self.a_crashed_adapter()
        held_off = watching.waiting["discord"]

        self.looked_again(watching)

        self.assertNotIn("discord", watching.running,
                         "an adapter that had just crashed was started again immediately")
        self.assertEqual(held_off, watching.waiting["discord"],
                         "the hold-off was pushed forward by a pass that started nothing, so it "
                         "would never end")

    def test_the_hold_off_ends_and_the_channel_comes_back(self):
        # The other half, and without it the case above passes with the *restart* deleted rather
        # than the guard: a channel that was briefly down would simply never come back.
        watching = self.a_crashed_adapter()
        watching.waiting["discord"] = time.monotonic() - hosting.AGAIN_AFTER - 1

        self.looked_again(watching)

        self.assertIn("discord", watching.running,
                      "the hold-off never ended, so a channel that stopped once stays stopped")

    def test_what_an_adapter_wrote_before_it_died_reaches_the_agents_own_log(self):
        # **`_said_on_the_way_out`, and the whole suite passed with it stubbed to a no-op.** The
        # error stream is where an adapter says why it could not go on, and a person looking into a
        # channel that keeps stopping reads the agent's day log, not a file inside the channel's own
        # directory that nothing points at.
        self.a_crashed_adapter(body=A_DYING_ADAPTER)

        said = self.said_in_the_log()
        self.assertIn("channel discord: the adapter stopped with code 2", said)
        self.assertIn("line 199 of what went wrong", said,
                      "the last thing the adapter said before it died went nowhere")

    def test_one_that_says_starting_it_again_cannot_help_is_not_started_again(self):
        # **`WILL_NOT_FIX`, and the whole suite passed with the exit code ignored.** `78` is
        # `EX_CONFIG`, and an adapter answers with it exactly where trying again is the damage: a
        # revoked Discord token on the flat ten-second hold-off is about 8,600 login attempts a day,
        # which is the Cloudflare ban of this machine's address that the adapter's own close-code
        # table was written to avoid.
        watching = self.a_crashed_adapter(body=AN_ADAPTER_THAT_CANNOT_COME_RIGHT)

        self.assertEqual(hosting.NEVER_AGAIN, watching.waiting["discord"],
                         "an adapter that said its configuration is wrong was held off for ten "
                         "seconds like any other crash")
        # The hold-off taken away entirely, which is what proves the refusal is not merely it: with
        # nothing to wait for, an ordinary crash comes straight back and this one must not.
        was = hosting.AGAIN_AFTER
        hosting.AGAIN_AFTER = 0.0
        self.addCleanup(setattr, hosting, "AGAIN_AFTER", was)

        self.looked_again(watching)

        self.assertNotIn("discord", watching.running,
                         "a channel whose credential is gone was started again anyway")

    def test_why_it_will_not_be_started_again_is_said_where_an_owner_reads_it(self):
        # It is said once and there will be no second attempt to report it, so a line nobody can
        # act on is the same as no line at all.
        self.a_crashed_adapter(body=AN_ADAPTER_THAT_CANNOT_COME_RIGHT)

        said = self.said_in_the_log()
        self.assertIn("EX_CONFIG", said)
        self.assertIn("will not start it again", said)
        self.assertIn("Discord refused the token (HTTP 401)", said,
                      "what the adapter said was wrong went nowhere")

    def test_only_a_bounded_tail_of_it_reaches_the_log(self):
        # The other half of the same function, and the reason it is bounded at all: a program that
        # wrote a megabyte of traceback would roll the rest of the day off the end of the file
        # somebody opened to read it — the failure destroyed in the act of reporting it.
        self.a_crashed_adapter(body=A_DYING_ADAPTER)

        said = self.said_in_the_log()
        self.assertEqual(hosting.SAID_AT_MOST, said.count("of what went wrong"),
                         "what was copied into the log is not bounded by SAID_AT_MOST")
        self.assertNotIn("line 0 of what went wrong", said,
                         "the whole of the error stream was copied, not its tail")


class WhenOneIsKilledOutright(Hosting):
    """A `SIGKILL` lets no tidying code run anywhere, which is the only way to ask the kernel.

    The property `hosting`'s docstring rests its whole design on — *the claim lives exactly as long
    as the child and the kernel drops it however that ends* — and nothing here asked it the one way
    that cannot be answered by code this product wrote. `firing`'s suite has asked it since the day
    it was written.
    """

    def test_the_claim_is_dropped_by_the_kernel_and_the_gateway_carries_on(self):
        self.an_adapter()
        self.a_channel()
        watching = self.hosting_now()
        pid = watching.running["discord"].pid
        self.assertTrue(support.waited_until(
            lambda: hosting.still_running(self.agent, "discord"), PATIENCE),
            f"the adapter never took its claim. It said: {self.said_in_the_log()}")

        ended_outright(self, pid, signal.SIGKILL)

        self.assertTrue(support.waited_until(
            lambda: not hosting.still_running(self.agent, "discord"), PATIENCE),
            "the claim outlived the child tree that was holding it")
        self.looked_again(watching)
        self.assertNotIn("discord", watching.running,
                         "the loop went on hosting an adapter that no longer exists")
        self.assertFalse(hosting.record_of(self.agent, "discord").exists(),
                         "the record of an adapter that is gone was left for the next gateway")
        self.assertIn("channel discord: the adapter stopped", self.said_in_the_log())

    def test_the_channel_comes_back_once_the_hold_off_has_passed(self):
        # A gateway that is otherwise fine goes on hosting its agent, and a channel whose adapter
        # was killed is one that reconnects rather than one that is gone until somebody notices.
        self.an_adapter()
        self.a_channel()
        watching = self.hosting_now()
        pid = watching.running["discord"].pid
        self.assertTrue(support.waited_until(
            lambda: hosting.still_running(self.agent, "discord"), PATIENCE))

        ended_outright(self, pid, signal.SIGKILL)
        self.assertTrue(support.waited_until(
            lambda: "discord" not in self.looked_again(watching).running, PATIENCE),
            f"it was never reaped. It said: {self.said_in_the_log()}")
        watching.waiting["discord"] = time.monotonic() - hosting.AGAIN_AFTER - 1

        self.looked_again(watching)

        self.assertIn("discord", watching.running, "a channel whose adapter was killed outright "
                                                   "never came back")
        self.assertNotEqual(pid, watching.running["discord"].pid)


class StoppingThem(Hosting):

    def test_one_this_gateway_started_is_stopped(self):
        self.an_adapter()
        self.a_channel()
        watching = self.hosting_now()
        support.waited_until(lambda: hosting.still_running(self.agent, "discord"), 5.0)
        hosting.stopping(self.agent, self.where, watching, 4.0)
        self.assertTrue(support.waited_until(
            lambda: not hosting.still_running(self.agent, "discord"), 5.0))

    def test_stopping_when_nothing_is_running_is_not_a_failure(self):
        self.assertEqual({}, hosting.stopping(self.agent, self.where,
                                              hosting.Watching({}, {}, {}), 4.0).running)


if __name__ == "__main__":
    unittest.main()
