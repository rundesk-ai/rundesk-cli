"""Grok's ACP stream, mapped onto the provider contract.

Nothing here starts the real Grok CLI. The mapping is driven with the structured events
measured from Grok 0.2.112, and the process lifecycle is driven through a small ACP stand-in.

Run: python3 tests/test_grok.py
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from rundesk import provider, turn  # noqa: E402

AT = ROOT / "src" / "providers" / "grok"


def _adapter():
    loader = importlib.machinery.SourceFileLoader("rundesk_grok", str(AT))
    spec = importlib.util.spec_from_loader("rundesk_grok", loader)
    made = importlib.util.module_from_spec(spec)
    loader.exec_module(made)
    return made


grok = _adapter()


def update(session_update: str, method="session/update", session="session-one",
           meta=None, **fields) -> str:
    params = {
        "sessionId": session,
        "update": {"sessionUpdate": session_update, **fields},
    }
    if meta is not None:
        params["_meta"] = meta
    return json.dumps({"jsonrpc": "2.0", "method": method, "params": params})


STREAM = [
    update("agent_thought_chunk", content={"type": "text", "text": "I"}),
    update("agent_thought_chunk", content={"type": "text", "text": " will list"}),
    update("tool_call", toolCallId="call-list", title="list_dir",
           rawInput={"target_directory": "."}),
    update("tool_call_update", toolCallId="call-list", title="List `.`", kind="other",
           rawInput={"target_directory": ".", "variant": "tool"},
           locations=[{"path": "/tmp/acp-probe"}]),
    update("tool_call_update", toolCallId="call-list", status="completed",
           rawOutput={"entries": []}),
    update("agent_thought_chunk", content={"type": "text", "text": "Now answer"}),
    update("agent_message_chunk", content={"type": "text", "text": "tool"}),
    update("agent_message_chunk", content={"type": "text", "text": "-ok"}),
    update("turn_completed", method="_x.ai/session_notification", stop_reason="end_turn",
           usage={
               "inputTokens": 26797, "outputTokens": 81, "totalTokens": 26878,
               "cachedReadTokens": 24448, "reasoningTokens": 73,
               "modelUsage": {
                   "grok-4.5-build": {
                       "inputTokens": 26797, "outputTokens": 81,
                       "cachedReadTokens": 24448,
                   },
               },
           }),
]


def carried(lines=None, session="session-one") -> tuple:
    seen = {"session": session, "ended": False}
    said = []
    for line in lines if lines is not None else STREAM:
        said.extend(grok.records(line, seen))
    return said, seen


def only(said: list, kind: str) -> list:
    return [one for one in said if one["type"] == kind]


class WhatTheACPStreamSaysBack(unittest.TestCase):
    def setUp(self):
        self.said, self.seen = carried()

    def test_a_tool_and_its_result_are_reported_with_the_same_id(self):
        """R-PRV-8 — the activity the one-shot stream discarded is present in ACP."""
        self.assertEqual([{
            "type": "tool", "id": "call-list", "name": "list_dir", "did": "list",
        }], only(self.said, "tool"))
        self.assertEqual("call-list", only(self.said, "result")[0]["id"])
        self.assertTrue(only(self.said, "result")[0]["ok"])

    def test_token_sized_thoughts_are_one_activity_per_reasoning_phase(self):
        """R-DIS-20 — a visible tool separates two reasoning phases."""
        thoughts = only(self.said, "think")
        self.assertEqual(2, len(thoughts))
        self.assertEqual(["I", "Now answer"], [one["text"] for one in thoughts])

    def test_a_reply_still_being_written_is_never_called_finished(self):
        spoken = only(self.said, "text")
        self.assertEqual(["tool", "-ok"], [one["text"] for one in spoken])
        for one in spoken:
            self.assertNotIn(provider.WHOLE, one)

    def test_acp_input_has_cached_tokens_subtracted_back_out(self):
        """ACP includes cache reads in input, unlike Grok's one-shot stream."""
        counted = only(self.said, "usage")[0]
        self.assertEqual(2349, counted["input"])
        self.assertEqual(24448, counted["cached"])
        self.assertEqual(81, counted["output"])
        self.assertEqual("grok-4.5-build", counted["model"])
        self.assertEqual(26878, counted["input"] + counted["cached"] + counted["output"])

    def test_a_turn_making_several_requests_reports_the_level_it_ended_at_and_not_the_sum(self):
        """R-USE-15 — ACP's metadata is a running context gauge, not turn billing."""
        said, _ = carried([
            update("agent_message_chunk", meta={"totalTokens": 18000},
                   content={"type": "text", "text": "working"}),
            update("agent_message_chunk", meta={"totalTokens": 24000},
                   content={"type": "text", "text": "done"}),
            STREAM[-1],
        ])
        session = only(said, "usage")[0]["session"]
        self.assertEqual(24000, session)
        self.assertNotEqual(42000, session)

    def test_a_compacted_conversation_is_reported_smaller_than_the_one_before_it(self):
        """R-USE-15 — the last gauge replaces the earlier one even when it decreases."""
        said, _ = carried([
            update("agent_message_chunk", meta={"totalTokens": 48000},
                   content={"type": "text", "text": "before"}),
            update("agent_message_chunk", meta={"totalTokens": 12000},
                   content={"type": "text", "text": "after"}),
            STREAM[-1],
        ])
        self.assertEqual(12000, only(said, "usage")[0]["session"])

    def test_a_subagents_own_conversation_is_not_where_this_turn_ended(self):
        """R-USE-14 — another ACP session cannot replace the parent's context gauge."""
        said, _ = carried([
            update("agent_message_chunk", meta={"totalTokens": 24000},
                   content={"type": "text", "text": "parent"}),
            update("agent_message_chunk", session="child-session",
                   meta={"totalTokens": 900000},
                   content={"type": "text", "text": "child"}),
            STREAM[-1],
        ])
        self.assertEqual(24000, only(said, "usage")[0]["session"])

    def test_the_resume_handle_is_the_session_the_protocol_used(self):
        ended = only(self.said, "done")
        self.assertEqual(1, len(ended))
        self.assertTrue(ended[0]["ok"])
        self.assertEqual("session-one", ended[0]["session"])

    def test_everything_reported_is_a_record_the_seam_knows(self):
        for one in self.said:
            self.assertIn(one["type"], provider.RECORDS)
            self.assertIsNotNone(provider.understood(json.dumps(one)))


class WhatAScheduledTurnOnThisBrainDelivers(unittest.TestCase):
    """R-SCH-45 on the adapter that refuses `whole` on purpose.

    The records here are this adapter's own, not a shape invented in `test_turn`: a reply
    written a token at a time, on both sides of one tool call. Read on `whole` alone the
    close of a scheduled turn is the whole turn — narration, no separator and all — which
    is exactly the defect the close exists to fix, arriving on the brains that never mark
    a finished thought.
    """

    def setUp(self):
        self.said, _ = carried([
            update("agent_message_chunk", content={"type": "text", "text": "I'll read "}),
            update("agent_message_chunk",
                   content={"type": "text", "text": "the instructions."}),
            update("tool_call", toolCallId="call-read", title="read_file"),
            update("tool_call_update", toolCallId="call-read", status="completed"),
            update("agent_message_chunk", content={"type": "text", "text": "Done. "}),
            update("agent_message_chunk", content={"type": "text", "text": "One report."}),
        ])

    def test_a_scheduled_turn_on_this_brain_says_its_report_and_not_its_working(self):
        self.assertEqual("Done. One report.", turn._close(self.said))

    def test_what_a_watched_turn_says_keeps_both_and_does_not_fuse_them(self):
        """R-PRV-22 — the guard on the one above. Everything is still delivered to whoever
        asked, and the two runs of fragments are two paragraphs rather than
        `the instructions.Done.`"""
        self.assertEqual("I'll read the instructions.\n\nDone. One report.",
                         turn._reply(self.said))


class ToolVocabulary(unittest.TestCase):
    def test_known_tools_use_words_no_provider_owns(self):
        expected = {
            "read_file": "read",
            "list_dir": "list",
            "grep": "search",
            "run_terminal_command": "run",
            "edit_file": "edit",
            "search_replace": "edit",
            "write": "make",
            "create_file": "make",
        }
        lines = [
            update("tool_call", toolCallId=f"id-{n}", title=name)
            for n, name in enumerate(expected)
        ]
        tools = only(carried(lines)[0], "tool")
        self.assertEqual(expected, {one["name"]: one["did"] for one in tools})

    def test_an_unknown_tool_is_not_given_a_guessed_verb(self):
        tools = grok.records(
            update("tool_call", toolCallId="new", title="future_tool"),
            {"session": "s"},
        )
        self.assertEqual("future_tool", tools[0]["name"])
        self.assertNotIn("did", tools[0])

    def test_an_intermediate_update_is_not_a_result(self):
        said = grok.records(update(
            "tool_call_update", toolCallId="one", title="Read `a`", kind="read",
            locations=[{"path": "a"}],
        ), {"session": "s"})
        self.assertEqual([], said)

    def test_each_terminal_update_is_reported_once(self):
        line = update("tool_call_update", toolCallId="one", status="completed",
                      rawOutput={"answer": "ok"})
        seen = {"session": "s"}
        first = grok.records(line, seen)
        second = grok.records(line, seen)
        self.assertEqual(["tool", "result"], [one["type"] for one in first])
        self.assertEqual("one", first[0]["id"])
        self.assertEqual("one", first[1]["id"])
        self.assertEqual([], second)

    def test_failed_and_cancelled_tools_are_not_called_successful(self):
        for status in ("failed", "cancelled"):
            said = grok.records(update(
                "tool_call_update", toolCallId=status, status=status,
                rawOutput={"message": status},
            ), {"session": "s"})
            self.assertFalse(only(said, "result")[0]["ok"])

    def test_a_result_summary_is_bounded(self):
        said = grok.records(update(
            "tool_call_update", toolCallId="one", status="failed",
            rawOutput={"private": "x" * 1000},
        ), {"session": "s"})
        self.assertLessEqual(len(only(said, "result")[0]["summary"]), grok.SUMMARY_CHARS)


class WhenTheStreamGoesWrong(unittest.TestCase):
    def test_a_turn_that_did_not_end_cleanly_is_not_called_ok(self):
        for stopped in ("max_turns", "aborted", "refusal", ""):
            said = grok.records(update(
                "turn_completed", method="_x.ai/session_notification",
                stop_reason=stopped, usage={"inputTokens": 1, "outputTokens": 1},
            ), {"session": "s"})
            ended = only(said, "done")[0]
            self.assertFalse(ended["ok"])
            self.assertIn("why", ended)

    def test_a_stream_that_stops_without_an_ending_says_no_done_record(self):
        said, seen = carried(STREAM[:-1])
        self.assertEqual([], only(said, "done"))
        self.assertFalse(seen.get("ended"))

    def test_a_terminal_response_without_usage_does_not_invent_zero_cost(self):
        ended = grok._finished("end_turn", {"session": "s"})
        self.assertEqual({"type": "done", "ok": True, "session": "s"}, ended)
        self.assertNotIn("usage", ended)

    def test_a_stream_without_context_metadata_claims_no_session_size(self):
        """R-USE-16 — billing totals are not substituted for an absent context gauge."""
        said = grok.records(STREAM[-1], {"session": "session-one"})
        self.assertNotIn("session", only(said, "usage")[0])

    def test_a_line_that_is_not_an_acp_update_is_understood_as_nothing(self):
        lines = (
            '{"method":"session/update"',
            "[1,2,3]",
            "42",
            "",
            "not json",
            json.dumps({"jsonrpc": "2.0", "id": 1, "result": {}}),
            update("plan"),
        )
        for line in lines:
            self.assertEqual([], grok.records(line, {"session": "x"}))

    def test_a_turn_that_named_no_model_leaves_none_claimed(self):
        said = grok.records(update(
            "turn_completed", method="_x.ai/session_notification",
            stop_reason="end_turn",
            usage={"inputTokens": 1, "outputTokens": 1, "cachedReadTokens": 0},
        ), {"session": "s"})
        self.assertNotIn("model", only(said, "usage")[0])


class WhatTheAdapterDecidesOnItsOwn(unittest.TestCase):
    def setUp(self):
        self.was = os.environ.get("RUNDESK_PREFACE")
        self.addCleanup(self._put_back)

    def _put_back(self):
        if self.was is None:
            os.environ.pop("RUNDESK_PREFACE", None)
        else:
            os.environ["RUNDESK_PREFACE"] = self.was

    def opening(self, posture="work", model=None, extra=None, preface=None):
        if preface is None:
            os.environ.pop("RUNDESK_PREFACE", None)
        else:
            os.environ["RUNDESK_PREFACE"] = preface
        return grok.opening(posture, model, extra or {})

    def test_tools_are_approved_headlessly_without_the_ignored_mode(self):
        for posture in ("read", "work"):
            argv = self.opening(posture=posture)
            self.assertNotIn("dontAsk", argv)
            self.assertEqual("bypassPermissions",
                             argv[argv.index("--permission-mode") + 1])
            self.assertEqual(["agent", "--always-approve", "stdio"], argv[-3:])

    def test_cross_session_memory_and_background_updates_are_off(self):
        argv = self.opening()
        self.assertIn("--no-memory", argv)
        self.assertIn("--no-auto-update", argv)

    def test_a_flag_that_enforces_nothing_is_never_passed(self):
        for posture in ("read", "work"):
            self.assertNotIn("--sandbox", self.opening(posture=posture))
        passing = re.findall(r"^[^#\n]*[\"']--sandbox[\"']", AT.read_text(), re.M)
        self.assertEqual([], passing)

    def test_a_read_turn_gets_only_the_measured_read_tools(self):
        argv = self.opening(posture="read")
        self.assertEqual(
            ["read_file", "list_dir", "grep"],
            argv[argv.index("--tools") + 1].split(","),
        )
        self.assertNotIn("run_terminal_command", argv[argv.index("--tools") + 1])

    def test_a_work_turn_gets_every_builtin(self):
        self.assertNotIn("--tools", self.opening())

    def test_standing_instructions_are_not_left_on_the_ignored_root_command(self):
        argv = self.opening(preface="Public room.")
        self.assertNotIn("--rules", argv)
        self.assertNotIn("--system-prompt-override", argv)

    def test_a_turn_with_nothing_standing_adds_no_root_prompt_flag(self):
        self.assertNotIn("--rules", self.opening(preface=None))
        self.assertNotIn("--rules", self.opening(preface="   \n "))

    def test_what_somebody_asked_is_never_an_argument(self):
        secret = "words-that-belong-only-on-stdin"
        argv = self.opening(extra={"flags": ["--reasoning-effort", "high"]})
        self.assertNotIn(secret, argv)
        self.assertNotIn("-p", argv)
        self.assertNotIn("--prompt-file", argv)
        self.assertNotIn("--output-format", argv)

    def test_what_an_owner_set_reaches_the_brain_before_the_subcommand(self):
        argv = self.opening(extra={"flags": ["--reasoning-effort", "high"]})
        self.assertEqual(
            ["--reasoning-effort", "high"],
            argv[argv.index("agent") - 2:argv.index("agent")],
        )

    def test_what_an_owner_set_wrongly_is_said_rather_than_guessed_at(self):
        self.assertEqual([], grok._flags({"flags": "--effort high"}))
        self.assertEqual([], grok._flags({"flags": [1, 2]}))

    def test_a_model_nobody_asked_for_is_not_claimed(self):
        self.assertNotIn("-m", self.opening())
        argv = self.opening(model="a-model")
        self.assertEqual("a-model", argv[argv.index("-m") + 1])


FAKE_GROK = r'''#!/usr/bin/env python3
import json, os, sys

log = os.environ["FAKE_GROK_LOG"]

def send(message):
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()

def note(kind, **fields):
    send({"jsonrpc":"2.0", "method":"session/update",
          "params":{"sessionId":"new-session",
                    "update":{"sessionUpdate":kind, **fields}}})

for line in sys.stdin:
    request = json.loads(line)
    with open(log, "a", encoding="utf-8") as kept:
        kept.write(json.dumps({"method":request.get("method"),
                               "params":request.get("params")}) + "\n")
    at = request["id"]
    method = request["method"]
    if method == "initialize":
        result = {"authMethods":[{"id":"cached_token"}],
                  "_meta":{"defaultAuthMethodId":"cached_token"}}
    elif method == "authenticate":
        result = {}
    elif method == "session/new":
        result = {"sessionId":"new-session"}
    elif method == "session/load":
        note("agent_message_chunk", content={"type":"text","text":"old reply"})
        send({"jsonrpc":"2.0", "method":"_x.ai/session_notification",
              "params":{"sessionId":"new-session",
                        "update":{"sessionUpdate":"turn_completed",
                                  "stop_reason":"end_turn",
                                  "usage":{"inputTokens":99,"cachedReadTokens":90,
                                           "outputTokens":9}}}})
        result = {}
    elif method == "session/prompt":
        note("agent_thought_chunk", content={"type":"text","text":"working"})
        note("tool_call", toolCallId="tool-1", title="run_terminal_command",
             rawInput={"command":"true"})
        note("tool_call_update", toolCallId="tool-1", status="completed",
             rawOutput={"exitCode":0})
        note("agent_message_chunk", content={"type":"text","text":"done"})
        send({"jsonrpc":"2.0", "method":"_x.ai/session_notification",
              "params":{"sessionId":"new-session",
                        "update":{"sessionUpdate":"turn_completed",
                                  "stop_reason":"end_turn",
                                  "usage":{"inputTokens":10,"cachedReadTokens":6,
                                           "outputTokens":2,
                                           "modelUsage":{"grok-test":{}}}}}})
        result = {"stopReason":"end_turn"}
    else:
        send({"jsonrpc":"2.0","id":at,
              "error":{"code":-32601,"message":"unknown method"}})
        continue
    send({"jsonrpc":"2.0","id":at,"result":result})
'''


class TheWholeACPConversation(unittest.TestCase):
    def setUp(self):
        self.where = Path(tempfile.mkdtemp(prefix="rundesk-grok-test-"))
        self.addCleanup(self._remove)
        self.fake = self.where / "fake-grok"
        self.fake.write_text(FAKE_GROK, encoding="utf-8")
        self.fake.chmod(0o700)
        self.log = self.where / "protocol.jsonl"

    def _remove(self):
        for path in sorted(self.where.rglob("*"), reverse=True):
            if path.is_symlink() or path.is_file():
                path.unlink()
            elif path.is_dir():
                path.rmdir()
        self.where.rmdir()

    def run_adapter(self, resume=None, preface="Standing rule."):
        env = dict(os.environ)
        env.update({
            "RUNDESK_GROK_BIN": str(self.fake),
            "RUNDESK_CWD": str(self.where),
            "RUNDESK_PROVIDER_HOME": str(self.where / "provider"),
            "RUNDESK_POSTURE": "work",
            "RUNDESK_RUN": "one",
            "FAKE_GROK_LOG": str(self.log),
        })
        if preface is None:
            env.pop("RUNDESK_PREFACE", None)
        else:
            env["RUNDESK_PREFACE"] = preface
        if resume is None:
            env.pop("RUNDESK_RESUME", None)
        else:
            env["RUNDESK_RESUME"] = resume
        done = subprocess.run(
            [str(AT)], input="do one thing", text=True, capture_output=True,
            env=env, cwd=self.where, timeout=20,
        )
        records = [json.loads(line) for line in done.stdout.splitlines()]
        protocol = [json.loads(line) for line in self.log.read_text().splitlines()]
        return done, records, protocol

    def test_a_new_turn_authenticates_creates_prompts_and_reports_everything(self):
        done, said, protocol = self.run_adapter()
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(
            ["initialize", "authenticate", "session/new", "session/prompt"],
            [one["method"] for one in protocol],
        )
        self.assertEqual(
            ["think", "tool", "result", "text", "usage", "done"],
            [one["type"] for one in said],
        )
        self.assertEqual("run", only(said, "tool")[0]["did"])
        self.assertEqual("new-session", only(said, "done")[0]["session"])
        self.assertEqual(4, only(said, "usage")[0]["input"])
        self.assertEqual(6, only(said, "usage")[0]["cached"])

    def test_a_new_conversation_appends_standing_instructions_through_acp(self):
        """R-PRV-23 — Grok receives standing rules separately from what was asked."""
        _, _, protocol = self.run_adapter(preface="Locked Rundesk rule.")
        created = next(one for one in protocol if one["method"] == "session/new")
        self.assertEqual(
            {"rules": "Locked Rundesk rule."},
            created["params"]["_meta"],
        )

    def test_a_new_conversation_with_no_standing_instructions_has_no_meta(self):
        _, _, protocol = self.run_adapter(preface=None)
        created = next(one for one in protocol if one["method"] == "session/new")
        self.assertNotIn("_meta", created["params"])

    def test_a_resume_loads_exactly_that_session_instead_of_making_one(self):
        done, said, protocol = self.run_adapter("old-session")
        self.assertEqual(0, done.returncode, done.stderr)
        methods = [one["method"] for one in protocol]
        self.assertIn("session/load", methods)
        self.assertNotIn("session/new", methods)
        loaded = next(one for one in protocol if one["method"] == "session/load")
        prompted = next(one for one in protocol if one["method"] == "session/prompt")
        self.assertEqual("old-session", loaded["params"]["sessionId"])
        self.assertEqual("old-session", prompted["params"]["sessionId"])
        self.assertNotIn("_meta", loaded["params"])
        self.assertEqual("old-session", only(said, "done")[0]["session"])
        self.assertNotIn("old reply", [one.get("text") for one in said])
        self.assertEqual(1, len(only(said, "done")))
        self.assertEqual(4, only(said, "usage")[0]["input"])

    def test_the_prompt_travels_in_the_protocol_and_not_the_process_arguments(self):
        _, _, protocol = self.run_adapter()
        prompted = next(one for one in protocol if one["method"] == "session/prompt")
        self.assertEqual("do one thing", prompted["params"]["prompt"][0]["text"])


class WhatThisBrainCanDo(unittest.TestCase):
    def test_it_says_what_it_can_do_and_every_answer_is_yes_or_no(self):
        self.assertEqual(sorted(provider.CAPABILITIES), sorted(grok.CAN))
        for said in grok.CAN.values():
            self.assertIsInstance(said, bool)

    def test_it_claims_tools_resume_usage_and_model_but_not_steering(self):
        self.assertTrue(grok.CAN["tools"])
        self.assertTrue(grok.CAN["resume"])
        self.assertTrue(grok.CAN["usage"])
        self.assertTrue(grok.CAN["model"])
        self.assertFalse(grok.CAN["steer"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
