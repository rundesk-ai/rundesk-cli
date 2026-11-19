"""The isolated Max core: durable ordering and independently progressing pipes/polls."""

import importlib.machinery
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import threading
import time
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


class ScriptedCore(support.Isolated):
    def setUp(self):
        super().setUp()
        self.max = adapter()
        self.calls = []
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
                body = json.loads(data) if data else {}
                route = self.path.rsplit("/", 1)[-1]
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

    def test_core_refuses_deferred_delivery_without_claiming_success(self):
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


if __name__ == "__main__":
    support.unittest.main()
