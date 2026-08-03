"""Discord, as an agent is reached on it — every row of channel-discord.

**Nothing here reaches Discord.** What is tested is the policy: which messages are for this
agent and where the answer goes, what a mark means, how an answer too long for one message
is broken up, and what each of the seam's records looks like once this surface has decided
how to show it. The wire itself — a socket, a rate limit, a permission — is what the canary
against a private server is for, and what a fake can never prove.

The adapter is loaded by path rather than imported as a module, because it is not one: it
is a program, which is the whole point of the seam. If `discord.py` is not installed the
whole file skips, since the adapter refuses to load without it and says so.

Run: python3 tests/test_discord.py
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import importlib.machinery
import importlib.util
import inspect
import io
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

#: The install's own virtualenv, exactly as the adapter finds it.
for _packages in sorted((ROOT / ".venv" / "lib").glob("python3.*/site-packages")):
    sys.path.insert(0, str(_packages))

#: The seam itself, because which fields reach this surface is decided there and rendered
#: here — and a list kept in two places is a list that disagrees with itself (R-CH-13).
from rundesk import answering, channel  # noqa: E402


def _adapter():
    """The adapter, loaded from its path — it is a program, not a module."""
    at = ROOT / "src" / "channels" / "discord"
    # **Asked before anything else, and on every machine.** Whether the file is there does not
    # depend on the dependency, so this is the one check that still fails where the skip is
    # legitimate — which is precisely where the adapter moving went unnoticed: CI runs with an
    # empty virtualenv, so a suite that only noticed a missing adapter when `discord.py` was
    # installed would have gone on skipping there for ever.
    if not at.is_file():
        raise RuntimeError(
            f"test_discord cannot find the adapter it tests at {at} — this is not a skip"
        )
    loader = importlib.machinery.SourceFileLoader("rundesk_discord", str(at))
    spec = importlib.util.spec_from_loader("rundesk_discord", loader)
    made = importlib.util.module_from_spec(spec)
    loader.exec_module(made)
    return made


#: Whether the one thing that may legitimately be missing is missing. **Asked of the
#: dependency itself, never inferred from how the adapter failed** — the adapter catches its
#: own absent import, says so as a record, and exits, so it never raises anything a caller
#: could tell apart from being broken. Reading its exception was exactly that mistake: CI
#: runs with an empty `.venv` on purpose, and a suite that turned that into "this is not a
#: skip" failed the build on the one machine the skip exists for.
try:  # pragma: no cover - the presence of a dependency is not a branch worth covering
    import discord as _installed
except ModuleNotFoundError:
    _installed = None

try:
    discord = _adapter()
except BaseException as why:  # pragma: no cover - proved by the install
    if _installed is None:
        # A machine without `discord.py` is a real configuration and skipping there is honest.
        discord = None
        WHY = "discord.py is not installed — run ./install.sh"
    else:
        # **Anything else is this suite being broken, and it must say so.** The adapter moved
        # in the src restructure and this went on loading it from where it used to be: every
        # case skipped, the file was never opened, and the gate said `ok` for months of
        # commits. A skip and a pass read identically, so the only defence is refusing to
        # skip for a reason that is not the one skipping is for.
        raise RuntimeError(
            f"test_discord cannot load the adapter it tests, which is not a skip: {why}"
        ) from why


@unittest.skipIf(discord is None, "discord.py is not installed — run ./install.sh")
class WhoItAnswers(unittest.TestCase):
    """R-DIS-1 to R-DIS-4 — the five cases, and the two that are easy to get wrong."""

    def test_being_named_in_a_server_channel_opens_a_thread(self):
        """R-DIS-1 — the turn happens in the thread, so one thread is one conversation."""
        self.assertEqual("open-thread", discord.where_to_answer(
            direct=False, in_thread=False, ours=False, mentioned=True))

    def test_an_agent_stays_silent_in_a_shared_channel_until_it_is_named(self):
        """R-DIS-2 — an agent that answered everything said in a shared room would be
        answering conversations it was never part of."""
        self.assertEqual("ignore", discord.where_to_answer(
            direct=False, in_thread=False, ours=False, mentioned=False))

    def test_inside_a_thread_it_opened_it_answers_without_being_named(self):
        """R-DIS-3 — the thread *is* the conversation, so naming it again in its own
        thread would be a thing nobody would think to do."""
        self.assertEqual("here", discord.where_to_answer(
            direct=False, in_thread=True, ours=True, mentioned=False))

    def test_it_does_not_answer_in_somebody_elses_thread_unless_named(self):
        """R-DIS-2, R-DIS-3 — the first of the two easy mistakes: a thread somebody else
        opened is somebody else's conversation."""
        self.assertEqual("ignore", discord.where_to_answer(
            direct=False, in_thread=True, ours=False, mentioned=False))

    def test_named_inside_a_thread_it_answers_there_rather_than_opening_another(self):
        """R-DIS-1 — the second easy mistake. Threads do not nest, and an agent that
        opened one to say it had stopped would be worse than one that said nothing."""
        self.assertEqual("here", discord.where_to_answer(
            direct=False, in_thread=True, ours=False, mentioned=True))

    def test_in_a_one_to_one_conversation_it_answers_where_it_was_spoken_to(self):
        """R-DIS-4 — nobody else is there, and there is nowhere to put a thread."""
        self.assertEqual("here", discord.where_to_answer(
            direct=True, in_thread=False, ours=False, mentioned=False))


@unittest.skipIf(discord is None, "discord.py is not installed — run ./install.sh")
class WhereItListens(unittest.TestCase):
    """R-DIS-1, R-DIS-4 — the places an owner said this agent may be reached."""

    def test_a_thread_belongs_to_the_channel_it_was_opened_in(self):
        """R-DIS-1 — asked by the thread's own id, the restriction matched nothing and
        was skipped for every thread in the server, so an agent told to listen in one
        channel would answer in a thread under any of them. A thread is where the
        conversations under a channel happen, and it is confined with it."""
        self.assertTrue(discord.within(False, belongs_to="1180",
                                       listens_in="1180", dms=False))
        self.assertFalse(discord.within(False, belongs_to="9999",
                                        listens_in="1180", dms=False),
                         "a thread under another channel was answered in")

    def test_an_agent_confined_to_a_server_and_no_further_answers_anywhere_in_it(self):
        """R-DIS-2 — naming a server and no channel is a choice, not an omission."""
        self.assertTrue(discord.within(False, belongs_to="9999", listens_in=None,
                                       dms=False, a_server="9930"))

    def test_an_agent_pointed_at_direct_messages_answers_only_those(self):
        """R-DIS-2, R-CAD-15 — this was the other way while one `add` made one channel:
        a channel pointed at direct messages was then the *only* channel, and refusing a
        mention from the one person allowed to make it protected nobody. Now one `add`
        makes one channel per kind of place, the room has a channel of its own, and both
        matching means the agent answers the same message twice from two processes."""
        self.assertFalse(discord.within(False, belongs_to="9999", listens_in=None,
                                        dms=True, a_server=None),
                         "the direct-message channel also took a message in a room")
        self.assertTrue(discord.within(True, belongs_to=None, listens_in=None,
                                       dms=True, a_server=None))

    def test_naming_a_channel_still_narrows_it_to_that_channel(self):
        """R-DIS-2 — the point of naming one is an agent in this room and not the next
        one along, and that has to keep working."""
        self.assertTrue(discord.within(False, belongs_to="1180", listens_in="1180",
                                       dms=False, a_server="9930"))
        self.assertFalse(discord.within(False, belongs_to="9999", listens_in="1180",
                                        dms=False, a_server="9930"))

    def test_a_direct_message_is_answered_only_when_that_is_what_was_asked_for(self):
        """R-DIS-4 — a channel pointed at a room is not also a channel for private
        messages, and an agent answering both when told about one is answering
        somewhere its owner never put it."""
        self.assertTrue(discord.within(True, belongs_to=None, listens_in=None, dms=True))
        self.assertFalse(discord.within(True, belongs_to=None, listens_in="1180",
                                        dms=False))


@unittest.skipIf(discord is None, "discord.py is not installed — run ./install.sh")
class AnAnswerRepliesToTheQuestion(unittest.TestCase):
    """R-DIS-28 — an answer quotes the message that asked for it, unless that message is
    somewhere other than where the answer is going.

    **The stand-in message carries `channel.id` and nothing else**, because that is what a
    real one carries. A stand-in given an attribute discord.py has never had is how this
    went unnoticed: the guard asked for `channel_id`, every message answered `""`, and no
    answer rundesk has ever posted was a reply."""

    class Room:
        """A place to write in, remembering only what it was asked to quote.

        It carries `id` because a real channel does, and because that is what the guard
        compares an anchor against: the room resolved for this write, which is the only
        thing a delivery routed by a place name has to go on."""

        def __init__(self, id):
            self.id = id
            self.quoted = []

        async def send(self, content, reference=None, mention_author=False, files=None):
            self.quoted.append(getattr(reference, "message", reference))
            return SimpleNamespace(id=99)

    class Forgetful:
        """A room that has forgotten the message being quoted, which is what Discord does
        when the asker deleted their question: it refuses the whole message rather than the
        quote alone, unless the reference says not to.

        It carries `id` because a real channel does, so the guard above keeps the anchor and
        this case is about the refusal rather than about the guard."""

        def __init__(self, id):
            self.id, self.quoted, self.wrote = id, [], []

        async def send(self, content, reference=None, mention_author=False, files=None):
            if reference is not None and getattr(reference, "fail_if_not_exists", True):
                raise RuntimeError("400 Bad Request (error code: 10008): Unknown message")
            self.quoted.append(getattr(reference, "message", reference))
            self.wrote.append(content)
            return SimpleNamespace(id=99)

    class Turn:
        def __init__(self, room):
            self.room = room

        async def _where_to_write(self, it):
            return self.room

    @staticmethod
    def _message(where):
        """A message standing in a place — the shape of a real one, no more, down to the
        reference a real one hands over when it is asked to be quoted."""
        asking = SimpleNamespace(id=7, channel=SimpleNamespace(id=where))
        asking.to_reference = lambda fail_if_not_exists=True: SimpleNamespace(
            message=asking, fail_if_not_exists=fail_if_not_exists)
        return asking

    def _posted_to(self, conversation, anchor, room_is=None):
        room = self.Room(conversation if room_is is None else room_is)
        asyncio.run(discord.Agent._post(
            self.Turn(room), {"conversation": str(conversation)}, "the answer",
            anchor=anchor))
        return room.quoted

    def test_the_anchor_is_read_off_the_attribute_a_message_actually_has(self):
        """A `discord.Message` has no `channel_id`, so `getattr(anchor, "channel_id", "")`
        returned `""` for every message that ever passed through, `"" != conversation` was
        always true, and the anchor was discarded unconditionally. Asked of the installed
        library, because that is the fact the guard is wrong about."""
        self.assertFalse(hasattr(_installed.Message, "channel_id"),
                         "the guard may be read off channel_id after all")
        self.assertTrue(hasattr(_installed.Message, "channel"))
        self.assertIn("fail_if_not_exists",
                      inspect.signature(_installed.Message.to_reference).parameters,
                      "the installed discord.py cannot be told to keep a refused quote")

    def test_an_answer_in_a_direct_message_is_a_reply_to_the_message_that_asked(self):
        """R-DIS-28 — the conversation is the direct-message channel's id, which is where
        the asking message stands. Scheduled reports and answers interleave in a one-to-one
        conversation, and a reply is the only thing telling them apart."""
        asking = self._message(4242)
        self.assertEqual([asking], self._posted_to(4242, asking))

    def test_an_answer_in_a_channel_is_a_reply_to_the_message_that_asked(self):
        """R-DIS-28 — a turn already happening where the question was asked quotes it, so
        it is findable in a busy room."""
        asking = self._message(555)
        self.assertEqual([asking], self._posted_to(555, asking))

    def test_an_answer_still_arrives_when_the_message_it_quotes_is_gone(self):
        """R-DIS-1, R-DIS-28 — the asker deleting their own question during a turn that
        runs for minutes must not cost them the answer. discord.py builds the reference
        without `fail_if_not_exists`, so Discord's default applied and it refused the whole
        message: a short answer was lost outright and a split one lost the piece carrying
        its cost line — the shape this guard exists to close, through another door. Built
        with it off, the quote is what goes and the answer still arrives."""
        asking = self._message(555)
        room = self.Forgetful(555)
        asyncio.run(discord.Agent._post(
            self.Turn(room), {"conversation": "555"}, "the answer", anchor=asking))
        self.assertEqual(["the answer"], room.wrote,
                         "a quote Discord would not resolve took the answer with it")
        self.assertEqual([asking], room.quoted)

    def test_an_answer_does_not_quote_a_message_from_somewhere_else(self):
        """R-DIS-1, R-DIS-28 — Discord refuses a whole message that quotes one in another
        channel. So a turn in a thread ended with a ✅ on the question and no answer under
        it: the mark went on the message in the channel, which works, and the reply quoting
        that same message was rejected outright. Being named opens a thread, so the
        conversation is the thread while the question stands in the parent."""
        asking = self._message(555)
        self.assertEqual([None], self._posted_to(90001, asking),
                         "an answer still quotes a message outside the place it is sent")

    def test_an_anchor_is_kept_for_the_room_being_written_in_not_the_one_named(self):
        """R-DIS-30 — a schedule reporting into a place rundesk has never seen a word in sends
        the word and no conversation at all, because only this surface can find that room. The
        guard compared the anchor against the conversation, so the one delivery whose notice
        most needed quoting was the one that dropped it."""
        notice = self._message(777)
        self.assertEqual([notice], self._posted_to(None, notice, room_is=777))

    def test_only_the_first_piece_of_a_split_answer_carries_the_anchor(self):
        """R-DIS-13, R-DIS-28 — a quote on every piece buries what it is quoting."""
        quoted = []

        class Splitting:
            async def _post(self, it, text, anchor=None, **kw): quoted.append(anchor)
            def _stop_typing(self, held): pass
            def _no_longer_last(self, held): pass

        held = discord.Live()
        held.anchor = self._message(555)
        asyncio.run(discord.Agent._answer(
            Splitting(), {"type": "answer", "text": "\n".join(
                "line %d" % i for i in range(400))}, held))
        self.assertGreater(len(quoted), 1, "the answer was not long enough to split")
        self.assertEqual([held.anchor] + [None] * (len(quoted) - 1), quoted)


class _Wrote:
    """A room that remembers, for every message written into it, whether it was a reply and
    whether it told Discord to mention the person being replied to.

    Carries `id` because a real channel does, and because that is what the anchor guard
    compares an anchor against. What it hands back is shaped like a real posted message —
    `channel` and `to_reference` — because a schedule's start notice is held and then
    quoted by the report that follows it."""

    def __init__(self, id=4242, refusing=False, recipient=None):
        self.id, self.refusing = id, refusing
        self.wrote = []          # (content, whether it quoted, whether it mentioned)
        # Only `discord.DMChannel` carries a recipient, so setting one is how a room here
        # says it is one person's own — the same question `_a_direct_message` asks.
        if recipient is not None:
            self.recipient = recipient

    async def send(self, content, reference=None, mention_author=False, files=None):
        if self.refusing:
            raise RuntimeError("403 Forbidden (error code: 50013): Missing Permissions")
        self.wrote.append((content, reference is not None, mention_author))
        posted = SimpleNamespace(id=len(self.wrote), channel=self)
        posted.to_reference = lambda fail_if_not_exists=True: SimpleNamespace(
            message=posted, fail_if_not_exists=fail_if_not_exists)

        async def edit(content=None):
            return posted

        posted.edit = edit
        return posted

    @property
    def mentioned(self):
        # Any line may open with the tag, not only the first: the mention sits under the
        # stats line, because `-#` renders as subtext only at the start of a line.
        return [one or any(line.startswith("<@") for line in content.splitlines())
                for content, _quoted, one in self.wrote]


def _writing_surface(room, activity=None):
    """The adapter's whole writing side, with only the room it writes into replaced.

    Built here rather than as a class body because every method on it is the *real* one:
    what is under test is which of the messages this surface writes reaches Discord asking
    for a mention, and a stand-in `_post` would answer that question for itself."""

    class Surface:
        _post = discord.Agent._post
        told = discord.Agent.told
        _answer = discord.Agent._answer
        _state = discord.Agent._state
        _doing = discord.Agent._doing
        _paced = discord.Agent._paced
        _flush = discord.Agent._flush
        _holding = discord.Agent._holding
        _no_longer_last = discord.Agent._no_longer_last
        _stop_typing = discord.Agent._stop_typing

        def __init__(self):
            self.live, self.scheduled, self.seen, self.started = {}, {}, {}, {}
            self.chose = SimpleNamespace(
                activity=discord.POSTS if activity is None else activity)

        async def _where_to_write(self, it):
            return room

        async def _typing(self, it):
            return

        async def _react(self, it, held, mark, instead_of=None):
            return

    return Surface()


def _asking(where=4242):
    """A person's message, standing in a place — the shape of a real one and no more."""
    return AnAnswerRepliesToTheQuestion._message(where)


@unittest.skipIf(discord is None, "discord.py is not installed — run ./install.sh")
class TheAnswerMentionsWhoAsked(unittest.TestCase):
    """R-DIS-31 — a message that mentions you is drawn by *your own* Discord client with a
    tint across the whole row, which is a thing no bot can draw for itself. Applied to the
    answer alone, the thing an owner asked for is the only coloured thing on the page; tint
    the commentary too and nothing is tinted.

    Proved through the real `_post`, because `mention_author` is the whole requirement and a
    stand-in `_post` would be answering the question for itself."""

    @staticmethod
    def _answered(surface, text, held):
        asyncio.run(discord.Agent._answer(
            surface, {"type": "answer", "conversation": "4242", "text": text}, held))

    def _held(self, anchor=None, clock=None):
        held = discord.Live(clock=clock)
        held.anchor = anchor
        return held

    def test_an_answer_in_a_direct_message_mentions_the_person_who_asked(self):
        """R-DIS-28, R-DIS-31 — the reply is what carries the mention, so the answer is both
        a reply to the question and the one message in the conversation an owner's own client
        colours in."""
        room = _Wrote()
        self._answered(_writing_surface(room), "here is what I found",
                       self._held(_asking(4242)))
        self.assertEqual([("here is what I found", True, True)], room.wrote)

    def test_only_the_first_piece_of_a_split_answer_mentions_anybody(self):
        """R-DIS-13, R-DIS-31 — one reply is one notification however many messages it takes.
        Mentioning on every piece is five pings for one answer, which is worse than the
        undifferentiated wall this exists to fix."""
        room = _Wrote()
        whole = "\n".join("line %d" % i for i in range(400))
        self._answered(_writing_surface(room), whole, self._held(_asking(4242)))
        self.assertGreater(len(room.wrote), 1, "the answer was not long enough to split")
        self.assertEqual([True] + [False] * (len(room.wrote) - 1), room.mentioned)
        self.assertEqual(
            whole.replace("\n", ""),
            "".join(content for content, _q, _m in room.wrote).replace("\n", ""),
            "the answer was not delivered whole")

    def test_an_answer_attached_as_a_file_still_mentions_who_asked(self):
        """R-DIS-13, R-DIS-31 — past a certain length an answer is a document rather than a
        message, and the one line saying so is still the answer arriving."""
        room = _Wrote()
        self._answered(_writing_surface(room),
                       "x" * (discord.LIMIT * discord.ATTACH_AFTER + 1),
                       self._held(_asking(4242)))
        self.assertEqual([True], room.mentioned)
        self.assertIn("attached", room.wrote[0][0])

    def test_an_answer_with_no_message_to_reply_to_mentions_nobody(self):
        """R-DIS-31 — the mention follows the anchor. There is nobody to mention where there
        is no question being replied to, and a room must not be pinged by an answer nobody
        standing in it asked for."""
        room = _Wrote()
        self._answered(_writing_surface(room), "here is what I found", self._held(None))
        self.assertEqual([("here is what I found", False, False)], room.wrote)

    def test_an_answer_whose_question_is_in_another_room_mentions_nobody(self):
        """R-DIS-28, R-DIS-31 — being named in a channel opens a thread while the question
        stays in the channel above it, so the anchor is dropped rather than costing the whole
        message. A mention that outlived the reply carrying it would ping somebody with a
        message they cannot see the question for."""
        room = _Wrote(id=90001)
        self._answered(_writing_surface(room), "here is what I found",
                       self._held(_asking(555)))
        self.assertEqual([("here is what I found", False, False)], room.wrote)

    def test_a_remark_said_mid_turn_mentions_nobody(self):
        """R-CH-19, R-DIS-31 — a finished thought said while the work goes on is not the
        answer, and a turn that thought out loud four times would be four notifications
        before the reply arrived."""
        room = _Wrote()
        surface = _writing_surface(room)

        async def carry():
            await discord.Agent.told(surface, {
                "type": "said", "conversation": "4242", "text": "I'll look at the logs."})
            await asyncio.sleep(0)

        asyncio.run(carry())
        self.assertEqual([("I'll look at the logs.", False, False)], room.wrote)

    def test_a_scheduled_final_mentions_its_recipient_and_not_the_notice_author(self):
        """R-DIS-30, R-DIS-31, R-SCH-46, R-SCH-50 — the report replies to rundesk's own
        notice, so reply-author mentions would ping the bot. Its explicit authorized
        recipient gives the final answer the ordinary highlighted treatment instead."""
        room = _Wrote()
        surface = _writing_surface(room)

        async def carry():
            for one in (
                    {"type": "said", "schedule": "nightly", "began": True,
                     "text": "💻 Working on 'nightly' …"},
                    {"type": "usage", "schedule": "nightly",
                     "session": 122435, "output": 837},
                    {"type": "answer", "schedule": "nightly", "recipient": "2207",
                     "provider": "a-brain", "elapsed": 120,
                     "text": "nothing broke overnight"}):
                await discord.Agent.told(
                    surface, dict({"conversation": "4242"}, **one))
            await asyncio.sleep(0)

        asyncio.run(carry())
        (_notice, notice_quoted, _n), (found, report_quoted, _r) = room.wrote
        self.assertFalse(notice_quoted, "the notice quoted something of its own")
        self.assertTrue(report_quoted, "the report stopped replying to its notice")
        self.assertEqual(
            "-# a-brain · 122k session · 837 output · 2m elapsed\n"
            "<@2207> nothing broke overnight",
            found,
        )
        self.assertEqual([False, True], room.mentioned)

    def test_a_scheduled_final_mentions_nobody_in_a_direct_message(self):
        """R-DIS-31 — the tint picks one message out of a busy room, and a direct message is
        not one. Every message there is already the owner's, so the mention buys no attention
        and spends a notification to buy it. The report still replies to its own notice."""
        room = _Wrote(recipient=SimpleNamespace(id=2207))
        surface = _writing_surface(room)

        async def carry():
            for one in (
                    {"type": "said", "schedule": "nightly", "began": True,
                     "text": "💻 Working on 'nightly' …"},
                    {"type": "answer", "schedule": "nightly", "recipient": "2207",
                     "provider": "a-brain", "elapsed": 120,
                     "text": "nothing broke overnight"}):
                await discord.Agent.told(
                    surface, dict({"conversation": "4242"}, **one))
            await asyncio.sleep(0)

        asyncio.run(carry())
        (_notice, _nq, _nm), (found, report_quoted, _rm) = room.wrote
        self.assertTrue(report_quoted, "the report stopped replying to its notice")
        self.assertNotIn("<@", found, "a direct message was still mentioned")
        self.assertEqual(
            "-# a-brain · 2m elapsed\nnothing broke overnight", found)
        self.assertEqual([False, False], room.mentioned)

    def test_a_mention_sits_under_the_stats_line_rather_than_in_front_of_it(self):
        """R-DIS-17, R-DIS-31, R-DIS-33 — `-#` is Discord's subtext and renders only at the
        start of a line. In front of it the mention turned the provider-and-cost line into
        ordinary text with a stray `-#` in it, which is the opposite of what that line is
        for."""
        self.assertEqual(
            "-# a-brain · 2m elapsed\n<@2207> nothing broke overnight",
            discord._mentioning(
                "2207", "-# a-brain · 2m elapsed\nnothing broke overnight"))
        self.assertEqual(
            "<@2207> nothing broke overnight",
            discord._mentioning("2207", "nothing broke overnight"),
            "an answer with no stats line lost its mention")

    def test_a_scheduled_final_does_not_consume_a_newer_turn_in_its_room(self):
        """R-DIS-35, R-SCH-50 — unattended usage and presentation have their own state;
        a final arriving beside a newer interactive turn preserves that turn's anchor,
        cost, timer, and typing task."""
        room = _Wrote()
        surface = _writing_surface(room)
        interactive = discord.Live()
        interactive.anchor = _asking(4242)
        interactive.cost = "-# · 10k session · 20 output"
        interactive.started = 10.0
        typing = _Cancels()
        interactive.typing = typing
        surface.live["4242"] = interactive

        async def carry():
            surface.started["nightly"] = _asking(4242)
            await discord.Agent.told(surface, {
                "type": "usage", "conversation": "4242", "schedule": "nightly",
                "session": 122435, "output": 837,
            })
            await discord.Agent.told(surface, {
                "type": "answer", "conversation": "4242", "schedule": "nightly",
                "recipient": "2207", "text": "nothing broke overnight",
            })

        asyncio.run(carry())
        self.assertIs(interactive, surface.live["4242"])
        self.assertEqual(("-# · 10k session · 20 output", 10.0, typing),
                         (interactive.cost, interactive.started, interactive.typing))
        self.assertFalse(typing.cancelled)

    def test_the_commentary_and_the_mark_on_a_failure_mention_nobody(self):
        """R-DIS-20, R-DIS-31 — what the agent is doing while it works, and the line saying
        what failed, are both bookkeeping. Neither is the answer, so neither is coloured."""
        room = _Wrote()
        surface = _writing_surface(room)

        async def carry():
            await discord.Agent.told(surface, {
                "type": "think", "conversation": "4242", "text": "weighing it up"})
            await discord.Agent.told(surface, {
                "type": "state", "conversation": "4242", "state": "failed",
                "why": "the brain stopped answering"})
            await asyncio.sleep(0)

        asyncio.run(carry())
        self.assertGreaterEqual(len(room.wrote), 2, "neither message was written")
        self.assertNotIn(True, room.mentioned)

    def test_a_quiet_channel_still_posts_one_message_and_it_is_the_mentioned_answer(self):
        """R-CH-27, R-DIS-31 — an owner who asked not to be shown the work gets exactly one
        message for the turn. That message is the answer, so it is the one that mentions —
        the whole value of the tint is on the surface where there is least to tell apart."""
        room = _Wrote()
        surface = _writing_surface(room, activity=discord.OFF)
        held = surface.live.setdefault("4242", discord.Live())
        held.anchor = _asking(4242)

        async def carry():
            for one in ({"type": "think", "text": "weighing it up"},
                        {"type": "tool", "name": "Read"},
                        {"type": "answer", "text": "here is what I found"}):
                await discord.Agent.told(
                    surface, dict({"conversation": "4242"}, **one))
            await asyncio.sleep(0)

        asyncio.run(carry())
        self.assertEqual([("here is what I found", True, True)], room.wrote)

    def test_a_mentioned_answer_that_cannot_be_delivered_is_said_and_the_turn_goes_on(self):
        """R-CH-12, R-DIS-31 — a delivery that fails is written to our own stderr and the
        turn carries on. Asking for a mention is one more thing Discord may refuse, and it
        must not become the first way a refusal ends a turn."""
        room = _Wrote(refusing=True)
        said = io.StringIO()
        with contextlib.redirect_stderr(said):
            self._answered(_writing_surface(room), "here is what I found",
                           self._held(_asking(4242)))
        self.assertEqual([], room.wrote)
        self.assertIn("could not write", said.getvalue())
        self.assertIn("WARNING\t", said.getvalue())

    def test_a_successful_delivery_marks_its_diagnostic_as_routine(self):
        """R-GW-44 — stderr stays separate from protocol records while its severity is
        explicit for the gateway that keeps it."""
        room = _Wrote()
        surface = _writing_surface(room)
        said = io.StringIO()
        with contextlib.redirect_stderr(said):
            asyncio.run(discord.Agent.told(surface, {
                "type": "state", "state": "taken", "conversation": "4242",
            }))
            asyncio.run(discord.Agent._post(
                surface, {"conversation": "4242"}, "delivered"))
        self.assertIn(
            "INFO\ttold state/taken for 4242 (0 chars, 0 files)",
            said.getvalue(),
        )
        self.assertIn("INFO\twrote 9 chars and 0 files", said.getvalue())

    def test_a_message_nobody_asked_to_mention_does_not(self):
        """R-DIS-31 — `_post` is shared by every message this surface writes, so not
        mentioning is what it does unless a caller says otherwise. Written as a case because
        the default is the whole of what keeps the answer the only tinted thing."""
        room = _Wrote()
        asyncio.run(discord.Agent._post(
            _writing_surface(room), {"conversation": "4242"}, "-# ⚠ something went wrong",
            anchor=_asking(4242)))
        self.assertEqual([("-# ⚠ something went wrong", True, False)], room.wrote)


@unittest.skipIf(discord is None, "discord.py is not installed — run ./install.sh")
class AScheduledRunReportsUnderItsOwnNotice(unittest.TestCase):
    """R-DIS-30, R-SCH-46 — an owner scrolling a busy direct message sees that a schedule
    began, and sees what it found attached to the thing that began it rather than floating
    loose among answers to other questions.

    Held in memory for as long as the run is: a gateway that restarts mid-run takes the run
    with it, so there is no report left to anchor and nothing durable worth keeping."""

    class Saying:
        """Everything `told` reaches for on a `said` record, and nothing else."""

        def __init__(self):
            self.live: dict = {}
            self.started: dict = {}
            self.posted: list = []

        _holding = discord.Agent._holding if discord is not None else None

        def _stop_typing(self, held): pass

        def _no_longer_last(self, held): pass

        async def _flush(self, it, held): pass

        async def _typing(self, it): return

        async def _post(self, it, content, anchor=None, files=(), text_as=None):
            self.posted.append((content, anchor))
            return SimpleNamespace(id=len(self.posted))

    @staticmethod
    def _remark(text="what it found", **held) -> dict:
        return dict({"type": "said", "conversation": "4242", "text": text}, **held)

    def _said(self, *records):
        saying = self.Saying()

        async def carry():
            for one in records:
                await discord.Agent.told(saying, one)
            await asyncio.sleep(0)

        asyncio.run(carry())
        return saying

    def test_a_scheduled_report_is_a_reply_to_the_message_that_said_it_started(self):
        """R-DIS-30 — the pair is self-describing only if the second quotes the first."""
        saying = self._said(
            self._remark("💻 Working on 'nightly' …", schedule="nightly", began=True),
            self._remark("nothing broke overnight", schedule="nightly"))
        (_notice, first), (found, quoted) = saying.posted
        self.assertIsNone(first, "the notice quoted something of its own")
        self.assertEqual("nothing broke overnight", found)
        self.assertEqual(1, getattr(quoted, "id", None),
                         "the report was not a reply to the notice that started it")

    def test_a_report_for_a_schedule_nobody_announced_quotes_nothing(self):
        """R-DIS-30 — a program schedule says nothing when it starts and still says what it
        came to, and a gateway that restarted holds nothing. Both post plainly, which is what
        every scheduled report did before there were notices at all."""
        saying = self._said(self._remark("schedule 'tidy' finished", schedule="tidy"))
        self.assertEqual([("schedule 'tidy' finished", None)], saying.posted)

    def test_an_ordinary_remark_still_quotes_nothing(self):
        """R-CH-19, R-DIS-30 — a finished thought said mid-turn names no schedule, and quoting
        the question on every remark buries the question."""
        saying = self._said(self._remark("I'll look at the logs."))
        self.assertEqual([("I'll look at the logs.", None)], saying.posted)

    def test_a_notice_is_answered_once_and_never_by_the_next_firing(self):
        """R-DIS-30 — the same schedule fires again tomorrow. Left standing, its second report
        would quote a message from a run that finished a day earlier."""
        saying = self._said(
            self._remark("💻 Working on 'nightly' …", schedule="nightly", began=True),
            self._remark("nothing broke overnight", schedule="nightly"),
            self._remark("nothing broke again", schedule="nightly"))
        self.assertEqual([None, 1, None],
                         [getattr(one, "id", one) for _text, one in saying.posted])
        self.assertEqual({}, saying.started, "the notice was kept after it was answered")

    def test_a_notice_that_could_not_be_posted_is_not_held(self):
        """R-DIS-30 — `_post` hands back nothing when the platform refused, and holding that
        would make the report a reply to a message that is not there."""
        class Refusing(self.Saying):
            async def _post(self, it, content, anchor=None, files=(), text_as=None):
                self.posted.append((content, anchor))
                return None

        saying = Refusing()

        async def carry():
            await discord.Agent.told(saying, self._remark(
                "💻 Working on 'nightly' …", schedule="nightly", began=True))
            await asyncio.sleep(0)

        asyncio.run(carry())
        self.assertEqual({}, saying.started)

    def test_a_scheduled_report_still_arrives_when_its_notice_is_gone(self):
        """R-DIS-1, R-DIS-28, R-DIS-30 — the notice stands in the room for the length of the
        run, which is exactly the window an owner has to tidy it away. Discord refuses a whole
        message quoting one it cannot resolve, so a deleted notice would have taken the report
        with it — a dangling notice is bad and a lost report is worse. The reference is built
        with `fail_if_not_exists` off for every anchor there is, this one included: the quote
        is what goes, and what the run found still arrives.

        Through the real `_post` and the room that refuses the way Discord does, because what
        is under test is the reference this delivery builds rather than the record it came
        from."""
        notice = AnAnswerRepliesToTheQuestion._message(4242)
        room = AnAnswerRepliesToTheQuestion.Forgetful(4242)
        asyncio.run(discord.Agent._post(
            AnAnswerRepliesToTheQuestion.Turn(room),
            {"conversation": "4242", "schedule": "nightly"},
            "nothing broke overnight", anchor=notice))
        self.assertEqual(["nothing broke overnight"], room.wrote,
                         "a notice the owner deleted took the report down with it")
        self.assertEqual([notice], room.quoted)


@unittest.skipIf(discord is None, "discord.py is not installed — run ./install.sh")
class AnAnswerInAThread(unittest.TestCase):
    """R-DIS-1 — being named opens a thread and the turn happens there, while the message
    that asked stays in the channel above it."""

    def test_a_thread_is_a_conversation_of_its_own(self):
        """R-DIS-1, R-CH-3 — one thread is one conversation and one session, so the id a
        turn is carried under is the thread's and not the channel's."""
        self.assertEqual("open-thread", discord.where_to_answer(
            direct=False, in_thread=False, ours=False, mentioned=True))
        self.assertEqual("here", discord.where_to_answer(
            direct=False, in_thread=True, ours=True, mentioned=False))


@unittest.skipIf(discord is None, "discord.py is not installed — run ./install.sh")
class WhatAThreadIsCalled(unittest.TestCase):
    """R-DIS-1 — a thread an owner can find again in a sidebar."""

    def test_a_thread_is_named_for_what_was_asked(self):
        self.assertEqual("what changed today?", discord.thread_name("what changed today?"))

    def test_a_long_question_is_clipped_rather_than_refused(self):
        """Discord allows a hundred characters, and a name it refuses is a thread that
        never opens — so the turn would happen in the channel instead."""
        made = discord.thread_name("x" * 500)
        self.assertLessEqual(len(made), discord.THREAD_CHARS)

    def test_a_question_with_nothing_in_it_still_gets_a_name(self):
        """A thread with no name is one Discord refuses outright."""
        self.assertTrue(discord.thread_name("   \n  "))


@unittest.skipIf(discord is None, "discord.py is not installed — run ./install.sh")
class WhatOneAddIsAskedFor(unittest.TestCase):
    """R-CAD-15 — a bot knows which servers it is in, and is signed in by the time it
    answers `--check`. Requiring `--server` was asking somebody to copy a number out of a
    URL to answer a question the adapter could answer itself."""

    def test_naming_no_place_at_all_takes_both_kinds(self):
        self.assertEqual((True, True), discord.wanted(discord.options([])))

    def test_naming_only_direct_messages_leaves_the_rooms_out(self):
        self.assertEqual((True, False), discord.wanted(discord.options(["--dm"])))

    def test_naming_only_a_room_leaves_direct_messages_out(self):
        for narrowed in (["--server", "9930"], ["--channel", "1180"]):
            self.assertEqual((False, True), discord.wanted(discord.options(narrowed)),
                             f"{' '.join(narrowed)} took direct messages as well")

    def test_naming_both_takes_both(self):
        self.assertEqual((True, True),
                         discord.wanted(discord.options(["--dm", "--server", "9930"])))


@unittest.skipIf(discord is None, "discord.py is not installed — run ./install.sh")
class WhichChannelTakesAMessage(unittest.TestCase):
    """R-CAD-15 — one `add` makes one channel per kind of place, so exactly one of them
    may take any given message."""

    def test_one_message_in_a_room_is_taken_by_exactly_one_channel(self):
        """Both took it, so the agent answered twice from two processes, neither aware of
        the other. The direct-message channel used to answer anywhere it was invited,
        which was right while it was the only channel there was."""
        for_dms = discord.within(direct=False, belongs_to=1180, listens_in=None, dms=True)
        for_rooms = discord.within(direct=False, belongs_to=1180, listens_in=1180, dms=False)
        self.assertEqual([False, True], [for_dms, for_rooms])

    def test_a_direct_message_is_taken_by_the_direct_message_channel_only(self):
        self.assertTrue(discord.within(direct=True, belongs_to=None, listens_in=None,
                                       dms=True))
        self.assertFalse(discord.within(direct=True, belongs_to=None, listens_in=1180,
                                        dms=False))

    def test_a_room_channel_given_a_server_answers_in_every_room_of_it(self):
        """R-DIS-2, R-CAD-15 — a server is what a room channel is ordinarily pointed at,
        and 'rooms' means the rooms. Naming one is the narrowing, not the ordinary case:
        an agent in a server that answered in exactly one room of it would be an agent
        nobody could reach from the room they were already in."""
        for room in (1180, 9999, 4242):
            self.assertTrue(discord.within(direct=False, belongs_to=room, listens_in=None,
                                           dms=False, a_server="9930"),
                            f"it refused room {room} in the server it was given")

    def test_a_room_channel_still_answers_only_in_the_room_it_names(self):
        """R-DIS-2 — narrowing is what naming a place means, and a thread is asked about
        by the channel it was opened in."""
        self.assertFalse(discord.within(direct=False, belongs_to=9999, listens_in=1180,
                                        dms=False))


@unittest.skipIf(discord is None, "discord.py is not installed — run ./install.sh")
class WhereAMessageCameFrom(unittest.TestCase):
    """R-DIS-21, R-CH-21 — the agent was handed a snowflake, which told it nothing, so it
    answered a room of forty people in the voice it used for a direct message."""

    class Where:
        def __init__(self, name=None, identifier=None):
            self.name = name
            self.id = identifier

    class Thread(Where):
        pass

    class Message:
        def __init__(self, channel, server=None, shown=None, name="tim"):
            self.channel, self.guild = channel, server
            self.author = type("A", (), {"display_name": shown, "name": name})()

    def message(self, channel, server=None, **how):
        return WhereAMessageCameFrom.Message(channel, server, **how)

    def test_discord_says_which_room_and_which_person_a_message_came_from(self):
        at = self.message(self.Where("ops"), self.Where("Rundesk"), shown="Tim")
        self.assertEqual("#ops on the 'Rundesk' server", discord._place(at, False, False))
        self.assertEqual("Tim", discord._who(at))

    def test_a_server_with_no_name_to_show_is_not_shown_as_blank(self):
        """R-DIS-21 — fetched by id, a channel comes back attached to a guild that may not
        have been resolved to a name. '#development in ' with nothing after it reads like
        something went missing rather than like there was nothing to say."""
        at = self.message(self.Where("ops"), self.Where(None), shown="Tim")
        self.assertEqual("#ops", discord._place(at, False, False))
        blank = self.message(self.Where("ops"), self.Where(""), shown="Tim")
        self.assertEqual("#ops", discord._place(blank, False, False))

    def test_a_direct_message_is_named_as_one_rather_than_as_a_channel(self):
        """A direct message has no name and no server, and calling it '#None' would be
        rundesk telling the agent something untrue about where it is."""
        at = self.message(self.Where(), shown=None)
        self.assertEqual("a direct message", discord._place(at, True, False))
        self.assertEqual("tim", discord._who(at), "no display name is still a name")

    def test_a_thread_is_named_under_the_channel_it_was_opened_in(self):
        """A thread's own name says what the turn is about; the channel it hangs under is
        what says where in the server it is happening."""
        thread = self.Thread("what changed today?")
        thread.parent = self.Where("ops")
        at = self.message(thread, self.Where("Rundesk"), shown="Tim")
        self.assertEqual("the thread 'what changed today?' under #ops on the "
                         "'Rundesk' server",
                         discord._place(at, False, True))

    def test_discord_maps_its_places_to_the_shared_channel_hierarchy(self):
        """R-DIS-21, R-AGT-38 — Discord nouns do not leak into shared variable names."""
        thread = self.Thread("release", 42)
        thread.parent = self.Where("ops", 1180)
        at = self.message(thread, self.Where("Acme", 99), shown="Tim")
        self.assertEqual({
            "channel_name": "ops",
            "channel_id": "1180",
            "channel_parent_name": "Acme",
            "channel_parent_id": "99",
            "channel_thread_name": "release",
            "channel_thread_id": "42",
        }, discord._prompt_context(at, False, True))

    def test_discord_maps_an_ordinary_room_without_inventing_a_thread(self):
        at = self.message(self.Where("ops", 1180), self.Where("Acme", 99), shown="Tim")
        self.assertEqual({
            "channel_name": "ops",
            "channel_id": "1180",
            "channel_parent_name": "Acme",
            "channel_parent_id": "99",
            "channel_thread_name": "",
            "channel_thread_id": "",
        }, discord._prompt_context(at, False, False))

    def test_discord_maps_a_direct_message_without_platform_containers(self):
        at = self.message(self.Where(None, 1180), shown="Tim")
        self.assertEqual({
            "channel_name": "a direct message",
            "channel_id": "1180",
            "channel_parent_name": "",
            "channel_parent_id": "",
            "channel_thread_name": "",
            "channel_thread_id": "",
        }, discord._prompt_context(at, True, False))

    def test_discords_exact_legacy_defaults_are_replaced_but_owner_edits_are_not(self):
        """R-DIS-21, R-CH-22 — old adapter defaults do not duplicate the standardized
        trigger, while text an owner changed stays additive."""
        for shape, direct in ((discord.DMS, True), (discord.ROOMS, False)):
            old = discord.LEGACY_INSTRUCTIONS[shape]
            arrived = {"direct": direct, "where": "#ops", "called": "Tim",
                       channel.PROMPT_REPLACES: old}
            built = channel.preface(
                {"kind": "discord", channel.INSTRUCTIONS: old},
                "ava", "discord-" + shape, arrived,
                core_variables={
                    "agent_home": "/agents/ava/home",
                    "workspace": "/agents/ava/home/workspace",
                },
            )
            self.assertNotIn("reached over discord", built)
            changed = old + "\nOwner addition."
            kept = channel.preface(
                {"kind": "discord", channel.INSTRUCTIONS: changed},
                "ava", "discord-" + shape, arrived,
                core_variables={
                    "agent_home": "/agents/ava/home",
                    "workspace": "/agents/ava/home/workspace",
                },
            )
            self.assertIn("Owner addition.", kept)


@unittest.skipIf(discord is None, "discord.py is not installed — run ./install.sh")
class WhatAMessageRepliesTo(unittest.IsolatedAsyncioTestCase):
    """R-DIS-34 — Discord's native reference becomes the shared reply shape."""

    @staticmethod
    def message(resolved=None, message_id=8839, kind=None):
        if kind is None:
            kind = discord.discord.MessageReferenceType.reply
        reference = SimpleNamespace(
            message_id=message_id, resolved=resolved, cached_message=None, type=kind,
        )
        return SimpleNamespace(reference=reference)

    @staticmethod
    def parent(text="the schedule report", shown="Winston", identifier=2207):
        author = SimpleNamespace(
            display_name=shown, name="winston", id=identifier,
        )
        return SimpleNamespace(author=author, content=text)

    def test_a_resolved_reply_carries_the_parent_identity_author_and_body(self):
        self.assertEqual({
            "id": "8839", "resolved": True, "author": "Winston",
            "text": "the schedule report",
        }, discord._reply_to(self.message(self.parent())))

    def test_a_deleted_or_unfetched_parent_still_carries_its_identity(self):
        self.assertEqual({
            "id": "8839", "resolved": False,
        }, discord._reply_to(self.message()))

    def test_a_non_reply_reference_is_not_presented_as_a_reply(self):
        kind = SimpleNamespace(name="forward")
        self.assertIsNone(discord._reply_to(self.message(self.parent(), kind=kind)))

    def test_a_message_without_a_reference_has_no_reply_context(self):
        self.assertIsNone(discord._reply_to(SimpleNamespace(reference=None)))

    async def test_on_message_reports_the_reply_on_the_arrived_record(self):
        parent = self.parent()
        message = SimpleNamespace(
            id=8841,
            author=SimpleNamespace(
                id=2207, bot=False, display_name="Tim", name="tim",
            ),
            guild=None,
            channel=SimpleNamespace(id=1180, name=None),
            mentions=[],
            content="fix the second one",
            attachments=[],
            reference=self.message(parent).reference,
        )
        agent = SimpleNamespace(
            chose=SimpleNamespace(
                server=None, channel=None, dm=True, allow=("2207",),
            ),
            user=SimpleNamespace(id=42),
            live={},
            seen={},
            _fetch=mock.AsyncMock(return_value=[]),
            _no_longer_last=lambda _live: None,
            _make_room=lambda _conversation: True,
        )
        with mock.patch.object(discord, "say") as reported:
            await discord.Agent.on_message(agent, message)
        self.assertEqual({
            "id": "8839", "resolved": True, "author": "Winston",
            "text": "the schedule report",
        }, reported.call_args.kwargs["reply_to"])


@unittest.skipIf(discord is None, "discord.py is not installed — run ./install.sh")
class AnAnswerTooLongForOneMessage(unittest.TestCase):
    """R-DIS-13 — split or attached, never cut in silence."""

    def test_an_answer_that_fits_is_one_message(self):
        head, rest = discord.split_at("short enough", discord.LIMIT)
        self.assertEqual("short enough", head)
        self.assertEqual("", rest)

    def test_an_answer_too_long_is_broken_at_a_line_where_there_is_one(self):
        """A break at a newline keeps a code block or a list readable."""
        text = ("a" * 1000) + "\n" + ("b" * 1500)
        head, rest = discord.split_at(text, discord.LIMIT)
        self.assertEqual("a" * 1000, head)
        self.assertEqual("b" * 1500, rest)

    def test_an_answer_with_nowhere_to_break_is_cut_rather_than_dropped(self):
        """A word that does not fit is still a word that has to go somewhere."""
        text = "x" * 5000
        head, rest = discord.split_at(text, discord.LIMIT)
        self.assertEqual(discord.LIMIT, len(head))
        self.assertEqual(5000 - discord.LIMIT, len(rest))

    def test_nothing_is_lost_however_many_messages_it_takes(self):
        """R-DIS-13 — the whole of the answer arrives, which is the requirement; how many
        messages it took is not."""
        text = "\n".join("line %d" % i for i in range(2000))
        rest, pieces = text, []
        while rest:
            piece, rest = discord.split_at(rest, discord.LIMIT)
            pieces.append(piece)
            self.assertLessEqual(len(piece), discord.LIMIT)
        self.assertEqual(text.replace("\n", ""), "".join(pieces).replace("\n", ""))

    def test_the_limit_is_under_what_discord_allows(self):
        """Discord refuses a message at two thousand characters, and a reply refused is a
        reply lost. The room to break at a line has to come from somewhere."""
        self.assertLess(discord.LIMIT, 2000)


@unittest.skipIf(discord is None, "discord.py is not installed — run ./install.sh")
class HowATurnIsMarked(unittest.TestCase):
    """R-DIS-5, R-DIS-7, R-DIS-8 — one mark at a time, and what each means."""

    def test_every_state_the_seam_decides_has_something_to_show_for_it(self):
        """R-CAD-4, R-DIS-7 — the surface decides how, never whether. A state with no
        mark is a turn that ends and says nothing."""
        from rundesk import channel

        shown = set(discord.MARKS) | {channel.TAKEN, channel.RUNNING}
        self.assertEqual(set(channel.STATES), shown,
                         "a state this surface would be told about has no way to show it")

    def test_how_it_ended_is_told_from_that_it_was_seen(self):
        """R-DIS-8 — 👀 means "working on it", and leaving it up beside ✅ says the
        opposite of what happened."""
        self.assertNotIn(discord.SEEN, discord.MARKS.values())

    def test_stopping_and_failing_are_not_the_same_mark(self):
        """R-DIS-9 — "it stopped" and "it broke" are different news, and only one of them
        means somebody should look at something."""
        self.assertNotEqual(discord.MARKS["stopped"], discord.MARKS["failed"])


@unittest.skipIf(discord is None, "discord.py is not installed — run ./install.sh")
class WhatOneTurnLooksLike(unittest.TestCase):
    """R-DIS-17 — one message, with what it cost above the answer."""

    def test_what_a_turn_cost_is_shown_as_one_line(self):
        """R-DIS-17 — a run already carries its own cost. This reports it and computes
        nothing."""
        self.assertEqual("-# · 1.2k input · 340 output · 17k cached",
                         discord._as_a_line({"type": "usage", "input": 1200,
                                             "output": 340, "cached": 17000}))

    def test_the_footer_omits_cache_writes_the_seam_hands_over(self):
        """R-DIS-17, R-CH-13 — cache writes remain part of the usage record, but the
        compact final footer omits them even when the real seam hands them over."""
        crossed = []
        seam = answering._Shown(
            SimpleNamespace(record={}, _tell=lambda **it: crossed.append(it)),
            SimpleNamespace(conversation="4242", run="run-1"))
        seam({"type": "usage", "input": 1200, "output": 340, "cached": 17000,
              "written": 1500})
        self.assertEqual("-# · 1.2k input · 340 output · 17k cached",
                         discord._as_a_line(crossed[0]))

    def test_the_footer_leads_with_how_big_the_conversation_is(self):
        """R-DIS-29, R-USE-15 — the footer is read to decide one thing: whether to start a
        fresh conversation. `2 input` is what a warm turn's fresh tokens are and says
        nothing about a session; the size it ended on does, and goes first. What the turn
        itself wrote stays beside it, and the breakdown stays in `rundesk runs`."""
        self.assertEqual(
            "-# · 122k session · 837 output",
            discord._as_a_line({"type": "usage", "session": 122435, "input": 2,
                                "output": 837, "cached": 121446, "written": 987}))

    def test_where_an_answer_is_posted_does_not_change_its_usage_summary(self):
        """R-DIS-29 — direct messages and rooms show the same useful session-size view;
        where an answer lands cannot silently replace it with the billing breakdown."""
        usage = {"type": "usage", "session": 122435, "input": 2,
                 "output": 837, "cached": 121446}
        self.assertEqual(
            ["-# · 122k session · 837 output"] * 2,
            [discord._as_a_line(dict(usage, direct=direct))
             for direct in (True, False)],
        )

    def test_the_whole_footer_an_owner_reads_is_the_size_what_was_written_and_the_clock(self):
        """R-DIS-29, R-DIS-24 — end to end, from the record the adapter sent to the line
        above the answer, because each half of this passes on its own while the line
        somebody actually reads is wrong."""
        posted = []

        class Turn:
            async def _post(self, it, text, **kw): posted.append(text)
            def _stop_typing(self, held): pass
            def _no_longer_last(self, held): pass

        held = discord.Live(clock=lambda: 128.0)
        held.started = 100.0
        asyncio.run(discord.Agent._doing(
            Turn(), {"type": "usage", "session": 122435, "output": 837}, held))
        asyncio.run(discord.Agent._answer(
            Turn(), {"type": "answer", "provider": "stand-in", "text": "done"}, held))
        self.assertEqual("-# stand-in · 122k session · 837 output · 28s elapsed",
                         posted[0].splitlines()[0])

    def test_a_brain_that_does_not_report_a_conversation_size_gets_the_footer_it_always_got(self):
        """R-DIS-29, R-USE-16 — a brain that cannot say how big its conversation is keeps
        every slot it used to show rather than being cut down to `output` alone. Adding a
        quantity for one brain may not take three away from another."""
        self.assertEqual("-# · 1.2k input · 340 output · 17k cached",
                         discord._as_a_line({"type": "usage", "input": 1200,
                                             "output": 340, "cached": 17000}))

    def test_elapsed_time_is_compact_at_seconds_minutes_and_hours(self):
        """R-DIS-24 — the duration stays readable beside compact token counts."""
        self.assertEqual(["40s", "2m", "2h"],
                         [discord._duration(one) for one in (40, 120, 7200)])

    def test_elapsed_time_runs_from_taken_until_the_answer_is_ready(self):
        """R-DIS-24 — a monotonic clock measures work, excluding Discord posting time."""
        now = [100.0]
        posted = []

        class Turn:
            async def _react(self, it, held, mark): pass
            async def _typing(self, it): pass
            async def _post(self, it, text, **kw): posted.append(text)
            def _stop_typing(self, held): pass
            def _no_longer_last(self, held): pass

        held = discord.Live(clock=lambda: now[0])
        asyncio.run(discord.Agent._state(
            Turn(), {"state": "taken", "conversation": "c"}, held))
        held.cost = "-# · 1.9k input · 94 output · 70k cached"
        now[0] += 120
        asyncio.run(discord.Agent._answer(
            Turn(), {"type": "answer", "provider": "stand-in", "text": "done"}, held))
        self.assertEqual(
            "-# stand-in · 1.9k input · 94 output · 70k cached · 2m elapsed",
            posted[0].splitlines()[0])

    def test_repeated_taken_does_not_restart_elapsed_time(self):
        """R-DIS-24 — duplicate state delivery cannot shorten the displayed work."""
        now = [100.0]

        class Turn:
            async def _react(self, it, held, mark): pass
            async def _typing(self, it): pass

        held = discord.Live(clock=lambda: now[0])
        asyncio.run(discord.Agent._state(Turn(), {"state": "taken"}, held))
        now[0] += 40
        asyncio.run(discord.Agent._state(Turn(), {"state": "taken"}, held))
        self.assertEqual(100.0, held.started)

    def test_provider_and_elapsed_time_are_shown_when_usage_was_not_reported(self):
        """R-DIS-24, R-DIS-33 — provenance does not depend on optional usage metadata."""
        posted = []

        class Turn:
            async def _post(self, it, text, **kw): posted.append(text)
            def _stop_typing(self, held): pass
            def _no_longer_last(self, held): pass

        held = discord.Live(clock=lambda: 140.0)
        held.started = 100.0
        asyncio.run(discord.Agent._answer(
            Turn(), {"type": "answer", "provider": "stand-in", "text": "done"}, held))
        self.assertEqual("-# stand-in · 40s elapsed", posted[0].splitlines()[0])

    def test_a_small_count_is_not_rounded_into_a_zero(self):
        """R-USE-7 — everything was shown in thousands, so a turn that answered in
        thirteen tokens reported `0k output`: a measurement, stated plainly, and wrong.
        An absent number means "could not tell" and a zero means zero, so neither may be
        invented by rounding."""
        said = discord._as_a_line({"type": "usage", "input": 4737, "output": 13,
                                   "cached": 13056})
        self.assertIn("13 output", said)
        self.assertNotIn("0k output", said)

    def test_a_count_in_the_millions_is_not_shown_in_thousands(self):
        """R-DIS-17 — a cache read is counted once per request, so a turn that made forty
        of them reported `15425k cached`: a unit nobody carries that far, which a reader
        has to divide in their head before it means anything. The decimal stays, because
        rounding one away is half a million tokens."""
        self.assertEqual(["999k", "1M", "1.4M", "15.4M"],
                         [discord._amount(one)
                          for one in (999_499, 999_500, 1_400_000, 15_424_940)])

    def test_a_turn_that_reported_no_cost_says_nothing_about_it(self):
        """An absent number is not a zero, and inventing one is claiming a measurement."""
        self.assertEqual("", discord._as_a_line({"type": "usage"}))

    def test_a_tool_that_worked_is_not_a_message_of_its_own(self):
        """R-DIS-17 — a phone that buzzes eleven times to say an agent read a file is
        worse than one that buzzes once with the reply."""
        self.assertEqual("", discord._as_a_line(
            {"type": "result", "id": "1", "ok": True, "summary": "3 files changed"}))

    def test_what_a_turn_cost_never_goes_in_the_commentary(self):
        """R-DIS-17 — it belongs above the answer, where somebody reading the reply sees
        it without going back for it."""
        self.assertEqual("", discord.commentary(
            {"type": "usage", "input": 1200, "output": 340, "cached": 17000}))
        self.assertNotEqual("", discord._as_a_line(
            {"type": "usage", "input": 1200, "output": 340, "cached": 17000}))

    def test_a_turn_that_neither_thought_nor_ran_anything_shows_no_commentary(self):
        """R-DIS-20 — an empty commentary message is a notification that says nothing."""
        for said in ({"type": "usage", "input": 1}, {"type": "result", "id": "1", "ok": True},
                     {"type": "think", "text": "   "}, {"type": "answer", "text": "hi"}):
            self.assertEqual("", discord.commentary(said), f"{said} became commentary")

    def test_a_long_remark_is_split_without_losing_any_of_it(self):
        """R-CH-19, R-DIS-13 — a finished thing said mid-turn goes through `told` as a
        remark. Discord refuses one content field beyond its limit, so bounding only the
        final answer loses scheduled reports before their final record arrives."""
        posted = []

        class Turn:
            live = {}

            async def _flush(self, it, held): pass
            async def _post(self, it, text, **kw): posted.append(text)
            def _no_longer_last(self, held): pass
            def _stop_typing(self, held): pass
            async def _typing(self, it): pass

        text = ("first line\n" + ("x" * discord.LIMIT) + "\nlast line")
        asyncio.run(discord.Agent.told(
            Turn(), {"type": "said", "conversation": "c1", "text": text}))

        self.assertGreater(len(posted), 1, "the oversized remark was posted as one message")
        self.assertTrue(all(len(piece) <= discord.LIMIT for piece in posted), posted)
        self.assertEqual(text.replace("\n", ""), "".join(posted).replace("\n", ""))

    def test_what_the_agent_did_does_become_commentary(self):
        """R-DIS-20 — the other half, or the option would show nothing at all."""
        self.assertNotEqual("", discord.commentary(
            {"type": "tool", "name": "Bash", "did": "run"}))
        self.assertNotEqual("", discord.commentary(
            {"type": "think", "text": "the error is in the parser"}))

    def test_thinking_is_a_broad_category_and_never_the_thought_itself(self):
        """R-DIS-20 — activity is enough to show progress, not a reasoning transcript."""
        shown = discord.commentary(
            {"type": "think", "text": "the error is in the private parser"})
        self.assertEqual("-# 💭 thinking", shown)
        self.assertNotIn("private parser", shown)

    def test_an_unknown_tool_uses_thinking_instead_of_a_gear(self):
        """R-DIS-20 — an unmapped provider label stays broad without the disliked gear."""
        shown = discord.commentary({"type": "tool", "name": "providerSpecificTool"})
        self.assertEqual("-# 💭 thinking", shown)
        self.assertNotIn("⚙", shown)

    def test_one_activity_has_no_count(self):
        """R-DIS-20 — a count starts only when something actually repeats."""
        self.assertEqual("-# 💻 ran command",
                         discord._render_activity(
                             discord._group_activity([], ["-# 💻 ran command"])))

    def test_consecutive_activity_is_one_line_with_a_count(self):
        """R-DIS-20 — repeated activity remains legible and leaves room for the answer."""
        groups = discord._group_activity([], [
            "-# 💻 ran command", "-# 💻 ran command", "-# 💻 ran command"])
        self.assertEqual("-# 💻 ran command **(x3)**",
                         discord._render_activity(groups))

    def test_only_consecutive_activity_is_counted(self):
        """R-DIS-20 — a different category closes the group permanently."""
        groups = discord._group_activity([], [
            "-# 💻 ran command", "-# 💻 ran command",
            "-# 📖 read file", "-# 💻 ran command"])
        self.assertEqual(
            "-# 💻 ran command **(x2)**\n"
            "-# 📖 read file\n"
            "-# 💻 ran command",
            discord._render_activity(groups))

    def test_a_growing_message_counts_across_separate_writes(self):
        """R-DIS-20 — the count grows by editing the active commentary message."""
        edited = []

        class Posted:
            async def edit(self, content):
                edited.append(content)

        class Turn:
            chose = type("Choice", (), {"activity": discord.GROWS})()

            async def _post(self, it, text, **kw):
                raise AssertionError("an editable commentary was posted again")

        held = discord.Live()
        held.posted = Posted()
        held.activity_groups = [("-# 💻 ran command", 1)]
        held.activity = discord._render_activity(held.activity_groups)
        held.pending = ["-# 💻 ran command"]
        asyncio.run(discord.Agent._flush(Turn(), {}, held))
        self.assertEqual(["-# 💻 ran command **(x2)**"], edited)

    def test_activity_arriving_during_an_edit_gets_a_successor_write(self):
        """R-DIS-20 — a Discord await may not strand the newest count until the answer."""
        async def scenario():
            editing = asyncio.Event()
            release = asyncio.Event()
            edited = []

            class Posted:
                async def edit(self, content):
                    edited.append(content)
                    editing.set()
                    await release.wait()

            class Turn:
                chose = type("Choice", (), {"activity": discord.GROWS})()

                async def _post(self, it, text, **kw):
                    raise AssertionError("an editable commentary was posted again")

                async def _flush(self, it, held):
                    await discord.Agent._flush(self, it, held)

                async def _paced(self, it, held):
                    await discord.Agent._paced(self, it, held)

            held = discord.Live()
            held.posted = Posted()
            held.activity_groups = [("-# 💻 ran command", 1)]
            held.pending = ["-# 💻 ran command"]
            held.pacing = asyncio.create_task(discord.Agent._paced(Turn(), {}, held))
            await asyncio.wait_for(editing.wait(), timeout=2)
            await discord.Agent._doing(
                Turn(), {"type": "tool", "id": "3", "did": "run"}, held)
            release.set()
            first = held.pacing
            await first
            successor = held.pacing
            self.assertIsNot(first, successor)
            await successor
            return edited, held

        edited, held = asyncio.run(scenario())
        self.assertEqual("-# 💻 ran command **(x3)**", edited[-1])
        self.assertEqual([], held.pending)

    def test_an_intervening_message_breaks_a_count_that_has_not_flushed_yet(self):
        """R-DIS-20 — a pending write may not merge activity across visible history."""
        held = discord.Live()
        held.pending = ["-# 💻 ran command"]
        discord.Agent._no_longer_last(None, held)
        held.pending.append("-# 💻 ran command")
        self.assertEqual(
            "-# 💻 ran command\n-# 💻 ran command",
            discord._render_activity(discord._group_activity([], held.pending)))

    def test_a_subagent_start_and_finish_are_two_broad_categories(self):
        """R-DIS-20 — a result is correlated without publishing the helper's response."""
        tools = {}
        started = discord._activity_line(
            {"type": "tool", "id": "helper-1", "did": "delegate"}, tools)
        finished = discord._activity_line(
            {"type": "result", "id": "helper-1", "ok": True,
             "summary": "private helper response"}, tools)
        self.assertEqual("-# 🤖 delegated to subagent", started)
        self.assertEqual("-# 🤖 subagent finished", finished)
        self.assertNotIn("private helper response", finished)

    def test_a_safe_subagent_name_is_shown_without_its_provider_path(self):
        """R-DIS-20 — one helper may be named without relaying its work or private path."""
        tools = {}
        started = discord._activity_line({
            "type": "tool", "id": "helper-1", "did": "delegate",
            "who": "/root/senior_code_reviewer",
        }, tools)
        finished = discord._activity_line({
            "type": "result", "id": "helper-1", "ok": True,
            "summary": "private response",
        }, tools)
        self.assertEqual("-# 🤖 delegated to subagent: senior_code_reviewer", started)
        self.assertEqual("-# 🤖 subagent finished: senior_code_reviewer", finished)
        self.assertNotIn("/root", started)
        self.assertNotIn("private response", finished)

    def test_named_subagents_still_collapse_as_one_broad_category(self):
        """R-DIS-20 — names add detail only while they do not defeat compact counts."""
        groups = discord._group_activity([], [
            "-# 🤖 delegated to subagent: Gibbs",
            "-# 🤖 delegated to subagent: Plato",
        ])
        self.assertEqual(
            "-# 🤖 delegated to subagent **(x2)**",
            discord._render_activity(groups))

    def test_it_stops_saying_it_is_typing_the_moment_there_is_something_to_read(self):
        """R-DIS-6 — cancelled when the turn *ended*, which is one record too late: the
        answer is handed over first, so the renewal could fire once more in between and
        Discord holds an indicator for about ten seconds after the last one. It went on
        saying the agent was typing while the reply was already sitting there."""

        class Fake:
            def __init__(self):
                self.cancelled = False

            def cancel(self):
                self.cancelled = True

        held = discord.Live()
        held.typing = Fake()
        discord.Agent._stop_typing(None, held)
        self.assertTrue(held.typing is None)

    def test_a_direct_message_gets_a_typing_indicator_at_all(self):
        """R-DIS-6 — `get_channel` reads the client's cache and a direct message is very
        often not in it, so it answered None, the renewal loop never ran once, and there was
        no indicator in a DM ever. Nothing reported it: the task was created and returned
        immediately, and a `held.typing` holding a finished task looks exactly like one that
        is working. `_react` has always fetched as a fallback, which is what makes this an
        omission rather than a decision."""
        typed = []

        class Cached:
            async def typing(self):
                typed.append(True)
                raise RuntimeError("stop after one, so the loop does not run for ever")

        class NotCached:
            def get_channel(self, where):
                return None                      # a DM, as the cache reports it

            async def fetch_channel(self, where):
                return Cached()

        with contextlib.suppress(BaseException):
            asyncio.run(asyncio.wait_for(
                discord.Agent._typing(NotCached(), {"conversation": "1180"}), 0.3))
        self.assertTrue(typed, "a direct message was never told the agent was typing")

    def test_a_channel_that_cannot_be_resolved_says_so_rather_than_going_quiet(self):
        """A turn with no indicator and no line saying why is the shape this bug already
        had once."""
        said = []

        class Gone:
            def get_channel(self, where):
                return None

            async def fetch_channel(self, where):
                raise RuntimeError("no such channel")

        was, discord.note = discord.note, lambda line: said.append(line)
        try:
            asyncio.run(discord.Agent._typing(Gone(), {"conversation": "1180"}))
        finally:
            discord.note = was
        self.assertTrue(any("typing" in one for one in said), said)

    def test_it_says_it_is_typing_again_after_a_remark_because_the_turn_goes_on(self):
        """R-DIS-6 — the other half, and it was missing for as long as the half above has
        existed. A remark stops the indicator so nobody is told the agent is typing while
        they read it, and the comment promised "the next thing said starts the indicator
        again" — but nothing did: typing is only ever started from a `taken` or `running`
        state, and an agent that says something and then carries on working sends neither.
        The indicator went out at the first remark and stayed out for the rest of the turn.

        Driven through the real `told`, because the bug was in which branch restarts it and
        a test that called the branch directly would have agreed with the bug."""
        started = []

        class Turn:
            live = {}

            async def _flush(self, it, held): pass
            async def _post(self, it, text, **kw): return None
            def _no_longer_last(self, held): pass
            def _stop_typing(self, held): held.typing = None
            async def _typing(self, it): started.append(it)

        turn = Turn()
        turn.live = {}
        asyncio.run(discord.Agent.told(turn, {"type": "said", "conversation": "c1",
                                              "text": "half way there"}))
        held = turn.live["c1"]
        self.assertIsNotNone(held.typing, "the indicator was left off for the rest of the turn")
        # What ends it is a final state, which cancels it — that path is untouched here.
        held.typing.cancel()

    def test_a_terminal_notice_does_not_claim_another_turn_is_running(self):
        """R-DIS-35 — a restart outcome has no turn left to end its typing indicator."""
        typed = []

        class Notice:
            live = {}
            started = {}

            async def _flush(self, it, held): pass
            async def _post(self, it, text, **kw): return None
            def _no_longer_last(self, held): pass
            def _stop_typing(self, held): discord.Agent._stop_typing(self, held)
            async def _typing(self, it): typed.append(it)

        notice = Notice()
        asyncio.run(discord.Agent.told(notice, {
            "type": "said", "conversation": "c1", "text": "restart succeeded",
            "continues": False,
        }))

        self.assertEqual([], typed)
        self.assertNotIn("c1", notice.live)

    def test_a_terminal_notice_does_not_erase_a_newer_running_turn(self):
        """R-DIS-35 — a new turn may begin before a queued restart notice is delivered."""
        async def scenario():
            class Notice:
                started = {}

                async def _flush(self, it, held): pass
                async def _post(self, it, text, **kw): return None
                def _no_longer_last(self, held): pass
                def _stop_typing(self, held): discord.Agent._stop_typing(self, held)
                async def _typing(self, it): await asyncio.Event().wait()

            held = discord.Live()
            held.started = 1.0
            held.typing = asyncio.create_task(asyncio.Event().wait())
            notice = Notice()
            notice.live = {"c1": held}

            await discord.Agent.told(notice, {
                "type": "said", "conversation": "c1", "text": "restart succeeded",
                "continues": False,
            })

            self.assertIs(held, notice.live["c1"])
            self.assertIsNotNone(held.typing)
            self.assertFalse(held.typing.done())
            held.typing.cancel()

        asyncio.run(scenario())

    def test_a_commentary_stops_growing_once_something_is_said_under_it(self):
        """R-DIS-20 — a message something has been posted under is one the reader has
        already scrolled past. Editing it changes history rather than showing progress:
        the new line appears above whatever came after it, where nobody is looking. So
        the next thing to show has to begin a message of its own."""
        held = discord.Live()
        held.posted, held.activity = object(), "-# 💻 ran command"
        held.activity_groups = [("-# 💻 ran command", 1)]
        # Unbound on purpose: the decision uses nothing of the connection, which is what
        # makes it testable without one.
        discord.Agent._no_longer_last(None, held)
        self.assertIsNone(held.posted, "it would have gone on editing a buried message")
        self.assertEqual("", held.activity,
                         "a fresh message would have opened with the old one's lines")
        self.assertEqual([], held.activity_groups,
                         "the next message would have continued the old count")

    def test_a_write_that_lands_after_the_message_was_buried_is_dropped(self):
        """R-DIS-20 — the buried-message fix was written as though nothing happened
        between deciding to post and the post landing. A paced flush suspended inside a
        write finishes *after* something else has buried the commentary, and its
        assignment put the buried message back for the next line to grow into."""
        held = discord.Live()
        was = held.writes
        discord.Agent._no_longer_last(None, held)
        self.assertNotEqual(was, held.writes,
                            "a write in flight would still be taken as the newest")

    def test_showing_the_work_is_off_unless_the_owner_asks(self):
        """R-DIS-20 — an owner who wants to watch says so, and one who does not gets one
        message per turn rather than a running commentary."""
        self.assertIsNone(discord.options([]).activity)
        self.assertEqual("grows", discord.options(["--activity", "grows"]).activity)

    def test_the_commentary_may_grow_but_the_answer_may_never(self):
        """R-CH-7, R-DIS-20 — a reply that rewrites itself in place is unreadable, so
        the message that is edited is the commentary and never the answer."""
        self.assertEqual({"grows", "posts", "off"},
                         {discord.GROWS, discord.POSTS, discord.OFF})

    def test_a_long_commentary_is_kept_to_what_one_message_holds(self):
        """R-DIS-13, R-DIS-20 — Discord refuses a message past its limit, so a turn that
        ran fifty tools would grow one that cannot be sent at all."""
        self.assertLess(discord.ACTIVITY_CHARS, discord.LIMIT)

    def test_a_tool_that_failed_still_says_so(self):
        """R-DIS-9 — what somebody watching wants is the thing that did not work."""
        said = discord._as_a_line(
            {"type": "result", "id": "1", "ok": False, "summary": "no such file"})
        self.assertEqual("-# ⚠ tool failed", said)

    def test_a_tool_failure_never_publishes_its_private_details(self):
        """R-DIS-20 — activity says what failed without relaying a command or path."""
        tools = {}
        discord._activity_line({"type": "tool", "id": "1", "did": "run"}, tools)
        said = discord._activity_line({
            "type": "result", "id": "1", "ok": False,
            "summary": "rg secret /Users/owner/private/project",
        }, tools)
        self.assertEqual("-# ⚠ command failed", said)
        self.assertNotIn("/Users/owner", said)
        self.assertNotIn("secret", said)

    def test_every_verb_the_seam_defines_has_a_mark_of_its_own(self):
        """R-PRV-8, R-CAD-4 — the list of what a tool did is the seam's and is closed. A
        verb with no mark here would quietly show as the fallback, which reads as "we do
        not know what that was" for something the contract does name."""
        from rundesk import provider

        self.assertEqual(set(provider.DID), set(discord.DID),
                         "this surface and the seam disagree about what a tool can do")
        self.assertEqual(set(provider.DID), set(discord.FAILED),
                         "a tool verb has no broad failure wording")
        self.assertEqual(len(set(discord.DID.values())), len(discord.DID),
                         "two verbs share a mark, so a reader cannot tell them apart")
        self.assertNotIn(discord.UNKNOWN, discord.DID.values(),
                         "a named verb uses the mark that means 'no idea what that was'")

    def test_a_tool_is_shown_by_what_it_did_and_never_by_its_brains_name_for_it(self):
        """R-PRV-8 — this showed the brain's own word first, so a commentary read
        `commandExecution` and `imageGeneration`: one vendor's identifiers, in front of
        somebody who has never heard of that vendor and never should."""
        said = discord.commentary({"type": "tool", "name": "commandExecution", "did": "run"})
        self.assertIn(discord.DID["run"], said)
        self.assertNotIn("commandExecution", said, "a vendor's own word reached a reader")

    def test_a_tool_with_no_verb_says_something_true_rather_than_the_vendors_word(self):
        """R-PRV-8 — a brain that gave no verb did something this vocabulary has no word
        for yet, and its own identifier is not a translation of that."""
        said = discord.commentary({"type": "tool", "name": "imageGeneration"})
        self.assertIn(discord.UNKNOWN, said)
        self.assertNotIn("imageGeneration", said)

    def test_every_verb_has_something_a_person_would_say(self):
        """R-PRV-8 — a commentary is read as a sentence, so a mark with no words beside
        it is a row of emoji nobody can act on."""
        from rundesk import provider

        self.assertEqual(set(provider.DID), set(discord.SHOWN))

    def test_activity_is_written_clipped_rather_than_as_prose(self):
        """R-DIS-20 — a turn puts dozens of these in a column of subtext beside a column
        of marks. At that width an article is a word carrying nothing, and one line
        starting with a capital reads as the start of a sentence the rest are not."""
        for verb, said in discord.SHOWN.items():
            with self.subTest(verb):
                self.assertNotRegex(said, r"\b(a|an|the)\b",
                                    "an article in a line nobody reads as a sentence")
                self.assertEqual(said[:1], said[:1].lower(),
                                 "one line capitalised and the rest not")

    def test_the_two_lines_a_delegation_is_bracketed_by_are_written_once(self):
        """R-DIS-20 — each is said three times: the line, the heading a repeat is counted
        under, and the prefix a helper's name is appended to. Three copies drifting apart
        is a count that stops matching the line above it, with nothing to see in a diff."""
        started = discord._activity_line(
            {"type": "tool", "id": "h", "did": "delegate"}, {})
        self.assertEqual(f"-# {discord.DELEGATED}", started)
        self.assertEqual(started, discord._activity_category(started))
        self.assertEqual(discord.SHOWN["delegate"],
                         discord.DELEGATED[len(discord.DID["delegate"]) + 1:])

    def test_changing_what_it_keeps_of_its_own_is_told_apart_from_any_other_edit(self):
        """R-PRV-29 — the whole point of the four verbs. Shown beside `edit` they would be
        the same pencil, and a reader could not tell a working file from the file the
        agent lives by."""
        from rundesk import provider

        for verb in provider.CONTINUITY.values():
            with self.subTest(verb):
                said = discord.commentary({"type": "tool", "name": "Write", "did": verb})
                self.assertIn(discord.DID[verb], said)
                self.assertNotIn(discord.DID["edit"], said)
                self.assertNotIn("Write", said, "a vendor's own word reached a reader")

    def test_what_it_keeps_of_its_own_is_spoken_of_in_the_first_person(self):
        """R-DIS-20 — an activity line is the agent saying what it just did. "Updated its
        memory" reads as a process writing to a store; the agent changed what it will know
        next time, and it is the one saying so."""
        from rundesk import provider

        for name, verb in provider.CONTINUITY.items():
            with self.subTest(verb):
                said = f" {discord.SHOWN[verb]} "
                self.assertNotIn(" its ", said)
                self.assertIn(" my ", said)


@unittest.skipIf(discord is None, "discord.py is not installed — run ./install.sh")
class WhatARoleRunLooksLikeHere(unittest.TestCase):
    """R-ROL-27, R-ROL-36 — work handed to a specialist, rendered from the record alone.

    Both marks used to ride the generic tool/result activity, which meant two things:
    with the default `grows` display they were *edited* into whatever unrelated turn was
    in flight, as grey subtext nobody was told about; and the closing one was rendered by
    correlating against a `Live` entry this process happened to be holding, so a restart
    between handing work over and getting it back left the mark open for ever.
    """

    def handed(self, **also) -> dict:
        said = {"type": "role", "conversation": "1180", "role_run": "rol-1-aaaa",
                "state": "handed", "role": "development", "label": "applicant export",
                "elapsed": 0}
        said.update(also)
        return said

    def test_handing_work_to_a_role_is_news_rather_than_subtext(self):
        line = discord.role_line(self.handed())
        self.assertEqual("🤖 Handed **applicant-export** to the *development* role.", line)
        self.assertFalse(line.startswith("-#"), "the news was shown as grey subtext")

    def test_a_settled_role_run_shows_in_full_with_no_prior_handed_ever_seen(self):
        """**The regression this exists for.** A run lasts hours and this program does
        not: the adapter that is told a run came back is routinely not the one that was
        told it went out. Asserted against `role_line`, which has no memory to have."""
        back = discord.role_line(self.handed(state="settled", ok=True, elapsed=4000))
        self.assertEqual(
            "✅ 🤖 **applicant-export** is back from the *development* role"
            " — not reviewed yet.", back)

    def test_a_role_that_did_not_finish_says_so_rather_than_that_a_subagent_failed(self):
        line = discord.role_line(self.handed(state="settled", ok=False, elapsed=4000))
        self.assertEqual(
            "⚠️ 🤖 **applicant-export** did not finish — what came back is not reviewed yet.",
            line)
        self.assertNotIn("subagent", line)

    def test_a_check_in_says_how_long_the_run_has_been_going(self):
        self.assertEqual(
            "-# 🤖 **applicant-export** — 40m, still working",
            discord.role_line(self.handed(state="working", elapsed=2400)))

    def test_a_state_this_surface_does_not_know_shows_nothing(self):
        """What `understood` already guarantees for anything unrecognised: an adapter that
        does not know a record shows nothing and stays correct."""
        self.assertEqual("", discord.role_line(self.handed(state="wandering")))
        self.assertEqual("", discord.role_line({"type": "role"}))

    def test_a_role_run_carrying_no_role_is_not_named_after_a_fallback(self):
        """`_plain_name` answers `attachment` when it is left nothing, which is right for
        a file and would have shown *the attachment role*."""
        line = discord.role_line(self.handed(role=""))
        self.assertEqual("🤖 Handed **applicant-export** to a role.", line)
        self.assertNotIn("attachment", line)

    def test_a_label_carrying_a_path_comes_out_through_the_shared_guard(self):
        """R-ROL-17, R-DIS-9 — the shared name sanitiser is not bent for a role."""
        line = discord.role_line(
            self.handed(label="/Users/somebody/secret/exporter",
                        role="/opt/roles/development"))
        self.assertNotIn("/Users", line)
        self.assertNotIn("secret", line)
        self.assertIn("exporter", line)
        self.assertIn("development", line)

    def test_a_role_is_not_called_a_subagent(self):
        """R-ROL-27 — both are delegation and only one is a subagent. Naming the wrong
        mechanism misleads somebody deciding whether to wait."""
        for state, also in (("handed", {}), ("working", {}), ("settled", {"ok": True})):
            with self.subTest(state):
                self.assertNotIn(
                    "subagent", discord.role_line(self.handed(state=state, **also)))
        self.assertNotIn(
            "role", discord._activity_line({"type": "tool", "id": "1", "did": "delegate"},
                                           {}))


@unittest.skipIf(discord is None, "discord.py is not installed — run ./install.sh")
class HowARoleRunReachesTheRoom(unittest.IsolatedAsyncioTestCase):
    """R-ROL-27, R-ROL-36 — its own message, and a check-in that does not fill a room."""

    class Posted:
        def __init__(self, refuses=False):
            self.edited: list = []
            self.refuses = refuses

        async def edit(self, content):
            if self.refuses:
                raise RuntimeError("the platform would not take it")
            self.edited.append(content)

    def surface(self, activity=None, posting=None):
        """The adapter, with only the platform boundary replaced."""
        posted, chose = [], type("Choice", (), {
            "activity": discord.GROWS if activity is None else activity})()

        class Turn:
            live: dict = {}

            def __init__(self):
                self.chose = chose
                self.posted = posted

            async def _post(self, it, content, **kw):
                self.posted.append(content)
                return posting() if posting is not None else None

            def _no_longer_last(self, held):
                discord.Agent._no_longer_last(self, held)

            async def _role(self, it, held):
                await discord.Agent._role(self, it, held)

        return Turn()

    def record(self, **also) -> dict:
        said = {"type": "role", "conversation": "1180", "role_run": "rol-1-aaaa",
                "state": "handed", "role": "development", "label": "a task", "elapsed": 0}
        said.update(also)
        return said

    async def test_a_role_run_is_a_message_of_its_own_and_never_the_commentary(self):
        turn = self.surface()
        turn.live = {}

        await discord.Agent.told(turn, self.record())

        self.assertEqual(["🤖 Handed **a-task** to the *development* role."], turn.posted)

    async def test_a_settled_run_is_posted_after_the_admitting_turn_was_cleared(self):
        """**The defect, through the real dispatch.** `_state` ends its terminal branch
        with `self.live.pop(...)`, so the whole `Live` — including `held.tools`, which
        held the `role:<run>` correlation written seconds earlier — is discarded the
        moment the turn that admitted the run reaches `finished`. A role run always
        outlives that turn, so the correlation was always gone by the time the run came
        back: `_activity_line` fell through, a successful `result` rendered as `""`, and
        `_doing` dropped it. The return therefore never rendered for any role run, not
        merely after a restart.

        Measured on `rol-1-964h` (2026-08-02): admitted 10:41:44, the admitting turn
        finished 10:41:56, the run settled 11:23:48, and nothing was written to that
        conversation between 10:41:56 and 11:24:13.
        """
        posted: list = []

        class Turn:
            def __init__(self):
                self.live: dict = {}
                self.chose = type("Choice", (), {"activity": discord.GROWS})()

            async def _post(self, it, content, **kw):
                posted.append(content)
                return None

            async def _react(self, it, held, mark, instead_of=None):
                pass

            async def _flush(self, it, held):
                pass

            def _no_longer_last(self, held):
                discord.Agent._no_longer_last(self, held)

            async def _state(self, it, held):
                await discord.Agent._state(self, it, held)

            async def _role(self, it, held):
                await discord.Agent._role(self, it, held)

        turn = Turn()
        await discord.Agent.told(turn, self.record())
        await discord.Agent.told(turn, {"type": "state", "conversation": "1180",
                                        "run": "7-a3f1", "state": "finished"})
        self.assertNotIn("1180", turn.live,
                         "the admitting turn's state was not cleared, so this case would "
                         "have passed against the defect it exists for")

        await discord.Agent.told(turn, self.record(state="settled", ok=True, elapsed=2524))

        self.assertEqual(
            ["🤖 Handed **a-task** to the *development* role.",
             "✅ 🤖 **a-task** is back from the *development* role — not reviewed yet."],
            posted, "what came back was never posted")

    async def test_a_role_run_still_shows_when_activity_is_off(self):
        """Turning activity off silences a turn's running commentary. A role coming back
        is not commentary — it is the only sign the work happened at all."""
        turn = self.surface(activity=discord.OFF)
        turn.live = {}

        await discord.Agent.told(turn, self.record(state="settled", ok=True))

        self.assertEqual(1, len(turn.posted))

    async def test_a_check_in_edits_the_message_it_already_posted_for_that_run(self):
        held, posted = discord.Live(), self.Posted()
        turn = self.surface(posting=lambda: posted)

        await turn._role(self.record(state="working", elapsed=1300), held)
        await turn._role(self.record(state="working", elapsed=2500), held)

        self.assertEqual(1, len(turn.posted), "a second message was posted for one run")
        self.assertEqual(["-# 🤖 **a-task** — 41m, still working"], posted.edited)

    async def test_a_check_in_posts_afresh_once_something_else_has_been_said(self):
        """R-DIS-20 — a message something has been posted under is one the reader has
        scrolled past, and editing it changes history rather than showing progress."""
        held, posted = discord.Live(), self.Posted()
        turn = self.surface(posting=lambda: posted)

        await turn._role(self.record(state="working", elapsed=1300), held)
        turn._no_longer_last(held)
        await turn._role(self.record(state="working", elapsed=2500), held)

        self.assertEqual(2, len(turn.posted))
        self.assertEqual([], posted.edited)

    async def test_two_runs_in_one_conversation_never_share_a_check_in(self):
        """Keyed per run, because one conversation can have several in flight — and only
        the newest is still the last thing here, so the other starts a message of its own
        rather than rewriting one the reader has already scrolled past (R-DIS-20)."""
        held = discord.Live()
        made: list = []
        turn = self.surface(posting=lambda: made.append(self.Posted()) or made[-1])

        await turn._role(self.record(state="working", elapsed=1300), held)
        await turn._role(self.record(role_run="rol-2-bbbb", label="another task",
                                     state="working", elapsed=1300), held)
        await turn._role(self.record(state="working", elapsed=2500), held)

        self.assertEqual(
            ["-# 🤖 **a-task** — 21m, still working",
             "-# 🤖 **another-task** — 21m, still working",
             "-# 🤖 **a-task** — 41m, still working"], turn.posted)
        self.assertEqual([[], [], []], [one.edited for one in made],
                         "one run's check-in was written over the other's message")
        self.assertEqual({"rol-1-aaaa"}, set(held.checked_in),
                         "a buried check-in was kept as though it were still editable")

    async def test_a_check_in_that_could_not_be_edited_is_posted_instead(self):
        """A platform boundary: a message somebody deleted must not silence a run."""
        held = discord.Live()
        refuses = self.Posted(refuses=True)
        turn = self.surface(posting=lambda: refuses)

        await turn._role(self.record(state="working", elapsed=1300), held)
        await turn._role(self.record(state="working", elapsed=2500), held)

        self.assertEqual(2, len(turn.posted))

    async def test_a_run_that_settled_stops_being_checked_in_on(self):
        held, posted = discord.Live(), self.Posted()
        turn = self.surface(posting=lambda: posted)

        await turn._role(self.record(state="working", elapsed=1300), held)
        await turn._role(self.record(state="settled", ok=True, elapsed=1400), held)

        self.assertEqual({}, held.checked_in)
        self.assertEqual([], posted.edited, "what came back was edited into a check-in")


@unittest.skipIf(discord is None, "discord.py is not installed — run ./install.sh")
class WhatItOffersAndWhatItIsTold(unittest.TestCase):
    """R-DIS-10, R-CAD-11, R-CAD-13 — its commands, its options, and its credential."""

    def test_every_command_it_offers_is_a_gesture_the_seam_defines(self):
        """R-DIS-10 — the platform picks the word its people recognise and the seam keeps
        the meaning, so a surface cannot invent a gesture nothing acts on."""
        from rundesk import channel

        for _name, _describes, gesture, _said in discord.CONTROL_COMMANDS:
            self.assertIn(gesture, channel.CONTROLS)

    def test_every_command_is_described_where_it_is_offered(self):
        """R-DIS-10 — a command nobody can tell the purpose of is one nobody uses."""
        for name, describes, _gesture, said in discord.CONTROL_COMMANDS:
            self.assertTrue(name and describes and said, f"{name} is not fully described")
        for name, describes, _query in discord.QUERY_COMMANDS:
            self.assertTrue(name and describes, f"{name} is not fully described")

    def test_a_new_session_and_stopping_a_turn_are_different_gestures(self):
        """R-CH-9, R-CH-10 — one ends what is running and the other throws away where the
        conversation had got to."""
        gestures = {
            name: gesture for name, _d, gesture, _s in discord.CONTROL_COMMANDS
        }
        self.assertEqual("forget", gestures["new"])
        self.assertEqual("stop", gestures["stop"])
        self.assertEqual("restart", gestures["restart"])

    def test_read_only_gateway_information_is_offered_as_discord_commands(self):
        """R-DIS-22, R-DIS-36, R-DIS-37"""
        from rundesk import channel

        queries = {name: query for name, _description, query in discord.QUERY_COMMANDS}
        self.assertEqual(set(channel.QUERIES), set(queries.values()))
        self.assertEqual({"status", "version", "agents", "skills", "schedules", "roles",
                          "help"},
                         set(queries))
        self.assertEqual("skills", queries["skills"])
        self.assertEqual("schedules", queries["schedules"])

    def test_one_slash_interaction_belongs_to_exactly_one_configured_surface(self):
        """R-DIS-23 — Discord delivers one bot's interaction to its simultaneous DM and
        room gateway sessions; only the configured surface may report it to Rundesk."""
        direct = SimpleNamespace(guild=None, channel=object(), channel_id=44)
        dm = SimpleNamespace(
            chose=SimpleNamespace(server=None, channel=None, dm=True)
        )
        rooms = SimpleNamespace(
            chose=SimpleNamespace(server="99", channel="44", dm=False)
        )
        self.assertTrue(discord.Agent._owns(dm, direct))
        self.assertFalse(discord.Agent._owns(rooms, direct))

        room = SimpleNamespace(
            guild=SimpleNamespace(id=99), channel=object(), channel_id=44
        )
        self.assertFalse(discord.Agent._owns(dm, room))
        self.assertTrue(discord.Agent._owns(rooms, room))

    def test_a_gateway_answer_completes_the_exact_deferred_interaction(self):
        """R-DIS-22 — a read-only result stays ephemeral and correlated to the slash
        interaction that asked; it is never posted into the public conversation."""
        class Interaction:
            def __init__(self):
                self.content = None

            async def edit_original_response(self, content):
                self.content = content

        asked = Interaction()
        client = SimpleNamespace(queries={"query-1": asked})
        asyncio.run(discord.Agent._query_result(client, {
            "type": "query-result", "conversation": "44", "query": "status",
            "ref": "query-1", "text": "ava: RUNNING",
        }))
        self.assertEqual("ava: RUNNING", asked.content)
        self.assertEqual({}, client.queries)

    def test_a_long_skills_answer_keeps_every_granted_skill(self):
        """R-DIS-36 — a large grant set remains a complete private bullet list."""
        class Followup:
            def __init__(self):
                self.messages = []

            async def send(self, content, ephemeral):
                self.messages.append((content, ephemeral))

        class Interaction:
            def __init__(self):
                self.original = None
                self.followup = Followup()

            async def edit_original_response(self, content):
                self.original = content

        granted = [f"- skill-{number:02d}-{'x' * 52}" for number in range(35)]
        answer = "\n".join(granted)
        self.assertGreater(len(answer), discord.LIMIT)
        asked = Interaction()
        client = SimpleNamespace(queries={"query-1": asked})

        asyncio.run(discord.Agent._query_result(client, {
            "type": "query-result", "conversation": "44", "query": "skills",
            "ref": "query-1", "text": answer,
        }))

        pieces = [asked.original] + [content for content, _private in
                                     asked.followup.messages]
        self.assertEqual(granted, "\n".join(pieces).splitlines())
        self.assertTrue(all(private for _content, private in asked.followup.messages))
        self.assertTrue(all(len(piece) <= discord.LIMIT for piece in pieces))
        self.assertEqual({}, client.queries)

    def test_a_read_only_command_is_deferred_and_reported_for_authorization(self):
        """R-DIS-22, R-CH-23 — Discord acknowledges promptly, while Rundesk remains the
        authority that decides whether any gateway information comes back."""
        class Response:
            def __init__(self):
                self.ephemeral = None

            async def defer(self, ephemeral):
                self.ephemeral = ephemeral

        interaction = SimpleNamespace(
            id=91, channel_id=44, user=SimpleNamespace(id=2207), response=Response()
        )
        client = SimpleNamespace(
            chose=SimpleNamespace(allow=["2207"]), queries={},
            _owns=lambda _interaction: True,
        )
        said = []
        was, discord.sys.stdout = discord.sys.stdout, _Collects(said)
        try:
            callback = discord.Agent._query_command(client, "status")
            asyncio.run(callback(interaction))
        finally:
            discord.sys.stdout = was
        record = json.loads("".join(said))
        self.assertTrue(interaction.response.ephemeral)
        self.assertIs(interaction, client.queries["91"])
        self.assertEqual({
            "type": "query", "conversation": "44", "user": "2207",
            "query": "status", "ref": "91",
        }, record)

    def test_provider_is_deferred_and_reported_for_authorized_configuration(self):
        """R-DIS-25 — the provider name crosses the seam; Discord changes nothing."""
        class Response:
            async def defer(self, ephemeral):
                self.ephemeral = ephemeral

        interaction = SimpleNamespace(
            id=92, channel_id=44, user=SimpleNamespace(id=2207), response=Response()
        )
        client = SimpleNamespace(
            chose=SimpleNamespace(allow=["2207"]), queries={},
            _owns=lambda _interaction: True,
        )
        said = []
        was, discord.sys.stdout = discord.sys.stdout, _Collects(said)
        try:
            asyncio.run(discord.Agent._provider_command(client)(
                interaction, "claude"))
        finally:
            discord.sys.stdout = was
        self.assertEqual({
            "type": "configure", "conversation": "44", "user": "2207",
            "provider": "claude", "ref": "92",
        }, json.loads("".join(said)))
        from rundesk import channel
        self.assertIsNotNone(channel.understood("".join(said)))
        self.assertTrue(interaction.response.ephemeral)
        self.assertIs(interaction, client.queries["92"])

    def test_provider_result_completes_the_exact_private_interaction(self):
        """R-DIS-25 — success or refusal is private and correlated to its command."""
        class Interaction:
            async def edit_original_response(self, content):
                self.content = content

        first, interaction = Interaction(), Interaction()
        client = SimpleNamespace(queries={"91": first, "92": interaction})
        asyncio.run(discord.Agent._configuration_result(client, {
            "type": "configure-result", "conversation": "44", "ref": "92",
            "text": "Default provider changed to claude.",
        }))
        self.assertEqual("Default provider changed to claude.", interaction.content)
        self.assertEqual({"91": first}, client.queries)
        self.assertFalse(hasattr(first, "content"))

    def test_a_gesture_from_somebody_not_allowed_is_refused_before_it_is_reported(self):
        """R-DIS-12 — somebody this channel does not allow typed `/restart` in a shared
        room and was told the agent was restarting: a promise nothing kept, and a
        confirmation to a stranger that the agent is listening. Advisory, exactly as
        `_query_command` and `_provider_command` already are — rundesk checks again and
        drops the gesture in silence."""
        class Response:
            async def send_message(self, text, ephemeral):
                self.text, self.ephemeral = text, ephemeral

        for gesture in ("stop", "forget", "restart"):
            interaction = SimpleNamespace(
                id=92, channel_id=44, user=SimpleNamespace(id=9999), response=Response()
            )
            client = SimpleNamespace(
                chose=SimpleNamespace(allow=["2207"]), _owns=lambda _interaction: True,
            )
            said = []
            was, discord.sys.stdout = discord.sys.stdout, _Collects(said)
            try:
                asyncio.run(discord.Agent._control_command(client, gesture)(interaction))
            finally:
                discord.sys.stdout = was
            self.assertIn("not available", interaction.response.text)
            self.assertEqual([], said, f"'{gesture}' from a stranger reached rundesk")

    def test_a_control_says_it_was_heard_and_never_what_it_did(self):
        """R-DIS-12 — rundesk drops a `stop` where no turn is running, so an
        acknowledgement claiming the turn is stopping is a promise nothing kept in one of
        the two ordinary cases. What a control did arrives as the turn's own outcome."""
        class Response:
            async def send_message(self, text, ephemeral):
                self.text, self.ephemeral = text, ephemeral

        interaction = SimpleNamespace(
            id=92, channel_id=44, user=SimpleNamespace(id=2207), response=Response()
        )
        client = SimpleNamespace(
            chose=SimpleNamespace(allow=["2207"]), _owns=lambda _interaction: True,
        )
        said = []
        was, discord.sys.stdout = discord.sys.stdout, _Collects(said)
        try:
            asyncio.run(discord.Agent._control_command(client, "stop")(interaction))
        finally:
            discord.sys.stdout = was
        self.assertIn("asked to stop", interaction.response.text)
        self.assertNotIn("stopping", interaction.response.text,
                         "the acknowledgement claimed an effect rundesk had not reported")
        self.assertEqual("stop", json.loads("".join(said))["control"])

    def test_shared_channel_provider_command_is_privately_refused_before_reporting(self):
        """R-DIS-25 — room access is not authority over the agent-wide default."""
        class Response:
            async def send_message(self, text, ephemeral):
                self.text, self.ephemeral = text, ephemeral

        interaction = SimpleNamespace(
            id=92, channel_id=44, user=SimpleNamespace(id=2207), response=Response()
        )
        client = SimpleNamespace(
            chose=SimpleNamespace(allow=["2207", "3308"]), queries={},
            _owns=lambda _interaction: True,
        )
        said = []
        was, discord.sys.stdout = discord.sys.stdout, _Collects(said)
        try:
            asyncio.run(discord.Agent._provider_command(client)(
                interaction, "claude"))
        finally:
            discord.sys.stdout = was
        self.assertTrue(interaction.response.ephemeral)
        self.assertIn("not available", interaction.response.text)
        self.assertEqual({}, client.queries)
        self.assertEqual([], said)

    def test_where_it_listens_is_its_own_option_and_never_rundesks(self):
        """R-CAD-13 — `--server` and `--dm` are Discord's words, parsed here."""
        chose = discord.options(["--server", "9930", "--channel", "1180"])
        self.assertEqual("9930", chose.server)
        self.assertEqual("1180", chose.channel)
        self.assertFalse(chose.dm)

    def test_an_option_it_does_not_understand_is_reported_rather_than_ignored(self):
        """R-CAD-9 — an owner who mistyped an option must hear about it while they are
        standing at the terminal, not by the agent being deaf later."""
        chose = discord.options(["--nonsense", "x"])
        self.assertEqual(["--nonsense", "x"], chose.unknown)

    def test_the_credential_is_read_from_the_environment_and_never_an_argument(self):
        """R-CAD-11 — a command line is readable through the process list and lands in
        shell history."""
        chose = discord.options([])
        self.assertEqual("DISCORD_TOKEN", chose.token_from,
                         "it stopped naming a variable to read the credential from")

    def test_a_supervised_gateway_finds_its_token_without_a_shell(self):
        """R-CAD-11 — the machine that keeps an agent up starts it with a built
        environment, so a variable exported in somebody's terminal is one the agent will
        never see once it is running the only way it is meant to. A file the owner
        already controls is the other place, and nothing here ever writes it."""
        import os
        import tempfile

        home = Path(tempfile.mkdtemp(prefix="rundesk-discord-token-"))
        self.addCleanup(lambda: [f.unlink() for f in home.iterdir()] and home.rmdir())
        (home / discord.TOKEN_FILE).write_text("  a-token-from-a-file  \n")
        was_home = os.environ.get("RUNDESK_CHANNEL_HOME")
        was_token = os.environ.pop("DISCORD_TOKEN", None)
        os.environ["RUNDESK_CHANNEL_HOME"] = str(home)
        try:
            self.assertEqual("a-token-from-a-file", discord.token_for(discord.options([])))
        finally:
            os.environ.pop("RUNDESK_CHANNEL_HOME", None)
            if was_home is not None:
                os.environ["RUNDESK_CHANNEL_HOME"] = was_home
            if was_token is not None:
                os.environ["DISCORD_TOKEN"] = was_token

    def test_the_variable_wins_over_the_file(self):
        """R-CAD-11 — a person at a terminal is saying what to use right now, and a file
        left over from last month must not quietly override them."""
        import os

        was = os.environ.get("DISCORD_TOKEN")
        os.environ["DISCORD_TOKEN"] = "from-the-shell"
        try:
            self.assertEqual("from-the-shell", discord.token_for(discord.options([])))
        finally:
            os.environ.pop("DISCORD_TOKEN", None)
            if was is not None:
                os.environ["DISCORD_TOKEN"] = was

    def test_no_option_takes_a_secret_as_a_value(self):
        """R-CAD-11 — the whole point: there is no way to type one, so nobody can. What
        the owner may say is *which variable* holds it, never what is in it."""
        said = discord.options(["--token-from", "SOMETHING_ELSE"])
        self.assertEqual("SOMETHING_ELSE", said.token_from)
        self.assertEqual({"bot", "server", "channel", "dm", "token_from", "activity",
                          "unknown"}, set(vars(said)),
                         "an option appeared that could carry a secret as its value")


@unittest.skipIf(discord is None, "discord.py is not installed — run ./install.sh")
class WhatAnOwnerWhoSaidNothingGets(unittest.TestCase):
    """R-CH-6 — the defaults, which is where this adapter and the core disagreed."""

    def settled(self, argv=(), settings=None):
        return discord.settled(discord.options(list(argv)), settings or {})

    def test_what_the_agent_is_doing_is_shown_unless_somebody_said_otherwise(self):
        """The core already decided this: `answering` streams what the agent is doing
        unless the channel record turns it off, because a room that goes quiet for four
        minutes and then answers looks broken. The adapter defaulted to `off` and dropped
        every line of it — two defaults for one idea, and the one further from the owner
        won. Nothing appeared, and nothing said why."""
        self.assertEqual(discord.GROWS, self.settled().activity)

    def test_the_quiet_way_of_showing_it_is_the_default_one(self):
        """`grows` edits one message so a turn reads as a single thing happening; `posts`
        fills the room. On by default is only defensible as the quiet one."""
        self.assertNotEqual(discord.POSTS, self.settled().activity)

    def test_a_stale_discord_off_setting_does_not_override_the_channel_choice(self):
        """R-CH-6 — the channel record is the owner's activity choice. Discord persisted
        its old default beside that choice, so an upgrade must ignore the contradiction
        without rewriting stored data."""
        self.assertEqual(discord.GROWS,
                         self.settled(settings={"activity": "off"}).activity)

    def test_the_adapter_does_not_offer_a_second_switch_that_turns_activity_off(self):
        """R-CH-6 — `--no-activity` belongs to the channel command. A second Discord-only
        switch can disagree with the record that `channels show` reports."""
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            discord.options(["--activity", "off"])

    def test_what_was_typed_wins_over_what_was_written_down(self):
        """Both places say the same words, so an owner who set it in either gets it — and
        the one they just typed is the one they meant."""
        self.assertEqual(discord.POSTS,
                         self.settled(["--activity", "posts"],
                                      {"activity": "off"}).activity)


@unittest.skipIf(discord is None, "discord.py is not installed — run ./install.sh")
class WhatItSaysBack(unittest.TestCase):
    """R-CAD-1 — what it reports is what the seam understands, and nothing else."""

    def test_everything_it_reports_is_a_record_the_seam_knows(self):
        """R-CAD-1 — a record of a kind nobody knows is kept and acted on by nothing, so
        an adapter reporting one is talking to itself."""
        from rundesk import channel

        said = []
        was, discord.sys.stdout = discord.sys.stdout, _Collects(said)
        try:
            discord.say(type="ready")
            discord.say(type="arrived", conversation="1", user="2", text="hi", ref="3")
            discord.say(type="gone", why="the socket closed")
        finally:
            discord.sys.stdout = was
        for line in said:
            if line.strip():
                self.assertIsNotNone(channel.understood(line),
                                     f"it reported something the seam cannot act on: {line}")

    def test_what_it_reports_is_one_object_to_a_line(self):
        """R-CAD-1 — a record split across lines is one nothing can read."""
        said = []
        was, discord.sys.stdout = discord.sys.stdout, _Collects(said)
        try:
            discord.say(type="arrived", conversation="1", user="2",
                        text="two\nlines\nof it", ref="3")
        finally:
            discord.sys.stdout = was
        self.assertEqual(1, len([one for one in said if one.strip()]))
        self.assertEqual("two\nlines\nof it", json.loads(said[0])["text"])


class _Collects:
    """Stands in for stdout, so what the adapter reports can be read back."""

    def __init__(self, into):
        self._into = into

    def write(self, said):
        self._into.append(said)

    def flush(self):
        pass


class _Surface:
    """A Discord client as `_room_named` and `_where_to_write` use one.

    **It records rather than refuses.** A fake that raises to prove a guard held proves
    nothing: the adapter reaches for a person inside `contextlib.suppress(Exception)`, so a
    raised `AssertionError` is swallowed and the call returns `None` either way — the same
    answer a held guard gives. Every reach is written down instead, and the test asserts on
    what came back and on what was never opened, which a deleted guard cannot fake.
    """

    def __init__(self, dm, allow, channel=None, conversation="the-conversation"):
        self.guilds = ()
        self.chose = SimpleNamespace(dm=dm, allow=list(allow), server=None)
        self.channel = channel
        self.conversation = conversation
        self.channels_asked = []
        self.people_asked = []
        self.dms_opened = []

    async def wait_until_ready(self):
        return None

    async def _room_named(self, said):
        """The real one, so driving `_where_to_write` still tests the resolution itself."""
        return await discord.Agent._room_named(self, said)

    async def fetch_channel(self, where):
        self.channels_asked.append(where)
        if self.channel is None:
            raise RuntimeError("not a channel")
        return self.channel

    async def fetch_user(self, where):
        self.people_asked.append(where)
        return _Person(self, where)

    def get_channel(self, where):
        return self.conversation


class _Person:
    """Someone a DM could be opened with — who records that it was."""

    def __init__(self, surface, who):
        self.surface = surface
        self.id = who

    async def create_dm(self):
        self.surface.dms_opened.append(self.id)
        return f"dm-with-{self.id}"


@unittest.skipIf(discord is None, "discord.py is not installed — run ./install.sh")
class WhichRoomAWordMeans(unittest.TestCase):
    """R-CAD-16 — a schedule names a place, and this is what turns that word into a room."""

    def test_a_name_with_its_hash_and_without_are_one_room(self):
        """The hash is how Discord writes a channel and how anybody types one; it is not part
        of the name, so asking for it either way asks for the same room."""
        self.assertTrue(discord.room_matches("#operations", "operations"))
        self.assertTrue(discord.room_matches("operations", "operations"))

    def test_a_room_is_found_however_it_was_capitalised(self):
        """Nobody types a room name the way the server stores it."""
        self.assertTrue(discord.room_matches("#Operations", "operations"))
        self.assertTrue(discord.room_matches("ops", "OPS"))

    def test_a_different_room_is_not_this_one(self):
        """The half that matters: a word that names another room must not match, or a daily
        report lands somewhere nobody chose — which is the whole failure this exists to end."""
        self.assertFalse(discord.room_matches("#operations", "operations-archive"))
        self.assertFalse(discord.room_matches("#ops", "operations"))
        self.assertFalse(discord.room_matches("", "operations"))

    def test_what_an_owner_typed_is_taken_as_they_typed_it(self):
        """Spaces around it are typing, not the name."""
        self.assertTrue(discord.room_matches("  #operations  ", "operations"))

    def test_a_dm_place_that_is_a_user_id_opens_that_persons_dm(self):
        """R-CAD-16 — schedule `--in` is often the same user snowflake as `--allow`.

        That is not a channel id. `fetch_channel` fails; without the user→DM path a finished
        schedule reports "nowhere to write" and the owner never sees the answer. Winston
        schedules that worked used a DM *channel* id; Markus's used a *user* id and silently
        posted nowhere. Both words must resolve on a DM surface.
        """
        surface = _Surface(dm=True, allow=["279024636254224384"])
        found, why = asyncio.run(
            discord.Agent._room_named(surface, "279024636254224384"))
        self.assertEqual("dm-with-279024636254224384", found)
        self.assertIsNone(why)
        self.assertEqual([279024636254224384], surface.people_asked)
        self.assertEqual([279024636254224384], surface.dms_opened)

    def test_a_dm_channel_id_still_resolves_as_a_channel(self):
        """R-CAD-16 — the working Winston shape: place is the DM channel snowflake.

        The channel is tried first and answers, so nobody is looked up and no DM is opened:
        asserted on the empty records rather than on a fake that refuses to be called, which
        the adapter's `suppress(Exception)` would swallow.
        """
        surface = _Surface(dm=True, allow=["279024636254224384"],
                           channel="channel-1529678042396622928")
        found, why = asyncio.run(
            discord.Agent._room_named(surface, "1529678042396622928"))
        self.assertEqual("channel-1529678042396622928", found)
        self.assertIsNone(why)
        self.assertEqual([1529678042396622928], surface.channels_asked)
        self.assertEqual([], surface.people_asked)
        self.assertEqual([], surface.dms_opened)

    def test_a_user_id_is_not_opened_as_a_dm_from_a_room_channel(self):
        """A failed room id must not become a private message (R-CH-4, R-CAD-16).

        Driven through `_where_to_write`, because the guarantee is about where the report
        landed, not about which method ran: a room channel handed a user snowflake writes in
        the conversation it came from and opens no private message with anybody. If the
        surface check were deleted the id is on the allow list, so a DM *would* open — this
        fails on the DM that came back and on the DM that was opened.
        """
        surface = _Surface(dm=False, allow=["279024636254224384"])
        with contextlib.redirect_stderr(io.StringIO()) as said:
            where = asyncio.run(discord.Agent._where_to_write(
                surface, {"place": "279024636254224384", "conversation": "77"}))
        self.assertEqual("the-conversation", where)
        self.assertEqual([], surface.people_asked)
        self.assertEqual([], surface.dms_opened)
        self.assertIn("could not find '279024636254224384'", said.getvalue())

    def test_a_dm_place_refuses_a_user_who_is_not_allowed(self):
        """Schedules must not open DMs with people the channel does not authorize.

        The refusal is observable twice: the report goes to the conversation instead, and
        the owner is told the id was declined rather than missing — "could not find" is the
        sentence a typo produces, and sending an owner on a wrong-id hunt is the
        misdiagnosis this path exists to end.
        """
        surface = _Surface(dm=True, allow=["111"])
        with contextlib.redirect_stderr(io.StringIO()) as said:
            where = asyncio.run(discord.Agent._where_to_write(
                surface, {"place": "279024636254224384", "conversation": "77"}))
        self.assertEqual("the-conversation", where)
        self.assertEqual([], surface.people_asked)
        self.assertEqual([], surface.dms_opened)
        self.assertIn("is not on this channel's allowed list", said.getvalue())
        self.assertNotIn("could not find", said.getvalue())

    def test_a_room_that_is_simply_missing_is_not_reported_as_a_refusal(self):
        """The other half of the refusal note: a word nobody can find still says so.

        Without this the refusal sentence could swallow every failure and the two would be
        indistinguishable again, in the other direction.
        """
        surface = _Surface(dm=True, allow=["279024636254224384"])
        with contextlib.redirect_stderr(io.StringIO()) as said:
            where = asyncio.run(discord.Agent._where_to_write(
                surface, {"place": "#no-such-room", "conversation": "77"}))
        self.assertEqual("the-conversation", where)
        self.assertIn("could not find '#no-such-room'", said.getvalue())
        self.assertNotIn("allowed list", said.getvalue())


@unittest.skipIf(discord is None, "discord.py is not installed — run ./install.sh")
class WhatTheOwnerIsTold(unittest.TestCase):
    """R-DIS-15, R-DIS-16 — coming up, going down, and closing the connection either way."""

    def test_a_notice_for_the_owner_is_sent_to_them_and_starts_no_conversation(self):
        """R-DIS-38 — bookkeeping about the agent reaches the owner privately, and a
        record with no conversation must not leave a live exchange nobody is in."""
        class Told:
            live: dict = {}

            def __init__(self):
                self.said: list = []
                self.who: list = []

            async def _tell_the_owner(self, it, who=None):
                self.said.append(it)
                self.who.append(who)

        told = Told()
        asyncio.run(discord.Agent.told(
            told, {"type": "owner-notice", "text": "🧩 **Skill added** — `alpha`"}))

        self.assertEqual(["🧩 **Skill added** — `alpha`"], told.said)
        self.assertEqual({}, told.live)

    def test_a_notice_for_the_owner_too_long_for_one_message_is_split(self):
        """R-DIS-13 — a catalog takes away every skill it brought in one go, and Discord
        refuses a message over its limit outright rather than shortening it."""
        class Told:
            live: dict = {}

            def __init__(self):
                self.said: list = []
                self.who: list = []

            async def _tell_the_owner(self, it, who=None):
                self.said.append(it)
                self.who.append(who)

        lines = "\n".join(f"🗑️ **Skill removed** — `{one}`" for one in range(200))
        told = Told()
        asyncio.run(discord.Agent.told(told, {"type": "owner-notice", "text": lines}))

        self.assertGreater(len(told.said), 1, "a notice over the limit was sent whole")
        self.assertTrue(all(len(one) <= discord.LIMIT for one in told.said))
        self.assertEqual(
            lines.splitlines(),
            [line for piece in told.said for line in piece.splitlines()],
            "splitting lost a skill the owner was owed")

    def test_a_notice_for_the_owner_with_nothing_in_it_is_not_sent(self):
        """R-DIS-38 — an empty message is one Discord refuses, and one nobody can read."""
        class Told:
            live: dict = {}

            def __init__(self):
                self.said: list = []
                self.who: list = []

            async def _tell_the_owner(self, it, who=None):
                self.said.append(it)
                self.who.append(who)

        told = Told()
        asyncio.run(discord.Agent.told(told, {"type": "owner-notice", "text": ""}))
        self.assertEqual([], told.said)

    def test_a_notice_naming_somebody_is_carried_to_that_person(self):
        """R-DIS-39 — an introduction is for the person who has just been allowed to reach
        the agent, and a gateway notice still reaches whoever the surface calls the owner."""
        class Told:
            live: dict = {}

            def __init__(self):
                self.said: list = []
                self.who: list = []

            async def _tell_the_owner(self, it, who=None):
                self.said.append(it)
                self.who.append(who)

        told = Told()
        asyncio.run(discord.Agent.told(
            told, {"type": "owner-notice", "text": "Hello, I am Ava.", "user": "1180"}))
        self.assertEqual(["1180"], told.who)

        again = Told()
        asyncio.run(discord.Agent.told(
            again, {"type": "owner-notice", "text": "🟢 **Gateway online**"}))
        self.assertEqual([None], again.who, "a notice for nobody in particular named one")

    def test_a_notice_naming_somebody_this_channel_does_not_allow_is_refused(self):
        """R-DIS-39, R-CAD-16 — a bot that would message any snowflake it was handed is
        one bug away from messaging a stranger, so the adapter asks its own list too."""
        kept, fetched = [], []

        class Surface:
            chose = SimpleNamespace(allow=["42"])

            async def fetch_user(self, who):
                fetched.append(who)
                raise AssertionError("a user outside the allowed list was reached for")

        with mock.patch.object(
                discord, "note",
                side_effect=lambda said, level="WARNING": kept.append((said, level))):
            asyncio.run(discord.Agent._tell_the_owner(
                Surface(), "Hello, I am Ava.", "9999"))
        self.assertEqual([], fetched)
        self.assertIn("not telling 9999", kept[0][0])

    def test_a_notice_naming_an_allowed_person_reaches_that_person(self):
        """R-DIS-39 — and never the first allowed user instead."""
        sent = []

        class Person:
            def __init__(self, who):
                self.who = who

            async def send(self, said):
                sent.append((self.who, said))

            def __str__(self):
                return f"person {self.who}"

        class Surface:
            chose = SimpleNamespace(allow=["42", "1180"])

            async def fetch_user(self, who):
                return Person(who)

        with mock.patch.object(discord, "note", side_effect=lambda *a, **kw: None):
            asyncio.run(discord.Agent._tell_the_owner(
                Surface(), "Hello, I am Ava.", "1180"))
        self.assertEqual([(1180, "Hello, I am Ava.")], sent)

    def test_successfully_telling_the_owner_is_routine_channel_activity(self):
        """R-GW-44 — a startup or shutdown notice that lands is not a warning."""
        kept = []

        class Person:
            async def send(self, _said):
                return None

            def __str__(self):
                return "owner"

        class Surface:
            chose = SimpleNamespace(allow=["42"])

            async def fetch_user(self, _who):
                return Person()

        with mock.patch.object(
                discord, "note",
                side_effect=lambda said, level="WARNING": kept.append((said, level))):
            asyncio.run(discord.Agent._tell_the_owner(Surface(), "Rundesk is online."))
        self.assertEqual(
            [("told the owner (owner): Rundesk is online.", "INFO")], kept)

    class Stand:
        """Exactly the surface `going` touches, and no more — a stand-in more generous
        than the real thing is what hides a whole feature behind a green suite."""

        def __init__(self, slow=0.0, claims=True):
            self.live, self.closed, self.greeted, self._slow = {}, False, [], slow
            self._claims = claims

        def _claim(self, what):
            return self._claims

        async def _tell_the_owner(self, said, who=None):
            self.greeted.append(said)
            await asyncio.sleep(self._slow)

        async def close(self):
            self.closed = True

    def test_going_down_closes_the_connection_even_when_the_goodbye_does_not_land(self):
        """R-DIS-16 — the goodbye had the whole shutdown budget to itself, so an owner who
        could not be reached spent all of it and `close()` was never reached at all. The
        socket was then dropped rather than closed, and Discord went on showing the bot as
        online long after the gateway behind it had gone."""
        it = self.Stand(slow=discord.GOODBYE_SECONDS * 2)
        with contextlib.suppress(BaseException):
            asyncio.run(asyncio.wait_for(discord.Agent.going(it),
                                         timeout=discord.GOODBYE_SECONDS))
        self.assertTrue(it.closed, "the connection was dropped rather than closed")

    def test_saying_goodbye_is_bounded_well_inside_what_rundesk_allows(self):
        """R-DIS-16 — the close has to fit in what is left after the message, so the
        message cannot be given the whole of it."""
        self.assertLess(discord.TELLING_SECONDS, discord.GOODBYE_SECONDS)

    def test_a_goodbye_that_lands_is_still_said(self):
        """The bound is on how long it may take, never on whether it happens."""
        it = self.Stand()
        asyncio.run(discord.Agent.going(it))
        self.assertEqual(1, len(it.greeted))
        self.assertTrue(it.closed)

    def test_update_maintenance_is_not_announced_as_an_unexplained_outage(self):
        """R-UPD-43"""
        with tempfile.TemporaryDirectory() as temporary:
            marker = Path(temporary) / "maintenance"
            marker.touch()
            with mock.patch.dict(
                    os.environ, {"RUNDESK_MAINTENANCE": str(marker)}, clear=False):
                it = self.Stand()
                asyncio.run(discord.Agent.going(it))
        self.assertIn("update", it.greeted[0].lower())
        self.assertIn("back shortly", it.greeted[0].lower(),
                      "the owner was not told the gateway is coming back")
        self.assertNotIn("offline", it.greeted[0].lower())

    def test_going_down_cancels_what_a_conversation_was_still_running(self):
        """R-CH-11 — nothing of this channel's is left running once it goes."""
        held = discord.Live()
        held.typing, held.pacing = _Cancels(), _Cancels()
        it = self.Stand()
        it.live = {"1180": held}
        asyncio.run(discord.Agent.going(it))
        self.assertEqual([True, True], [held.typing.cancelled, held.pacing.cancelled])

    class Connects:
        """The surface `on_ready` touches."""

        class User:
            name = "The Owner's Bot"

            async def edit(self, **given):
                pass

        def __init__(self, claims=True):
            self.greeted, self.said = False, []
            self._claims = claims
            self.user = self.User()

        def _claim(self, what):
            return self._claims

        async def change_presence(self, **kw):
            pass

        async def _tell_the_owner(self, said, who=None):
            self.said.append(said)

    def test_connecting_never_edits_the_bot_profile(self):
        """R-DIS-32 — Discord account identity belongs to its owner, not Rundesk."""
        changed = []

        class User:
            name = "The Owner's Bot"

            async def edit(self, **given):
                changed.append(given)

        it = self.Connects()
        it.user = User()
        with mock.patch.dict(os.environ, {"RUNDESK_AGENT": "winston"}, clear=False), \
                mock.patch.object(discord, "say"):
            asyncio.run(discord.Agent.on_ready(it))
            asyncio.run(discord.Agent.on_ready(it))
        self.assertEqual([], changed)

    def test_only_one_adapter_of_a_gateway_greets_the_owner(self):
        """R-DIS-15 — an agent reachable both by direct message and in rooms runs *two* of
        these, each with its own `greeted`, so the owner was told the gateway was online
        twice about a minute apart — which reads as it having restarted in between. The
        claim is shared by every adapter of one gateway."""
        it, second = self.Connects(), self.Connects(claims=False)
        was, discord.say = discord.say, lambda **kw: None
        try:
            asyncio.run(discord.Agent.on_ready(it))
            asyncio.run(discord.Agent.on_ready(second))
        finally:
            discord.say = was
        self.assertEqual(1, len(it.said))
        self.assertEqual([], second.said, "the second adapter greeted as well")

    def test_a_gateway_returning_from_an_update_says_the_update_landed(self):
        """R-UPD-43"""
        with tempfile.TemporaryDirectory() as temporary:
            marker = Path(temporary) / "maintenance"
            marker.touch()
            with mock.patch.dict(
                    os.environ, {"RUNDESK_MAINTENANCE": str(marker)}, clear=False), \
                    mock.patch.object(discord, "say"):
                # An install told no version says the shorter sentence, and this case is
                # about the marker rather than the version — so it states which of the two
                # it is arranging rather than inheriting whatever ran it (R-DIS-26).
                for named in ("RUNDESK_VERSION", "RUNDESK_RELEASE_URL"):
                    os.environ.pop(named, None)
                it = self.Connects()
                asyncio.run(discord.Agent.on_ready(it))
        self.assertIn("new rundesk update installed", it.said[0].lower())
        self.assertTrue(it.said[0].startswith("👋 **I'm back**"))
        self.assertNotIn("🟢", it.said[0])
        self.assertFalse(marker.exists(), "completed maintenance stayed attached to the gateway")

    def test_a_gateway_returning_from_an_update_links_the_version_now_listening(self):
        """R-DIS-26 — the return notice is the only thing every returning gateway sends,
        including after an unattended update no conversation started. Told the version and
        the link by rundesk: an adapter that asked a forge what is newest would name a
        release this gateway is not running."""
        with tempfile.TemporaryDirectory() as temporary:
            marker = Path(temporary) / "maintenance"
            marker.touch()
            with mock.patch.dict(os.environ, {
                        "RUNDESK_MAINTENANCE": str(marker),
                        "RUNDESK_VERSION": "0.15.0",
                        "RUNDESK_RELEASE_URL":
                            "https://github.com/rundesk-ai/rundesk-cli/releases/tag/v0.15.0",
                    }, clear=False), \
                    mock.patch.object(discord, "say"):
                it = self.Connects()
                asyncio.run(discord.Agent.on_ready(it))
        self.assertIn(
            "[v0.15.0](https://github.com/rundesk-ai/rundesk-cli/releases/tag/v0.15.0)",
            it.said[0],
        )
        self.assertIn("update installed", it.said[0].lower())

    def test_a_gateway_told_only_a_version_still_names_it(self):
        """An install with no link to offer says which release is listening in plain text.
        Saying nothing would make the useful half of the notice depend on the other."""
        with tempfile.TemporaryDirectory() as temporary:
            marker = Path(temporary) / "maintenance"
            marker.touch()
            with mock.patch.dict(os.environ, {
                        "RUNDESK_MAINTENANCE": str(marker),
                        "RUNDESK_VERSION": "0.15.0",
                    }, clear=False), \
                    mock.patch.object(discord, "say"):
                # Inside the patch, which restores the whole environment on the way out.
                os.environ.pop("RUNDESK_RELEASE_URL", None)
                it = self.Connects()
                asyncio.run(discord.Agent.on_ready(it))
        self.assertIn("v0.15.0", it.said[0])
        self.assertNotIn("](", it.said[0], "a link was made out of nothing")

    def test_an_ordinary_startup_adds_no_update_wording_and_no_release_link(self):
        """R-DIS-27 — a reconnection is not a release. Discord drops a session it will not
        resume on its own over the weeks a channel is held open, and a version offered
        there would read as one having just been installed."""
        with mock.patch.dict(os.environ, {"RUNDESK_VERSION": "0.15.0"}, clear=False), \
                mock.patch.object(discord, "say"):
            # Inside the patch, which restores the whole environment on the way out.
            os.environ.pop("RUNDESK_MAINTENANCE", None)
            it = self.Connects()
            asyncio.run(discord.Agent.on_ready(it))
        self.assertNotIn("maintenance", it.said[0].lower())
        self.assertNotIn("0.15.0", it.said[0])
        self.assertNotIn("releases/tag", it.said[0])

    def test_only_one_adapter_of_a_gateway_says_the_goodbye(self):
        """R-DIS-15 — the same on the way out, and for a worse reason than tidiness: two
        goodbyes for one shutdown read as two gateways."""
        quiet = self.Stand(claims=False)
        asyncio.run(discord.Agent.going(quiet))
        self.assertEqual([], quiet.greeted, "a second adapter said goodbye too")
        self.assertTrue(quiet.closed, "not claiming the goodbye stopped it closing")

    def test_the_second_adapter_to_ask_does_not_get_the_claim(self):
        """Driven against a real directory, because what is relied on is the operating
        system's behaviour and a stand-in for it would be relying on itself.

        **This proves the exclusion, not the atomicity.** Checking and then creating gives
        the same answer as creating-exclusively when the two happen one after another, which
        is all a test can arrange without a race it cannot make reliable. Why the one
        operation rather than the two is in the source, where the reader who would break it
        is looking — two adapters coming up together would both read "nobody has greeted
        yet"."""
        import os
        import tempfile

        where = tempfile.mkdtemp(prefix="rundesk-greeting-")
        self.addCleanup(shutil.rmtree, where, True)
        was = os.environ.get("RUNDESK_HOME")
        was_gateway = os.environ.get("RUNDESK_GATEWAY")
        os.environ["RUNDESK_HOME"] = where
        os.environ["RUNDESK_GATEWAY"] = "this-gateway"
        self.addCleanup(lambda: os.environ.__setitem__("RUNDESK_HOME", was)
                        if was is not None else os.environ.pop("RUNDESK_HOME", None))
        self.addCleanup(lambda: os.environ.__setitem__("RUNDESK_GATEWAY", was_gateway)
                        if was_gateway is not None else os.environ.pop("RUNDESK_GATEWAY", None))

        first = discord.Agent._claim(object(), "online")
        second = discord.Agent._claim(object(), "online")
        self.assertTrue(first, "the first adapter did not get the greeting")
        self.assertFalse(second, "both adapters got it")
        # Coming up and going down are claimed apart, so an adapter that came up second and
        # said no hello can still be the one that says the goodbye.
        self.assertTrue(discord.Agent._claim(object(), "offline"))

    def test_a_successor_gateway_gets_its_own_claim(self):
        """R-DIS-15 — a claim belongs to one gateway lifetime, not to the run directory.

        The run directory deliberately survives a stop: it carries the lock and the
        successor's record. A static marker there therefore silenced every real startup
        after the first one, even though both new adapters connected successfully."""
        import os
        import tempfile

        where = tempfile.mkdtemp(prefix="rundesk-greeting-")
        self.addCleanup(shutil.rmtree, where, True)
        was_home = os.environ.get("RUNDESK_HOME")
        was_gateway = os.environ.get("RUNDESK_GATEWAY")
        os.environ["RUNDESK_HOME"] = where
        os.environ["RUNDESK_GATEWAY"] = "first"
        self.addCleanup(lambda: os.environ.__setitem__("RUNDESK_HOME", was_home)
                        if was_home is not None else os.environ.pop("RUNDESK_HOME", None))
        self.addCleanup(lambda: os.environ.__setitem__("RUNDESK_GATEWAY", was_gateway)
                        if was_gateway is not None else os.environ.pop("RUNDESK_GATEWAY", None))

        self.assertTrue(discord.Agent._claim(object(), "online"))
        self.assertFalse(discord.Agent._claim(object(), "online"),
                         "the second adapter of one gateway also claimed the greeting")
        os.environ["RUNDESK_GATEWAY"] = "successor"
        self.assertTrue(discord.Agent._claim(object(), "online"),
                        "the predecessor's claim silenced the successor gateway")

    def test_nowhere_to_claim_in_means_greeting_rather_than_silence(self):
        """Being told once too often is a smaller failure than never being told a gateway
        came up at all."""
        import os

        was = os.environ.pop("RUNDESK_HOME", None)
        self.addCleanup(lambda: os.environ.__setitem__("RUNDESK_HOME", was)
                        if was is not None else None)
        self.assertTrue(discord.Agent._claim(object(), "online"))

    def test_the_owner_is_told_the_agent_came_up_once_and_not_once_per_reconnect(self):
        """R-DIS-15 — this runs on every connection, not only the first: a session Discord
        will not resume is a fresh one, and over the weeks a channel is held open that
        happens on its own. An owner told "the gateway is up" after a blip is told about
        something that did not happen, and there is no going-down message to pair it
        with."""
        it = self.Connects()
        said = []
        was, discord.say = discord.say, lambda **kw: said.append(kw)
        try:
            asyncio.run(discord.Agent.on_ready(it))
            asyncio.run(discord.Agent.on_ready(it))
        finally:
            discord.say = was
        self.assertEqual(1, len(it.said), "a reconnection was announced as coming up")
        self.assertEqual([{"type": "ready"}, {"type": "ready"}], said,
                         "rundesk stopped being told the connection came back")


class _Cancels:
    """Stands in for a task, so cancelling one can be asserted without a loop."""

    def __init__(self):
        self.cancelled = False

    def cancel(self):
        self.cancelled = True


@unittest.skipIf(discord is None, "discord.py is not installed — run ./install.sh")
class WhatWasActuallyAsked(unittest.TestCase):
    """R-CH-1 — the naming is not the ask, and everything else is."""

    def test_the_naming_is_taken_out(self):
        self.assertEqual("what changed today?",
                         discord._without_mentions("<@42> what changed today?", 42))
        self.assertEqual("what changed today?",
                         discord._without_mentions("<@!42> what changed today?", 42))

    def test_somebody_else_named_in_the_question_is_left_alone(self):
        """Every mention used to go: "ask <@alice> to review it" reached the brain as
        "ask  to review it", so it answered a question a word short of the one asked."""
        self.assertEqual("ask <@7> to review it",
                         discord._without_mentions("<@42> ask <@7> to review it", 42))

    def test_words_that_merely_look_like_a_naming_survive(self):
        """Everything between a literal `<@` and the next `>` went with the mentions, so a
        message about `a<@b` arrived as `ab` — text nobody wrote, silently."""
        self.assertEqual("fix the guard: if (a <@ b) return; and log it",
                         discord._without_mentions(
                             "<@42> fix the guard: if (a <@ b) return; and log it", 42))

    def test_with_nobody_to_strip_what_was_said_is_handed_over_as_typed(self):
        """Guessing at which mention was ours is worse than leaving one in."""
        self.assertEqual("<@42> what changed?",
                         discord._without_mentions("<@42> what changed?", None))


@unittest.skipIf(discord is None, "discord.py is not installed — run ./install.sh")
class OutboundAttachmentsAreBoundToValidatedBytes(unittest.TestCase):
    """R-CH-18 — validation and delivery name the same immutable byte snapshot."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="rundesk-outbound-")
        self.addCleanup(self.temporary.cleanup)
        self.where = Path(self.temporary.name)

    @staticmethod
    def _declared(at):
        payload = at.read_bytes()
        return {
            "name": at.name,
            "at": str(at.resolve()),
            "bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        }

    def test_an_attachment_changed_after_validation_is_not_sent(self):
        parent = self.where / "exports"
        parent.mkdir()
        approved = parent / "approved.pdf"
        approved.write_bytes(b"approved")
        declared = self._declared(approved)
        outside = self.where / "outside"
        outside.mkdir()
        (outside / approved.name).write_bytes(b"private replacement")
        parent.rename(self.where / "held-exports")
        parent.symlink_to(outside, target_is_directory=True)

        with contextlib.redirect_stderr(io.StringIO()):
            attached = discord._outbound_attachment(declared)

        self.assertIsNone(attached)

    def test_the_verified_snapshot_does_not_change_with_its_source(self):
        approved = self.where / "approved.pdf"
        approved.write_bytes(b"approved")

        attached = discord._outbound_attachment(self._declared(approved))
        def close_snapshot():
            attached.close()
            attached.fp.close()
        self.addCleanup(close_snapshot)
        approved.write_bytes(b"changed later")
        attached.fp.seek(0)

        self.assertEqual(b"approved", attached.fp.read())

    def test_discord_verification_leaves_the_event_loop_free(self):
        approved = self.where / "approved.pdf"
        approved.write_bytes(b"approved")
        declared = self._declared(approved)
        entered = threading.Event()
        release = threading.Event()
        verify = discord._outbound_attachment
        sent = []

        def slow(attachment):
            entered.set()
            release.wait(1)
            return verify(attachment)

        class Room:
            id = 7

            async def send(self, content, reference=None, mention_author=False, files=None):
                sent.extend(files or ())
                return SimpleNamespace(id=8)

        class Turn:
            async def _where_to_write(self, _it):
                return Room()

        async def prove():
            async def advance():
                self.assertTrue(await asyncio.to_thread(entered.wait, 0.2))
                release.set()

            with mock.patch.object(discord, "_outbound_attachment", side_effect=slow):
                posting = asyncio.create_task(discord.Agent._post(
                    Turn(), {"conversation": "7"}, "answer", files=[declared]))
                await asyncio.wait_for(advance(), timeout=0.3)
                await posting
                self.assertTrue(sent)
                self.assertTrue(all(attached.fp.closed for attached in sent))

        with contextlib.redirect_stderr(io.StringIO()):
            asyncio.run(prove())

    def test_a_later_attachment_failure_closes_an_earlier_snapshot(self):
        """R-CH-12, R-CH-18 — partial preparation cannot leak verified bytes."""
        approved = self.where / "approved.pdf"
        approved.write_bytes(b"approved")
        declared = self._declared(approved)
        verify = discord._outbound_attachment
        made = []

        def prepare(attachment):
            if made:
                raise RuntimeError("second preparation failed")
            ready = verify(attachment)
            made.append(ready)
            return ready

        class Room:
            id = 7

            async def send(self, content, reference=None, mention_author=False, files=None):
                return SimpleNamespace(id=8)

        class Turn:
            async def _where_to_write(self, _it):
                return Room()

        with contextlib.redirect_stderr(io.StringIO()), mock.patch.object(
                discord, "_outbound_attachment", side_effect=prepare):
            posted = asyncio.run(discord.Agent._post(
                Turn(), {"conversation": "7"}, "answer", files=[declared, declared]))

        self.assertEqual(8, posted.id)
        self.assertTrue(made[0].fp.closed)


@unittest.skipIf(discord is None, "discord.py is not installed — run ./install.sh")
class TwoThingsAttachedToOneMessage(unittest.TestCase):
    """R-CH-17 — what a person attached reaches the agent, and so does the other one."""

    def setUp(self):
        import tempfile

        self.where = Path(tempfile.mkdtemp(prefix="rundesk-discord-attached-"))
        self.addCleanup(lambda: [one.unlink() for one in self.where.iterdir()]
                        and self.where.rmdir())

    def test_two_names_that_rebuild_to_one_are_two_files(self):
        """`report v2.csv` and `report-v2.csv` are both `report-v2.csv` once a filename has
        been rebuilt into something that can only be a filename — so the second was written
        over the first, and the agent was handed two names that were one file. It opened
        the right name and read the other one's contents."""
        first = discord._somewhere_new(self.where, discord._plain_name("report v2.csv"))
        first.write_text("the first one")
        second = discord._somewhere_new(self.where, discord._plain_name("report-v2.csv"))
        second.write_text("the second one")
        self.assertNotEqual(first, second)
        self.assertEqual("the first one", first.read_text(),
                         "the second attachment was written over the first")

    def test_a_name_nothing_has_taken_is_used_as_it_stands(self):
        """A second file beside every first one would be a name nobody recognises."""
        self.assertEqual(self.where / "chart.png",
                         discord._somewhere_new(self.where, "chart.png"))

    def test_what_makes_a_filename_only_a_filename_is_not_weakened(self):
        """A path is the one thing a name arriving from somebody else must not become."""
        self.assertEqual("etc-passwd", discord._plain_name("../../etc/passwd"))


@unittest.skipIf(discord is None, "discord.py is not installed — run ./install.sh")
class MakingRoomForOneMoreConversation(unittest.TestCase):
    """R-CH-11 — bounded, and never by dropping a turn that is still running."""

    class Holds:
        def __init__(self, live):
            self.live = live

    def _busy(self):
        held = discord.Live()
        held.typing, held.pacing = _Cancels(), _Cancels()
        return held

    def test_a_conversation_with_a_turn_running_is_not_the_one_dropped(self):
        """The oldest *entered* one went, whatever was happening in it — and an entry is
        where that turn's typing and pacing tasks are held, so nothing was left to cancel
        them and the indicator went on renewing for the rest of the process's life."""
        busy = self._busy()
        it = self.Holds({"oldest-and-busy": busy, "idle": discord.Live(),
                         "newest": discord.Live()})
        self.assertTrue(discord.Agent._make_room(it, "newest"))
        self.assertIn("oldest-and-busy", it.live, "a running turn was dropped")
        self.assertNotIn("idle", it.live)
        self.assertEqual([False, False], [busy.typing.cancelled, busy.pacing.cancelled])

    def test_one_that_has_to_go_has_what_it_was_running_cancelled(self):
        """With nothing idle to take, something running goes — and it is cancelled on the
        way out rather than merely forgotten."""
        busy = self._busy()
        it = self.Holds({"oldest-and-busy": busy, "newest": self._busy()})
        self.assertTrue(discord.Agent._make_room(it, "newest"))
        self.assertNotIn("oldest-and-busy", it.live)
        self.assertEqual([True, True], [busy.typing.cancelled, busy.pacing.cancelled])

    def test_the_conversation_being_answered_is_never_the_one_dropped(self):
        """It has just been spoken in, which is what the room is being made for."""
        it = self.Holds({"newest": discord.Live()})
        self.assertFalse(discord.Agent._make_room(it, "newest"),
                         "it would have dropped the conversation it was making room for")
        self.assertIn("newest", it.live)


if __name__ == "__main__":
    if discord is None:
        print(f"discord.py is not installed, so nothing here can run: {WHY}", file=sys.stderr)
    unittest.main(verbosity=2)
