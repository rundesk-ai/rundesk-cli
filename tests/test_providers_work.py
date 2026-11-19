"""Correlated work recovers across adapter replacement without inventing message outcomes."""

import io
import json
import subprocess
import sys
import threading
import unittest
from types import SimpleNamespace
from unittest import mock

import support
from rundesk.agents import directory
from rundesk.channels import arriving, hosting
from rundesk.channels import kept as channels_kept
from rundesk.core import paths
from rundesk.providers import adapters, answering, instructions, kept, protocol, turns
from rundesk.utils import locking


class WithWork(support.Isolated):
    def setUp(self):
        super().setUp()
        self.agent = "cole"
        directory.made(self.agent, support.A_STAND_IN)
        self.where = directory.logs(self.agent)
        self.pipe = io.StringIO()
        self.one = hosting.Running(
            kind="test", pid=0, talking=SimpleNamespace(stdin=self.pipe), listening=None,
            since=0, mine=True, awaiting={}, posted={}, refused={}, saying=threading.Lock())
        self.hosted = hosting.Watching({"test": self.one}, {}, {})
        self.owner = answering.OnAChannel(self.where, lambda: self.hosted)
        self.landed = arriving.recorded(
            self.agent, "test", "room", "member", "hello", external_id="m1")
        self.addCleanup(mock.patch.stopall)
        mock.patch.object(answering.channels_adapters, "capabilities", return_value={"work": True}).start()
        self.delivery = mock.patch.object(self.owner, "_delivered", return_value="").start()
        answering.inherited_work(self.agent)

    def said(self):
        return [json.loads(line) for line in self.pipe.getvalue().splitlines()]

    def ended(self):
        return [row for row in self.said() if "ended" in row]

    def answer(self):
        self.owner._answered(self.agent, "test", "room", "hello", "m1", self.landed)

    def snapshot(self, previous=None, force=True):
        return self.owner.snapshot(self.agent, "test", self.one, previous, force)

    def turn(self):
        return kept.add_turn(self.agent, {
            "conversation_id": self.landed.conversation, "provider_name": support.A_STAND_IN,
            "access_mode": protocol.ACCESS_WORK, "provider_capabilities": "{}"})

    def external_claim(self):
        claim = adapters.lock_of(self.agent, self.landed.conversation)
        claim.parent.mkdir(parents=True, exist_ok=True)
        child = subprocess.Popen([
            sys.executable, "-c",
            "import fcntl,sys; f=open(sys.argv[1], 'a'); fcntl.flock(f, fcntl.LOCK_EX); "
            "print('held',flush=True); sys.stdin.read()", str(claim)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        def stop():
            if child.poll() is None:
                child.communicate(timeout=5)
            for pipe in (child.stdin, child.stdout, child.stderr):
                pipe.close()
        self.addCleanup(stop)
        self.assertEqual("held\n", child.stdout.readline())
        return child


class CorrelatedProducers(WithWork):
    def test_answer_terminal_and_ended_share_work_and_original_message(self):
        with mock.patch.object(turns, "run", return_value=SimpleNamespace(turn_status=kept.DONE)):
            self.answer()
        working, terminal, ended = self.said()
        self.assertEqual("m1", working["for"])
        self.assertEqual(working["work"], terminal["work"])
        self.assertEqual(working["work"], ended["work"])
        self.assertEqual(("answered", "m1", "done"),
                         (ended["ended"], ended["marked"], ended["state"]))
        self.snapshot()
        self.assertEqual([], self.said()[-1]["open"])

    def test_busy_retries_reuse_work_and_end_pending_without_a_mark(self):
        with mock.patch.object(turns, "run", side_effect=turns.Busy), \
                mock.patch.object(turns, "also_say", return_value=False), \
                mock.patch.object(answering.time, "sleep"):
            self.answer()
        states = [row for row in self.said() if row["do"] == "state"]
        self.assertEqual(3, len(states))
        self.assertEqual(1, len({row["work"] for row in states}))
        self.assertEqual(("pending", None, None),
                         tuple(self.ended()[0][key] for key in ("ended", "marked", "state")))

    def test_joined_producer_ends_without_a_message_mark(self):
        def joined(_agent, _conversation, _body, _messages, admitted):
            admitted.accepted()
            return True
        with mock.patch.object(turns, "run", side_effect=turns.Busy), \
                mock.patch.object(turns, "also_say", side_effect=joined):
            self.answer()
        self.assertEqual(("joined", None, None),
                         tuple(self.ended()[0][key] for key in ("ended", "marked", "state")))

    def test_admission_refusal_ends_pending_and_does_not_fail_the_message(self):
        with mock.patch.object(turns, "run", side_effect=locking.Stuck("busy")), \
                mock.patch.object(turns, "running_here", return_value=False):
            self.answer()
        self.assertNotIn("external_id", self.said()[-2])
        self.assertEqual(("pending", None, None),
                         tuple(self.ended()[0][key] for key in ("ended", "marked", "state")))

    def test_exception_ended_preserves_the_named_failure_even_if_terminal_is_lost(self):
        with mock.patch.object(turns, "run", side_effect=OSError("provider gone")):
            self.answer()
        self.assertEqual(("failed", "m1", "failed"),
                         tuple(self.ended()[0][key] for key in ("ended", "marked", "state")))

    def test_legacy_adapter_gets_correlation_but_no_work_records(self):
        with mock.patch.object(answering.channels_adapters, "capabilities", return_value={}), \
                mock.patch.object(turns, "run", return_value=SimpleNamespace(turn_status=kept.DONE)):
            self.answer()
            self.snapshot()
        self.assertEqual(["state", "state"], [row["do"] for row in self.said()])
        self.assertTrue(all(row.get("work") for row in self.said()))

    def test_work_opened_without_an_adapter_is_recovered_with_metadata(self):
        self.hosted.running.clear()
        work = answering._Work(self.owner, self.agent, "test", "room", "m1")
        work.start()
        try:
            self.hosted.running["test"] = self.one
            self.snapshot()
            self.assertEqual([work.metadata], self.said()[-1]["open"])
            self.assertEqual("room", self.said()[-1]["open"][0]["place"])
            self.assertTrue(self.said()[-1]["open"][0]["began"])
        finally:
            work.end()

    def test_delegation_terminal_has_work_but_never_marks_a_human_message(self):
        owner = answering.OnADelegation(self.where, lambda: self.hosted)

        def run(_request, **kwargs):
            kwargs["admitted"]()
            return SimpleNamespace(turn_status=kept.DONE)
        with mock.patch.object(turns, "run", side_effect=run), \
                mock.patch.object(owner, "_out_loud"):
            owner._take(self.agent, self.landed.conversation, "review",
                        instructions.USER_TO_AGENT, None, None, "review")
        working, terminal, ended = self.said()
        self.assertEqual(working["work"], terminal["work"])
        self.assertEqual(working["work"], ended["work"])
        self.assertEqual(("answered", None, None, None),
                         tuple(ended[key] for key in ("ended", "marked", "state", "for")))

    def test_continuation_terminal_and_ended_are_correlated_without_a_human_mark(self):
        owner = answering.OnAContinuation(self.where, lambda: self.hosted)
        row = SimpleNamespace(conversation=self.landed.conversation, provider="test",
                              provider_alias=None, origin_instructions="test")

        def run(_request, **kwargs):
            kwargs["admitted"]()
            return SimpleNamespace(turn_status=kept.DONE)
        with mock.patch.object(answering.continuations, "one", return_value=row), \
                mock.patch.object(answering.continuations, "prompt", return_value="resume"), \
                mock.patch.object(answering.continuations, "delivered"), \
                mock.patch.object(turns, "run_if", side_effect=run), \
                mock.patch.object(owner, "_delivered", return_value=""):
            owner._resumed(self.agent, 1)
        working, terminal, ended = self.said()
        self.assertEqual(working["work"], terminal["work"])
        self.assertEqual(working["work"], ended["work"])
        self.assertEqual(("answered", None, None),
                         tuple(ended[key] for key in ("ended", "marked", "state")))

    def test_stop_mark_has_no_producer_work(self):
        hosting.marked(self.agent, self.where, self.hosted, "test", "room", answering.STOPPED, "m1")
        self.assertNotIn("work", self.said()[0])

    def test_delegation_admitted_without_adapter_emits_terminal_after_replacement(self):
        owner = answering.OnADelegation(self.where, lambda: self.hosted)
        self.hosted.running.clear()

        def run(_request, **kwargs):
            kwargs["admitted"]()
            self.hosted.running["test"] = self.one
            self.snapshot()
            return SimpleNamespace(turn_status=kept.DONE)

        with mock.patch.object(turns, "run", side_effect=run), \
                mock.patch.object(owner, "_out_loud"):
            owner._take(self.agent, self.landed.conversation, "review",
                        instructions.USER_TO_AGENT, None, None, "review")
        snapshot, terminal, ended = self.said()
        self.assertEqual("done", terminal["state"])
        self.assertEqual(snapshot["open"][0]["work"], terminal["work"])
        self.assertEqual(terminal["work"], ended["work"])
        self.assertNotIn("external_id", terminal)
        self.assertIsNone(ended["marked"])
        self.assertIsNone(ended["state"])

    def test_continuation_admitted_without_adapter_emits_terminal_after_replacement(self):
        owner = answering.OnAContinuation(self.where, lambda: self.hosted)
        row = SimpleNamespace(conversation=self.landed.conversation, provider="test",
                              provider_alias=None, origin_instructions="test")
        self.hosted.running.clear()

        def run(_request, **kwargs):
            kwargs["admitted"]()
            self.hosted.running["test"] = self.one
            self.snapshot()
            return SimpleNamespace(turn_status=kept.DONE)

        with mock.patch.object(answering.continuations, "one", return_value=row), \
                mock.patch.object(answering.continuations, "prompt", return_value="resume"), \
                mock.patch.object(answering.continuations, "delivered"), \
                mock.patch.object(turns, "run_if", side_effect=run), \
                mock.patch.object(owner, "_delivered", return_value=""):
            owner._resumed(self.agent, 1)
        snapshot, terminal, ended = self.said()
        self.assertEqual("done", terminal["state"])
        self.assertEqual(snapshot["open"][0]["work"], terminal["work"])
        self.assertEqual(terminal["work"], ended["work"])
        self.assertNotIn("external_id", terminal)
        self.assertIsNone(ended["marked"])
        self.assertIsNone(ended["state"])


class RecoveringWork(WithWork):
    def test_ready_between_force_read_and_clear_still_gets_a_forced_snapshot(self):
        sampled = threading.Event()
        release = threading.Event()
        forced_snapshot = threading.Event()
        ready_done = threading.Event()

        class PausingEvent(threading.Event):
            def is_set(self):
                value = super().is_set()
                if not sampled.is_set():
                    sampled.set()
                    if not release.wait(5):
                        raise AssertionError("force read was not released")
                return value

        one = self.one._replace(
            snapshot_requested=threading.Event(), snapshot_forced=PausingEvent(),
            snapshot_stopped=threading.Event(), snapshot_lock=threading.Lock(), answering=self.owner)

        def snapshot(_agent, _kind, _one, _previous, force):
            if force:
                forced_snapshot.set()
            return []

        def ready():
            hosting._heard(self.agent, self.where, one, '{"say":"ready"}',
                           channels_kept.Admitting((), ()))
            ready_done.set()

        with mock.patch.object(self.owner, "snapshot", side_effect=snapshot):
            worker = threading.Thread(target=hosting._snapshots, args=(self.agent, self.where, one))
            reader = threading.Thread(target=ready)
            one.snapshot_requested.set()
            worker.start()
            try:
                self.assertTrue(sampled.wait(5))
                reader.start()
                # In the fault build, ready completes while the old false read is paused.
                # With atomic consumption it waits, then publishes the next forced request.
                ready_done.wait(0.05)
                release.set()
                self.assertTrue(forced_snapshot.wait(5))
            finally:
                release.set()
                one.snapshot_stopped.set()
                one.snapshot_requested.set()
                worker.join(5)
                if reader.ident is not None:
                    reader.join(5)
            self.assertFalse(worker.is_alive())
            self.assertFalse(reader.is_alive())

    def test_killed_owner_leaves_surviving_child_classed_elsewhere_until_claim_release(self):
        inherited = self.turn()
        answering.inherited_work(self.agent)
        claim = adapters.lock_of(self.agent, self.landed.conversation)
        claim.parent.mkdir(parents=True, exist_ok=True)
        owner = subprocess.Popen([
            sys.executable, "-c", '''import fcntl, signal, subprocess, sys
held = open(sys.argv[1], 'a')
fcntl.flock(held, fcntl.LOCK_EX)
subprocess.Popen([sys.executable, '-c',
                  'import sys; print("child ready", flush=True); sys.stdin.read()'],
                 pass_fds=(held.fileno(),))
signal.pause()
''', str(claim)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True)

        def stop():
            if owner.poll() is None:
                owner.kill()
            owner.stdin.close()
            owner.wait(timeout=5)
            self.assertTrue(support.waited_until(
                lambda: turns.standing(self.agent, self.landed.conversation) is False, 5))
            owner.stdout.close()
            owner.stderr.close()

        self.addCleanup(stop)
        self.assertEqual("child ready\n", owner.stdout.readline())
        owner.kill()
        self.assertLess(owner.wait(timeout=5), 0)
        previous = self.snapshot()
        self.assertEqual("elsewhere", self.said()[-1]["inherited"][0]["activity"])
        self.assertEqual(0, turns.settle_abandoned(self.agent))
        owner.stdin.close()
        self.assertTrue(support.waited_until(
            lambda: turns.standing(self.agent, self.landed.conversation) is False, 5))
        previous = self.snapshot(previous, force=False)
        self.assertEqual("free", self.said()[-1]["inherited"][0]["activity"])
        self.assertEqual(inherited, self.said()[-1]["inherited"][0]["turns"][0]["turn"])
        self.assertEqual(1, turns.settle_abandoned(self.agent))
        self.snapshot(previous, force=False)
        self.assertEqual([], self.said()[-1]["inherited"])

    def test_ready_from_a_real_adapter_replays_work_opened_while_it_was_down(self):
        self.hosted.running.clear()
        work = answering._Work(self.owner, self.agent, "test", "room", "m1")
        adapter = self.home / "app" / "src" / "channels" / "test"
        adapter.parent.mkdir(parents=True)
        told = self.home / "told.jsonl"
        adapter.write_text('''#!/usr/bin/env python3
import json, os, sys
settings = json.loads(os.environ['RUNDESK_SETTINGS'])
print('{"say":"ready"}', flush=True)
for line in sys.stdin:
    with open(settings['told'], 'a') as out:
        out.write(line)
    if json.loads(line).get('do') == 'stop':
        break
''')
        adapter.chmod(0o755)
        self.assertEqual(adapter.parent.parent, paths.code())
        channels_kept.added(self.agent, "test", {
            "allowed": '["member"]', "describes": "Synthetic channel",
            "settings": json.dumps({"told": str(told)})})
        try:
            work.start()
            hosting._started(self.agent, self.where, "test", self.hosted, self.owner)
            self.assertTrue(support.waited_until(lambda: told.exists() and told.stat().st_size > 0, 5))
            snapshot = json.loads(told.read_text().splitlines()[0])
            self.assertEqual("work", snapshot["do"])
            self.assertEqual([work.metadata], snapshot["open"])
        finally:
            work.end()
            hosting.stopping(self.agent, self.where, self.hosted, 5)

    def test_snapshot_and_registration_are_ordered_as_whole_operations(self):
        snapshot_written = threading.Event()
        release = threading.Event()
        start_attempted = threading.Event()
        start_done = threading.Event()
        work = answering._Work(self.owner, self.agent, "test", "room", "m1")
        send = hosting.work_record

        def paused(where, one, record):
            result = send(where, one, record)
            if "open" in record:
                snapshot_written.set()
                self.assertTrue(release.wait(5))
            return result

        def start():
            start_attempted.set()
            work.start()
            start_done.set()

        with mock.patch.object(hosting, "work_record", side_effect=paused):
            sampling = threading.Thread(target=self.snapshot)
            starting = threading.Thread(target=start)
            sampling.start()
            try:
                self.assertTrue(snapshot_written.wait(5))
                starting.start()
                self.assertTrue(start_attempted.wait(5))
                self.assertFalse(start_done.wait(0.05))
            finally:
                release.set()
                sampling.join(5)
                if starting.ident is not None:
                    starting.join(5)
        try:
            self.assertFalse(starting.is_alive())
            self.assertEqual(["work", "state"], [row["do"] for row in self.said()])
            self.snapshot()
            self.assertEqual([work.metadata], self.said()[-1]["open"])
        finally:
            work.end()

    def test_failed_ready_snapshot_is_retried_even_when_inherited_work_is_unchanged(self):
        previous = self.snapshot()
        with mock.patch.object(hosting, "work_record", return_value=False):
            with self.assertRaises(OSError):
                self.snapshot(previous, force=True)

    def test_unreadable_records_never_emit_an_empty_inherited_snapshot(self):
        self.turn()
        answering.inherited_work(self.agent)
        with mock.patch.object(answering.records, "reading", side_effect=OSError("unreadable")):
            with self.assertRaises(OSError):
                self.snapshot()
        self.assertEqual([], self.said())

    def test_only_inherited_unfinished_turns_are_grouped_and_linked_to_first_message(self):
        first = self.turn()
        second = self.turn()
        arriving.handled_by_turn(self.agent, self.landed.conversation, (self.landed.message,), first)
        answering.inherited_work(self.agent)
        fresh = self.turn()
        self.snapshot()
        inherited = self.said()[-1]["inherited"]
        self.assertEqual(1, len(inherited))
        self.assertEqual("free", inherited[0]["activity"])
        self.assertEqual([first, second], [row["turn"] for row in inherited[0]["turns"]])
        self.assertEqual("m1", inherited[0]["turns"][0]["for"])
        self.assertNotIn(fresh, [row["turn"] for row in inherited[0]["turns"]])
        kept.finish_turn(self.agent, first, kept.DONE)
        self.snapshot()
        self.assertEqual([second], [row["turn"] for row in self.said()[-1]["inherited"][0]["turns"]])

    def test_unknown_claim_is_reported_without_omitting_the_turn(self):
        inherited = self.turn()
        answering.inherited_work(self.agent)
        with mock.patch.object(turns, "standing", return_value=None):
            self.snapshot()
        group = self.said()[-1]["inherited"][0]
        self.assertEqual("unknown", group["activity"])
        self.assertEqual(inherited, group["turns"][0]["turn"])

    def test_here_precedes_the_claim_probe_even_before_a_new_row_exists(self):
        self.turn()
        answering.inherited_work(self.agent)
        with mock.patch.object(turns, "running_here", return_value=True), \
                mock.patch.object(turns, "standing", side_effect=AssertionError("must not probe")):
            self.snapshot()
        self.assertEqual("here", self.said()[-1]["inherited"][0]["activity"])

    def test_external_claim_release_keeps_row_listed_until_it_is_settled(self):
        inherited = self.turn()
        answering.inherited_work(self.agent)
        child = self.external_claim()
        previous = self.snapshot()
        self.assertEqual("elsewhere", self.said()[-1]["inherited"][0]["activity"])
        child.communicate(timeout=5)
        previous = self.snapshot(previous, force=False)
        self.assertEqual("free", self.said()[-1]["inherited"][0]["activity"])
        self.assertEqual(inherited, self.said()[-1]["inherited"][0]["turns"][0]["turn"])
        turns.settle_abandoned(self.agent)
        self.snapshot(previous, force=False)
        self.assertEqual([], self.said()[-1]["inherited"])

    def test_new_external_owner_does_not_make_an_inherited_turn_its_provider(self):
        first = self.turn()
        answering.inherited_work(self.agent)
        old = self.external_claim()
        old.communicate(timeout=5)
        newer = self.external_claim()
        second = self.turn()
        self.snapshot()
        group = self.said()[-1]["inherited"][0]
        self.assertEqual("elsewhere", group["activity"])
        self.assertEqual([first], [row["turn"] for row in group["turns"]])
        turns.settle_abandoned(self.agent)
        self.assertEqual(kept.WORKING, kept.get_turn(self.agent, first)["turn_status"])
        self.assertEqual(kept.WORKING, kept.get_turn(self.agent, second)["turn_status"])
        newer.communicate(timeout=5)

    def test_repeated_loop_sample_is_quiet_but_ready_always_replays(self):
        previous = self.snapshot()
        self.snapshot(previous, force=False)
        self.assertEqual(1, len(self.said()))
        self.snapshot(previous, force=True)
        self.assertEqual(2, len(self.said()))

    def test_total_snapshot_entries_are_bounded_and_truncation_is_explicit(self):
        works = [answering._Work(self.owner, self.agent, "test", "room") for _ in range(201)]
        try:
            for work in works:
                work.start()
            self.snapshot()
            snapshot = self.said()[-1]
            self.assertTrue(snapshot["truncated"])
            self.assertEqual(200, len(snapshot["open"]))
        finally:
            for work in works:
                work.end()

    def test_snapshot_cannot_reopen_work_paused_between_ended_and_removal(self):
        work = answering._Work(self.owner, self.agent, "test", "room", "m1")
        work.start()
        ended_written = threading.Event()
        release = threading.Event()
        snapshot_started = threading.Event()
        snapshot_done = threading.Event()
        send = hosting.work_record

        def paused(where, one, record):
            result = send(where, one, record)
            if "ended" in record:
                ended_written.set()
                self.assertTrue(release.wait(5))
            return result

        def snapshot():
            snapshot_started.set()
            self.snapshot()
            snapshot_done.set()
        with mock.patch.object(hosting, "work_record", side_effect=paused):
            ending = threading.Thread(target=work.end)
            sampling = threading.Thread(target=snapshot)
            ending.start()
            try:
                self.assertTrue(ended_written.wait(5))
                sampling.start()
                self.assertTrue(snapshot_started.wait(5))
                self.assertFalse(snapshot_done.wait(0.05))
            finally:
                release.set()
                ending.join(5)
                if sampling.ident is not None:
                    sampling.join(5)
            self.assertFalse(ending.is_alive())
            self.assertFalse(sampling.is_alive())
        self.assertEqual([], self.said()[-1]["open"])

    def test_ready_never_runs_snapshot_sampling_on_the_stdout_reader(self):
        requested = threading.Event()
        one = self.one._replace(snapshot_requested=requested, snapshot_forced=threading.Event(),
                                snapshot_stopped=threading.Event(), answering=self.owner)
        with mock.patch.object(self.owner, "snapshot", side_effect=AssertionError("reader sampled")):
            hosting._heard(self.agent, self.where, one, '{"say":"ready"}', channels_kept.Admitting((), ()))
        self.assertTrue(requested.is_set())
        self.assertTrue(one.snapshot_forced.is_set())

    def test_snapshot_worker_can_block_while_the_reader_handles_ready(self):
        entered = threading.Event()
        release = threading.Event()
        requested = threading.Event()
        one = self.one._replace(snapshot_requested=requested, snapshot_forced=threading.Event(),
                                snapshot_stopped=threading.Event(), answering=self.owner)

        def snapshot(*_args):
            entered.set()
            release.wait(5)
            return []
        with mock.patch.object(self.owner, "snapshot", side_effect=snapshot):
            worker = threading.Thread(target=hosting._snapshots, args=(self.agent, self.where, one))
            worker.start()
            try:
                hosting._heard(self.agent, self.where, one, '{"say":"ready"}', channels_kept.Admitting((), ()))
                self.assertTrue(entered.wait(5))
                hosting._heard(self.agent, self.where, one, '{"say":"ready"}', channels_kept.Admitting((), ()))
                self.assertTrue(one.snapshot_forced.is_set())
            finally:
                one.snapshot_stopped.set()
                requested.set()
                release.set()
                worker.join(5)
            self.assertFalse(worker.is_alive())


if __name__ == "__main__":
    unittest.main()
