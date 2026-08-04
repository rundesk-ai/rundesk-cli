#!/usr/bin/env python3
"""One agent's ask of another: what it is admitted with, and what it owes after.

Answers for `agent-delegation` (R-DEL-n). Nothing here starts a provider or reaches the
network: the turn is an argument, so what an answering agent is *told* and *given* is
asserted with no brain anywhere near it, and the durable record is driven against a scratch
data root with no gateway near it either.

Run: python3 tests/test_delegation.py
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from rundesk import agent, config, delegation  # noqa: E402
from rundesk import handoff as handoffs  # noqa: E402
from rundesk import instructions  # noqa: E402
from rundesk import provider, role, store, turn  # noqa: E402

TASK = "Look at the quote flow and say what is slow about it.\nRead only; change nothing.\n"
AT = "2026-08-01T09:00:00Z"


def at(said: str):
    """That moment, as the clock every decision here is handed."""
    return lambda: store.moment(said).timestamp()


class Carried:
    """The turn, as a stand-in — it records what it was handed and answers well.

    **Exactly the surface `turn.carry` has at the seams this module uses**, and no more: it
    calls `admitted` with what the brain can do the way a real turn does, and reads whatever
    is on the steering generator when a case asks it to. A stand-in more generous than the
    real thing hides whole features, and one less generous never exercises them.
    """

    def __init__(self, ok: bool = True, said: str = "It is the second query. Here is why.",
                 narrating: str = "", steer: bool = True, listening: int = 0,
                 while_working=None):
        self.given: dict = {}
        self.heard: list = []
        self._ok = ok
        self._said = said
        self._narrating = narrating
        self._steer = steer
        self._listening = listening
        #: Called once the turn is admitted and still running — which is the only moment
        #: the record is `working` and knows what this brain can do.
        self._while_working = while_working

    async def __call__(self, name, prompt, named, **given):
        self.given = {"name": name, "prompt": prompt, "provider": named, **given}
        if given.get("admitted") is not None:
            given["admitted"]("7-abcd", {"steer": self._steer, "resume": True})
        if self._while_working is not None:
            self._while_working()
        guiding = given.get("steering")
        if guiding is not None and self._listening:
            async for word in guiding:
                self.heard.append(word.text)
                if len(self.heard) >= self._listening:
                    break
        # Working narration, then a tool call, then the report — the shape a real turn
        # has, so what is handed on can be told from what was merely said on the way.
        spoke: list = []
        if self._narrating:
            spoke += [{"type": "text", "text": self._narrating, "whole": True},
                      {"type": "tool", "name": "Read"}]
        if self._said:
            spoke.append({"type": "text", "text": self._said, "whole": True})
        return turn.Outcome(
            run="7-abcd", ok=self._ok,
            reason="finished" if self._ok else "failed",
            said=spoke,
            tokens={"reported": True, "input": 10, "output": 5},
            handle="session-1",
            why=None if self._ok else "the brain said it could not",
        )


class WithTwoAgentsOnOneInstall(unittest.TestCase):
    """One agent with a turn to hand work from, and one with a brain to answer it."""

    def setUp(self):
        self.where = Path(tempfile.mkdtemp(prefix="rundesk-agents-"))
        self.addCleanup(shutil.rmtree, self.where, True)
        self.before = Path(tempfile.mkdtemp(prefix="rundesk-before-"))
        self.addCleanup(shutil.rmtree, self.before, True)
        for said, to in (("RUNDESK_DATA_DIR", self.before / "data"),
                         ("RUNDESK_AGENTS_DIR", self.where),
                         ("RUNDESK_RUN_DIR", self.before / "run"),
                         ("RUNDESK_LOG_DIR", self.before / "logs"),
                         ("RUNDESK_JOBS_DIR", self.before / "jobs")):
            self.addCleanup(os.environ.pop, said, None)
            os.environ[said] = str(to)
            to.mkdir(parents=True, exist_ok=True)
        config.ensure(self.before / "data")
        agent.add("elena", self.where)
        agent.remember("elena", self.where, provider="codex")
        agent.add("cole", self.where)
        agent.remember("cole", self.where, provider="claude", model="a-model")
        self.kept = agent.records("elena", self.where)
        # A surface the asking agent is actually reachable on. The answer arrives long
        # after this turn has ended, and is delivered by waking the agent where the request
        # arrived — so admission refuses a turn that happened nowhere anybody can answer
        # into (R-DEL-4).
        self.kept.remember_channel("discord", "discord", ["2207"], AT)
        self.parent = self.a_turn()

    def a_turn(self, source: str = "channel", posture: str = "work", **given) -> str:
        """One ordinary turn of the asking agent's, in a conversation somebody is in."""
        where_it_is = store.conversation_id("discord", "general")
        self.kept.opened(where_it_is, "discord", "discord", "general", AT)
        return self.kept.began(source, "codex", posture, AT,
                               conversation_id=where_it_is, **given)

    def ask(self, **given):
        said = {"name": "elena", "to": "cole", "brief": TASK,
                "parent_run": self.parent, "where": self.where}
        said.update(given)
        return delegation.ask(**said)

    def carried(self, ask_id: str, **given):
        carry = Carried(**given)
        outcome = asyncio.run(
            delegation.carry("cole", ask_id, where=self.where, carrying=carry))
        return carry, outcome


class TheRecordOfOneAsk(WithTwoAgentsOnOneInstall):
    """R-DEL-1 — one bounded task, written down whole before anything can act on it."""

    def test_an_ask_is_written_whole_and_read_back(self):
        record = self.ask(label="the quote flow")
        self.assertTrue(record["id"].startswith("del-1-"))
        self.assertTrue(delegation.path(record["id"]).is_file())
        back = delegation.read(record["id"])
        self.assertEqual(record, back)
        self.assertEqual("elena", back["from"])
        self.assertEqual("cole", back["to"])
        self.assertEqual(["elena"], back["chain"])
        self.assertEqual(TASK, back["brief"])
        self.assertEqual(delegation.ASKED, back["state"])
        self.assertEqual(self.parent, back["parent_run"])
        self.assertEqual([back], delegation.waiting("cole"))
        self.assertEqual([], delegation.owed("elena"))

    def test_a_record_that_cannot_be_parsed_is_unreadable_and_never_empty(self):
        """**What cannot be read is not empty.** Answering "there is no such ask" for a
        record that is there and broken is how an answer somebody is owed disappears."""
        record = self.ask()
        delegation.path(record["id"]).write_text("{ not json", encoding="utf-8")
        with self.assertRaises(delegation.Unreadable):
            delegation.read(record["id"])
        with self.assertRaises(delegation.Unreadable):
            delegation.every()
        self.assertIsNone(delegation.read("del-9-zzzz"), "a missing one raised instead")

    def test_two_writers_cannot_lose_a_state_change(self):
        """The lock is the whole of the safety: two gateways each reading the same record
        and each writing theirs back is one attempt silently uncounted, and a ceiling that
        never fires is an answer nobody is ever told about.

        Made to happen rather than waited for. The first writer is stopped inside its own
        hold, after the read and before the write; the second must not be able to get in
        while it stands there, and that is what the bounded wait below asserts.
        """
        record = self.ask()
        first_in, second_in, release = (threading.Event(), threading.Event(),
                                        threading.Event())
        real = store.stamped

        def stamped(now=None):
            if not first_in.is_set():
                first_in.set()
                release.wait(10.0)
            else:
                second_in.set()
            return real(now)

        self.addCleanup(setattr, store, "stamped", real)
        store.stamped = stamped
        counted = []

        def claim():
            counted.append(delegation.claim_review(record["id"]))

        one = threading.Thread(target=claim)
        one.start()
        self.assertTrue(first_in.wait(10.0), "the first writer never reached its hold")
        other = threading.Thread(target=claim)
        other.start()
        self.assertFalse(second_in.wait(0.5),
                         "the second writer changed the record while the first held it")
        release.set()
        one.join(10.0)
        other.join(10.0)
        self.assertEqual([1, 2], sorted(counted), "one attempt was lost")
        self.assertEqual(2, delegation.read(record["id"])["review_attempts"])

    def test_a_claim_moves_one_ask_and_leaves_the_rest(self):
        mine = self.ask()
        other = self.ask()
        held = delegation.claim_work(mine["id"])
        self.assertEqual(delegation.WORKING, held["state"])
        self.assertEqual(delegation.WORKING, delegation.read(mine["id"])["state"])
        self.assertEqual(delegation.ASKED, delegation.read(other["id"])["state"])
        # Still waiting, because a gateway that stood down mid-ask leaves one `working`
        # on purpose and the next gateway is what carries it on.
        self.assertEqual({mine["id"], other["id"]},
                         {one["id"] for one in delegation.waiting("cole")})

    def test_an_ask_nothing_answered_inside_the_window_is_left_alone(self):
        record = self.ask(now=at("2026-08-01T09:00:00Z"))
        swept = delegation.sweep(now=at("2026-08-01T14:00:00Z"))
        self.assertEqual({"settled": [], "removed": []}, swept)
        self.assertEqual(delegation.ASKED, delegation.read(record["id"])["state"])

    def test_an_ask_past_the_window_is_settled_undeliverable(self):
        """R-DEL-13 — an ask nobody can hear from is not one that is going to be answered,
        and the agent that handed the work over has to be told rather than left waiting."""
        record = self.ask(now=at("2026-08-01T09:00:00Z"))
        swept = delegation.sweep(now=at("2026-08-01T16:00:00Z"))
        self.assertEqual([record["id"]], swept["settled"])
        back = delegation.read(record["id"])
        self.assertEqual(delegation.UNDELIVERABLE, back["state"])
        self.assertIn("stopped producing any activity", back["why"])
        self.assertIn("cole", back["why"])
        self.assertEqual([back], delegation.owed("elena"))

    def test_a_settled_ask_past_retention_is_taken_away(self):
        record = self.ask(now=at("2026-08-01T09:00:00Z"))
        delegation.answered(record["id"], "here it is", now=at("2026-08-01T10:00:00Z"))
        swept = delegation.sweep(now=at("2026-08-10T10:00:00Z"))
        self.assertEqual([], swept["removed"], "it was taken away inside its window")
        swept = delegation.sweep(now=at("2026-08-20T10:00:00Z"))
        self.assertEqual([record["id"]], swept["removed"])
        self.assertIsNone(delegation.read(record["id"]))
        self.assertEqual([], delegation.every())

    def test_a_collected_ask_stops_being_owed(self):
        """R-DEL-11 — exactly one review, delivered once. An answer still owed after the
        asking agent has reviewed it is an agent woken about the same work for ever."""
        record = self.ask()
        delegation.answered(record["id"], "here it is")
        self.assertEqual([record["id"]],
                         [one["id"] for one in delegation.owed("elena")])
        self.assertTrue(delegation.collected(record["id"]))
        self.assertEqual([], delegation.owed("elena"))
        self.assertFalse(delegation.collected(record["id"]), "it was collected twice")
        self.assertTrue(delegation.read(record["id"])["collected_at"])

    def test_a_carry_that_threw_once_is_left_alone_and_tried_again(self):
        record = self.ask()
        said = delegation.carry_failed(record["id"], "the brain has gone",
                                       now=at("2026-08-01T09:00:00Z"))
        self.assertEqual({"attempts": 1, "settled": False}, said)
        back = delegation.read(record["id"])
        self.assertEqual(delegation.ASKED, back["state"])
        self.assertFalse(handoffs.ready_to_carry(back, now=at("2026-08-01T09:00:30Z")))
        self.assertTrue(handoffs.ready_to_carry(back, now=at("2026-08-01T09:02:00Z")))
        self.assertEqual(handoffs.CARRY_BACKOFF_SECONDS * 2,
                         handoffs.backoff_seconds(2))

    def test_the_ceiling_settles_it_with_the_reason(self):
        """R-DEL-11 — however a delegation ends, the agent that asked is told once. A
        transient fault that never heals must not become work nobody hears about."""
        record = self.ask()
        for _ in range(delegation.CARRY_CEILING - 1):
            delegation.carry_failed(record["id"], "the brain has gone")
        said = delegation.carry_failed(record["id"], "the brain has gone")
        self.assertEqual({"attempts": delegation.CARRY_CEILING, "settled": True}, said)
        back = delegation.read(record["id"])
        self.assertEqual(delegation.FAILED, back["state"])
        self.assertIn("Rundesk could not carry this delegation", back["why"])
        self.assertIn("the brain has gone", back["why"])
        self.assertIn("rather than cole reporting on the work", back["why"])
        self.assertEqual([back], delegation.owed("elena"))

    def test_a_label_carrying_a_path_is_never_written_down_as_one(self):
        """R-DEL-15 — a label is written into a listing and into the room the work was
        asked for in. The same guarantee `role_run.safe_label` gives, and the same limit:
        what survives is one plain word, never a path anything would follow."""
        record = self.ask(label="/Users/somebody/private/exporter")
        self.assertNotIn("/", record["label"])
        self.assertEqual("cole", handoffs.safe_label("", "cole"))
        self.assertNotIn("`", handoffs.safe_label("`rm -rf /`", "cole"))
        self.assertLessEqual(len(handoffs.safe_label("x " * 200, "cole")), 60)

    def test_an_answer_longer_than_the_ceiling_keeps_its_tail(self):
        """The report is at the end. A ceiling that kept the head would keep the working
        and throw away the answer."""
        record = self.ask()
        delegation.answered(record["id"],
                            "x" * delegation.ANSWER_KEPT + "\n\nOutcome: done.")
        kept = delegation.read(record["id"])["answer"]
        self.assertEqual(delegation.ANSWER_KEPT, len(kept))
        self.assertTrue(kept.endswith("Outcome: done."))

    def test_the_undeliverable_notice_repeats_no_word_of_the_answer(self):
        """R-DEL-14 — the answer has been read by nobody. Putting any of it in front of an
        owner would publish unreviewed work by the one route built to prevent it."""
        said = delegation.ANSWER_UNDELIVERABLE.format(
            ask="del-1-aaaa", to="cole", attempts=delegation.REVIEW_CEILING)
        for word in ("It is the second query", "quote flow", TASK.split("\n")[0]):
            with self.subTest(word=word):
                self.assertNotIn(word, said)
        self.assertIn("none of it is repeated here", said)
        self.assertIn("del-1-aaaa", said)


class WhatAnAskIsRefusedFor(WithTwoAgentsOnOneInstall):
    """R-DEL-3, R-DEL-4, R-DEL-7, R-DEL-8 — refused first, and costing nothing."""

    def refused(self, **given) -> str:
        with self.assertRaises(delegation.NotDelegable) as refused:
            self.ask(**given)
        self.assertEqual([], delegation.every(), "a refused ask was written down anyway")
        return str(refused.exception)

    def test_an_ask_with_no_brief_is_refused(self):
        self.assertIn("needs a task", self.refused(brief="  \n "))

    def test_a_brief_over_the_ceiling_is_refused(self):
        self.assertIn("bounded task",
                      self.refused(brief="x" * (delegation.BRIEF_LIMIT + 1)))

    def test_an_agent_cannot_hand_work_to_itself(self):
        self.assertIn("cannot hand work to itself", self.refused(to="elena"))

    def test_an_agent_already_in_the_chain_is_refused(self):
        said = self.refused(to="dana", chain=["dana", "elena"])
        self.assertIn("already in this chain", said)

    def test_an_agent_reached_by_delegation_may_not_delegate_onward(self):
        """R-DEL-8 — depth one. An agent answering somebody else's bounded task with
        nobody present must not open a tree of work nobody is left owning."""
        said = self.refused(chain=["dana"])
        self.assertIn("cannot be handed on", said)
        self.assertIn("dana", said)

    def test_an_agent_this_install_has_not_got_is_refused(self):
        self.assertIn("no agent called 'nobody'", self.refused(to="nobody"))

    def test_an_agent_with_no_brain_is_refused_at_admission(self):
        """R-DEL-1 — knowable from the records and the machine, so it costs nothing here
        rather than a durable record, three gateway attempts and a handoff six seconds
        later saying Rundesk could not carry the work."""
        agent.add("mute", self.where)
        self.assertIn("nothing says which brain answers for 'mute'",
                      self.refused(to="mute"))

        def gone(named):
            raise provider.NotRunnable(f"there is no brain at {named}")

        self.assertIn("has no brain called", self.refused(runnable=gone))

    def test_a_turn_that_has_already_ended_is_not_a_turn_that_can_delegate(self):
        self.kept.ended(self.parent, AT, "finished")
        self.assertIn("has already ended", self.refused())
        self.assertIn("not a run of this agent", self.refused(parent_run="404-zzzz"))

    def test_a_role_execution_cannot_hand_work_to_an_agent(self):
        """The agent that put the role on hands work to another agent itself. A role
        execution has no identity of its own to be answering on behalf of."""
        working = self.a_turn(role_run="rol-1-aaaa")
        self.assertIn("a role execution cannot hand work to a named agent",
                      self.refused(parent_run=working))

    def test_a_turn_on_no_surface_the_agent_is_reachable_on_cannot_delegate(self):
        """R-DEL-4 — the answer arrives long after this turn has ended, and is delivered
        by waking the agent where the request arrived. A terminal turn has nowhere."""
        where_it_is = store.conversation_id(turn.TERMINAL, turn.TERMINAL)
        self.kept.opened(where_it_is, turn.TERMINAL, turn.TERMINAL, turn.TERMINAL, AT)
        typed = self.kept.began(turn.TERMINAL, "codex", "work", AT,
                                conversation_id=where_it_is)
        self.assertIn("not happening on a surface the agent can be reached on",
                      self.refused(parent_run=typed))

    def test_an_ask_never_widens_the_authority_its_parent_turn_had(self):
        """R-DEL-7 — the parent turn is the authority the answering agent acts under, so
        asking to change the machine from a turn only allowed to read it is asking for
        authority nobody granted."""
        self.parent = self.a_turn(posture=provider.READ)
        self.assertEqual(provider.READ, self.ask(posture=provider.WORK)["posture"])
        self.assertEqual(provider.READ, self.ask()["posture"])

    def test_an_ask_may_still_narrow_it(self):
        self.assertEqual(provider.READ, self.ask(posture=provider.READ)["posture"])
        self.assertEqual(provider.WORK, self.ask()["posture"])


class CarryingOneAsk(WithTwoAgentsOnOneInstall):
    """R-DEL-2, R-DEL-5 — the answering agent answers as itself, somewhere of its own."""

    def test_carrying_an_ask_asks_the_answering_agents_own_brain(self):
        """R-DEL-2 — never the caller's. The whole of what was asked for is this agent's
        own judgement, which its own brain, model and settings are part of."""
        record = self.ask()
        carry, outcome = self.carried(record["id"])
        self.assertEqual("cole", carry.given["name"])
        self.assertEqual("claude", carry.given["provider"])
        self.assertEqual("a-model", carry.given["model"])
        self.assertEqual(TASK, carry.given["prompt"])
        self.assertEqual("work", carry.given["posture"])
        self.assertTrue(outcome.ok)
        # Its own home and its own skills, and the marker a command refuses a second
        # level on.
        whose = agent.paths("cole", self.where)
        running = carry.given["context"]
        self.assertEqual(whose["home"], running.cwd)
        self.assertEqual(whose["skills"], running.skills)
        self.assertEqual(record["id"], running.delegating)
        self.assertIsNone(running.role_run)

    def test_the_answer_is_asked_in_a_conversation_keyed_by_the_caller_and_the_calling_run(self):
        """R-DEL-5 — never a conversation a person is typing into, and never the answering
        agent's own room, where a second ask would resume the first one's session."""
        record = self.ask()
        carry, _ = self.carried(record["id"])
        self.assertEqual(f"elena/{self.parent}", carry.given["conversation"])
        self.assertEqual(turn.AGENT, carry.given["on"])
        self.assertEqual(turn.AGENT, carry.given["kind"])
        self.assertEqual(turn.AGENT, carry.given["source"])
        self.assertEqual("rundesk", carry.given["prompt_author"])
        self.assertTrue(carry.given["stands_alone"])

    def test_the_preface_is_rundesks_standing_rules_and_the_delegation_layer(self):
        """R-DEL-2, R-DEL-6 — the opposite of a role execution: this agent is itself, so
        it is told everything a named agent is told, and then who handed it the work."""
        record = self.ask()
        carry, _ = self.carried(record["id"])
        preface = carry.given["preface"]
        self.assertTrue(preface.startswith(instructions.CORE_INSTRUCTIONS))
        self.assertIn("# Rundesk agent operating rules", preface)
        self.assertIn("You are cole, an agent running inside rundesk.", preface)
        self.assertIn("## Answering another agent", preface)
        self.assertIn("elena, an agent on your team, handed you this task.", preface)
        self.assertIn(str(agent.home("cole", self.where)), preface)
        self.assertNotIn("{caller_agent}", preface)

    def test_a_delegation_turn_is_offered_no_roles(self):
        """R-DEL-9 — the layer forbids putting a role on, so nothing above it may offer
        one. An agent shown a door it is refused at spends a turn finding out."""
        written = role.home(self.where) / "research"
        written.mkdir(parents=True, exist_ok=True)
        (written / role.MANIFEST).write_text(json.dumps(
            {"description": "Answer one bounded question.",
             "skills": ["writing-plans"], "posture": "read"}), encoding="utf-8")
        (written / role.INSTRUCTIONS).write_text("# Research\n\nAnswer it.\n",
                                                 encoding="utf-8")
        self.assertTrue(role.offered(self.where).strip(), "no role was on offer to refuse")
        record = self.ask()
        carry, _ = self.carried(record["id"])
        self.assertNotIn("## Roles you may hand heavy work to", carry.given["preface"])
        self.assertNotIn("delegating-to-roles", carry.given["preface"])
        self.assertNotIn("research", carry.given["preface"])

    def test_an_ask_that_answered_nothing_is_settled_failed_rather_than_answered(self):
        """A turn that produced nothing is not an answer, and `turn.carry` already said
        so — nothing here judges it a second time."""
        record = self.ask()
        _, outcome = self.carried(record["id"], ok=False, said="")
        self.assertFalse(outcome.ok)
        back = delegation.read(record["id"])
        self.assertEqual(delegation.FAILED, back["state"])
        self.assertEqual("", back["answer"])
        self.assertEqual("the brain said it could not", back["why"])
        self.assertEqual([back], delegation.owed("elena"))

    def test_an_ask_that_answered_is_settled_with_the_words_the_brain_said(self):
        """R-DEL-14 — recorded and never read out of. An answer claiming the work is done
        is an answer claiming the work is done; whether it is, is elena's to check."""
        record = self.ask()
        _, outcome = self.carried(record["id"], said="I read it. The join is the cost.")
        back = delegation.read(record["id"])
        self.assertEqual(delegation.ANSWERED, back["state"])
        self.assertEqual("I read it. The join is the cost.", back["answer"])
        self.assertTrue(back["settled_at"])
        self.assertEqual("", back["why"])

    def test_only_the_final_message_of_a_delegation_turn_is_returned(self):
        """R-DEL-10 — the delegation layer tells the answering agent exactly this, so it
        has to be true. Everything said on the way is working narration, and handing it on
        would bury the report inside it. Its own conversation still keeps all of it."""
        record = self.ask()
        _, outcome = self.carried(
            record["id"], narrating="Reading the quote flow now.",
            said="Outcome: the join is the cost.")
        back = delegation.read(record["id"])
        self.assertEqual("Outcome: the join is the cost.", back["answer"])
        self.assertNotIn("Reading the quote flow now.", back["answer"])
        self.assertIn("Reading the quote flow now.", outcome.text,
                      "the turn's own account lost what it said on the way")

    def test_a_settled_ask_is_never_carried_again(self):
        record = self.ask()
        self.carried(record["id"])
        with self.assertRaises(delegation.NotDelegable) as refused:
            self.carried(record["id"])
        self.assertIn("already been settled", str(refused.exception))
        with self.assertRaises(delegation.NotDelegable):
            asyncio.run(delegation.carry("elena", record["id"], where=self.where,
                                         carrying=Carried()))


class GuidingAnAskThatIsBeingAnswered(WithTwoAgentsOnOneInstall):
    """R-DEL-22 — the three verbs a role run has, with the same meanings and the same
    refusals. Three rather than one that guessed from the state: a verb that said something
    into work in flight when an agent meant to start it again spends a turn's money."""

    def test_a_word_said_to_an_ask_in_flight_reaches_the_turn_carrying_it(self):
        """The steering seam is the same one a role execution is steered through, so a word
        said to another agent travels the path a word typed at a terminal does."""
        record = self.ask()
        delegation.claim_work(record["id"])
        self.assertEqual("it reaches the work in flight; nothing is answered back here",
                         delegation.say("elena", record["id"], "read the migration too"))
        self.assertEqual(["read the migration too"],
                         delegation.claim_said(record["id"]))
        self.assertEqual([], delegation.claim_said(record["id"]),
                         "one word said reached two turns")

    def test_words_said_before_it_starts_are_folded_into_what_it_is_asked(self):
        """A brain that cannot be sent to mid-turn would never read them at the steering
        seam, and the words would simply be lost."""
        record = self.ask()
        delegation.say("elena", record["id"], "read the migration too")
        carry, _ = self.carried(record["id"])
        self.assertEqual(f"{TASK}\n\nread the migration too", carry.given["prompt"])

    def test_a_word_said_to_a_brain_that_cannot_be_sent_to_is_refused_by_name(self):
        """R-DEL-22 — said rather than queued behind a brain that will never read it. The
        answer comes off what the answering turn recorded it could do, written into the
        record when that turn started: this side of a delegation never opens the other
        agent's store, so there is nowhere else it could come from."""
        record = self.ask()
        refused: list = []

        def while_working():
            try:
                delegation.say("elena", record["id"], "and read the migration")
            except delegation.NotDelegable as why:
                refused.append(str(why))

        self.carried(record["id"], steer=False, while_working=while_working)
        self.assertEqual(1, len(refused), "a word was taken for a brain that cannot read it")
        self.assertIn("cannot be sent to while it works", refused[0])
        self.assertIn("cole", refused[0])
        # Through `provider.label`, never the configured word: a brain may be the path of a
        # program somebody wrote, and this sentence is read wherever the asking agent is
        # reached (R-DEL-15). For one that ships the label is its name, which is why this
        # asserts the guard was used rather than that the name is absent.
        self.assertIn(f"{provider.label('claude')}, the brain answering for 'cole',",
                      refused[0])

    def test_a_word_said_to_a_settled_ask_says_which_verb_was_wanted(self):
        record = self.ask()
        self.carried(record["id"])
        with self.assertRaises(delegation.NotDelegable) as refused:
            delegation.say("elena", record["id"], "and the migration")
        self.assertIn("to carry it on with more work, resume it", str(refused.exception))

    def test_carrying_on_an_ask_still_being_answered_says_which_verb_was_wanted(self):
        record = self.ask()
        delegation.claim_work(record["id"])
        with self.assertRaises(delegation.NotDelegable) as refused:
            delegation.resume("elena", record["id"], "and the migration")
        self.assertIn("to guide the work it is doing now, say it", str(refused.exception))

    def test_an_ask_another_agent_handed_over_is_not_this_agents_to_guide(self):
        """An ask is guided by the agent that handed the work over and by nobody else,
        including the one answering it — whose own turn is the thing being guided."""
        record = self.ask()
        for verb, given in ((delegation.say, ("more",)), (delegation.stop, ()),
                            (delegation.resume, ("more",))):
            with self.subTest(verb=verb.__name__):
                with self.assertRaises(delegation.NotDelegable) as refused:
                    verb("cole", record["id"], *given)
                self.assertIn("is not a delegation 'cole' handed over",
                              str(refused.exception))

    def test_no_such_ask_is_refused_by_every_verb(self):
        for verb, given in ((delegation.say, ("more",)), (delegation.stop, ()),
                            (delegation.resume, ("more",))):
            with self.subTest(verb=verb.__name__):
                with self.assertRaises(delegation.NotDelegable) as refused:
                    verb("elena", "del-9-zzzz", *given)
                self.assertIn("there is no delegation called", str(refused.exception))

    def test_an_ask_past_its_retention_window_can_no_longer_be_carried_on(self):
        """R-DEL-21 — the record is swept an hour later at most, and in between a resume
        would start work whose deadline has already gone."""
        record = self.ask()
        self.carried(record["id"])
        after = at("2026-09-01T09:00:00Z")
        for verb, given in ((delegation.say, ("more",)), (delegation.stop, ()),
                            (delegation.resume, ("more",))):
            with self.subTest(verb=verb.__name__):
                with self.assertRaises(delegation.NotDelegable) as refused:
                    verb("elena", record["id"], *given, now=after)
                self.assertIn("past its retention window", str(refused.exception))

    def test_nothing_said_and_too_much_said_are_both_refused(self):
        record = self.ask()
        delegation.claim_work(record["id"])
        for empty in ("", "   "):
            with self.subTest(said=repr(empty)):
                with self.assertRaises(delegation.NotDelegable):
                    delegation.say("elena", record["id"], empty)
        with self.assertRaises(delegation.NotDelegable) as refused:
            delegation.say("elena", record["id"], "x" * (delegation.BRIEF_LIMIT + 1))
        self.assertIn("guidance", str(refused.exception))

    def test_more_words_than_anything_is_reading_are_refused_rather_than_queued(self):
        """The record is read whole into memory by two gateways and a command, so an
        unbounded queue is the unbounded file `ANSWER_KEPT` exists to prevent."""
        record = self.ask()
        delegation.claim_work(record["id"])
        for n in range(delegation.SAID_WAITING):
            delegation.say("elena", record["id"], f"word {n}")
        with self.assertRaises(delegation.NotDelegable) as refused:
            delegation.say("elena", record["id"], "one too many")
        self.assertIn("already waiting to be read", str(refused.exception))
        self.assertEqual(delegation.SAID_WAITING,
                         delegation.words_waiting(record["id"]))


class StoppingAndCarryingOnAnAsk(WithTwoAgentsOnOneInstall):
    """R-DEL-18, R-DEL-20 — the third ending, and a resumption that keeps its session."""

    def test_a_stopped_ask_is_a_decision_and_still_owes_one_review(self):
        """R-DEL-18 — settled by `ok` alone a stop would read in the room as a fault about
        something somebody chose, and however a delegation ends the agent that handed the
        work over is told exactly once."""
        record = self.ask()
        self.assertTrue(delegation.stop("elena", record["id"], asked_by="agent"))
        back = delegation.read(record["id"])
        self.assertTrue(back["stop_asked_at"])
        self.assertEqual("agent", back["stop_asked_by"])
        self.assertEqual([], delegation.waiting("cole"),
                         "a gateway would have spent a brain on work about to be ended")
        self.assertEqual([back], delegation.stopping("cole"))

        self.assertTrue(delegation.stopped(record["id"]))
        back = delegation.read(record["id"])
        self.assertEqual(delegation.STOPPED, back["state"])
        self.assertEqual(delegation.STOPPED_EARLY, back["why"])
        self.assertEqual([back], delegation.owed("elena"))

    def test_what_an_ask_had_said_by_the_time_it_was_stopped_is_kept(self):
        """Work stopped half done is exactly the case where what came back so far is worth
        reading, so the third ending keeps it rather than clearing it like a failure."""
        record = self.ask()
        delegation.claim_work(record["id"])
        delegation.stopped(record["id"], "I read two of the three queries.")
        back = delegation.read(record["id"])
        self.assertEqual("I read two of the three queries.", back["answer"])
        self.assertEqual("", back["why"])

    def test_an_ask_already_settled_is_not_one_there_was_anything_to_stop(self):
        record = self.ask()
        self.carried(record["id"])
        self.assertFalse(delegation.stop("elena", record["id"], asked_by="terminal"))

    def test_a_resumed_ask_carries_on_in_the_conversation_it_already_had(self):
        """R-DEL-20 — the whole point. The answering turn is opened on the caller and the
        run that asked, so a resumption reaches the brain with everything it already knew
        rather than starting cold; a resume that lost the session is not a resume."""
        record = self.ask()
        first, _ = self.carried(record["id"])
        delegation.resume("elena", record["id"], "now check the index too")
        again, _ = self.carried(record["id"])
        self.assertEqual(first.given["conversation"], again.given["conversation"])
        self.assertEqual(f"elena/{self.parent}", again.given["conversation"])
        self.assertEqual(turn.AGENT, again.given["on"])

    def test_a_resumed_ask_is_asked_what_was_said_rather_than_the_task_again(self):
        """R-DEL-20 — and a first carry whose gateway died part-way is still a first carry.
        Counted on resumptions rather than on turns, which is what makes it impossible to
        hand a brain a correction where the whole task was meant."""
        record = self.ask()
        delegation.claim_work(record["id"])
        again, _ = self.carried(record["id"])
        self.assertEqual(TASK, again.given["prompt"], "a second look re-read the task")
        self.assertTrue(again.given["stands_alone"])

        delegation.resume("elena", record["id"], "now check the index too")
        carried, _ = self.carried(record["id"])
        self.assertEqual("now check the index too", carried.given["prompt"])
        self.assertFalse(carried.given["stands_alone"],
                         "a continuation was offered to a fresh session")

    def test_a_resumption_with_nothing_more_to_do_is_asked_to_carry_on(self):
        """A brain handed nothing answers about nothing, and the session it is carrying on
        already holds the work."""
        record = self.ask()
        self.carried(record["id"])
        delegation.resume("elena", record["id"], "carry on")
        delegation.claim_said(record["id"])
        carried, _ = self.carried(record["id"])
        self.assertEqual(delegation.CARRY_ON, carried.given["prompt"])

    def test_resuming_reopens_the_record_and_owes_the_review_again(self):
        """R-DEL-11 — the agent that asked is never told twice about one answer, and is
        always told once about the latest."""
        record = self.ask()
        self.carried(record["id"], said="A first answer.")
        self.assertEqual(1, len(delegation.owed("elena")))

        delegation.resume("elena", record["id"], "now check the index too")
        back = delegation.read(record["id"])
        self.assertEqual(delegation.ASKED, back["state"])
        self.assertEqual([], delegation.owed("elena"),
                         "the settled answer was still owed after being carried on")
        self.assertEqual("", back["answer"])
        self.assertEqual("", back["settled_at"])
        self.assertEqual(0, back["review_attempts"])
        self.assertEqual(1, back["resumes"])
        self.assertEqual([back], delegation.waiting("cole"))

        self.carried(record["id"], said="A second answer.")
        owed = delegation.owed("elena")
        self.assertEqual(1, len(owed), "the carried-on ask owes exactly one review")
        self.assertEqual("A second answer.", owed[0]["answer"])

    def test_carrying_on_needs_something_more_to_do(self):
        record = self.ask()
        self.carried(record["id"])
        with self.assertRaises(delegation.NotDelegable) as refused:
            delegation.resume("elena", record["id"], "   ")
        self.assertIn("needs something more to do", str(refused.exception))
        with self.assertRaises(delegation.NotDelegable):
            delegation.resume("elena", record["id"], "x" * (delegation.BRIEF_LIMIT + 1))

    def test_every_change_moves_the_deadline_and_a_listing_says_what_it_is(self):
        """R-DEL-21 — counted from latest activity rather than from settling, so an ask
        somebody is still carrying on at day thirteen is work in progress."""
        record = self.ask(now=at("2026-08-01T09:00:00Z"))
        self.assertEqual("2026-08-15T09:00:00Z", record["retained_until"])
        self.carried(record["id"])
        delegation.resume("elena", record["id"], "more", now=at("2026-08-10T09:00:00Z"))
        it = delegation.shown(delegation.read(record["id"]))
        self.assertEqual("2026-08-24T09:00:00Z", it["retained_until"])


class WhatAResumedAskStillCannotDo(WithTwoAgentsOnOneInstall):
    """R-DEL-8, R-DEL-4 — adding a way to carry an ask on must not open a hole in any of
    the three refusals that close the cycle.

    **Proved durably rather than through the environment marker.** `RUNDESK_DELEGATION` is
    a convenience a command refuses early on and never the authority — a brain that cleared
    it would still meet the record. So every case here calls `delegation.ask` directly, with
    no environment anywhere near it, from a turn shaped exactly as a resumed delegation
    turn's is: on the pseudo-surface `agent`, in a conversation keyed by the agent that
    asked and the run it asked from.
    """

    def a_delegation_turn(self) -> tuple:
        """One ask, carried and then carried on, and the answering agent's own turn of it.

        The run is written into `cole`'s records the way `turn.carry` writes one: source
        `agent`, on the `agent` surface, in the conversation `delegation.carry` opens.
        """
        record = self.ask()
        self.carried(record["id"])
        delegation.resume("elena", record["id"], "now check the index too")
        held = delegation.read(record["id"])
        self.assertEqual(1, held["resumes"], "the ask was not carried on")
        theirs = agent.records("cole", self.where)
        where_it_is = theirs.opened(
            store.conversation_id(turn.AGENT, f'elena/{self.parent}'),
            turn.AGENT, turn.AGENT, f'elena/{self.parent}', AT)["id"]
        return held, theirs.began(turn.AGENT, "claude", "work", AT,
                                  conversation_id=where_it_is)

    def test_a_resumed_delegation_turn_cannot_hand_work_back_to_the_agent_that_asked(self):
        held, run = self.a_delegation_turn()
        with self.assertRaises(delegation.NotDelegable) as refused:
            delegation.ask("cole", "elena", "have another look", run,
                           chain=held["chain"], where=self.where)
        self.assertIn("already in this chain of work", str(refused.exception))
        self.assertIn("elena", str(refused.exception))

    def test_a_resumed_delegation_turn_cannot_hand_work_to_itself(self):
        held, run = self.a_delegation_turn()
        with self.assertRaises(delegation.NotDelegable) as refused:
            delegation.ask("cole", "cole", "have another look", run,
                           chain=held["chain"], where=self.where)
        self.assertIn("cannot hand work to itself", str(refused.exception))

    def test_a_resumed_delegation_turn_cannot_hand_work_on_at_all(self):
        """Depth one. An agent reached by delegation is answering somebody else's bounded
        task with nobody present, and letting it hand that on is a tree of work nobody is
        left owning — every branch of which owes a review to an agent that has answered."""
        agent.add("dana", self.where)
        agent.remember("dana", self.where, provider="claude")
        held, run = self.a_delegation_turn()
        with self.assertRaises(delegation.NotDelegable) as refused:
            delegation.ask("cole", "dana", "have another look", run,
                           chain=held["chain"], where=self.where)
        self.assertIn("cannot be handed on", str(refused.exception))
        self.assertIn("elena", str(refused.exception))

    def test_a_resumed_delegation_turn_is_refused_even_carrying_no_chain_at_all(self):
        """**The backstop, and the reason there is one.** The three refusals above all read
        the chain the caller passed. This one reads nothing the caller said: a delegation
        turn stands on a surface that joins no channel, so there is nowhere to report work
        back to and admission refuses it whatever chain it claims to be carrying (R-DEL-4).
        """
        agent.add("dana", self.where)
        agent.remember("dana", self.where, provider="claude")
        _, run = self.a_delegation_turn()
        with self.assertRaises(delegation.NotDelegable) as refused:
            delegation.ask("cole", "dana", "have another look", run, where=self.where)
        self.assertIn("not happening on a surface the agent can be reached on",
                      str(refused.exception))

    def test_the_agent_that_asked_may_still_hand_work_on_from_its_own_turn(self):
        """The guards close a cycle, not the feature: a resumption changes nothing about
        what the agent that asked may do from a turn of its own."""
        agent.add("dana", self.where)
        agent.remember("dana", self.where, provider="claude")
        record = self.ask()
        self.carried(record["id"])
        delegation.resume("elena", record["id"], "now check the index too")
        second = delegation.ask("elena", "dana", "and look at the report",
                                self.parent, where=self.where)
        self.assertEqual(["elena"], second["chain"])
        self.assertEqual(delegation.ASKED, second["state"])


class WhatAPersonIsShown(WithTwoAgentsOnOneInstall):
    """R-DEL-15 — an owner's private words stay in the record."""

    def test_what_a_delegation_shows_carries_no_local_path_and_no_brief(self):
        record = self.ask(label="the quote flow")
        said = delegation.shown(delegation.read(record["id"]))
        self.assertEqual("the quote flow", said["label"])
        self.assertEqual("cole", said["to"])
        self.assertNotIn(TASK.split("\n")[0], json.dumps(said))
        self.assertNotIn("brief", said)
        self.assertNotIn("answer", said)


if __name__ == "__main__":
    unittest.main()
