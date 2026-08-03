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

from rundesk import agent, config, delegation, provider, role, store, turn  # noqa: E402

TASK = "Look at the quote flow and say what is slow about it.\nRead only; change nothing.\n"
AT = "2026-08-01T09:00:00Z"


def at(said: str):
    """That moment, as the clock every decision here is handed."""
    return lambda: store.moment(said).timestamp()


class Carried:
    """The turn, as a stand-in — it records what it was handed and answers well."""

    def __init__(self, ok: bool = True, said: str = "It is the second query. Here is why.",
                 narrating: str = ""):
        self.given: dict = {}
        self._ok = ok
        self._said = said
        self._narrating = narrating

    async def __call__(self, name, prompt, named, **given):
        self.given = {"name": name, "prompt": prompt, "provider": named, **given}
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
        self.assertFalse(delegation.ready_to_carry(back, now=at("2026-08-01T09:00:30Z")))
        self.assertTrue(delegation.ready_to_carry(back, now=at("2026-08-01T09:02:00Z")))
        self.assertEqual(delegation.CARRY_BACKOFF_SECONDS * 2,
                         delegation.backoff_seconds(2))

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
        self.assertEqual("cole", delegation.safe_label("", "cole"))
        self.assertNotIn("`", delegation.safe_label("`rm -rf /`", "cole"))
        self.assertLessEqual(len(delegation.safe_label("x " * 200, "cole")), 60)

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
        self.assertTrue(preface.startswith("# Rundesk agent operating rules"))
        self.assertIn("You are cole, an agent running inside rundesk.", preface)
        self.assertIn("## Work handed to you by another agent", preface)
        self.assertIn("The named agent elena handed you this task.", preface)
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
