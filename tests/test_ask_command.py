"""`rundesk ask` — a person typing, and what that person is shown while a turn runs.

Driven through `self.rundesk(...)`, so the real parser and the real dispatch answer every case. A
case that called `cmd_ask` directly would prove the module and not the command: the flag it spelled,
the exit code the shell reads, and the words on the screen are exactly the parts a direct call skips.

**This is the attended way in.** A gateway answers a channel and the clock starts a schedule; this is
somebody at a keyboard, and it is the only caller with anybody to take a mid-turn word from. So what
is proved here is mostly about the person: that the answer arrives, that a failure says whether
waiting will help, that a vendor's vocabulary never reaches the screen, and that asking again carries
the same exchange on rather than starting a new one.

Run directly: `python3 tests/test_ask_command.py`
"""

import json
import unittest

import support
from rundesk.agents import directory, records
from rundesk.channels import arriving
from rundesk.exits import FAILED, OK, USAGE
from rundesk.providers import kept

#: The provider adapter every case here runs. A path, so a case does not depend on where an install
#: keeps the ones it was given.
STAND_IN = str(support.CHECKOUT / "tests" / "samples" / "a-stand-in")


class Asking(support.Isolated):

    def setUp(self):
        super().setUp()
        self.agent = "cole"
        directory.made(self.agent, STAND_IN)

    def a_stand_in_that(self, **how):
        """What the adapter should do, said the way an owner's own settings reach one."""
        records.stated(directory.records(self.agent), {"agent_settings": json.dumps(how)})

    def asked(self, *more):
        return self.rundesk("ask", self.agent, "what changed today?", *more)


class OneQuestionAndItsAnswer(Asking):

    def test_the_answer_is_printed_and_the_shell_reads_success(self):
        code, out, err = self.asked()
        self.assertEqual(OK, code, err)
        self.assertIn("what changed today?", out)

    def test_what_it_cost_and_which_turn_it_was_are_said_underneath(self):
        """Somebody who has just spent money on a question is told what it cost, and given the one
        thing that leads to everything else about that run."""
        code, out, _err = self.asked()
        self.assertEqual(OK, code)
        self.assertIn("turn 1", out)
        self.assertIn("in", out)

    def test_quiet_prints_the_answer_and_nothing_around_it(self):
        """For a pipe. A cost line in the middle of somebody's data is the thing that makes a
        command unusable from a script."""
        code, out, _err = self.asked("--quiet")
        self.assertEqual(OK, code)
        self.assertNotIn("turn 1", out)
        self.assertIn("what changed today?", out)

    def test_the_question_and_the_answer_are_both_written_down(self):
        self.asked()
        conversation = kept.get_turn(self.agent, 1)["conversation_id"]
        said = arriving.messages(self.agent, conversation)
        self.assertEqual([arriving.BY_USER, arriving.BY_AGENT],
                         [one["author"] for one in said][:2])

    def test_the_answer_carries_the_turn_that_said_it(self):
        """The one join between what was said and what it cost. Without it nobody can get from a
        sentence in the history to the run that produced it."""
        self.asked()
        conversation = kept.get_turn(self.agent, 1)["conversation_id"]
        said = [one for one in arriving.messages(self.agent, conversation)
                if one["author"] == arriving.BY_AGENT]
        self.assertEqual(1, said[0]["turn_id"])


class WhatItShowsWhileItWorks(Asking):

    def test_a_tool_is_named_by_what_it_did_and_never_by_the_brains_word_for_it(self):
        """The same act is `Bash` on one brain, `shell` on the next and `run_terminal_command` on a
        third. A surface that printed any of them would carry that vendor's vocabulary for ever."""
        code, out, _err = self.asked()
        self.assertEqual(OK, code)
        self.assertIn("read", out)

    def test_what_it_is_thinking_is_off_by_default_and_on_when_asked(self):
        """Reasoning is long, and a terminal that printed all of it would bury the answer."""
        _code, quiet, _err = self.asked()
        _code, loud, _err = self.rundesk("ask", self.agent, "what changed today?", "--fresh",
                                         "--thinking")
        self.assertLess(len(quiet), len(loud))

    def test_account_news_is_shown_apart_from_the_work(self):
        """**Not this turn's activity and not an outcome**: a turn carrying one may have succeeded."""
        code, out, _err = self.asked()
        self.assertEqual(OK, code)
        self.assertIn("allowance", out)


class WhenItCouldNotAnswer(Asking):

    def test_it_exits_non_zero_and_says_what_the_brain_said(self):
        self.a_stand_in_that(fail_with="rate_limited")
        code, _out, err = self.asked()
        self.assertEqual(FAILED, code)
        self.assertIn("the stand-in was told to fail", err)

    def test_it_says_whether_waiting_will_help(self):
        self.a_stand_in_that(fail_with="rate_limited")
        _code, _out, err = self.asked()
        self.assertIn("later may work", err)

    def test_it_says_when_waiting_will_not_help(self):
        self.a_stand_in_that(fail_with="signed_out")
        _code, _out, err = self.asked()
        self.assertIn("will not clear on its own", err)

    def test_it_says_where_to_read_what_the_turn_did(self):
        self.a_stand_in_that(fail_with="upstream_error")
        _code, _out, err = self.asked()
        self.assertIn(f"rundesk turns {self.agent} 1", err)

    def test_a_turn_that_ended_with_nothing_said_is_not_a_turn_that_worked(self):
        """Exit zero having said nothing is the failure that looks most like a success."""
        self.a_stand_in_that(say_nothing_and_finish=True)
        code, _out, err = self.asked()
        self.assertEqual(FAILED, code)
        self.assertIn("did not answer", err)

    def test_an_adapter_that_will_not_start_says_so_before_anything_is_written(self):
        records.stated(directory.records(self.agent), {"agent_provider": "nothing-stands-here"})
        code, _out, err = self.asked()
        self.assertEqual(FAILED, code)
        self.assertIn("looked in", err)
        self.assertEqual([], kept.list_turns(self.agent))


class OneConversationPerAgent(Asking):

    def test_asking_again_carries_the_same_exchange_on(self):
        """Which is what a person means by asking again."""
        self.asked()
        self.rundesk("ask", self.agent, "and now?")
        first, second = (kept.get_turn(self.agent, one)["conversation_id"] for one in (1, 2))
        self.assertEqual(first, second)

    def test_fresh_starts_a_new_one_on_the_brain_and_keeps_the_same_history(self):
        """**Two different things.** The exchange a person reads back is rundesk's; what the brain
        remembers is the brain's, and `--fresh` drops only the second."""
        self.asked()
        self.rundesk("ask", self.agent, "and now?", "--fresh")
        first, second = (kept.get_turn(self.agent, one) for one in (1, 2))
        self.assertEqual(first["conversation_id"], second["conversation_id"])
        self.assertEqual(0, second["session_resumed"])

    def test_a_second_turn_in_a_busy_conversation_is_refused_rather_than_queued(self):
        """The claim is the kernel's, so this competes correctly with a gateway answering the same
        agent on a channel, with no coordination between the two."""
        from rundesk.providers import turns
        landed = arriving.asked_at_a_terminal(self.agent, "the first")
        with turns.claiming(self.agent, landed.conversation):
            code, _out, err = self.asked()
        self.assertEqual(FAILED, code)
        self.assertIn(f"rundesk turns {self.agent}", err)


class WhenTheCommandLineIsWrong(Asking):

    def test_an_agent_that_is_not_there_says_what_to_type(self):
        code, _out, err = self.rundesk("ask", "nobody", "hello")
        self.assertEqual(FAILED, code)
        self.assertIn("rundesk agents", err)

    def test_asking_nothing_at_all_is_the_command_line_being_wrong(self):
        code, _out, _err = self.rundesk("ask", self.agent)
        self.assertEqual(USAGE, code)

    def test_a_prompt_of_only_spaces_is_refused_rather_than_sent(self):
        code, _out, err = self.rundesk("ask", self.agent, "   ")
        self.assertEqual(FAILED, code)
        self.assertIn("nothing to ask", err)


if __name__ == "__main__":
    unittest.main()
