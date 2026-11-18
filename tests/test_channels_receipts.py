"""Admission receipts describe recording, never the result of a provider turn."""

import io
import json
import threading
import unittest
from types import SimpleNamespace
from unittest import mock

import support
from rundesk.agents import directory
from rundesk.channels import arriving, hosting, kept


class RecordingReceipts(support.Isolated):

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


if __name__ == "__main__":
    unittest.main()
