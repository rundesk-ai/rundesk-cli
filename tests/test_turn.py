"""One whole turn — what it resolves, what it records, and what it costs.

The brains here are stand-in adapters this file writes: small programs, which is what
every adapter is. Nothing reaches the network and nothing needs an account.

Run: python3 tests/test_turn.py
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import json
import os
import shutil
import stat
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from rundesk import agent, provider, store, transcript, turn  # noqa: E402

PY = sys.executable

#: Answers, reports what it cost, and says where the conversation got to.
PLAIN = '''
import json, os, sys
if "--capabilities" in sys.argv:
    print(json.dumps({"tools": True, "resume": True, "model": True, "usage": True}))
    sys.exit(0)
prompt = sys.stdin.read().strip()
say = lambda **it: (sys.stdout.write(json.dumps(it) + "\\n"), sys.stdout.flush())
say(type="text", text="heard " + prompt)
say(type="usage", input=100, output=8, cached=40, model="stand-in-1")
say(type="done", ok=True, session=(os.environ.get("RUNDESK_RESUME") or "") + "s")
'''

#: Says nothing about what it cost, and cannot carry a conversation on.
QUIET = '''
import json, sys
if "--capabilities" in sys.argv:
    print("{}")
    sys.exit(0)
sys.stdin.read()
sys.stdout.write(json.dumps({"type": "text", "text": "answered"}) + "\\n")
sys.stdout.write(json.dumps({"type": "done", "ok": True, "session": "ignored"}) + "\\n")
sys.stdout.flush()
'''

#: Reports what it was told, so a case can assert what a turn resolved.
NOSY = '''
import json, os, sys
if "--capabilities" in sys.argv:
    print(json.dumps({"resume": True}))
    sys.exit(0)
prompt = sys.stdin.read()
told = {what: os.environ.get(what) for what in (
    "RUNDESK_CWD", "RUNDESK_PROVIDER_HOME", "RUNDESK_MODEL", "RUNDESK_RUN",
    "RUNDESK_RESUME", "RUNDESK_POSTURE", "RUNDESK_SETTINGS", "RUNDESK_PREFACE")}
say = lambda **it: (sys.stdout.write(json.dumps(it) + "\\n"), sys.stdout.flush())
say(type="text", text=json.dumps({"told": told, "prompt": prompt}))
say(type="done", ok=True, session="a-handle")
'''

#: Emits something nobody here knows, and says what went wrong on the right stream.
STRANGE = '''
import json, sys
if "--capabilities" in sys.argv:
    print("{}")
    sys.exit(0)
sys.stdin.read()
sys.stderr.write("a warning worth keeping\\n")
sys.stderr.flush()
sys.stdout.write(json.dumps({"type": "constellation", "shape": "orion"}) + "\\n")
sys.stdout.write(json.dumps({"type": "done", "ok": True}) + "\\n")
sys.stdout.flush()
'''

#: A turn that failed.
FAILING = '''
import json, sys
if "--capabilities" in sys.argv:
    print("{}")
    sys.exit(0)
sys.stdin.read()
sys.stdout.write(json.dumps({"type": "done", "ok": False}) + "\\n")
sys.stdout.flush()
'''

#: Can be sent to mid-turn: reads records for as long as its input stays open, and reports
#: each one back so a case can see it arrived while the turn was still going.
STEERABLE = '''
import json, sys
if "--capabilities" in sys.argv:
    print(json.dumps({"steer": True, "resume": True}))
    sys.exit(0)
say = lambda **it: (sys.stdout.write(json.dumps(it) + "\\n"), sys.stdout.flush())
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    said = json.loads(line)
    say(type="text", text="heard:" + said["text"])
say(type="done", ok=True, session="steered")
'''

#: Can be steered, and ends when its own work is done rather than when its input closes.
#: What every real brain is, and what no stand-in here was: the others all read stdin to
#: the end first, so a caller that never closes it — which is what a surface is — waited
#: for ever on a brain that had already finished.
FINISHES = '''
import json, sys, threading
if "--capabilities" in sys.argv:
    print(json.dumps({"steer": True, "resume": True}))
    sys.exit(0)
say = lambda **it: (sys.stdout.write(json.dumps(it) + "\\n"), sys.stdout.flush())
first = threading.Event()

def listen():
    for line in sys.stdin:
        if line.strip():
            first.set()

threading.Thread(target=listen, daemon=True).start()
first.wait(15)
say(type="text", text="all done")
say(type="done", ok=True, session="finished-on-its-own")
'''

#: Starts a turn and then keeps working, so a gateway standing down can cancel it midway.
#: It never reports `done`, which is exactly what a turn cut off looks like from here.
GOES_ON = '''
import json, sys, time
if "--capabilities" in sys.argv:
    print(json.dumps({"tools": True, "resume": True}))
    sys.exit(0)
sys.stdin.readline()
say = lambda **it: (sys.stdout.write(json.dumps(it) + "\\n"), sys.stdout.flush())
say(type="text", text="working on it")
time.sleep(30)
'''

BRAINS = {"plain": PLAIN, "quiet": QUIET, "nosy": NOSY, "strange": STRANGE,
          "failing": FAILING, "steerable": STEERABLE, "finishes": FINISHES, "goes_on": GOES_ON}


class WithAnAgentToRunTurnsFor(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.where = Path(tempfile.mkdtemp(prefix="rundesk-agents-"))
        self.addCleanup(shutil.rmtree, self.where, True)
        self.before = Path(tempfile.mkdtemp(prefix="rundesk-before-"))
        self.addCleanup(shutil.rmtree, self.before, True)
        # **The data root as well, and it is not optional.** Everything else here
        # falls back to it, so a fixture that isolates the four and forgets this
        # one still reaches the owner's real library — `add` grants what the
        # release ships, and would link a scratch agent at what they actually have.
        for said, at in (("RUNDESK_DATA_DIR", self.before / "data"),
                         ("RUNDESK_AGENTS_DIR", self.where),
                         ("RUNDESK_RUN_DIR", self.before / "run"),
                         ("RUNDESK_LOG_DIR", self.before / "logs"),
                         ("RUNDESK_SCHEDULES_DIR", self.before / "schedules"),
                         ("RUNDESK_JOBS_DIR", self.before / "jobs")):
            self.addCleanup(os.environ.pop, said, None)
            os.environ[said] = str(at)
            at.mkdir(parents=True, exist_ok=True)
        self.brains = Path(tempfile.mkdtemp(prefix="rundesk-brains-"))
        self.addCleanup(shutil.rmtree, self.brains, True)
        agent.add("ava", self.where)

    def brain(self, which: str) -> str:
        at = self.brains / which
        at.write_text("#!%s\n%s" % (PY, BRAINS[which]), encoding="utf-8")
        at.chmod(at.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        return str(at)

    async def ask(self, which: str = "plain", prompt: str = "what changed?", **extra):
        return await turn.carry("ava", prompt, self.brain(which), where=self.where, **extra)

    def kept(self, name: str = "ava"):
        """What this agent keeps, read the way anything reads it."""
        return agent.reading(name, self.where)

    def logs(self, name: str = "ava") -> Path:
        return agent.logs_home(name, self.where)

    def settled(self, run: str, name: str = "ava") -> dict:
        """What the run resolved and what became of it — the run's own row."""
        return self.kept(name).run(run)

    def account(self, run: str, name: str = "ava") -> list:
        """Every record of this run, in the order it happened.

        Each is what the seam made of a line the brain reported. What was *said* is not
        here: that is a message, in the conversation it was said in.
        """
        return [dict(one["event"] or {}, kind=one["kind"], seq=one["seq"])
                for one in self.kept(name).records(run)]

    def talk(self, run: str, name: str = "ava") -> list:
        """What was said in this run's conversation, in the order it was said."""
        kept = self.kept(name)
        return kept.messages(kept.run(run)["conversation_id"])

    def asked(self, run: str, name: str = "ava") -> dict:
        """The message that caused this run."""
        kept = self.kept(name)
        wanted = kept.run(run)["trigger_message_id"]
        return [one for one in self.talk(run, name) if one["id"] == wanted][0]

    def answer(self, run: str, name: str = "ava") -> str:
        """What the agent said in this run, joined the way it was written."""
        said = [one["text"] for one in self.talk(run, name) if one["run_id"] == run]
        return said[0] if said else ""

    def handle_for(self, which: str, conversation: str = turn.TERMINAL,
                   name: str = "ava") -> str | None:
        """What was kept for this brain — under the key the ledger really uses.

        Asked with the path an owner typed rather than the key derived from it, every
        `assertIsNone` here passes because the lookup misses, which proves nothing at all.
        """
        return agent.reading(name, self.where).session(
            store.conversation_id(turn.TERMINAL, conversation),
            provider.key(self.brain(which)))

    def only(self, run: str, kind: str, name: str = "ava") -> dict:
        found = [one for one in self.account(run, name) if one["type"] == kind]
        self.assertEqual(1, len(found), f"expected one '{kind}' record, got {len(found)}")
        return found[0]


class WhatATurnResolves(WithAnAgentToRunTurnsFor):
    async def test_what_a_run_resolved_is_written_when_it_is_admitted(self):
        """R-RUN-3 — a binding is not a thing anybody maintains: it is whatever this turn
        was asked for, settled once and recorded."""
        said = await self.ask("nosy", model="a-model", posture=provider.READ,
                              settings={"effort": "high"}, conversation="operations")
        admitted = self.settled(said.run)
        self.assertEqual("a-model", admitted["model"])
        self.assertEqual("read", admitted["posture"])
        self.assertEqual(store.conversation_id(turn.TERMINAL, "operations"),
                         admitted["conversation_id"])
        self.assertEqual("operations",
                         self.kept().conversation(turn.TERMINAL, "operations")["space"])
        self.assertEqual({"effort": "high"}, admitted["settings"])

    async def test_what_a_run_resolved_is_never_changed_after(self):
        """R-RUN-3 — a later turn resolving something else must not rewrite what an
        earlier one already did, which is what an account being append-only is for."""
        first = await self.ask("nosy", model="one")
        await self.ask("nosy", model="two")
        self.assertEqual("one", self.settled(first.run)["model"])

    async def test_what_a_brain_says_it_can_do_is_recorded_with_the_run(self):
        """R-PRV-15 — a turn that reported no tools and one whose brain has none read the
        same afterwards unless what it said it could do is part of the account."""
        said = await self.ask("quiet")
        self.assertEqual({what: False for what in provider.CAPABILITIES},
                         self.settled(said.run)["can"])

    async def test_an_adapter_that_cannot_run_says_why_before_a_turn_is_admitted(self):
        """R-PRV-12 — before, so nothing is written down about a turn that never was."""
        with self.assertRaises(provider.NotRunnable):
            await turn.carry("ava", "hello", str(self.brains / "no-such-brain"),
                             where=self.where)
        self.assertEqual([], [one['id'] for one in reversed(self.kept().runs())])


class WhatReachesABrain(WithAnAgentToRunTurnsFor):
    async def test_anything_rundesk_added_to_a_turn_appears_in_that_turns_account(self):
        """R-RUN-9, R-PRV-10 — injecting text a person never wrote and leaving it out of
        the audit makes the audit a lie, and it is invisible precisely because it is the
        audit."""
        said = await self.ask("plain", prompt="what changed today?")
        self.assertEqual("what changed today?", self.asked(said.run)["text"])

    async def test_what_was_sent_is_written_down_before_the_brain_is_started(self):
        """R-RUN-9 — an account written afterwards is one that can be written to match
        whatever happened."""
        said = await self.ask("plain")
        # The message the run names as its cause exists before the run does, so a turn
        # that died before it reached the brain still shows what somebody asked for.
        self.assertLess(self.asked(said.run)["id"],
                        [one["id"] for one in self.talk(said.run)
                         if one["author"] == "agent"][0])
        self.assertEqual(self.asked(said.run)["id"],
                         self.settled(said.run)["trigger_message_id"])

    async def test_a_turn_stands_where_its_own_agents_rules_stand(self):
        """R-PRV-3, R-PRV-14, R-AGT-15 — one agent reaching another's home is one agent
        reading another's work; and standing below its own is an agent that cannot read
        the rules written for it, because a brain loads them by standing beside them."""
        agent.add("bo", self.where)
        said = await self.ask("nosy")
        told = json.loads(self.answer(said.run))["told"]
        self.assertEqual(str(agent.home("ava", self.where)), told["RUNDESK_CWD"])
        self.assertTrue((Path(told["RUNDESK_CWD"]) / "AGENTS.md").is_file())
        self.assertNotIn("/bo/", told["RUNDESK_CWD"])
        self.assertNotIn("/bo/", told["RUNDESK_PROVIDER_HOME"])

    async def test_what_a_turn_was_told_to_stand_on_is_written_into_the_account(self):
        """R-PRV-23 — a turn given standing instructions read something the person never
        typed, and an account that does not say so cannot explain afterwards why it
        answered the way it did."""
        said = await self.ask("nosy", preface="You are in a room. Others read this.")
        # Written as something rundesk said into the conversation, because that is what
        # it is: an author of its own, told apart from the person and from the agent.
        self.assertEqual([("rundesk", "You are in a room. Others read this.")],
                         [(one["author"], one["text"]) for one in self.talk(said.run)
                          if one["author"] == "rundesk"])
        plain = await self.ask("nosy", conversation="somewhere-else")
        self.assertEqual([], [one for one in self.talk(plain.run)
                              if one["author"] == "rundesk"],
                         "a turn nobody prefaced claimed to have read something")

    async def test_a_brain_is_told_where_its_own_things_would_go_but_given_no_home(self):
        """R-AGT-8, R-PRV-3 — an adapter is *told* where a place of its own is, and rundesk
        does not make one.

        Made eagerly, a real brain does not merely keep a sign-in there: pointed at a
        directory it builds its whole state tree, tens of megabytes an agent, and starts
        out signed out so every agent needs its own login. A brain is reached as the
        machine has it installed; what an adapter wants to keep between turns it makes for
        itself."""
        said = await self.ask("nosy")
        told = json.loads(self.answer(said.run))["told"]
        home = Path(told["RUNDESK_PROVIDER_HOME"])
        self.assertFalse(home.exists(), "rundesk built a home no brain asked for")
        self.assertNotIn(str(agent.home("ava", self.where)), str(home),
                         "what a brain keeps stands outside what the agent loads")
        self.assertNotEqual(agent.provider_home("bo", "nosy", self.where), home,
                            "two agents would keep a brain's things in one place")


class WhatATurnRecords(WithAnAgentToRunTurnsFor):
    async def test_what_the_agent_said_is_written_in_one_place_and_not_two(self):
        """The rule the whole shape rests on: nothing is written twice where the two
        copies could come to disagree. What was *said* is a message — it is what a person
        reads back and what a search matches — and a record of it beside that would be a
        second answer to the same question, with nothing keeping them in step.

        The order has no hole in it either: only what happened claims a place, so a run
        whose brain said something does not skip a number where the saying went by."""
        said = await self.ask("plain")
        records = self.kept().records(said.run)
        self.assertEqual(["usage", "done"], [one["kind"] for one in records])
        self.assertEqual([1, 2], [one["seq"] for one in records],
                         "the order skips a place where something that is not a record went by")
        self.assertEqual([], [one for one in records
                              if "the parser" in (one["raw"] or "")
                              or "heard" in (one["raw"] or "")],
                         "what the agent said was kept as a record as well as a message")
        self.assertEqual(1, len([one for one in self.talk(said.run)
                                 if one["author"] == "agent"]))

    async def test_a_record_rundesk_did_not_understand_is_kept_and_shown_to_nobody(self):
        """R-PRV-5 — the turn finishes, its place in the order is kept, and what it
        actually said is there to be read afterwards."""
        watched: list = []
        said = await self.ask("strange", watching=watched.append)
        self.assertTrue(said.ok)
        self.assertNotIn("constellation",
                         [one.get("type") for one in self.account(said.run)])
        self.assertNotIn("constellation", [one["type"] for one in watched])
        # Kept as a record nobody here knows, with the brain's own words beside it — in a
        # row rather than only in a file, so a machine that swept what the brain printed
        # still has every line the adapter produced (R-RUN-6, R-STO-5).
        unknown = [one for one in self.kept().records(said.run) if one["kind"] == "unknown"]
        self.assertEqual(1, len(unknown), "a record nobody knows was dropped rather than kept")
        self.assertIn("constellation", unknown[0]["raw"])

    async def test_what_a_brain_said_went_wrong_is_kept_apart_from_what_it_reported(self):
        """R-PRV-6 — all of it, not a tail of it: an account is only worth having if it
        is the whole of what the brain gave us."""
        said = await self.ask("strange")
        self.assertEqual(b"a warning worth keeping\n",
                         transcript.read(self.logs(), said.run, transcript.ERRORS))

    async def test_a_turn_that_failed_is_recorded_as_one(self):
        """R-RUN-4 — a brain that says the turn did not work is believed, whatever its
        exit code said."""
        said = await self.ask("failing")
        self.assertFalse(said.ok)
        self.assertEqual("failed", self.settled(said.run)["outcome"])

    async def test_a_runs_account_is_found_by_the_runs_id(self):
        """R-RUN-2 — the id is what its account, its cost and its outcome are found by."""
        said = await self.ask("plain")
        self.assertIn(said.run, [one["id"] for one in self.kept().runs()])
        self.assertTrue(self.account(said.run))
        self.assertEqual(said.tokens["input"], self.settled(said.run)["tokens_in"])


class WhatAdmittedThisTurn(WithAnAgentToRunTurnsFor):
    """R-CH-15 — a turn admitted from somewhere says so in its own account.

    The two things a surface needs from the turn, and the reason they are the turn's to
    give rather than a channel's to keep: a channel that wrote either of them down itself
    would become the only place they existed, and it goes when its platform's history does.
    """

    async def test_a_turn_says_which_run_it_became_before_the_brain_is_started(self):
        """R-CH-15 — anything showing a turn as it happens has to name the run from its
        first mark. Waiting for the outcome to learn it leaves everything shown while
        somebody is actually waiting uncorrelated."""
        told: list = []
        said = await self.ask("plain", admitted=lambda run, can: told.append((run, can)))
        self.assertEqual([said.run], [run for run, _can in told],
                         "the run was named late, or twice")
        self.assertEqual({"tools", "resume", "model", "usage", "steer"}, set(told[0][1]),
                         "what the brain can do did not arrive with the run")

    async def test_the_run_is_named_before_anything_is_shown_of_it(self):
        """R-CH-15 — the order is the requirement: the id exists before the first record
        the watcher is handed, or the first mark cannot carry it."""
        order: list = []
        await self.ask("plain", admitted=lambda run, can: order.append("admitted"),
                       watching=lambda said: order.append(said["type"]))
        self.assertEqual("admitted", order[0], f"something was shown before the run had a name: {order}")

    async def test_where_a_turn_came_from_is_written_into_its_account(self):
        """R-CH-15 — so a run read back afterwards says which conversation asked for it,
        and the channel needs to have written nothing."""
        said = await self.ask("plain", on="ops", kind="somewhere", conversation="1180",
                              asked_by={"channel": "ops", "on": "1180", "user": "2207"})
        one = self.settled(said.run)
        self.assertEqual("channel", one["source"], "a turn from a surface read as a terminal's")
        self.assertEqual("2207", self.asked(said.run)["who"],
                         "the account does not say who asked")
        where_it_is = self.kept().conversation("ops", "1180")
        self.assertEqual(where_it_is["id"], one["conversation_id"])

    async def test_a_turn_nobody_admitted_from_anywhere_says_nothing_about_it(self):
        """R-CH-15 — `rundesk ask` is a turn from a terminal, and inventing an empty
        origin for it would make the account claim a surface that does not exist."""
        said = await self.ask("plain")
        self.assertEqual("terminal", self.settled(said.run)["source"])
        self.assertIsNone(self.asked(said.run)["who"],
                          "a turn from a terminal claimed somebody had asked for it")


class CarryingAConversationOn(WithAnAgentToRunTurnsFor):
    async def test_a_second_turn_resumes_the_conversations_session(self):
        """R-RUN-11 — the whole point of keeping a handle at all."""
        first = await self.ask("plain")
        self.assertEqual("s", first.handle)
        again = await self.ask("plain")
        self.assertEqual("ss", again.handle, "the second turn started a fresh session")
        self.assertTrue(self.settled(again.run)["resumed"])

    async def test_changing_the_brain_does_not_hand_over_the_other_ones_session(self):
        """R-RUN-12 — the failure this is all shaped to prevent: one brain resuming a
        conversation it was never part of."""
        await self.ask("plain")
        after = await self.ask("nosy")
        told = json.loads(self.answer(after.run))["told"]
        self.assertIsNone(told["RUNDESK_RESUME"], "one brain was given another's session")
        self.assertFalse(self.settled(after.run)["resumed"])

    async def test_two_conversations_of_one_brain_are_carried_on_separately(self):
        """R-RUN-12 — the conversation is the other half of the key."""
        await self.ask("plain", conversation="operations")
        elsewhere = await self.ask("nosy", conversation="planning")
        told = json.loads(self.answer(elsewhere.run))["told"]
        self.assertIsNone(told["RUNDESK_RESUME"])

    async def test_a_turn_asked_to_start_fresh_carries_nothing_on(self):
        """R-RUN-14 — an owner asking for a clean start is asking for one."""
        await self.ask("nosy")
        self.assertEqual("a-handle", self.handle_for("nosy"),
                         "the first turn kept nothing to start fresh from")
        after = await self.ask("nosy", fresh=True)
        told = json.loads(self.answer(after.run))["told"]
        self.assertIsNone(told["RUNDESK_RESUME"])

    async def test_losing_what_a_conversation_was_continuing_costs_the_next_turn_its_context(self):
        """R-RUN-14 — and nothing else. A handle is a convenience the next turn is better
        for having; a turn refused because it was missing would make an agent that cannot
        answer out of one that would merely answer without remembering."""
        await self.ask("nosy")
        self.assertEqual("a-handle", self.handle_for("nosy"))
        agent.records("ava", self.where).forget_session(
            store.conversation_id(turn.TERMINAL, turn.TERMINAL))

        after = await self.ask("nosy")
        told = json.loads(self.answer(after.run))["told"]
        self.assertIsNone(told["RUNDESK_RESUME"], "it carried on from a handle that had gone")
        self.assertTrue(after.ok, "a turn was refused over a handle nobody has to have")
        self.assertEqual("a-handle", self.handle_for("nosy"),
                         "the turn that started fresh kept nothing to carry on from")

    async def test_a_handle_is_kept_for_one_conversation_and_one_brain_together(self):
        """R-RUN-12 — never for either alone. Keyed on the conversation only, changing
        which brain answers hands one vendor's session to another; keyed on the brain only,
        every conversation it has had shares one."""
        await self.ask("plain", conversation="operations")
        await self.ask("nosy", conversation="operations")

        self.assertEqual("s", self.handle_for("plain", "operations"))
        self.assertEqual("a-handle", self.handle_for("nosy", "operations"))
        self.assertIsNone(self.handle_for("plain"), "one conversation answered for another")
        self.assertIsNone(self.handle_for("nosy"))

    async def test_a_brain_that_cannot_carry_a_conversation_on_is_not_asked_to(self):
        """R-PRV-15 — it said it cannot, so nothing is kept for it and nothing is handed
        back. A handle kept for a brain that will never use it is state nobody reads."""
        await self.ask("plain")          # one that can, so the lookup is proven to work
        said = await self.ask("quiet")
        self.assertIsNone(said.handle)
        self.assertIsNone(self.handle_for("quiet"))
        self.assertEqual("s", self.handle_for("plain"),
                         "the lookup is wrong, so finding nothing proved nothing")


class WhatATurnCost(WithAnAgentToRunTurnsFor):
    async def test_every_run_records_what_it_cost_in_tokens(self):
        """R-USE-1"""
        said = await self.ask("plain")
        self.assertEqual({"reported": True, "input": 100, "output": 8, "cached": 40,
                          "model": "stand-in-1"}, said.tokens)

    async def test_tokens_are_recorded_as_the_brain_reported_them(self):
        """R-USE-2 — the arithmetic that turns a conversation's running total into a
        turn's share belongs in the adapter, which is the only thing that knows its brain
        reports one. Adjusting it here would be guessing on every brain's behalf."""
        said = await self.ask("plain")
        reported = [one for one in self.account(said.run) if one["type"] == "usage"][0]
        for what in ("input", "output", "cached"):
            self.assertEqual(reported[what], said.tokens[what])

    async def test_tokens_written_into_a_cache_are_recorded_apart_from_ones_read_from_it(self):
        """R-USE-4 — folding them together reports a number that is technically real and
        practically a lie, because they are billed at different rates."""
        said = await self.ask("plain")
        self.assertEqual(40, said.tokens["cached"])
        self.assertEqual(100, said.tokens["input"], "cache reads were folded into input")

    async def test_a_run_whose_usage_never_arrived_says_so(self):
        """R-USE-6, R-USE-7 — zero and unknown are different answers, and a spend limit
        that read the first for the second would never fire."""
        said = await self.ask("quiet")
        self.assertEqual({"reported": False}, said.tokens)
        self.assertNotIn("input", said.tokens, "a cost that was never given was invented")

    async def test_a_brain_that_names_no_model_leaves_none_claimed(self):
        """R-PRV-9 — a model that was merely asked for is not a measurement."""
        said = await self.ask("quiet", model="asked-for-this-one")
        self.assertNotIn("model", said.tokens)

    async def test_what_an_agent_has_cost_is_read_without_a_brain_being_started(self):
        """R-USE-10 — a cost is a file, and reading it must not run anything."""
        said = await self.ask("plain")
        one = self.settled(said.run)
        self.assertEqual((100, 8, 40, True), (one["tokens_in"], one["tokens_out"],
                                              one["tokens_cached"], one["tokens_reported"]))

    async def test_what_an_agent_has_cost_outlives_the_gateway_that_recorded_it(self):
        """R-USE-9 — nothing was running to record it in the first place, and nothing has
        to be running to read it back."""
        said = await self.ask("plain")
        # Read from the records alone, with nothing of the turn that wrote them in reach.
        back = store.Store(store.path_for(agent.directory("ava", self.where)))
        back.made()
        self.assertEqual(100, back.run(said.run)["tokens_in"])
        self.assertEqual(1, back.usage()["reported"])


class BeingSentToMidTurn(WithAnAgentToRunTurnsFor):
    """R-PRV-19 — a word said to a brain that is already working, without stopping it."""

    async def words(self, *said):
        for one in said:
            await asyncio.sleep(0.05)   # after the turn is under way, not before it
            yield one

    async def test_a_brain_that_can_be_steered_hears_a_word_said_mid_turn(self):
        """R-PRV-19 — the whole point: more can be said to a turn that is already running,
        and the turn carries on rather than being taken away and started again."""
        said = await turn.carry("ava", "first", self.brain("steerable"), where=self.where,
                                steering=self.words("second", "third"))
        self.assertTrue(said.ok)
        self.assertEqual(["heard:first", "heard:second", "heard:third"],
                         [one["text"] for one in said.said if one["type"] == "text"])

    async def test_everything_said_mid_turn_is_in_that_turns_account(self):
        """R-RUN-9, R-PRV-10 — a word put into a turn that the account does not show makes
        the account a lie, and this is the one thing that adds words after it starts."""
        said = await turn.carry("ava", "first", self.brain("steerable"), where=self.where,
                                steering=self.words("second"))
        sent = [one["text"] for one in self.talk(said.run) if one["author"] == "user"]
        self.assertEqual(["first", "second"], sent,
                         "a word said mid-turn is not in the account of the turn it reached")

    async def test_a_brain_that_cannot_be_steered_is_not_left_waiting_for_more(self):
        """R-PRV-19 — holding input open for a brain that will never read again is a turn
        that never ends, so what it said it can do decides how it is run."""
        said = await turn.carry("ava", "hello", self.brain("plain"), where=self.where,
                                steering=self.words("never arrives"))
        self.assertTrue(said.ok, "a brain that reads to the end of its input never finished")
        sent = [one for one in self.talk(said.run) if one["author"] == "user"]
        self.assertEqual(["hello"], [one["text"] for one in sent])


class ATurnNobodyStopsTyping(WithAnAgentToRunTurnsFor):
    """R-PRV-19 — a turn whose input is never closed, which is what a surface does.

    Every other case here closes stdin, because that is what a terminal does when the
    person stops typing. A channel holds a conversation open for weeks and closes nothing,
    and the first brain driven that way answered, reported its work complete, and then sat
    waiting for a word that was never coming — so no `done` was written, no answer was
    ever handed over, and the turn never ended. The guide had always said a turn ends when
    the brain is finished, whatever the input is doing; nothing had ever checked.
    """

    async def never_closes(self):
        """Words, and then silence — held open, exactly as a conversation is."""
        yield "second"
        while True:
            await asyncio.sleep(0.05)

    async def test_a_turn_ends_when_the_brain_is_finished_not_when_its_input_closes(self):
        """R-PRV-19 — the case that would have caught it, and the one a surface is."""
        said = await asyncio.wait_for(
            turn.carry("ava", "first", self.brain("finishes"), where=self.where,
                       steering=self.never_closes()),
            timeout=20)
        self.assertTrue(said.ok, "a turn whose input stayed open never finished")
        self.assertEqual("done", said.said[-1]["type"])

    async def test_the_answer_is_there_to_hand_over_when_the_turn_ends(self):
        """R-CH-8 — prose is held until the turn ends, so a turn that never ends is an
        answer nobody ever sees. This is the same defect from the other side."""
        said = await asyncio.wait_for(
            turn.carry("ava", "first", self.brain("finishes"), where=self.where,
                       steering=self.never_closes()),
            timeout=20)
        self.assertEqual("all done", said.text)


class WhatAReviewFound(WithAnAgentToRunTurnsFor):
    """Three defects a review caught, each with the case that would have caught them."""

    async def test_a_brain_that_can_be_steered_is_given_records_even_with_nothing_to_add(self):
        """R-RUN-9, R-PRV-10 — how a brain is spoken to is decided by what *it* said it
        can do, and never by whether the caller happened to have a second thing to say.

        Decided in two places it was two rules: what the brain can do gated the account,
        and whether the caller passed anything gated the transport. They agree until the
        ordinary case — `rundesk ask` with no `--steer` — where the record was skipped in
        one and never written in the other, so a turn reached a brain with nothing in its
        account to show for it."""
        said = await self.ask("steerable", prompt="hello")
        self.assertTrue(said.ok)
        sent = [one for one in self.talk(said.run) if one["author"] == "user"]
        self.assertEqual(["hello"], [one["text"] for one in sent],
                         "a turn reached a brain and its account does not show it")

    async def test_a_word_that_could_not_be_said_is_not_reported_as_a_turn_that_was_fine(self):
        """R-RUN-9 — saying it runs as a task of its own, and a task whose exception
        nobody retrieves is one that failed invisibly. A word that never reached the brain
        left the turn reporting success it had not earned."""
        async def breaks_down():
            yield "this one arrives"
            raise RuntimeError("the terminal went away")

        said = await self.ask("steerable", steering=breaks_down())
        self.assertFalse(said.ok, "a turn that lost a word said it was fine")
        lost = [one for one in self.account(said.run) if one["kind"] == "lost"]
        self.assertTrue(lost, "what went wrong saying it reached nobody")
        self.assertIn("terminal went away", lost[0]["why"])

    async def test_two_things_named_at_once_do_not_erase_one_another(self):
        """R-AGT-4 — read, decide and write under one hold. Each read the same file, each
        merged only its own half, and the later write erased the other's with both
        reporting success."""
        agent.remember("ava", self.where, provider="one")
        agent.remember("ava", self.where, model="a-model")
        keeping = agent.chosen("ava", self.where)
        self.assertEqual(("one", "a-model"), (keeping["provider"], keeping["model"]),
                         "naming a model forgot the brain")


class AskingAnAgentFromATerminal(WithAnAgentToRunTurnsFor):
    """`rundesk ask` — the whole slice, from a typed command to an account on disk."""

    def ask(self, *argv):
        from rundesk import cli
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_asking_an_agent_carries_a_turn_and_prints_the_answer(self):
        """R-PRV-2, R-RUN-1 — one agent, one adapter, one turn, this terminal."""
        code, said, why = self.ask("add", "ava", "--provider", self.brain("plain"))
        self.assertEqual(0, code, why)
        code, said, why = self.ask("ask", "ava", "what changed?")
        self.assertEqual(0, code, why)
        self.assertEqual("heard what changed?", said.strip())

    def test_a_turn_can_be_given_standing_instructions_from_the_command(self):
        """R-PRV-23, R-SCH-3 — how a schedule gives a turn standing instructions. A
        schedule names a command and rundesk carries it without reading it, so a schedule
        holding its own instructions would have to be read on the way past — and the seam
        that keeps every kind of work the same would be the thing that broke. It belongs
        to the command the schedule names."""
        self.ask("add", "ava", "--provider", self.brain("nosy"))
        code, said, why = self.ask("ask", "ava", "what changed?",
                                   "--instructions", "You are running unattended overnight.")
        self.assertEqual(0, code, why)
        told = json.loads(said)["told"]
        # Added to rundesk's own rather than replacing them (R-AGT-17): ours says what the
        # agent is and how to find what it did, theirs says what to do about tonight.
        self.assertTrue(told["RUNDESK_PREFACE"].startswith(agent.standing("ava")))
        self.assertTrue(told["RUNDESK_PREFACE"].endswith(
            "You are running unattended overnight."))
        self.assertEqual("what changed?", json.loads(said)["prompt"].strip(),
                         "standing instructions were folded into what was asked")

    def test_a_turn_is_always_told_rundesks_own_words_whatever_else_it_was_told(self):
        """R-PRV-3, R-PRV-23 — unset rather than empty, so an adapter reading it can
        trust that there is something to act on."""
        self.ask("add", "ava", "--provider", self.brain("nosy"))
        _, said, _ = self.ask("ask", "ava", "what changed?")
        # Never unset now: rundesk itself always has something to say, so what an adapter
        # reads is ours alone rather than nothing (R-AGT-17). What is *absent* is anybody
        # else's — nothing of the owner's is invented to fill it.
        told = json.loads(said)["told"]["RUNDESK_PREFACE"]
        self.assertEqual(agent.standing("ava"), told)

    def test_the_answer_goes_where_it_can_be_piped_and_the_rest_does_not(self):
        """R-CMD-4 — what comes out of `rundesk ask … > answer.txt` has to be the answer
        and not a commentary around it."""
        self.ask("add", "ava", "--provider", self.brain("plain"))
        _, said, why = self.ask("ask", "ava", "what changed?")
        self.assertNotIn("in,", said, "what it cost was printed among the answer")
        self.assertIn("in,", why, "what it cost was not said at all")

    def test_a_turn_is_written_down_whether_or_not_anyone_is_watching(self):
        """R-RUN-4, R-RUN-10 — the terminal is a view of the turn and the account is the
        turn, and only one of the two is still there in the morning."""
        self.ask("add", "ava", "--provider", self.brain("plain"))
        _, _, why = self.ask("ask", "ava", "what changed?")
        run = [one['id'] for one in reversed(self.kept().runs())][0]
        self.assertIn(run, why, "it never said which run this was")
        self.assertEqual("what changed?", self.asked(run)["text"])

    def test_an_agent_that_reaches_for_no_brain_says_so_rather_than_guessing(self):
        """R-PRV-12 — there is no list of brains to fall back to, and picking one would
        be rundesk deciding whose model somebody pays for."""
        self.ask("add", "ava")
        code, _, why = self.ask("ask", "ava", "what changed?")
        self.assertEqual(1, code)
        self.assertIn("NO BRAIN", why)
        self.assertEqual([], [one['id'] for one in reversed(self.kept().runs())], "it wrote a run down anyway")

    def test_a_brain_named_for_one_turn_is_used_for_that_turn_only(self):
        """R-RUN-3 — what a turn resolved is the turn's, and an agent's default is a
        convenience rather than an identity."""
        self.ask("add", "ava", "--provider", self.brain("quiet"))
        self.ask("ask", "ava", "one", "--provider", self.brain("plain"))
        first, second = [one['id'] for one in reversed(self.kept().runs())][0], None
        self.assertIn("plain", self.settled(first)["provider"])
        self.ask("ask", "ava", "two")
        second = [one['id'] for one in reversed(self.kept().runs())][1]
        self.assertIn("quiet", self.settled(second)["provider"])

    def test_what_an_owner_set_reaches_the_brain_and_is_written_down(self):
        """R-PRV-16, R-RUN-9 — carried unread, and never carried without being recorded."""
        self.ask("add", "ava", "--provider", self.brain("nosy"))
        self.ask("ask", "ava", "hi", "--set", "effort=high", "--set", '{"flags":["-q"]}')
        run = [one['id'] for one in reversed(self.kept().runs())][0]
        self.assertEqual({"effort": "high", "flags": ["-q"]},
                         self.settled(run)["settings"])
        told = json.loads(self.answer(run))["told"]
        self.assertEqual({"effort": "high", "flags": ["-q"]},
                         json.loads(told["RUNDESK_SETTINGS"]))

    def test_a_setting_that_is_not_a_setting_is_refused_before_a_brain_is_started(self):
        """R-CMD-4 — refused in our words, and refused before anything runs."""
        self.ask("add", "ava", "--provider", self.brain("plain"))
        code, _, why = self.ask("ask", "ava", "hi", "--set", "nonsense")
        self.assertEqual(1, code)
        self.assertIn("nonsense", why)
        self.assertEqual([], [one['id'] for one in reversed(self.kept().runs())])

    def test_asking_the_same_agent_again_carries_the_conversation_on(self):
        """R-RUN-11 — what a person at a terminal means by asking again."""
        self.ask("add", "ava", "--provider", self.brain("plain"))
        self.ask("ask", "ava", "one")
        self.ask("ask", "ava", "two")
        second = [one['id'] for one in reversed(self.kept().runs())][1]
        self.assertTrue(self.settled(second)["resumed"])

    def test_asking_for_a_fresh_start_carries_nothing_on(self):
        """R-RUN-14"""
        self.ask("add", "ava", "--provider", self.brain("plain"))
        self.ask("ask", "ava", "one")
        self.ask("ask", "ava", "two", "--fresh")
        second = [one['id'] for one in reversed(self.kept().runs())][1]
        self.assertFalse(self.settled(second)["resumed"])

    def test_a_turn_asked_to_only_look_says_so_to_the_brain(self):
        """R-PRV-18 — a posture in rundesk's words, carried to the brain to act on."""
        self.ask("add", "ava", "--provider", self.brain("nosy"))
        self.ask("ask", "ava", "hi", "--read-only")
        run = [one['id'] for one in reversed(self.kept().runs())][0]
        self.assertEqual("read", self.settled(run)["posture"])

    def test_asking_an_agent_that_was_never_made_says_so(self):
        """R-AGT-13 — and says what to type next, rather than what went wrong inside."""
        code, _, why = self.ask("ask", "nobody", "hi")
        self.assertEqual(1, code)
        self.assertIn("NO SUCH AGENT", why)
        self.assertIn("rundesk add nobody", why)

    def test_a_turn_whose_cost_was_never_reported_says_that_rather_than_nothing(self):
        """R-USE-7 — zero and unknown are different answers."""
        self.ask("add", "ava", "--provider", self.brain("quiet"))
        _, _, why = self.ask("ask", "ava", "hi")
        self.assertIn("never reported", why)


class ATurnTheGatewayStoodDownOn(WithAnAgentToRunTurnsFor):
    """R-RUN-13 — a run that was begun is settled, whatever happens to the turn."""

    async def test_a_cancelled_turn_does_not_stay_running_for_ever(self):
        """Reported: stopping or restarting a gateway mid-turn cut the brain off and left
        the run marked `running` in the owner's own records permanently. `rundesk runs`
        went on showing a turn in flight that nothing was doing, no restart cleared it —
        nothing afterwards knew it had ever been begun — and a later turn succeeded beside
        it, which reads as two gateways rather than one bad record.

        A cancellation is the ordinary way a gateway stands down, and it unwinds *past* the
        settling at the end of the happy path rather than through it, so no `except` in the
        body could have caught this."""
        going = asyncio.ensure_future(self.ask("goes_on"))
        # Long enough for the brain to be started and the run admitted, short enough that
        # the turn is certainly still in flight — the brain sleeps for thirty seconds.
        await asyncio.sleep(1.5)
        going.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await going

        runs = list(self.kept().runs())
        self.assertEqual(1, len(runs), "the turn never got as far as being admitted")
        self.assertIsNotNone(runs[0]["ended_at"], "the run is still marked as running")
        self.assertEqual("stopped", runs[0]["outcome"])
        self.assertIn("gateway stopped", (runs[0]["why"] or ""))

    async def test_a_gateway_cancelled_channel_turn_is_left_for_one_successor(self):
        """R-GW-22 — gateway loss is marked apart from a person's explicit stop."""
        going = asyncio.ensure_future(self.ask(
            "goes_on", conversation="one", on="ops", kind="somewhere",
            asked_by={"channel": "ops", "on": "one", "user": "2207"},
            resume_on_interrupt=lambda: True,
        ))
        await asyncio.sleep(1.5)
        going.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await going

        recoverable = self.kept().recoverable("ops")
        self.assertEqual(1, len(recoverable))
        self.assertEqual("one", recoverable[0]["conversation"])

    async def test_recovery_without_a_saved_session_refuses_before_replaying_the_prompt(self):
        """R-GW-22 — a missing handle produces a terminal failure, never repeated effects."""
        with self.assertRaises(turn.CannotResume):
            await self.ask(
                "plain", prompt="continue safely", conversation="one", on="ops",
                kind="somewhere", resume_required=True, prompt_author="rundesk",
            )
        self.assertEqual([], self.kept().runs(), "an unsafe replay was admitted as a run")

    async def test_a_recovery_interrupted_again_is_not_retried_forever(self):
        """R-GW-24 — one continuation attempt is the bound, not a restart loop."""
        kept = agent.records("ava", self.where)
        conversation = store.conversation_id("ops", "one")
        kept.opened(conversation, "ops", "somewhere", "one", store.stamped())
        kept.remember_session(
            conversation, provider.key(self.brain("goes_on")), "saved-session",
        )
        going = asyncio.ensure_future(self.ask(
            "goes_on", prompt="continue safely", conversation="one", on="ops",
            kind="somewhere", resume_required=True, prompt_author="rundesk",
            resume_on_interrupt=lambda: False,
        ))
        await asyncio.sleep(1.5)
        going.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await going
        self.assertEqual([], self.kept().recoverable("ops"))

    async def test_a_recovery_run_names_the_execution_it_continues(self):
        """R-RUN-17 — both executions remain readable as one recovery chain."""
        kept = agent.records("ava", self.where)
        conversation = store.conversation_id("ops", "one")
        kept.opened(conversation, "ops", "somewhere", "one", store.stamped())
        kept.remember_session(
            conversation, provider.key(self.brain("plain")), "saved-session",
        )
        outcome = await self.ask(
            "plain", prompt="continue safely", conversation="one", on="ops",
            kind="somewhere", resume_required=True, prompt_author="rundesk",
            recovery_of="1-old",
        )
        linked = [one for one in self.account(outcome.run)
                  if one.get("type") == "recovery"]
        self.assertEqual(["1-old"], [one["run"] for one in linked])

    async def test_a_turn_that_ended_normally_keeps_the_outcome_it_earned(self):
        """The other half, and the one that makes the guard safe: settling on the way out
        must never write over the real outcome a finished turn already recorded."""
        said = await self.ask("plain")
        runs = list(self.kept().runs())
        self.assertEqual("finished", runs[0]["outcome"])
        self.assertEqual("finished", said.became)


if __name__ == "__main__":
    unittest.main(verbosity=2)
