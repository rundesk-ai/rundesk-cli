"""The seam a brain is reached through — every row of provider-adapter.

**This suite takes the adapter as an argument.** It is what a shipped adapter passes and
what a stranger's passes, which is the whole of what makes "a brain rundesk has never
heard of" a claim rather than a hope:

    python3 tests/test_provider.py                          # the stand-in, in the gate
    python3 tests/test_provider.py --adapter /opt/my-brain  # yours

The cases come in two kinds, and the difference matters.

**What holds of any adapter** — `TheContract` below — is run against whatever `--adapter`
names, and against a stand-in when nothing does. These assert the shape of a turn and
never its content, because what a brain answers is the brain's business.

**What holds of the seam** — everything after it — is run against stand-ins this file
writes, because the cases are about behaviour no real brain can be asked to produce on
demand: a running total, a record of a kind nobody knows, a child left running.

Nothing here reaches the network or needs an account **when it is run bare**, which is how
the gate runs it: the adapters it drives are small programs, which is the same thing every
adapter is. Pointed at a real adapter it will really run that adapter's brain, which is
what an author wanting to prove their own adapter wants it to do — and why the shipped
one's run against a real account is a probe rather than part of the gate.

Run: python3 tests/test_provider.py
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import stat
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from rundesk_cli import process, provider  # noqa: E402

PY = sys.executable

#: The adapter under test, when one was named. `None` means the stand-in below, which is
#: what the gate runs and what this file is written against.
ADAPTER: Path | None = None

#: The private home to hand the adapter under test, when one was named. A brain that
#: needs a sign-in cannot complete a turn out of an empty directory — pointing this at a
#: home that already has one is what lets these cases drive a real adapter for real.
HOME: Path | None = None

#: How long an adapter may say nothing before a case here gives up on it. Not how long a
#: turn may take: a real brain is entitled to think for as long as it needs, and pointed
#: at a real adapter these cases really run one. Ten minutes of complete silence is a
#: brain that has stopped rather than one that is working.
PATIENCE_SECONDS = 600.0


# --------------------------------------------------------------------------------------
# The stand-ins. Each is a whole adapter, written to the contract in the guide, and each
# exists because it does one thing a real brain cannot be asked to do to order.
# --------------------------------------------------------------------------------------

#: Reports everything there is to report. The reference an author reads next to the guide.
PLAIN = '''
import json, os, sys

if "--capabilities" in sys.argv:
    print(json.dumps({"tools": True, "resume": True, "model": True, "usage": True}))
    sys.exit(0)

prompt = sys.stdin.read()
say = lambda **it: (sys.stdout.write(json.dumps(it) + "\\n"), sys.stdout.flush())

say(type="think", text="working out what was asked")
say(type="tool", id="1", name="Whatever", did="read")
say(type="result", id="1", ok=True, summary="read one thing")
say(type="text", text="you said: " + prompt.strip())
say(type="usage", input=12, output=3, cached=100, model="stand-in-1")
say(type="done", ok=True, session=os.environ.get("RUNDESK_RESUME") or "session-one")
'''

#: Says it can do nothing, and does a whole turn anyway. A conversational CLI with no
#: loop of its own is this, and it is a first-class brain rather than a degraded one.
BARE = '''
import json, sys

if "--capabilities" in sys.argv:
    print("{}")
    sys.exit(0)

sys.stdin.read()
sys.stdout.write(json.dumps({"type": "text", "text": "answered"}) + "\\n")
sys.stdout.write(json.dumps({"type": "done", "ok": True}) + "\\n")
sys.stdout.flush()
'''

#: Emits a record of a kind nobody here has heard of, so a brain can be ahead of us.
STRANGE = '''
import json, sys

if "--capabilities" in sys.argv:
    print("{}")
    sys.exit(0)

sys.stdin.read()
out = sys.stdout
out.write(json.dumps({"type": "constellation", "shape": "orion"}) + "\\n")
out.write("this line is not even JSON\\n")
out.write(json.dumps(["not an object at all"]) + "\\n")
out.write(json.dumps({"type": "text", "text": "and a real one"}) + "\\n")
out.write(json.dumps({"type": "done", "ok": True}) + "\\n")
out.flush()
'''

#: Its brain reports the whole conversation's running total, the way a real one does. The
#: subtraction is the adapter's, and what it subtracts from lives in its own private home
#: — so it survives this process ending, which a gateway's memory would not.
COUNTING = '''
import json, os, sys

if "--capabilities" in sys.argv:
    print(json.dumps({"usage": True, "resume": True}))
    sys.exit(0)

sys.stdin.read()
home = os.environ["RUNDESK_PROVIDER_HOME"]
kept = os.path.join(home, "billed.json")
try:
    with open(kept) as f:
        before = json.load(f)
except (OSError, ValueError):
    before = {"input": 0, "output": 0}

# What this brain would report: the conversation's total, climbing every turn.
total = {"input": before["input"] + 100, "output": before["output"] + 5}
os.makedirs(home, exist_ok=True)
with open(kept, "w") as f:
    json.dump(total, f)

say = lambda **it: (sys.stdout.write(json.dumps(it) + "\\n"), sys.stdout.flush())
say(type="usage", input=total["input"] - before["input"],
    output=total["output"] - before["output"], cached=0)
say(type="done", ok=True, session="one-thread")
'''

#: Starts something that outlives it, to prove ending a turn ends everything it started.
SPAWNER = '''
import json, os, subprocess, sys

if "--capabilities" in sys.argv:
    print("{}")
    sys.exit(0)

sys.stdin.read()
child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(300)"])
sys.stdout.write(json.dumps({"type": "text", "text": "started %d" % child.pid}) + "\\n")
sys.stdout.flush()
import time
time.sleep(300)
'''

#: Reports what it was told, so a case can assert what reaches an adapter and what does not.
NOSY = '''
import json, os, sys

if "--capabilities" in sys.argv:
    print("{}")
    sys.exit(0)

prompt = sys.stdin.read()
told = {what: os.environ.get(what) for what in (
    "RUNDESK_CWD", "RUNDESK_PROVIDER_HOME", "RUNDESK_MODEL", "RUNDESK_RUN",
    "RUNDESK_RESUME", "RUNDESK_POSTURE", "RUNDESK_SETTINGS",
)}
say = lambda **it: (sys.stdout.write(json.dumps(it) + "\\n"), sys.stdout.flush())
say(type="text", text=json.dumps({"told": told, "where": os.getcwd(), "prompt": prompt}))
say(type="done", ok=True)
'''

#: Says a great deal, all of it too large to hold, to prove the loss is bounded and said.
SHOUTING = '''
import json, sys

if "--capabilities" in sys.argv:
    print("{}")
    sys.exit(0)

sys.stdin.read()
for n in range(40):
    sys.stdout.write(json.dumps({"type": "text", "text": "y" * 4000}) + "\\n")
sys.stdout.write(json.dumps({"type": "done", "ok": True}) + "\\n")
sys.stdout.flush()
'''

#: A turn that failed says so, rather than going quiet.
FAILING = '''
import json, sys

if "--capabilities" in sys.argv:
    print("{}")
    sys.exit(0)

sys.stdin.read()
sys.stderr.write("the brain could not be reached\\n")
sys.stdout.write(json.dumps({"type": "done", "ok": False}) + "\\n")
sys.stdout.flush()
sys.exit(1)
'''

STAND_INS = {
    "plain": PLAIN, "bare": BARE, "strange": STRANGE, "counting": COUNTING,
    "spawner": SPAWNER, "nosy": NOSY, "shouting": SHOUTING, "failing": FAILING,
}


class Turn:
    """What one turn through an adapter came to."""

    def __init__(self, records: list, raw: list, errors: str, outcome):
        self.records = records          # the ones we understood
        self.raw = raw                  # every line, as it was said
        self.errors = errors
        self.outcome = outcome

    def of(self, kind: str) -> list:
        return [one for one in self.records if one.get("type") == kind]

    @property
    def done(self) -> dict | None:
        ended = self.of("done")
        return ended[-1] if ended else None


class DrivesAnAdapter(unittest.IsolatedAsyncioTestCase):
    """Somewhere for an adapter to work, and one way of running it."""

    def setUp(self):
        self.where = Path(tempfile.mkdtemp(prefix="rundesk-adapter-"))
        self.addCleanup(shutil.rmtree, self.where, True)
        for what in ("cwd", "provider", "home"):
            (self.where / what).mkdir(parents=True, exist_ok=True)
        # Scratch, always. `--home` belongs to the adapter under test and to nothing
        # else: pointed at a real one, the stand-ins below wrote their own bookkeeping
        # into a brain's actual home and read what a previous run had left there.
        self.provider_home = self.where / "provider"

    def stand_in(self, which: str) -> Path:
        """One of the adapters above, on disk and runnable — which is all an adapter is."""
        at = self.where / which
        at.write_text("#!%s\n%s" % (PY, STAND_INS[which]), encoding="utf-8")
        at.chmod(at.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        return at

    def told(self, **extra) -> dict:
        said = provider.environment(
            home=self.where / "home",
            cwd=self.where / "cwd",
            provider_home=self.provider_home,
            run=extra.pop("run", "1-abcd"),
            **extra,
        )
        # The stand-ins are Python, so they need to be able to find one.
        said["PATH"] = os.environ.get("PATH", "")
        return said

    async def carry(self, adapter: Path, prompt: str = "say something", started=None,
                    steering=None, **extra) -> Turn:
        """One whole turn, exactly as rundesk runs one.

        **A turn takes as long as it takes.** Pointed at a real adapter these cases drive
        a real brain, and one is entitled to think for an hour or to sit quietly through
        a single long tool call — so what is bounded is how long it may say *nothing*,
        never how long it may work, and there is no ceiling at all. The stand-ins answer
        instantly, so the gate is quick; only an adapter that has genuinely stopped
        talking waits.
        """
        raw: list = []
        program = process.Program(
            [str(adapter)], env=self.told(**extra), cwd=self.where / "cwd",
            takes_input=True, errors_apart=True,
            silence=PATIENCE_SECONDS, ceiling=None,
        )
        await program.start()
        if started is not None:
            started(program)
        reading = asyncio.ensure_future(program.wait(sink=raw.append))
        if steering is None:
            await program.send(prompt.encode("utf-8"))
        else:
            # Records, and the input held open, exactly as rundesk drives one that said it
            # can be steered. Anything after the prompt reaches a turn already running.
            await program.send(provider.spoken(prompt))
            for word in steering:
                await asyncio.sleep(0.2)
                await program.send(provider.spoken(word))
        await program.close_input()
        outcome = await reading
        records = [it for it in (provider.understood(one) for one in raw
                                 if isinstance(one, bytes)) if it is not None]
        return Turn(records, raw, program.errors, outcome)


# --------------------------------------------------------------------------------------
# What holds of ANY adapter — the part `--adapter` swaps.
# --------------------------------------------------------------------------------------

class TheContract(DrivesAnAdapter):
    """Every case here is run against whatever adapter this suite was given.

    They assert the *shape* of a turn and never its content: what a brain answers is the
    brain's own business, and a suite that checked the words would be a suite only one
    brain could pass.
    """

    def setUp(self):
        super().setUp()
        # Only here. A brain with a sign-in cannot complete a turn out of an empty
        # directory, so an author proving their own adapter points this at the home that
        # has one — and nothing that drives a stand-in ever sees it.
        if HOME is not None and ADAPTER is not None:
            self.provider_home = HOME

    def under_test(self) -> Path:
        return ADAPTER if ADAPTER is not None else self.stand_in("plain")

    async def test_an_adapter_says_what_it_can_do_without_carrying_a_turn(self):
        """R-PRV-15 — asked before a turn is admitted, so nothing is assumed of a brain
        and nothing is inferred from its name."""
        said = await provider.capabilities(self.under_test(), self.told())
        self.assertEqual(sorted(provider.CAPABILITIES), sorted(said))
        for what, answer in said.items():
            self.assertIsInstance(answer, bool, f"'{what}' was answered with something else")

    async def test_an_adapter_carries_a_whole_turn(self):
        """R-PRV-4 — the one thing every adapter must do. A turn that reached its end
        says so; only `done` is required, and it is required."""
        turn = await self.carry(self.under_test())
        self.assertIsNotNone(turn.done, "the turn never said it was done")
        self.assertTrue(turn.done.get("ok"), f"the turn failed: {turn.errors}")

    async def test_what_an_adapter_reports_is_whole_records_one_to_a_line(self):
        """R-PRV-4 — half a record is not a smaller record, it is a corrupt one."""
        turn = await self.carry(self.under_test())
        self.assertTrue(turn.raw, "it reported nothing at all")
        for line in turn.raw:
            self.assertNotIsInstance(line, process.Gap, "records were lost carrying a turn")

    async def test_what_an_adapter_says_went_wrong_is_kept_off_what_it_reports(self):
        """R-PRV-6 — anything not part of the structure corrupts it, and what explains a
        failure would be exactly the thing that caused one."""
        turn = await self.carry(self.under_test())
        for line in turn.raw:
            self.assertIsNotNone(
                provider.understood(line) if _looks_like_json(line) else {},
                "something unreadable arrived on the stream meant to be parsed")

    async def test_an_adapter_naming_no_model_leaves_none_claimed(self):
        """R-PRV-9 — a model is what actually answered. One that was merely asked for is
        not a measurement, and claiming it makes every later reading of the cost a guess
        wearing a fact's clothes."""
        turn = await self.carry(self.under_test())
        for said in turn.of("usage"):
            if "model" in said:
                self.assertTrue(said["model"], "it claimed a model with no name in it")

    async def test_an_adapter_says_what_a_tool_did_in_words_no_brain_owns(self):
        """R-PRV-8 — the same action is `Bash` on one brain and `run_terminal_command` on
        the next. A channel that learned either would carry that vendor's words forever."""
        turn = await self.carry(self.under_test())
        for said in turn.of("tool"):
            if "did" in said:
                self.assertIn(said["did"], ("read", "search", "run", "edit", "list"),
                              "a tool was described in its own brain's vocabulary")

    async def test_an_adapter_can_be_steered_exactly_as_much_as_it_said_it_could(self):
        """R-PRV-15, R-PRV-19 — the one capability that changes how a turn is *run*, so
        saying it wrongly is a turn that hangs rather than a feature that is missing. An
        adapter that says it can be steered has its input held open and reads records; one
        that says it cannot is given the prompt and told there is no more."""
        can = await provider.capabilities(self.under_test(), self.told())
        turn = await self.carry(self.under_test(), steering=["and one more thing"]
                                if can["steer"] else None)
        self.assertIsNotNone(turn.done, "it did not finish a turn run the way it asked for")
        self.assertTrue(turn.done.get("ok"), f"the turn failed: {turn.errors}")

    async def test_an_adapter_works_where_it_is_told_and_not_where_it_pleases(self):
        """R-PRV-3, R-PRV-14 — an agent's workspace is its own, and an adapter reaching
        another one is one agent reading another's work."""
        turn = await self.carry(self.under_test())
        self.assertIsNotNone(turn.done, "the turn never finished, so nothing was proved")
        left = {path.name for path in (self.where / "cwd").iterdir()}
        self.assertNotIn("home", left, "it wrote outside the workspace it was given")


# --------------------------------------------------------------------------------------
# What holds of the seam — always the stand-ins, because no real brain does these to order.
# --------------------------------------------------------------------------------------

class ABrainWithNoLoopOfItsOwn(DrivesAnAdapter):
    async def test_an_adapter_that_runs_no_tools_carries_a_whole_turn(self):
        """R-PRV-7 — a conversational CLI with nothing but an answer in it is a first
        class brain. The work is absent, not missing, and nothing pretends otherwise."""
        turn = await self.carry(self.stand_in("bare"))
        self.assertTrue(turn.done.get("ok"))
        self.assertEqual([], turn.of("tool"), "it appeared to have run tools it has none of")
        self.assertEqual([], turn.of("usage"))
        self.assertEqual(1, len(turn.of("text")))

    async def test_an_adapter_that_says_it_can_do_nothing_is_believed(self):
        """R-PRV-15 — absent is no, so the smallest honest answer is an empty one."""
        said = await provider.capabilities(self.stand_in("bare"), self.told())
        self.assertEqual({what: False for what in provider.CAPABILITIES}, said)

    async def test_an_adapter_that_cannot_answer_the_question_can_do_nothing(self):
        """R-PRV-15 — the smallest legitimate adapter in the guide is a shell script that
        answers a prompt. Telling its author their brain is broken for not knowing a flag
        we invented would be this seam failing, not their adapter."""
        deaf = self.where / "deaf"
        deaf.write_text("#!/bin/sh\nexit 3\n", encoding="utf-8")
        deaf.chmod(0o755)
        said = await provider.capabilities(deaf, self.told())
        self.assertEqual({what: False for what in provider.CAPABILITIES}, said)


class ARecordNobodyHereKnows(DrivesAnAdapter):
    async def test_a_record_of_a_kind_we_do_not_know_is_kept_rather_than_refused(self):
        """R-PRV-5 — a brain that can only grow when we release is a brain we have made
        slower than we are. Kept verbatim, shown to nobody, and the turn finishes."""
        turn = await self.carry(self.stand_in("strange"))
        self.assertTrue(turn.done.get("ok"), "an unknown record broke the turn")
        said = [one.decode() for one in turn.raw if isinstance(one, bytes)]
        self.assertTrue(any("constellation" in one for one in said),
                        "the record we did not understand was thrown away")
        self.assertEqual([], [one for one in turn.records
                              if one.get("type") == "constellation"],
                         "a record we do not understand was passed off as one we do")

    def test_a_line_that_is_not_a_record_at_all_is_understood_as_nothing(self):
        """R-PRV-5 — nothing here raises. Unreadable, not an object, and a kind we have
        never heard of are one answer: keep it, show it to nobody."""
        self.assertIsNone(provider.understood(b"not json at all"))
        self.assertIsNone(provider.understood(b'["a list"]'))
        self.assertIsNone(provider.understood(b'{"type":"constellation"}'))
        self.assertIsNone(provider.understood(b'{"no":"type"}'))
        self.assertIsNone(provider.understood(b"\xff\xfe not even text"))
        self.assertEqual({"type": "done", "ok": True},
                         provider.understood(b'{"type":"done","ok":true}'))


class WhatAnAdapterIsTold(DrivesAnAdapter):
    async def test_an_adapter_is_told_where_to_work_and_where_its_own_things_go(self):
        """R-PRV-3 — the workspace is the agent's and the home is the adapter's, and they
        are different directories on purpose: a brain reading the agent's rules must not
        be reading its own configuration at the same time."""
        turn = await self.carry(self.stand_in("nosy"))
        said = json.loads(turn.of("text")[0]["text"])
        self.assertEqual(str(self.where / "cwd"), said["told"]["RUNDESK_CWD"])
        self.assertEqual(str(self.provider_home), said["told"]["RUNDESK_PROVIDER_HOME"])
        # Resolved on both sides: a temporary directory on macOS is reached through a
        # link, so the path a program reports itself standing in is the real one and the
        # path it was handed is the one with the link still in it.
        self.assertEqual((self.where / "cwd").resolve(), Path(said["where"]).resolve(),
                         "it did not start where told")

    async def test_the_prompt_arrives_on_the_stream_meant_for_it(self):
        """R-PRV-4 — never on a command line, where the process list and the shell's
        history would both keep a copy of whatever was asked."""
        turn = await self.carry(self.stand_in("nosy"), prompt="what changed today?")
        said = json.loads(turn.of("text")[0]["text"])
        # Stripped, because what arrives is the whole of stdin up to the end of input and
        # a record is a record because of where it ends — so the newline that terminated
        # it is part of what was written, not part of what was asked.
        self.assertEqual("what changed today?", said["prompt"].strip())

    async def test_what_an_owner_set_reaches_the_brain_unread_and_unchanged(self):
        """R-PRV-16 — a new flag on somebody's CLI is theirs to reach today, not ours to
        release. Nothing here reads it, so nothing here can be wrong about it."""
        turn = await self.carry(self.stand_in("nosy"),
                                settings={"effort": "high", "flags": ["--no-color"]})
        said = json.loads(turn.of("text")[0]["text"])
        self.assertEqual({"effort": "high", "flags": ["--no-color"]},
                         json.loads(said["told"]["RUNDESK_SETTINGS"]))

    async def test_an_adapter_is_told_how_much_of_the_machine_a_turn_may_touch(self):
        """R-PRV-18 — a posture in rundesk's words. What it means in tools, sandboxes or
        permission modes is the adapter's to decide, and never ours to believe in."""
        turn = await self.carry(self.stand_in("nosy"), posture=provider.READ)
        said = json.loads(turn.of("text")[0]["text"])
        self.assertEqual("read", said["told"]["RUNDESK_POSTURE"])

    async def test_what_was_not_asked_for_is_left_unset_rather_than_set_to_nothing(self):
        """R-PRV-3 — a brain asked to use a model called empty string does something odd
        with it. One told nothing falls back to its own default, which is what was meant."""
        turn = await self.carry(self.stand_in("nosy"))
        said = json.loads(turn.of("text")[0]["text"])
        self.assertIsNone(said["told"]["RUNDESK_MODEL"])
        self.assertIsNone(said["told"]["RUNDESK_RESUME"])
        self.assertIsNone(said["told"]["RUNDESK_SETTINGS"])

    async def test_no_vendor_variable_is_put_in_front_of_an_adapter(self):
        """R-PRV-1 — which variable a brain wants is that brain's adapter's business.
        Set here, the vendor would be in the core, which is the seam failing."""
        told = self.told(model="whatever", resume="a-handle")
        self.assertEqual(
            sorted(["HOME", "PATH", "RUNDESK_HOME", "TERM", "LANG", "RUNDESK_CWD",
                    "RUNDESK_PROVIDER_HOME", "RUNDESK_RUN", "RUNDESK_POSTURE",
                    "RUNDESK_MODEL", "RUNDESK_RESUME"]),
            sorted(told))


class CarryingAConversationOn(DrivesAnAdapter):
    async def test_an_adapter_is_handed_back_the_handle_it_reported(self):
        """R-PRV-17 — the handle is the brain's own and opaque here. Rundesk keeps it and
        hands it back; it never reads it and never gives it to a different brain."""
        first = await self.carry(self.stand_in("plain"))
        self.assertEqual("session-one", first.done.get("session"))
        again = await self.carry(self.stand_in("plain"), resume=first.done["session"])
        self.assertEqual("session-one", again.done.get("session"))
        said = await self.carry(self.stand_in("nosy"), resume="a-handle-of-its-own")
        told = json.loads(said.of("text")[0]["text"])
        self.assertEqual("a-handle-of-its-own", told["told"]["RUNDESK_RESUME"])


class WhatATurnCost(DrivesAnAdapter):
    async def test_a_brain_reporting_a_running_total_reports_only_this_turns_share(self):
        """R-USE-3 — three one-word replies on one thread reported five, ten and fifteen
        in the build this replaces. Reported as a turn's cost, that overstates every turn
        after the first, and a spend limit reading it fires on how long a conversation is
        rather than on what it cost.

        The subtraction is the adapter's and what it subtracts from is in its own private
        home, so it survives the process — which is the half the prior art got wrong, its
        running totals living in a gateway's memory and going with every restart."""
        counting = self.stand_in("counting")
        for _ in range(3):
            turn = await self.carry(counting)
            self.assertEqual({"type": "usage", "input": 100, "output": 5, "cached": 0},
                             turn.of("usage")[0],
                             "a turn was charged the conversation's running total")

    async def test_what_a_brain_remembers_between_turns_survives_the_process(self):
        """R-USE-3 — an adapter is a fresh process every turn, so anything it must carry
        from the last one has to be on disk. The private home is where."""
        counting = self.stand_in("counting")
        await self.carry(counting)
        self.assertTrue((self.provider_home / "billed.json").is_file(),
                        "it kept what it must subtract from somewhere that does not last")


class EndingATurn(DrivesAnAdapter):
    async def test_ending_a_turn_ends_the_adapter_and_everything_it_started(self):
        """R-PRV-11 — a brain runs editors, search tools and language servers, and ending
        only the process we can see leaves every one of them behind."""
        held: list = []
        spawner = self.stand_in("spawner")
        program = process.Program(
            [str(spawner)], env=self.told(), cwd=self.where / "cwd",
            takes_input=True, errors_apart=True, silence=None,
        )
        await program.start()
        reading = asyncio.ensure_future(program.wait(sink=held.append))
        await program.send(b"go")
        await program.close_input()
        started = await self._until_it_says(held)
        self.assertTrue(await program.end(), "the process group was not really taken")
        await reading
        self.assertFalse(_alive(started), "the adapter went and left its child running")

    async def _until_it_says(self, held: list, seconds: float = 20.0) -> int:
        deadline = asyncio.get_event_loop().time() + seconds
        while asyncio.get_event_loop().time() < deadline:
            for one in held:
                said = provider.understood(one) if isinstance(one, bytes) else None
                if said and said.get("type") == "text":
                    return int(said["text"].split()[-1])
            await asyncio.sleep(0.05)
        self.fail("the adapter never said what it had started")


class AnAdapterThatCannotBeRun(DrivesAnAdapter):
    def test_a_brain_this_rundesk_has_never_heard_of_is_the_ordinary_case(self):
        """R-PRV-1 — a path is a provider exactly as much as a shipped adapter is. There
        is no list of brains here, so not recognising a name is not a failure."""
        mine = self.stand_in("bare")
        self.assertEqual(mine, provider.program(str(mine)))

    def test_the_only_failure_is_nothing_runnable_being_there(self):
        """R-PRV-12 — said before a turn is admitted, and said about the thing that is
        actually missing rather than about the name."""
        with self.assertRaises(provider.NotRunnable):
            provider.program(str(self.where / "no-such-brain"))
        with self.assertRaises(provider.NotRunnable):
            provider.program("")
        cannot = self.where / "not-runnable"
        cannot.write_text("#!/bin/sh\ntrue\n", encoding="utf-8")
        cannot.chmod(0o644)
        with self.assertRaises(provider.NotRunnable) as why:
            provider.program(str(cannot))
        self.assertIn("run", str(why.exception))

    def test_a_shipped_adapter_is_found_by_looking_rather_than_by_being_listed(self):
        """R-PRV-1 — a list of adapters here is a second place to remember, and the one
        that gets forgotten. The directory is the list."""
        mine = self.stand_in("bare")
        self.assertEqual(mine, provider.program("bare", adapters=self.where))

    def test_two_brains_of_one_name_in_two_places_are_two_brains(self):
        """R-AGT-8 — what is kept per brain is keyed by this, so two of them sharing a
        name would share one private home, and one's credentials and session files would
        be handed to the other."""
        self.assertEqual("codex", provider.key("codex"))
        one = provider.key("/opt/one/brain")
        other = provider.key("/opt/other/brain")
        self.assertNotEqual(one, other)
        self.assertTrue(one.startswith("brain-"))
        self.assertEqual(one, provider.key("/opt/one/brain"), "it is not the same twice")


class ATurnThatWentWrong(DrivesAnAdapter):
    async def test_a_turn_that_failed_says_so_rather_than_going_quiet(self):
        """R-PRV-4 — a turn that ends without a word is indistinguishable from one still
        running, and the thing waiting on it cannot tell which."""
        turn = await self.carry(self.stand_in("failing"))
        self.assertIsNotNone(turn.done)
        self.assertFalse(turn.done.get("ok"))

    async def test_what_an_adapter_said_went_wrong_is_kept_and_kept_apart(self):
        """R-PRV-6 — it is where a brain says why it died, and it is never mistaken for
        what the brain reported."""
        turn = await self.carry(self.stand_in("failing"))
        self.assertIn("could not be reached", turn.errors)
        for line in turn.raw:
            self.assertNotIn(b"could not be reached", line if isinstance(line, bytes) else b"")

    async def test_a_brain_that_says_more_than_can_be_held_loses_the_oldest_and_says_where(self):
        """R-PROC-17, R-PRV-4 — what is held for a receiver is bounded, so a brain that
        outruns it loses records. Silently, that renders a wrong answer with nothing to
        say it is wrong; the end of what a brain said is the part worth keeping."""
        self.addCleanup(setattr, process, "HELD_BYTES", process.HELD_BYTES)
        process.HELD_BYTES = 8000
        held: list = []

        async def dawdles(record):
            await asyncio.sleep(0.05)
            held.append(record)

        program = process.Program(
            [str(self.stand_in("shouting"))], env=self.told(), cwd=self.where / "cwd",
            takes_input=True, errors_apart=True, silence=PATIENCE_SECONDS,
        )
        await program.start()
        reading = asyncio.ensure_future(program.wait(sink=dawdles))
        await program.send(b"go")
        await program.close_input()
        await reading
        self.assertTrue(any(isinstance(one, process.Gap) for one in held),
                        "records went missing with nothing said")
        last = provider.understood(held[-1]) if isinstance(held[-1], bytes) else None
        self.assertEqual("done", (last or {}).get("type"), "it lost the end rather than the start")


def _looks_like_json(line) -> bool:
    return isinstance(line, bytes) and line.strip()[:1] in (b"{", b"[")


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, PermissionError):
        return False
    return True


def _taken(argv: list, flag: str) -> tuple[Path | None, list]:
    """`--adapter <path>` or `--home <path>`, out before unittest sees the arguments.

    Its own parsing rather than argparse's, because unittest owns this command line and
    a parser that took it over would refuse every flag unittest offers.
    """
    if flag not in argv:
        return None, argv
    at = argv.index(flag)
    if at + 1 >= len(argv):
        print(f"{flag} needs a path after it", file=sys.stderr)
        raise SystemExit(2)
    return Path(argv[at + 1]).expanduser().resolve(), argv[:at] + argv[at + 2:]


if __name__ == "__main__":
    ADAPTER, rest = _taken(sys.argv[1:], "--adapter")
    HOME, rest = _taken(rest, "--home")
    if ADAPTER is not None:
        print(f"conformance: driving {ADAPTER}", file=sys.stderr)
        provider.program(str(ADAPTER))   # said here rather than in every case
    if HOME is not None:
        print(f"conformance: with the private home {HOME}", file=sys.stderr)
    unittest.main(argv=[sys.argv[0]] + rest, verbosity=2)
