"""The gateway process — run for real, because the guarantee is about what a process does.

Every case here starts an actual child in a scratch root and reads its actual exit code. Nothing
that stands in for a process can be `SIGKILL`ed, and nothing that stands in for an interpreter can
prove the one thing that matters most here: **that a gateway refusing to run exits `0`.** Under
`KeepAlive {"SuccessfulExit": false}` a non-zero exit is a request to be restarted, so a refusal
that exited `1` would turn a permanent condition into an endless loop that escalates into launchd's
exponential throttling and simply looks like a hang.

Every signal goes to a pid this suite started itself. Never a process group, never `0` and never
`1` — the build this replaces recorded `killpg` at group `0` taking out the test run and the shell
around it.

Waits are bounded and asked for rather than slept through: `support.waited_until`.

Run directly: `python3 tests/test_gateway_host.py`
"""

import contextlib
import datetime
import json
import os
import shutil
import signal
import sqlite3
import time
import unittest
from pathlib import Path
from typing import List, Optional
from unittest import mock

from fixtures_gateways import WithAnAgent

import support
from rundesk import __version__
from rundesk.agents import directory, records
from rundesk.channels import arriving, hosting
from rundesk.channels import files as arrivals
from rundesk.channels import kept as channels
from rundesk.core import paths
from rundesk.delegations import kept as delegations_kept
from rundesk.exits import OK
from rundesk.gateways import delegation_query, host, job, standing
from rundesk.providers import kept as turns_kept
from rundesk.providers import protocol
from rundesk.schedules import firing, kept
from rundesk.skills import catalogs, grants, library
from rundesk.utils import locking, logs, programs


class AConversationScopedDelegationQuery(support.Isolated):
    """The cross-store read model behind a private channel query."""

    def setUp(self):
        super().setUp()
        directory.made("ava", support.A_STAND_IN)
        directory.made("bob", support.A_STAND_IN)
        self.parent = arriving.recorded(
            "ava", "discord", "1180", "2207", "coordinate the release", external_id="m-1",
            when=datetime.datetime(2026, 8, 10, 12, 0, tzinfo=datetime.timezone.utc))
        self.turn = self.a_turn(
            "ava", self.parent.conversation, "done", "2026-08-10T12:00:01Z")

    @staticmethod
    def a_turn(agent, conversation, state, created, resumed=0, ended=None):
        turn = turns_kept.add_turn(agent, {
            "conversation_id": conversation, "provider_name": support.A_STAND_IN,
            "access_mode": "work", "session_resumed": resumed,
        }, when=datetime.datetime.fromisoformat(created.replace("Z", "+00:00")))
        if state != "working":
            turns_kept.finish_turn(
                agent, turn, state, when=datetime.datetime.fromisoformat(
                    (ended or created).replace("Z", "+00:00")))
        return turn

    def handed_over(self, delegation_id="del-1-aabbcc", task=None, conversation=None,
                    turn=None, target="bob"):
        parent_conversation = conversation or self.parent.conversation
        parent_turn = turn or self.turn
        task = task or "Audit the exporter\nPRIVATE PROMPT BODY MUST NOT APPEAR"
        arriving.recorded_for_a_delegation(
            target, "ava", parent_turn, task, delegation_id=delegation_id,
            when=datetime.datetime(2026, 8, 10, 12, 0, 2, tzinfo=datetime.timezone.utc))
        delegations_kept.made(
            "ava", delegation_id, target, parent_conversation, parent_turn,
            now=datetime.datetime(2026, 8, 10, 12, 0, 2, tzinfo=datetime.timezone.utc))
        return delegation_id

    def summary(self):
        return delegation_query.summary(
            "ava", "discord", "1180",
            now=datetime.datetime(2026, 8, 10, 12, 5, tzinfo=datetime.timezone.utc))

    def test_active_named_work_survives_a_replaced_origin_session_and_is_scoped_once(self):
        wanted = self.handed_over()
        other = arriving.recorded(
            "ava", "discord", "9900", "2207", "unrelated", external_id="m-2")
        other_turn = self.a_turn("ava", other.conversation, "done", "2026-08-10T12:01:00Z")
        self.handed_over("del-other-ffffff", "Unrelated private task", other.conversation,
                         other_turn)
        current = self.a_turn(
            "ava", self.parent.conversation, "working", "2026-08-10T12:02:00Z")

        before = (delegations_kept.one("ava", wanted),
                  tuple(turns_kept.turns_in_conversation("ava", self.parent.conversation)))
        with mock.patch.object(records, "writing", side_effect=AssertionError("query wrote state")):
            said = self.summary()

        self.assertEqual(1, said.count(wanted))
        self.assertIn("named-agent", said)
        self.assertIn("target: bob", said)
        self.assertIn("task: Audit the exporter", said)
        self.assertIn("state: active", said)
        self.assertIn(f"origin: conversation {self.parent.conversation}, turn {self.turn}", said)
        self.assertIn(f"delivery: discord:1180, turn {current}", said)
        self.assertIn("session reset/replaced", said)
        self.assertIn("4m elapsed", said)
        self.assertNotIn("PRIVATE PROMPT BODY", said)
        self.assertNotIn("del-other-ffffff", said)
        self.assertNotIn("Unrelated private task", said)
        self.assertEqual(before, (delegations_kept.one("ava", wanted),
                                  tuple(turns_kept.turns_in_conversation(
                                      "ava", self.parent.conversation))))

    def test_returned_work_is_awaiting_review_then_reviewed_and_later_becomes_stale(self):
        wanted = self.handed_over()
        result = arriving.said_by_rundesk_into(
            "ava", self.parent.conversation, "FULL RESULT MUST NOT APPEAR",
            external_id=f"delegation-result:{wanted}:answer-9",
            when=datetime.datetime(2026, 8, 10, 12, 3, tzinfo=datetime.timezone.utc))
        review = self.a_turn(
            "ava", self.parent.conversation, "working", "2026-08-10T12:03:01Z")
        arriving.handled_by_turn("ava", self.parent.conversation, (result.message,), review)
        delegations_kept.answered(
            "ava", wanted, now=datetime.datetime(2026, 8, 10, 12, 3, tzinfo=datetime.timezone.utc))

        self.assertIn("state: returned — awaiting review", self.summary())
        self.assertNotIn("FULL RESULT", self.summary())

        turns_kept.finish_turn(
            "ava", review, turns_kept.DONE,
            when=datetime.datetime(2026, 8, 10, 12, 4, tzinfo=datetime.timezone.utc))
        self.assertIn("state: reviewed", self.summary())

        self.a_turn("ava", self.parent.conversation, "done", "2026-08-10T12:04:30Z")
        self.assertNotIn(wanted, self.summary())

    def test_stopping_and_provider_local_work_are_distinct_without_claiming_full_visibility(self):
        wanted = self.handed_over()
        delegations_kept.stop_asked(
            "ava", wanted, now=datetime.datetime(2026, 8, 10, 12, 1, tzinfo=datetime.timezone.utc))
        current = self.a_turn(
            "ava", self.parent.conversation, "working", "2026-08-10T12:02:00Z")
        turns_kept.add_turn_record(
            "ava", current, "tool",
            {"type": "tool", "id": "provider-internal-id", "did": "delegate",
             "name": "INTERNAL TOOL NAME", "who": "/secret/provider/helper/path"},
            when=datetime.datetime(2026, 8, 10, 12, 2, 5, tzinfo=datetime.timezone.utc))

        said = self.summary()

        self.assertIn("state: stopping", said)
        self.assertIn("provider-local", said)
        self.assertIn("state: active", said)
        self.assertIn("visibility is partial", said)
        self.assertNotIn("provider-internal-id", said)
        self.assertNotIn("INTERNAL TOOL NAME", said)
        self.assertNotIn("/secret/", said)

        turns_kept.add_turn_record(
            "ava", current, "result", {"type": "result", "id": "provider-internal-id",
                                        "ok": True},
            when=datetime.datetime(2026, 8, 10, 12, 3, tzinfo=datetime.timezone.utc))
        returned = self.summary()
        self.assertEqual(1, returned.count(f"local-{current}-"))
        self.assertIn("state: returned", returned)

    def unreadable_records(self, target):
        """Leave one target's store there and impossible to read — the reported live failure.

        Bytes rather than a patched read: `records.reading` is what decides that a file which is
        not a database is `Unreadable` rather than absent, and a case that induced that decision
        itself would pass with the decision gone. The probe proves the fixture before the query is
        asked anything, and any delegation key does — the store refuses at open time.
        """
        directory.records(target).write_bytes(b"not an agent's records at all")
        with self.assertRaises(records.Unreadable):
            arriving.delegation_brief(target, "ava", self.turn, "del-probe")

    def test_an_unreadable_target_brief_keeps_named_and_local_work_listed(self):
        wanted = self.handed_over()
        directory.made("cass", support.A_STAND_IN)
        readable = self.handed_over("del-2-ddeeff", "Draft the changelog", target="cass")
        current = self.a_turn(
            "ava", self.parent.conversation, "working", "2026-08-10T12:02:00Z")
        turns_kept.add_turn_record(
            "ava", current, "tool",
            {"type": "tool", "id": "provider-internal-id", "did": "delegate"},
            when=datetime.datetime(2026, 8, 10, 12, 2, 5, tzinfo=datetime.timezone.utc))
        self.unreadable_records("bob")

        with mock.patch.object(records, "writing", side_effect=AssertionError("query wrote state")):
            result = delegation_query.read(
                "ava", "discord", "1180",
                now=datetime.datetime(2026, 8, 10, 12, 5, tzinfo=datetime.timezone.utc))
            said = self.summary()

        held = {item.item_id: item for item in result.items}
        self.assertEqual({wanted, readable},
                         {one.item_id for one in result.items if one.kind == "named-agent"})
        self.assertEqual("task identity unavailable", held[wanted].task)
        self.assertEqual("bob", held[wanted].target)
        self.assertEqual("active", held[wanted].state)
        self.assertEqual("4m elapsed", held[wanted].timing)
        self.assertEqual("Draft the changelog", held[readable].task)
        self.assertEqual("active", held[readable].state)
        self.assertEqual(
            1, len([one for one in result.items if one.kind == "provider-local"]))
        self.assertIn("Relevant delegations:", said)
        self.assertEqual(1, said.count(wanted))
        self.assertEqual(1, said.count(readable))
        self.assertNotIn("PRIVATE PROMPT BODY", said)

    def test_every_live_named_state_stays_listed_when_the_target_brief_cannot_be_read(self):
        wanted = self.handed_over()
        self.unreadable_records("bob")

        def shown(state):
            said = self.summary()
            self.assertEqual(1, said.count(wanted), said)
            self.assertIn(f"state: {state}", said)
            self.assertIn("task identity unavailable", said)
            self.assertNotIn("Audit the exporter", said)
            self.assertNotIn("PRIVATE PROMPT BODY", said)

        shown("active")

        delegations_kept.stop_asked(
            "ava", wanted, now=datetime.datetime(2026, 8, 10, 12, 1, tzinfo=datetime.timezone.utc))
        shown("stopping")

        result = arriving.said_by_rundesk_into(
            "ava", self.parent.conversation, "FULL RESULT MUST NOT APPEAR",
            external_id=f"delegation-result:{wanted}:answer-9",
            when=datetime.datetime(2026, 8, 10, 12, 3, tzinfo=datetime.timezone.utc))
        review = self.a_turn(
            "ava", self.parent.conversation, "working", "2026-08-10T12:03:01Z")
        arriving.handled_by_turn("ava", self.parent.conversation, (result.message,), review)
        delegations_kept.answered(
            "ava", wanted, now=datetime.datetime(2026, 8, 10, 12, 3, tzinfo=datetime.timezone.utc))
        shown("returned — awaiting review")

        turns_kept.finish_turn(
            "ava", review, turns_kept.DONE,
            when=datetime.datetime(2026, 8, 10, 12, 4, tzinfo=datetime.timezone.utc))
        shown("reviewed")

    def test_a_target_store_that_is_missing_or_unopenable_reads_as_identity_unavailable(self):
        wanted = self.handed_over()
        directory.records("bob").unlink()

        said = self.summary()
        self.assertEqual(1, said.count(wanted), said)
        self.assertIn("task identity unavailable", said)

        # A store present and impossible to open answers in sqlite3's own word rather than this
        # product's, and one behind a directory nobody may enter in the operating system's.
        # Induced exactly, because neither state can be staged from a file's contents.
        for why in (sqlite3.OperationalError("unable to open database file"),
                    PermissionError("state.db")):
            with self.subTest(why=type(why).__name__):
                with mock.patch.object(arriving, "delegation_brief", side_effect=why):
                    said = self.summary()
                self.assertEqual(1, said.count(wanted), said)
                self.assertIn("task identity unavailable", said)

    def test_the_asking_agents_own_unreadable_records_are_still_a_failure(self):
        self.handed_over()
        with mock.patch.object(turns_kept, "get_turn",
                               side_effect=records.Unreadable("ava's own turns")):
            with self.assertRaises(records.Unreadable):
                self.summary()

    def test_an_unexpected_failure_at_the_target_seam_is_still_a_query_failure(self):
        """The upper bound of the one optional read, at the seam that absorbs a storage answer.

        A `TypeError` from `delegation_brief` is this product's own defect — a signature that moved
        under its caller — and not a colleague's disk. Widened to `Exception`, the catch would
        answer a whole conversation with identities nobody can restore and no failure anywhere,
        which is the shape of the outage this seam was narrowed to end rather than to hide.
        """
        self.handed_over()
        with mock.patch.object(arriving, "delegation_brief",
                               side_effect=TypeError("signature changed")):
            with self.assertRaisesRegex(TypeError, "signature changed"):
                self.summary()

    def test_empty_state_is_plain_and_a_missing_conversation_is_not_created(self):
        before = arriving.conversations("ava")
        said = delegation_query.summary("ava", "discord", "new-place")
        self.assertEqual("No relevant delegations are active or recorded here.", said)
        self.assertEqual(before, arriving.conversations("ava"))


class AutomaticUpkeepOnTheGatewayBeat(WithAnAgent):
    """The real host loop carries a due usage window through settlement exactly once."""

    def setUp(self) -> None:
        super().setUp()
        records.stated(directory.records(self.name), {"provider_name": support.A_STAND_IN})
        conversation = arriving.recorded(
            self.name, "terminal", self.name, "owner", "start").conversation
        for offset in range(7):
            at = datetime.datetime(2026, 7, 1 + offset, 12, tzinfo=datetime.timezone.utc)
            turn = turns_kept.add_turn(
                self.name, {"conversation_id": conversation, "provider_name": "standin",
                            "access_mode": protocol.ACCESS_WORK}, when=at)
            turns_kept.finish_turn(self.name, turn, turns_kept.DONE, when=at)

    def upkeep_turns(self) -> List[dict]:
        """Every automatic upkeep turn in this agent's durable records."""
        try:
            with records.reading(directory.records(self.name)) as conn:
                return [dict(one) for one in conn.execute(
                    "SELECT id, turn_status FROM turns WHERE schedule_name = ? ORDER BY id",
                    (kept.UPKEEP,)).fetchall()]
        except records.Unreadable:
            return []

    def upkeep_outcome(self) -> Optional[str]:
        """The protected row's settlement, or ``None`` before it exists or settles."""
        try:
            with records.reading(directory.records(self.name)) as conn:
                row = conn.execute(
                    "SELECT last_outcome FROM schedules WHERE name = ?", (kept.UPKEEP,)).fetchone()
        except records.Unreadable:
            return None
        return str(row["last_outcome"]) if row and row["last_outcome"] else None

    def test_the_first_beat_starts_settles_and_does_not_repeat_one_due_window(self):
        child = self.a_running_gateway(beat=0.05)
        self.assertTrue(support.waited_until(
            lambda: self.upkeep_outcome() == kept.DONE, self.PATIENCE),
            f"upkeep never settled. Gateway log: {self.its_log()}")
        self.assertEqual([turns_kept.DONE],
                         [one["turn_status"] for one in self.upkeep_turns()])

        time.sleep(0.3)

        self.assertEqual(1, len(self.upkeep_turns()), "a later beat repeated the same usage window")
        self.assertIsNone(child.poll(), "the gateway ended while carrying automatic upkeep")


class TheVeryFirstThingItSays(WithAnAgent):
    """One line with a moment and a pid, before anything is parsed and before anything is read."""

    def test_it_says_what_pid_it_is_before_it_does_anything_else(self):
        # If `gateway.out` is empty while launchd says the job ran, the failure is upstream of this
        # code and belongs in the unified log. That one line is what turns "cannot tell" into
        # "look here" — so it has to land before the first thing that can fail.
        _code, said = self.ran(name="nobody-made-this-one")
        first = said.splitlines()[0]
        self.assertIn(f"pid {self.started[0].pid}", first)
        self.assertIn("nobody-made-this-one", first)
        self.assertIn(__version__, first)

    def test_the_moment_it_carries_is_the_shape_every_other_line_here_carries(self):
        # The same function as the log lines and the gateway's record, because these are read side
        # by side and two clocks would mean arithmetic on every comparison.
        _code, said = self.ran(name="nobody-made-this-one")
        self.assertTrue(said.startswith(f"[{logs.stamp()[:13]}"), said.splitlines()[0])

    def test_a_gateway_that_comes_up_says_it_too(self):
        self.a_running_gateway()
        self.assertIn(f"pid {self.started[0].pid}", self.what_it_said().splitlines()[0])


class StartingWhileAnUpdateOwnsTheInstall(WithAnAgent):
    """The cross-process barrier: no old imported gateway may claim during an update."""

    def test_it_waits_then_refreshes_before_claiming_the_agent(self):
        with locking.only_one(paths.gateway_transition_lock(), "the test update"):
            child = self.hosting(refreshing=True)
            self.assertTrue(support.waited_until(
                lambda: "this process is pid" in self.what_it_said(), 2.0), self.what_it_said())
            time.sleep(0.1)
            self.assertIsNone(self.holder(), "the gateway claimed its agent inside the update")
            self.assertIsNone(child.poll(), "the blocked gateway exited instead of waiting")

        self.assertTrue(support.waited_until(
            lambda: (self.home / "reentered").is_file(), self.PATIENCE), self.what_it_said())
        self.assertTrue(support.waited_until(
            lambda: self.holder() == child.pid, self.PATIENCE), self.what_it_said())


class WhatItRefusesToRunFor(WithAnAgent):
    """Every refusal, and every one of them exits `0` — see the module docstring for why."""

    def test_an_agent_that_is_not_there_says_so_and_exits_zero(self):
        code, said = self.ran(name="nobody-made-this-one")
        self.assertEqual(0, code, f"a refusal exited {code}, which asks launchd to restart it")
        self.assertIn("no agent called nobody-made-this-one", said)

    def test_a_directory_with_no_records_in_it_is_not_an_agent(self):
        # `state.db` is what makes a directory an agent. A half-made one exists and is not one.
        (self.home / "data" / "agents" / "half").mkdir(parents=True)
        code, said = self.ran(name="half")
        self.assertEqual(0, code)
        self.assertIn(directory.RECORDS, said)

    def test_an_agent_that_is_not_settled_onto_this_release_says_which_command_to_run(self):
        # Its records were written by an older rundesk and the steps that would carry it have not
        # run. Restarting would never fix that; `rundesk update` would.
        with records.writing(directory.records(self.name)) as conn:
            conn.execute("DELETE FROM migrations")
        code, said = self.ran()
        self.assertEqual(0, code)
        self.assertIn("not settled", said)
        self.assertIn("run: rundesk update", said)

    def test_a_second_gateway_stands_down_and_names_the_pid_that_has_the_name(self):
        # The claim *is* the check. Anything that asked first and started second has a gap another
        # gateway can arrive in — an ordinary `start` ended a live agent's whole process tree once.
        first = self.a_running_gateway()
        code, said = self.ran(out=self.home / "second.out")
        self.assertEqual(0, code)
        self.assertIn("already running", said)
        self.assertIn(str(first.pid), said)

    def test_a_refusal_that_raises_on_the_way_to_being_a_refusal_still_exits_zero(self):
        # The sharp edge stated as its own case. `directory.where` refuses a name that reaches
        # outside the agents directory, and an uncaught exception would exit 1 — which under
        # `SuccessfulExit: false` is a request to be restarted, for ever.
        somewhere = self.home / "not-an-agent"
        somewhere.mkdir()
        (self.home / "data" / "agents" / "reaching").symlink_to(somewhere)
        code, said = self.ran(name="reaching")
        self.assertEqual(0, code, "a refusal that raised exited non-zero")
        self.assertIn("could not be started", said)

    def test_records_that_cannot_be_read_at_all_still_exit_zero(self):
        directory.records(self.name).write_bytes(b"this is not a database")
        code, said = self.ran()
        self.assertEqual(0, code)
        self.assertIn("NOT RUNNING", said)

    def test_a_refusal_is_written_into_the_agents_own_log_as_well(self):
        # Two places, because they are read by two different people at two different moments:
        # `gateway.out` is what somebody explaining a job that will not start reaches for, and the
        # day file is where everything else this gateway ever said is.
        with records.writing(directory.records(self.name)) as conn:
            conn.execute("DELETE FROM migrations")
        self.ran()
        self.assertIn("gateway did not start", self.its_log())


class WhileItIsRunning(WithAnAgent):
    """The name is held by the kernel for exactly as long as the process lives."""

    def test_the_lock_is_held_while_it_lives_and_free_the_moment_it_is_gone(self):
        child = self.a_running_gateway()
        self.assertEqual(standing.ONLINE, standing.standing(self.at).how)
        self.assertEqual(child.pid, standing.standing(self.at).pid)

        os.kill(child.pid, signal.SIGTERM)               # a pid this case started, never a group
        child.wait(timeout=self.PATIENCE)
        self.assertEqual(standing.OFFLINE, standing.standing(self.at).how)

    def test_it_writes_down_what_it_is_and_says_so_in_its_own_log(self):
        child = self.a_running_gateway()
        said = standing.standing(self.at)
        self.assertEqual(child.pid, said.pid)
        self.assertFalse(said.stale, "a gateway that has just started has not missed a beat")
        self.assertTrue(support.waited_until(lambda: "gateway up for" in self.its_log(),
                                             self.PATIENCE), self.its_log())

    def test_the_name_it_holds_belongs_to_that_agents_directory_and_nowhere_else(self):
        self.a_running_gateway()
        self.assertTrue((self.at / standing.LOCK).is_file())
        self.assertTrue((self.at / standing.RECORD).is_file())


class HowItStops(WithAnAgent):
    """An orderly stop and a crash have to be different things in the log, or neither is readable."""

    def test_a_termination_request_brings_it_down_cleanly_and_exits_zero(self):
        # It has to land inside the job's `ExitTimeOut` too: a gateway that ignores SIGTERM makes
        # `bootout --wait` block for that whole window and then be SIGKILLed, which launchd calls
        # *languishing*.
        child = self.a_running_gateway()
        os.kill(child.pid, signal.SIGTERM)
        self.assertTrue(support.waited_until(lambda: child.poll() is not None, self.PATIENCE),
                        f"it did not stop. It said: {self.what_it_said()}")
        self.assertEqual(0, child.returncode)
        self.assertIn("gateway stopping", self.its_log())

    def test_a_hang_up_stops_it_the_same_way(self):
        # Python installs no handler for `SIGHUP`, so without one the kernel ends the process
        # outright — no exception, no `finally`, and nothing in the log to tell it from a crash.
        child = self.a_running_gateway()
        os.kill(child.pid, signal.SIGHUP)
        self.assertTrue(support.waited_until(lambda: child.poll() is not None, self.PATIENCE))
        self.assertEqual(0, child.returncode)
        self.assertIn("gateway stopping", self.its_log())

    def test_a_gateway_killed_outright_leaves_its_record_and_still_reads_as_offline(self):
        # Nothing runs on `SIGKILL`: no handler, no `finally`, no tidying. The record is still whole
        # on disk and the answer is still offline, because the answer was never the record's to give.
        child = self.a_running_gateway()
        os.kill(child.pid, signal.SIGKILL)
        self.assertTrue(support.waited_until(lambda: not programs.alive(child.pid), self.PATIENCE))
        child.wait(timeout=self.PATIENCE)

        self.assertTrue((self.at / standing.RECORD).is_file(),
                        "the record was cleaned up, so this proves nothing")
        self.assertEqual(standing.OFFLINE, standing.standing(self.at).how)
        self.assertNotIn("gateway stopping", self.its_log(),
                         "a gateway that was killed outright claimed to have stopped cleanly")

    def test_the_name_is_free_again_for_a_gateway_that_was_killed_outright(self):
        child = self.a_running_gateway()
        os.kill(child.pid, signal.SIGKILL)
        self.assertTrue(support.waited_until(lambda: not programs.alive(child.pid), self.PATIENCE))
        child.wait(timeout=self.PATIENCE)

        second = self.hosting(out=self.home / "second.out")
        self.assertTrue(support.waited_until(lambda: self.holder() == second.pid, self.PATIENCE),
                        "the name never came free. It said: "
                        f"{self.what_it_said(self.home / 'second.out')}")


class TheWindowBetweenTheClaimAndTheRecord(WithAnAgent):
    """A gateway is online the instant it holds the name, and the record arrives afterwards.

    Claiming the name and writing the record are deliberately two steps: the lock **is** the
    identity and the record is only a description of whoever holds it. So there is a real moment —
    short, and reachable by anybody running `status` at the wrong instant — where a gateway is
    `ONLINE` and has said nothing about itself yet.

    Pinned here because the obvious "fix" is wrong in a way that is hard to argue back from later.
    Making `standing` answer `OFFLINE` when the record is missing would have it say a running
    gateway is not running, which is the one answer this whole design exists to make impossible. And
    moving the record inside `holding` would put a write inside the claim, giving a start one more
    thing to fail at and one more way to hold a name it cannot describe.

    This case is also why the suite waits on the record rather than on `ONLINE`: a case that waited
    on the claim would be racing this window rather than avoiding it.
    """

    def test_a_gateway_that_has_not_written_its_record_yet_is_still_online(self):
        with standing.holding(self.at):
            how = standing.standing(self.at)

        self.assertEqual(standing.ONLINE, how.how)
        self.assertIsNone(how.pid, "a pid was invented for a gateway that has not said what it is")
        self.assertIsNone(how.stale, "a gateway with nothing to judge it by was judged")

    def test_the_record_is_what_arrives_second_and_never_what_decides(self):
        # The order, stated as a case: no record on disk while the name is already held.
        with standing.holding(self.at):
            self.assertFalse((self.at / standing.RECORD).exists())
            standing.write_record(self.at, "one", "9.9.9")
            self.assertEqual(os.getpid(), standing.standing(self.at).pid)


class WhatTheSupervisorCaptured(WithAnAgent):
    """`gateway.out` and `gateway.err` are appended to for ever by something that never rotates them.

    launchd opens both `O_CREAT|O_RDWR|O_APPEND` and never truncates, so in a crash loop every
    restart adds another traceback and nothing comes to sweep it. They are also the only account of a
    start that died before the gateway had a log of its own, so the gateway rotates them itself, at
    startup, by content — see `host`'s docstring for why a rename would be worse than the growth.

    Every case here starts a real gateway with a real descriptor on the real file, because what is
    being asked is what a process inheriting that descriptor does after the file moves underneath it.
    """

    def setUp(self) -> None:
        super().setUp()
        self.out, self.err = standing.captured(self.at)
        self.out.parent.mkdir(parents=True, exist_ok=True)
        self.aside = self.out.with_name(f"{self.out.name}.1")

    def a_capture_of(self, size: int, into: Optional[Path] = None, first: bytes = b"") -> Path:
        """A capture of about that many bytes, as a crash loop leaves one."""
        one = into or self.out
        line = b"Traceback (most recent call last): nobody read this\n"
        one.write_bytes(first + line * (max(0, size - len(first)) // len(line) + 1))
        return one

    def cannot_be_hosted(self) -> None:
        """Leave the agent in a state this release refuses to host, so a start refuses and exits.

        A refusal is the case that fills these files: a gateway refusing for a permanent reason is
        one launchd brings back and back, appending another sentence every time. It is also the only
        way to watch a *whole* start — up, rotate, say, exit — inside a case.
        """
        with records.writing(directory.records(self.name)) as conn:
            conn.execute("DELETE FROM migrations")

    def a_whole_start(self) -> str:
        """One start of a real gateway onto the real capture file. Hands back what is in it after."""
        code, said = self.ran(out=self.out)
        self.assertEqual(0, code, f"the start did not refuse cleanly. It said: {said}")
        return said

    def captures(self) -> List[str]:
        """Everything standing beside the live capture, by name."""
        return sorted(one.name for one in self.out.parent.iterdir()
                      if one.name.startswith(self.out.name))

    def test_a_capture_that_has_grown_past_the_threshold_is_moved_aside(self):
        self.a_capture_of(host.CAPTURE_OVER + 1)
        self.cannot_be_hosted()

        self.a_whole_start()

        self.assertTrue(self.aside.is_file(), "nothing was kept")
        self.assertIn(b"nobody read this", self.aside.read_bytes())
        self.assertLess(self.out.stat().st_size, 1024, "the live file was not emptied")

    def test_a_capture_that_is_still_small_is_left_exactly_where_it_is(self):
        # The guarantee that keeps a gateway `KeepAlive` brings back every thirty seconds from
        # rotating 2,880 times a day and rolling the evidence off the end within minutes.
        self.out.write_bytes(b"one earlier start said this\n")
        self.cannot_be_hosted()

        said = self.a_whole_start()

        self.assertFalse(self.aside.exists(), "it rotated a file that had barely anything in it")
        self.assertIn("one earlier start said this", said)

    def test_the_first_line_lands_in_the_live_file_even_when_the_rotation_took_it(self):
        # The whole worth of that line is that it is *in* `gateway.out`: an empty one beside a job
        # launchd says has run means the failure is upstream of this code. A rotation that carried
        # it off into `gateway.out.1` and left nothing behind would have destroyed exactly that.
        self.a_capture_of(host.CAPTURE_OVER + 1)
        self.cannot_be_hosted()

        said = self.a_whole_start()

        self.assertIn(f"pid {self.started[0].pid}", said.splitlines()[0])
        self.assertIn(__version__, said.splitlines()[0])

    def test_a_gateway_that_is_still_running_goes_on_writing_into_the_file_it_emptied(self):
        # The one that would be silently wrong if the rotation renamed instead of truncating: the
        # gateway holds the descriptor launchd opened, so a rename would have it spend its whole
        # life writing into `gateway.out.1` while the file everybody opens stayed empty.
        self.a_capture_of(host.CAPTURE_OVER + 1)

        child = self.hosting(out=self.out)
        self.assertTrue(support.waited_until(lambda: self.holder() == child.pid, self.PATIENCE),
                        f"the gateway never came up. It said: {self.what_it_said(self.out)}")

        self.assertIn(f"pid {child.pid}", self.what_it_said(self.out))
        self.assertLess(self.out.stat().st_size, 1024,
                        "the live file still holds everything, so nothing was rotated at all")
        self.assertIn(b"nobody read this", self.aside.read_bytes())

    def test_what_it_kept_holds_the_start_of_what_went_wrong_and_says_what_it_dropped(self):
        # The head and not the tail: the crash that started a loop is the one somebody is looking
        # for, and it is the one at the top of the file.
        self.a_capture_of(host.CAPTURE_OVER * 2, first=b"the first thing that ever went wrong\n")
        self.cannot_be_hosted()

        self.a_whole_start()

        kept = self.aside.read_bytes()
        self.assertTrue(kept.startswith(b"the first thing that ever went wrong"))
        self.assertIn(b"the rest is not here", kept)

    def test_what_went_to_standard_error_is_moved_aside_too(self):
        self.a_capture_of(host.CAPTURE_OVER + 1, into=self.err)
        self.cannot_be_hosted()

        self.a_whole_start()

        self.assertIn(b"nobody read this", self.err.with_name(f"{self.err.name}.1").read_bytes())
        self.assertEqual(0, self.err.stat().st_size)

    def test_a_gateway_restarted_over_and_over_never_leaves_more_than_it_keeps(self):
        # The months-scale case, run small: a crash loop that fills the file, is brought back, fills
        # it again, for as long as nobody is watching. What that may ever cost is fixed.
        self.cannot_be_hosted()
        for _start in range(host.CAPTURES_KEPT + 3):
            self.a_capture_of(host.CAPTURE_OVER + 1)
            self.a_whole_start()

        self.assertEqual([f"{self.out.name}.{which}" for which in range(1, host.CAPTURES_KEPT + 1)],
                         self.captures()[1:], f"it left {self.captures()}")
        self.assertLess(sum(one.stat().st_size for one in self.out.parent.iterdir()),
                        host.CAPTURE_OVER * (host.CAPTURES_KEPT + 2),
                        "what the captures cost is not bounded by the two numbers that decide it")

    def test_a_capture_it_cannot_move_aside_never_stops_it_refusing_cleanly(self):
        # Failing to *tidy* a log may never become failing to *exit*: a non-zero exit here is a
        # request to be restarted, and the condition would be exactly the same on the way back.
        support.not_as_root(self)
        self.a_capture_of(host.CAPTURE_OVER + 1)
        self.cannot_be_hosted()
        self.out.parent.chmod(0o500)
        self.addCleanup(self.out.parent.chmod, 0o700)

        code, _said = self.ran(out=self.out)

        self.assertEqual(0, code, "a refusal that could not rotate its capture exited non-zero")


class WhatItGoesOnDoingForMonths(WithAnAgent):
    """The loop, read as though this process has been in it since March.

    Nothing here is about coming up. Everything here is about the things that only appear once
    nobody has restarted the gateway in a long time: a beat that stops landing, a warning written
    every fifteen seconds for a week, a directory gaining a file a day for ever.
    """

    #: Fast enough that a case sees several passes of the loop without sleeping through the real
    #: fifteen seconds, and slow enough that it is still a loop and not a spin.
    QUICKLY = 0.2

    def several_more_beats(self) -> None:
        """Give the loop time to do the wrong thing, which is the only way to prove it does not.

        A guessed wait, and deliberately so: every other wait in this suite is for something to
        happen, and these two cases are about something that must *not* — a second warning, an exit.
        There is nothing to ask about, so the wait is a window rather than a question, and it is six
        passes of a loop the case has already made fast.
        """
        time.sleep(self.QUICKLY * 6)

    def taken_away(self, at: Path) -> None:
        """Remove a directory a live gateway is still writing into, and prove it went.

        **`shutil.rmtree` is two steps and a running gateway fits between them.** It walks the tree
        unlinking as it goes and then `rmdir`s what is left, so a beat, a log line or a swept day
        landing in that window leaves the directory not empty and the call raises `ENOTEMPTY` — the
        case going red in its own setup, before the guarantee it exists for has been asked about at
        all. Measured on the 3.9 floor with eight suites running at once.

        So the removal is asked for until it takes, which is the same shape as every other wait in
        this suite: a condition asked about rather than a window slept through. It cannot hide the
        thing the case is *for* — that a gateway does not put its agent's directory back is proved by
        the assertion after the beats that follow, and a gateway which really did rebuild it would
        rebuild it there too.
        """
        def gone() -> bool:
            shutil.rmtree(at, ignore_errors=True)
            return not at.exists()
        self.assertTrue(support.waited_until(gone, self.PATIENCE),
                        f"{at} could not be taken away: something is writing into it faster than "
                        f"it can be removed")

    def a_day_file_from(self, days_ago: int) -> Path:
        """One of this gateway's own day files, from far enough back that it should be swept."""
        where = standing.logs_at(self.at)
        where.mkdir(parents=True, exist_ok=True)
        when = datetime.datetime.now().astimezone() - datetime.timedelta(days=days_ago)
        one = where / logs.named_for(when)
        one.write_text("[an older day] INFO:   gateway up\n", encoding="utf-8")
        return one

    def an_arrival_from(self, days_ago: int, kind: str = "discord") -> Path:
        """One day's worth of what came in through a channel, from that many days ago."""
        when = datetime.datetime.now() - datetime.timedelta(days=days_ago)
        at = arrivals.arrived_at(self.name, kind, f"m{days_ago}", when)
        at.mkdir(parents=True, exist_ok=True)
        (at / "report.csv").write_text("one,two\n", encoding="utf-8")
        return at

    def test_it_sweeps_the_days_it_no_longer_keeps(self):
        # A file a day, kept for ever, is the same unbounded growth as a capture nobody truncates —
        # reached slowly instead of quickly. `utils.logs` has always had the sweep; nothing called it.
        old = self.a_day_file_from(host.KEPT_DAYS + 1)
        recent = self.a_day_file_from(1)

        # Made fast, because the sweep is the loop's first pass and not a call before it — which is
        # what makes this case cover the wiring as well as the sweeping.
        self.a_running_gateway(beat=self.QUICKLY)

        self.assertTrue(support.waited_until(lambda: not old.exists(), self.PATIENCE),
                        f"the old day was kept. It said: {self.what_it_said()}")
        self.assertTrue(recent.exists(), "it swept a day it was told to keep")

    def test_it_sweeps_again_when_the_day_turns_rather_than_only_on_the_way_up(self):
        # The half of the sweep a running gateway proves nothing about: a gateway that is doing its
        # job is one nobody restarts, so a process up since March swept once, in March, and has been
        # gaining a file a day ever since. Driven directly rather than through a child, because the
        # only thing that would make a real one do this is waiting until midnight.
        where = standing.logs_at(self.at)
        old = self.a_day_file_from(host.KEPT_DAYS + 1)

        today = host._kept_the_days(self.name, where, "")   # the sweep on the way up

        self.assertFalse(old.exists(), "it did not sweep at all")
        again = self.a_day_file_from(host.KEPT_DAYS + 1)
        self.assertEqual(today, host._kept_the_days(self.name, where, today))
        self.assertTrue(again.exists(), "it swept twice in one day, which is a listing per beat")

        host._kept_the_days(self.name, where, "a day that has now turned")

        self.assertFalse(again.exists(), "the day turned and it never swept again")

    def test_it_sweeps_what_arrived_through_a_channel_on_the_same_beat_it_sweeps_its_own_days(self):
        # Arrivals are the other thing here that gains a directory a day with nobody having decided
        # to keep it, and this loop is the only thing that will ever remove one — `channels.files`
        # has always had the sweep and nothing called it, which is exactly how the day files began.
        where = standing.logs_at(self.at)
        old = self.an_arrival_from(arrivals.KEPT_DAYS + 1)
        recent = self.an_arrival_from(1)

        host._kept_the_days(self.name, where, "")

        self.assertFalse(old.exists(), "a day of arrivals older than any are kept was left standing")
        self.assertTrue(recent.exists(), "it swept a day of arrivals it was told to keep")

    def test_a_channel_directory_it_cannot_read_never_stops_it_sweeping_or_ends_the_gateway(self):
        # Tidying may not end a gateway, and this one walks a directory a stranger's adapter writes
        # into. `_kept_the_days` answers with the day whatever happened, because what it answers is
        # what stops the loop doing the arithmetic every fifteen seconds.
        support.not_as_root(self)
        where = standing.logs_at(self.at)
        old = self.a_day_file_from(host.KEPT_DAYS + 1)
        directory.channels(self.name).mkdir(parents=True, exist_ok=True)
        directory.channels(self.name).chmod(0o000)
        self.addCleanup(directory.channels(self.name).chmod, 0o700)

        today = host._kept_the_days(self.name, where, "")

        self.assertEqual(logs.named_for(datetime.datetime.now()), today)
        self.assertFalse(old.exists(), "an unreadable channel directory stopped the day files being "
                                       "swept at all")

    def a_turn_with_records(self, old: int, recent: int) -> int:
        """One turn carrying records from long ago and records from today."""
        conversation = arriving.asked_at_a_terminal(self.name, "what changed?").conversation
        turn = turns_kept.add_turn(self.name, {"conversation_id": conversation,
                                               "provider_name": "a-stand-in",
                                               "access_mode": "read"})
        long_ago = (datetime.datetime.now(datetime.timezone.utc)
                    - datetime.timedelta(days=host.KEPT_DAYS + 16))
        for n in range(old):
            turns_kept.add_turn_record(self.name, turn, "tool", {"n": n}, when=long_ago)
        for n in range(recent):
            turns_kept.add_turn_record(self.name, turn, "tool", {"n": n})
        return turn

    def test_it_sweeps_what_turns_did_on_the_same_beat(self):
        """`turn_records_days` was configurable, documented, and read by nothing at all — which is
        worse than not offering it, because somebody who set it believed they had bounded
        something."""
        turn = self.a_turn_with_records(old=5, recent=2)
        where = standing.logs_at(self.at)
        where.mkdir(parents=True, exist_ok=True)

        host._kept_the_days(self.name, where, "")

        self.assertEqual(2, len(turns_kept.list_turn_records(self.name, turn)),
                         "what turns did grew without bound however the setting was set")

    def test_the_turn_and_what_was_said_are_never_swept_with_it(self):
        """A turn's own row is the ledger and what was said is the owner's history."""
        turn = self.a_turn_with_records(old=3, recent=0)
        where = standing.logs_at(self.at)
        where.mkdir(parents=True, exist_ok=True)

        host._kept_the_days(self.name, where, "")

        self.assertEqual(turn, turns_kept.get_turn(self.name, turn)["id"])
        self.assertTrue(arriving.conversations(self.name), "a conversation was swept away")

    def test_records_it_cannot_sweep_never_end_the_gateway(self):
        """Tidying may not end a gateway — the same rule the day files are swept under."""
        self.a_turn_with_records(old=1, recent=0)
        where = standing.logs_at(self.at)
        where.mkdir(parents=True, exist_ok=True)
        directory.records(self.name).write_text("this is prose, not a database", encoding="utf-8")

        self.assertEqual(logs.named_for(datetime.datetime.now()),
                         host._kept_the_days(self.name, where, ""))

    def test_a_beat_that_cannot_be_written_does_not_take_a_working_gateway_down(self):
        # A full disk, a volume gone read-only, a record taken away — none of them is a reason to
        # end a gateway that is hosting its agent, and all of them would be the same on the way back
        # from a restart. Letting it through would exit non-zero into an endless restart.
        child = self.a_running_gateway(beat=self.QUICKLY)
        (self.at / standing.RECORD).unlink()

        self.assertTrue(support.waited_until(lambda: "could not say it is still working"
                                             in self.its_log(), self.PATIENCE), self.its_log())
        self.assertIsNone(child.poll(), "a beat that failed took the whole gateway down")
        self.assertEqual(standing.ONLINE, standing.standing(self.at).how)

    def test_it_says_a_beat_stopped_landing_once_and_not_every_fifteen_seconds(self):
        # A log that grows with the beat is the growth it was meant to bound, arrived at from the
        # other side: a line every fifteen seconds for as long as a disk stays full is 5,760 a day.
        child = self.a_running_gateway(beat=self.QUICKLY)
        (self.at / standing.RECORD).unlink()
        self.assertTrue(support.waited_until(lambda: "could not say it is still working"
                                             in self.its_log(), self.PATIENCE), self.its_log())

        self.several_more_beats()
        self.assertIsNone(child.poll())

        self.assertEqual(1, self.its_log().count("could not say it is still working"),
                         f"it said it every time round the loop: {self.its_log()}")

    def test_a_beat_that_starts_landing_again_is_said_out_loud_as_well(self):
        # A warning nothing ever retracts is one somebody goes on believing.
        child = self.a_running_gateway(beat=self.QUICKLY)
        (self.at / standing.RECORD).unlink()
        self.assertTrue(support.waited_until(lambda: "could not say it is still working"
                                             in self.its_log(), self.PATIENCE), self.its_log())

        standing.write_record(self.at, self.name, __version__)

        self.assertTrue(support.waited_until(lambda: "still working again" in self.its_log(),
                                             self.PATIENCE), self.its_log())
        self.assertIsNone(child.poll())

    def test_a_gateway_whose_agent_was_taken_away_does_not_put_the_directory_back(self):
        # `_refused` has the same rule for the same reason: a directory invented by whatever is
        # complaining that it is missing is one that then looks half-made to everything else.
        child = self.a_running_gateway(beat=self.QUICKLY)
        first = json.loads((self.at / standing.RECORD).read_text(encoding="utf-8"))["since_boot"]

        def a_later_beat_landed() -> bool:
            try:
                now = json.loads(
                    (self.at / standing.RECORD).read_text(encoding="utf-8"))["since_boot"]
                return float(now) > float(first)
            except (OSError, KeyError, TypeError, ValueError):
                return False

        # Holding the gateway lock proves the process was admitted, not that startup settlement
        # has finished. Taking the records away during that settlement tests a startup crash rather
        # than this case's long-running loop. A later beat can land only after settlement and one
        # whole pass through that loop.
        self.assertTrue(support.waited_until(a_later_beat_landed, self.PATIENCE),
                        f"the gateway never finished starting. It said: {self.what_it_said()}")
        self.taken_away(self.at)

        self.several_more_beats()

        self.assertIsNone(
            child.poll(),
            "it ended when its agent went away, which exits non-zero. Captured output:\n"
            + self.what_it_said())
        self.assertFalse(self.at.exists(), "it made its agent's directory again to complain into")


class TheScheduleItHosts(WithAnAgent):
    """A real gateway, a real schedule, and the child it really starts.

    Driven through the same gateway process every other case here uses, because the guarantees are
    about what the *loop* does: when it first looks at the clock, and what it takes down with it.
    `tests/test_schedules_firing.py` proves everything the firing itself promises; what is here is
    only the wiring, which is the part no unit case can see.
    """

    #: A beat long enough that a schedule firing inside it cannot have waited for one. The whole
    #: point of the case below: with the look after the sleep, nothing happens for this long.
    A_LONG_BEAT = 30.0

    #: And one short enough that a case about what the log *says* is not sitting out a beat waiting
    #: for the reaping. What a firing came to is written on the look after it finished, so the
    #: outcome arrives within one beat of the work ending — which is the design, not a delay to
    #: engineer around.
    A_SHORT_BEAT = 1.0

    def given(self, name: str = "tick", command: str = "/bin/echo it ran") -> None:
        kept.added(self.name, name, {"cron": "* * * * *", "command": command})

    def fired(self, name: str = "tick") -> bool:
        return kept.one(self.name, name)["last_fired_for"] is not None

    def test_a_gateway_looks_at_the_clock_as_soon_as_it_has_its_name(self):
        # **Not one interval later.** A schedule is due in one stated minute, so a gateway that
        # waited a whole beat before its first look lost every occurrence due in the last fifteen
        # seconds of the minute it started in — which is exactly the moment a machine restarts one.
        # The beat here is thirty seconds, so a firing that lands promptly cannot have waited for it.
        self.given()
        started = time.monotonic()
        self.a_running_gateway(beat=self.A_LONG_BEAT)
        self.assertTrue(support.waited_until(self.fired, self.PATIENCE),
                        f"it never fired. It said: {self.its_log()}")
        self.assertLess(time.monotonic() - started, self.A_LONG_BEAT,
                        "the first look waited for a beat, so a firing due in that window is lost")

    def test_the_beat_still_waits_before_saying_anything(self):
        # The other half, and it is the opposite decision: saying a gateway is working before it has
        # done any work is a report with nothing behind it. Looking at the clock first must not have
        # moved the beat forward with it.
        self.given()
        child = self.a_running_gateway(beat=self.A_LONG_BEAT)
        self.assertTrue(support.waited_until(self.fired, self.PATIENCE))
        how = standing.standing(self.at)
        self.assertEqual(child.pid, how.pid)
        self.assertFalse(how.stale, "a gateway that has only just come up already reads as wedged")

    def test_a_gateway_says_in_its_own_log_that_a_schedule_ran_and_what_it_came_to(self):
        # The whole reason somebody opens this file: it ran, it finished, or it failed and why.
        self.given(command="/bin/sh -c 'echo the work happened; exit 0'")
        self.a_running_gateway(beat=self.A_SHORT_BEAT)
        self.assertTrue(support.waited_until(
            lambda: "completed" in self.its_log(), self.PATIENCE),
            f"it never said what became of the schedule. It said: {self.its_log()}")
        said = self.its_log()
        self.assertIn("schedule tick is due for", said)
        self.assertIn("schedule tick started as pid", said)
        self.assertIn("the work happened", said)

    def test_a_schedule_that_failed_says_why_in_the_gateways_own_log(self):
        self.given(command="/bin/sh -c 'echo it went wrong >&2; exit 3'")
        self.a_running_gateway(beat=self.A_SHORT_BEAT)
        self.assertTrue(support.waited_until(
            lambda: "failed with exit 3" in self.its_log(), self.PATIENCE),
            f"a failure was never reported. It said: {self.its_log()}")
        self.assertIn("it went wrong", self.its_log())

    def test_an_orderly_stop_takes_the_work_a_schedule_started_with_it(self):
        # A child is in a session of its own, so launchd's group-wide cleanup of this job cannot
        # reach it: if the gateway does not stop it, nothing ever will.
        self.given(command="/bin/sh -c 'while true; do sleep 0.05; done'")
        child = self.a_running_gateway(beat=self.A_LONG_BEAT)
        # **Waited for by the line the gateway writes, not by the lock.** The lock is taken by the
        # gateway *before* it spawns — that is what stops two of them starting one schedule — so it
        # goes to "running" a moment before there is anything to stop, and a case that signalled
        # there was signalling a gateway that had not taken hold of the work yet. It failed one run
        # in five on the 3.9 floor and never on a current interpreter, which is exactly the shape of
        # a race nobody notices until CI does.
        self.assertTrue(support.waited_until(
            lambda: "started as pid" in self.its_log(), self.PATIENCE),
            f"the work never started. It said: {self.its_log()}")

        child.send_signal(signal.SIGTERM)
        self.assertTrue(support.waited_until(lambda: child.poll() is not None, self.PATIENCE))

        self.assertTrue(support.waited_until(
            lambda: not firing.still_running(self.name, "tick"), self.PATIENCE),
            "the gateway stopped and left the work it started running with nobody holding it")
        self.assertEqual(kept.STOPPED, kept.one(self.name, "tick")["last_outcome"])

    def test_a_second_stop_arriving_during_the_shutdown_does_not_crash_the_gateway(self):
        # **The window this work opened.** Before schedules there was nothing on the `ExitStack` to
        # unwind, so a second signal during shutdown had nothing to interrupt. Now the unwind stops
        # every child a schedule started and may spend up to `STOPPING_WITHIN` seconds doing it — and
        # `Stopped` is a `BaseException` precisely so `firing`'s guards cannot swallow it, so a
        # second `SIGTERM` in that window escaped `run` entirely. Exit non-zero under
        # `KeepAlive {SuccessfulExit: false}` is *bring it back*, so a clean stop became the endless
        # restart this module is arranged to make unreachable — and the children not yet reached were
        # left running with nothing holding them.
        self.given(command="/bin/sh -c 'trap \"\" TERM; while true; do sleep 0.05; done'")
        child = self.a_running_gateway(beat=self.A_LONG_BEAT)
        self.assertTrue(support.waited_until(
            lambda: "started as pid" in self.its_log(), self.PATIENCE),
            f"the work never started. It said: {self.its_log()}")

        child.send_signal(signal.SIGTERM)
        # **Waited for, and the wait is what gives this case teeth.** Sent immediately, the second
        # signal lands while the gateway is still inside its own `except Stopped` and is caught
        # exactly as the first was — the case then passes with the guard deleted, which is how it
        # first read. The line below is written *after* the handlers have been stood down, so seeing
        # it means the shutdown proper has begun; and the child ignores `SIGTERM`, so the stop that
        # follows spends seconds asking, waiting, and only then telling. That is the window.
        self.assertTrue(support.waited_until(
            lambda: "gateway stopping for" in self.its_log(), self.PATIENCE),
            f"it never began stopping. It said: {self.its_log()}")
        for _again in range(3):
            if child.poll() is None:
                child.send_signal(signal.SIGTERM)

        self.assertTrue(support.waited_until(lambda: child.poll() is not None, self.PATIENCE),
                        f"it never ended. It said: {self.its_log()}")
        self.assertEqual(OK, child.returncode,
                         "a gateway asked to stop twice exited non-zero, which launchd reads as a "
                         f"request to be restarted. It said: {self.its_log()}")

    def test_a_schedule_that_could_not_run_never_takes_the_gateway_down(self):
        # Under `KeepAlive {SuccessfulExit: false}` a non-zero exit is a request to be restarted, so
        # a firing that ended the process would be a permanent condition turned into a loop.
        self.given(command="/no/such/program at all")
        child = self.a_running_gateway(beat=1.0)
        self.assertTrue(support.waited_until(
            lambda: "did not start" in self.its_log(), self.PATIENCE),
            f"it never tried. It said: {self.its_log()}")
        self.assertIsNone(child.poll(), "a schedule that could not run ended the gateway")


class WhatItMayDo(WithAnAgent):
    """The loop that says when this agent gains or loses a skill.

    Driven directly, the way `_kept_the_days` is: what these prove is the carrier and the file, and
    a real gateway is the wrong instrument for "and then it wrote nothing".
    """

    def setUp(self) -> None:
        super().setUp()
        self.where = standing.logs_at(self.at)
        library.where().mkdir(parents=True, exist_ok=True)
        catalogs.place_bundled()

    def a_channel(self) -> None:
        """A channel this agent is told things through, with no adapter running for it."""
        channels.added(self.name, "discord", {
            "describes": "discord", "allowed": json.dumps(["2207"])})
        channels.telling(self.name, "discord", "1180")

    def a_skill(self, name: str) -> None:
        """A grant standing in the agent's own directory, made the way every grant is."""
        source = library.tree(library.BUNDLED) / library.INSIDE / library.REQUIRED_SKILL
        stands = grants.where(self.name)
        stands.mkdir(parents=True, exist_ok=True)
        (stands / name).symlink_to(os.path.relpath(source, stands))

    def look(self, knew=None):
        return host._told_what_changed(self.name, self.where, hosting.Watching({}, {}, {}), knew)

    def test_a_first_look_says_nothing_at_all(self):
        # Otherwise the one startup after an upgrade announces every skill the agent already holds
        # as newly gained — a paragraph of noise in somebody's chat for no change at all.
        #
        # **Asserted on whether anything was *said*, not on what came back.** Both answers are the
        # same tuple, so a case reading only the carrier cannot tell a quiet first look from one that
        # announced everything — which is how this case was first written and why it proved nothing.
        self.a_skill("jira")
        with mock.patch.object(host, "_told", return_value=host.TOLD) as told:
            self.assertEqual(("jira",), self.look())
        told.assert_not_called()

    def test_a_skill_granted_and_revoked_between_two_looks_leaves_nothing_to_say(self):
        # Worked out afresh against what was last *said*, never accumulated.
        self.assertEqual(("jira",), self.look(("jira",)))

    def test_the_lines_it_composes_name_the_skill_and_say_which_way_it_went(self):
        self.assertEqual(["🧩 Skill granted — `b`", "🗑️ Skill revoked — `a`"],
                         host._what_changed(("a",), ("b",)))

    def test_several_changes_at_once_are_one_message(self):
        # A catalog update that retires six skills is one change to what this agent can do, not six
        # notifications.
        said = host._what_changed(("a", "b"), ("c", "d", "e"))
        self.assertEqual(5, len(said))
        self.assertTrue(said[0].startswith("🧩"), "gains are not first")

    def test_a_change_waits_for_a_surface_rather_than_being_lost(self):
        # A notified channel with no adapter up. Nothing is offered to it at all, and nothing is
        # written down, so the change is still owed after a restart.
        #
        # **The gate is asked before `_told`, and that is the point being pinned.** `hosting.told`
        # answers `False` only when there is no child; an adapter that has been started and has not
        # authenticated takes the write into its pipe and answers `True`, so a change offered before
        # the gate is a change nobody ever sees and the record says it was told.
        self.a_channel()
        self.a_skill("jira")
        with mock.patch.object(host, "_told", return_value=host.TOLD) as told:
            self.assertEqual((), self.look(()),
                             "a change nobody could be told was carried forward as said")
        told.assert_not_called()

    def test_an_agent_that_tells_nobody_anything_still_tracks_what_it_may_do(self):
        # There is no channel and there never will be until somebody marks one, so the baseline
        # tracks quietly — otherwise an owner who adds a channel in November is greeted by every
        # grant they made since March.
        self.a_skill("jira")
        self.assertEqual(("jira",), self.look(()))

    def test_a_home_that_is_not_there_is_not_an_agent_that_lost_every_skill(self):
        # Absent is not empty. And the write must not put the directory back: `files.write_json`
        # makes the directory it writes into.
        shutil.rmtree(grants.where(self.name), ignore_errors=True)
        self.assertEqual(("jira",), self.look(("jira",)))
        self.assertFalse(grants.where(self.name).exists(), "it put the agent's directory back")

    def test_grants_that_cannot_be_read_change_nothing_and_never_raise(self):
        # Nothing in this loop may exit non-zero: launchd would bring the gateway straight back into
        # the same condition.
        support.not_as_root(self)
        self.a_skill("jira")
        grants.where(self.name).chmod(0o000)
        self.addCleanup(grants.where(self.name).chmod, 0o755)
        self.assertEqual(("jira",), self.look(("jira",)))


class TheStopFitsInsideWhatTheJobAllows(unittest.TestCase):
    """The one number this module shares with the layer above it, and cannot import.

    `host` may not import `job` — a process never talks to its own supervisor — so the budget a
    shutdown has and the `ExitTimeOut` the job hands it are two constants that have to agree with
    nothing forcing them to. Above it, launchd `SIGKILL`s the gateway partway through stopping its
    children and every one of them is orphaned still holding its lock.
    """

    def test_a_gateways_stop_budget_leaves_room_inside_the_jobs_exit_timeout(self):
        self.assertLess(host.STOPPING_WITHIN, job.EXIT_TIMEOUT,
                        "a gateway may spend longer stopping its children than launchd allows it "
                        "to live, which orphans every one of them")

    def test_the_budget_is_not_so_small_that_nothing_can_be_stopped_in_it(self):
        self.assertGreater(host.STOPPING_WITHIN, firing.STOPPING_LEAST)

    def test_every_tenant_that_stops_children_is_given_a_share_rather_than_the_whole_budget(self):
        # **The arithmetic that reads as correct at every line and takes forty seconds.** Two things
        # this gateway hosts have children to stop, and handing each the whole of `STOPPING_WITHIN`
        # spends it twice against an `ExitTimeOut` of twenty-five — after which launchd `SIGKILL`s
        # the gateway partway through the second one and orphans every child it never reached.
        #
        # Counted off the teardown stack rather than asserted as a number, because the way this goes
        # wrong is a *third* tenant being registered by somebody who never read this file.
        said = (support.CHECKOUT / "src" / "rundesk" / "gateways" / "host.py").read_text()
        self.assertEqual(host.STOPPING_SHARES, said.count("held.callback("),
                         "a tenant was added to the shutdown without the budget being divided "
                         "again — every share here is now larger than the gateway's whole window")

    def test_each_share_is_still_enough_to_stop_a_child_with(self):
        # Divided too far is the same failure from the other side: a share below what either tenant
        # will spend per child is a budget that stopped bounding anything.
        each = host.STOPPING_WITHIN / host.STOPPING_SHARES
        self.assertGreater(each, firing.STOPPING_LEAST)
        self.assertGreater(each, hosting.STOPPING_LEAST)

    def test_a_request_to_stop_is_not_something_a_generic_guard_can_swallow(self):
        # `Stopped` is raised from a signal handler, so it lands wherever the interpreter happens to
        # be — including inside `schedules.firing`, whose whole contract is that no ordinary failure
        # may end a gateway and which therefore guards its work with `suppress(Exception)`. Derived
        # from `Exception` the request was eaten there, the signal was spent, and the gateway went
        # back to sleep unstoppable short of a second `SIGTERM` — inside a twenty-five second window
        # after which launchd `SIGKILL`s it. This is why `KeyboardInterrupt` is a `BaseException`.
        self.assertFalse(issubclass(host.Stopped, Exception),
                         "a stop a generic `except Exception` can swallow is a gateway that cannot "
                         "be stopped from inside a guarded call")
        with self.assertRaises(host.Stopped):
            with contextlib.suppress(Exception):
                raise host.Stopped("asked to stop")


class TheProcessNeverTalksToItsSupervisor(unittest.TestCase):
    """`host` may not import `job`, and that is checked rather than remembered."""

    def test_it_does_not_import_the_job_layer(self):
        # A gateway that could bootstrap, boot out or kick its own job could restart itself, and the
        # decision to keep a gateway running would sit inside the thing being kept running. It is
        # also what lets every case above run with launchd nowhere near it.
        said = (support.CHECKOUT / "src" / "rundesk" / "gateways" / "host.py").read_text()
        for one in ("import job", "gateways.job", "gateways import job"):
            with self.subTest(reaching=one):
                self.assertNotIn(one, said)

    def test_it_never_reaches_for_launchctl_either(self):
        said = (support.CHECKOUT / "src" / "rundesk" / "gateways" / "host.py").read_text()
        self.assertNotIn("launchctl", said)


if __name__ == "__main__":
    unittest.main()
