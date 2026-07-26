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
    at = ROOT / "src" / "rundesk_cli" / "channels" / "discord"
    loader = importlib.machinery.SourceFileLoader("rundesk_discord", str(at))
    spec = importlib.util.spec_from_loader("rundesk_discord", loader)
    made = importlib.util.module_from_spec(spec)
    loader.exec_module(made)
    return made


try:
    discord = _adapter()
except BaseException as why:  # pragma: no cover - proved by the install
    discord = None
    WHY = str(why)


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
        """R-DIS-2 — naming no channel is a choice, not an omission."""
        self.assertTrue(discord.within(False, belongs_to="9999",
                                       listens_in=None, dms=False))

    def test_a_direct_message_is_answered_only_when_that_is_what_was_asked_for(self):
        """R-DIS-4 — a channel pointed at a room is not also a channel for private
        messages, and an agent answering both when told about one is answering
        somewhere its owner never put it."""
        self.assertTrue(discord.within(True, belongs_to=None, listens_in=None, dms=True))
        self.assertFalse(discord.within(True, belongs_to=None, listens_in="1180",
                                        dms=False))


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
        from rundesk_cli import channel

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

    def test_a_tool_that_failed_still_says_so(self):
        """R-DIS-9 — what somebody watching wants is the thing that did not work."""
        said = discord._as_a_line(
            {"type": "result", "id": "1", "ok": False, "summary": "no such file"})
        self.assertIn("no such file", said)

    def test_a_tool_is_marked_by_what_it_did_and_never_by_its_brains_name_for_it(self):
        """R-CAD-13 — recognising a vendor's own tool names would carry that vendor's
        vocabulary into this file forever."""
        self.assertIn(discord.DID["run"], discord._as_a_line(
            {"type": "tool", "name": "Bash", "did": "run"}))
        self.assertIn("⚙", discord._as_a_line(
            {"type": "tool", "name": "SomethingNobodyKnows"}))


@unittest.skipIf(discord is None, "discord.py is not installed — run ./install.sh")
class WhatItOffersAndWhatItIsTold(unittest.TestCase):
    """R-DIS-10, R-CAD-11, R-CAD-13 — its commands, its options, and its credential."""

    def test_every_command_it_offers_is_a_gesture_the_seam_defines(self):
        """R-DIS-10 — the platform picks the word its people recognise and the seam keeps
        the meaning, so a surface cannot invent a gesture nothing acts on."""
        from rundesk_cli import channel

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
        self.assertEqual({"bot", "server", "channel", "dm", "token_from", "unknown"},
                         set(vars(said)),
                         "an option appeared that could carry a secret as its value")


@unittest.skipIf(discord is None, "discord.py is not installed — run ./install.sh")
class WhatItSaysBack(unittest.TestCase):
    """R-CAD-1 — what it reports is what the seam understands, and nothing else."""

    def test_everything_it_reports_is_a_record_the_seam_knows(self):
        """R-CAD-1 — a record of a kind nobody knows is kept and acted on by nothing, so
        an adapter reporting one is talking to itself."""
        from rundesk_cli import channel

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


if __name__ == "__main__":
    if discord is None:
        print(f"discord.py is not installed, so nothing here can run: {WHY}", file=sys.stderr)
    unittest.main(verbosity=2)
