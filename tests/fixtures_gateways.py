"""A gateway hosted for real, and a channel on it, for the suites that drive one.

Not named `test_…`, so `scripts/suites` does not try to run it as one — the same shape as
`tests/fixtures_skills.py`.

**Here rather than in either suite because both need it and neither owns it.** `tests/test_gateway_
host.py` proves what a supervised process does and `tests/test_gateway_channels.py` proves what a
channel on one does; they are two files so that the runner, which parallelises whole files, can run
them at the same time. A base class copied into both would be two bases that drift.

Neither class holds a case of its own, and that is deliberate: `unittest` inherits test methods, so
a class carrying both helpers and cases hands every case to every subclass that wanted only the
helpers.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional, Tuple

import support
from rundesk.agents import directory
from rundesk.channels import kept as channels
from rundesk.core import paths
from rundesk.gateways import standing
from rundesk.utils import logs

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


class WithAChannel(WithAnAgent):
    """A real gateway with a real channel on it, and the means to drive one. No case of its own.

    **The cases live in `TheChannelsItHosts` below, and the separation is load-bearing.** `unittest`
    inherits test methods, so a class holding both these helpers and those cases hands every case to
    every subclass that wanted only the helpers — and two of them below want only the helpers. They
    re-ran all twenty of `TheChannelsItHosts`' cases to add one and fourteen of their own, which was
    a hundred and five seconds of every run of this suite, proving three times what was proved once.
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


