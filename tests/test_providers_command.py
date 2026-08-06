"""`rundesk providers` — what a person types, and what a person is shown.

Driven through `self.rundesk(...)`, so the real parser and the real dispatch answer every case. A
case that called `cmd_providers` directly would prove the module and not the command: the sub-verb it
registered, the flag it spelled, and the exit code the shell reads are exactly the parts a direct
call skips.

Four verbs, and they are asked for four different reasons. **`list` and `check` are the offline
pair** — what can this install run, and what does one of them say it can do — and neither needs an
account, a network or an agent. **`instructions` is the prompt in front of somebody**, which is the
only way the standing words an agent works under can be read, tweaked and compared against a turn
that has already happened. **`run` is what a firing starts**, and it is on the command surface
because a schedule that cannot be tried by hand is a schedule nobody can debug.

Run directly: `python3 tests/test_providers_command.py`
"""

import unittest
from unittest import mock

import support
from rundesk.agents import directory
from rundesk.core import paths
from rundesk.exits import FAILED, OK, USAGE
from rundesk.providers import adapters, instructions, kept
from rundesk.schedules import kept as schedules_kept

#: The smallest legitimate adapter: it answers `--capabilities` and can do nothing.
SAYS_NOTHING = """#!/bin/sh
printf '%s\\n' '{}'
"""


class Providers(support.Isolated):

    def setUp(self):
        super().setUp()
        # `paths.code()` answers with the checkout until an install exists, so a case that wrote an
        # adapter without this would write it into the repository somebody is working in — and
        # `list` would answer with whatever this release happens to ship.
        (paths.home() / "app" / "src").mkdir(parents=True, exist_ok=True)
        self.shipped = paths.code() / adapters.SHIPPED_IN
        self.shipped.mkdir(parents=True, exist_ok=True)

    def an_adapter(self, named="a-brain", body=SAYS_NOTHING, runnable=True):
        at = self.shipped / named
        at.write_text(body, encoding="utf-8")
        at.chmod(0o755 if runnable else 0o644)
        return at

    def an_agent(self, named="cole", provider=support.A_STAND_IN):
        directory.made(named, provider)
        return named


class Listing(Providers):

    def test_an_install_with_none_says_so_and_says_where_they_go(self):
        # `as_table` prints nothing at all when there are no rows, headings included — so a listing
        # that leant on it would print nothing and leave "there are none" to be inferred silence.
        code, out, _err = self.rundesk("providers")
        self.assertEqual(OK, code)
        self.assertIn("no provider adapter here yet", out)
        self.assertIn(str(paths.data() / adapters.GIVEN_IN), out)

    def test_each_one_is_shown_with_the_program_behind_it(self):
        """The program, not just the name: two installs on one machine is the case where knowing
        *which* file answers to a name is the whole question."""
        made = self.an_adapter("a-brain")
        code, out, _err = self.rundesk("providers", "list")
        self.assertEqual(OK, code)
        self.assertIn("a-brain", out)
        self.assertIn(str(made), out)

    def test_a_file_that_cannot_be_run_is_not_offered_as_one(self):
        self.an_adapter("half-installed", runnable=False)
        code, out, _err = self.rundesk("providers")
        self.assertEqual(OK, code)
        self.assertNotIn("half-installed", out)


class Checking(Providers):

    def test_it_shows_each_capability_as_yes_or_no_and_never_only_the_yeses(self):
        """**Absent means no**, and a person has to be able to see the no. A list of what a brain
        can do, with the rest left out, reads as a shorter list of capabilities rather than as a
        complete answer."""
        self.an_adapter("a-brain", SAYS_NOTHING)
        code, out, _err = self.rundesk("providers", "check", "a-brain")
        self.assertEqual(OK, code)
        for can in ("tools", "resume", "model", "usage", "steer"):
            self.assertIn(can, out)
        self.assertIn("no", out)

    def test_whatever_it_volunteered_is_shown_apart_from_what_was_asked(self):
        """A version an adapter reports is the thing that explains a turn six months later, and it
        is kept because it was said — not because this release knows what it means."""
        self.an_adapter("a-brain", """#!/bin/sh
printf '%s\\n' '{"tools": true, "codex_cli": "0.146.0"}'
""")
        code, out, _err = self.rundesk("providers", "check", "a-brain")
        self.assertEqual(OK, code)
        self.assertIn("rundesk did not ask", out)
        self.assertIn("0.146.0", out)

    def test_a_name_nothing_stands_behind_fails_and_says_where_it_looked(self):
        code, _out, err = self.rundesk("providers", "check", "nowhere")
        self.assertEqual(FAILED, code)
        self.assertIn("looked in", err)

    def test_asking_with_no_name_is_the_command_line_being_wrong(self):
        code, _out, _err = self.rundesk("providers", "check")
        self.assertEqual(USAGE, code)


class Instructions(Providers):
    """The standing words an agent works under, in front of somebody who can change them."""

    def test_it_prints_the_prompt_with_what_each_layer_cost(self):
        agent = self.an_agent()
        code, out, err = self.rundesk("providers", "instructions", agent)
        self.assertEqual(OK, code, err)
        self.assertIn("core", out)
        self.assertIn("bytes", out)

    def test_the_situation_changes_what_is_said(self):
        """A person asking and a schedule falling due are different situations, and an agent that
        could not tell them apart would answer a clock as though somebody were waiting."""
        agent = self.an_agent()
        _code, asked, _err = self.rundesk("providers", "instructions", agent,
                                          "--trigger", "a_person_asked")
        _code, due, _err = self.rundesk("providers", "instructions", agent,
                                        "--trigger", "a_schedule_came_due")
        self.assertNotEqual(asked, due)

    def test_a_past_turn_is_recomposed_and_compared_rather_than_read_back(self):
        """Nothing stores what was sent. The fingerprint is re-derived, so a release that composes
        something different **says so** rather than quietly showing today's words as yesterday's."""
        agent = self.an_agent()
        code, _out, err = self.rundesk("ask", agent, "what changed today?")
        self.assertEqual(OK, code, err)
        code, out, err = self.rundesk("providers", "instructions", agent, "--turn", "1")
        self.assertEqual(OK, code, err)
        self.assertIn("turn 1", out)
        self.assertIn("unchanged since it ran", out)
        self.assertIn(agent, out)

    def test_a_release_that_composes_something_else_says_so_rather_than_showing_today(self):
        """**The whole reason nothing stores the prompt.** A stored copy survives a change to the
        composer; a fingerprint detects one — and a reader shown today's words as yesterday's has
        been told something untrue about a turn that has already happened."""
        agent = self.an_agent()
        self.rundesk("ask", agent, "what changed today?")
        with mock.patch.object(instructions, "CORE", instructions.CORE + "\n\nAnd one more rule."):
            code, out, err = self.rundesk("providers", "instructions", agent, "--turn", "1")
        self.assertEqual(OK, code, err)
        self.assertIn("composes a different prompt", out)
        self.assertIn("today's words", out)

    def test_a_turn_asked_for_without_an_agent_says_what_to_type(self):
        code, _out, err = self.rundesk("providers", "instructions", "--turn", "1")
        self.assertEqual(FAILED, code)
        self.assertIn("--turn", err)

    def test_a_turn_that_is_not_there_fails_rather_than_composing_something(self):
        agent = self.an_agent()
        code, _out, err = self.rundesk("providers", "instructions", agent, "--turn", "9")
        self.assertEqual(FAILED, code)
        self.assertTrue(err.strip(), "a turn that is not there was refused in silence")

    def test_an_agent_that_is_not_there_fails_and_says_what_to_type(self):
        code, _out, err = self.rundesk("providers", "instructions", "nobody")
        self.assertEqual(FAILED, code)
        self.assertIn("rundesk agents", err)


class Running(Providers):
    """`providers run` — one scheduled turn, taken here. What a firing starts."""

    def a_schedule(self, agent, name="nightly", prompt="what happened overnight?", **also):
        schedules_kept.added(agent, name, dict({"cron": "* * * * *", "agent_prompt": prompt},
                                               **also))
        return name

    def test_it_takes_the_turn_and_says_what_became_of_it(self):
        agent = self.an_agent()
        self.a_schedule(agent)
        code, _out, err = self.rundesk("providers", "run", agent, "--schedule", "nightly")
        self.assertEqual(OK, code, err)
        there = kept.list_turns(agent)
        self.assertEqual(1, len(there))
        self.assertEqual("done", there[0]["turn_status"])

    def test_the_turn_it_took_is_tied_to_the_schedule_that_caused_it(self):
        agent = self.an_agent()
        self.a_schedule(agent)
        self.rundesk("providers", "run", agent, "--schedule", "nightly")
        turn = kept.list_turns(agent)[0]
        self.assertEqual(schedules_kept.one(agent, "nightly")["id"], turn["schedule_id"])

    def test_a_schedule_that_names_a_program_is_refused_and_says_what_to_type(self):
        agent = self.an_agent()
        self.a_schedule(agent, "build", prompt=None, command="/bin/echo hi")
        code, _out, err = self.rundesk("providers", "run", agent, "--schedule", "build")
        self.assertEqual(FAILED, code)
        self.assertIn("rundesk schedules run", err)

    def test_a_brain_that_could_not_answer_exits_non_zero(self):
        """The number a supervisor reads. A firing recorded as having worked when it did not is
        worse than one recorded as having failed."""
        agent = self.an_agent()
        self.a_stand_in_told(agent, fail_with="upstream_error")
        self.a_schedule(agent)
        code, _out, err = self.rundesk("providers", "run", agent, "--schedule", "nightly")
        self.assertEqual(FAILED, code)
        self.assertIn("upstream_error", err)

    def test_a_schedule_that_is_not_there_fails_rather_than_running_nothing_quietly(self):
        agent = self.an_agent()
        code, _out, err = self.rundesk("providers", "run", agent, "--schedule", "nowhere")
        self.assertEqual(FAILED, code)
        self.assertIn("nowhere", err)


if __name__ == "__main__":
    unittest.main()
