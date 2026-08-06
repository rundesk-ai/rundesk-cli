"""`rundesk messages` — what an agent said and was told, and how anything is found in it again.

Driven through `self.rundesk(...)`, so the real parser and the real dispatch answer every case.

**The agent is the primary caller, and that shapes everything here.** Its own instructions name this
command, so it reads its own history back before answering a question about work it has no record of
— which means every line costs tokens. So the default is one bounded line per hit and `--full` is
the exception, and a narrowing that does not narrow is a turn's worth of tokens spent on nothing.

**Search is answered by an index when there is one and by a scan when there is not, and it says
which.** A `LIKE` scan has no stemming, no phrase and no ranking; it finds different things, and a
caller told nothing about the difference would read an empty answer as an absence.

Run directly: `python3 tests/test_messages_command.py`
"""

import unittest
from unittest import mock

import support
from rundesk.agents import directory
from rundesk.channels import arriving
from rundesk.exits import FAILED, OK, USAGE
from rundesk.providers import kept

STAND_IN = str(support.CHECKOUT / "tests" / "samples" / "a-stand-in")


class Messages(support.Isolated):

    def setUp(self):
        super().setUp()
        self.agent = "cole"
        directory.made(self.agent, STAND_IN)

    def on_a_channel(self, text, place="ops", channel="discord", who="2207"):
        return arriving.recorded(self.agent, channel, place, who, text)

    def at_a_terminal(self, text):
        return arriving.asked_at_a_terminal(self.agent, text)

    def for_a_schedule(self, text, schedule="nightly"):
        return arriving.recorded_for_a_schedule(self.agent, schedule, text)


class Listing(Messages):

    def test_an_agent_that_has_said_nothing_says_so_rather_than_printing_a_heading(self):
        code, out, _err = self.rundesk("messages", self.agent)
        self.assertEqual(OK, code)
        self.assertIn("nothing", out)

    def test_each_message_says_who_said_it_where_and_when(self):
        self.on_a_channel("what changed today?")
        code, out, _err = self.rundesk("messages", self.agent)
        self.assertEqual(OK, code)
        for said in ("user", "discord", "what changed today?"):
            self.assertIn(said, out)

    def test_newest_first_because_that_is_what_somebody_asking_wants(self):
        self.on_a_channel("the older one")
        self.on_a_channel("the newer one")
        _code, out, _err = self.rundesk("messages", self.agent)
        self.assertLess(out.index("the newer one"), out.index("the older one"))

    def test_a_long_message_is_one_bounded_line_unless_the_whole_of_it_is_asked_for(self):
        """Every line costs tokens, and the agent is the primary caller."""
        self.on_a_channel("x" * 400)
        _code, bounded, _err = self.rundesk("messages", self.agent)
        _code, whole, _err = self.rundesk("messages", self.agent, "--full")
        self.assertLess(len(bounded), len(whole))
        self.assertIn("x" * 400, whole)

    def test_an_agent_that_is_not_there_says_what_to_type(self):
        code, _out, err = self.rundesk("messages", "nobody")
        self.assertEqual(FAILED, code)
        self.assertIn("rundesk agents", err)

    def test_a_limit_that_is_not_a_count_is_the_command_line_being_wrong(self):
        code, _out, _err = self.rundesk("messages", self.agent, "--limit", "0")
        self.assertEqual(USAGE, code)


class Narrowing(Messages):
    """The part the agent's own instructions name, and the part that has to actually narrow."""

    def test_one_exchange_and_nothing_from_any_other(self):
        here = self.on_a_channel("in this one")
        self.on_a_channel("in another", place="general")
        _code, out, _err = self.rundesk("messages", self.agent,
                                        "--conversation", str(here.conversation))
        self.assertIn("in this one", out)
        self.assertNotIn("in another", out)

    def test_one_channel_and_nothing_from_another(self):
        self.on_a_channel("said on discord", channel="discord")
        self.on_a_channel("said on slack", channel="slack", place="rooms")
        _code, out, _err = self.rundesk("messages", self.agent, "--channel", "slack")
        self.assertIn("said on slack", out)
        self.assertNotIn("said on discord", out)

    def test_work_the_clock_started_told_apart_from_somebody_typing(self):
        """The narrowing the agent's own instructions name by hand, because *what have I been doing
        overnight* and *what did you ask me* are different questions."""
        self.at_a_terminal("somebody typed this")
        self.for_a_schedule("the clock started this")
        _code, out, _err = self.rundesk("messages", self.agent, "--source", "schedule")
        self.assertIn("the clock started this", out)
        self.assertNotIn("somebody typed this", out)

    def test_a_narrowing_that_matches_nothing_says_so_and_says_what_it_narrowed_by(self):
        """An empty answer that does not repeat the question back reads as *there is nothing*
        rather than as *there is nothing here*."""
        self.on_a_channel("something")
        code, out, _err = self.rundesk("messages", self.agent, "--channel", "nowhere")
        self.assertEqual(OK, code)
        self.assertIn("nothing", out)
        self.assertIn("nowhere", out)

    def test_only_what_is_recent_enough(self):
        self.on_a_channel("today's")
        _code, out, _err = self.rundesk("messages", self.agent, "--since", "2099-01-01")
        self.assertNotIn("today's", out)


class Searching(Messages):

    def test_it_finds_a_word_and_shows_where_it_matched(self):
        self.on_a_channel("the deployment went out at nine")
        code, out, _err = self.rundesk("messages", self.agent, "--search", "deployment")
        self.assertEqual(OK, code)
        self.assertIn("deployment", out)

    def test_it_leaves_out_what_does_not_hold_the_word(self):
        self.on_a_channel("the deployment went out at nine")
        self.on_a_channel("lunch is at one")
        _code, out, _err = self.rundesk("messages", self.agent, "--search", "deployment")
        self.assertNotIn("lunch", out)

    def test_a_search_can_be_narrowed_to_one_channel(self):
        """The whole point: *what did somebody ask me on Discord about the release* is one question,
        and an answer drawn from every surface at once is not it."""
        self.on_a_channel("the release is out", channel="discord")
        self.on_a_channel("the release is out", channel="slack", place="rooms")
        _code, out, _err = self.rundesk("messages", self.agent, "--search", "release",
                                        "--channel", "slack")
        # The body comes back as an excerpt with the match marked, so what is counted is the rows.
        self.assertEqual(1, len([one for one in out.splitlines() if one.startswith("2026-")]))
        self.assertNotIn("discord", out)

    def test_finding_nothing_says_so_and_repeats_what_was_looked_for(self):
        self.on_a_channel("something")
        code, out, _err = self.rundesk("messages", self.agent, "--search", "nowhere")
        self.assertEqual(OK, code)
        self.assertIn("nowhere", out)

    def test_an_install_with_no_index_still_answers_and_says_it_is_falling_back(self):
        """A scan has no stemming, no phrase and no ranking, so it finds different things — and a
        caller not told that would read a shorter answer as a smaller history."""
        self.on_a_channel("the deployment went out at nine")
        with mock.patch.object(kept, "has_search_index", return_value=False):
            code, out, _err = self.rundesk("messages", self.agent, "--search", "deployment")
        self.assertEqual(OK, code)
        self.assertIn("deployment", out)
        self.assertIn("no search index on this install", out)


class WhatATurnSaid(Messages):
    """A turn's answer is a message like any other, and it carries the turn that said it."""

    def test_an_answer_is_listed_beside_the_question_that_caused_it(self):
        code, _out, err = self.rundesk("ask", self.agent, "what changed today?")
        self.assertEqual(OK, code, err)
        _code, out, _err = self.rundesk("messages", self.agent)
        self.assertIn("what changed today?", out)
        self.assertIn("agent", out)


if __name__ == "__main__":
    unittest.main()
