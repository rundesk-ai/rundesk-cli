"""Admission receipts describe recording, never the result of a provider turn."""

import io
import json
import os
import signal
import threading
import unittest
from types import SimpleNamespace
from unittest import mock

import support
from rundesk.agents import directory
from rundesk.channels import arriving, hosting, kept


class ReceivingOnAChannel(support.Isolated):
    """One hosted channel whose adapter pipe is a string. Holds no case of its own."""

    def setUp(self):
        super().setUp()
        self.agent = "cole"
        directory.made(self.agent, "claude")
        self.pipe = io.StringIO()
        self.one = hosting.Running(
            kind="test", pid=0, talking=SimpleNamespace(stdin=self.pipe), listening=None,
            since=0, mine=True, awaiting={}, posted={}, refused={}, saying=threading.Lock())
        self.where = directory.logs(self.agent)
        self.admitting = kept.Admitting(("m1",), ())

    def receive(self, **changes):
        record = {"say": "arrived", "receipt": "r1", "conversation": "t1", "user": "m1",
                  "text": "hello", "external_id": "1.1"}
        record.update(changes)
        hosting._arrived(self.agent, self.where, self.one, record, self.admitting)

    def receipts(self):
        return [one for one in map(json.loads, self.pipe.getvalue().splitlines())
                if one["do"] == "received"]


class RecordingReceipts(ReceivingOnAChannel):

    def test_a_committed_message_is_accepted_before_the_answer_starts(self):
        def answer(*_args):
            self.assertEqual([{"do": "received", "receipt": "r1", "outcome": "accepted"}],
                             self.receipts())
            conversation = arriving.conversations(self.agent)[0]["id"]
            self.assertEqual(1, len(arriving.messages(self.agent, conversation)))
            return True

        answering = SimpleNamespace(busy=lambda *_args: False, answer=answer)
        self.one = self.one._replace(answering=answering)
        self.receive()

    def test_redelivery_is_duplicate_and_the_message_is_stored_once(self):
        self.receive()
        self.receive()
        self.assertEqual(["accepted", "duplicate"],
                         [one["outcome"] for one in self.receipts()])
        conversation = arriving.conversations(self.agent)[0]["id"]
        self.assertEqual(1, len(arriving.messages(self.agent, conversation)))

    def test_an_unadmitted_message_is_refused_without_being_recorded(self):
        self.receive(user="m2")
        self.assertEqual("refused", self.receipts()[0]["outcome"])
        self.assertEqual([], arriving.conversations(self.agent))

    def test_missing_conversation_and_empty_message_are_invalid(self):
        self.receive(conversation="")
        self.receive(text="", attachments=[])
        self.assertEqual(["invalid", "invalid"],
                         [one["outcome"] for one in self.receipts()])
        self.assertEqual([], arriving.conversations(self.agent))

    def test_files_only_with_no_file_taken_in_is_empty(self):
        with mock.patch.object(hosting, "_taken_in", return_value=[]):
            self.receive(text="", attachments=[{"name": "missing.txt"}])
        self.assertEqual("empty", self.receipts()[0]["outcome"])
        self.assertEqual([], arriving.conversations(self.agent))

    def test_a_recording_exception_produces_no_receipt(self):
        with mock.patch.object(arriving, "recorded", side_effect=OSError("cannot record")):
            with self.assertRaises(OSError):
                self.receive()
        self.assertEqual([], self.receipts())

    def test_a_file_exception_produces_no_receipt(self):
        with mock.patch.object(hosting, "_taken_in", side_effect=OSError("cannot land")):
            with self.assertRaises(OSError):
                self.receive(attachments=[{"name": "report.txt"}])
        self.assertEqual([], self.receipts())

    def test_unsupplied_and_invalid_receipt_tokens_leave_legacy_output_alone(self):
        for receipt in (None, "", 1, [], {}, "x" * 65):
            with self.subTest(receipt=receipt):
                self.receive(receipt=receipt)
        self.assertEqual([], self.receipts())

    def test_a_receipt_at_the_limit_is_preserved_whole(self):
        self.receive(receipt="x" * 64)
        self.assertEqual("x" * 64, self.receipts()[0]["receipt"])


class TestOnlyKillPoint(ReceivingOnAChannel):
    """The gateway's F4 point: inert unless `RUNDESK_TEST_KILL_AT` names it, and then only once."""

    def setUp(self):
        super().setUp()
        self.marker = hosting.at(self.agent, "test") / "test-kill-gateway-after-record.fired"
        self.marker.parent.mkdir(parents=True, exist_ok=True)
        self.answered = []
        self.one = self.one._replace(answering=SimpleNamespace(
            busy=lambda *_args: False, answer=lambda *args: self.answered.append(args) or True))

    def kill_at(self, value):
        """The environment with `KILL_AT` set to `value`, or with it absent when `value` is None."""
        patched = mock.patch.dict(os.environ)
        patched.start()
        self.addCleanup(patched.stop)
        os.environ.pop(hosting.KILL_AT, None)
        if value is not None:
            os.environ[hosting.KILL_AT] = value
        return patched

    def test_unset_or_another_point_changes_nothing(self):
        for value in (None, "", "adapter-after-claim", "gateway-after-record "):
            with self.subTest(value=value), mock.patch("os.kill") as kill:
                self.kill_at(value)
                self.receive(receipt=f"r-{value}", external_id=f"{len(self.answered) + 1}.1")
                kill.assert_not_called()
                self.assertFalse(self.marker.exists())
        self.assertEqual(4, len(self.answered))
        self.assertEqual(["accepted"] * 4, [one["outcome"] for one in self.receipts()])

    def test_named_point_kills_after_the_receipt_and_before_the_turn_once(self):
        def killed(pid, sent):
            self.assertEqual((os.getpid(), signal.SIGKILL), (pid, sent))
            self.assertTrue(self.marker.exists())
            self.assertEqual(["accepted"], [one["outcome"] for one in self.receipts()])
            self.assertEqual([], self.answered)
            raise SystemExit("killed")

        self.kill_at(hosting.AFTER_RECORD)
        with mock.patch("os.kill", side_effect=killed) as kill:
            with self.assertRaises(SystemExit):
                self.receive()
            self.receive(receipt="r2", external_id="2.1")
        self.assertEqual(1, kill.call_count)
        self.assertEqual(1, len(self.answered))

    def sweep(self):
        """One pass of the gateway's own pending sweep over this connected channel."""
        connected = threading.Event()
        connected.set()
        watching = hosting.Watching({"test": SimpleNamespace(connected=connected)}, {}, {})
        hosting._answered_pending(self.agent, watching, self.one.answering)

    def test_the_sweep_starts_no_turn_between_the_receipt_and_the_kill(self):
        swept = []
        receipt = hosting._received

        def received_then_swept(*args):
            receipt(*args)
            self.sweep()
            swept.append(len(self.answered))

        def killed(*_args):
            raise SystemExit("killed")

        self.kill_at(hosting.AFTER_RECORD)
        with mock.patch.object(hosting, "_received", side_effect=received_then_swept), \
                mock.patch("os.kill", side_effect=killed):
            with self.assertRaises(SystemExit):
                self.receive()
        self.assertEqual([0], swept)
        self.assertEqual([], self.answered)
        self.assertEqual(["accepted"], [one["outcome"] for one in self.receipts()])

    def test_the_sweep_recovers_the_message_once_the_point_fired_or_is_unset(self):
        arriving.recorded(self.agent, "test", "t1", "m1", "hello", "1.1")
        self.kill_at(hosting.AFTER_RECORD)
        self.sweep()
        self.assertEqual([], self.answered)
        self.marker.touch()
        self.sweep()
        self.assertEqual(1, len(self.answered))
        self.marker.unlink()
        self.kill_at(None)
        arriving.recorded(self.agent, "test", "t2", "m1", "again", "2.1")
        self.sweep()
        # The stub claims nothing, so the unclaimed first message is found again beside the second.
        self.assertEqual(["t1", "t1", "t2"], [one[2] for one in self.answered])

    def test_a_sweep_right_after_the_marker_is_made_starts_no_turn(self):
        swept = []

        def killed(*_args):
            # The marker is closed and the kill not yet delivered: the instant a sweep that read
            # only the marker would admit the channel and start the turn the kill must leave.
            self.assertTrue(self.marker.exists())
            self.sweep()
            swept.append(len(self.answered))
            raise SystemExit("killed")

        self.kill_at(hosting.AFTER_RECORD)
        with mock.patch("os.kill", side_effect=killed):
            with self.assertRaises(SystemExit):
                self.receive()
        self.assertEqual([0], swept)
        self.assertEqual([], self.answered)

    def test_after_a_marker_that_cannot_be_made_the_sweep_recovers_an_older_message(self):
        arriving.recorded(self.agent, "test", "t-old", "m1", "earlier", "1.1")
        self.marker.parent.rmdir()
        self.kill_at(hosting.AFTER_RECORD)
        with mock.patch("os.kill") as kill:
            self.receive(receipt="r2", conversation="t-new", external_id="2.1")
            self.sweep()
        kill.assert_not_called()
        self.assertIn("t-old", [one[2] for one in self.answered])

    def test_a_redelivery_never_fires_the_point(self):
        self.receive()
        self.kill_at(hosting.AFTER_RECORD)
        with mock.patch("os.kill") as kill:
            self.receive()
        kill.assert_not_called()
        self.assertFalse(self.marker.exists())
        self.assertEqual(["accepted", "duplicate"], [one["outcome"] for one in self.receipts()])

    def test_a_marker_that_cannot_be_made_leaves_the_point_inert(self):
        self.marker.parent.rmdir()
        self.kill_at(hosting.AFTER_RECORD)
        with mock.patch("os.kill") as kill:
            self.receive()
        kill.assert_not_called()
        self.assertEqual(1, len(self.answered))

    def test_only_a_set_kill_point_is_handed_to_the_adapter(self):
        row = {"kind": "test", "settings": "{}", "allowed": "[]"}
        self.kill_at(None)
        os.environ["RUNDESK_TEST_OTHER"] = "x"
        self.assertNotIn(hosting.KILL_AT, hosting._the_environment(self.agent, "test", row))
        os.environ[hosting.KILL_AT] = ""
        self.assertNotIn(hosting.KILL_AT, hosting._the_environment(self.agent, "test", row))
        os.environ[hosting.KILL_AT] = "adapter-after-claim"
        built = hosting._the_environment(self.agent, "test", row)
        self.assertEqual("adapter-after-claim", built[hosting.KILL_AT])
        self.assertNotIn("RUNDESK_TEST_OTHER", built)


if __name__ == "__main__":
    unittest.main()
