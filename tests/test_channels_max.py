"""The isolated Max core: durable ordering and independently progressing pipes/polls."""

import hashlib
import importlib.machinery
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

import support


def adapter():
    path = support.CHECKOUT / "src" / "channels" / "max"
    loader = importlib.machinery.SourceFileLoader("max_channel", str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class JournalRecovery(support.Isolated):
    def setUp(self):
        super().setUp()
        self.max = adapter()
        self.at = self.home / "channel" / "journal"
        self.notes = []

    def journal(self, current=0, applied=0):
        one = self.max.Journal(self.at, current, applied, self.notes.append)
        self.addCleanup(one.close)
        return one

    def test_pending_nonce_and_basis_survive_restart(self):
        one = self.journal(7)
        header = dict(one.header)
        one.close()
        again = self.journal(99)
        self.assertEqual(header, again.header)
        self.assertEqual(7, again.header["supersede"])
        self.assertIsNone(again.header["stream"])

    def test_records_recover_in_order_with_original_delivery_id(self):
        one = self.journal()
        one.allocated(1)
        one.append({"do": "deliver", "id": "piece-0", "text": "  hello\n"})
        one.append({"do": "state", "state": "done"})
        one.close()
        again = self.journal(1, 1)
        self.assertEqual([1, 2], [row["seq"] for row in again.records])
        self.assertEqual("piece-0", again.records[0]["id"])
        self.assertEqual("  hello\n", again.records[0]["text"])
        self.assertEqual(3, again.append({"do": "answered", "text": "all"})["seq"])

    def test_missing_records_continue_at_server_cursor(self):
        one = self.journal()
        one.allocated(1)
        one.close()
        again = self.journal(1, 8)
        self.assertEqual(9, again.append({"do": "state"})["seq"])

    def test_damage_is_preserved_and_reported_before_new_allocation(self):
        self.at.mkdir(parents=True)
        (self.at / "stream.json").write_text("{torn")
        (self.at / "records.jsonl").write_text('{"seq":1,"do":"state"}\n')
        one = self.journal(4)
        damaged = list(self.at.glob("damaged-*"))
        self.assertEqual(1, len(damaged))
        self.assertEqual("{torn", (damaged[0] / "stream.json").read_text())
        self.assertIn("1", self.notes[0])
        self.assertEqual(4, one.header["supersede"])

    def test_two_writers_cannot_open_one_journal(self):
        self.journal()
        with self.assertRaises(BlockingIOError):
            self.journal()

    def test_header_install_is_complete_json(self):
        one = self.journal(2)
        one.allocated(3)
        self.assertEqual(one.header, json.loads((self.at / "stream.json").read_text()))
        self.assertEqual([], list(self.at.glob(".stream-*")))

    def test_unreadable_header_preserves_files_and_releases_lock(self):
        one = self.journal()
        one.close()
        before = (self.at / "stream.json").read_bytes()
        with mock.patch.object(self.max.Path, "read_text", side_effect=PermissionError(13, "denied")):
            with self.assertRaises(PermissionError):
                self.journal()
        self.assertEqual(before, (self.at / "stream.json").read_bytes())
        self.assertEqual([], list(self.at.glob("damaged-*")))
        self.journal()

    def test_superseded_header_exits_without_allocating_or_deleting(self):
        one = self.journal()
        one.allocated(1)
        one.append({"do": "state"})
        one.close()
        before = (self.at / "records.jsonl").read_bytes()
        with self.assertRaises(self.max.Superseded):
            self.journal(2, 0)
        self.assertEqual(before, (self.at / "records.jsonl").read_bytes())
        self.journal(1, 0)

    def test_fsync_failure_cannot_publish_a_record_for_posting(self):
        one = self.journal()
        one.allocated(1)
        sync = self.max.os.fsync

        def failed_file_sync(fd):
            if fd != one.fd:
                raise OSError(5, "I/O failure")
            sync(fd)

        with mock.patch.object(self.max.os, "fsync", side_effect=failed_file_sync):
            with self.assertRaises(OSError):
                one.append({"do": "deliver", "id": "unearned", "text": "x"})
        self.assertIsNone(one.at_seq(1))

    def test_pending_header_is_synced_before_rename_and_directory_afterward(self):
        one = self.journal()
        events = []
        sync = self.max.os.fsync
        replace = self.max.os.replace

        def synced(fd):
            events.append("directory" if fd == one.fd else "file")
            sync(fd)

        def replaced(source, destination):
            events.append("rename")
            replace(source, destination)

        with mock.patch.object(self.max.os, "fsync", side_effect=synced), \
                mock.patch.object(self.max.os, "replace", side_effect=replaced):
            one.allocated(1)
        self.assertEqual(["file", "rename", "directory"], events)


class Scripted(support.Isolated):
    def setUp(self):
        super().setUp()
        self.max = adapter()
        self.calls = []
        self.queries = []
        self.said = []
        self.release = threading.Event()
        self.recording = threading.Event()
        self.script = self.reply
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.respond()

            def do_POST(self):
                self.respond()

            def respond(self):
                data = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                json_body = self.headers.get("Content-Type", "").startswith("application/json")
                body = (json.loads(data) if json_body else data) if data else {}
                split = urllib.parse.urlsplit(self.path)
                # Nested routes keep their whole suffix; the core's single-word routes are unchanged.
                route = split.path.split("/synthetic-tenant/", 1)[-1]
                owner.queries.append(dict(urllib.parse.parse_qsl(split.query)))
                owner.calls.append((route, body, self.headers.get("Authorization")))
                status, result, headers = owner.script(route, body)
                encoded = (result if isinstance(result, bytes) else json.dumps(result).encode()) if result is not None and status != 204 else b""
                self.send_response(status)
                for name, value in headers.items():
                    self.send_header(name, value)
                if not isinstance(result, bytes):
                    self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                try:
                    self.wfile.write(encoded)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def log_message(self, *_args):
                pass

        # The closed external proxy stays in place; only this exact loopback host is exempted.
        self.env = mock.patch.dict(os.environ, {"NO_PROXY": "127.0.0.1", "no_proxy": "127.0.0.1"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.endpoint = "http://127.0.0.1:%d/channel/synthetic-tenant" % self.server.server_port
        thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.01})
        thread.start()
        self.addCleanup(thread.join)
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.addCleanup(self.release.set)
        self.journal = self.max.Journal(self.home / "channel" / "journal", 0, 0, self.said.append)
        self.addCleanup(self.journal.close)
        self.client = self.max.Client(self.endpoint, "synthetic-secret")
        self.core = self.max.Core(self.client, self.journal, 0, self.said.append,
                                  active_poll=0.02, idle_poll=0.04)
        self.threads = []
        self.addCleanup(self.stop)

    def stop(self):
        self.core.stopped.set()
        self.core.changed.set()
        self.release.set()
        for thread in self.threads:
            thread.join(12)
            self.assertFalse(thread.is_alive(), "core worker leaked")

    def start(self, *names):
        for name in names:
            thread = threading.Thread(target=getattr(self.core, name))
            self.threads.append(thread)
            thread.start()

    def until(self, condition):
        deadline = time.monotonic() + 5
        while not condition() and time.monotonic() < deadline:
            threading.Event().wait(0.005)
        self.assertTrue(condition(), "calls=%r said=%r" % (self.calls, self.said))

    def reply(self, route, body):
        if route == "streams":
            return 200, {"stream": 1, "current_stream": 1, "applied_seq": 0}, {}
        if route == "inbox":
            return 204, {}, {}
        if route == "check":
            return 200, {"current_stream": 0, "applied_seq": 0,
                         "max_text": 20000, "agent": "synthetic"}, {}
        if route == "records":
            return 200, {"id": "message-1"}, {}
        return 200, {}, {}


class ScriptedCore(Scripted):
    def test_empty_heartbeat_polls_again_without_wait_parameter(self):
        self.start("poll")
        self.until(lambda: len([c for c in self.calls if c[0] == "inbox"]) >= 2)
        self.assertEqual(1, len([s for s in self.said if s.get("say") == "ready"]))
        self.assertTrue(all(c[2] == "Bearer synthetic-secret" for c in self.calls))
        self.assertFalse(any("wait" in c[0] for c in self.calls))

    def test_default_poll_delays_are_three_active_fifteen_idle(self):
        self.assertEqual((3, 15), (self.max.Core(self.client, self.journal, 0, self.said.append).active_poll,
                                  self.max.Core(self.client, self.journal, 0, self.said.append).idle_poll))
        waits = []

        def wait(delay):
            waits.append(delay)
            if len(waits) == 2:
                self.core.stopped.set()

        count = [0]

        def reply(route, body):
            count[0] += 1
            return (200, {"commands": [{"say": "query", "query": "status", "user": "m1"}]}, {}) if count[0] == 1 else self.reply(route, body)

        self.script = reply
        self.core.active_poll, self.core.idle_poll = 3, 15
        with mock.patch.object(self.core.stopped, "wait", side_effect=wait):
            self.core.poll()
        self.assertEqual([3, 15], waits)

    def test_open_work_keeps_active_polling_across_idle_heartbeats(self):
        self.core.accept({"do": "state", "state": "working", "work": "g:1", "place": "t1"})
        waits = []

        def wait(delay):
            waits.append(delay)
            if len(waits) == 3:
                self.core.stopped.set()

        self.core.active_poll, self.core.idle_poll = 3, 15
        with mock.patch.object(self.core.stopped, "wait", side_effect=wait):
            self.core.poll()
        self.assertEqual([3, 3, 3], waits)
        self.assertEqual({"g:1"}, self.core.open_work)

    def test_prolonged_work_polls_and_receives_steer_and_stop_until_ended(self):
        polls = []
        steer = {"run": 2, "attempt": 1, "conversation": "t1", "user": "m1",
                 "text": "  steer\n", "external_place": "d"}
        stop = {"say": "control", "control": "stop", "conversation": "t1",
                "user": "m1", "ref": "stop-long"}

        def reply(route, body):
            if route == "records" and not self.release.is_set():
                self.recording.set()
                return 503, {}, {"Retry-After": "3"}
            if route == "inbox":
                polls.append(time.monotonic())
                if len(polls) == 3:
                    return 200, {"runs": [steer]}, {}
                if len(polls) == 4:
                    return 200, {"commands": [stop]}, {}
            return self.reply(route, body)

        self.script = reply
        self.core.active_poll, self.core.idle_poll = 3, 15
        self.core.inbox({"runs": [{"run": 1, "attempt": 1, "conversation": "t1",
                                   "user": "m1", "text": "work"}]})
        self.core.accept({"do": "received", "receipt": "1.1", "outcome": "accepted"})
        self.core.accept({"do": "state", "state": "working", "work": "g:long",
                          "place": "t1", "for": "1.1"})
        began = time.monotonic()
        self.start("post", "poll")
        self.assertTrue(self.recording.wait(2), self.calls)

        # Real elapsed time is the acceptance boundary; accelerated polling cannot prove it.
        deadline = began + 46
        while time.monotonic() < deadline:
            self.assertEqual({"g:long"}, self.core.open_work)
            self.assertEqual(1, self.core.cursor)
            self.assertFalse(any(s.get("say") in {"failed", "delivered"} for s in self.said))
            self.assertTrue(all(thread.is_alive() for thread in self.threads), self.said)
            self.assertFalse(self.core.stopped.wait(min(0.1, max(0, deadline - time.monotonic()))))

        self.until(lambda: polls and polls[-1] - began > 45)
        self.assertGreaterEqual(len(polls), 16)
        self.assertTrue(all(b - a >= 3 for a, b in zip(polls, polls[1:])), polls)
        self.assertFalse(any("wait" in call[0] for call in self.calls))
        self.assertIn(stop, self.said)
        arrived = next(s for s in self.said if s.get("receipt") == "2.1")
        self.assertEqual(("arrived", "2.1", "  steer\n"),
                         (arrived["say"], arrived["external_id"], arrived["text"]))
        self.assertEqual({"g:long"}, self.core.open_work)
        self.assertEqual({1}, {c[1]["seq"] for c in self.calls if c[0] == "records"})

        self.core.accept({"do": "received", "receipt": "2.1", "outcome": "accepted"})
        self.core.accept({"do": "deliver", "id": "long-answer", "text": "answer",
                          "place": "t1", "reply_to": "1.1"})
        self.release.set()
        self.until(lambda: self.core.cursor == 5)
        self.assertIn({"say": "delivered", "id": "long-answer", "external_id": "message-1"}, self.said)
        self.assertEqual({"g:long"}, self.core.open_work)
        self.core.accept({"do": "work", "work": "g:long", "place": "t1", "for": "1.1",
                          "ended": "answered", "marked": "1.1", "state": "done"})
        self.until(lambda: self.core.cursor == 6)
        self.assertEqual(set(), self.core.open_work)
        terminal = next(c[1] for c in self.calls if c[0] == "records" and c[1]["seq"] == 5)
        self.assertEqual(("answered", "1.1", "succeeded"),
                         (terminal["ended"], terminal["marked"], terminal["state"]))

    def test_slow_post_does_not_block_steering_stop_or_new_arrival(self):
        def reply(route, body):
            if route == "records":
                self.recording.set()
                self.release.wait(5)
            if route == "inbox":
                return 200, {"runs": [{"run": 3, "attempt": 2, "conversation": "t1",
                                       "user": "m1", "text": "  steer\n", "external_place": "d"}],
                             "commands": [{"say": "control", "control": "stop", "user": "m1",
                                           "conversation": "t1", "ref": "command-1"}]}, {}
            return self.reply(route, body)

        self.script = reply
        self.core.accept({"do": "deliver", "id": "original", "text": "answer", "place": "t1"})
        self.start("post")
        self.assertTrue(self.recording.wait(2))
        self.start("poll")
        self.until(lambda: any(s.get("say") == "arrived" for s in self.said))
        self.assertTrue(any(s.get("control") == "stop" for s in self.said))
        arrived = next(s for s in self.said if s.get("say") == "arrived")
        self.assertEqual(("3.2", "3.2", "  steer\n"),
                         (arrived["receipt"], arrived["external_id"], arrived["text"]))
        self.assertFalse(any(s.get("say") == "delivered" for s in self.said))
        self.core.accept({"do": "received", "receipt": "3.2", "outcome": "accepted"})
        self.assertEqual([1, 2], [r["seq"] for r in self.journal.records])
        self.release.set()
        self.until(lambda: any(s.get("say") == "delivered" for s in self.said))
        self.assertIn({"say": "delivered", "id": "original", "external_id": "message-1"}, self.said)

    def test_503_keeps_original_record_and_never_reports_failure(self):
        def reply(route, body):
            if route == "records" and not self.release.is_set():
                self.recording.set()
                return 503, {}, {"Retry-After": "0.02"}
            return self.reply(route, body)

        self.script = reply
        self.core.accept({"do": "deliver", "id": "piece-7", "text": "  preserve\n"})
        self.core.accept({"do": "state", "state": "done", "external_id": "1.1"})
        self.start("post", "poll")
        self.until(lambda: len([c for c in self.calls if c[0] == "records"]) >= 2)
        self.assertEqual({1}, {c[1]["seq"] for c in self.calls if c[0] == "records"})
        self.assertFalse(any(s.get("say") in {"failed", "delivered"} for s in self.said))
        self.assertGreaterEqual(len([c for c in self.calls if c[0] == "inbox"]), 1)
        self.release.set()
        self.until(lambda: self.core.cursor == 3)
        self.assertIn({"say": "delivered", "id": "piece-7", "external_id": "message-1"}, self.said)
        rows = [c[1] for c in self.calls if c[0] == "records"]
        self.assertEqual("  preserve\n", rows[0]["text"])
        self.assertEqual(2, rows[-1]["seq"])
        self.assertTrue(all(c[1] == rows[0] for c in self.calls if c[0] == "records" and c[1]["seq"] == 1))

    def test_truncated_inbox_response_recovers_and_still_receives_stop(self):
        polls = [0]

        def reply(route, body):
            if route == "inbox":
                polls[0] += 1
                if polls[0] == 1:
                    return 200, b"5\r\nab", {"Transfer-Encoding": "chunked"}
                return 200, {"commands": [{"say": "control", "control": "stop", "user": "m1", "ref": "stop-1"}]}, {}
            return self.reply(route, body)

        self.script = reply
        self.start("poll")
        self.until(lambda: any(s.get("control") == "stop" for s in self.said))
        self.assertFalse(self.core.stopped.is_set())
        self.assertTrue(self.threads[0].is_alive())
        self.assertTrue(any("deferred" in s.get("text", "") for s in self.said))

    def test_truncated_post_response_retries_same_record_without_unearned_outcome(self):
        attempts = []

        def reply(route, body):
            if route == "records":
                attempts.append(dict(body))
                if len(attempts) == 1:
                    return 200, b"5\r\nab", {"Transfer-Encoding": "chunked"}
            return self.reply(route, body)

        self.script = reply
        self.core.accept({"do": "deliver", "id": "truncated", "text": "still whole"})
        self.start("post")
        self.until(lambda: any("deferred" in s.get("text", "") for s in self.said))
        self.assertEqual(1, self.core.cursor)
        self.assertFalse(any(s.get("say") in {"delivered", "failed"} for s in self.said))
        self.until(lambda: self.core.cursor == 2)
        self.assertEqual(2, len(attempts))
        self.assertEqual(attempts[0], attempts[1])
        self.assertEqual([{"say": "delivered", "id": "truncated", "external_id": "message-1"}],
                         [s for s in self.said if s.get("say") == "delivered"])

    def test_revocation_on_idle_poll_exits_78(self):
        self.script = lambda route, body: (401, {}, {})
        self.start("poll")
        self.until(self.core.stopped.is_set)
        self.assertEqual(78, self.core.code)

    def test_superseded_post_exits_78_and_keeps_record(self):
        def reply(route, body):
            return (410, {"current_stream": 2}, {}) if route == "records" else self.reply(route, body)

        self.script = reply
        self.core.accept({"do": "state", "state": "working", "place": "t1", "work": "g:1"})
        self.start("post")
        self.until(self.core.stopped.is_set)
        self.assertEqual(78, self.core.code)
        self.assertEqual(1, len(self.journal.records))
        self.assertEqual(1, len([c for c in self.calls if c[0] == "streams"]))

    def test_recorded_receipt_stops_repeat_arrivals_while_posting_is_down(self):
        body = {"runs": [{"run": 4, "attempt": 1, "conversation": "t1", "user": "m1", "text": "x"}]}
        self.assertTrue(self.core.inbox(body))
        self.core.accept({"do": "received", "receipt": "4.1", "outcome": "duplicate"})
        self.assertFalse(self.core.inbox(body))
        self.assertEqual(1, len([s for s in self.said if s.get("say") == "arrived"]))

    def test_work_does_not_expire_and_ended_keeps_mark_authority(self):
        self.core.accept({"do": "state", "state": "working", "work": "g:1", "place": "t1"})
        with mock.patch.object(self.max.time, "monotonic", return_value=10**12):
            self.assertEqual({"g:1"}, self.core.open_work)
        ended = {"do": "work", "work": "g:1", "place": "t1", "for": "3.1",
                 "ended": "pending", "marked": None, "state": None}
        self.core.accept(ended)
        self.assertEqual(set(), self.core.open_work)
        self.assertEqual(dict(ended, seq=2), self.journal.records[-1])

    def test_done_translates_to_max_status_without_changing_journal_or_marked(self):
        terminal = {"do": "state", "state": "done", "place": "t1", "external_id": "3.1"}
        ended = {"do": "work", "work": "g:1", "place": "t1", "for": "3.1",
                 "ended": "answered", "marked": "3.1", "state": "done"}
        self.core.accept(terminal)
        self.core.accept(ended)
        self.start("post")
        self.until(lambda: self.core.cursor == 3)
        posted = [c[1] for c in self.calls if c[0] == "records"]
        self.assertEqual(["succeeded", "succeeded"], [r["state"] for r in posted])
        self.assertEqual(["done", "done"], [r["state"] for r in self.journal.records])
        self.assertEqual("3.1", posted[1]["marked"])

    def test_all_commands_are_forwarded_whole_and_answer_keeps_whitespace(self):
        commands = [
            {"say": "control", "control": word, "user": "m1", "ref": "ref-" + word}
            for word in ("stop", "forget", "restart", "shutdown")]
        commands += [{"say": "query", "query": word, "user": "m1", "ref": "ref-" + word}
                     for word in ("status", "version", "agents", "skills", "schedules", "delegations")]
        commands += [{"say": "configure", "provider": "codex", "alias": "other", "user": "m1", "ref": "ref-config"}]
        self.assertTrue(self.core.inbox({"commands": commands}))
        self.assertEqual(commands, self.said)
        answer = "  full answer\n" * 3000
        self.core.accept({"do": "answered", "ref": "ref-agents", "text": answer})
        self.start("post")
        self.until(lambda: self.core.cursor == 2)
        self.assertEqual(answer, next(c[1]["text"] for c in self.calls if c[0] == "records"))

    def test_claim_conflict_never_hands_message_to_rundesk(self):
        self.script = lambda route, body: (409, {}, {})
        self.assertFalse(self.core.inbox({"runs": [{"run": 1, "attempt": 1, "text": "late"}]}))
        self.assertEqual([], self.said)

    def test_refused_delivery_advances_sequence_and_reports_failure_once(self):
        def reply(route, body):
            if route == "records" and body["seq"] == 1:
                return 422, {}, {}
            return self.reply(route, body)

        self.script = reply
        self.core.accept({"do": "deliver", "id": "refused", "text": "a"})
        self.core.accept({"do": "answered", "ref": "cmd", "text": "b"})
        self.start("post")
        self.until(lambda: self.core.cursor == 3)
        self.assertEqual(["failed"], [s["say"] for s in self.said])
        self.assertEqual([1, 2], [c[1]["seq"] for c in self.calls if c[0] == "records"])

    def test_gap_rewinds_only_to_retained_records(self):
        self.journal.allocated(1)
        self.core.accept({"do": "answered", "ref": "a", "text": "one"})
        self.core.accept({"do": "answered", "ref": "b", "text": "two"})
        self.core.cursor = 2
        seen = []

        def reply(route, body):
            if route == "records":
                seen.append(body["seq"])
                if len(seen) == 1:
                    return 409, {"expected": 1}, {}
            return self.reply(route, body)

        self.script = reply
        self.start("post")
        self.until(lambda: self.core.cursor == 3)
        self.assertEqual([2, 1, 2], seen)

    def test_php_empty_array_is_a_successful_claim_result(self):
        self.script = lambda route, body: (200, [], {})
        self.assertEqual((200, {}), self.client.request("POST", "claim", {"run": 1, "attempt": 1})[:2])

    def test_revocation_body_does_not_need_to_be_json_object(self):
        self.script = lambda route, body: (401, "Unauthorized", {})
        self.start("poll")
        self.until(self.core.stopped.is_set)
        self.assertEqual(78, self.core.code)

    def test_no_receipt_retries_same_identity_and_warns_after_ten(self):
        body = {"runs": [{"run": 4, "attempt": 1, "conversation": "t1", "user": "m1", "text": "x"}]}
        for number in range(10):
            with mock.patch.object(self.max.time, "monotonic", return_value=number * 100):
                self.assertTrue(self.core.inbox(body))
        arrivals = [s for s in self.said if s.get("say") == "arrived"]
        self.assertEqual(10, len(arrivals))
        self.assertEqual({"4.1"}, {s["external_id"] for s in arrivals})
        self.assertEqual(1, len([s for s in self.said if s.get("say") == "note"]))
        self.assertFalse(self.core.stopped.is_set())

    def test_process_restart_after_allocation_commit_reuses_pending_nonce(self):
        state = {"current_stream": 0, "nonce": None}

        def reply(route, body):
            if route == "streams":
                if body["nonce"] != state["nonce"]:
                    self.assertEqual(state["current_stream"], body["supersede"])
                    state["current_stream"] += 1
                    state["nonce"] = body["nonce"]
                return 200, {"stream": state["current_stream"]}, {}
            if route == "check":
                return 200, {"current_stream": state["current_stream"], "applied_seq": 0}, {}
            return self.reply(route, body)

        self.script = reply
        executable = support.CHECKOUT / "src" / "channels" / "max"
        channel = self.home / "restarted-channel"
        env = dict(os.environ, RUNDESK_HOME=str(self.home), RUNDESK_CHANNEL_HOME=str(channel),
                   RUNDESK_SETTINGS=json.dumps({"endpoint": self.endpoint}), MAX_CHANNEL_SECRET="synthetic-secret")
        code = """import os, runpy, sys
from pathlib import Path
m = runpy.run_path(sys.argv[1])
j = m['Journal'](Path(sys.argv[2]) / 'journal', 0, 0, print)
c = m['Client'](sys.argv[3], 'synthetic-secret')
c.request('POST', 'streams', {k:j.header[k] for k in ('nonce','supersede')})
os._exit(0)
"""
        first = subprocess.run([sys.executable, "-B", "-c", code, str(executable), str(channel), self.endpoint],
                               env=env, capture_output=True, timeout=5)
        self.assertEqual(0, first.returncode, first.stderr)
        pending = json.loads((channel / "journal" / "stream.json").read_text())
        self.assertIsNone(pending["stream"])
        second = subprocess.Popen([sys.executable, "-B", str(executable), "serve"], env=env,
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            second.stdin.write(b'{"do":"answered","ref":"command","text":"answer"}\n')
            second.stdin.flush()
            self.until(lambda: any(c[0] == "records" for c in self.calls))
            second.stdin.write(b'{"do":"stop"}\n')
            second.stdin.flush()
            out, err = second.communicate(timeout=5)
            self.assertEqual(0, second.returncode, (out, err))
        finally:
            if second.poll() is None:
                second.kill()
                second.communicate()
        self.assertEqual(1, state["current_stream"])
        allocations = [c[1] for c in self.calls if c[0] == "streams"]
        self.assertEqual(2, len(allocations))
        self.assertEqual(allocations[0], allocations[1])
        self.assertEqual(pending["nonce"], json.loads((channel / "journal" / "stream.json").read_text())["nonce"])

    def test_unverifiable_file_refuses_delivery_without_claiming_success(self):
        self.core.accept({"do": "deliver", "id": "file", "text": "file", "files": [{"name": "x"}]})
        self.assertEqual("failed", self.said[0]["say"])
        self.assertEqual([], self.journal.records)

    def test_real_process_drains_pipe_during_delayed_post_and_stops_cleanly(self):
        # The installed shape is exercised under one temporary root, never the live install.
        executable = self.home / "data" / "adapters" / "max"
        executable.parent.mkdir(parents=True)
        shutil.copy2(support.CHECKOUT / "src" / "channels" / "max", executable)
        channel = self.home / "data" / "agents" / "synthetic" / "channels" / "max"

        def reply(route, body):
            if route == "records":
                self.recording.set()
                self.release.wait(5)
            return self.reply(route, body)

        self.script = reply
        env = dict(os.environ, RUNDESK_HOME=str(self.home), RUNDESK_CHANNEL_HOME=str(channel),
                   RUNDESK_SETTINGS=json.dumps({"endpoint": self.endpoint}), MAX_CHANNEL_SECRET="synthetic-secret")
        process = subprocess.Popen([sys.executable, "-B", str(executable), "serve"], env=env,
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.addCleanup(lambda: process.poll() is None and process.kill())
        try:
            process.stdin.write(b'{"do":"deliver","id":"piece-0","text":"answer","place":"t1"}\n')
            process.stdin.flush()
            self.assertTrue(self.recording.wait(2))
            process.stdin.write(b'{"do":"state","state":"working","place":"t1","work":"g:2"}\n'
                                b'{"do":"work","work":"g:2","place":"t1","ended":"answered","marked":null}\n')
            process.stdin.flush()
            journal = channel / "journal" / "records.jsonl"
            self.until(lambda: journal.exists() and len(journal.read_text().splitlines()) == 3)
            self.release.set()
            process.stdin.write(b'{"do":"stop"}\n')
            process.stdin.flush()
            out, err = process.communicate(timeout=5)
            self.assertEqual(0, process.returncode, (out, err))
            self.assertEqual(b"", err)
        finally:
            self.release.set()
            if process.poll() is None:
                process.kill()
                process.communicate()


class ScriptedParity(Scripted):
    """Files, notices, delegation, child threads, search and fetch against the scripted Max routes."""

    def approved(self, name="report.txt", content=b"quarterly numbers\n"):
        folder = self.home / "agents" / "synthetic" / "home"
        folder.mkdir(parents=True, exist_ok=True)
        at = folder / name
        at.write_bytes(content)
        return {"name": name, "at": str(at), "bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest()}

    def records(self):
        return [c[1] for c in self.calls if c[0] == "records"]

    def test_capabilities_and_check_offer_parity_and_notices(self):
        out = subprocess.run([sys.executable, "-B", str(support.CHECKOUT / "src" / "channels" / "max"),
                              "--capabilities"], capture_output=True, text=True, timeout=20)
        said = json.loads(out.stdout)
        for key in ("attach", "search", "thread", "address"):
            self.assertIs(True, said[key], key)
        env = dict(os.environ, MAX_CHANNEL_SECRET="synthetic-secret",
                   RUNDESK_SETTINGS=json.dumps({"endpoint": self.endpoint}))
        out = subprocess.run([sys.executable, "-B", str(support.CHECKOUT / "src" / "channels" / "max"),
                              "--check"], capture_output=True, text=True, timeout=20, env=env)
        checked = json.loads(out.stdout)
        self.assertTrue(checked["ok"], checked)
        self.assertEqual("notices", checked["notify_place"])

    def test_inbound_file_lands_with_declared_size_and_never_follows_the_described_url(self):
        def reply(route, body):
            if route == "attachments/7":
                return 200, b"hello", {"Content-Length": "5"}
            return self.reply(route, body)

        self.script = reply
        run = {"run": 3, "attempt": 1, "conversation": "t9", "user": "m1", "text": "see file",
               "attachments": [{"id": 7, "name": "plan.pdf", "bytes": 5,
                                "url": "https://elsewhere.invalid/steal"}]}
        self.assertTrue(self.core.inbox({"runs": [run]}))
        arrived = next(s for s in self.said if s.get("say") == "arrived")
        at = self.home / "channel" / "fetched" / "3.1" / "0"
        self.assertEqual([{"at": str(at), "name": "plan.pdf", "bytes": 5}], arrived["attachments"])
        self.assertEqual(b"hello", at.read_bytes())
        self.assertEqual(["claim", "attachments/7"], [c[0] for c in self.calls])

    def test_refused_inbound_file_is_left_out_so_files_only_message_is_not_taken_in(self):
        self.script = lambda route, body: (403, {}, {}) if route.startswith("attachments/") else self.reply(route, body)
        run = {"run": 4, "attempt": 2, "conversation": "t9", "user": "m1", "text": "",
               "attachments": [{"id": 8, "name": "x.bin", "bytes": 3}]}
        self.assertTrue(self.core.inbox({"runs": [run]}))
        arrived = next(s for s in self.said if s.get("say") == "arrived")
        self.assertNotIn("attachments", arrived)
        self.assertEqual("", arrived["text"])
        self.assertTrue(any("HTTP 403" in s.get("text", "") for s in self.said if s.get("say") == "note"))

    def test_deferred_inbound_file_is_not_handed_on_until_it_downloads_whole(self):
        answers = [(503, {}, {}), (200, b"abc", {"Content-Length": "3"})]
        self.script = lambda route, body: answers.pop(0) if route == "attachments/5" else self.reply(route, body)
        run = {"run": 5, "attempt": 1, "conversation": "t9", "user": "m1", "text": "",
               "attachments": [{"id": 5, "name": "a", "bytes": 3}]}
        self.core.inbox({"runs": [run]})
        self.assertEqual([], [s for s in self.said if s.get("say") == "arrived"])
        with mock.patch.object(self.max.time, "monotonic", return_value=time.monotonic() + 100):
            self.core.inbox({"runs": [run]})
        arrived = [s for s in self.said if s.get("say") == "arrived"]
        self.assertEqual(1, len(arrived))
        self.assertEqual(3, arrived[0]["attachments"][0]["bytes"])

    def test_inbound_body_must_match_the_declared_size(self):
        bodies = {"attachments/1": (200, b"abc", {"Content-Length": "3"}),
                  "attachments/2": (200, b"toolong", {"Content-Length": "7"})}
        self.script = lambda route, body: bodies.get(route) or self.reply(route, body)
        short = {"run": 6, "attempt": 1, "conversation": "t9", "user": "m1", "text": "",
                 "attachments": [{"id": 1, "name": "a", "bytes": 5}]}
        self.core.inbox({"runs": [short]})
        self.assertEqual([], [s for s in self.said if s.get("say") == "arrived"])
        self.assertFalse((self.home / "channel" / "fetched" / "6.1" / "0").exists())
        long = {"run": 7, "attempt": 1, "conversation": "t9", "user": "m1", "text": "hi",
                "attachments": [{"id": 2, "name": "b", "bytes": 5}]}
        self.core.inbox({"runs": [long]})
        arrived = [s for s in self.said if s.get("say") == "arrived"]
        self.assertEqual(1, len(arrived))
        self.assertNotIn("attachments", arrived[0])
        self.assertFalse((self.home / "channel" / "fetched" / "7.1" / "0").exists())

    def test_outbound_file_is_snapshotted_staged_alone_and_named_by_upload(self):
        uploads = []

        def reply(route, body):
            if route == "uploads":
                uploads.append(body)
                return 201, {"upload": "00000000-0000-4000-8000-000000000001"}, {}
            return self.reply(route, body)

        self.script = reply
        said = self.approved()
        self.core.accept({"do": "deliver", "id": "p-0", "place": "t9", "text": "here", "files": [said]})
        # The original may change after approval: the journalled snapshot is what goes out.
        (self.home / "agents" / "synthetic" / "home" / "report.txt").write_bytes(b"changed")
        self.start("post")
        self.until(lambda: any(s.get("say") == "delivered" for s in self.said))
        self.assertEqual(1, len(uploads))
        self.assertIn(b"quarterly numbers\n", uploads[0])
        self.assertIn(said["sha256"].encode(), uploads[0])
        posted = self.records()[0]
        self.assertEqual([{"name": "report.txt", "bytes": said["bytes"], "sha256": said["sha256"],
                           "upload": "00000000-0000-4000-8000-000000000001"}], posted["files"])
        self.assertNotIn("snapshot", posted)
        self.until(lambda: list((self.home / "channel" / "outbox").iterdir()) == [])

    def test_file_changed_or_linked_before_snapshot_refuses_whole_delivery(self):
        said = self.approved()
        said["sha256"] = "0" * 64
        self.core.accept({"do": "deliver", "id": "bad", "place": "t9", "text": "x", "files": [said]})
        linked = self.approved("real.txt")
        link = self.home / "linked"
        os.symlink(str(self.home / "agents"), str(link))
        linked["at"] = str(link / "synthetic" / "home" / "real.txt")
        self.core.accept({"do": "deliver", "id": "link", "place": "t9", "text": "x", "files": [linked]})
        failed = [s for s in self.said if s.get("say") == "failed"]
        self.assertEqual(["bad", "link"], [s["id"] for s in failed])
        self.assertIn("changed after it was approved", failed[0]["why"])
        self.assertIn("symbolic link", failed[1]["why"])
        self.assertEqual([], self.journal.records)
        self.assertEqual([], list((self.home / "channel" / "outbox").iterdir()))

    def test_refused_upload_still_consumes_the_sequence_and_reports_failure(self):
        def reply(route, body):
            if route == "uploads":
                return 422, {}, {}
            if route == "records" and body.get("do") == "deliver":
                self.assertNotIn("upload", body["files"][0])
                return 422, {}, {}
            return self.reply(route, body)

        self.script = reply
        self.core.accept({"do": "deliver", "id": "f", "place": "t9", "text": "x", "files": [self.approved()]})
        self.core.accept({"do": "answered", "ref": "c", "text": "after"})
        self.start("post")
        self.until(lambda: self.core.cursor == 3)
        self.assertEqual(["failed"], [s["say"] for s in self.said if s["say"] != "note"])

    def test_busy_upload_is_retried_without_any_outcome(self):
        answers = [(503, {}, {"Retry-After": "0"}),
                   (201, {"upload": "00000000-0000-4000-8000-000000000002"}, {})]
        self.script = lambda route, body: answers.pop(0) if route == "uploads" else self.reply(route, body)
        self.core.accept({"do": "deliver", "id": "f", "place": "t9", "text": "x", "files": [self.approved()]})
        self.start("post")
        self.until(lambda: any(s.get("say") == "delivered" for s in self.said))
        self.assertEqual([], [s for s in self.said if s.get("say") == "failed"])
        self.assertEqual(2, len([c for c in self.calls if c[0] == "uploads"]))

    def test_notice_fans_out_to_each_allowed_member_and_answers_once(self):
        self.core.allowed = ["m1", "m2", "U9"]

        def reply(route, body):
            if route == "records" and body.get("to", {}).get("sender") == "m2":
                return 403, {}, {}
            return self.reply(route, body)

        self.script = reply
        self.core.accept({"do": "deliver", "id": "n-0", "place": "notices", "text": "back up",
                          "notice": True, "reply_to": "77"})
        self.start("post")
        self.until(lambda: self.core.cursor == 3)
        posted = self.records()
        self.assertEqual([("n-0/m1", {"sender": "m1"}), ("n-0/m2", {"sender": "m2"})],
                         [(r["id"], r["to"]) for r in posted])
        for record in posted:
            for absent in ("place", "reply_to", "of"):
                self.assertNotIn(absent, record)
        self.assertEqual([{"say": "delivered", "id": "n-0", "external_id": "message-1"}],
                         [s for s in self.said if s["say"] in {"delivered", "failed"}])

    def test_notice_nobody_received_fails_once_and_no_allowed_member_refuses(self):
        self.core.allowed = ["m1", "m2"]
        self.script = lambda route, body: (403, {}, {}) if route == "records" else self.reply(route, body)
        self.core.accept({"do": "deliver", "id": "n", "place": "notices", "text": "x", "notice": True})
        self.start("post")
        self.until(lambda: self.core.cursor == 3)
        outcomes = [s for s in self.said if s["say"] in {"delivered", "failed"}]
        self.assertEqual([("failed", "n")], [(s["say"], s["id"]) for s in outcomes])
        self.core.allowed = ["U1"]
        self.core.accept({"do": "deliver", "id": "none", "place": "notices", "text": "x", "notice": True})
        self.assertIn("no allowed Max member", self.said[-1]["why"])

    def test_aimed_delivery_is_never_fanned_out_and_a_place_is_refused(self):
        self.core.allowed = ["m1", "m2"]
        self.core.accept({"do": "deliver", "id": "a", "place": "", "text": "x", "notice": True,
                          "to": {"sender": "m2"}})
        self.core.accept({"do": "deliver", "id": "b", "place": "", "text": "x", "to": {"place": "c4"}})
        self.assertEqual([{"do": "deliver", "id": "a", "text": "x", "notice": True,
                           "to": {"sender": "m2"}, "seq": 1}], self.journal.records)
        self.assertEqual("b", self.said[-1]["id"])
        self.assertIn("no place destinations", self.said[-1]["why"])

    def test_child_thread_anchor_kept_only_for_a_run_attempt(self):
        self.core.accept({"do": "deliver", "id": "t1", "place": "t9", "text": "x",
                          "reply_to": "12.1", "threaded": "weekly"})
        self.core.accept({"do": "deliver", "id": "t2", "place": "t9", "text": "x",
                          "reply_to": "4401", "threaded": "weekly"})
        first, second = self.journal.records
        self.assertEqual(("12.1", "weekly"), (first["reply_to"], first["threaded"]))
        self.assertNotIn("reply_to", second)
        self.assertNotIn("threaded", second)

    def test_delegation_records_are_journalled_and_posted_whole(self):
        record = {"do": "delegation", "place": "t9", "state": "handed", "who": "dev",
                  "ask": "del-41", "provider": "/opt/x/codex", "provider_alias": "work"}
        self.core.accept(record)
        self.start("post")
        self.until(lambda: self.core.cursor == 2)
        posted = self.records()[0]
        self.assertEqual(dict(record, seq=1, stream=1), posted)

    def test_notice_copies_journalled_before_a_restart_still_answer_once(self):
        self.journal.allocated(1)
        for person in ("m1", "m2"):
            self.journal.append({"do": "deliver", "id": "n/" + person, "text": "x", "notice": True,
                                 "to": {"sender": person}, "of": "n"})
        self.script = lambda route, body: (403, {}, {}) if route == "records" else self.reply(route, body)
        self.start("post")
        self.until(lambda: self.core.cursor == 3)
        self.assertEqual([("failed", "n")], [(s["say"], s["id"]) for s in self.said
                                             if s["say"] in {"delivered", "failed"}])

    def test_rewound_delivery_keeps_its_snapshot_and_never_answers_twice(self):
        answers = {"deliver": [(403, {}, {}), (201, {"id": "late"}, {})],
                   "answered": [(409, {"expected": 1}, {}), (200, {}, {})]}
        uploads = []

        def reply(route, body):
            if route == "uploads":
                uploads.append(1)
                return 201, {"upload": "00000000-0000-4000-8000-00000000000%d" % len(uploads)}, {}
            if route == "records":
                return answers[body["do"]].pop(0)
            return self.reply(route, body)

        self.script = reply
        self.core.accept({"do": "deliver", "id": "d", "place": "t9", "text": "x", "files": [self.approved()]})
        self.core.accept({"do": "answered", "ref": "c", "text": "after"})
        self.start("post")
        self.until(lambda: self.core.cursor == 3)
        outcomes = [s for s in self.said if s["say"] in {"delivered", "failed"}]
        self.assertEqual([("failed", "d")], [(s["say"], s["id"]) for s in outcomes])
        self.assertFalse(any("lost its file snapshot" in s.get("text", "") for s in self.said))
        self.until(lambda: list((self.home / "channel" / "outbox").iterdir()) == [])

    def test_paused_binding_is_retried_without_consuming_or_answering(self):
        self.core.idle_poll = 0.01
        off = (403, {"message": "Forbidden.", "binding": "inactive"}, {})
        answers = {"uploads": [off, (201, {"upload": "00000000-0000-4000-8000-000000000009"}, {})],
                   "records": [off, (201, {"id": "m"}, {})]}
        self.script = lambda route, body: answers[route].pop(0) if route in answers else self.reply(route, body)
        self.core.accept({"do": "deliver", "id": "p", "place": "t9", "text": "x", "files": [self.approved()]})
        self.start("post")
        self.until(lambda: self.core.cursor == 2)
        self.assertEqual([{"say": "delivered", "id": "p", "external_id": "m"}],
                         [s for s in self.said if s["say"] in {"delivered", "failed"}])
        self.assertEqual(2, len([c for c in self.calls if c[0] == "records"]))

    def test_paused_binding_keeps_polling_and_holds_runs(self):
        off = (403, {"message": "Forbidden.", "binding": "inactive"}, {})
        self.script = lambda route, body: off
        self.start("poll")
        self.until(lambda: len([c for c in self.calls if c[0] == "inbox"]) >= 2)
        self.assertFalse(self.core.stopped.is_set())
        self.assertFalse(self.core.inbox({"runs": [{"run": 2, "attempt": 1, "text": "x"}]}))
        self.assertIn("2.1", self.core.pending)
        self.assertEqual({"ok": False, "why": self.max.PAUSED_WHY},
                         self.max.search(self.client, {"words": "x"}))

    def test_snapshot_destination_failure_is_a_refusal_not_a_double_close(self):
        said = self.approved()
        into = self.home / "channel" / "outbox" / "taken" / "0"
        into.parent.mkdir(parents=True)
        into.write_bytes(b"")
        with self.assertRaises(self.max.Refused):
            self.max.a_snapshot(said, into)

    def test_interrupted_download_leaves_no_partial_file(self):
        class Cut:
            code = 200

            def __init__(self):
                self.reads = [b"ab"]

            def read(self, _amount):
                if self.reads:
                    return self.reads.pop()
                raise ConnectionResetError("reset mid-body")

            def __enter__(self):
                return self

            def __exit__(self, *_exc):
                return False

        at = self.home / "channel" / "fetched" / "8.1" / "0"
        with mock.patch.object(self.client, "open", return_value=Cut()):
            with self.assertRaises(ConnectionResetError):
                self.client.download("attachments/3", at, 5)
        self.assertFalse(at.exists())

    def test_run_that_is_not_two_positive_numbers_is_never_named_on_disk(self):
        self.assertFalse(self.core.inbox({"runs": [{"run": "../../x", "attempt": 1, "text": "x",
                                                     "attachments": [{"id": 1, "bytes": 1}]}]}))
        self.assertEqual([], self.calls)
        self.assertFalse((self.home / "channel" / "fetched").exists())

    def test_threaded_pieces_are_numbered_so_only_the_first_can_link(self):
        for n in range(2):
            self.core.accept({"do": "deliver", "id": "r-%d" % n, "place": "t9", "text": "x",
                              "reply_to": "12.1", "threaded": "report"})
        self.assertEqual([0, 1], [row["piece"] for row in self.journal.records])

    def test_seen_does_not_close_legacy_work(self):
        self.core.accept({"do": "state", "place": "t9", "state": "working"})
        self.core.accept({"do": "state", "place": "t9", "external_id": "1.1", "state": "seen"})
        self.assertEqual({"legacy:t9"}, self.core.open_work)


class SearchAndFetch(Scripted):
    def test_search_pages_to_limit_with_inclusive_days_and_maps_hits(self):
        pages = [{"hits": [{"ref": "t9/3", "conversation": "t9", "user": "m1", "display": "Dana",
                            "text": "invoice", "at": "2026-11-19T10:00:00+00:00", "link": "https://x/3"}],
                  "before": "c1", "looked": {"messages": 4}},
                 {"hits": [{"ref": "t9/1", "conversation": "t9", "user": "m1", "text": "invoice again",
                            "at": "2026-11-18T10:00:00+00:00"}], "before": "c2", "looked": {"messages": 2}}]
        self.script = lambda route, body: (200, pages.pop(0), {})
        answer = self.max.search(self.client, {"words": "invoice", "place": "t9", "user": "m1",
                                               "since": "2026-11-01", "until": "2026-11-19", "limit": 2})
        self.assertTrue(answer["ok"])
        self.assertEqual("", answer["partial"])
        self.assertEqual({"messages": 6}, answer["looked"])
        self.assertEqual({"who": "m1", "when": "2026-11-19T10:00:00+00:00", "text": "invoice",
                          "ref": "t9/3", "display": "Dana", "link": "https://x/3",
                          "external_place": "t9"}, answer["results"][0])
        self.assertEqual("2026-11-19 23:59:59.999999", self.queries[0]["until"])
        self.assertEqual("c1", self.queries[1]["before"])
        self.assertEqual(["2", "1"], [q["limit"] for q in self.queries])

    def test_search_refuses_scopes_max_cannot_read_and_says_when_it_stopped_early(self):
        self.assertFalse(self.max.search(self.client, {"place": "c5"})["ok"])
        self.assertFalse(self.max.search(self.client, {"user": "dana"})["ok"])
        self.assertEqual([], self.calls)
        self.script = lambda route, body: (503, {}, {"Retry-After": "5"})
        busy = self.max.search(self.client, {"words": "x", "limit": 5})
        self.assertTrue(busy["ok"])
        self.assertIn("busy", busy["partial"])
        # No page answered, so nothing was measured: absent, never a zero.
        self.assertNotIn("looked", busy)
        self.assertEqual(1, len(self.calls))
        page = {"hits": [], "before": "more", "looked": {"messages": 200}}
        self.script = lambda route, body: (200, page, {})
        ticks = iter([0, 0, 60])
        spent = self.max.search(self.client, {"words": "x", "limit": 5}, clock=lambda: next(ticks))
        self.assertIn("50 seconds", spent["partial"])
        self.script = lambda route, body: (401, {}, {})
        self.assertFalse(self.max.search(self.client, {"words": "x"})["ok"])

    def test_search_skips_hits_that_could_not_be_shown(self):
        page = {"hits": [{"ref": "t9/2", "user": "m1", "text": "", "at": "2026-11-19T10:00:00Z"},
                         {"ref": "t9/1", "user": "m1", "text": "kept", "at": "2026-11-19T09:00:00Z"}],
                "before": None, "looked": {"messages": 2}}
        self.script = lambda route, body: (200, page, {})
        answer = self.max.search(self.client, {"words": "", "limit": 5})
        self.assertEqual(["t9/1"], [one["ref"] for one in answer["results"]])

    def test_fetch_rechecks_and_lands_each_file_at_its_own_position(self):
        def reply(route, body):
            if route == "messages/9/3/attachments":
                return 200, {"attachments": [{"id": 1, "name": "a.txt", "bytes": 1},
                                             {"id": 2, "name": "b.txt", "bytes": 2},
                                             {"id": 3, "name": "c.txt", "bytes": 1}]}, {}
            if route == "messages/9/3/attachments/1":
                return 200, b"a", {"Content-Length": "1"}
            if route == "messages/9/3/attachments/2":
                return 403, {}, {}
            return 200, b"c", {"Content-Length": "1"}

        self.script = reply
        answer = self.max.fetch(self.client, {"ref": "t9/3"}, self.home / "channel")
        self.assertTrue(answer["ok"])
        self.assertEqual("3", answer["message"])
        landed = self.home / "channel" / "fetched" / "3"
        self.assertEqual([str(landed / "0"), str(landed / "2")], [a["at"] for a in answer["attachments"]])
        self.assertEqual(b"c", (landed / "2").read_bytes())
        self.assertIn("HTTP 403", answer["partial"])
        self.script = lambda route, body: (403, {}, {})
        self.assertFalse(self.max.fetch(self.client, {"ref": "t9/4"}, self.home / "channel")["ok"])
        self.assertFalse(self.max.fetch(self.client, {"ref": "c9/4"}, self.home / "channel")["ok"])

    def test_search_invocation_reads_one_request_and_prints_one_answer(self):
        self.script = lambda route, body: (200, {"hits": [], "before": None, "looked": {"messages": 0}}, {})
        env = dict(os.environ, MAX_CHANNEL_SECRET="synthetic-secret",
                   RUNDESK_SETTINGS=json.dumps({"endpoint": self.endpoint}))
        out = subprocess.run([sys.executable, "-B", str(support.CHECKOUT / "src" / "channels" / "max"),
                              "search"], input='{"words": "x", "place": "", "user": "", "since": "", '
                             '"until": "", "limit": 3}', capture_output=True, text=True, timeout=20, env=env)
        self.assertEqual(0, out.returncode, out.stderr)
        self.assertEqual({"ok": True, "results": [], "partial": "", "looked": {"messages": 0}},
                         json.loads(out.stdout))


if __name__ == "__main__":
    support.unittest.main()
