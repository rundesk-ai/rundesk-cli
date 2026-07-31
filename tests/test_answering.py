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
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from rundesk import agent as agents  # noqa: E402
from rundesk import answering, channel, config, store  # noqa: E402

#: When a conversation was opened. A calendar fact, never what anything is ordered by.
AT = "2026-07-26T09:00:00Z"


class Outcome:
    """What a turn came to, in the shape `turn.carry` returns.

    Every attribute the real one has, including the ones a case does not use: a stand-in
    missing one is a stand-in that passes while the thing it stands in for raises.
    """

    def __init__(self, run="1-aaaa", ok=True, reason="finished", text="", why=None,
                 files=()):
        self.run, self.ok, self.reason, self.why = run, ok, reason, why
        self.text = text
        self.files = list(files)


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
        # Exactly what `turn.carry` does, and no more. It told the watcher what the
        # brain could do as though that were one of the brain's own records, which the
        # real turn has never passed on — so the surface never learned it, `running` was
        # never marked, and steering was dead. A stand-in more generous than the thing it
        # stands in for proves nothing at all.
        if how.get("admitted"):
            how["admitted"](self.outcome.run, dict(self.can))
        watching = how.get("watching")
        if watching is not None:
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
        before = os.environ.get("RUNDESK_DATA_DIR")
        data = self.where / "_data"
        os.environ["RUNDESK_DATA_DIR"] = str(data)
        self.addCleanup(lambda: os.environ.__setitem__("RUNDESK_DATA_DIR", before)
                        if before is not None
                        else os.environ.pop("RUNDESK_DATA_DIR", None))
        config.ensure(data)
        agents.add("ava", self.where)
        agents.remember("ava", self.where, provider="a-brain")
        self.whose = agents.directory("ava", self.where)
        self.record = {"kind": "somewhere", "allow": ["2207"], "settings": {}}
        self.told: list = []

    def kept(self, conversation: str = "one", brain: str = "a-brain",
             channel: str = "ops") -> str | None:
        """Where this conversation got to for this brain, asked the way a turn asks."""
        return agents.reading("ava", self.where).session(
            store.conversation_id(channel, conversation), brain)

    def keeping(self, conversation: str, handle: str, brain: str = "a-brain",
                channel: str = "ops") -> None:
        """Arrange a conversation that has already got somewhere, as a restart finds it."""
        records = agents.records("ava", self.where)
        where_it_is = store.conversation_id(channel, conversation)
        records.opened(where_it_is, channel, "somewhere", conversation, AT)
        records.remember_session(where_it_is, brain, handle)

    def answering(self, surface, brain, record=None, querying=None,
                  restart_waiting=None, restart_ready=None) -> answering.Answering:
        return answering.Answering(
            "ava", "ops", record if record is not None else self.record, surface,
            where=self.where, carry=brain, note=self.told.append, querying=querying,
            restart_waiting=restart_waiting, restart_ready=restart_ready)

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
    def words(prompt: str) -> str:
        """What somebody actually typed, without what rundesk added under it (R-CH-21).

        A prompt is the words, then what was attached, then where it was said — so a case
        about the words says so, and does not have to be rewritten every time something
        else is worth telling a brain.
        """
        return prompt.split("\n\n")[0]

    @staticmethod
    def arrived(text="what changed?", user="2207", conversation="one", ref="8841") -> dict:
        return {"type": "arrived", "conversation": conversation, "user": user,
                "text": text, "ref": ref}


class QueuedRestartDelivery(CarriesAConversation):
    async def test_a_queued_restart_waits_for_the_final_answer_delivery(self):
        """R-GW-43"""
        releasing = asyncio.Event()
        final_attempted = asyncio.Event()
        released = []

        class SlowFinal(Surface):
            async def __call__(mine, said):
                record = json.loads(said)
                if record.get("state") == channel.FINISHED:
                    final_attempted.set()
                    await releasing.wait()
                await super().__call__(said)

        surface = SlowFinal()
        held = self.answering(
            surface, Brain(),
            restart_waiting=lambda run: run == "1-aaaa",
            restart_ready=lambda run: released.append((run, list(surface.states))),
        )
        await held.heard(self.arrived())
        await asyncio.wait_for(final_attempted.wait(), timeout=1)
        self.assertEqual([], released, "the restart was released before the final answer")
        releasing.set()
        await self._settled(held)
        self.assertEqual([
            ("1-aaaa", [channel.TAKEN, channel.RUNNING, channel.FINISHED])
        ], released)


class WhereABrainIsAnswering(CarriesAConversation):
    """R-CH-21 — a brain was handed the words and nothing else, so it answered a room of
    forty people in exactly the voice it used for a direct message, and the person it was
    talking to was a number it never saw."""

    def spoken_on(self, space: str = "one") -> str:
        """A conversation this surface has already had, which is what gives a schedule
        somewhere to report. Opened through the store rather than by driving a turn: what is
        under test is where an outcome goes, not how a conversation comes to exist."""
        kept = agents.records("ava", self.where)
        return kept.opened(store.conversation_id("ops", space), "ops", "somewhere", space,
                           store.stamped())["id"]

    def a_schedule(self, named: str = "nightly", **held) -> dict:
        kept = agents.records("ava", self.where)
        kept.remember_schedule(named, "0 3 * * *", store.stamped(),
                               prompt=held.pop("prompt", "what changed?"), **held)
        return kept.schedule(named)

    async def test_a_reply_tells_the_brain_which_message_the_follow_up_is_for(self):
        """R-CH-29 — reply context is distinct from the new words and channel neutral."""
        surface, brain = Surface(), Brain()
        held = self.answering(surface, brain)
        arrived = self.arrived(text="fix the second one")
        arrived[channel.REPLY_TO] = {
            "id": "8839", "resolved": True, "author": "Winston",
            "text": "1. logs\n2. parser\n3. docs",
        }
        await self.carry(held, arrived)
        prompt = brain.asked[0]["prompt"]
        self.assertEqual(
            "fix the second one\n\n--\n\n"
            "This message replies to conversation message 8839 from Winston.\n"
            "Quoted message: 1. logs\n2. parser\n3. docs",
            prompt,
        )

    async def test_an_unresolved_reply_still_starts_a_turn_and_says_what_is_missing(self):
        """R-CH-30 — a deleted or unavailable parent never costs the new message."""
        surface, brain = Surface(), Brain()
        held = self.answering(surface, brain)
        arrived = self.arrived(text="what about this?")
        arrived[channel.REPLY_TO] = {"id": "8839", "resolved": False}
        await self.carry(held, arrived)
        self.assertEqual(
            "what about this?\n\n--\n\n"
            "This message replies to conversation message 8839 "
            "(quoted text unavailable).",
            brain.asked[0]["prompt"],
        )

    async def test_an_ordinary_message_has_no_empty_reply_context(self):
        """R-CH-29 — the ordinary prompt remains exactly the words somebody sent."""
        surface, brain = Surface(), Brain()
        held = self.answering(surface, brain)
        await self.carry(held, self.arrived())
        self.assertEqual("what changed?", brain.asked[0]["prompt"])

    async def test_what_a_schedule_came_to_is_said_where_this_agent_is_reached(self):
        """R-SCH-31 — the first trigger with no person at the other end. Work that failed at
        three in the morning is no use in an account nobody opens until they think to.

        Said as a remark: there is no message to reply to and no reaction to put on one."""
        where_it_is = self.spoken_on()
        self.a_schedule()
        surface = Surface()
        held = self.answering(surface, Brain())
        await held.told_what_a_schedule_did("nightly", "finished")
        await self._settled(held)
        said = surface.of("said")
        self.assertEqual(1, len(said), f"nothing was said on the surface: {surface.shown}")
        self.assertIn("nightly", said[0]["text"])
        self.assertIn("finished", said[0]["text"])
        self.assertEqual(where_it_is, said[0]["conversation"],
                         "it was said somewhere other than where this surface has been used")

    async def test_what_the_turn_answered_is_said_with_what_it_came_to(self):
        """R-SCH-31 — the outcome word alone is an owner asking what happened and being told
        that something did. What it said is read back out of the account, where it already is."""
        self.spoken_on()
        row = self.a_schedule()
        kept = agents.records("ava", self.where)
        its_own = kept.opened(store.conversation_id("schedule", "nightly"), "schedule",
                              "schedule", "nightly", store.stamped())["id"]
        run = kept.began("schedule", "a-brain", "safe", store.stamped(),
                         conversation_id=its_own, schedule_id=row["id"])
        kept.answered(its_own, run, store.stamped(), "nothing broke overnight")
        kept.ended(run, store.stamped(), "finished")

        surface = Surface()
        held = self.answering(surface, Brain())
        await held.told_what_a_schedule_did("nightly", "finished")
        await self._settled(held)
        self.assertIn("nothing broke overnight", surface.of("said")[0]["text"])

    async def test_what_a_surface_is_shown_is_what_the_agent_said(self):
        """R-SCH-34 — a person reading a room wants what their agent found, not a line of
        rundesk's bookkeeping above it on every post for ever. Which schedule produced it is in
        the account and in `schedules`, where somebody asking that is already looking."""
        self.spoken_on()
        row = self.a_schedule()
        kept = agents.records("ava", self.where)
        its_own = kept.opened(store.conversation_id("schedule", "nightly"), "schedule",
                              "schedule", "nightly", store.stamped())["id"]
        run = kept.began("schedule", "a-brain", "safe", store.stamped(),
                         conversation_id=its_own, schedule_id=row["id"])
        kept.answered(its_own, run, store.stamped(), "nothing broke overnight")
        kept.ended(run, store.stamped(), "finished")
        surface = Surface()
        held = self.answering(surface, Brain())
        await held.told_what_a_schedule_did("nightly", "finished")
        await self._settled(held)
        self.assertEqual("nothing broke overnight", surface.of("said")[0]["text"])

    async def test_a_schedule_that_failed_says_so_rather_than_saying_nothing(self):
        """R-SCH-34 — the half the answer alone must not swallow. A reader left to infer a
        failure from a post that never came is a reader who infers nothing at all."""
        self.spoken_on()
        self.a_schedule()
        surface = Surface()
        held = self.answering(surface, Brain())
        await held.told_what_a_schedule_did("nightly", "failed")
        await self._settled(held)
        self.assertIn("failed", surface.of("said")[0]["text"])
        self.assertIn("nightly", surface.of("said")[0]["text"])

    async def test_a_schedule_that_started_a_program_is_still_said(self):
        """R-SCH-31 — a program has no answer to read back, so the remark is what it came to
        and nothing else. One shape for both kinds rather than two callers deciding."""
        self.spoken_on()
        kept = agents.records("ava", self.where)
        kept.remember_schedule("tidy", "0 4 * * *", store.stamped(), command=["/bin/tidy"])
        surface = Surface()
        held = self.answering(surface, Brain())
        await held.told_what_a_schedule_did("tidy", "failed")
        await self._settled(held)
        self.assertEqual("schedule 'tidy' failed", surface.of("said")[0]["text"])

    async def test_a_surface_that_will_not_take_it_changes_nothing(self):
        """R-SCH-31 — the work is over and the record of it is already written, so a platform
        refusing is said in the log and nothing else."""
        self.spoken_on()
        self.a_schedule()
        surface = Surface(refuses=True)
        held = self.answering(surface, Brain())
        await held.told_what_a_schedule_did("nightly", "finished")
        await self._settled(held)
        self.assertEqual([], surface.shown)
        self.assertTrue(any("could not show" in one for one in self.told),
                        f"a refusal was swallowed: {self.told}")

    async def test_a_schedule_says_which_place_on_a_surface_it_reports_in(self):
        """R-SCH-32 — a channel reaching a whole server has many rooms, and the newest
        conversation is whichever somebody last spoke in. An owner naming one is the only
        thing that makes a daily report land where they meant."""
        self.spoken_on("one")
        wanted = self.spoken_on("two")
        self.a_schedule(place="two")
        surface = Surface()
        held = self.answering(surface, Brain())
        await held.told_what_a_schedule_did("nightly", "finished")
        await self._settled(held)
        said = surface.of("said")[0]
        self.assertEqual(wanted, said["conversation"],
                         "it followed the conversation instead of the place it was given")
        self.assertEqual("two", said["place"], "the surface was not told which place")

    async def test_a_schedule_naming_no_place_follows_the_conversation(self):
        """R-SCH-32 — the older behaviour, kept: a channel that reaches one place has one
        place to report in, so requiring a word for it would be asking for nothing."""
        where_it_is = self.spoken_on()
        self.a_schedule()
        surface = Surface()
        held = self.answering(surface, Brain())
        await held.told_what_a_schedule_did("nightly", "finished")
        await self._settled(held)
        said = surface.of("said")[0]
        self.assertEqual(where_it_is, said["conversation"])
        self.assertIsNone(said["place"], "a place nobody named was invented")

    async def test_what_a_place_is_called_is_never_read_on_the_way_past(self):
        """R-SCH-32, R-CAD-16 — the core does not know this platform has rooms. A place it has
        never seen a word in is the adapter's to resolve, so it goes over with no conversation
        rather than being refused: only the surface can reach a room nobody has spoken in."""
        self.spoken_on("one")
        self.a_schedule(place="#a-room-nobody-has-used")
        surface = Surface()
        held = self.answering(surface, Brain())
        await held.told_what_a_schedule_did("nightly", "finished")
        await self._settled(held)
        said = surface.of("said")[0]
        self.assertEqual("#a-room-nobody-has-used", said["place"])
        self.assertIsNone(said["conversation"], "a place we have not seen was guessed at")

    async def test_what_a_schedule_reported_is_written_down_where_it_was_reported(self):
        """R-SCH-33 — the gap that made an agent ask "what work?". The turn ran in the
        schedule's own conversation, so a person replying in the room it was posted to reaches
        a brain whose session never saw it — and the account of that room did not have it
        either, which is the one place looking it up could have found it."""
        where_it_is = self.spoken_on()
        self.a_schedule()
        surface = Surface()
        held = self.answering(surface, Brain())
        await held.told_what_a_schedule_did("nightly", "finished")
        await self._settled(held)
        kept = agents.records("ava", self.where)
        said = [one for one in kept.messages(where_it_is) if one["author"] == "agent"]
        self.assertEqual(1, len(said), "what was posted was not written down where it went")
        self.assertIn("nightly", said[0]["text"])

    async def test_what_was_reported_names_the_run_that_produced_it(self):
        """R-SCH-33 — one run, delivered into a second conversation. Naming it is what ties
        the message somebody replies to back to the work it is about."""
        where_it_is = self.spoken_on()
        row = self.a_schedule()
        kept = agents.records("ava", self.where)
        its_own = kept.opened(store.conversation_id("schedule", "nightly"), "schedule",
                              "schedule", "nightly", store.stamped())["id"]
        run = kept.began("schedule", "a-brain", "safe", store.stamped(),
                         conversation_id=its_own, schedule_id=row["id"])
        kept.ended(run, store.stamped(), "finished")
        surface = Surface()
        held = self.answering(surface, Brain())
        await held.told_what_a_schedule_did("nightly", "finished")
        await self._settled(held)
        said = [one for one in kept.messages(where_it_is) if one["author"] == "agent"]
        self.assertEqual(run, said[0]["run_id"])

    async def test_a_surface_nobody_has_spoken_on_has_nowhere_to_say_it(self):
        """R-SCH-31 — said rather than invented. Guessing a place on a platform whose words
        this code does not read is how an agent posts into a room nobody meant it to be in."""
        surface = Surface()
        held = self.answering(surface, Brain())
        await held.told_what_a_schedule_did("nightly", "finished")
        self.assertEqual([], surface.of("said"), "it invented somewhere to post")
        self.assertTrue(any("nowhere to say" in one for one in self.told),
                        f"it said nothing about having nowhere: {self.told}")

    async def test_a_scheduled_run_says_it_has_started_where_it_will_report(self):
        """R-SCH-46 — where the pair goes is resolved here, once, and handed back for the
        report to be delivered to, because a notice in one room and its outcome in another is
        worse than neither."""
        where_it_is = self.spoken_on()
        self.a_schedule()
        surface = Surface()
        held = self.answering(surface, Brain())
        self.assertEqual((True, where_it_is), await held.told_a_schedule_started("nightly"),
                         "it did not hand back where the notice went")
        await self._settled(held)
        said = surface.of("said")
        self.assertEqual(1, len(said), f"nothing was said on the surface: {surface.shown}")
        self.assertEqual("💻 Working on 'nightly' — I will report back when it is done.",
                         said[0]["text"])
        self.assertEqual(where_it_is, said[0]["conversation"])
        self.assertEqual("nightly", said[0]["schedule"])
        self.assertTrue(said[0]["began"], "the surface cannot tell a notice from a report")

    async def test_a_scheduled_run_says_which_schedule_its_report_is_for(self):
        """R-SCH-46 — the name is how a surface finds the message it posted at the start. It is
        a key and never something to read: what a place is called is already carried unread past
        this file, and this is the same promise for the same reason (R-SCH-32)."""
        self.spoken_on()
        self.a_schedule()
        surface = Surface()
        held = self.answering(surface, Brain())
        await held.told_a_schedule_started("nightly")
        await held.told_what_a_schedule_did("nightly", "finished")
        await self._settled(held)
        notice, report = surface.of("said")
        self.assertEqual(("nightly", True), (notice["schedule"], notice["began"]))
        self.assertEqual("nightly", report["schedule"])
        self.assertIsNone(report.get("began"),
                          "the report claims to be a notice, so it would anchor to itself")

    async def test_a_scheduled_run_starting_is_said_in_the_place_the_schedule_named(self):
        """R-SCH-32, R-SCH-46 — an owner naming a room is what makes a daily report land where
        they meant, and a notice that ignored it would stand in a room the report never reaches."""
        self.spoken_on("one")
        wanted = self.spoken_on("two")
        self.a_schedule(place="two")
        surface = Surface()
        held = self.answering(surface, Brain())
        await held.told_a_schedule_started("nightly")
        await self._settled(held)
        said = surface.of("said")[0]
        self.assertEqual(wanted, said["conversation"])
        self.assertEqual("two", said["place"], "the surface was not told which place")

    async def test_a_report_is_delivered_where_the_notice_went(self):
        """R-SCH-46, R-SCH-32 — resolving the same *way* is not resolving to the same *answer*.
        Where a schedule with no place named reports is the newest conversation on the surface,
        and the owner writing in another room during the twenty minutes the run takes is what
        makes that a different room. Asked again at the end, the notice stands in the first one
        for ever with nothing under it while the report lands in the second, anchored to
        nothing — so the notice decides where, once, and the report is delivered there."""
        kept = agents.records("ava", self.where)
        began_in = kept.opened(store.conversation_id("ops", "general"), "ops", "somewhere",
                               "general", "2026-07-26T06:00:00Z")["id"]
        self.a_schedule()
        surface = Surface()
        held = self.answering(surface, Brain())
        said, where = await held.told_a_schedule_started("nightly")
        self.assertTrue(said)
        # The owner writes in another room while the run is going, which is all it takes for
        # the newest conversation on this surface to be a different one.
        kept.opened(store.conversation_id("ops", "random"), "ops", "somewhere", "random",
                    "2026-07-26T06:10:00Z")
        await held.told_what_a_schedule_did("nightly", "finished", where=where)
        await self._settled(held)
        notice, report = surface.of("said")
        self.assertEqual(began_in, notice["conversation"])
        self.assertEqual(began_in, report["conversation"],
                         "the report went to whichever room was newest, not to its notice")
        wrote = [one["text"] for one in kept.messages(began_in) if one["author"] == "agent"]
        self.assertEqual([report["text"]], wrote,
                         "what was delivered was written down in another conversation (R-SCH-33)")

    async def test_a_report_for_a_schedule_that_named_a_place_goes_to_the_place(self):
        """R-SCH-32, R-SCH-46 — a place is a word the owner said, carried to the adapter for
        both messages, so there is nothing for the pair to disagree about and nothing to carry
        over from the notice. The word wins over anything handed in beside it."""
        self.spoken_on("one")
        wanted = self.spoken_on("two")
        self.a_schedule(place="two")
        surface = Surface()
        held = self.answering(surface, Brain())
        await held.told_a_schedule_started("nightly")
        await held.told_what_a_schedule_did("nightly", "finished", where="somewhere-else")
        await self._settled(held)
        notice, report = surface.of("said")
        self.assertEqual((wanted, "two"), (notice["conversation"], notice["place"]))
        self.assertEqual((wanted, "two"), (report["conversation"], report["place"]),
                         "the report left the place its owner named")

    async def test_a_surface_with_nowhere_to_deliver_says_nothing_when_a_run_starts(self):
        """R-SCH-46 — nowhere to say what a run found is nowhere to say it began. Said rather
        than invented, and handed back, because only a notice that went out is owed a reply."""
        surface = Surface()
        held = self.answering(surface, Brain())
        self.assertEqual((False, None), await held.told_a_schedule_started("nightly"))
        await self._settled(held)
        self.assertEqual([], surface.of("said"), "it invented somewhere to post")
        self.assertTrue(any("nowhere to say that 'nightly' has started" in one
                            for one in self.told),
                        f"it said nothing about having nowhere: {self.told}")

    async def test_what_rundesk_says_a_run_started_is_not_the_agents_own_record(self):
        """R-SCH-33, R-SCH-46 — the report is written down where it was delivered so a person
        replying to it reaches a brain whose session saw it. Nobody replies "nice work" to
        rundesk saying work has begun, and writing it in would put a line the agent never said
        into the account of what the agent said."""
        where_it_is = self.spoken_on()
        self.a_schedule()
        surface = Surface()
        held = self.answering(surface, Brain())
        await held.told_a_schedule_started("nightly")
        await self._settled(held)
        kept = agents.records("ava", self.where)
        said = [one for one in kept.messages(where_it_is) if one["author"] == "agent"]
        self.assertEqual([], said, "rundesk's own bookkeeping was written down as the agent's")

    async def test_a_channel_that_says_nothing_falls_to_what_the_agent_says(self):
        """R-AGT-16, R-CH-22 — the composition, rather than either half of it. `channel.py`
        has no idea what an agent keeps and `agent.py` has no idea what a surface is, so this
        is the only place the order between them is actually exercised."""
        agents.remember("ava", self.where, instructions="You are {agent}, and you are brief.")
        brain, surface = Brain(), Surface()
        held = self.answering(surface, brain)
        await self.carry(held, self.arrived())
        # Added to rundesk's own rather than replacing them (R-AGT-17); which of the
        # *situation* lines won is what this case is about.
        said = brain.asked[0]["preface"].replace(
            agents.standing("ava", self.where), ""
        ).strip()
        self.assertEqual("You are ava, and you are brief.", said,
                         "the agent's own was passed over for rundesk's default sentence")

    async def test_channel_and_agent_instructions_both_append(self):
        """R-AGT-16, R-AGT-17, R-CH-22 — neither owner layer replaces another."""
        agents.remember("ava", self.where, instructions="what the agent says")
        brain, surface = Brain(), Surface()
        held = self.answering(surface, brain,
                              record=dict(self.record, instructions="Keep it short here."))
        await self.carry(held, self.arrived())
        said = brain.asked[0]["preface"]
        self.assertTrue(said.startswith(agents.standing("ava", self.where)))
        self.assertIn("Keep it short here.", said)
        self.assertIn("what the agent says", said)
        self.assertLess(said.index("rundesk messages ava"), said.index("Keep it short here."))
        self.assertLess(said.index("Keep it short here."), said.index("what the agent says"))

    async def test_a_brain_is_told_which_surface_and_conversation_it_is_answering_in(self):
        """R-CH-21 — the surface, the channel the owner named, the place as that surface
        shows it, and who is asking."""
        brain, surface = Brain(), Surface()
        held = self.answering(surface, brain)
        await self.carry(held, dict(
            self.arrived(), direct=False,
            where="#ops on the Rundesk server", called="Tim",
        ))
        said = brain.asked[0]["preface"]
        self.assertEqual("what changed?", brain.asked[0]["prompt"],
                         "the situation was folded into what the person typed")
        self.assertIn("through somewhere", said)
        self.assertNotIn("'ops'", said, "rundesk's own label for the connection is not "
                         "the agent's business, and collides with the platform's own word")
        self.assertIn("in #ops on the Rundesk server", said)
        self.assertIn("responding to Tim", said)

    async def test_channel_turns_fill_the_agents_resolved_locations(self):
        """R-AGT-38 — channel composition receives local agent paths from the agent layer."""
        brain, surface = Brain(), Surface()
        held = self.answering(surface, brain)
        await self.carry(held, self.arrived())
        said = brain.asked[0]["preface"]
        self.assertIn(f"`{agents.home('ava', self.where)}`", said)
        self.assertIn(f"`{agents.workspace('ava', self.where)}`", said)
        self.assertNotIn("{agent_home}", said)
        self.assertNotIn("{workspace}", said)

    async def test_a_surface_that_names_neither_is_answered_exactly_as_before(self):
        """R-CH-21 — an adapter that supplies no trigger context gets none invented."""
        brain, surface = Brain(), Surface()
        held = self.answering(surface, brain)
        await self.carry(held, self.arrived())
        # Rundesk's own words come first on every turn now (R-AGT-17) and legitimately
        # contain ", in " — so the guard reads what the *surface* added, not the whole of it.
        said = brain.asked[0]["preface"].replace(
            agents.standing("ava", self.where), ""
        ).strip()
        self.assertEqual("", said)

    async def test_a_channel_of_an_unnamed_kind_says_nothing_about_where_it_is(self):
        """R-CH-21 — a half-written line about a surface with no name is worse than no
        line: it is rundesk telling a brain something it does not know."""
        brain, surface = Brain(), Surface()
        held = self.answering(surface, brain, record={"kind": "", "allow": ["2207"],
                                                      "settings": {}})
        await self.carry(held, dict(self.arrived(), where="#ops", called="Tim"))
        self.assertEqual("what changed?", brain.asked[0]["prompt"])
        # Rundesk's own words and nothing else: nothing was invented about a surface that
        # said nothing about itself (R-CH-21, R-AGT-17).
        self.assertEqual(agents.standing("ava", self.where), brain.asked[0]["preface"])


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
        self.assertEqual("what changed?", self.words(brain.asked[0]["prompt"]))

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


class ReadOnlyGatewayQuestions(CarriesAConversation):
    """R-CAD-17, R-CH-23, R-CH-24 — inspection without a brain turn."""

    @staticmethod
    def query(user="2207", named="status"):
        return {
            "type": "query", "conversation": "one", "user": user,
            "query": named, "ref": "interaction-1",
        }

    async def test_an_authorized_gateway_query_is_answered_without_a_brain_turn(self):
        """R-CH-23, R-CH-24"""
        brain, surface = Brain(), Surface()
        held = self.answering(
            surface, brain, querying=lambda asked: f"{asked}: RUNNING"
        )
        await held.heard(self.query())
        await self._settled(held)
        self.assertEqual([], brain.asked)
        self.assertEqual([{
            "type": "query-result", "conversation": "one", "query": "status",
            "ref": "interaction-1", "text": "status: RUNNING",
        }], surface.of("query-result"))

    async def test_somebody_not_allowed_receives_no_gateway_information(self):
        """R-CH-23"""
        surface = Surface()
        held = self.answering(
            surface, Brain(), querying=lambda _asked: "private gateway state"
        )
        await held.heard(self.query(user="9999"))
        await self._settled(held)
        self.assertEqual([], surface.of("query-result"))


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

    async def test_a_running_turn_keeps_its_brain_and_the_next_uses_the_new_default(self):
        """R-AGT-31 — defaults are settled once when a turn is admitted."""
        agents.remember("ava", self.where, provider="a-brain", model="old",
                        settings={"effort": "high"})
        release = asyncio.Event()
        brain, surface = Brain(holds=release), Surface()
        held = self.answering(surface, brain)

        await held.heard(self.arrived(conversation="first"))
        await asyncio.wait_for(brain.started.wait(), timeout=1)
        agents.remember("ava", self.where, provider="new-brain",
                        replace_brain=True)
        release.set()
        await self._settled(held)
        await self.carry(held, self.arrived(conversation="second"))

        self.assertEqual(
            [("a-brain", "old", {"effort": "high"}),
             ("new-brain", None, {})],
            [(one["provider"], one["model"], one["settings"])
             for one in brain.asked])

    async def test_an_authorized_provider_command_changes_the_default_and_starts_fresh(self):
        """R-CH-26 — configuration is authorized, agent-wide, and session-safe."""
        self.keeping("one", "old-session", brain="a-brain")
        executable = self.where / "new-provider"
        executable.write_text("#!/bin/sh\n", encoding="utf-8")
        executable.chmod(0o755)
        surface = Surface()
        held = self.answering(surface, Brain())
        await held.heard({
            "type": "configure", "conversation": "one", "user": "2207",
            "provider": str(executable), "ref": "command-1",
        })
        await self._settled(held)
        self.assertEqual(str(executable), agents.chosen("ava", self.where)["provider"])
        self.assertIsNone(self.kept("one", brain="a-brain"))
        self.assertIn("next message starts fresh",
                      surface.of("configure-result")[0]["text"])

    async def test_a_stranger_cannot_change_the_provider(self):
        """R-CH-26 — seeing the command is not authority to change the agent."""
        surface = Surface()
        held = self.answering(surface, Brain())
        await held.heard({
            "type": "configure", "conversation": "one", "user": "9999",
            "provider": "claude", "ref": "command-1",
        })
        self.assertEqual("a-brain", agents.chosen("ava", self.where)["provider"])
        self.assertEqual([], surface.of("configure-result"))

    async def test_an_unrunnable_provider_is_reported_and_changes_nothing(self):
        """R-CH-26 — the private result reports refusal without corrupting the default."""
        agents.remember("ava", self.where, provider="a-brain", model="old-model",
                        settings={"effort": "high"})
        self.keeping("one", "old-a", brain="a-brain")
        self.keeping("one", "old-b", brain="other-brain")
        surface = Surface()
        held = self.answering(surface, Brain())
        await held.heard({
            "type": "configure", "conversation": "one", "user": "2207",
            "provider": "definitely-not-a-provider", "ref": "command-1",
        })
        await self._settled(held)
        self.assertEqual({
            "provider": "a-brain", "model": "old-model", "instructions": None,
            "settings": {"effort": "high"},
        }, agents.chosen("ava", self.where))
        self.assertEqual("old-a", self.kept("one", brain="a-brain"))
        self.assertEqual("old-b", self.kept("one", brain="other-brain"))
        result = surface.of("configure-result")
        self.assertEqual("command-1", result[0]["ref"])
        self.assertIn("not changed", result[0]["text"])

    async def test_provider_change_waits_for_the_old_turn_then_starts_fresh(self):
        """R-CH-26 — post-change words never steer the old provider."""
        release = asyncio.Event()
        executable = self.where / "new-provider"
        executable.write_text("#!/bin/sh\n", encoding="utf-8")
        executable.chmod(0o755)
        self.keeping("one", "old-a", brain="a-brain")
        self.keeping("one", "old-b", brain=str(executable))
        sessions_seen = []

        class KeepsIts(Brain):
            async def __call__(mine, name, prompt, named, **how):
                records = agents.records("ava", how["where"])
                conversation = store.conversation_id(how["on"], how["conversation"])
                sessions_seen.append(records.session(conversation, named))
                said = await super().__call__(name, prompt, named, **how)
                records.remember_session(conversation, named, f"new-{len(mine.asked)}")
                return said

        brain, surface = KeepsIts(
            holds=release, can={"steer": True}), Surface()
        held = self.answering(surface, brain)
        await held.heard(self.arrived(text="before switch"))
        await asyncio.wait_for(brain.started.wait(), timeout=1)
        await held.heard({
            "type": "configure", "conversation": "one", "user": "2207",
            "provider": str(executable), "ref": "command-1",
        })
        await held.heard(self.arrived(text="after switch", ref="8842"))
        self.assertEqual([], brain.steered,
                         "post-change words were steered into the old provider")
        release.set()
        await self._settled(held)
        await asyncio.sleep(0.05)

        self.assertEqual(
            ["a-brain", str(executable)],
            [one["provider"] for one in brain.asked])
        self.assertEqual("after switch", self.words(brain.asked[1]["prompt"]))
        self.assertEqual(["old-a", None], sessions_seen)
        self.assertIsNone(self.kept("one", brain="a-brain"))

    async def test_a_shared_channels_members_cannot_change_agent_wide_defaults(self):
        """R-CH-26 — room membership is not agent administration."""
        record = {"kind": "somewhere", "allow": ["owner", "guest"], "settings": {}}
        brain, surface = Brain(), Surface()
        held = self.answering(surface, brain, record=record)
        await self.carry(held, self.arrived(user="guest"))
        self.assertEqual(1, len(brain.asked), "a permitted guest could not send a message")
        for user in ("owner", "guest"):
            await held.heard({
                "type": "configure", "conversation": "one", "user": user,
                "provider": "claude", "ref": f"command-{user}",
            })
        self.assertEqual("a-brain", agents.chosen("ava", self.where)["provider"])
        self.assertEqual([], surface.of("configure-result"))


class OneConversationIsOneSession(CarriesAConversation):
    """R-CH-3, R-CH-14 — a session of its own, found again afterwards."""

    async def test_each_conversation_keeps_a_session_of_its_own(self):
        """R-CH-3 — two threads answering into each other is the failure this prevents."""
        brain, surface = Brain(), Surface()
        held = self.answering(surface, brain)
        await self.carry(held, self.arrived(conversation="one"),
                         self.arrived(conversation="two"))
        self.assertEqual({"one", "two"}, {one["conversation"] for one in brain.asked})
        self.assertEqual({"ops"}, {one["on"] for one in brain.asked})

    async def test_a_conversation_is_named_so_two_channels_cannot_collide(self):
        """R-CH-3 — a thread called `general` on one surface and on another are two
        conversations, and one session handed to both is one of them answering wrongly.
        The surface is part of what names it, so this is not a rule anybody applies."""
        self.assertNotEqual(store.conversation_id("ops", "general"),
                            store.conversation_id("plans", "general"))

    async def test_a_conversations_session_is_found_again_after_a_restart(self):
        """R-CH-14 — the handle is kept where the agent keeps things, not in the channel,
        so a gateway coming back finds the conversation exactly where it left it."""
        self.keeping("one", "abc-123")
        brain, surface = Brain(), Surface()
        # A second Answering entirely, which is what a restart is.
        held = self.answering(surface, brain)
        await self.carry(held, self.arrived())
        self.assertEqual("abc-123", self.kept("one"))

    async def test_forgetting_while_a_turn_runs_is_not_undone_when_it_ends(self):
        """R-CH-10 — the ordinary way somebody uses it, and the one that did not work.

        Forgetting ends no turn: a person asking to start again is not asking to throw
        away the answer they are waiting for. But a turn already running writes down
        where it got to when it ends, and that lands *after* the forgetting — so the
        session came back a few seconds later, put there by the very turn the gesture
        deliberately did not interrupt, and the next message carried on from the
        conversation somebody had just asked to leave. The gesture said it had worked
        and the store disagreed.
        """
        self.keeping("one", "abc-123")
        stop = asyncio.Event()

        class KeepsIts(Brain):
            """A turn that writes down where it got to, which every resumable one does."""

            async def __call__(self, name, prompt, named_, **how):
                said = await super().__call__(name, prompt, named_, **how)
                agents.records("ava", how["where"]).remember_session(
                    store.conversation_id(how["on"], how["conversation"]), "a-brain",
                    "handle-from-the-turn")
                return said

        brain, surface = KeepsIts(holds=stop), Surface()
        held = self.answering(surface, brain)
        await held.heard(self.arrived())
        await brain.started.wait()
        await held.heard({"type": "control", "conversation": "one", "user": "2207",
                          "control": "forget"})
        self.assertIsNone(self.kept("one"), "the gesture did not take effect at all")
        stop.set()
        await self._settled(held)
        await asyncio.sleep(0.05)
        self.assertIsNone(self.kept("one"),
                          "the turn put back a session the person had asked to be rid of")

    async def test_forgetting_a_conversation_starts_the_next_one_fresh(self):
        """R-CH-10 — and leaves every other conversation exactly as it was."""
        self.keeping("one", "abc-123")
        self.keeping("two", "def-456")
        brain, surface = Brain(), Surface()
        held = self.answering(surface, brain)
        await self.carry(held, {"type": "control", "conversation": "one", "user": "2207",
                                "control": "forget"})
        self.assertIsNone(self.kept("one"))
        self.assertEqual("def-456", self.kept("two"),
                         "forgetting one conversation took another with it")


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

    async def test_a_stop_ends_the_backlog_and_does_not_promote_the_next_message(self):
        """R-CH-9 — a turn ending starts whatever queued behind it, and a cancelled turn
        ends like any other, so a stop drained the queue instead of ending it: the agent
        went quiet for a beat and carried on with the next message. There was no way to
        actually stop — *n* waiting messages needed *n* stops, each racing the turn it had
        just started."""
        stop = asyncio.Event()
        brain, surface = Brain(holds=stop), Surface()
        held = self.answering(surface, brain)
        await held.heard(self.arrived(conversation="one", text="first"))
        await brain.started.wait()
        await held.heard(self.arrived(conversation="one", text="second"))
        await asyncio.sleep(0.02)
        await held.heard({"type": "control", "conversation": "one", "user": "2207",
                          "control": "stop"})
        await asyncio.sleep(0.1)
        self.assertEqual([channel.TAKEN, channel.RUNNING, channel.STOPPED], surface.states,
                         "the message waiting behind the stopped turn was started anyway")
        self.assertEqual([], held.exchanges["one"].waiting)
        stop.set()
        await self._settled(held)

    async def test_a_stop_leaves_another_conversations_backlog_alone(self):
        """R-CH-9 — the gesture is aimed at one conversation. Ending every backlog on the
        channel would make a stop in one room throw away what somebody had queued in
        another."""
        stop = asyncio.Event()
        brain, surface = Brain(holds=stop), Surface()
        held = self.answering(surface, brain)
        await held.heard(self.arrived(conversation="one", text="first"))
        await held.heard(self.arrived(conversation="two", text="first"))
        await asyncio.sleep(0.02)
        await held.heard(self.arrived(conversation="one", text="second"))
        await held.heard(self.arrived(conversation="two", text="second"))
        await asyncio.sleep(0.02)
        await held.heard({"type": "control", "conversation": "one", "user": "2207",
                          "control": "stop"})
        await asyncio.sleep(0.05)
        self.assertEqual([], held.exchanges["one"].waiting)
        self.assertEqual(1, len(held.exchanges["two"].waiting),
                         "a stop in one conversation dropped another's waiting message")
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
        self.assertEqual(["actually, stop at three"],
                         [self.words(one.text) for one in brain.steered])
        self.assertEqual(1, len(brain.asked), "it started a second turn as well")

    async def test_a_word_steered_into_a_running_turn_carries_who_said_it(self):
        """R-STO-27 — what a person says mid-turn is a message of its own and is written
        down as one, so it needs the identity the message that started the turn already
        carries. Reported (#106): the same person appeared throughout one conversation
        twice over — by their platform identity when they began a turn, and as the bare
        word `user` whenever they spoke into one already running."""
        stop = asyncio.Event()
        brain = Brain(holds=stop, can={"steer": True})
        held = self.answering(Surface(), brain)
        await held.heard(self.arrived(text="count to ten", user="2207"))
        await brain.started.wait()
        await asyncio.sleep(0.02)
        await held.heard(self.arrived(text="stop at three", user="2207"))
        await asyncio.sleep(0.02)
        stop.set()
        await self._settled(held)
        self.assertEqual(["2207"], [one.who for one in brain.steered],
                         "a word said into a running turn reached it unattributed")

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
        self.assertEqual(["first", "second"],
                         [self.words(one["prompt"]) for one in brain.asked])

    async def test_a_follow_up_offered_after_provider_input_closed_becomes_the_next_turn(self):
        """R-CH-25 — a provider may finish accepting input before the outer turn finishes
        publishing. Words offered in that window must not disappear into its dead queue."""
        finish = asyncio.Event()

        class InputAlreadyClosed(Brain):
            async def __call__(self, name, prompt, named, **how):
                self.asked.append({"name": name, "prompt": prompt, "provider": named, **how})
                how["admitted"](self.outcome.run, {"steer": True})
                self.started.set()
                # The provider's input consumer is already gone, while the outer carry
                # still has answer cleanup left to do.
                await finish.wait()
                return self.outcome

        brain, surface = InputAlreadyClosed(), Surface()
        held = self.answering(surface, brain)
        await held.heard(self.arrived(text="first"))
        await brain.started.wait()
        await held.heard(self.arrived(text="must not be lost"))
        finish.set()
        await self._settled(held)
        await asyncio.sleep(0.05)
        await self._settled(held)
        self.assertEqual(
            ["first", "must not be lost"],
            [self.words(one["prompt"]) for one in brain.asked],
        )

    async def test_a_burst_arriving_before_the_turn_is_admitted_still_steers_it(self):
        """R-CH-9 — whether a brain can be steered is not known until the turn is
        admitted, and somebody typing quickly is faster than that. Held until the answer
        comes back, the first message of every burst steered and the rest became turns of
        their own — which is one conversation answered twice over."""
        stop = asyncio.Event()
        brain = Brain(holds=stop, can={"steer": True})
        surface = Surface()
        held = self.answering(surface, brain)
        # No await between them: the second lands while the first is still being admitted.
        await held.heard(self.arrived(text="first"))
        await held.heard(self.arrived(text="and also this"))
        await held.heard(self.arrived(text="and this"))
        await asyncio.sleep(0.05)
        stop.set()
        await self._settled(held)
        self.assertEqual(1, len(brain.asked), "a burst became several turns")
        self.assertEqual(["and also this", "and this"],
                         [self.words(one.text) for one in brain.steered])

    async def test_the_mark_stays_on_the_message_that_asked(self):
        """R-DIS-8 — a second message sent while a turn runs took the mark that belonged
        to the message that asked for it, so the wrong one was ticked as answered."""
        stop = asyncio.Event()
        brain = Brain(holds=stop, can={"steer": True})
        surface = Surface()
        held = self.answering(surface, brain)
        await held.heard(self.arrived(text="first", ref="8841"))
        await asyncio.sleep(0.05)
        await held.heard(self.arrived(text="second", ref="9999"))
        await asyncio.sleep(0.02)
        stop.set()
        await self._settled(held)
        marked = [one.get("ref") for one in surface.of("state") if one.get("ref")]
        self.assertEqual({"8841"}, set(marked),
                         f"a mark landed on a message that did not ask for the turn: {marked}")

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
        self.assertEqual([("ops", "one"), ("ops", "one")],
                         [(one["on"], one["conversation"]) for one in brain.asked])


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

    async def test_a_final_answer_names_the_provider_that_produced_it(self):
        """R-CH-28 — provenance is Rundesk's fact, not optional brain metadata."""
        surface = Surface()
        held = self.answering(surface, Brain())
        await self.carry(held, self.arrived())
        self.assertEqual("a-brain", surface.of("answer")[0]["provider"])

    async def test_how_big_the_conversation_is_reaches_a_surface_with_what_it_cost(self):
        """R-USE-15, R-CH-13 — the field is named here or it never leaves, and a footer
        showing it would be dead the day it was written. A brain's own bookkeeping around
        it still stays where it was said."""
        brain = Brain(showing=[{"type": "usage", "input": 2, "output": 837,
                                "cached": 121446, "session": 122435,
                                "prompt_cache_key": "a private key"}])
        surface = Surface()
        held = self.answering(surface, brain)
        await self.carry(held, self.arrived())
        shown = surface.of("usage")[0]
        self.assertEqual(122435, shown["session"])
        self.assertNotIn("prompt_cache_key", shown)

    async def test_what_a_brain_wrote_into_its_cache_reaches_a_surface_too(self):
        """R-CH-13, R-USE-13 — the fourth quantity a turn is billed for, and the one that
        bills above fresh input. Discord has named `written` as the fourth slot of its
        footer since v0.17.0 and could never once be given it, because this allowlist did
        not name it: both suites green, nothing raised, nothing logged, and an owner shown
        three of the four quantities they paid for."""
        brain = Brain(showing=[{"type": "usage", "input": 2, "output": 88,
                                "cached": 34200, "written": 1500,
                                "prompt_cache_key": "a private key"}])
        surface = Surface()
        held = self.answering(surface, brain)
        await self.carry(held, self.arrived())
        shown = surface.of("usage")[0]
        self.assertEqual(1500, shown["written"],
                         "cache writes still do not cross the seam")
        self.assertNotIn("prompt_cache_key", shown)

    async def test_a_safe_helper_name_leaves_but_unrelated_tool_fields_do_not(self):
        """R-CH-13 — a helper name is deliberately allowed; provider extras stay private."""
        brain = Brain(showing=[
            {
                "type": "tool", "id": "helper-1", "name": "subAgentActivity",
                "did": "delegate", "who": "senior_code_reviewer",
                "prompt": "private helper instructions", "agentPath": "/root/private",
            },
            {
                "type": "tool", "id": "run-1", "name": "Bash",
                "did": "run", "who": "private path",
            },
        ])
        surface = Surface()
        held = self.answering(surface, brain)
        await self.carry(held, self.arrived())
        shown = surface.of("tool")[0]
        self.assertEqual("senior_code_reviewer", shown["who"])
        self.assertNotIn("prompt", shown)
        self.assertNotIn("agentPath", shown)
        self.assertNotIn("who", surface.of("tool")[1])

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

    async def test_a_surface_told_not_to_show_what_it_is_doing_still_answers(self):
        """R-CH-6 — everything a turn shows on the way is what an owner may turn off, and
        the answer is not. Turning that off too would be a channel that takes a message and
        never replies to it, which is not a quieter agent but a broken one."""
        brain = Brain(showing=[{"type": "think", "text": "the error is in the parser"},
                               {"type": "tool", "id": "1", "did": "run"},
                               {"type": "usage", "input": 10, "output": 2}])
        surface = Surface()
        held = self.answering(surface, brain, record=dict(self.record, activity=False))
        await self.carry(held, self.arrived())
        kinds = [one["type"] for one in surface.shown]
        self.assertEqual([], [one for one in kinds if one in ("think", "tool", "usage")],
                         "a surface told not to be shown what it was doing was shown it")
        self.assertIn("answer", kinds, "turning activity off took the answer with it")

    async def test_a_quiet_channel_posts_one_message_for_the_whole_turn(self):
        """R-CH-27, R-CH-6 — the regression. A turn that thinks out loud four times posted
        four remarks and then the answer into a room explicitly set to stay quiet, because
        prose was routed on before the owner's choice was ever asked. Only the marks a
        platform shows without posting anything — how the turn stands — are left."""
        brain = Brain(showing=[
            {"type": "text", "text": "I'll read the issue.", "whole": True},
            {"type": "text", "text": "Now the code.", "whole": True},
            {"type": "text", "text": "The routing is the cause.", "whole": True},
            {"type": "text", "text": "Writing the fix.", "whole": True},
            {"type": "think", "text": "the error is in the parser"},
            {"type": "text", "text": "Done: one line.", "whole": True}],
            outcome=Outcome(text="Done: one line."))
        surface = Surface()
        held = self.answering(surface, brain, record=dict(self.record, activity=False))
        await self.carry(held, self.arrived())
        posted = [one["type"] for one in surface.shown if one["type"] != "state"]
        self.assertEqual(["answer"], posted,
                         f"a channel told to stay quiet posted {posted}")
        self.assertEqual(["Done: one line."],
                         [one["text"] for one in surface.of("answer")],
                         "the one message it posted was not the answer")

    async def test_what_a_quiet_channel_says_at_the_end_is_still_only_its_last_thought(self):
        """R-CH-27, R-CH-19 — what is said is still collected when none of it is posted.
        Dropping the record instead of the delivery would make the answer every thought
        the turn ever had, joined together — the room quieter and the message four times
        longer, which is the opposite of what was asked for."""
        brain = Brain(showing=[
            {"type": "text", "text": "I'll read the issue.", "whole": True},
            {"type": "text", "text": "Three files changed.", "whole": True}],
            outcome=Outcome(text="I'll read the issue.Three files changed."))
        surface = Surface()
        held = self.answering(surface, brain, record=dict(self.record, activity=False))
        await self.carry(held, self.arrived())
        self.assertEqual(["Three files changed."],
                         [one["text"] for one in surface.of("answer")])

    async def test_a_quiet_channels_reply_written_a_piece_at_a_time_still_arrives_whole(self):
        """R-CH-27, R-CH-7 — a brain that streams fragments and never marks one whole has
        said nothing complete until it stops, and the pieces are still what the answer is
        made of on a channel that posts nothing before it."""
        brain = Brain(showing=[{"type": "text", "text": "Three "},
                               {"type": "text", "text": "files changed."}],
                      outcome=Outcome(text="Three files changed."))
        surface = Surface()
        held = self.answering(surface, brain, record=dict(self.record, activity=False))
        await self.carry(held, self.arrived())
        self.assertEqual([], surface.of("said"))
        self.assertEqual(["Three files changed."],
                         [one["text"] for one in surface.of("answer")])

    async def test_a_channel_shown_what_it_is_doing_still_hears_every_thought(self):
        """R-CH-6, R-CH-19 — the other half of the choice, and the one nobody asked to
        change. A room that is watching a long turn is readable because each finished
        thought arrives when it was had."""
        brain = Brain(showing=[
            {"type": "text", "text": "I'll read the issue.", "whole": True},
            {"type": "text", "text": "Now the code.", "whole": True},
            {"type": "text", "text": "Done: one line.", "whole": True}],
            outcome=Outcome(text="Done: one line."))
        surface = Surface()
        held = self.answering(surface, brain)
        await self.carry(held, self.arrived())
        self.assertEqual(["I'll read the issue.", "Now the code."],
                         [one["text"] for one in surface.of("said")])
        self.assertEqual(["Done: one line."],
                         [one["text"] for one in surface.of("answer")])

    async def test_a_finished_thing_said_mid_turn_is_shown_when_the_next_one_arrives(self):
        """R-CH-19 — an agent that says "I will look at the logs" and then, a minute
        later, what it found is writing the way a person does. Both arriving at once
        loses the first one's whole purpose."""
        brain = Brain(showing=[
            {"type": "text", "text": "I'll look at the logs.", "whole": True},
            {"type": "text", "text": "Three files changed.", "whole": True}],
            outcome=Outcome(text="I'll look at the logs.Three files changed."))
        surface = Surface()
        held = self.answering(surface, brain)
        await self.carry(held, self.arrived())
        self.assertEqual(["I'll look at the logs."],
                         [one["text"] for one in surface.of("said")])
        self.assertEqual(["Three files changed."],
                         [one["text"] for one in surface.of("answer")],
                         "the last thing it said was not the answer")

    async def test_one_turn_never_repeats_what_the_last_one_ended_on(self):
        """R-CH-19 — what a turn ends on is in hand when it finishes, and was still in
        hand when the next turn began: the first thing said in the second turn pushed the
        first turn's answer out as a remark, so every turn after the first posted a
        message too many, quoting itself from a minute ago."""
        brain = Brain(showing=[{"type": "text", "text": "First answer.", "whole": True}],
                      outcome=Outcome(text="First answer."))
        surface = Surface()
        held = self.answering(surface, brain)
        await self.carry(held, self.arrived(text="one"))
        await self.carry(held, self.arrived(text="two"))
        await asyncio.sleep(0.05)
        await self._settled(held)
        self.assertEqual([], surface.of("said"),
                         f"a turn repeated the last one: {surface.of('said')}")
        self.assertEqual(["First answer.", "First answer."],
                         [one["text"] for one in surface.of("answer")])

    async def test_only_one_finished_thing_said_is_all_answer_and_no_remark(self):
        """R-CH-19 — the ordinary turn. One message means there is nothing to show early
        and nothing is invented to fill the gap."""
        brain = Brain(showing=[{"type": "text", "text": "Three files.", "whole": True}],
                      outcome=Outcome(text="Three files."))
        surface = Surface()
        held = self.answering(surface, brain)
        await self.carry(held, self.arrived())
        self.assertEqual([], surface.of("said"))
        self.assertEqual(["Three files."], [one["text"] for one in surface.of("answer")])

    async def test_a_reply_written_a_piece_at_a_time_is_still_held_to_the_end(self):
        """R-CH-7 — a brain that streams fragments says nothing finished until it stops,
        and showing one is showing a sentence that changes under whoever is reading."""
        brain = Brain(showing=[{"type": "text", "text": "Three "},
                               {"type": "text", "text": "files changed."}],
                      outcome=Outcome(text="Three files changed."))
        surface = Surface()
        held = self.answering(surface, brain)
        await self.carry(held, self.arrived())
        self.assertEqual([], surface.of("said"), "a half-written reply was shown")
        self.assertEqual(["Three files changed."],
                         [one["text"] for one in surface.of("answer")])

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


class WhenTheChannelGoesAway(CarriesAConversation):
    """R-CH-11 — a channel leaves nothing running once it is gone."""

    async def test_a_turn_waiting_behind_another_never_starts_during_a_shutdown(self):
        """R-CH-11 — a turn ending is what starts the next, and that happens inside the
        cancelling. So the last turn's cancellation started a new one, after the caller
        had been told everything had stopped, and a brain went on working for a channel
        already reported gone."""
        stop = asyncio.Event()
        brain, surface = Brain(holds=stop), Surface()
        held = self.answering(surface, brain)
        await held.heard(self.arrived(text="first"))
        await brain.started.wait()
        await held.heard(self.arrived(text="second"))   # waits behind the first
        self.assertEqual(1, len(held.exchanges["one"].waiting))

        await held.stop()
        await asyncio.sleep(0.1)
        self.assertEqual(1, len(brain.asked),
                         f"a turn began after everything was stopped: {brain.asked}")

    async def test_nothing_of_this_channels_is_still_running_afterwards(self):
        """R-CH-11 — however many conversations were carrying one."""
        stop = asyncio.Event()
        brain, surface = Brain(holds=stop), Surface()
        held = self.answering(surface, brain)
        for one in ("a", "b", "c"):
            await held.heard(self.arrived(conversation=one))
        await asyncio.sleep(0.05)
        await held.stop()
        left = [it.conversation for it in held.exchanges.values()
                if it.task is not None and not it.task.done()]
        self.assertEqual([], left, f"still running: {left}")


class WhatAChannelHoldsForWeeks(CarriesAConversation):
    """R-CAD-6 — a channel is held open for as long as the agent is up, so anything that
    only ever grows is a leak measured in weeks."""

    async def test_conversations_do_not_pile_up_without_end(self):
        """A thread opened once in March still had an entry in July. Everything else here
        that accumulates over a gateway's life is bounded; this was not."""
        brain, surface = Brain(), Surface()
        held = self.answering(surface, brain)
        for i in range(answering.CONVERSATIONS + 20):
            await self.carry(held, self.arrived(conversation=f"c{i}"))
        self.assertLessEqual(len(held.exchanges), answering.CONVERSATIONS)

    async def test_a_conversation_with_a_turn_running_is_never_dropped(self):
        """The bound must not be able to take a conversation out from under the turn it
        is carrying — that is a live answer nobody would ever receive."""
        stop = asyncio.Event()
        brain, surface = Brain(holds=stop), Surface()
        held = self.answering(surface, brain)
        await held.heard(self.arrived(conversation="busy"))
        await brain.started.wait()
        for i in range(answering.CONVERSATIONS + 5):
            held.exchanges.setdefault(f"c{i}", answering.Exchange(f"c{i}"))
        held._make_room()
        self.assertIn("busy", held.exchanges, "it dropped a conversation that was working")
        stop.set()
        await self._settled(held)

    async def test_forgetting_a_conversation_here_costs_nothing(self):
        """Where a conversation got to lives in the agent's own record, found again by
        name — so dropping what is held for it is bookkeeping, never data."""
        self.keeping("one", "abc-123")
        brain, surface = Brain(), Surface()
        held = self.answering(surface, brain)
        await self.carry(held, self.arrived(conversation="one"))
        held.exchanges.clear()
        await self.carry(held, self.arrived(conversation="one", text="and now?"))
        self.assertEqual("abc-123", self.kept("one"))


class WhatTheAgentMade(CarriesAConversation):
    """R-CH-18 — a brain that makes something, and a surface that can send it.

    Nothing could be sent at all until a brain had a way to say it had made one: it drew
    a picture, said "here it is", and a surface showed the sentence and not the picture.
    """

    def _made(self, name="chart.png", inside=True):
        whose = agents.paths("ava", self.where)
        at = (whose["workspace"] if inside else self.where) / name
        at.parent.mkdir(parents=True, exist_ok=True)
        at.write_bytes(b"not really a picture")
        return at

    async def test_what_the_agent_made_is_sent_from_where_it_works(self):
        """R-CH-18 — named by the brain, checked here, handed to the surface."""
        at = self._made()
        brain = Brain(outcome=Outcome(text="here it is",
                                      files=[{"type": "file", "at": str(at)}]))
        surface = Surface()
        held = self.answering(surface, brain)
        await self.carry(held, self.arrived())
        sent = surface.of("answer")[0]["attachments"]
        # Compared resolved: a scratch directory reaches this machine through a symlink,
        # and what is sent is the real path rather than the way it was named.
        self.assertEqual(1, len(sent))
        self.assertEqual("chart.png", sent[0]["name"])
        self.assertEqual(at.resolve(), Path(sent[0]["at"]))

    async def test_a_file_outside_where_the_agent_works_is_not_sent(self):
        """R-CH-18 — a brain runs as the owner and can read anything they can, so "the
        brain asked for it" is not on its own a reason to put a file in a chat room."""
        at = self._made("secrets.txt", inside=False)
        brain = Brain(outcome=Outcome(text="here", files=[{"type": "file", "at": str(at)}]))
        surface = Surface()
        held = self.answering(surface, brain)
        await self.carry(held, self.arrived())
        self.assertEqual([], surface.of("answer")[0]["attachments"])
        self.assertTrue(any("outside where this agent works" in one for one in self.told),
                        "it refused silently")

    async def test_a_file_a_brain_never_made_is_not_invented(self):
        """R-CH-18 — a path that is not there is not a file, however confidently it was
        named, and nothing is guessed from what a tool happened to print."""
        brain = Brain(outcome=Outcome(text="here", files=[
            {"type": "file", "at": "/no/such/thing.png"},
            {"type": "file", "at": "relative.png"},
            {"type": "file"}]))
        surface = Surface()
        held = self.answering(surface, brain)
        await self.carry(held, self.arrived())
        self.assertEqual([], surface.of("answer")[0]["attachments"])

    async def test_a_turn_that_only_made_something_still_arrives(self):
        """R-CH-8, R-CH-18 — a picture with no words is an answer."""
        at = self._made()
        brain = Brain(outcome=Outcome(text="", files=[{"type": "file", "at": str(at)}]))
        surface = Surface()
        held = self.answering(surface, brain)
        await self.carry(held, self.arrived())
        self.assertEqual(1, len(surface.of("answer")), "the picture was never sent")


class InterruptedTurnsContinue(CarriesAConversation):
    def interrupted(self, session=True) -> str:
        kept = agents.records("ava", self.where)
        conversation = store.conversation_id("ops", "one")
        kept.opened(conversation, "ops", "somewhere", "one", AT)
        asked = kept.arrived(conversation, AT, "finish the release", who="2207")
        run = kept.began(
            "channel", "a-brain", "safe", AT, conversation_id=conversation,
            trigger_message_id=asked, model="gpt-5", can={"resume": True},
            settings={"effort": "high"},
        )
        if session:
            kept.remember_session(conversation, "a-brain", "thread-1180")
        kept.interrupted(
            run, store.stamped(), "the gateway stopped while this turn was running",
            recoverable=True,
        )
        return run

    async def test_a_successor_continues_the_interrupted_provider_session_once(self):
        """R-GW-22 — reconnecting resumes rather than replaying the original request."""
        interrupted = self.interrupted()
        brain, surface = Brain(outcome=Outcome(run="2-bbbb", text="released")), Surface()
        held = self.answering(surface, brain)

        await self.carry(held, {"type": "ready"})
        await self.carry(held, {"type": "ready"})

        self.assertEqual(1, len(brain.asked), "one interrupted turn was continued twice")
        asked = brain.asked[0]
        self.assertEqual(answering.CONTINUE, asked["prompt"])
        self.assertEqual(("a-brain", "gpt-5", {"effort": "high"}, "safe"),
                         (asked["provider"], asked["model"], asked["settings"],
                          asked["posture"]))
        self.assertTrue(asked["resume_required"])
        self.assertEqual("rundesk", asked["prompt_author"])
        self.assertEqual(["released"], [one["text"] for one in surface.of("answer")])
        raw = [one["raw"] for one in agents.reading("ava", self.where).records(interrupted)]
        self.assertIn(store.RECOVERY_CLAIMED, raw)
        self.assertIn(store.RECOVERED_BY + "2-bbbb", raw)

    async def test_an_interrupted_turn_without_a_session_gets_one_visible_failure(self):
        """R-GW-22 — unsafe replay is refused, but the original conversation is not silent."""
        self.interrupted(session=False)
        brain = Brain(raises=RuntimeError(
            "the interrupted turn could not be resumed because no provider session was saved"
        ))
        surface = Surface()
        held = self.answering(surface, brain)

        await self.carry(held, {"type": "ready"})
        await self.carry(held, {"type": "ready"})

        self.assertEqual(1, len(brain.asked), "the failed recovery was retried")
        failed = [one for one in surface.of("state") if one["state"] == "failed"]
        self.assertEqual(1, len(failed))
        self.assertIn("no provider session", failed[0]["why"])


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


class CompletedUpdateOutcome(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.data = Path(tempfile.mkdtemp(prefix="rundesk-update-data-"))
        self.addCleanup(shutil.rmtree, self.data, True)
        before = os.environ.get("RUNDESK_DATA_DIR")
        os.environ["RUNDESK_DATA_DIR"] = str(self.data)
        self.addCleanup(lambda: os.environ.__setitem__("RUNDESK_DATA_DIR", before)
                        if before is not None
                        else os.environ.pop("RUNDESK_DATA_DIR", None))
        config.ensure(self.data)

    async def test_a_completed_update_is_delivered_after_the_channel_reconnects(self):
        """R-UPD-40"""
        where = Path(tempfile.mkdtemp(prefix="rundesk-update-notice-"))
        self.addCleanup(shutil.rmtree, where, True)
        agents.add("ava", where)
        agents.remember("ava", where, provider="a-brain")
        records = agents.records("ava", where)
        records.opened(
            store.conversation_id("ops", "one"), "ops", "somewhere", "one", AT
        )
        surface = Surface()
        held = answering.Answering(
            "ava", "ops", {"kind": "somewhere", "allow": ["2207"]},
            surface, where=where, carry=Brain(),
        )
        held.connected = True
        await held.told_update_finished("one", "Rundesk update succeeded")
        self.assertEqual("Rundesk update succeeded", surface.of("said")[0]["text"])

    async def test_a_completed_update_resumes_its_originating_work_after_reconnect(self):
        """R-UPD-41"""
        where = Path(tempfile.mkdtemp(prefix="rundesk-update-continuation-"))
        self.addCleanup(shutil.rmtree, where, True)
        agents.add("ava", where)
        agents.remember("ava", where, provider="a-brain")
        agents.records("ava", where).opened(
            store.conversation_id("ops", "one"), "ops", "somewhere", "one", AT
        )
        brain, surface = Brain(), Surface()
        held = answering.Answering(
            "ava", "ops", {"kind": "somewhere", "allow": ["2207"]},
            surface, where=where, carry=brain,
        )
        held.connected = True

        await held.told_update_finished("one", "Rundesk update succeeded")

        self.assertEqual(1, len(brain.asked))
        self.assertEqual(answering.AFTER_UPDATE, brain.asked[0]["prompt"])
        self.assertEqual("rundesk", brain.asked[0]["prompt_author"])

    async def test_a_completed_restart_is_delivered_without_starting_another_turn(self):
        """R-GW-43"""
        where = Path(tempfile.mkdtemp(prefix="rundesk-restart-notice-"))
        self.addCleanup(shutil.rmtree, where, True)
        agents.add("ava", where)
        agents.remember("ava", where, provider="a-brain")
        agents.records("ava", where).opened(
            store.conversation_id("ops", "one"), "ops", "somewhere", "one", AT
        )
        brain, surface = Brain(), Surface()
        held = answering.Answering(
            "ava", "ops", {"kind": "somewhere", "allow": ["2207"]},
            surface, where=where, carry=brain,
        )
        held.connected = True

        await held.told_restart_finished("one", "Rundesk restart succeeded")

        self.assertEqual("Rundesk restart succeeded", surface.of("said")[0]["text"])
        self.assertFalse(surface.of("said")[0]["continues"])
        self.assertEqual([], brain.asked)


if __name__ == "__main__":
    unittest.main(verbosity=2)
