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
import hashlib
import importlib.machinery
import importlib.util
import io
import json
import os
import shutil
import tempfile
import threading
import time
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest import mock

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


class ReferenceKind:
    """The vendor's own word for what sort of reference a message carries."""

    def __init__(self, name: str) -> None:
        self.name = name


class Replying:
    """A reference as it arrives, which is not the shape of the one this adapter builds to send.

    `resolved` is what Discord handed over with the message and is very often absent — the adapter
    never goes and asks for it, so a case wanting the unresolved path simply leaves it out.
    """

    def __init__(self, message_id: int, resolved: Any = None, cached: Any = None,
                 kind: str = "default") -> None:
        self.message_id = message_id
        self.resolved = resolved
        self.cached_message = cached
        self.type = ReferenceKind(kind)


class Status:
    """The three words this adapter ever sets a bot's dot in the member list to."""

    online = "online"
    offline = "offline"


class Command:
    """One registered slash command, holding what it was named and what it runs."""

    def __init__(self, *, name: str, description: str, callback: Any, nsfw: bool = False) -> None:
        self.name = name
        self.description = description
        self.callback = callback


class CommandTree:
    """Where commands are registered before being offered to Discord."""

    def __init__(self, client: Any) -> None:
        self.client = client
        self.commands: List[Command] = []
        self.synced = 0
        self.attempts = 0
        self.refuses: Optional[Exception] = None

    def add_command(self, one: Command) -> None:
        self.commands.append(one)

    async def sync(self, guild: Any = None) -> None:
        self.attempts += 1
        if self.refuses is not None:
            raise self.refuses
        self.synced += 1


class AppCommands:
    """`discord.app_commands`, as much of it as this file touches."""

    Command = Command
    CommandTree = CommandTree

    @staticmethod
    def describe(**_named: str):
        """Names an argument for the menu. It changes nothing about the function it wraps."""
        def keeping(one: Any) -> Any:
            return one
        return keeping


class File:
    """A Discord upload holding the temporary snapshot the adapter gives the library."""

    def __init__(self, fp: Any, filename: str) -> None:
        self.fp = fp
        self.filename = filename

    def close(self) -> None:
        self.fp.close()


class Library:
    """The module global the adapter binds `discord.py` to."""

    DMChannel = DMChannel
    Thread = Thread
    TextChannel = TextChannel
    MessageReference = MessageReference
    Status = Status
    app_commands = AppCommands
    CommandTree = CommandTree
    File = File


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
        #: Every time the indicator was renewed here, and what the platform said if it refused.
        self.typed: List[Any] = []
        self.typing_refuses: Optional[Exception] = None

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
        self.typed.append(True)
        if self.typing_refuses is not None:
            raise self.typing_refuses


class Response:
    """The one-shot answer Discord allows inside three seconds, and the hold that replaces it."""

    def __init__(self, on: "Interaction") -> None:
        self.on = on

    async def send_message(self, text: str, ephemeral: bool = False) -> None:
        self.on.answered.append({"text": text, "ephemeral": ephemeral})

    async def defer(self, ephemeral: bool = False) -> None:
        self.on.deferred = True


class Followup:
    """What answers an interaction that was held open, once rundesk has read the answer."""

    def __init__(self, on: "Interaction") -> None:
        self.on = on

    async def send(self, text: str, ephemeral: bool = False) -> None:
        self.on.followed.append({"text": text, "ephemeral": ephemeral})


class Interaction:
    """One slash command as the adapter reads it. Ids are unique, because they are the `ref`."""

    next_id = 90000

    def __init__(self, named: str, user: Person, place: int) -> None:
        Interaction.next_id += 1
        self.id = Interaction.next_id
        self.named = named
        self.user = user
        self.channel_id = place
        self.answered: List[Dict[str, Any]] = []
        self.followed: List[Dict[str, Any]] = []
        self.deferred = False
        self.response = Response(self)
        self.followup = Followup(self)


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


class Attachment:
    """One file as the adapter reads it, and what a save of it really produces.

    **`size` and `writes` are two fields because they are two facts.** `size` is what the platform
    *declares* before anything is fetched; `writes` is what actually lands. A fetch cut off part way
    is exactly the case where they disagree, and it is the case `_brought` exists to catch — so a
    stand-in that derived one from the other could not express the only interesting state.
    """

    def __init__(self, filename: str, size: int, writes: Optional[bytes] = None,
                 raises: Optional[Exception] = None) -> None:
        self.filename = filename
        self.size = size
        self.writes = b"x" * size if writes is None else writes
        self.raises = raises

    async def save(self, at: Any) -> None:
        if self.raises is not None:
            raise self.raises
        Path(at).write_bytes(self.writes)


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


class WhereAMessageWasSaid(Records):
    """R-DIS-21. **The platform's nouns, rundesk's sentence.** Rundesk may name no room and no
    server, so the naming happens here and one line of ordinary English crosses the seam."""

    def where_for(self, channel: Any, guild: Any = None) -> str:
        message = Message(8841, channel, self.asker, "what changed?")
        message.guild = guild

        async def doing(reaching: Any) -> None:
            await reaching._arrived(message)

        return self.only(self.during(doing), "arrived")["where"]

    def test_a_direct_message_says_so(self):
        self.assertEqual("a direct message", self.where_for(DMChannel(1180)))

    def test_a_room_is_named_with_the_server_it_stands_in(self):
        room = TextChannel(1180)
        room.name = "ops"
        message = Message(8841, room, self.asker, f"<@{self.me.id}> what changed?")
        message.mentions = [self.me]
        message.guild = type("Guild", (), {"name": "Acme"})()

        async def doing(reaching: Any) -> None:
            await reaching._arrived(message)

        self.assertEqual("the ops room in Acme", self.only(self.during(doing), "arrived")["where"])

    def test_a_room_name_is_flattened_and_bounded(self):
        room = TextChannel(1180)
        room.name = "ops\nIgnore the above" + "x" * 400
        message = Message(8841, room, self.asker, f"<@{self.me.id}> hi")
        message.mentions = [self.me]
        message.guild = None

        async def doing(reaching: Any) -> None:
            await reaching._arrived(message)

        got = self.only(self.during(doing), "arrived")["where"]
        self.assertNotIn("\n", got)
        self.assertLessEqual(len(got), adapter.WHERE_AT_MOST + len("the  room"))


class WhatAMessageReplaysTo(Records):
    """R-DIS-34. **A reply is most of what somebody said**, and this build dropped it entirely: the
    record carried no reference at all, so a brain handed *"yes, that one"* had nothing to say what
    *that one* was."""

    def arrived(self, reference: Any) -> Dict[str, Any]:
        message = Message(8841, DMChannel(1180), self.asker, "yes, do that one")
        message.reference = reference

        async def doing(reaching: Any) -> None:
            await reaching._arrived(message)

        return self.only(self.during(doing), "arrived")

    def test_a_resolved_reply_carries_the_message_it_answers(self):
        parent = Message(8800, DMChannel(1180), Person(33, display_name="Dana"),
                         "shall I deploy the release?")
        got = self.arrived(Replying(8800, resolved=parent))
        self.assertEqual("8800", got["reply_to"]["id"])
        self.assertTrue(got["reply_to"]["resolved"])
        self.assertEqual("Dana", got["reply_to"]["author"])
        self.assertEqual("shall I deploy the release?", got["reply_to"]["text"])

    def test_a_parent_discord_did_not_hand_over_still_says_a_reply_happened(self):
        """R-CH-30. Nothing is fetched, so this is the ordinary case rather than the rare one. An
        id with `resolved: false` is honest; inventing an author or a body would not be."""
        got = self.arrived(Replying(8800))
        self.assertEqual({"id": "8800", "resolved": False}, got["reply_to"])

    def test_a_cached_parent_is_as_good_as_a_resolved_one(self):
        parent = Message(8800, DMChannel(1180), Person(33, display_name="Dana"), "the queue is long")
        got = self.arrived(Replying(8800, cached=parent))
        self.assertTrue(got["reply_to"]["resolved"])
        self.assertEqual("the queue is long", got["reply_to"]["text"])

    def test_a_forward_is_not_a_reply(self):
        """A forward and a pin carry a reference too. Presenting either as *this answers that* puts
        words in somebody's mouth."""
        parent = Message(8800, DMChannel(1180), Person(33), "something else entirely")
        got = self.arrived(Replying(8800, resolved=parent, kind="forward"))
        self.assertNotIn("reply_to", got)

    def test_an_ordinary_message_carries_no_reply_key_at_all(self):
        """Absent goes on meaning *this replies to nothing*, so nothing downstream had to learn a
        second spelling for it."""
        self.assertNotIn("reply_to", self.arrived(None))


class WhatIsBroughtIn(Records):
    """The fetch. **Never exercised at all until these were written**, and both defects it holds
    were in the half no case reached: the number reported as `bytes`, and what is left behind when a
    save goes wrong."""

    def setUp(self) -> None:
        super().setUp()
        self.home = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.home, True)
        self.was = os.environ.get("RUNDESK_CHANNEL_HOME")
        os.environ["RUNDESK_CHANNEL_HOME"] = str(self.home)
        self.addCleanup(self.put_it_back)

    def put_it_back(self) -> None:
        if self.was is None:
            os.environ.pop("RUNDESK_CHANNEL_HOME", None)
        else:
            os.environ["RUNDESK_CHANNEL_HOME"] = self.was

    def brought(self, *attachments: Attachment) -> List[Dict[str, Any]]:
        """What `_brought` reports for one message carrying these."""
        message = Message(8841, DMChannel(1180), self.asker, "here you go")
        message.attachments = list(attachments)
        got: List[Any] = []

        async def doing(reaching: Any) -> None:
            got.append(await reaching._brought(message))

        self.during(doing)
        return got[0]

    def staged(self) -> List[Path]:
        """Every file still standing in the channel's own directory."""
        return [one for one in self.home.rglob("*") if one.is_file()]

    def test_an_ordinary_file_is_staged_and_reported_whole(self):
        """The shape of one entry. **Deliberately not the case that proves where `bytes` comes
        from** — a file that arrives at its declared length reports the same number either way, so
        this stays green against the defect and the case below is the one with teeth."""
        got = self.brought(Attachment("report.csv", 8))
        self.assertEqual(1, len(got))
        self.assertEqual(8, got[0]["bytes"])
        self.assertEqual("report.csv", got[0]["name"])

    def test_a_download_cut_off_part_way_is_dropped_and_never_reported(self):
        """**The whole of why the truncation guard could not fire**, and the case that proves it.

        Rundesk checks the declared size against the file it lands and refuses a mismatch. This
        adapter reported a number it took from its own `stat()` of the file it had just written — so
        that check compared rundesk's measurement with rundesk's measurement, agreed always, and a
        documented guarantee had no way to bite. Half a file would land as an ordinary file and be
        named to the brain as the whole of what somebody sent.
        """
        got = self.brought(Attachment("report.csv", 4096, writes=b"only the first bit"))
        self.assertEqual([], got, "half a file was reported as though it were the whole")
        self.assertEqual([], self.staged(), "the half that arrived was left on disk")

    def test_a_save_that_raises_leaves_nothing_behind(self):
        """`files.landed` removes every staged file it is *told about*, taken or refused — and
        `files.swept` never looks in here. A path this does not report is one nothing can ever
        remove, so the debris would stand for the life of the install."""
        got = self.brought(Attachment("report.csv", 8, raises=OSError("the socket went away")))
        self.assertEqual([], got)
        self.assertEqual([], self.staged())

    def test_a_file_the_platform_says_is_too_big_costs_no_bandwidth(self):
        """Refused on what Discord declared, before a byte is fetched."""
        got = self.brought(Attachment("huge.bin", adapter.BROUGHT_BYTES + 1))
        self.assertEqual([], got)
        self.assertEqual([], self.staged())

    def test_only_the_first_ten_are_brought_in(self):
        got = self.brought(*[Attachment(f"{nth}.txt", 4) for nth in range(adapter.BROUGHT_MOST + 3)])
        self.assertEqual(adapter.BROUGHT_MOST, len(got))

    def test_with_nowhere_to_put_them_nothing_is_fetched_and_it_is_said(self):
        os.environ.pop("RUNDESK_CHANNEL_HOME", None)
        message = Message(8841, DMChannel(1180), self.asker, "here you go")
        message.attachments = [Attachment("report.csv", 8)]
        got: List[Any] = []

        async def doing(reaching: Any) -> None:
            got.append(await reaching._brought(message))

        said = self.during(doing)
        self.assertEqual([], got[0])
        self.assertTrue([one for one in said if one.get("say") == "note"],
                        "nothing was said about having nowhere to put what arrived")


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

    def test_a_successful_upload_closes_its_temporary_snapshot(self) -> None:
        project = tempfile.TemporaryDirectory()
        self.addCleanup(project.cleanup)
        at = Path(project.name) / "project" / "preview.png"
        at.parent.mkdir(parents=True)
        at.write_bytes(b"pixels")
        sent = self.delivering(
            place="500", files=[{"name": "preview.png", "at": str(at.resolve()), "bytes": 6,
                                  "sha256": hashlib.sha256(b"pixels").hexdigest()}])
        uploaded = sent["files"][0]
        self.assertTrue(uploaded.fp.closed,
                        "a successful upload left its verification snapshot open")

    def test_a_file_replaced_by_a_pipe_is_refused_without_blocking(self) -> None:
        project = tempfile.TemporaryDirectory()
        self.addCleanup(project.cleanup)
        at = Path(project.name).resolve() / "preview.png"
        at.write_bytes(b"pixels")
        said = {"name": "preview.png", "at": str(at), "bytes": 6,
                "sha256": hashlib.sha256(b"pixels").hexdigest()}
        at.unlink()
        os.mkfifo(str(at))
        opened = adapter.os.open
        final_flags: List[int] = []

        def opening(name: Any, flags: int, *args: Any, **kwargs: Any) -> int:
            if name == at.name:
                final_flags.append(flags)
                # Keep the regression itself bounded even against the broken implementation.
                flags |= os.O_NONBLOCK
            return opened(name, flags, *args, **kwargs)

        adapter.os.open = opening
        self.addCleanup(setattr, adapter.os, "open", opened)
        with self.assertRaises(adapter.Refused):
            adapter.a_verified_file(said)
        self.assertTrue(final_flags[0] & os.O_NONBLOCK,
                        "the final component may block before it is known to be regular")

    def test_a_file_changed_after_approval_refuses_words_and_file_together(self) -> None:
        project = tempfile.TemporaryDirectory()
        self.addCleanup(project.cleanup)
        at = Path(project.name).resolve() / "preview.png"
        at.write_bytes(b"first!")
        said = {"do": "deliver", "id": "changed-1", "place": "500", "text": "preview",
                "files": [{"name": "preview.png", "at": str(at), "bytes": 6,
                           "sha256": hashlib.sha256(b"first!").hexdigest()}]}
        at.write_bytes(b"second")

        async def exchange(reaching: Any) -> None:
            await reaching._deliver(said)

        records = self.during(exchange)
        self.assertTrue([one for one in records if one.get("say") == "failed"])
        place = self.client.places.get(500)
        self.assertTrue(place is None or not place.sent)

    def test_a_snapshot_that_cannot_be_made_still_says_the_delivery_failed(self) -> None:
        # **The one failure in this function that was not turned into a `Refused`.** Everything
        # inside the walk converts, but the snapshot was opened above the `try`, so a `TMPDIR` that
        # is full or unwritable raised an `OSError` straight past `_deliver` — whose `except` names
        # only `Refused`, `TypeError` and `ValueError` — and into `_reading`, which logs and reads
        # on. No `failed` was ever emitted, so rundesk's id stayed in `awaiting`, `_landed` sat out
        # its whole ceiling, nothing was collected into `refusals`, and `told` answered `True`:
        # the answer was reported delivered when not one byte of it was sent.
        project = tempfile.TemporaryDirectory()
        self.addCleanup(project.cleanup)
        at = Path(project.name).resolve() / "preview.png"
        at.write_bytes(b"pixels")
        said = {"do": "deliver", "id": "no-room-1", "place": "500", "text": "preview",
                "files": [{"name": "preview.png", "at": str(at), "bytes": 6,
                           "sha256": hashlib.sha256(b"pixels").hexdigest()}]}

        def no_room(*_args: Any, **_kwargs: Any) -> Any:
            raise OSError(28, "No space left on device")

        async def exchange(reaching: Any) -> None:
            with mock.patch.object(adapter.tempfile, "TemporaryFile", no_room):
                await reaching._deliver(said)

        records = self.during(exchange)
        refused = [one for one in records if one.get("say") == "failed"]
        self.assertEqual(1, len(refused),
                         f"nothing said the delivery failed, so it reads as sent: {records}")
        self.assertEqual("no-room-1", refused[0].get("id"),
                         "the refusal named no delivery, so nothing could be released by it")
        place = self.client.places.get(500)
        self.assertTrue(place is None or not place.sent,
                        "words went out for a delivery whose file was never verified")

    def test_discord_file_verification_leaves_the_event_loop_free(self) -> None:
        entered = threading.Event()
        release = threading.Event()
        verifying = adapter.a_verified_file
        self.addCleanup(setattr, adapter, "a_verified_file", verifying)

        def blocked(_said: Any) -> Any:
            entered.set()
            release.wait(1.0)
            raise adapter.Refused("fixture refusal")

        adapter.a_verified_file = blocked
        elapsed = []

        async def exchange(reaching: Any) -> None:
            began = time.monotonic()
            delivering = asyncio.create_task(reaching._deliver(
                {"do": "deliver", "id": "slow-1", "place": "500", "text": "preview",
                 "files": [{}]}))
            while not entered.is_set():
                await asyncio.sleep(0)
            release.set()
            await delivering
            elapsed.append(time.monotonic() - began)

        self.during(exchange)
        self.assertLess(elapsed[0], 0.5, "file verification blocked the adapter event loop")

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


class HowLongTheIndicatorRuns(Records):
    """The typing indicator, which is what `working` looks like on this platform (R-DIS-6).

    Nothing repeats on the seam — `working` is sent once, when the turn is admitted — so an
    indicator that lapses after ten seconds has to be renewed on this side's own clock. A turn that
    is still running and looks finished is the failure this exists to prevent.
    """

    async def marking(self, reaching: Any, place: str, state: str,
                      external_id: Optional[str] = None) -> None:
        said = {"do": "state", "place": place, "state": state}
        if external_id:
            said["external_id"] = external_id
        await reaching._state(said)

    def test_a_turn_being_worked_on_starts_the_indicator(self) -> None:
        async def exchange(reaching: Any) -> None:
            await self.marking(reaching, "800", "working")
            self.assertIn(800, reaching.typing)
            reaching._typing_stops(800)

        self.during(exchange)

    def test_it_is_renewed_rather_than_set_once(self) -> None:
        # Discord's own lapses in about ten seconds. Renewed inside that, on this side's clock.
        self.assertLess(adapter.TYPING_SECONDS, 10.0)

        async def exchange(reaching: Any) -> None:
            reaching._typing_starts(800)
            for _ in range(4):             # let the loop go round more than once
                await asyncio.sleep(0)
            reaching._typing_stops(800)

        self.during(exchange)
        self.assertGreaterEqual(len(self.client.places[800].typed), 1)

    def test_asking_twice_renews_one_indicator_and_not_two(self) -> None:
        async def exchange(reaching: Any) -> None:
            await self.marking(reaching, "800", "working")
            first = reaching.typing[800]
            await self.marking(reaching, "800", "working")
            self.assertIs(first, reaching.typing[800])
            reaching._typing_stops(800)

        self.during(exchange)

    def test_every_way_a_turn_can_end_stops_it(self) -> None:
        # An indicator that outlived its turn says the agent is still working on something it
        # finished, which is worse than never having shown one.
        for ending in ("done", "stopped", "failed"):
            async def exchange(reaching: Any, ending: str = ending) -> None:
                await self.marking(reaching, "800", "working")
                self.assertIn(800, reaching.typing)
                await self.marking(reaching, "800", ending, external_id="84")
                self.assertNotIn(800, reaching.typing, f"{ending} left the indicator running")

            self.during(exchange)

    def test_a_message_being_seen_does_not_start_or_stop_one(self) -> None:
        # `seen` belongs to a message arriving and has no turn behind it.
        async def exchange(reaching: Any) -> None:
            await self.marking(reaching, "800", "seen", external_id="84")
            self.assertNotIn(800, reaching.typing)
            await self.marking(reaching, "800", "working")
            await self.marking(reaching, "800", "seen", external_id="85")
            self.assertIn(800, reaching.typing, "a second message stopped the turn's indicator")
            reaching._typing_stops(800)

        self.during(exchange)

    def test_one_refusal_ends_it_rather_than_asking_again_for_the_whole_turn(self) -> None:
        # An indicator is fidelity and a turn completes without one, so asking again every eight
        # seconds for the length of a turn would spend a rate limit saying nothing.
        #
        # **The task ending is the assertion, not the call count.** Counting calls proves nothing:
        # a loop that went on retrying would sleep for TYPING_SECONDS before the second one, which
        # is longer than any case here waits — so the toothless version passed either way.
        held: List[Any] = []

        async def exchange(reaching: Any) -> None:
            where = self.client.get_partial_messageable(800)
            where.typing_refuses = RuntimeError("Discord would not take it")
            reaching._typing_starts(800)
            held.append(reaching.typing[800])
            for _ in range(6):
                await asyncio.sleep(0)
            self.assertTrue(held[0].done(), "it is still waiting to ask again after a refusal")
            self.assertIsNone(held[0].exception(), "the refusal escaped the loop")

        records = self.during(exchange)
        self.assertEqual(1, len(self.client.places[800].typed))
        self.assertTrue(any("no typing indicator" in one for one in self.noted(records)))


class WhatItOffers(unittest.TestCase):
    """The nine gestures, and the words each speaks. Pure tables — no connection."""

    #: Rundesk's own closed vocabularies, written out rather than imported: this suite imports
    #: nothing of rundesk's, because the adapter is a program on the far side of a pipe.
    RUNDESK_CONTROLS = ("stop", "forget", "restart", "shutdown")
    RUNDESK_QUERIES = ("status", "version", "skills", "schedules")

    def test_every_gesture_speaks_a_word_rundesk_knows(self) -> None:
        # A name here that rundesk does not know is a command that appears on the menu, is pressed,
        # and does nothing at all — with no refusal anywhere for anybody to read.
        self.assertEqual(set(self.RUNDESK_CONTROLS), {one[2] for one in adapter.CONTROLS})
        self.assertEqual(set(self.RUNDESK_QUERIES), {one[2] for one in adapter.QUERIES})

    def test_the_nine_a_person_is_offered(self) -> None:
        offered = [one[0] for one in adapter.CONTROLS] + [one[0] for one in adapter.QUERIES]
        offered.append(adapter.CONFIGURE[0])
        self.assertEqual(
            {"stop", "new", "restart", "shutdown", "status", "version", "skills", "schedules",
             "provider"}, set(offered))

    def test_new_is_what_a_person_sees_and_forget_is_what_rundesk_hears(self) -> None:
        # *New* says what they get; *forget* says what happens to the session. Two words for one
        # gesture, and the seam speaks the second.
        named, _describes, spoken = next(one for one in adapter.CONTROLS if one[0] == "new")
        self.assertEqual("new", named)
        self.assertEqual("forget", spoken)

    def test_every_gesture_is_described_where_it_is_offered(self) -> None:
        # R-DIS-10. A command with no description is one somebody has to already know.
        for name, describes, _spoken in adapter.CONTROLS + adapter.QUERIES:
            self.assertTrue(describes.strip(), f"/{name} has nothing to say for itself")
            self.assertLessEqual(len(describes), 100, f"/{name} is past Discord's own limit")
        self.assertTrue(adapter.CONFIGURE[1].strip())

    def test_the_invite_asks_to_be_installed_as_a_command_provider(self) -> None:
        # Without this scope every command registers cleanly, syncs without error, and never
        # appears — and there is no refusal anywhere to read.
        self.assertIn("applications.commands", adapter.SCOPES)
        self.assertIn("scope=bot+applications.commands", adapter.invited(4471))


class HowAGestureIsAnswered(Records):
    """What crosses the seam when somebody presses one, and what comes back."""

    def pressed(self, named: str, who: int = 22, **also: Any) -> List[Dict[str, Any]]:
        """One command pressed, and the records it put on stdout."""
        interaction = Interaction(named, Person(who), place=700)

        async def exchange(reaching: Any) -> None:
            found = self.command(reaching, named)
            await (found(interaction, **also) if also else found(interaction))
            self.interaction = interaction

        return self.during(exchange)

    @staticmethod
    def command(reaching: Any, named: str):
        for name, _describes, control in adapter.CONTROLS:
            if name == named:
                return reaching._a_control(name, control)
        for name, _describes, query in adapter.QUERIES:
            if name == named:
                return reaching._a_query(query)
        return reaching._the_provider()

    def test_a_control_says_the_word_rundesk_speaks(self) -> None:
        said = self.only(self.pressed("new"), "control")
        self.assertEqual("forget", said["control"])
        self.assertEqual("700", said["conversation"])
        self.assertEqual("22", said["user"])

    def test_a_control_is_held_open_and_completed_by_what_rundesk_says(self) -> None:
        # R-DIS-11. Answered on the spot, the only thing there is to say is *heard* — so somebody
        # who pressed `/stop` where nothing was running was left looking at a placeholder while the
        # sentence telling them so was thrown away for want of anywhere to put it.
        async def exchange(reaching: Any) -> None:
            interaction = Interaction("stop", Person(22), place=700)
            await reaching._a_control("stop", "stop")(interaction)
            self.assertIs(interaction.deferred, True, "Discord's three seconds were not answered")
            await reaching._told({"do": "answered", "ref": str(interaction.id),
                                  "text": "✋ Nothing is running here."})
            self.assertEqual(["✋ Nothing is running here."],
                             [one["text"] for one in interaction.followed])
            self.assertTrue(all(one["ephemeral"] for one in interaction.followed))

        self.during(exchange)

    def test_a_query_is_held_open_and_named_by_its_own_id(self) -> None:
        said = self.only(self.pressed("skills"), "query")
        self.assertEqual("skills", said["query"])
        self.assertEqual(str(self.interaction.id), said["ref"])
        self.assertIs(self.interaction.deferred, True)
        self.assertIn(str(self.interaction.id), self.reaching.asked)

    def test_an_answer_completes_the_interaction_that_asked_it(self) -> None:
        async def exchange(reaching: Any) -> None:
            first = Interaction("skills", Person(22), place=700)
            second = Interaction("status", Person(22), place=700)
            await reaching._a_query("skills")(first)
            await reaching._a_query("status")(second)
            await reaching._told({"do": "answered", "ref": str(second.id), "text": "🟢 online"})
            self.assertEqual(["🟢 online"], [one["text"] for one in second.followed])
            self.assertEqual([], first.followed, "the wrong interaction was completed")

        self.during(exchange)

    def test_an_answer_for_a_question_nobody_asked_is_dropped(self) -> None:
        async def exchange(reaching: Any) -> None:
            await reaching._told({"do": "answered", "ref": "nobody", "text": "hello"})

        self.during(exchange)

    def test_somebody_this_channel_does_not_allow_is_told_so_and_reports_nothing(self) -> None:
        # Advisory only — rundesk refuses again in silence. It exists so a stranger is not left
        # watching a deferred question that will never be answered.
        records = self.pressed("status", who=9999)
        self.assertEqual([], [one for one in records if one.get("say") == "query"])
        self.assertEqual([adapter.NOT_YOURS],
                         [one["text"] for one in self.interaction.answered])

    def test_shutting_down_asks_once_before_it_does_it(self) -> None:
        # A one-way door: the bot goes offline and there is no command left to bring it back.
        first = self.pressed("shutdown")
        self.assertEqual([], [one for one in first if one.get("say") == "control"],
                         "a mistyped slash shut the gateway down")
        self.assertIn("again", self.interaction.answered[0]["text"])

    def test_pressing_it_twice_confirms_it(self) -> None:
        async def exchange(reaching: Any) -> None:
            asking = reaching._a_control("shutdown", "shutdown")
            await asking(Interaction("shutdown", Person(22), place=700))
            await asking(Interaction("shutdown", Person(22), place=700))

        said = [one for one in self.during(exchange) if one.get("say") == "control"]
        self.assertEqual(["shutdown"], [one["control"] for one in said])

    def test_one_persons_confirmation_is_not_anothers(self) -> None:
        async def exchange(reaching: Any) -> None:
            reaching.allow = ["22", "33"]
            asking = reaching._a_control("shutdown", "shutdown")
            await asking(Interaction("shutdown", Person(22), place=700))
            await asking(Interaction("shutdown", Person(33), place=700))

        said = [one for one in self.during(exchange) if one.get("say") == "control"]
        self.assertEqual([], said, "one person's warning confirmed another person's shutdown")

    def test_the_provider_gesture_carries_what_was_typed(self) -> None:
        said = self.only(self.pressed("provider", provider="codex"), "configure")
        self.assertEqual("codex", said["provider"])
        self.assertEqual(str(self.interaction.id), said["ref"])

    def test_all_nine_are_registered(self) -> None:
        async def exchange(reaching: Any) -> None:
            reaching.tree = adapter.discord.app_commands.CommandTree(self.client)
            reaching._offers()
            self.assertEqual(9, len(reaching.tree.commands))

        self.during(exchange)

    def test_they_are_offered_once_and_not_on_every_reconnection(self) -> None:
        # A global sync is rate-limited hard, and a bot reconnecting through a bad hour would spend
        # its whole allowance re-registering nine commands that have not changed.
        async def exchange(reaching: Any) -> None:
            reaching.tree = adapter.discord.app_commands.CommandTree(self.client)
            for _ in range(4):
                await reaching._synced()
            self.assertEqual(1, reaching.tree.synced)

        self.during(exchange)

    def test_a_sync_that_failed_is_said_and_names_the_scope_to_check(self) -> None:
        # The failure with no symptom: without `applications.commands` every command registers
        # cleanly and simply never appears, with no refusal anywhere to read.
        async def exchange(reaching: Any) -> None:
            reaching.tree = adapter.discord.app_commands.CommandTree(self.client)
            reaching.tree.refuses = RuntimeError("Missing Access")
            await reaching._synced()
            await reaching._synced()
            # Tried again rather than given up: a sync refused once is usually a scope somebody is
            # about to fix, and a bot that never retried would need restarting to offer anything.
            self.assertEqual(2, reaching.tree.attempts)
            self.assertEqual(0, reaching.tree.synced)

        records = self.during(exchange)
        self.assertTrue(any("applications.commands" in one for one in self.noted(records)))


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
        # Already offered: what is under test here is the dot in the member list, and a command
        # sync is a separate connection-time errand with a case of its own.
        self.hosting.offered = True

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
