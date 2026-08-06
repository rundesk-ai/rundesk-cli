#!/usr/bin/env python3
"""The Discord adapter, proved without an account and without `discord.py`.

**Nothing here signs in and nothing here imports the vendor library.** The adapter binds it to one
module global, lazily, and every decision worth checking is made against that global rather than
against the network — so a stand-in with four classes on it is enough to run the whole of what
arrives and the whole of what is delivered. That is not a convenience: `--capabilities` has to
answer on a machine where nothing is installed, and a suite that needed the package to run would be
one that could not check the case the design exists for.

This suite imports nothing of rundesk's either, and that is deliberate too. The adapter is a program
on the far side of a pipe; if it ever needs `tests/support.py` to be exercised, the seam has leaked.

    python3 tests/test_channels_discord.py
"""

import asyncio
import contextlib
import importlib.machinery
import importlib.util
import io
import json
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional

#: The adapter is an executable with a shebang and no `.py`, so it is loaded by path rather than
#: imported by name — and under a name of this suite's own, because `discord` is the vendor
#: library's and taking it here would put this file in front of the real one.
ADAPTER = Path(__file__).resolve().parent.parent / "src" / "channels" / "discord"


def _the_adapter():
    """Load the adapter as a module, the way rundesk loads any script it did not write."""
    loader = importlib.machinery.SourceFileLoader("channels_discord", str(ADAPTER))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


adapter = _the_adapter()


# ---------------------------------------------------------------------------------------------
# The stand-in for `discord.py`: only what this file actually touches, and no more.
# ---------------------------------------------------------------------------------------------


class DMChannel:
    """One person's own channel. Told apart by its type and never by asking about a guild."""

    def __init__(self, which: int) -> None:
        self.id = which


class Thread:
    """A conversation of its own, reached by its own id, and whoever opened it."""

    def __init__(self, which: int, owner_id: Optional[int] = None) -> None:
        self.id = which
        self.owner_id = owner_id


class TextChannel:
    """A room. The one kind of place a thread is opened in."""

    def __init__(self, which: int) -> None:
        self.id = which


class MessageReference:
    """What Discord is told a message is replying to."""

    def __init__(self, *, message_id: int, channel_id: int, fail_if_not_exists: bool) -> None:
        self.message_id = message_id
        self.channel_id = channel_id
        self.fail_if_not_exists = fail_if_not_exists


class Status:
    """The three words this adapter ever sets a bot's dot in the member list to."""

    online = "online"
    offline = "offline"


class Library:
    """The module global the adapter binds `discord.py` to."""

    DMChannel = DMChannel
    Thread = Thread
    TextChannel = TextChannel
    MessageReference = MessageReference
    Status = Status


class Person:
    def __init__(self, which: int, bot: bool = False, display_name: str = "Ann") -> None:
        self.id = which
        self.bot = bot
        self.display_name = display_name
        self.name = display_name.lower()


class Posted:
    """What `send` hands back: an id, and every edit made to it afterwards.

    The edits are the whole point for a running commentary — a turn that grows one message and a
    turn that posts eleven are told apart here and nowhere else.
    """

    def __init__(self, which: int, refuses: Optional[Exception] = None) -> None:
        self.id = which
        self.edits: List[str] = []
        self.refuses = refuses

    async def edit(self, content: str) -> None:
        if self.refuses is not None:
            raise self.refuses
        self.edits.append(content)


class PartialMessage:
    def __init__(self, place: "Messageable", which: int) -> None:
        self.place = place
        self.id = which

    async def add_reaction(self, mark: str) -> None:
        self.place.marked.append((self.id, mark))

    async def remove_reaction(self, mark: str, who: Any) -> None:
        self.place.unmarked.append((self.id, mark))


class Messageable:
    """Where a delivery lands, and the record of everything that landed there."""

    def __init__(self, which: int) -> None:
        self.id = which
        self.sent: List[Dict[str, Any]] = []
        self.posted: List[Posted] = []
        self.marked: List[Any] = []
        self.unmarked: List[Any] = []
        self.next_id = which * 10
        #: Handed to every message posted here, so a case can make an edit fail.
        self.edits_refuse: Optional[Exception] = None
        #: Set by a case that needs a send to be genuinely *in flight* — the only way to check what
        #: happens when something else is posted while a write has not come back yet.
        self.holds: Optional[asyncio.Event] = None

    async def send(self, **called: Any) -> Posted:
        self.sent.append(called)
        if self.holds is not None:
            await self.holds.wait()
        self.next_id += 1
        made = Posted(self.next_id, refuses=self.edits_refuse)
        self.posted.append(made)
        return made

    def get_partial_message(self, which: int) -> PartialMessage:
        return PartialMessage(self, which)

    async def typing(self) -> None:
        pass


class Client:
    def __init__(self, user: Person) -> None:
        self.user = user
        self.places: Dict[int, Messageable] = {}
        #: Every presence this bot was asked to show, in the order it was asked.
        self.showed: List[str] = []
        self.closed = False

    def get_partial_messageable(self, place: int) -> Messageable:
        return self.places.setdefault(place, Messageable(place))

    async def change_presence(self, status: str) -> None:
        self.showed.append(status)

    async def close(self) -> None:
        self.closed = True


class Message:
    """One message as the adapter reads it, and the thread it will or will not give up."""

    def __init__(self, which: int, channel: Any, author: Person, content: str = "",
                 mentions: Optional[List[Person]] = None, opens: Optional[int] = 900,
                 refuses: Optional[Exception] = None) -> None:
        self.id = which
        self.channel = channel
        self.author = author
        self.content = content
        self.mentions = mentions or []
        self.attachments: List[Any] = []
        self.opens = opens
        self.refuses = refuses
        self.named: List[str] = []

    async def create_thread(self, *, name: str) -> Thread:
        self.named.append(name)
        if self.refuses is not None:
            raise self.refuses
        return Thread(self.opens)


class Records(unittest.TestCase):
    """Everything a case here needs: a wired adapter, and the records it wrote."""

    def setUp(self) -> None:
        adapter.discord = Library
        self.addCleanup(setattr, adapter, "discord", None)
        self.me = Person(11, bot=True, display_name="rundesk")
        self.asker = Person(22)
        self.client = Client(self.me)
        self.reaching: Any = None

    def during(self, doing) -> List[Dict[str, Any]]:
        """Run one whole exchange inside a loop, and hand back the records it put on stdout.

        **The connection is built in here rather than in `setUp`.** It holds an `asyncio.Event`,
        which on the floor Python this pins binds to the running loop as it is constructed — so a
        `Reaching` built outside one cannot exist at all. That is also exactly where `serving()`
        builds it, so a case here has the same shape the program does.
        """
        caught = io.StringIO()

        async def whole() -> None:
            self.reaching = adapter.Reaching([str(self.asker.id)])
            self.reaching.client = self.client
            await doing(self.reaching)

        with contextlib.redirect_stdout(caught):
            asyncio.run(whole())
        return [json.loads(line) for line in caught.getvalue().splitlines() if line.strip()]

    def only(self, records: List[Dict[str, Any]], saying: str) -> Dict[str, Any]:
        found = [one for one in records if one.get("say") == saying]
        self.assertEqual(len(found), 1, f"expected one {saying!r} in {records}")
        return found[0]

    def noted(self, records: List[Dict[str, Any]]) -> List[str]:
        return [one["text"] for one in records if one.get("say") == "note"]


# ---------------------------------------------------------------------------------------------
# What a thread is called.
# ---------------------------------------------------------------------------------------------


class WhatAThreadIsCalled(unittest.TestCase):
    """The name comes from what was said, is one line, and is inside Discord's own cap."""

    def test_it_is_the_words_that_were_said(self) -> None:
        self.assertEqual(adapter.thread_name("what changed today?"), "what changed today?")

    def test_it_is_flattened_to_one_line(self) -> None:
        # A newline in a thread name is somebody ending our label and starting one of their own.
        self.assertEqual(adapter.thread_name("deploy the api\nand then tell me"),
                         "deploy the api and then tell me")
        self.assertEqual(adapter.thread_name("  spaced   out \n\n  words  "), "spaced out words")

    def test_it_stays_inside_what_discord_takes(self) -> None:
        # Discord refuses a name past a hundred characters outright, so the bound is not a
        # preference: a long question must still produce a thread.
        named = adapter.thread_name("x" * 500)
        self.assertLessEqual(len(named), 100)
        self.assertLessEqual(len(named), adapter.THREAD_NAME_MOST)
        self.assertTrue(named.endswith("…"), named)

    def test_nothing_usable_still_produces_a_name(self) -> None:
        # A message that is only a file has nothing to be named from, and Discord will not take an
        # empty name — so a plain one stands in rather than the thread failing to open.
        for nothing in ("", "   ", "\n\n", None):
            self.assertEqual(adapter.thread_name(nothing), adapter.THREAD_UNNAMED)
            self.assertTrue(adapter.thread_name(nothing))


# ---------------------------------------------------------------------------------------------
# What the connection asks for, offline.
# ---------------------------------------------------------------------------------------------


class WhatIsAskedFor(unittest.TestCase):
    """The intent mask and the invite, both read without a network and without the library."""

    def test_the_invite_asks_to_open_a_thread(self) -> None:
        # Named against the platform's own bit rather than against the table, so a table edited to
        # the wrong number fails here instead of producing an invite that grants nothing.
        self.assertEqual(adapter.PERMITS["open a thread"], 1 << 35)
        wanted = 0
        for bit in adapter.PERMITS.values():
            wanted |= bit
        url = adapter.invited(4471)
        self.assertIn(f"permissions={wanted}", url)
        self.assertTrue(wanted & (1 << 35), "the invite would not let this open a thread")
        self.assertTrue(wanted & (1 << 38), "the invite would not let this answer in one")

    def test_the_intents_are_the_named_bits_and_nothing_else(self) -> None:
        # Checked against the named bits rather than against itself. Without GUILDS the library
        # caches nothing, a thread cannot be told from a room and `create_thread` refuses for want
        # of guild info; without MESSAGE_CONTENT every message in a room or a thread that does not
        # name this bot arrives blank. Neither GUILD_MEMBERS nor GUILD_PRESENCES is asked for.
        guilds, guild_messages, reactions, direct, content = 1 << 0, 1 << 9, 1 << 10, 1 << 12, 1 << 15
        self.assertEqual(adapter.INTENTS, guilds | guild_messages | reactions | direct | content)
        self.assertFalse(adapter.INTENTS & (1 << 1), "GUILD_MEMBERS is a toggle bought for nothing")
        self.assertFalse(adapter.INTENTS & (1 << 8), "GUILD_PRESENCES is a toggle bought for "
                                                     "nothing")

    def test_the_one_privileged_intent_is_named_wherever_it_is_refused(self) -> None:
        # A person meeting this at `--check` and a person meeting it as close code 4014 in a
        # gateway log are looking for the same switch, and must be sent to it in the same words.
        self.assertIn("Message Content Intent", adapter.THE_TOGGLE)
        self.assertIn("Privileged Gateway Intents", adapter.THE_TOGGLE)
        self.assertIn(adapter.THE_TOGGLE, adapter.unreadable_without())
        self.assertIn(adapter.THE_TOGGLE, adapter.WILL_NOT_COME_RIGHT[4014])

    def test_an_unverified_bot_with_the_toggle_on_is_not_refused(self) -> None:
        # Every bot is unverified until a hundred servers make verification compulsory, and an
        # unverified one carries the *limited* flag — reading only the other would refuse every new
        # bot on the day it was set up correctly.
        class Flags:
            def __init__(self, verified: bool, limited: bool) -> None:
                self.gateway_message_content = verified
                self.gateway_message_content_limited = limited

        self.assertIs(adapter.content_allowed(Flags(True, False)), True)
        self.assertIs(adapter.content_allowed(Flags(False, True)), True)
        self.assertIs(adapter.content_allowed(Flags(False, False)), False)
        # A library that renamed a flag must read as *not granted*, which is a refusal somebody can
        # act on, rather than as an AttributeError in the middle of a sign-in.
        self.assertIs(adapter.content_allowed(object()), False)

    def test_capabilities_answers_with_no_library_at_all(self) -> None:
        adapter.discord = None
        caught = io.StringIO()
        with contextlib.redirect_stdout(caught):
            self.assertEqual(adapter.capabilities(), 0)
        said = json.loads(caught.getvalue())
        self.assertIs(said["thread"], True)
        self.assertEqual(said["max_text"], adapter.MAX_TEXT)


# ---------------------------------------------------------------------------------------------
# Where a message is answered.
# ---------------------------------------------------------------------------------------------


class WhereAMessageIsAnswered(Records):
    """A room opens a thread; a thread and a private conversation stay where they are."""

    def arriving(self, message: Message) -> List[Dict[str, Any]]:
        async def exchange(reaching: Any) -> None:
            await reaching._arrived(message)
        return self.during(exchange)

    def test_being_named_in_a_room_opens_a_thread_and_the_turn_happens_there(self) -> None:
        message = Message(41, TextChannel(500), self.asker, "what changed today?",
                          mentions=[self.me])
        arrived = self.only(self.arriving(message), "arrived")
        self.assertEqual(message.named, ["what changed today?"])
        self.assertEqual(arrived["conversation"], "900")
        self.assertEqual(arrived["external_id"], "41")
        self.assertEqual(arrived["place"], "room")

    def test_a_message_already_in_a_thread_stays_in_it(self) -> None:
        # Threads do not nest, and a second thread under the first is where an exchange goes to be
        # lost. The id reported is the thread's own, never the room it hangs under.
        message = Message(42, Thread(901), self.asker, "and now?", mentions=[self.me])
        arrived = self.only(self.arriving(message), "arrived")
        self.assertEqual(message.named, [])
        self.assertEqual(arrived["conversation"], "901")

    def test_inside_a_thread_this_opened_it_answers_without_being_named(self) -> None:
        # The half the whole trade was made for. Nobody says a name twice into a conversation that
        # exists because they said it once.
        message = Message(47, Thread(902, owner_id=self.me.id), self.asker, "and the second one?")
        arrived = self.only(self.arriving(message), "arrived")
        self.assertEqual(arrived["conversation"], "902")
        self.assertEqual(arrived["text"], "and the second one?")
        self.assertEqual(message.named, [])

    def test_somebody_elses_thread_is_still_their_room(self) -> None:
        # Being *in* a thread is not the same as it being ours. An agent that answered every line
        # of a thread it was pulled into would have lost the silence rule through the back door.
        theirs = Thread(903, owner_id=self.asker.id)
        quiet = Message(48, theirs, self.asker, "what do we think?")
        self.assertEqual(self.arriving(quiet), [])
        named = Message(49, theirs, self.asker, f"<@{self.me.id}> what do we think?",
                        mentions=[self.me])
        arrived = self.only(self.arriving(named), "arrived")
        self.assertEqual(arrived["conversation"], "903")
        self.assertEqual(arrived["text"], "what do we think?")
        self.assertEqual(named.named, [])

    def test_a_private_message_is_answered_flat(self) -> None:
        message = Message(43, DMChannel(700), self.asker, "hello")
        arrived = self.only(self.arriving(message), "arrived")
        self.assertEqual(message.named, [])
        self.assertEqual(arrived["conversation"], "700")
        self.assertEqual(arrived["place"], "dm")

    def test_a_room_message_that_does_not_name_us_is_not_answered_at_all(self) -> None:
        message = Message(44, TextChannel(500), self.asker, "morning everyone")
        self.assertEqual(self.arriving(message), [])
        self.assertEqual(message.named, [])

    def test_a_stranger_never_gets_a_thread_opened_for_them(self) -> None:
        # Opening one is the first visible thing this program does. Doing it before the allow check
        # is how a stranger makes an agent litter a room it is never going to answer them in.
        stranger = Person(99)
        message = Message(45, TextChannel(500), stranger, "hi", mentions=[self.me])
        self.assertEqual(self.arriving(message), [])
        self.assertEqual(message.named, [])

    def test_a_message_with_nothing_in_it_opens_nothing(self) -> None:
        message = Message(46, TextChannel(500), self.asker, f"<@{self.me.id}>",
                          mentions=[self.me])
        self.assertEqual(self.arriving(message), [])
        self.assertEqual(message.named, [])


class WhenAThreadIsRefused(Records):
    """The permission may not be there, and a channel that stopped working would be worse."""

    def a_refused_message(self, which: int) -> Message:
        return Message(which, TextChannel(500), self.asker, "what changed?", mentions=[self.me],
                       refuses=RuntimeError("Missing Permissions"))

    def test_it_falls_back_to_answering_in_the_room(self) -> None:
        message = self.a_refused_message(51)

        async def exchange(reaching: Any) -> None:
            await reaching._arrived(message)

        records = self.during(exchange)
        self.assertEqual(self.only(records, "arrived")["conversation"], "500")
        said = self.only(records, "note")["text"]
        self.assertIn("could not open a thread", said)
        self.assertIn("open a thread", said)        # names the permission somebody has to grant
        self.assertIn("invite", said)               # and how an existing bot comes to have it

    def test_it_is_said_once_and_not_once_per_message(self) -> None:
        # A room is busy and the permission is one standing fact about this bot. Said every time,
        # it would bury everything else in the log it is written to.
        async def exchange(reaching: Any) -> None:
            await reaching._arrived(self.a_refused_message(52))
            await reaching._arrived(self.a_refused_message(53))

        records = self.during(exchange)
        self.assertEqual(len(self.noted(records)), 1)
        answered = [one for one in records if one.get("say") == "arrived"]
        self.assertEqual([one["conversation"] for one in answered], ["500", "500"])


# ---------------------------------------------------------------------------------------------
# What a delivery quotes, and what it tints.
# ---------------------------------------------------------------------------------------------


class WhatADeliveryQuotes(Records):
    """An answer quotes and tints; commentary does neither; and neither ever costs the answer."""

    def delivering(self, known: Optional[Dict[str, Any]] = None,
                   **it: Any) -> Dict[str, Any]:
        """One delivery, into a connection that already knows what `known` says it does."""
        said = {"do": "deliver", "id": "1754431200.1-0", "text": "three files changed"}
        said.update(it)

        async def exchange(reaching: Any) -> None:
            for message_id, standing in (known or {}).items():
                reaching.handled[message_id] = standing
            await reaching._deliver(said)

        records = self.during(exchange)
        self.assertEqual([one for one in records if one.get("say") == "failed"], [])
        return self.client.places[int(said["place"])].sent[-1]

    @staticmethod
    def asked(place: int) -> adapter.Handled:
        return adapter.Handled(place=place, ours=False)

    def test_an_answer_quotes_the_message_that_asked_and_tints_it(self) -> None:
        # The amber bar down the side of a message is drawn by the asker's own client for a
        # mention, and a reply draws it by pinging the author of what it quotes.
        sent = self.delivering({"61": self.asked(500)}, place="500", reply_to="61")
        self.assertEqual(sent["reference"].message_id, 61)
        self.assertEqual(sent["reference"].channel_id, 500)
        self.assertIs(sent["mention_author"], True)

    def test_the_quote_never_costs_the_answer(self) -> None:
        # Discord refuses a whole message quoting one it cannot resolve, and a turn runs for
        # minutes — the asker deleting their own question is enough to lose the answer to it.
        sent = self.delivering({"61": self.asked(500)}, place="500", reply_to="61")
        self.assertIs(sent["reference"].fail_if_not_exists, False)

    def test_a_message_this_has_never_seen_is_still_quoted(self) -> None:
        # Every message a restart forgot. Quoting it is what the caller asked for, and Discord
        # drops a reference it cannot resolve rather than refusing the answer.
        sent = self.delivering(place="500", reply_to="65")
        self.assertEqual(sent["reference"].message_id, 65)
        self.assertIs(sent["mention_author"], True)

    def test_commentary_carries_no_quote_and_no_tint(self) -> None:
        # Which delivery is an answer is rundesk's to say, and it says so with `reply_to`. Nothing
        # here reads the words and guesses.
        sent = self.delivering(place="500")
        self.assertIsNone(sent["reference"])
        self.assertIs(sent["mention_author"], False)

    def test_an_answer_in_a_private_conversation_is_quoted_and_tinted(self) -> None:
        # R-DIS-28. This was dropped on the reasoning that two people alone need no quote — which is
        # wrong about what the quote is for. The tint separates the answer from the commentary above
        # it, and in a one-to-one conversation the reply ping is the only thing that draws it.
        sent = self.delivering({"62": self.asked(700)}, place="700", reply_to="62")
        self.assertEqual(sent["reference"].message_id, 62)
        self.assertIs(sent["mention_author"], True)

    def test_a_message_this_program_wrote_is_quoted_without_a_ping(self) -> None:
        # Pinging the author of our own message pings the bot, and leaves the person the answer is
        # for untinted — the recorded failure from the build this replaces.
        ours = adapter.Handled(place=500, ours=True)
        sent = self.delivering({"63": ours}, place="500", reply_to="63")
        self.assertEqual(sent["reference"].message_id, 63)
        self.assertIs(sent["mention_author"], False)

    def test_the_message_a_thread_was_opened_from_is_not_quoted_inside_it(self) -> None:
        # It is still standing in the room above, and a reply does not reach across. Dropped here
        # rather than left to Discord, which would drop it silently.
        sent = self.delivering({"64": self.asked(500)}, place="900", reply_to="64")
        self.assertIsNone(sent["reference"])
        self.assertIs(sent["mention_author"], False)

    def test_what_a_turn_cost_stands_above_the_answer_in_small_print(self) -> None:
        # R-DIS-17. Above, because a long answer pushes anything after it off a phone screen — and in
        # Discord's own subtext register, so the bookkeeping is visibly not something the agent said.
        sent = self.delivering(place="500", text="the deploy is green",
                               cost="codex · 2.2k input · 481 output · 1m elapsed")
        self.assertEqual("-# codex · 2.2k input · 481 output · 1m elapsed\nthe deploy is green",
                         sent["content"])

    def test_a_delivery_with_nothing_said_about_cost_is_left_exactly_as_it_was(self) -> None:
        # A turn whose brain reported nothing is not given a line of empty punctuation.
        sent = self.delivering(place="500", text="the deploy is green")
        self.assertEqual("the deploy is green", sent["content"])

    def test_what_this_posts_is_remembered_as_its_own(self) -> None:
        self.delivering(place="500")
        self.assertEqual(len(self.client.places[500].sent), 1)
        wrote = self.reaching.handled["5001"]
        self.assertEqual((wrote.place, wrote.ours), (500, True))


# ---------------------------------------------------------------------------------------------
# Where a mark is put.
# ---------------------------------------------------------------------------------------------


class WhereAMarkIsPut(Records):
    """On the message, wherever it is standing — which is not always where its conversation is."""

    @staticmethod
    async def marking(reaching: Any, place: str, external_id: str, state: str = "seen") -> None:
        await reaching._state(
            {"do": "state", "place": place, "external_id": external_id, "state": state})

    def test_the_message_that_opened_a_thread_is_marked_in_the_room_above(self) -> None:
        # Rundesk names the thread as the place, because that is the conversation. The message it
        # is marking never moved, and Discord answers 404 for it inside the thread.
        message = Message(71, TextChannel(500), self.asker, "what changed?", mentions=[self.me])

        async def exchange(reaching: Any) -> None:
            await reaching._arrived(message)
            await self.marking(reaching, "900", "71")

        self.during(exchange)
        self.assertEqual(self.client.places[500].marked, [(71, "👀")])
        self.assertNotIn(900, self.client.places)

    def test_a_message_this_never_saw_is_marked_where_it_was_told(self) -> None:
        # Every message a restart forgot, and the only answer available for one.
        async def exchange(reaching: Any) -> None:
            await self.marking(reaching, "800", "72")

        self.during(exchange)
        self.assertEqual(self.client.places[800].marked, [(72, "👀")])

    def test_the_new_mark_goes_up_before_the_old_one_comes_down(self) -> None:
        # A message with no mark for a moment reads as a turn nobody picked up.
        async def exchange(reaching: Any) -> None:
            await self.marking(reaching, "800", "73", "seen")
            await self.marking(reaching, "800", "73", "done")

        self.during(exchange)
        place = self.client.places[800]
        self.assertEqual(place.marked, [(73, "👀"), (73, "✅")])
        self.assertEqual(place.unmarked, [(73, "👀")])

    def test_every_state_rundesk_speaks_is_shown(self) -> None:
        # The five words are the vocabulary, and `working` is the indicator rather than a mark: a
        # second mark there would say a turn had been seen twice.
        self.assertEqual(set(adapter.MARKS), {"seen", "done", "stopped", "failed"})

        async def exchange(reaching: Any) -> None:
            for nth, state in enumerate(("seen", "done", "stopped", "failed")):
                await self.marking(reaching, "800", str(80 + nth), state)
            await self.marking(reaching, "800", "84", "working")
            self.assertIn(800, reaching.typing)
            reaching._typing_stops(800)

        self.during(exchange)
        self.assertEqual([mark for _, mark in self.client.places[800].marked],
                         ["👀", "✅", "✋", "⚠️"])


# ---------------------------------------------------------------------------------------------
# What the agent is doing, while it is still doing it.
# ---------------------------------------------------------------------------------------------


class WhatEachThingReads(unittest.TestCase):
    """One activity record as one line. Pure text — no connection and no library."""

    #: Every word `providers/protocol.py` defines. Written out rather than imported: this suite
    #: imports nothing of rundesk's, because the adapter is a program on the far side of a pipe.
    RUNDESK_DID = ("read", "search", "run", "edit", "list", "make", "delegate",
                   "memory", "rules", "identity")

    def line(self, **it: Any) -> str:
        return adapter.activity_line(it)

    def test_every_word_rundesk_can_send_has_a_mark_and_words_of_its_own(self) -> None:
        # A word absent from either table would silently render as the unknown fallback, so a whole
        # category of what the agent does would read as "thinking" and nothing would say why.
        self.assertEqual(set(adapter.DID), set(self.RUNDESK_DID))
        self.assertEqual(set(adapter.SHOWN), set(self.RUNDESK_DID))
        self.assertEqual(set(adapter.FAILED), set(self.RUNDESK_DID))
        for did in self.RUNDESK_DID:
            self.assertNotIn(adapter.UNKNOWN, self.line(did=did), f"{did} fell back to thinking")
            self.assertNotIn("thinking", self.line(did=did), f"{did} fell back to thinking")

    def test_the_ten_words_as_a_person_reads_them(self) -> None:
        self.assertEqual("-# 💻 ran command", self.line(did="run"))
        self.assertEqual("-# 📖 read file", self.line(did="read"))
        self.assertEqual("-# ✏️ edited file", self.line(did="edit"))
        self.assertEqual("-# 🔎 searched", self.line(did="search"))
        self.assertEqual("-# 📁 listed files", self.line(did="list"))
        self.assertEqual("-# 🎨 made something", self.line(did="make"))
        self.assertEqual("-# 🤖 delegated to subagent", self.line(did="delegate"))
        self.assertEqual("-# 🧠 updated my memory", self.line(did="memory"))
        self.assertEqual("-# 📜 updated my rules", self.line(did="rules"))
        self.assertEqual("-# ✨ updated my identity", self.line(did="identity"))

    def test_a_word_this_does_not_know_is_thinking_rather_than_a_guess(self) -> None:
        # A brain doing something outside the closed set is doing something with no word here yet.
        # A reader shown nothing is better off than one taught to believe a word that means
        # something else — and this is the catch-all every provider relies on by omitting `did`.
        self.assertEqual("-# 💭 thinking", self.line(did="teleported"))
        self.assertEqual("-# 💭 thinking", self.line())
        self.assertEqual("-# 💭 thinking", self.line(did=None))

    def test_a_failure_says_what_failed_and_never_why(self) -> None:
        # A command line or a path may be private, and this is posted into a room. The whole account
        # stays in the turn's own record (R-DIS-9, R-DIS-20).
        self.assertEqual("-# ⚠ command failed", self.line(did="run", ok=False))
        self.assertEqual("-# ⚠ subagent failed", self.line(did="delegate", ok=False))
        self.assertEqual("-# ⚠ could not update my rules", self.line(did="rules", ok=False))
        self.assertEqual("-# ⚠ tool failed", self.line(did="teleported", ok=False))

    def test_a_subagent_starting_and_finishing_are_two_different_lines(self) -> None:
        # A delegation is the one act long enough that its ending is news of its own.
        self.assertEqual("-# 🤖 delegated to subagent", self.line(did="delegate"))
        self.assertEqual("-# 🤖 subagent finished", self.line(did="delegate", ok=True))

    def test_a_helper_is_named_without_its_location(self) -> None:
        self.assertEqual("-# 🤖 delegated to subagent: reviewer",
                         self.line(did="delegate", who="/Users/someone/agents/reviewer"))
        self.assertEqual("-# 🤖 subagent finished: reviewer",
                         self.line(did="delegate", ok=True, who="reviewer"))

    def test_a_name_cannot_end_our_line_and_start_one_of_its_own(self) -> None:
        # A helper's name is a stranger's text arriving on a line of running commentary.
        self.assertEqual("-# 🤖 delegated to subagent: bad name",
                         self.line(did="delegate", who="bad\nname"))

    def test_only_a_delegation_is_ever_named(self) -> None:
        # Every other word is broad on purpose; a name beside one would be an argument in disguise.
        self.assertEqual("-# 💻 ran command", self.line(did="run", who="something"))


class HowActivityIsCounted(unittest.TestCase):
    """Adjacent repeats collapse to one line and a count. Pure text."""

    def grouped(self, *lines: Any) -> str:
        return adapter.rendered(adapter.grouped([], list(lines)))

    def test_one_occurrence_carries_no_count(self) -> None:
        self.assertEqual("-# 💻 ran command", self.grouped("-# 💻 ran command"))

    def test_consecutive_activity_is_one_line_with_a_count(self) -> None:
        self.assertEqual("-# 💻 ran command **(x3)**",
                         self.grouped(*["-# 💻 ran command"] * 3))

    def test_only_consecutive_activity_is_counted(self) -> None:
        # The order is what a reader is following: read, read, run, read is four things happening
        # and not two.
        self.assertEqual("-# 📖 read file **(x2)**\n-# 💻 ran command\n-# 📖 read file",
                         self.grouped("-# 📖 read file", "-# 📖 read file",
                                      "-# 💻 ran command", "-# 📖 read file"))

    def test_a_count_grows_across_separate_writes(self) -> None:
        # A burst split over two flushes is still one run of the same thing.
        groups = adapter.grouped([], ["-# 💻 ran command", "-# 💻 ran command"])
        groups = adapter.grouped(groups, ["-# 💻 ran command"])
        self.assertEqual("-# 💻 ran command **(x3)**", adapter.rendered(groups))

    def test_something_visible_in_between_breaks_a_count(self) -> None:
        # The `None` barrier. Without it a burst spanning a message the reader has already scrolled
        # past was counted as one unbroken run.
        self.assertEqual("-# 💻 ran command\n-# 💻 ran command",
                         self.grouped("-# 💻 ran command", None, "-# 💻 ran command"))

    def test_named_subagents_still_collapse_under_one_heading(self) -> None:
        # Listing every name defeats compact counting; once the category repeats it owns the count.
        self.assertEqual("-# 🤖 delegated to subagent **(x2)**",
                         self.grouped("-# 🤖 delegated to subagent: one",
                                      "-# 🤖 delegated to subagent: two"))

    def test_starting_and_finishing_a_subagent_are_not_counted_together(self) -> None:
        self.assertEqual("-# 🤖 delegated to subagent\n-# 🤖 subagent finished",
                         self.grouped("-# 🤖 delegated to subagent", "-# 🤖 subagent finished"))

    def test_a_long_commentary_drops_whole_oldest_groups_and_says_so(self) -> None:
        # Past Discord's own limit every further edit is refused, freezing the commentary at the
        # moment it got interesting. Whole groups, because half a line with its count sheared off
        # reads as a different event.
        many = [f"-# 💻 line {nth}" for nth in range(400)]
        shown, kept = adapter.bounded(adapter.grouped([], many))
        self.assertLessEqual(len(shown), adapter.ACTIVITY_CHARS)
        self.assertTrue(shown.startswith(adapter.CLIPPED))
        self.assertIn("line 399", shown)
        self.assertNotIn("line 0\n", shown)
        self.assertLess(len(kept), len(many))

    def test_one_enormous_group_is_kept_rather_than_dropped_to_nothing(self) -> None:
        # A commentary showing nothing at all is worse than one showing its most recent line.
        shown, kept = adapter.bounded([(f"-# 💻 {'x' * 4000}", 1)])
        self.assertEqual(1, len(kept))
        self.assertIn("x", shown)


class HowTheCommentaryGrows(Records):
    """One message that grows while it is still last, and a fresh one once it is not.

    `GROW_SECONDS` is pinned to nothing here — the flush is driven directly, because what is being
    checked is *which message a line lands in*, and waiting out a real clock in a suite buys a slow
    case rather than a truer one. The pacing that gathers a burst is checked once, separately.
    """

    async def doing(self, reaching: Any, place: str, *lines: Dict[str, Any]) -> None:
        for one in lines:
            reaching._doing({"place": place, **one})
        held = reaching.growing[int(place)]
        held.let_go()                      # the timer's job is done by the flush below
        await reaching._flush(int(place), held)

    def test_activity_grows_one_message_rather_than_posting_many(self) -> None:
        # A phone that buzzes eleven times to say an agent read a file is worse than one that
        # buzzes once with the reply.
        async def exchange(reaching: Any) -> None:
            await self.doing(reaching, "500", {"did": "run"})
            await self.doing(reaching, "500", {"did": "run"})
            await self.doing(reaching, "500", {"did": "read"})

        self.during(exchange)
        place = self.client.places[500]
        self.assertEqual(1, len(place.sent), "the commentary posted more than one message")
        self.assertEqual("-# 💻 ran command", place.sent[0]["content"])
        self.assertEqual(["-# 💻 ran command **(x2)**",
                          "-# 💻 ran command **(x2)**\n-# 📖 read file"], place.posted[0].edits)

    def test_a_burst_is_one_write_rather_than_one_each(self) -> None:
        # `_doing` gathers; a single task started once writes the lot after GROW_SECONDS.
        async def exchange(reaching: Any) -> None:
            for _ in range(10):
                reaching._doing({"place": "500", "did": "run"})
            self.assertEqual(10, len(reaching.growing[500].pending))
            held = reaching.growing[500]
            held.let_go()
            await reaching._flush(500, held)

        self.during(exchange)
        place = self.client.places[500]
        self.assertEqual(1, len(place.sent))
        self.assertEqual("-# 💻 ran command **(x10)**", place.sent[0]["content"])
        self.assertEqual([], place.posted[0].edits, "a single burst should need no edit at all")

    def test_something_posted_under_it_starts_a_fresh_commentary(self) -> None:
        # A message something has been posted under is one the reader has already scrolled past,
        # and editing it changes history rather than showing progress.
        async def exchange(reaching: Any) -> None:
            await self.doing(reaching, "500", {"did": "run"})
            await reaching._deliver({"do": "deliver", "id": "1", "place": "500", "text": "answer"})
            await self.doing(reaching, "500", {"did": "run"})

        self.during(exchange)
        place = self.client.places[500]
        self.assertEqual(3, len(place.sent), "the second run did not start its own message")
        self.assertEqual("-# 💻 ran command", place.sent[0]["content"])
        self.assertEqual("answer", place.sent[1]["content"])
        self.assertEqual("-# 💻 ran command", place.sent[2]["content"])
        # And the count restarted rather than carrying across the answer.
        self.assertNotIn("x2", place.sent[2]["content"])

    def test_somebody_speaking_also_buries_the_commentary(self) -> None:
        async def exchange(reaching: Any) -> None:
            await self.doing(reaching, "700", {"did": "run"})
            self.assertIsNotNone(reaching.growing[700].posted)
            reaching._no_longer_last(700)
            self.assertIsNone(reaching.growing[700].posted)

        self.during(exchange)

    def test_activity_waiting_when_it_is_buried_still_lands_and_starts_a_new_count(self) -> None:
        # It belongs above the visible message but may still be written after it; what follows must
        # not be counted with what preceded.
        async def exchange(reaching: Any) -> None:
            reaching._doing({"place": "500", "did": "run"})
            reaching._no_longer_last(500)
            held = reaching.growing[500]
            held.let_go()
            reaching._doing({"place": "500", "did": "run"})
            await reaching._flush(500, held)

        self.during(exchange)
        sent = self.client.places[500].sent
        self.assertEqual("-# 💻 ran command\n-# 💻 ran command", sent[0]["content"])

    def test_a_write_still_in_flight_when_it_is_buried_is_not_grown_into(self) -> None:
        # The generation counter. A post that comes back after something buried the commentary must
        # be dropped rather than becoming the message the next line is written into.
        async def exchange(reaching: Any) -> None:
            where = self.client.get_partial_messageable(500)
            where.holds = asyncio.Event()
            held = reaching.growing.setdefault(500, adapter.Growing())
            held.pending = ["-# 💻 ran command"]
            flushing = asyncio.ensure_future(reaching._flush(500, held))
            await asyncio.sleep(0)         # let the write reach Discord and stop there
            self.assertEqual(1, len(where.sent), "the write never got under way")
            held.buried()                  # something else is posted while it is still in flight
            where.holds.set()
            await flushing
            self.assertIsNone(held.posted, "a buried commentary was resurrected by a stale write")

        self.during(exchange)

    def test_an_edit_that_fails_starts_a_fresh_message_rather_than_failing_for_ever(self) -> None:
        # An edit fails because the message is gone or the channel is unreachable, and neither
        # improves by being asked twice a second for the rest of the turn.
        async def exchange(reaching: Any) -> None:
            self.client.places[500] = Messageable(500)
            self.client.places[500].edits_refuse = RuntimeError("that message is gone")
            await self.doing(reaching, "500", {"did": "run"})
            await self.doing(reaching, "500", {"did": "read"})
            self.assertIsNone(reaching.growing[500].posted)
            await self.doing(reaching, "500", {"did": "read"})

        records = self.during(exchange)
        self.assertEqual(2, len(self.client.places[500].sent))
        self.assertTrue(any("could not grow" in one for one in self.noted(records)))

    def test_an_edit_saying_exactly_what_is_already_there_is_not_sent(self) -> None:
        async def exchange(reaching: Any) -> None:
            await self.doing(reaching, "500", {"did": "run"})
            held = reaching.growing[500]
            held.pending = []
            await reaching._flush(500, held)

        self.during(exchange)
        self.assertEqual([], self.client.places[500].posted[0].edits)

    def test_the_commentary_is_remembered_as_ours_so_an_answer_never_pings_the_bot(self) -> None:
        async def exchange(reaching: Any) -> None:
            await self.doing(reaching, "500", {"did": "run"})

        self.during(exchange)
        posted = self.client.places[500].posted[0]
        self.assertIs(self.reaching.handled[str(posted.id)].ours, True)

    def test_a_place_this_cannot_parse_is_a_note_rather_than_a_crash(self) -> None:
        async def exchange(reaching: Any) -> None:
            reaching._doing({"place": "not-a-snowflake", "did": "run"})
            self.assertEqual({}, reaching.growing)

        records = self.during(exchange)
        self.assertTrue(self.noted(records))


# ---------------------------------------------------------------------------------------------
# What is held, for a process that runs for weeks.
# ---------------------------------------------------------------------------------------------


class WhatIsHeld(Records):
    """What this holds is bounded, because this process runs for weeks."""

    def test_nothing_grows_without_a_bound(self) -> None:
        async def exchange(reaching: Any) -> None:
            for nth in range(adapter.LIVE_KEPT + 40):
                reaching.handled[str(nth)] = adapter.Handled(place=nth, ours=False)
                reaching._make_room()

        self.during(exchange)
        self.assertLessEqual(len(self.reaching.handled), adapter.LIVE_KEPT)
        # Oldest first: the newest conversation is the one still waiting on an answer.
        self.assertIn(str(adapter.LIVE_KEPT + 39), self.reaching.handled)
        self.assertNotIn("0", self.reaching.handled)


class WhatTheDotInTheMemberListSays(unittest.TestCase):
    """A bot's presence is the one place somebody looks to find out whether their agent is up.

    Both halves are set rather than left to the library and the socket, and each for its own reason.
    """

    def setUp(self):
        self.old, adapter.discord = adapter.discord, Library
        self.addCleanup(setattr, adapter, "discord", self.old)
        self.hosting = adapter.Reaching.__new__(adapter.Reaching)
        self.hosting.connected = False
        self.hosting.client = Client(Person(1, bot=True, display_name="Markus"))

    def test_it_goes_green_when_the_socket_comes_up(self):
        asyncio.run(self.hosting._up())
        self.assertEqual(["online"], self.hosting.client.showed)

    def test_it_goes_green_again_on_every_resume_and_not_only_the_first(self):
        """**`Status.online` is only the library's default until something changes it.** A resumed
        session carries whatever the last one ended on, and after an orderly stop that is `offline`
        — so a gateway that came back would be green in its own log and grey to everybody else."""
        asyncio.run(self.hosting._up())
        asyncio.run(self.hosting._up())
        self.assertEqual(["online", "online"], self.hosting.client.showed)

    def test_the_ready_record_still_goes_out_when_the_presence_will_not_set(self):
        """A dot nobody could set is not a channel that failed to connect."""
        async def refuses(status):
            raise RuntimeError("Discord would not take it")
        self.hosting.client.change_presence = refuses
        with contextlib.redirect_stdout(io.StringIO()) as printed:
            asyncio.run(self.hosting._up())
        self.assertIn('"ready"', printed.getvalue())


if __name__ == "__main__":
    unittest.main()
