"""What arrives on a channel, carried through to an answer — every row of channel-messaging.

Nothing here reaches a platform, and nothing here runs a brain. Both edges are arguments:
what a turn does is a stand-in this file writes, and what reaches the adapter is a list.
That is the whole point of the seam — a routing failure and a Discord failure can never be
confused, because none of this has ever heard of Discord.

Run: python3 tests/test_answering.py
"""

from __future__ import annotations

import asyncio
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from rundesk_cli import agent as agents  # noqa: E402
from rundesk_cli import answering, channel, session  # noqa: E402


class Outcome:
    """What a turn came to, in the shape `turn.carry` returns."""

    def __init__(self, run="1-aaaa", ok=True, reason="finished", text="", why=None):
        self.run, self.ok, self.reason, self.why = run, ok, reason, why
        self.text = text


class Brain:
    """A turn, as far as a channel is concerned: what it does, and how long it takes.

    Stands in for `turn.carry` and is handed in, so every case below runs with no adapter,
    no provider and no process anywhere near it.
    """

    def __init__(self, showing=(), outcome=None, holds=None, can=None, raises=None):
        self.showing = list(showing)
        self.outcome = outcome if outcome is not None else Outcome(text="all done")
        #: Something to wait on, for a case that needs a turn to still be running.
        self.holds = holds
        self.can = can if can is not None else {"steer": False}
        self.raises = raises
        #: Every call, so a case can assert on what a turn was actually asked for.
        self.asked: list = []
        #: Everything steered into the running turn.
        self.steered: list = []
        self.started = asyncio.Event()

    async def __call__(self, name, prompt, named, **how):
        self.asked.append({"name": name, "prompt": prompt, "provider": named, **how})
        if how.get("admitted"):
            how["admitted"](self.outcome.run)
        watching = how.get("watching")
        if watching is not None:
            watching({"type": "admitted", "can": self.can})
            for one in self.showing:
                watching(one)
        steering = how.get("steering")
        if steering is not None and self.can.get("steer"):
            asyncio.ensure_future(self._listen(steering))
        self.started.set()
        if self.raises is not None:
            raise self.raises
        if self.holds is not None:
            await self.holds.wait()
        return self.outcome

    async def _listen(self, steering):
        async for word in steering:
            self.steered.append(word)


class Surface:
    """Everything that reached the adapter, in order — and, when asked, a refusal."""

    def __init__(self, refuses=False):
        self.shown: list = []
        self.refuses = refuses
        self.tries = 0

    async def __call__(self, said: bytes) -> None:
        self.tries += 1
        if self.refuses:
            raise OSError("the platform would not take it")
        self.shown.append(json.loads(said))

    def of(self, kind: str) -> list:
        return [one for one in self.shown if one.get("type") == kind]

    @property
    def states(self) -> list:
        return [one["state"] for one in self.of("state")]


class CarriesAConversation(unittest.IsolatedAsyncioTestCase):
    """One agent, one channel, and nothing of the owner's anywhere near it."""

    def setUp(self):
        self.where = Path(tempfile.mkdtemp(prefix="rundesk-answering-"))
        self.addCleanup(shutil.rmtree, self.where, True)
        agents.add("ava", self.where)
        agents.remember("ava", self.where, provider="a-brain")
        self.whose = agents.directory("ava", self.where)
        self.record = {"kind": "somewhere", "allow": ["2207"], "settings": {}}
        self.told: list = []

    def answering(self, surface, brain, record=None) -> answering.Answering:
        return answering.Answering(
            "ava", "ops", record if record is not None else self.record, surface,
            where=self.where, carry=brain, note=self.told.append)

    async def carry(self, held, *records, wait=True):
        """Hand these to the channel, and let whatever they started finish."""
        for one in records:
            await held.heard(one)
        if wait:
            await self._settled(held)

    async def _settled(self, held) -> None:
        for _ in range(200):
            running = [it.task for it in held.exchanges.values()
                       if it.task is not None and not it.task.done()]
            if not running and held._showing.empty() and (
                    held._writer is None or held._writer.done()):
                return
            await asyncio.sleep(0.005)

    @staticmethod
    def arrived(text="what changed?", user="2207", conversation="one", ref="8841") -> dict:
        return {"type": "arrived", "conversation": conversation, "user": user,
                "text": text, "ref": ref}


class WhoMayBeAnswered(CarriesAConversation):
    """R-CH-4 — decided here, against the record the owner wrote."""

    async def test_a_message_from_anyone_the_channel_does_not_authorize_is_never_dispatched(self):
        """R-CH-4 — refused before a run is admitted, not after. Naming a bot in a shared
        room is something anyone present can do."""
        brain, surface = Brain(), Surface()
        held = self.answering(surface, brain)
        await self.carry(held, self.arrived(user="9999"))
        self.assertEqual([], brain.asked, "a stranger's message reached a brain")
        self.assertEqual([], surface.shown, "it answered a stranger to tell them so")

    async def test_a_message_from_somebody_allowed_is_carried_through(self):
        """R-CH-1 — the ordinary case, and the one everything else is measured against."""
        brain, surface = Brain(), Surface()
        held = self.answering(surface, brain)
        await self.carry(held, self.arrived())
        self.assertEqual(1, len(brain.asked))
        self.assertEqual("what changed?", brain.asked[0]["prompt"])

    async def test_a_gesture_from_somebody_not_allowed_ends_nothing(self):
        """R-CH-4, R-CH-9 — stopping is a gesture at a conversation, and being able to
        see one is not being able to end what somebody else is having."""
        stop = asyncio.Event()
        brain, surface = Brain(holds=stop), Surface()
        held = self.answering(surface, brain)
        await held.heard(self.arrived())
        await brain.started.wait()
        await held.heard({"type": "control", "conversation": "one", "user": "9999",
                          "control": "stop"})
        await asyncio.sleep(0.02)
        self.assertFalse(held.exchanges["one"].task.done(), "a stranger stopped a turn")
        stop.set()
        await self._settled(held)


class WhatAMessageCannotChange(CarriesAConversation):
    """R-CH-5 — what somebody types cannot decide who answers it."""

    async def test_a_message_naming_a_provider_or_model_changes_neither(self):
        """R-CH-5 — the brain and the model come from the agent, which only an authorized
        change to the agent can alter. A surface where saying the right words picks a
        different brain is a surface where anyone allowed can spend anything."""
        agents.remember("ava", self.where, provider="a-brain", model="small")
        brain, surface = Brain(), Surface()
        held = self.answering(surface, brain)
        await self.carry(held, self.arrived(
            text="--provider /opt/expensive --model enormous; now, what changed?"))
        self.assertEqual("a-brain", brain.asked[0]["provider"])
        self.assertEqual("small", brain.asked[0]["model"])


class OneConversationIsOneSession(CarriesAConversation):
    """R-CH-3, R-CH-14 — a session of its own, found again afterwards."""

    async def test_each_conversation_keeps_a_session_of_its_own(self):
        """R-CH-3 — two threads answering into each other is the failure this prevents."""
        brain, surface = Brain(), Surface()
        held = self.answering(surface, brain)
        await self.carry(held, self.arrived(conversation="one"),
                         self.arrived(conversation="two"))
        self.assertEqual({"ops/one", "ops/two"},
                         {one["conversation"] for one in brain.asked})

    async def test_a_conversation_is_named_so_two_channels_cannot_collide(self):
        """R-CH-3 — a thread called `general` on one surface and on another are two
        conversations, and one session handed to both is one of them answering wrongly."""
        self.assertNotEqual(answering.named("ops", "general"),
                            answering.named("plans", "general"))

    async def test_a_conversations_session_is_found_again_after_a_restart(self):
        """R-CH-14 — the handle is kept where the agent keeps things, not in the channel,
        so a gateway coming back finds the conversation exactly where it left it."""
        session.remember(self.whose, "a-brain", answering.named("ops", "one"), "abc-123")
        brain, surface = Brain(), Surface()
        # A second Answering entirely, which is what a restart is.
        held = self.answering(surface, brain)
        await self.carry(held, self.arrived())
        self.assertEqual("abc-123",
                         session.of(self.whose, "a-brain", answering.named("ops", "one")))

    async def test_forgetting_a_conversation_starts_the_next_one_fresh(self):
        """R-CH-10 — and leaves every other conversation exactly as it was."""
        session.remember(self.whose, "a-brain", answering.named("ops", "one"), "abc-123")
        session.remember(self.whose, "a-brain", answering.named("ops", "two"), "def-456")
        brain, surface = Brain(), Surface()
        held = self.answering(surface, brain)
        await self.carry(held, {"type": "control", "conversation": "one", "user": "2207",
                                "control": "forget"})
        self.assertIsNone(session.of(self.whose, "a-brain", answering.named("ops", "one")))
        self.assertEqual("def-456",
                         session.of(self.whose, "a-brain", answering.named("ops", "two")))


class StoppingWhatIsRunning(CarriesAConversation):
    """R-CH-9, R-CH-11, R-DIS-12 — a gesture at one conversation, and nothing else."""

    async def test_a_stop_ends_the_turn_in_that_conversation_and_nothing_else(self):
        """R-CH-9 — one conversation's, and never the gateway's."""
        stop = asyncio.Event()
        brain, surface = Brain(holds=stop), Surface()
        held = self.answering(surface, brain)
        await held.heard(self.arrived(conversation="one"))
        await held.heard(self.arrived(conversation="two"))
        await asyncio.sleep(0.02)
        await held.heard({"type": "control", "conversation": "one", "user": "2207",
                          "control": "stop"})
        await asyncio.sleep(0.02)
        self.assertTrue(held.exchanges["one"].task.done(), "the turn asked about ran on")
        self.assertFalse(held.exchanges["two"].task.done(), "it stopped somebody else's turn")
        stop.set()
        await self._settled(held)

    async def test_a_stopped_turn_is_marked_as_stopped_rather_than_failed(self):
        """R-CAD-3 — "it stopped" and "it broke" are different news about the same
        silence, and only one of them means somebody should look at something."""
        stop = asyncio.Event()
        brain, surface = Brain(holds=stop), Surface()
        held = self.answering(surface, brain)
        await held.heard(self.arrived())
        await brain.started.wait()
        await held.heard({"type": "control", "conversation": "one", "user": "2207",
                          "control": "stop"})
        await asyncio.sleep(0.05)
        await held.stop()
        self.assertIn(channel.STOPPED, surface.states)
        self.assertNotIn(channel.FAILED, surface.states)

    async def test_a_control_raised_mid_turn_publishes_no_half_written_answer(self):
        """R-DIS-12 — acknowledging a control with the running turn's output is how a
        half-finished sentence got published as though it were the reply."""
        stop = asyncio.Event()
        brain = Brain(holds=stop, showing=[{"type": "text", "text": "I was about to say"}])
        surface = Surface()
        held = self.answering(surface, brain)
        await held.heard(self.arrived())
        await brain.started.wait()
        await held.heard({"type": "control", "conversation": "one", "user": "2207",
                          "control": "stop"})
        await asyncio.sleep(0.05)
        await held.stop()
        self.assertEqual([], surface.of("answer"), "it published what the turn had written")
        self.assertNotIn("I was about to say", json.dumps(surface.shown))


class ASecondMessageWhileOneIsRunning(CarriesAConversation):
    """R-CH-9 — where a word said mid-turn actually goes."""

    async def test_a_brain_that_can_be_steered_is_given_the_words_now(self):
        """The seam already carries this, so a second message reaches the turn that is
        running rather than a new one that has forgotten what it was about."""
        stop = asyncio.Event()
        brain = Brain(holds=stop, can={"steer": True})
        surface = Surface()
        held = self.answering(surface, brain)
        await held.heard(self.arrived(text="count to ten"))
        await brain.started.wait()
        await asyncio.sleep(0.02)
        await held.heard(self.arrived(text="actually, stop at three"))
        await asyncio.sleep(0.02)
        stop.set()
        await self._settled(held)
        self.assertEqual(["actually, stop at three"], brain.steered)
        self.assertEqual(1, len(brain.asked), "it started a second turn as well")

    async def test_a_brain_that_cannot_be_steered_answers_the_second_message_after(self):
        """A brain that will never read again must not be held open for words, so they
        wait and become their own turn."""
        brain, surface = Brain(), Surface()
        held = self.answering(surface, brain)
        await held.heard(self.arrived(text="first"))
        await held.heard(self.arrived(text="second"))
        await self._settled(held)
        await asyncio.sleep(0.05)
        await self._settled(held)
        self.assertEqual(["first", "second"], [one["prompt"] for one in brain.asked])

    async def test_more_than_can_be_kept_waiting_is_bounded_and_said(self):
        """One person typing faster than an agent can answer must not be able to hand
        themselves the whole gateway."""
        stop = asyncio.Event()
        brain, surface = Brain(holds=stop), Surface()
        held = self.answering(surface, brain)
        await held.heard(self.arrived(text="first"))
        await brain.started.wait()
        for i in range(answering.WAITING + 3):
            await held.heard(self.arrived(text=f"and {i}"))
        self.assertEqual(answering.WAITING, len(held.exchanges["one"].waiting))
        self.assertTrue(any("kept waiting" in one for one in self.told))
        stop.set()
        await held.stop()


class WhenTheSurfaceWillNotTakeIt(CarriesAConversation):
    """R-CH-12 — a delivery failure is not a reason to lose the work."""

    async def test_a_delivery_that_fails_does_not_end_the_turn_it_was_reporting(self):
        """R-CH-12 — the brain is doing work somebody asked for, and losing it because a
        chat platform was busy would be losing the thing of value to protect the thing
        showing it."""
        brain, surface = Brain(), Surface(refuses=True)
        held = self.answering(surface, brain)
        await self.carry(held, self.arrived())
        self.assertEqual(1, len(brain.asked), "a refused delivery stopped the turn")
        self.assertTrue(any("could not show" in one for one in self.told),
                        "a delivery that failed was lost in silence")

    async def test_every_delivery_failing_still_leaves_the_turn_finished(self):
        """R-CH-12 — retry exhaustion is the same answer as one refusal, said more
        times: the turn stands, and what could not be shown is written down."""
        brain, surface = Brain(), Surface(refuses=True)
        held = self.answering(surface, brain)
        await self.carry(held, self.arrived())
        self.assertGreaterEqual(surface.tries, 2, "it gave up before the turn was over")
        self.assertEqual([], surface.shown)

    async def test_a_turn_that_went_wrong_is_reported_rather_than_lost(self):
        """R-CAD-3 — a turn that failed and said nothing is one somebody is waiting on."""
        brain = Brain(raises=RuntimeError("the brain would not start"))
        surface = Surface()
        held = self.answering(surface, brain)
        await self.carry(held, self.arrived())
        self.assertIn(channel.FAILED, surface.states)
        self.assertIn("would not start", json.dumps(surface.shown))


class WhenTheConnectionComesAndGoes(CarriesAConversation):
    """R-CAD-7 — a drop is the adapter's to recover from, and a turn does not notice."""

    async def test_a_connection_that_drops_does_not_end_a_running_turn(self):
        """R-CAD-7 — the work is on this machine and the connection is not."""
        stop = asyncio.Event()
        brain, surface = Brain(holds=stop), Surface()
        held = self.answering(surface, brain)
        await held.heard(self.arrived())
        await brain.started.wait()
        await held.heard({"type": "gone", "why": "the socket closed"})
        await asyncio.sleep(0.02)
        self.assertFalse(held.exchanges["one"].task.done(), "a dropped socket ended a turn")
        self.assertFalse(held.connected)
        stop.set()
        await self._settled(held)

    async def test_a_connection_that_comes_back_is_said_rather_than_guessed(self):
        """R-CAD-7 — an owner can tell a quiet agent from a deaf one."""
        brain, surface = Brain(), Surface()
        held = self.answering(surface, brain)
        await self.carry(held, {"type": "ready"})
        self.assertTrue(held.connected)
        await self.carry(held, {"type": "gone"})
        self.assertFalse(held.connected)
        await self.carry(held, {"type": "ready"})
        self.assertTrue(held.connected)

    async def test_reconnecting_finds_the_conversation_it_already_had(self):
        """R-CH-14 — the conversation is keyed by what the platform calls it, so coming
        back is finding what was there rather than starting something beside it."""
        brain, surface = Brain(), Surface()
        held = self.answering(surface, brain)
        await self.carry(held, self.arrived())
        await self.carry(held, {"type": "gone"}, {"type": "ready"})
        await self.carry(held, self.arrived(text="and now?"))
        self.assertEqual(1, len(held.exchanges), "reconnecting made a second conversation")
        self.assertEqual(["ops/one", "ops/one"],
                         [one["conversation"] for one in brain.asked])


class WhatDoesNotLeaveTheMachine(CarriesAConversation):
    """R-CH-13, R-CH-6, R-CH-7 — what is shown while a turn runs, and what is not."""

    async def test_raw_tool_arguments_and_results_do_not_leave_the_machine(self):
        """R-CH-13 — a tool's own arguments, the file it read, the whole of what a command
        printed. All of it is kept in the account and none of it is posted into a room
        somebody else can read."""
        brain = Brain(showing=[{
            "type": "tool", "id": "1", "name": "Bash", "did": "run",
            "arguments": {"command": "cat ~/.ssh/id_rsa"}, "cwd": "/home/someone"}])
        surface = Surface()
        held = self.answering(surface, brain)
        await self.carry(held, self.arrived())
        shown = surface.of("tool")[0]
        self.assertEqual("Bash", shown["name"])
        self.assertNotIn("arguments", shown, "a tool's own arguments were published")
        self.assertNotIn("id_rsa", json.dumps(surface.shown))

    async def test_a_field_nobody_here_knows_stays_here(self):
        """R-CH-13 — named rather than filtered, so the default for whatever a vendor
        attaches next year is that it does not leave."""
        brain = Brain(showing=[{"type": "result", "id": "1", "ok": True,
                                "summary": "3 files changed",
                                "invented_next_year": "a private path"}])
        surface = Surface()
        held = self.answering(surface, brain)
        await self.carry(held, self.arrived())
        self.assertEqual({"type", "conversation", "run", "id", "ok", "summary"},
                         set(surface.of("result")[0]))

    async def test_a_summary_too_long_to_show_is_bounded_rather_than_dropped(self):
        """R-CH-13 — a brain may hand back everything a command printed. The first of it
        is worth showing and the rest is worth not pasting anywhere."""
        brain = Brain(showing=[{"type": "result", "id": "1", "ok": False,
                                "summary": "x" * 5000}])
        surface = Surface()
        held = self.answering(surface, brain)
        await self.carry(held, self.arrived())
        shown = surface.of("result")[0]["summary"]
        self.assertLess(len(shown), 5000)
        self.assertTrue(shown.startswith("x"), "it dropped the summary instead of bounding it")

    async def test_what_the_agent_did_is_shown_while_the_turn_is_still_running(self):
        """R-CH-6 — a tool it ran, a thought it closed. Worth watching as it happens, and
        whole the moment it exists."""
        brain = Brain(showing=[{"type": "think", "text": "the error is in the parser"},
                               {"type": "tool", "id": "1", "did": "run"}])
        surface = Surface()
        held = self.answering(surface, brain)
        await self.carry(held, self.arrived())
        kinds = [one["type"] for one in surface.shown]
        self.assertLess(kinds.index("think"), kinds.index("answer"),
                        "what it did was shown after what it said")

    async def test_the_answer_arrives_whole_and_once(self):
        """R-CH-8 — however it was written, it is handed over in one piece at the end."""
        brain = Brain(showing=[{"type": "text", "text": "three "},
                               {"type": "text", "text": "files changed"}],
                      outcome=Outcome(text="three files changed"))
        surface = Surface()
        held = self.answering(surface, brain)
        await self.carry(held, self.arrived())
        self.assertEqual(["three files changed"],
                         [one["text"] for one in surface.of("answer")])

    async def test_an_answer_too_long_for_any_one_message_crosses_whole(self):
        """R-CH-8, R-DIS-13 — splitting it is the surface's, because the limit is the
        surface's. What crosses here is all of it, or the surface is splitting something
        that was already cut."""
        whole = "word " * 4000
        brain = Brain(outcome=Outcome(text=whole))
        surface = Surface()
        held = self.answering(surface, brain)
        await self.carry(held, self.arrived())
        self.assertEqual(whole.strip(), surface.of("answer")[0]["text"])

    async def test_a_turn_that_said_nothing_hands_over_no_empty_answer(self):
        """R-CH-8 — an empty message is a thing a surface would have to post."""
        brain, surface = Brain(outcome=Outcome(text="   ")), Surface()
        held = self.answering(surface, brain)
        await self.carry(held, self.arrived())
        self.assertEqual([], surface.of("answer"))
        self.assertIn(channel.FINISHED, surface.states)


class WhatAChannelDoesNotWriteDown(CarriesAConversation):
    """R-CH-15 — delivery on top of the account, never a second record."""

    async def test_work_a_channel_dispatched_is_findable_by_the_run_it_became(self):
        """R-CH-15 — the account is told where the turn came from, so a run can be read
        back afterwards and say which conversation asked for it."""
        brain, surface = Brain(), Surface()
        held = self.answering(surface, brain)
        await self.carry(held, self.arrived())
        self.assertEqual({"channel": "ops", "on": "one", "user": "2207"},
                         brain.asked[0]["asked_by"])

    async def test_the_run_is_named_from_the_first_mark_rather_than_the_last(self):
        """R-CH-15 — everything shown before the end is uncorrelated otherwise, which is
        every mark that matters while somebody is waiting."""
        brain, surface = Brain(showing=[{"type": "tool", "id": "1", "did": "run"}]), Surface()
        held = self.answering(surface, brain)
        await self.carry(held, self.arrived())
        self.assertTrue(all(one.get("run") == "1-aaaa" for one in surface.of("tool")))
        self.assertEqual("1-aaaa", surface.of("state")[-1]["run"])

    async def test_a_channel_writes_nothing_of_its_own(self):
        """R-CH-15 — everything about the turn is the account's, and the channel's own
        directory holds only what the adapter put there."""
        brain, surface = Brain(), Surface()
        held = self.answering(surface, brain)
        await self.carry(held, self.arrived())
        beside = {at.name for at in self.whose.iterdir()}
        self.assertNotIn("ops.json", beside)
        self.assertNotIn("conversations.json", beside)


if __name__ == "__main__":
    unittest.main(verbosity=2)
