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
import importlib.machinery
import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

#: The install's own virtualenv, exactly as the adapter finds it.
for _packages in sorted((ROOT / ".venv" / "lib").glob("python3.*/site-packages")):
    sys.path.insert(0, str(_packages))


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
class AnAnswerInAThread(unittest.TestCase):
    """R-DIS-1 — being named opens a thread and the turn happens there, while the message
    that asked stays in the channel above it."""

    class Message:
        def __init__(self, channel_id):
            self.channel_id = channel_id

    def test_an_answer_does_not_quote_a_message_from_somewhere_else(self):
        """R-DIS-1 — Discord refuses a whole message that quotes one in another channel.
        So a turn in a thread ended with a ✅ on the question and no answer under it: the
        mark went on the message in the channel, which works, and the reply quoting that
        same message was rejected outright."""
        source = (ROOT / "src" / "channels" / "discord").read_text()
        self.assertIn('str(getattr(anchor, "channel_id", "")) != str(', source,
                      "an answer can still quote a message outside the place it is sent")

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
        def __init__(self, name=None):
            self.name = name

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

    def test_a_small_count_is_not_rounded_into_a_zero(self):
        """R-USE-7 — everything was shown in thousands, so a turn that answered in
        thirteen tokens reported `0k output`: a measurement, stated plainly, and wrong.
        An absent number means "could not tell" and a zero means zero, so neither may be
        invented by rounding."""
        said = discord._as_a_line({"type": "usage", "input": 4737, "output": 13,
                                   "cached": 13056})
        self.assertIn("13 output", said)
        self.assertNotIn("0k output", said)

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

    def test_what_the_agent_did_does_become_commentary(self):
        """R-DIS-20 — the other half, or the option would show nothing at all."""
        self.assertNotEqual("", discord.commentary(
            {"type": "tool", "name": "Bash", "did": "run"}))
        self.assertNotEqual("", discord.commentary(
            {"type": "think", "text": "the error is in the parser"}))

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

    def test_a_commentary_stops_growing_once_something_is_said_under_it(self):
        """R-DIS-20 — a message something has been posted under is one the reader has
        already scrolled past. Editing it changes history rather than showing progress:
        the new line appears above whatever came after it, where nobody is looking. So
        the next thing to show has to begin a message of its own."""
        held = discord.Live()
        held.posted, held.activity = object(), "-# 💻 ran a command"
        # Unbound on purpose: the decision uses nothing of the connection, which is what
        # makes it testable without one.
        discord.Agent._no_longer_last(None, held)
        self.assertIsNone(held.posted, "it would have gone on editing a buried message")
        self.assertEqual("", held.activity,
                         "a fresh message would have opened with the old one's lines")

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
        self.assertIn("no such file", said)

    def test_every_verb_the_seam_defines_has_a_mark_of_its_own(self):
        """R-PRV-8, R-CAD-4 — the list of what a tool did is the seam's and is closed. A
        verb with no mark here would quietly show as the fallback, which reads as "we do
        not know what that was" for something the contract does name."""
        from rundesk import provider

        self.assertEqual(set(provider.DID), set(discord.DID),
                         "this surface and the seam disagree about what a tool can do")
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


@unittest.skipIf(discord is None, "discord.py is not installed — run ./install.sh")
class WhatItOffersAndWhatItIsTold(unittest.TestCase):
    """R-DIS-10, R-CAD-11, R-CAD-13 — its commands, its options, and its credential."""

    def test_every_command_it_offers_is_a_gesture_the_seam_defines(self):
        """R-DIS-10 — the platform picks the word its people recognise and the seam keeps
        the meaning, so a surface cannot invent a gesture nothing acts on."""
        from rundesk import channel

        for _name, _describes, gesture, _said in discord.COMMANDS:
            self.assertIn(gesture, channel.CONTROLS)

    def test_every_command_is_described_where_it_is_offered(self):
        """R-DIS-10 — a command nobody can tell the purpose of is one nobody uses."""
        for name, describes, _gesture, said in discord.COMMANDS:
            self.assertTrue(name and describes and said, f"{name} is not fully described")

    def test_a_new_session_and_stopping_a_turn_are_different_gestures(self):
        """R-CH-9, R-CH-10 — one ends what is running and the other throws away where the
        conversation had got to."""
        gestures = {name: gesture for name, _d, gesture, _s in discord.COMMANDS}
        self.assertEqual("forget", gestures["new"])
        self.assertEqual("stop", gestures["stop"])
        self.assertEqual("restart", gestures["restart"])

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


@unittest.skipIf(discord is None, "discord.py is not installed — run ./install.sh")
class WhatTheOwnerIsTold(unittest.TestCase):
    """R-DIS-15, R-DIS-16 — coming up, going down, and closing the connection either way."""

    class Stand:
        """Exactly the surface `going` touches, and no more — a stand-in more generous
        than the real thing is what hides a whole feature behind a green suite."""

        def __init__(self, slow=0.0):
            self.live, self.closed, self.greeted, self._slow = {}, False, [], slow

        async def _tell_the_owner(self, said):
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

        def __init__(self):
            self.greeted, self.said = False, []

        async def change_presence(self, **kw):
            pass

        async def _tell_the_owner(self, said):
            self.said.append(said)

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
