"""`rundesk schedules` — what a person types, and what a person is shown.

Driven through `self.rundesk(...)`, so the real parser and the real dispatch answer every case. A
case that called `cmd_schedules` directly would prove the module and not the command: the sub-verb it
registered, the flag it spelled, and the exit code the shell reads are exactly the parts a direct
call skips.

Every assertion is on what somebody sees or on the number a script reads. Nothing here looks at the
schedules layer's internals except to set a schedule up or to break one on purpose, because a test
that asserts on a private shape goes green while the sentence a person reads goes wrong.

Run directly: `python3 tests/test_schedules_command.py`
"""

import unittest

import support
from rundesk.agents import directory, records
from rundesk.exits import FAILED, OK, USAGE
from rundesk.schedules import firing, kept

#: A program that really is on this machine, and one that is not. Located when a schedule is added,
#: so both spellings have to be real ones.
THERE = "/bin/echo"
NOT_THERE = "/no/such/program"


#: The provider these agents are recorded against. **A name nothing stands behind, and it has to
#: stay one.** This file used to say `claude`, which was a name for nothing right up until an adapter
#: of that name shipped — and then the one case here that really runs a turn stopped being refused,
#: started a real brain, reached a real account and took fifty-one seconds to fail differently. A
#: placeholder that names a thing somebody might one day build is a placeholder with an expiry date
#: on it, so this one says what it is for.
NO_SUCH_BRAIN = "no-brain-stands-behind-this"


class Scheduling(support.Isolated):
    """An install with one real agent in it."""

    def setUp(self):
        super().setUp()
        self.agent = "cole"
        directory.made(self.agent, NO_SUCH_BRAIN)

    def given(self, name="nightly", *more):
        """One schedule, added the way a person adds one."""
        code, _out, err = self.rundesk("schedules", "add", self.agent, name,
                                      "--when", "0 2 * * *", "--run", f"{THERE} hello", *more)
        self.assertEqual(OK, code, err)
        return name

    def row(self, name="nightly"):
        return kept.one(self.agent, name)


class Listing(Scheduling):
    """`rundesk schedules`, and the same thing narrowed to one agent."""

    def test_an_install_with_nothing_scheduled_says_so_and_says_what_to_type(self):
        # `as_table` prints nothing at all when there are no rows, headings included — so a listing
        # that leant on it would print the directory and stop, and "nothing scheduled" would be
        # something the reader had to infer from silence.
        code, out, _ = self.rundesk("schedules")
        self.assertEqual(OK, code)
        self.assertIn("nothing is scheduled yet", out)
        self.assertIn("rundesk schedules add", out)

    def test_where_they_are_kept_is_printed_even_when_there_are_none(self):
        # "nothing scheduled" and "nothing scheduled *here*" are different things to learn, and
        # somebody looking at the wrong root needs to see which directory was just found empty.
        _code, out, _ = self.rundesk("schedules")
        self.assertIn(str(self.home), out)

    def test_a_bare_schedules_lists_every_agents_with_the_agent_named(self):
        directory.made("alan", NO_SUCH_BRAIN)
        self.given("nightly")
        self.rundesk("schedules", "add", "alan", "morning",
                     "--when", "0 9 * * *", "--run", THERE)
        code, out, _ = self.rundesk("schedules")
        self.assertEqual(OK, code)
        self.assertIn("AGENT", out)
        self.assertIn("cole", out)
        self.assertIn("alan", out)

    def test_listing_one_agent_shows_that_agents_and_no_other(self):
        directory.made("alan", NO_SUCH_BRAIN)
        self.given("nightly")
        self.rundesk("schedules", "add", "alan", "morning",
                     "--when", "0 9 * * *", "--run", THERE)
        code, out, _ = self.rundesk("schedules", "list", self.agent)
        self.assertEqual(OK, code)
        self.assertIn("nightly", out)
        self.assertNotIn("morning", out)

    def test_a_listing_says_when_each_next_runs_and_what_it_last_did(self):
        self.given()
        _code, out, _ = self.rundesk("schedules", "list", self.agent)
        self.assertIn("SCHEDULE", out)
        self.assertIn("NEXT", out)
        self.assertIn("never ran", out)

    def test_a_schedule_that_is_off_says_off_rather_than_a_time(self):
        self.given("nightly", "--disabled")
        _code, out, _ = self.rundesk("schedules", "list", self.agent)
        self.assertIn("off", out)

    def test_a_schedule_nobody_can_understand_is_still_listed_and_says_why(self):
        # It is on the disk and it is something to be done about. A listing that left it out would
        # say it is not there, which is a different and worse thing to be told.
        self.given()
        with records.writing(directory.records(self.agent)) as conn:
            conn.execute("UPDATE schedules SET cron = 'not a cron' WHERE name = 'nightly'")
        code, out, _ = self.rundesk("schedules", "list", self.agent)
        self.assertEqual(OK, code)
        self.assertIn("nightly", out)
        self.assertIn("cannot be read", out)

    def test_an_agent_whose_schedules_cannot_be_read_says_so_rather_than_showing_none(self):
        self.given()
        directory.records(self.agent).write_bytes(b"this is not a database")
        code, out, _ = self.rundesk("schedules")
        self.assertEqual(OK, code)
        self.assertIn("cannot be read", out)

    def test_listing_an_agent_that_is_not_there_says_so(self):
        code, _out, err = self.rundesk("schedules", "list", "nobody")
        self.assertEqual(FAILED, code)
        self.assertIn("nobody is not an agent on this install", err)
        self.assertIn("nothing was listed", err)


class Adding(Scheduling):

    def test_a_schedule_is_added_and_says_everything_it_was_given(self):
        code, out, err = self.rundesk("schedules", "add", self.agent, "nightly",
                                      "--when", "0 2 * * *", "--run", f"{THERE} hello")
        self.assertEqual(OK, code, err)
        self.assertIn("schedule nightly added for cole", out)
        self.assertIn("0 2 * * *", out)
        self.assertIn(f"{THERE} hello", out)
        self.assertIn("next", out)

    def test_a_schedule_can_state_one_moment_instead(self):
        code, _out, err = self.rundesk("schedules", "add", self.agent, "once",
                                      "--at", "2099-01-01T09:00", "--run", THERE)
        self.assertEqual(OK, code, err)
        self.assertEqual("2099-01-01T09:00", self.row("once")["run_at"])
        self.assertIsNone(self.row("once")["cron"])

    def test_a_schedule_can_be_given_a_moment_it_is_finished(self):
        self.given("nightly", "--until", "2099-01-01T00:00")
        self.assertEqual("2099-01-01T00:00", self.row()["expire_at"])

    def test_a_schedule_can_be_added_switched_off(self):
        self.given("nightly", "--disabled")
        self.assertEqual(0, self.row()["enabled"])

    def test_saying_nothing_about_when_is_refused_with_the_command_to_type(self):
        # Refused by the verb at exit 1, not by argparse at exit 2: argparse names a flag and does
        # not say what to type.
        code, _out, err = self.rundesk("schedules", "add", self.agent, "nightly", "--run", THERE)
        self.assertEqual(FAILED, code)
        self.assertIn("nothing said when it runs", err)
        self.assertIn("rundesk schedules add cole nightly --when", err)
        self.assertIn("nothing was added", err)

    def test_saying_when_two_ways_is_refused(self):
        code, _out, err = self.rundesk("schedules", "add", self.agent, "nightly",
                                       "--when", "0 2 * * *", "--at", "2099-01-01T09:00",
                                       "--run", THERE)
        self.assertEqual(FAILED, code)
        self.assertIn("runs over and over or runs once", err)

    def test_saying_nothing_to_run_is_refused_with_the_command_to_type(self):
        code, _out, err = self.rundesk("schedules", "add", self.agent, "nightly",
                                       "--when", "0 2 * * *")
        self.assertEqual(FAILED, code)
        self.assertIn("nothing said what it does", err)
        self.assertIn("--run", err)

    def test_a_program_with_nothing_in_it_is_a_different_mistake_from_none_at_all(self):
        # Usually a shell variable that was not set, which is exactly the case where being told what
        # to type again does not help.
        code, _out, err = self.rundesk("schedules", "add", self.agent, "nightly",
                                       "--when", "0 2 * * *", "--run", "   ")
        self.assertEqual(FAILED, code)
        self.assertIn("a program with nothing in it is not one", err)

    def test_a_program_that_is_not_on_this_machine_is_refused_where_it_is_typed(self):
        # **The whole reason the program is located at add time.** Found instead by a gateway, this
        # is a line in a log at two in the morning saying a schedule nobody was watching did not run.
        code, _out, err = self.rundesk("schedules", "add", self.agent, "nightly",
                                       "--when", "0 2 * * *", "--run", NOT_THERE)
        self.assertEqual(FAILED, code)
        self.assertIn("is not a program on this machine", err)
        self.assertIn("nothing was added", err)

    def test_a_program_named_by_a_bare_name_on_the_path_is_accepted(self):
        code, _out, err = self.rundesk("schedules", "add", self.agent, "nightly",
                                       "--when", "0 2 * * *", "--run", "echo hello")
        self.assertEqual(OK, code, err)

    def test_a_cron_nobody_can_understand_is_refused_where_it_is_typed(self):
        code, _out, err = self.rundesk("schedules", "add", self.agent, "nightly",
                                       "--when", "60 * * * *", "--run", THERE)
        self.assertEqual(FAILED, code)
        self.assertIn("minute is 0 to 59", err)
        self.assertEqual([], kept.all(self.agent))

    def test_a_moment_carrying_a_time_zone_is_refused_rather_than_converted(self):
        code, _out, err = self.rundesk("schedules", "add", self.agent, "once",
                                       "--at", "2099-01-01T09:00Z", "--run", THERE)
        self.assertEqual(FAILED, code)
        self.assertIn("time zone", err)

    def test_a_name_that_is_already_a_schedules_is_refused_rather_than_replacing_it(self):
        self.given("nightly")
        code, _out, err = self.rundesk("schedules", "add", self.agent, "nightly",
                                       "--when", "0 9 * * *", "--run", THERE)
        self.assertEqual(FAILED, code)
        self.assertIn("already has a schedule", err)
        self.assertEqual("0 2 * * *", self.row()["cron"])

    def test_adding_to_an_agent_that_is_not_there_says_so(self):
        code, _out, err = self.rundesk("schedules", "add", "nobody", "nightly",
                                       "--when", "0 2 * * *", "--run", THERE)
        self.assertEqual(FAILED, code)
        self.assertIn("nobody is not an agent", err)
        self.assertIn("nothing was added", err)


class Updating(Scheduling):

    def test_a_schedule_is_changed_and_says_what_it_now_is(self):
        self.given()
        code, out, err = self.rundesk("schedules", "update", self.agent, "nightly",
                                      "--when", "0 3 * * *")
        self.assertEqual(OK, code, err)
        self.assertIn("schedule nightly changed", out)
        self.assertIn("0 3 * * *", out)

    def test_only_what_is_named_moves(self):
        self.given()
        self.rundesk("schedules", "update", self.agent, "nightly", "--when", "0 3 * * *")
        self.assertEqual(f"{THERE} hello", self.row()["command"])

    def test_a_repeating_time_and_a_single_moment_replace_each_other(self):
        self.given()
        self.rundesk("schedules", "update", self.agent, "nightly", "--at", "2099-01-01T09:00")
        self.assertIsNone(self.row()["cron"])
        self.assertEqual("2099-01-01T09:00", self.row()["run_at"])

    def test_naming_nothing_to_change_is_refused_rather_than_reported_as_done(self):
        # A command that reports success having changed nothing teaches somebody it worked, and the
        # next thing they do rests on a change that never happened.
        #
        # **The command to type is what this asserts on**, and that is not decoration: the store
        # refuses an empty change too, in words close enough that a case checking only the refusal
        # went green with the verb's own guard deleted. What the store cannot know is what somebody
        # should have typed instead, so that sentence is the one thing only this layer can produce.
        self.given()
        code, _out, err = self.rundesk("schedules", "update", self.agent, "nightly")
        self.assertEqual(FAILED, code)
        self.assertIn("nothing was named to change about nightly", err)
        self.assertIn("rundesk schedules update cole nightly --when", err)
        self.assertIn("nothing was changed", err)

    def test_a_schedule_is_turned_off_and_on_again_without_being_lost(self):
        self.given()
        self.rundesk("schedules", "update", self.agent, "nightly", "--disable")
        self.assertEqual(0, self.row()["enabled"])
        self.rundesk("schedules", "update", self.agent, "nightly", "--enable")
        self.assertEqual(1, self.row()["enabled"])

    def test_enabling_and_disabling_at_once_is_the_command_line_being_wrong(self):
        self.given()
        code, _out, err = self.rundesk("schedules", "update", self.agent, "nightly",
                                       "--enable", "--disable")
        self.assertEqual(USAGE, code)
        self.assertIn("cannot be enabled and disabled at once", err)

    def test_a_change_to_a_schedule_that_is_not_there_says_so_and_alters_nothing(self):
        self.given()
        code, _out, err = self.rundesk("schedules", "update", self.agent, "missing",
                                       "--when", "0 3 * * *")
        self.assertEqual(FAILED, code)
        self.assertIn("has no schedule called missing", err)
        self.assertIn("nothing was changed", err)

    def test_a_change_that_would_leave_a_schedule_nobody_can_act_on_is_refused(self):
        self.given()
        code, _out, err = self.rundesk("schedules", "update", self.agent, "nightly",
                                       "--when", "60 * * * *")
        self.assertEqual(FAILED, code)
        self.assertIn("minute is 0 to 59", err)
        self.assertEqual("0 2 * * *", self.row()["cron"])

    def test_a_program_that_is_not_on_this_machine_is_refused_by_a_change_too(self):
        self.given()
        code, _out, err = self.rundesk("schedules", "update", self.agent, "nightly",
                                       "--run", NOT_THERE)
        self.assertEqual(FAILED, code)
        self.assertIn("is not a program on this machine", err)
        self.assertEqual(f"{THERE} hello", self.row()["command"])

    def test_a_change_keeps_every_record_of_what_the_schedule_has_already_done(self):
        self.given()
        kept.claimed(self.agent, "nightly", "2026-08-05 02:00")
        kept.became(self.agent, "nightly", kept.DONE)
        self.rundesk("schedules", "update", self.agent, "nightly", "--when", "0 3 * * *")
        self.assertEqual("2026-08-05 02:00", self.row()["last_fired_for"])
        self.assertEqual(kept.DONE, self.row()["last_outcome"])


class Showing(Scheduling):

    def test_one_schedule_reads_back_everything_it_was_given(self):
        self.given("nightly", "--until", "2099-01-01T00:00")
        code, out, err = self.rundesk("schedules", "show", self.agent, "nightly")
        self.assertEqual(OK, code, err)
        for said in ("0 2 * * *", f"{THERE} hello", "2099-01-01T00:00", "yes"):
            self.assertIn(said, out)

    def test_what_a_schedule_was_not_given_reads_as_not_yet_rather_than_as_blank(self):
        self.given()
        _code, out, _ = self.rundesk("schedules", "show", self.agent, "nightly")
        self.assertIn("not yet", out)

    def test_showing_a_schedule_changes_nothing(self):
        self.given()
        before = self.row()
        self.rundesk("schedules", "show", self.agent, "nightly")
        self.assertEqual(dict(before), dict(self.row()))

    def test_a_schedule_that_is_not_there_is_said_rather_than_shown_as_empty(self):
        code, _out, err = self.rundesk("schedules", "show", self.agent, "missing")
        self.assertEqual(FAILED, code)
        self.assertIn("has no schedule called missing", err)

    def test_a_schedule_nobody_can_understand_is_still_shown(self):
        self.given()
        with records.writing(directory.records(self.agent)) as conn:
            conn.execute("UPDATE schedules SET cron = 'not a cron' WHERE name = 'nightly'")
        code, out, _ = self.rundesk("schedules", "show", self.agent, "nightly")
        self.assertEqual(OK, code)
        self.assertIn("not a cron", out)
        self.assertIn("cannot be worked out", out)

    def test_it_says_where_to_look_for_what_the_work_wrote(self):
        # The two files somebody investigating actually opens.
        self.given()
        _code, out, _ = self.rundesk("schedules", "show", self.agent, "nightly")
        self.assertIn("logs", out)
        self.assertIn("nightly.out", out)


class RunningOneByHand(Scheduling):

    def test_it_runs_and_prints_what_the_program_wrote(self):
        self.rundesk("schedules", "add", self.agent, "hello",
                     "--when", "0 2 * * *", "--run", f"{THERE} what it said")
        code, out, err = self.rundesk("schedules", "run", self.agent, "hello")
        self.assertEqual(OK, code, err)
        self.assertIn("what it said", out)
        self.assertIn("schedule hello completed", out)

    def test_a_program_that_disagreed_ends_non_zero_and_says_its_exit_code(self):
        self.rundesk("schedules", "add", self.agent, "bad",
                     "--when", "0 2 * * *", "--run", "/bin/sh -c 'exit 3'")
        code, _out, err = self.rundesk("schedules", "run", self.agent, "bad")
        self.assertEqual(FAILED, code)
        self.assertIn("ended with exit 3", err)

    def test_running_by_hand_leaves_the_minute_it_next_falls_due_alone(self):
        # Testing a schedule must not be how you stop it from happening.
        self.given()
        self.rundesk("schedules", "run", self.agent, "nightly")
        self.assertIsNone(self.row()["last_fired_for"])

    def test_running_by_hand_writes_down_what_became_of_it_because_it_did_run(self):
        self.given()
        self.rundesk("schedules", "run", self.agent, "nightly")
        self.assertEqual(kept.DONE, self.row()["last_outcome"])

    def test_a_schedule_that_is_not_there_says_so(self):
        code, _out, err = self.rundesk("schedules", "run", self.agent, "missing")
        self.assertEqual(FAILED, code)
        self.assertIn("has no schedule called missing", err)
        self.assertIn("nothing was run", err)

    def test_a_schedule_that_is_off_can_still_be_run_by_hand(self):
        # Switching one off says the clock must not start it. A person asking for it by name is not
        # the clock, and refusing would leave no way to test a schedule before turning it on.
        self.given("nightly", "--disabled")
        code, _out, err = self.rundesk("schedules", "run", self.agent, "nightly")
        self.assertEqual(OK, code, err)

    def test_a_ceiling_of_no_time_at_all_is_the_command_line_being_wrong(self):
        self.given()
        code, _out, err = self.rundesk("schedules", "run", self.agent, "nightly", "--wait", "0")
        self.assertEqual(USAGE, code)
        self.assertIn("not long enough", err)

    def test_a_program_that_would_not_finish_is_not_reported_as_one_that_failed(self):
        # There is no exit code, because nothing finished — and reporting one would say the program
        # ran and disagreed, which is a different fact about the machine.
        self.rundesk("schedules", "add", self.agent, "slow",
                     "--when", "0 2 * * *", "--run", "/bin/sh -c 'sleep 30'")
        code, _out, err = self.rundesk("schedules", "run", self.agent, "slow", "--wait", "0.5")
        self.assertEqual(FAILED, code)
        self.assertIn("did not run", err)
        self.assertNotIn("exit", err)

    def test_running_for_an_agent_that_is_not_there_says_so(self):
        code, _out, err = self.rundesk("schedules", "run", "nobody", "nightly")
        self.assertEqual(FAILED, code)
        self.assertIn("nobody is not an agent", err)


class Removing(Scheduling):

    def test_a_schedule_is_taken_away(self):
        self.given()
        code, out, err = self.rundesk("schedules", "remove", self.agent, "nightly")
        self.assertEqual(OK, code, err)
        self.assertIn("schedule nightly removed from cole", out)
        self.assertEqual([], kept.all(self.agent))

    def test_a_schedule_that_has_run_can_still_be_taken_away(self):
        self.given()
        self.rundesk("schedules", "run", self.agent, "nightly")
        code, _out, err = self.rundesk("schedules", "remove", self.agent, "nightly")
        self.assertEqual(OK, code, err)

    def test_a_removal_names_what_its_firings_left_behind_and_takes_it(self):
        # A schedule that is gone leaving a lock and an output file is litter the next schedule of
        # that name would inherit — and `agents remove` already sets the shape: name each thing.
        self.given()
        self.rundesk("schedules", "run", self.agent, "nightly")
        self.assertTrue(firing.output_of(self.agent, "nightly").exists())
        code, out, err = self.rundesk("schedules", "remove", self.agent, "nightly")
        self.assertEqual(OK, code, err)
        self.assertIn("nightly.out", out)
        self.assertFalse(firing.output_of(self.agent, "nightly").exists())
        self.assertFalse(firing.lock_of(self.agent, "nightly").exists())

    def test_a_removal_that_did_not_happen_is_a_failure(self):
        code, _out, err = self.rundesk("schedules", "remove", self.agent, "missing")
        self.assertEqual(FAILED, code)
        self.assertIn("has no schedule called missing", err)
        self.assertIn("nothing was removed", err)

    def test_taking_one_away_leaves_the_others(self):
        self.given("one")
        self.given("two")
        self.rundesk("schedules", "remove", self.agent, "one")
        self.assertEqual(["two"], [row["name"] for row in kept.all(self.agent)])


class AScheduleThatAsksTheAgent(Scheduling):
    """The kind the records always held, now that something can run one.

    `AGENTS.md`: a verb rundesk cannot perform is a verb rundesk does not have — so `--ask` was off
    the parser for as long as nothing could honour it, and it is on now because something can.
    """

    def test_it_can_be_spelled(self):
        code, out, _err = self.rundesk("schedules", "add", self.agent, "review",
                                       "--when", "0 9 * * *", "--ask", "what changed?")
        self.assertEqual(OK, code)
        self.assertIn("review", out)

    def test_it_starts_a_program_or_asks_the_agent_and_never_both(self):
        code, _out, err = self.rundesk("schedules", "add", self.agent, "review",
                                       "--when", "0 9 * * *", "--ask", "what changed?",
                                       "--run", "/bin/echo hello")
        self.assertEqual(FAILED, code)
        self.assertIn("never both", err)

    def test_one_that_does_neither_is_refused_with_both_ways_to_type_it(self):
        code, _out, err = self.rundesk("schedules", "add", self.agent, "review",
                                       "--when", "0 9 * * *")
        self.assertEqual(FAILED, code)
        self.assertIn("--ask", err)
        self.assertIn("--run", err)

    def test_the_two_the_records_hold_and_nothing_yet_sets_stay_off_the_parser(self):
        """`provider_name` and `model_name` are columns nothing writes: a schedule runs on the
        agent's own brain, and a way to override it per schedule is a verb nobody has asked for."""
        for flag in ("--provider", "--model"):
            with self.subTest(flag=flag):
                code, _out, err = self.rundesk("schedules", "add", self.agent, "review",
                                               "--when", "0 9 * * *", "--ask", "x", flag, "y")
                self.assertEqual(USAGE, code, f"{flag} is on the parser and nothing honours it")
                self.assertIn("unrecognized arguments", err)

    def test_one_written_straight_into_the_records_is_still_listed_and_shown(self):
        # The store holds the kind, so a listing has to be able to read one — and it has to say the
        # honest thing about it rather than crash on a row it did not expect.
        kept.added(self.agent, "review", {"cron": "0 9 * * *", "prompt": "review the queue"})
        code, out, _ = self.rundesk("schedules", "list", self.agent)
        self.assertEqual(OK, code)
        self.assertIn("review", out)
        code, out, _ = self.rundesk("schedules", "show", self.agent, "review")
        self.assertEqual(OK, code)

    def test_running_one_by_hand_takes_the_turn_rather_than_refusing(self):
        """**One verb for both kinds.** A schedule starts a program or asks the agent, and somebody
        checking their own work should not have to know which they wrote.

        The agent here has a provider nothing stands behind, so the turn cannot start — which is the
        point: it is refused for a reason about *this agent's brain*, and no longer for the reason
        that rundesk has no providers at all.
        """
        kept.added(self.agent, "review", {"cron": "0 9 * * *", "prompt": "review the queue"})
        code, _out, err = self.rundesk("schedules", "run", self.agent, "review")
        self.assertEqual(FAILED, code)
        self.assertNotIn("nothing in this release runs a provider", err)
        self.assertIn("nothing was run", err)


class WhatTheExitCodeSays(Scheduling):
    """`0` it was done, `1` understood and could not be, `2` never a command."""

    def test_a_listing_exits_zero_for_whatever_it_found(self):
        self.assertEqual(OK, self.rundesk("schedules")[0])
        self.given()
        self.assertEqual(OK, self.rundesk("schedules", "list", self.agent)[0])

    def test_a_sub_verb_that_is_not_one_is_never_a_command(self):
        self.assertEqual(USAGE, self.rundesk("schedules", "frobnicate")[0])

    def test_a_missing_positional_is_argparses_own_refusal(self):
        self.assertEqual(USAGE, self.rundesk("schedules", "add")[0])

    def test_the_root_being_refused_is_said_before_anything_else(self):
        # `RUNDESK_HOME` set and empty is not the same answer as unset, and a verb that read on
        # regardless would be working against a directory nobody chose.
        import os
        os.environ["RUNDESK_HOME"] = ""
        code, _out, err = self.rundesk("schedules")
        self.assertEqual(FAILED, code)
        self.assertIn("schedules: FAILED", err)


if __name__ == "__main__":
    unittest.main()
