"""One whole turn — what it resolves, what it records, and what it costs.

The brains here are stand-in adapters this file writes: small programs, which is what
every adapter is. Nothing reaches the network and nothing needs an account.

Run: python3 tests/test_turn.py
"""

from __future__ import annotations

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

from rundesk_cli import agent, provider, session, transcript, turn  # noqa: E402

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
    "RUNDESK_RESUME", "RUNDESK_POSTURE", "RUNDESK_SETTINGS")}
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

BRAINS = {"plain": PLAIN, "quiet": QUIET, "nosy": NOSY, "strange": STRANGE,
          "failing": FAILING}


class WithAnAgentToRunTurnsFor(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.where = Path(tempfile.mkdtemp(prefix="rundesk-agents-"))
        self.addCleanup(shutil.rmtree, self.where, True)
        self.before = Path(tempfile.mkdtemp(prefix="rundesk-before-"))
        self.addCleanup(shutil.rmtree, self.before, True)
        for said, at in (("RUNDESK_AGENTS_DIR", self.where),
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

    def runs(self, name: str = "ava") -> Path:
        return agent.runs_home(name, self.where)

    def account(self, run: str, name: str = "ava") -> list:
        return [one["event"] for one in transcript.read(self.runs(name), run)
                if "event" in one]

    def handle_for(self, which: str, conversation: str = turn.TERMINAL,
                   name: str = "ava") -> str | None:
        """What was kept for this brain — under the key the ledger really uses.

        Asked with the path an owner typed rather than the key derived from it, every
        `assertIsNone` here passes because the lookup misses, which proves nothing at all.
        """
        return session.of(agent.directory(name, self.where),
                          provider.key(self.brain(which)), conversation)

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
        admitted = self.only(said.run, turn.ADMITTED)
        self.assertEqual("a-model", admitted["model"])
        self.assertEqual("read", admitted["posture"])
        self.assertEqual("operations", admitted["conversation"])
        self.assertEqual({"effort": "high"}, admitted["settings"])

    async def test_what_a_run_resolved_is_never_changed_after(self):
        """R-RUN-3 — a later turn resolving something else must not rewrite what an
        earlier one already did, which is what an account being append-only is for."""
        first = await self.ask("nosy", model="one")
        await self.ask("nosy", model="two")
        self.assertEqual("one", self.only(first.run, turn.ADMITTED)["model"])

    async def test_what_a_brain_says_it_can_do_is_recorded_with_the_run(self):
        """R-PRV-15 — a turn that reported no tools and one whose brain has none read the
        same afterwards unless what it said it could do is part of the account."""
        said = await self.ask("quiet")
        self.assertEqual({what: False for what in provider.CAPABILITIES},
                         self.only(said.run, turn.ADMITTED)["can"])

    async def test_an_adapter_that_cannot_run_says_why_before_a_turn_is_admitted(self):
        """R-PRV-12 — before, so nothing is written down about a turn that never was."""
        with self.assertRaises(provider.NotRunnable):
            await turn.carry("ava", "hello", str(self.brains / "no-such-brain"),
                             where=self.where)
        self.assertEqual([], transcript.known(self.runs()))


class WhatReachesABrain(WithAnAgentToRunTurnsFor):
    async def test_anything_rundesk_added_to_a_turn_appears_in_that_turns_account(self):
        """R-RUN-9, R-PRV-10 — injecting text a person never wrote and leaving it out of
        the audit makes the audit a lie, and it is invisible precisely because it is the
        audit."""
        said = await self.ask("plain", prompt="what changed today?")
        self.assertEqual("what changed today?", self.only(said.run, turn.SENT)["text"])

    async def test_what_was_sent_is_written_down_before_the_brain_is_started(self):
        """R-RUN-9 — an account written afterwards is one that can be written to match
        whatever happened."""
        said = await self.ask("plain")
        order = [one["type"] for one in self.account(said.run)]
        self.assertLess(order.index(turn.SENT), order.index("text"))
        self.assertLess(order.index(turn.ADMITTED), order.index(turn.SENT))

    async def test_a_turn_works_in_its_own_agents_workspace(self):
        """R-PRV-3, R-PRV-14 — one agent reaching another's workspace is one agent
        reading another's work."""
        agent.add("bo", self.where)
        said = await self.ask("nosy")
        told = json.loads(self.only(said.run, "text")["text"])["told"]
        self.assertEqual(str(agent.workspace("ava", self.where)), told["RUNDESK_CWD"])
        self.assertNotIn("/bo/", told["RUNDESK_CWD"])
        self.assertNotIn("/bo/", told["RUNDESK_PROVIDER_HOME"])

    async def test_a_brain_is_given_a_private_home_of_its_own_under_this_agent(self):
        """R-AGT-8 — a brain's configuration and sign-in are about an agent and a brain
        together, and stand outside what the agent loads."""
        said = await self.ask("nosy")
        told = json.loads(self.only(said.run, "text")["text"])["told"]
        home = Path(told["RUNDESK_PROVIDER_HOME"])
        self.assertTrue(home.is_dir(), "the brain was pointed at a home nobody made")
        self.assertNotIn(str(agent.home("ava", self.where)), str(home))


class WhatATurnRecords(WithAnAgentToRunTurnsFor):
    async def test_a_record_rundesk_did_not_understand_is_kept_and_shown_to_nobody(self):
        """R-PRV-5 — the turn finishes, its place in the order is kept, and what it
        actually said is there to be read afterwards."""
        watched: list = []
        said = await self.ask("strange", watching=watched.append)
        self.assertTrue(said.ok)
        self.assertNotIn("constellation", [one["type"] for one in self.account(said.run)])
        self.assertNotIn("constellation", [one["type"] for one in watched])
        self.assertIn(b"constellation", transcript.raw(self.runs(), said.run))

    async def test_what_a_brain_said_went_wrong_is_kept_apart_from_what_it_reported(self):
        """R-PRV-6 — all of it, not a tail of it: an account is only worth having if it
        is the whole of what the brain gave us."""
        said = await self.ask("strange")
        self.assertEqual(b"a warning worth keeping\n",
                         transcript.raw(self.runs(), said.run, transcript.ERRORS))

    async def test_a_turn_that_failed_is_recorded_as_one(self):
        """R-RUN-4 — a brain that says the turn did not work is believed, whatever its
        exit code said."""
        said = await self.ask("failing")
        self.assertFalse(said.ok)
        self.assertFalse(self.only(said.run, turn.OUTCOME)["ok"])

    async def test_a_runs_account_is_found_by_the_runs_id(self):
        """R-RUN-2 — the id is what its account, its cost and its outcome are found by."""
        said = await self.ask("plain")
        self.assertIn(said.run, transcript.known(self.runs()))
        self.assertTrue(self.account(said.run))
        self.assertEqual(said.tokens, self.only(said.run, turn.OUTCOME)["tokens"])


class CarryingAConversationOn(WithAnAgentToRunTurnsFor):
    async def test_a_second_turn_resumes_the_conversations_session(self):
        """R-RUN-11 — the whole point of keeping a handle at all."""
        first = await self.ask("plain")
        self.assertEqual("s", first.handle)
        again = await self.ask("plain")
        self.assertEqual("ss", again.handle, "the second turn started a fresh session")
        self.assertTrue(self.only(again.run, turn.ADMITTED)["resumed"])

    async def test_changing_the_brain_does_not_hand_over_the_other_ones_session(self):
        """R-RUN-12 — the failure this is all shaped to prevent: one brain resuming a
        conversation it was never part of."""
        await self.ask("plain")
        after = await self.ask("nosy")
        told = json.loads(self.only(after.run, "text")["text"])["told"]
        self.assertIsNone(told["RUNDESK_RESUME"], "one brain was given another's session")
        self.assertFalse(self.only(after.run, turn.ADMITTED)["resumed"])

    async def test_two_conversations_of_one_brain_are_carried_on_separately(self):
        """R-RUN-12 — the conversation is the other half of the key."""
        await self.ask("plain", conversation="operations")
        elsewhere = await self.ask("nosy", conversation="planning")
        told = json.loads(self.only(elsewhere.run, "text")["text"])["told"]
        self.assertIsNone(told["RUNDESK_RESUME"])

    async def test_a_turn_asked_to_start_fresh_carries_nothing_on(self):
        """R-RUN-14 — an owner asking for a clean start is asking for one."""
        await self.ask("nosy")
        self.assertEqual("a-handle", self.handle_for("nosy"),
                         "the first turn kept nothing to start fresh from")
        after = await self.ask("nosy", fresh=True)
        told = json.loads(self.only(after.run, "text")["text"])["told"]
        self.assertIsNone(told["RUNDESK_RESUME"])

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
        self.assertEqual({"reported": True, "input": 100, "output": 8, "cached": 40,
                          "model": "stand-in-1"},
                         self.only(said.run, turn.OUTCOME)["tokens"])

    async def test_what_an_agent_has_cost_outlives_the_gateway_that_recorded_it(self):
        """R-USE-9 — nothing was running to record it in the first place, and nothing has
        to be running to read it back."""
        said = await self.ask("plain")
        found = [one for one in transcript.events(self.runs(), said.run)
                 if one["type"] == turn.OUTCOME]
        self.assertEqual(1, len(found))


class AskingAnAgentFromATerminal(WithAnAgentToRunTurnsFor):
    """`rundesk ask` — the whole slice, from a typed command to an account on disk."""

    def ask(self, *argv):
        from rundesk_cli import cli
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
        run = transcript.known(self.runs())[0]
        self.assertIn(run, why, "it never said which run this was")
        self.assertEqual("what changed?", self.only(run, turn.SENT)["text"])

    def test_an_agent_that_reaches_for_no_brain_says_so_rather_than_guessing(self):
        """R-PRV-12 — there is no list of brains to fall back to, and picking one would
        be rundesk deciding whose model somebody pays for."""
        self.ask("add", "ava")
        code, _, why = self.ask("ask", "ava", "what changed?")
        self.assertEqual(1, code)
        self.assertIn("NO BRAIN", why)
        self.assertEqual([], transcript.known(self.runs()), "it wrote a run down anyway")

    def test_a_brain_named_for_one_turn_is_used_for_that_turn_only(self):
        """R-RUN-3 — what a turn resolved is the turn's, and an agent's default is a
        convenience rather than an identity."""
        self.ask("add", "ava", "--provider", self.brain("quiet"))
        self.ask("ask", "ava", "one", "--provider", self.brain("plain"))
        first, second = transcript.known(self.runs())[0], None
        self.assertIn("plain", self.only(first, turn.ADMITTED)["provider"])
        self.ask("ask", "ava", "two")
        second = transcript.known(self.runs())[1]
        self.assertIn("quiet", self.only(second, turn.ADMITTED)["provider"])

    def test_what_an_owner_set_reaches_the_brain_and_is_written_down(self):
        """R-PRV-16, R-RUN-9 — carried unread, and never carried without being recorded."""
        self.ask("add", "ava", "--provider", self.brain("nosy"))
        self.ask("ask", "ava", "hi", "--set", "effort=high", "--set", '{"flags":["-q"]}')
        run = transcript.known(self.runs())[0]
        self.assertEqual({"effort": "high", "flags": ["-q"]},
                         self.only(run, turn.ADMITTED)["settings"])
        told = json.loads(self.only(run, "text")["text"])["told"]
        self.assertEqual({"effort": "high", "flags": ["-q"]},
                         json.loads(told["RUNDESK_SETTINGS"]))

    def test_a_setting_that_is_not_a_setting_is_refused_before_a_brain_is_started(self):
        """R-CMD-4 — refused in our words, and refused before anything runs."""
        self.ask("add", "ava", "--provider", self.brain("plain"))
        code, _, why = self.ask("ask", "ava", "hi", "--set", "nonsense")
        self.assertEqual(1, code)
        self.assertIn("nonsense", why)
        self.assertEqual([], transcript.known(self.runs()))

    def test_asking_the_same_agent_again_carries_the_conversation_on(self):
        """R-RUN-11 — what a person at a terminal means by asking again."""
        self.ask("add", "ava", "--provider", self.brain("plain"))
        self.ask("ask", "ava", "one")
        self.ask("ask", "ava", "two")
        second = transcript.known(self.runs())[1]
        self.assertTrue(self.only(second, turn.ADMITTED)["resumed"])

    def test_asking_for_a_fresh_start_carries_nothing_on(self):
        """R-RUN-14"""
        self.ask("add", "ava", "--provider", self.brain("plain"))
        self.ask("ask", "ava", "one")
        self.ask("ask", "ava", "two", "--fresh")
        second = transcript.known(self.runs())[1]
        self.assertFalse(self.only(second, turn.ADMITTED)["resumed"])

    def test_a_turn_asked_to_only_look_says_so_to_the_brain(self):
        """R-PRV-18 — a posture in rundesk's words, carried to the brain to act on."""
        self.ask("add", "ava", "--provider", self.brain("nosy"))
        self.ask("ask", "ava", "hi", "--read-only")
        run = transcript.known(self.runs())[0]
        self.assertEqual("read", self.only(run, turn.ADMITTED)["posture"])

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
