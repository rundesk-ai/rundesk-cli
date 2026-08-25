"""Handing one schedule's finished report to another agent: what is refused, what is written, and
what a second pass must not do twice.

Every case here works on real agents with real records, made the way the product makes one — so the
columns under test are the ones migration step `0014` laid down and not a fixture that agrees with
them.

**Most of the value is in the refusals and in the second pass.** Writing a report into a second
agent's records is easy; what this has to get right is refusing a target that cannot be one, never
delivering to a stranger who took a removed agent's name, and reading the same outbox twice without
the recipient hearing the same report twice.

Run directly: `python3 tests/test_schedules_delivering.py`
"""

import datetime
import unittest

import support
from rundesk.agents import directory, records
from rundesk.channels import arriving
from rundesk.channels import hosting as channels_hosting
from rundesk.delegations import kept as delegations_kept
from rundesk.providers import answering, instructions, turns
from rundesk.providers import kept as turns_kept
from rundesk.schedules import delivering
from rundesk.schedules import kept as schedules_kept

#: One finished run's own identity, as a scheduled invocation's conversation spells it.
A_RUN = "nightly/0f1e2d3c4b5a69788796a5b4c3d2e1f0"

#: The moment that run finished, in the shape the records keep moments in.
AT = "2026-08-24T06:00:00Z"


class Recording:
    """A `delivering.Handing` that writes nothing and remembers everything it was handed.

    The sweep's own decisions — which rows are ours, which mark moves, what a refusal leaves behind
    — are answerable with no brain, no adapter and no conversation store anywhere near them, and
    this is what keeps them that way. The real seam is `providers.answering.OnADelivery`, proved
    against real records further down.
    """

    def __init__(self, taking: bool = True):
        self.taking = taking
        self.given = []
        self.answered = []

    def recorded(self, agent, from_agent, from_identity, schedule, run_key, ran_at, report):
        self.given.append((agent, from_agent, from_identity, schedule, run_key, ran_at, report))
        return self.taking

    def answer_waiting(self, agent):
        self.answered.append(agent)


class TwoAgents(support.Isolated):
    """One agent with a schedule, and one it may be told to deliver to."""

    def setUp(self):
        super().setUp()
        self.source, self.target = "cole", "dana"
        directory.made(self.source, "claude")
        directory.made(self.target, "claude")

    def asking(self, name="nightly", **also):
        """One schedule that asks the agent, written through the store."""
        schedules_kept.added(self.source, name,
                             dict({"cron": "0 6 * * *", "prompt": "write the report"}, **also))
        return name

    def delivering_to(self, target=None, name="nightly"):
        """The same, pointed at the other agent the way a command points it."""
        named = target or self.target
        self.asking(name)
        schedules_kept.changed(self.source, name, {
            "deliver_to_agent": named, "deliver_to_identity": delivering.identity_of(named)})
        return name

    def finished_delivery(self, run=A_RUN, outcome=schedules_kept.DONE):
        """Freeze and settle the target the way a clock-fired invocation does."""
        row = schedules_kept.one(self.source, "nightly")
        delivering.started(
            self.source, "nightly", run, AT,
            row.get("deliver_to_agent"), row.get("deliver_to_identity"))
        delivering.finished(
            self.source, run, outcome,
            when=datetime.datetime(2026, 8, 24, 6, 0, tzinfo=datetime.timezone.utc))

    def logs(self, agent):
        return directory.logs(agent)

    def messages_of(self, agent):
        """Every conversation of one agent's, with the messages in it."""
        found = []
        for conversation in arriving.conversations(agent):
            for message in arriving.messages(agent, int(conversation["id"])):
                found.append((conversation, message))
        return found


class AnAgentHasAnIdentityOfItsOwn(TwoAgents):

    def test_every_agent_gets_one_when_it_is_made(self):
        self.assertTrue(delivering.identity_of(self.source))
        self.assertTrue(delivering.identity_of(self.target))

    def test_two_agents_are_never_the_same_one(self):
        self.assertNotEqual(delivering.identity_of(self.source),
                            delivering.identity_of(self.target))

    def test_it_does_not_change_when_anything_else_about_the_agent_does(self):
        was = delivering.identity_of(self.source)
        records.stated(directory.records(self.source), {"model_name": "something-else"})
        self.assertEqual(was, delivering.identity_of(self.source))

    def test_an_agent_re_made_under_the_same_name_is_not_the_same_agent(self):
        was = delivering.identity_of(self.target)
        directory.forgotten(self.target)
        directory.made(self.target, "claude")
        self.assertNotEqual(was, delivering.identity_of(self.target))

    def test_nothing_may_state_it(self):
        # The whole value of the column is that no later write reaches it. A caller that could set
        # one agent's identity to another's could point every stored reference at a stranger.
        with self.assertRaises(records.Refused):
            records.stated(directory.records(self.source), {"agent_identity": "somebody else"})


class WhatMayBeGivenATarget(TwoAgents):

    def test_a_schedule_that_asks_the_agent_keeps_the_name_and_who_that_was(self):
        self.delivering_to()
        row = schedules_kept.one(self.source, "nightly")
        self.assertEqual(self.target, row["deliver_to_agent"])
        self.assertEqual(delivering.identity_of(self.target), row["deliver_to_identity"])

    def test_a_schedule_that_starts_a_program_is_refused_by_the_records(self):
        schedules_kept.added(self.source, "backup",
                             {"cron": "0 2 * * *", "command": "/bin/echo hello"})
        with self.assertRaises(schedules_kept.Refused) as refused:
            schedules_kept.changed(self.source, "backup", {
                "deliver_to_agent": self.target,
                "deliver_to_identity": delivering.identity_of(self.target)})
        self.assertIn("no report to deliver", str(refused.exception))

    def test_one_that_carries_a_target_may_not_become_a_program(self):
        # The other direction of the same rule, and the one a person meets by editing rather than
        # by adding: a schedule delivering its report cannot be turned into one that has none.
        self.delivering_to()
        with self.assertRaises(schedules_kept.Refused):
            schedules_kept.changed(self.source, "nightly",
                                   {"prompt": None, "command": "/bin/echo hello"})

    def test_a_name_with_nobody_behind_it_is_refused_by_the_records(self):
        self.asking()
        with self.assertRaises(schedules_kept.Refused) as refused:
            schedules_kept.changed(self.source, "nightly", {"deliver_to_agent": self.target})
        self.assertIn("who that agent is", str(refused.exception))

    def test_who_it_was_with_no_name_is_refused_too(self):
        self.asking()
        with self.assertRaises(schedules_kept.Refused):
            schedules_kept.changed(self.source, "nightly", {"deliver_to_identity": "whoever"})

    def test_a_schedule_delivers_nowhere_until_somebody_says_so(self):
        self.asking()
        row = schedules_kept.one(self.source, "nightly")
        self.assertIsNone(row["deliver_to_agent"])
        self.assertIsNone(row["deliver_to_identity"])


class WhatTheCommandRefuses(TwoAgents):

    def test_an_asking_schedule_takes_a_target_and_reads_it_back(self):
        code, out, _err = self.rundesk("schedules", "add", self.source, "nightly",
                                       "--when", "0 6 * * *", "--ask", "write the report",
                                       "--deliver-to", self.target)
        self.assertEqual(0, code, out)
        self.assertIn(f"deliver   {self.target}", out)
        self.assertEqual(self.target,
                         schedules_kept.one(self.source, "nightly")["deliver_to_agent"])

    def test_a_program_schedule_is_refused_and_nothing_is_added(self):
        code, _out, err = self.rundesk("schedules", "add", self.source, "backup",
                                       "--when", "0 2 * * *", "--run", "/bin/echo hello",
                                       "--deliver-to", self.target)
        self.assertEqual(1, code)
        self.assertIn("no report to deliver", err)
        self.assertIn("nothing was added", err)
        self.assertEqual([], schedules_kept.all(self.source))

    def test_delivering_to_itself_is_refused(self):
        code, _out, err = self.rundesk("schedules", "add", self.source, "nightly",
                                       "--when", "0 6 * * *", "--ask", "write the report",
                                       "--deliver-to", self.source)
        self.assertEqual(1, code)
        self.assertIn("cannot deliver its own report to itself", err)
        self.assertEqual([], schedules_kept.all(self.source))

    def test_a_target_that_is_not_an_agent_is_refused(self):
        code, _out, err = self.rundesk("schedules", "add", self.source, "nightly",
                                       "--when", "0 6 * * *", "--ask", "write the report",
                                       "--deliver-to", "nobody")
        self.assertEqual(1, code)
        self.assertIn("nothing was added", err)
        self.assertEqual([], schedules_kept.all(self.source))

    def test_a_target_said_with_nothing_in_it_is_refused(self):
        code, _out, err = self.rundesk("schedules", "add", self.source, "nightly",
                                       "--when", "0 6 * * *", "--ask", "write the report",
                                       "--deliver-to", "  ")
        self.assertEqual(1, code)
        self.assertIn("nothing said which agent", err)
        self.assertEqual([], schedules_kept.all(self.source))

    def test_update_points_an_existing_schedule_at_an_agent(self):
        self.asking()
        code, out, _err = self.rundesk("schedules", "update", self.source, "nightly",
                                       "--deliver-to", self.target)
        self.assertEqual(0, code, out)
        self.assertEqual(self.target,
                         schedules_kept.one(self.source, "nightly")["deliver_to_agent"])

    def test_update_can_return_a_schedule_to_its_owner_notice(self):
        self.delivering_to()
        code, out, err = self.rundesk("schedules", "update", self.source, "nightly",
                                      "--no-deliver-to")
        self.assertEqual(0, code, err)
        self.assertIn("schedule nightly changed", out)
        row = schedules_kept.one(self.source, "nightly")
        self.assertIsNone(row["deliver_to_agent"])
        self.assertIsNone(row["deliver_to_identity"])

    def test_clearing_delivery_can_turn_the_schedule_into_a_program_in_one_change(self):
        self.delivering_to()
        code, _out, err = self.rundesk(
            "schedules", "update", self.source, "nightly",
            "--run", "/bin/echo hello", "--no-deliver-to")
        self.assertEqual(0, code, err)
        row = schedules_kept.one(self.source, "nightly")
        self.assertEqual("/bin/echo hello", row["command"])
        self.assertIsNone(row["deliver_to_agent"])

    def test_update_cannot_name_and_clear_a_target_at_once(self):
        self.asking()
        code, _out, err = self.rundesk(
            "schedules", "update", self.source, "nightly",
            "--deliver-to", self.target, "--no-deliver-to")
        self.assertEqual(2, code)
        self.assertIn("cannot name and clear", err)

    def test_show_says_when_the_agent_it_was_pointed_at_is_gone(self):
        # A stranger holding a removed agent's name must never read as the target. The readout says
        # so where somebody can see it, because nothing is delivered until it is said again.
        self.delivering_to()
        directory.forgotten(self.target)
        directory.made(self.target, "claude")
        code, out, _err = self.rundesk("schedules", "show", self.source, "nightly")
        self.assertEqual(0, code)
        self.assertIn("not the agent this was pointed at any more", out)


class WhatACompletedRunOwes(TwoAgents):

    def test_a_completed_run_writes_one_row_for_the_agent_it_names(self):
        self.delivering_to()
        self.finished_delivery()
        self.assertTrue(delivering.owed(self.source, "nightly", A_RUN, AT, "the whole report"))
        owing = delivering.owing(self.source)
        self.assertEqual(1, len(owing))
        self.assertEqual(self.target, owing[0].to_agent)
        self.assertEqual(delivering.identity_of(self.target), owing[0].to_identity)
        self.assertEqual(("nightly", A_RUN, AT, "the whole report"),
                         (owing[0].schedule_name, owing[0].run_key, owing[0].ran_at,
                          owing[0].report))

    def test_the_same_run_reported_twice_owes_one_report(self):
        # A gateway that adopted the firing, and one that reported it before going down, both write
        # this run's key. Exactly once is the row's `UNIQUE`, not anybody remembering.
        self.delivering_to()
        self.finished_delivery()
        delivering.owed(self.source, "nightly", A_RUN, AT, "the whole report")
        delivering.owed(self.source, "nightly", A_RUN, AT, "the whole report again")
        self.assertEqual(1, len(delivering.owing(self.source)))
        self.assertEqual("the whole report", delivering.owing(self.source)[0].report)

    def test_recovery_keeps_the_real_settlement_time_not_its_later_retry_time(self):
        self.delivering_to()
        self.finished_delivery()

        delivering.owed(
            self.source, "nightly", A_RUN, "2026-08-25T09:30:00Z", "the whole report")

        self.assertEqual(AT, delivering.owing(self.source)[0].ran_at)

    def test_two_runs_of_one_schedule_each_owe_their_own(self):
        self.delivering_to()
        self.finished_delivery()
        delivering.owed(self.source, "nightly", A_RUN, AT, "monday")
        self.finished_delivery(run="nightly/second")
        delivering.owed(self.source, "nightly", "nightly/second", AT, "tuesday")
        self.assertEqual(["monday", "tuesday"],
                         [one.report for one in delivering.owing(self.source)])

    def test_an_oversized_report_keeps_its_opening_and_conclusion(self):
        self.delivering_to()
        self.finished_delivery()
        report = "opening:" + ("x" * delivering.A_REPORT_AT_MOST) + ":conclusion"
        delivering.owed(self.source, "nightly", A_RUN, AT, report)
        carried = delivering.owing(self.source)[0].report
        self.assertLessEqual(len(carried), delivering.A_REPORT_AT_MOST)
        self.assertTrue(carried.startswith("opening:"))
        self.assertTrue(carried.endswith(":conclusion"))
        self.assertIn("middle omitted", carried)

    def test_a_schedule_that_names_nowhere_owes_nothing(self):
        self.asking()
        self.assertFalse(delivering.owed(self.source, "nightly", A_RUN, AT, "the whole report"))
        self.assertEqual([], delivering.owing(self.source))


class WhatAnInvocationFreezes(TwoAgents):

    def test_adding_a_target_while_it_runs_does_not_redirect_that_run(self):
        self.asking()
        self.assertFalse(delivering.started(
            self.source, "nightly", A_RUN, AT, None, None))
        schedules_kept.changed(self.source, "nightly", {
            "deliver_to_agent": self.target,
            "deliver_to_identity": delivering.identity_of(self.target),
        })
        delivering.finished(self.source, A_RUN, schedules_kept.DONE)
        self.assertFalse(delivering.owed(
            self.source, "nightly", A_RUN, AT, "the whole report"))

    def test_clearing_a_target_while_it_runs_keeps_that_run_s_target(self):
        self.delivering_to()
        self.finished_delivery()
        schedules_kept.changed(self.source, "nightly", {
            "deliver_to_agent": None, "deliver_to_identity": None,
        })
        self.assertTrue(delivering.owed(
            self.source, "nightly", A_RUN, AT, "the whole report"))
        self.assertEqual(self.target, delivering.owing(self.source)[0].to_agent)

    def test_changing_a_target_while_it_runs_does_not_redirect_that_run(self):
        directory.made("erin", "claude")
        self.delivering_to()
        self.finished_delivery()
        schedules_kept.changed(self.source, "nightly", {
            "deliver_to_agent": "erin",
            "deliver_to_identity": delivering.identity_of("erin"),
        })
        self.assertTrue(delivering.owed(
            self.source, "nightly", A_RUN, AT, "the whole report"))
        self.assertEqual(self.target, delivering.owing(self.source)[0].to_agent)

    def test_a_run_that_said_nothing_owes_nothing(self):
        self.delivering_to()
        self.finished_delivery()
        self.assertFalse(delivering.owed(self.source, "nightly", A_RUN, AT, "   "))
        self.assertEqual([], delivering.owing(self.source))

    def test_a_schedule_taken_away_while_its_run_finishes_keeps_the_frozen_delivery(self):
        self.delivering_to()
        self.finished_delivery()
        schedules_kept.forgotten(self.source, "nightly")
        self.assertTrue(delivering.owed(
            self.source, "nightly", A_RUN, AT, "the whole report"))

    def test_a_removed_target_leaves_the_report_for_the_source_notice(self):
        self.delivering_to()
        self.finished_delivery()
        directory.forgotten(self.target)
        directory.made(self.target, "claude")
        self.assertFalse(delivering.owed(
            self.source, "nightly", A_RUN, AT, "the whole report"))
        self.assertEqual([], delivering.owing(self.source))


class WhatTheRecipientReads(TwoAgents):

    def owed(self, report="the whole report", run=A_RUN):
        self.delivering_to()
        self.finished_delivery(run=run)
        delivering.owed(self.source, "nightly", run, AT, report)

    def test_it_reads_a_report_addressed_to_it_out_of_the_other_store(self):
        self.owed()
        handing = Recording()
        delivering.looked(self.target, self.logs(self.target), handing)
        self.assertEqual(1, len(handing.given))
        _agent, from_agent, from_identity, schedule, run_key, ran_at, report = handing.given[0]
        self.assertEqual((self.source, delivering.identity_of(self.source)),
                         (from_agent, from_identity))
        self.assertEqual(("nightly", A_RUN, AT, "the whole report"),
                         (schedule, run_key, ran_at, report))

    def test_a_second_pass_reads_the_same_report_no_second_time(self):
        self.owed()
        handing = Recording()
        delivering.looked(self.target, self.logs(self.target), handing)
        delivering.looked(self.target, self.logs(self.target), handing)
        self.assertEqual(1, len(handing.given))

    def test_the_source_keeps_durable_acknowledgement_after_the_recipient_admits_it(self):
        self.owed()
        delivering.looked(self.target, self.logs(self.target), Recording())

        delivering.acknowledged(self.source)

        self.assertFalse(delivering.has_unread_from(self.source))
        self.assertFalse(delivering.has_unread_for(self.target))

    def test_a_report_it_could_not_write_down_is_read_again_next_pass(self):
        # The mark moves only after the report is durably in this agent's own records. A recipient
        # whose store would not take it must find the row again rather than move past it.
        self.owed()
        refusing = Recording(taking=False)
        delivering.looked(self.target, self.logs(self.target), refusing)
        taking = Recording()
        delivering.looked(self.target, self.logs(self.target), taking)
        self.assertEqual(1, len(taking.given))

    def test_the_agent_that_owns_the_schedule_reads_nothing_of_its_own(self):
        self.owed()
        handing = Recording()
        delivering.looked(self.source, self.logs(self.source), handing)
        self.assertEqual([], handing.given)

    def test_a_stranger_holding_the_name_is_never_given_the_report(self):
        # The one failure this whole design exists to prevent: an agent removed and re-made under
        # the same name is somebody else, and last month's report must not reach it.
        self.owed()
        directory.forgotten(self.target)
        directory.made(self.target, "claude")
        handing = Recording()
        delivering.looked(self.target, self.logs(self.target), handing)
        self.assertEqual([], handing.given)

    def test_it_still_reads_the_next_report_after_passing_over_a_stranger_s(self):
        # Passing over a row that will never be ours must not stall the ones behind it.
        self.owed(report="for somebody else")
        stale = delivering.owing(self.source)[0]
        with records.writing(directory.records(self.source)) as conn:
            conn.execute("UPDATE schedule_deliveries SET to_identity = ? WHERE id = ?",
                         ("somebody else entirely", stale.id))
        self.finished_delivery(run="nightly/second")
        delivering.owed(self.source, "nightly", "nightly/second", AT, "for us")
        handing = Recording()
        delivering.looked(self.target, self.logs(self.target), handing)
        self.assertEqual(["for us"], [one[6] for one in handing.given])

    def test_a_report_written_while_nothing_was_running_is_still_read(self):
        # The recipient has no gateway at all when the run completes — which is the ordinary case
        # for an agent nobody keeps up — and the row is waiting whenever one next looks.
        self.owed()
        handing = Recording()
        delivering.looked(self.target, self.logs(self.target), handing)
        self.assertEqual(1, len(handing.given))

    def test_every_pass_asks_what_is_still_waiting_to_be_answered(self):
        self.owed()
        handing = Recording()
        delivering.looked(self.target, self.logs(self.target), handing)
        delivering.looked(self.target, self.logs(self.target), handing)
        self.assertEqual([self.target, self.target], handing.answered)

    def test_an_agent_whose_store_cannot_be_read_does_not_stop_the_others(self):
        self.owed()
        directory.records(self.source).write_bytes(b"not a database at all")
        handing = Recording()
        delivering.looked(self.target, self.logs(self.target), handing)
        self.assertEqual([], handing.given)
        self.assertEqual([self.target], handing.answered)


class WhatTheRecipientDoesWithIt(TwoAgents):
    """The seam filled: the report written into the recipient's own records, and the turn it owes."""

    class RecordingOnly(answering.OnADelivery):
        """Write the durable message without starting a provider thread this case does not test."""

        def answer_waiting(self, agent):
            pass

    def seam(self):
        return self.RecordingOnly(self.logs(self.target),
                                  lambda: channels_hosting.Watching({}, {}, {}))

    def delivered(self, report="the whole report", run=A_RUN):
        self.delivering_to()
        self.finished_delivery(run=run)
        delivering.owed(self.source, "nightly", run, AT, report)
        delivering.looked(self.target, self.logs(self.target), self.seam())

    def test_the_report_lands_in_the_recipient_s_own_records(self):
        self.delivered()
        found = self.messages_of(self.target)
        self.assertEqual(1, len(found))
        conversation, message = found[0]
        self.assertEqual(arriving.FROM_SCHEDULE, conversation["source"])
        self.assertEqual(
            arriving.delivery_stands_at(self.source, delivering.identity_of(self.source), A_RUN),
            conversation["source_id"])
        self.assertEqual(self.source, message["author_id"])

    def test_it_says_whose_run_it_was_and_carries_the_whole_report(self):
        self.delivered(report="everything that happened")
        _conversation, message = self.messages_of(self.target)[0]
        for said in (self.source, "nightly", A_RUN, AT, "everything that happened"):
            self.assertIn(said, message["body"])

    def test_the_same_report_recorded_again_is_one_message(self):
        # Whatever re-reads the row — a mark that never moved, an adoption, a restart — the
        # conversation and the message are both already there.
        self.delivered()
        with records.writing(directory.records(self.target)) as conn:
            conn.execute("DELETE FROM schedule_delivery_marks")
        delivering.looked(self.target, self.logs(self.target), self.seam())
        self.assertEqual(1, len(self.messages_of(self.target)))

    def test_it_waits_to_be_answered_until_a_turn_claims_it(self):
        self.delivered()
        conversation, message = self.messages_of(self.target)[0]
        waiting = arriving.pending_deliveries(self.target, 8)
        self.assertEqual([(int(conversation["id"]), int(message["id"]))],
                         [(one[0], one[1]) for one in waiting])
        turn = turns_kept.add_turn(self.target, {
            "conversation_id": int(conversation["id"]),
            "provider_name": "stand-in", "access_mode": "work"})
        arriving.handled_by_turn(self.target, int(conversation["id"]), (int(message["id"]),), turn)
        self.assertEqual([], arriving.pending_deliveries(self.target, 8))

    def test_no_delegation_is_written_at_either_end(self):
        # A report handed over is not work handed over. Nothing is owed back, so there is no row
        # for anything to collect an answer against.
        self.delivered()
        self.assertEqual([], delegations_kept.every(self.source))
        self.assertEqual([], delegations_kept.every(self.target))

    def test_the_recipient_s_final_can_never_be_handed_on_as_another_delivery(self):
        directory.made("erin", "claude")
        place = arriving.delivery_stands_at(
            self.source, delivering.identity_of(self.source), A_RUN)
        delivering.started(
            self.target, "foreign/nightly", place, AT,
            "erin", delivering.identity_of("erin"))
        delivering.finished(self.target, place, schedules_kept.DONE)
        seam = self.seam()

        self.assertFalse(seam._owed_onward(
            self.target, arriving.FROM_SCHEDULE, place,
            turns.Outcome(turn=1, turn_status=turns_kept.DONE, reply="recipient final")))
        self.assertEqual([], delivering.owing(self.target))

    def test_a_failed_review_releases_the_source_delivery_obligation(self):
        self.delivering_to()
        self.finished_delivery()
        seam = self.RecordingOnly(self.logs(self.source),
                                  lambda: channels_hosting.Watching({}, {}, {}))

        self.assertFalse(seam._owed_onward(
            self.source, arriving.FROM_SCHEDULE, A_RUN,
            turns.Outcome(turn=2, turn_status=turns_kept.FAILED, reply="review failed")))

        with records.reading(directory.records(self.source)) as conn:
            left = conn.execute("SELECT count(*) FROM schedule_delivery_obligations").fetchone()[0]
        self.assertEqual(0, left)


class TheTurnItStarts(TwoAgents):
    """What `answer_waiting` asks for, without a brain: the request a delivered report becomes."""

    class Watching(answering.OnADelivery):
        """The seam with its one outward call replaced, so what it would start can be read."""

        taken = None

        def _take(self, agent, conversation, body, **how):
            type(self).taken = dict(how, agent=agent, conversation=conversation, body=body)
            return True

    def setUp(self):
        super().setUp()
        type(self).Watching.taken = None

    def test_a_waiting_report_becomes_an_ordinary_unattended_turn(self):
        self.delivering_to()
        self.finished_delivery()
        delivering.owed(self.source, "nightly", A_RUN, AT, "the whole report")
        watching = self.Watching(self.logs(self.target),
                                 lambda: channels_hosting.Watching({}, {}, {}))
        delivering.looked(self.target, self.logs(self.target), watching)
        self.assertTrue(support.waited_until(
            lambda: self.Watching.taken is not None and not watching._starting, 5.0),
                        "no turn was started for a delivered report")
        taken = self.Watching.taken
        self.assertEqual(instructions.SCHEDULE_TO_AGENT, taken["situation"])
        # Named as its owner's schedule, because this agent may well have one called `nightly` and
        # a turn row saying it ran for that one is a row every surface would believe.
        self.assertEqual(f"{self.source}/nightly", taken["schedule_name"])
        self.assertIn("the whole report", taken["body"])
        # Nothing is being answered and nobody is owed a handback: this is not a delegation.
        self.assertIsNone(taken["answering"])
        self.assertIsNone(taken["caller_agent"])

    def test_nothing_waiting_starts_nothing(self):
        self.delivering_to()
        watching = self.Watching(self.logs(self.target),
                                 lambda: channels_hosting.Watching({}, {}, {}))
        delivering.looked(self.target, self.logs(self.target), watching)
        self.assertIsNone(self.Watching.taken)


if __name__ == "__main__":
    unittest.main()
