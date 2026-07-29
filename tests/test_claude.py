"""Claude Code, as the brain rundesk ships an adapter for.

**Nothing here starts claude.** What is driven is `tests/samples/claude-stream.jsonl` — 184
lines of real output, captured once against a real account, committed because it cost money
and cannot be re-derived by reading anything. So this suite needs no account, no token and
no network, and it still holds the adapter to what a real brain actually said.

What is tested is the arithmetic and the policy the adapter decides on its own, which is
where every expensive mistake in this stream lives: the reply arrives twice and reporting
both doubles every answer; three lines carry a usage block and only one of them is the
turn; two token fields are billed differently and summing them reports a number that is
real and misleading; and a posture is the allowlist rather than the mode.

The adapter is loaded by path rather than imported as a module, because it is not one: it
is a program, which is the whole point of the seam.

Run: python3 tests/test_claude.py
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import io
import json
import os
import re
import sys
import tempfile
import threading
import textwrap
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from rundesk import provider  # noqa: E402  — after the path is set, as every suite here does

AT = ROOT / "src" / "providers" / "claude"
GOLDEN = ROOT / "tests" / "samples" / "claude-stream.jsonl"


def _adapter():
    """The adapter, loaded from its path — it is a program, not a module."""
    loader = importlib.machinery.SourceFileLoader("rundesk_claude", str(AT))
    spec = importlib.util.spec_from_loader("rundesk_claude", loader)
    made = importlib.util.module_from_spec(spec)
    loader.exec_module(made)
    return made


claude = _adapter()


def carried(lines=None) -> tuple:
    """The whole golden stream, as the records the adapter makes of it.

    Returns what it reported and what it learned along the way, which is the same pair the
    adapter itself carries — so a case can assert on either without starting anything.
    """
    seen = {"session": "minted-before-the-first-byte", "model": None, "ended": False}
    said = []
    for line in (lines if lines is not None else GOLDEN.read_text(encoding="utf-8").splitlines()):
        said.extend(claude.records(line, seen))
    return said, seen


def only(said: list, kind: str) -> list:
    return [one for one in said if one["type"] == kind]


class Sink:
    """A text pipe whose contents remain inspectable after the writer closes it."""

    def __init__(self):
        self.text = ""

    def write(self, said: str) -> None:
        self.text += said

    def flush(self) -> None:
        pass

    def close(self) -> None:
        pass

    def getvalue(self) -> str:
        return self.text


class WhatTheGoldenSaysBack(unittest.TestCase):
    """The stream, driven end to end, as the seam's own records."""

    def setUp(self):
        self.said, self.seen = carried()

    def test_the_reply_is_reported_once_and_never_twice(self):
        """The single most expensive mistake this stream invites, and it is invisible: the
        turn looks right and says everything twice. Ten `text_delta` fragments and three
        whole `assistant` blocks carry the same 574 bytes, and a turn joins every `text`
        record it is given."""
        spoken = "".join(one["text"] for one in only(self.said, "text"))
        self.assertEqual(574, len(spoken), "the reply was reported twice, or not at all")

        # The other copy, taken straight off the stream rather than off the adapter, so
        # this case fails if the *stream* ever stops carrying both rather than only if the
        # adapter stops choosing.
        fragments = []
        for line in GOLDEN.read_text(encoding="utf-8").splitlines():
            one = json.loads(line)
            if one.get("type") != "stream_event":
                continue
            delta = one.get("event", {}).get("delta", {})
            if delta.get("type") == "text_delta":
                fragments.append(delta.get("text", ""))
        self.assertEqual("".join(fragments), spoken,
                         "the two copies have stopped agreeing, so one of them changed")

    def test_every_complete_thing_it_said_is_marked_as_finished(self):
        """R-PRV-22. This brain says several complete things as it works — 'I'll set up the
        plan first', then later the answer — and marking each one lets a surface show it as
        it is said instead of delivering the lot at the end."""
        spoken = only(self.said, "text")
        self.assertEqual(3, len(spoken), "the three finished thoughts are not three records")
        for one in spoken:
            self.assertIs(True, one.get(provider.WHOLE), f"{one['text'][:40]!r} was not whole")

    def test_what_a_turn_cost_is_read_from_one_line_and_nowhere_else(self):
        """Three lines in this stream carry a full usage block — `message_start`,
        `message_delta` and `result`. Counting the framing ones as well is how a turn ends
        up reporting many times what it cost."""
        counted = only(self.said, "usage")
        self.assertEqual(1, len(counted), "usage was taken from more than the result line")
        self.assertEqual(1510, counted[0]["output"])

    def test_four_billed_quantities_are_reported_in_four_slots(self):
        """R-USE-13. The captured turn carries 20 fresh, 17,453 written into the cache and
        302,567 read back from it — three prices, and this vendor is the only shipped brain
        that reports all three. Summing any two of them into one slot reports a number that
        is real and misleading; this used to add the first two, so 20 fresh tokens were
        recorded as 17,473 input."""
        counted = only(self.said, "usage")[0]
        self.assertEqual(20, counted["input"], "cache writes are folded into fresh input")
        self.assertEqual(17453, counted["written"], "what was written to cache is not kept")
        self.assertEqual(302567, counted["cached"], "the cheap volume is not being kept apart")
        self.assertNotEqual(20 + 17453, counted["input"])
        self.assertNotEqual(20 + 17453 + 302567, counted["input"])

    def test_account_state_a_brain_volunteers_is_reported_as_a_limit(self):
        """R-PRV-28. The captured stream carries one of these and this adapter used to drop
        it — on reasoning that was right as far as it went, that it is account state rather
        than this turn's activity, and wrong only in that account state had nowhere to go.
        What reached an owner instead was whatever prose could be scraped after the fact."""
        found = only(self.said, "limit")
        self.assertEqual(1, len(found), "the account state on this stream was dropped")
        self.assertEqual("rate", found[0]["of"])
        self.assertEqual("five_hour", found[0]["scope"])
        self.assertEqual(1784920200, found[0]["resets_at"])

    def test_an_allowance_that_is_merely_allowed_reports_no_state(self):
        """`allowed` is the ordinary condition of an account and says nothing worth telling
        an owner. `near` and `reached` are the two that are worth saying, so a stream that
        only ever says `allowed` reports the window and its reset without claiming either."""
        self.assertNotIn("state", only(self.said, "limit")[0])

    def test_a_turn_carrying_a_limit_is_not_a_turn_that_failed(self):
        """The distinction that makes this a record of its own rather than an outcome: the
        captured turn reports an allowance *and* succeeds, so anything treating one as a
        failure would fail every turn on an account that reports its state at all."""
        self.assertTrue(only(self.said, "done")[0]["ok"])

    def test_a_limit_a_brain_never_mentions_is_never_invented(self):
        """R-USE-6's reasoning at the seam. A stream with no account state on it reports
        none, rather than an `of: rate` with everything about it unknown."""
        self.assertEqual([], claude.records('{"type":"system","subtype":"init"}', {}))
        self.assertEqual([], claude.records('{"type":"rate_limit_event"}', {}))

    def test_a_turn_stopped_for_a_reason_the_seam_has_a_word_for_records_that_word(self):
        """R-RUN-19. This vendor puts a limit-stopped turn on an ordinary `result` line with
        `is_error` — the same shape as a crash, a bad flag or a refusal — so the prose is
        the only place the kind of failure appears. Matching it is weak evidence and is
        treated as such: what is not recognised stays unclassified."""
        for said, word in (
            ("Claude AI usage limit reached|1784920200", "usage_exhausted"),
            ("rate limit exceeded, please try again later", "rate_limited"),
            ("Your credit balance is too low to run this", "no_credit"),
            ("Invalid API key · Please run /login", "signed_out"),
            ("prompt is too long: 400000 tokens > 200000 maximum", "context_exceeded"),
        ):
            ending = claude.records(json.dumps(
                {"type": "result", "is_error": True, "result": said}), {})
            done = [one for one in ending if one["type"] == "done"][0]
            self.assertEqual(word, done.get("because"), said)
            self.assertEqual(said, done["why"], "the brain's own words were replaced")

    def test_a_failure_this_adapter_cannot_classify_says_nothing_rather_than_guessing(self):
        """The guard on the one above, and the whole reason the phrases are kept narrow. A
        wrong word inside a total cannot be seen; an absent one can."""
        ending = claude.records(json.dumps(
            {"type": "result", "is_error": True, "result": "the parser exploded"}), {})
        done = [one for one in ending if one["type"] == "done"][0]
        self.assertNotIn("because", done)
        self.assertEqual("the parser exploded", done["why"])

    def test_the_model_that_answered_is_named(self):
        """R-PRV-9. Reported rather than requested: a silent substitution shows up here."""
        self.assertEqual("claude-opus-5[1m]", only(self.said, "usage")[0]["model"])

    def test_every_tool_call_is_paired_with_what_it_returned(self):
        """Thirteen calls, thirteen results, and the brain's own ids carried through
        untouched so the two can be put back together by whoever reads the run."""
        called = only(self.said, "tool")
        returned = only(self.said, "result")
        self.assertEqual(13, len(called))
        self.assertEqual([one["id"] for one in called], [one["id"] for one in returned])
        self.assertTrue(all(one["id"].startswith("toolu_") for one in called))

    def test_a_tool_is_reported_by_what_it_did_and_never_by_its_brains_name_for_it(self):
        """R-PRV-8 and R-PRV-21. `did` is one of a closed set of words no brain owns, and a
        tool whose work is not one of them leaves it out rather than stretching one to fit
        — `name` still carries this vendor's own word either way."""
        for one in only(self.said, "tool"):
            self.assertIn("name", one)
            if "did" in one:
                self.assertIn(one["did"], provider.DID)
        did = {one["name"]: one.get("did") for one in only(self.said, "tool")}
        self.assertEqual("run", did["Bash"])
        self.assertEqual("read", did["Read"])
        self.assertEqual("search", did["ToolSearch"])
        self.assertIsNone(did["TaskCreate"], "a tool with no verb here claimed one anyway")

    def test_a_line_kind_nobody_mapped_is_reported_as_nothing(self):
        """R-PRV-5 from the adapter's side. Framing, status churn and a reasoning meter are
        dropped deliberately — and the raw stream is kept beside the run either way, so a
        vendor changing shape is visible as drift.

        The account's rate-limit state used to be dropped here too, and is now a `limit`
        record: it was never unmappable, only unhoused (R-PRV-28)."""
        for line in GOLDEN.read_text(encoding="utf-8").splitlines():
            one = json.loads(line)
            if one.get("type") == "stream_event":
                self.assertEqual([], claude.records(line, dict(self.seen)))
            if one.get("type") == "system" and one.get("subtype") in ("status", "thinking_tokens"):
                self.assertEqual([], claude.records(line, dict(self.seen)))

    def test_everything_reported_is_a_record_the_seam_knows(self):
        """The adapter cannot emit a kind rundesk would keep and show to nobody: every one
        of these is checked against the seam's own list rather than against a copy."""
        for one in self.said:
            self.assertIn(one["type"], provider.RECORDS)
            self.assertIsNotNone(provider.understood(json.dumps(one)))

    def test_the_turn_says_it_finished_and_hands_back_a_handle(self):
        said = only(self.said, "done")
        self.assertEqual(1, len(said))
        self.assertTrue(said[0]["ok"])
        self.assertEqual("ab594a62-5488-4b74-9b63-8886aaa826dd", said[0]["session"])


class WhenTheStreamGoesWrong(unittest.TestCase):
    """The paths a captured happy turn cannot reach."""

    def test_a_stream_that_stops_without_an_ending_says_so_rather_than_going_quiet(self):
        """A child that dies before its `result` line has said nothing terminal, and
        whatever is waiting on the turn would wait for ever. The adapter is what notices."""
        lines = GOLDEN.read_text(encoding="utf-8").splitlines()[:-1]
        said, seen = carried(lines)
        self.assertEqual([], only(said, "done"))
        self.assertFalse(seen["ended"], "the adapter thinks a truncated stream ended")

    def test_a_turn_the_brain_says_failed_is_not_reported_as_having_worked(self):
        """R-PRV-6. `done.ok` is what the brain made of the turn, and a reason comes with
        it — one actionable line, rather than a failure filed where nobody looks."""
        said = claude.records(json.dumps({
            "type": "result", "subtype": "error_during_execution", "is_error": True,
            "session_id": "a-session", "result": "the model refused",
            "usage": {"input_tokens": 5, "output_tokens": 0}}), {"session": "a-session"})
        ended = [one for one in said if one["type"] == "done"][0]
        self.assertFalse(ended["ok"])
        self.assertEqual("the model refused", ended["why"])

    def test_a_turn_that_failed_hands_back_no_handle_to_carry_on_from(self):
        """The bug this prevents was reproduced in production, and it is permanent once it
        happens: this brain mints a session id even for a turn that fails, but no
        conversation is created — so reporting the handle makes *every* turn afterwards
        resume something that was never there. Not reporting one costs the next turn its
        context and nothing else, which is the cheaper of the two."""
        said = claude.records(json.dumps({
            "type": "result", "subtype": "error_during_execution", "is_error": True,
            "session_id": "a-session-that-does-not-exist", "result": "it went wrong",
            "usage": {}}), {"session": "a-session-that-does-not-exist", "model": None})
        ended = [one for one in said if one["type"] == "done"][0]
        self.assertNotIn("session", ended, "a failed turn handed back a handle")

    def test_a_turn_that_worked_hands_back_the_handle_it_was_given(self):
        said = claude.records(json.dumps({
            "type": "result", "subtype": "success", "is_error": False,
            "session_id": "a-real-session", "usage": {}}), {"session": "a-real-session"})
        self.assertEqual("a-real-session",
                         [one for one in said if one["type"] == "done"][0]["session"])

    def test_a_conversation_that_has_gone_is_told_apart_from_a_turn_that_failed(self):
        """Losing a handle costs a turn its context, which is what losing one is supposed
        to cost; it must not cost the turn. Telling the two apart is the whole of that, and
        this brain makes it awkward: it says `No conversation found with session ID` on
        **stderr** while its result line says only `error_during_execution`."""
        self.assertTrue(claude._lost({"ok": False, "why": "No conversation found with session ID: x"}))
        self.assertFalse(claude._lost({"ok": False, "why": "the model refused"}))
        self.assertFalse(claude._lost({"ok": True, "why": "No conversation found"}),
                         "a turn that worked was read as a lost conversation")
        self.assertFalse(claude._lost({"ok": False}))

    def test_being_logged_out_is_carried_where_the_adapter_will_look_for_it(self):
        """Measured at 2.1.220, and the reason this is not left to stderr: having no login
        arrives as an ordinary failed turn on the `result` line. An adapter watching only
        the stream it was told errors go on would report the failure and never say what to
        run about it."""
        seen = {"session": "s", "model": None, "ended": False}
        said = claude.records(json.dumps({
            "type": "result", "subtype": "error_during_execution", "is_error": True,
            "session_id": "s", "result": "Not logged in · Please run /login",
            "usage": {}}), seen)
        self.assertFalse([one for one in said if one["type"] == "done"][0]["ok"])
        self.assertIn("not logged in", (seen.get("why") or "").lower())
        self.assertTrue(any(one in seen["why"].lower() for one in claude.LOGGED_OUT))

    def test_a_line_that_is_not_a_record_at_all_is_understood_as_nothing(self):
        """Nothing an upstream writes can break a turn here: a half-written line, a bare
        array and a number are all simply not records."""
        for said in ('{"type":"assis', "[1,2,3]", "42", "", "   ", "not json at all"):
            self.assertEqual([], claude.records(said, {"session": "x"}))

    def test_a_thought_this_brain_left_empty_is_not_reported_as_one(self):
        """Measured: every captured thinking block carries an empty string, so the shape is
        proven and the content is not. Reporting an empty thought would show a reader that
        the agent thought nothing, which is not what an empty field means."""
        empty = json.dumps({"type": "assistant", "session_id": "s", "message": {
            "content": [{"type": "thinking", "thinking": "", "signature": "abc"}]}})
        self.assertEqual([], claude.records(empty, {"session": "s"}))
        real = json.dumps({"type": "assistant", "session_id": "s", "message": {
            "content": [{"type": "thinking", "thinking": "weighing it up"}]}})
        self.assertEqual([{"type": "think", "text": "weighing it up", "whole": True}],
                         claude.records(real, {"session": "s"}))

    def test_what_a_tool_returned_is_shortened_before_it_is_passed_on(self):
        """A tool result can hold a whole file, a command's entire output, a credential or
        a private path. What the account keeps and what a surface shows are different
        decisions, and this is the first of them."""
        long = json.dumps({"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "toolu_1", "content": "x" * 5000}]}})
        said = claude.records(long, {"session": "s"})[0]
        self.assertEqual(claude.SUMMARY_CHARS, len(said["summary"]))
        self.assertTrue(said["ok"])


class WhenItHandsWorkToAHelper(unittest.TestCase):
    def test_a_subagent_spawn_is_reported_as_delegating(self):
        """R-PRV-8, R-PRV-21 — measured 2026-07-27 against 2.1.220: a subagent arrives as a
        tool named `Agent`, and its own steps then stream through the parent as ordinary
        tool calls. Without a verb the only thing marking a delegation at all was this
        vendor's word for it, which is the one thing a channel must never be shown.

        The name is measured rather than read: the documentation describes a `Task` tool,
        and what actually came over the stream was `Agent`.
        """
        self.assertEqual("delegate", claude.DID.get("Agent"))
        self.assertNotIn("Task", claude.DID)

    def test_a_subagent_type_is_carried_as_its_compact_name(self):
        """R-PRV-8 — Claude supplies a helper type without exposing its prompt."""
        real = json.dumps({"type": "assistant", "session_id": "s", "message": {
            "content": [{
                "type": "tool_use", "id": "helper-1", "name": "Agent",
                "input": {
                    "subagent_type": "code-reviewer",
                    "prompt": "private instructions must not be relayed",
                },
            }]
        }})
        self.assertEqual([{
            "type": "tool", "id": "helper-1", "name": "Agent",
            "did": "delegate", "who": "code-reviewer",
        }], claude.records(real, {"session": "s"}))


class WhatTheAdapterDecidesOnItsOwn(unittest.TestCase):
    """The command line, which is where this brain's two traps live."""

    def setUp(self):
        self.was = os.environ.get("RUNDESK_PREFACE")
        self.addCleanup(self._put_back)

    def _put_back(self):
        if self.was is None:
            os.environ.pop("RUNDESK_PREFACE", None)
        else:
            os.environ["RUNDESK_PREFACE"] = self.was

    def told(self, said):
        if said is None:
            os.environ.pop("RUNDESK_PREFACE", None)
        else:
            os.environ["RUNDESK_PREFACE"] = said

    def opening(self, posture="work", model=None, resume=None, extra=None, preface=None):
        self.told(preface)
        return claude.opening(posture, model, resume, extra or {}, "a-minted-id")

    def test_a_turn_asked_to_only_look_is_given_an_allowlist_and_not_a_mode(self):
        """R-PRV-18. Measured: `--permission-mode` is a prompting policy, not containment —
        under `plan` with no allowlist this CLI reached for `Write` and wrote a file outside
        the repository, and `plan` never returned. What holds is which tools exist."""
        argv = self.opening(posture="read")
        self.assertNotIn("--permission-mode", argv)
        allowed = argv[argv.index("--allowedTools") + 1].split(",")
        self.assertNotIn("Bash", allowed)
        self.assertNotIn("Write", allowed)
        self.assertIn("Read", allowed)

    def test_a_working_turn_is_given_no_list_at_all(self):
        """R-PRV-18. A working turn gets everything this brain has, because an allowlist is
        a list and a list cannot stay complete: every tool the CLI gains next release, and
        every tool an MCP server brings, would be one a working turn was refused — silently,
        with the model taking the blame.

        Measured 2026-07-27 against 2.1.220: with the old work list passed and a tool off it
        asked for, the turn was refused it; with the bypass and no list, a `Write` that is on
        no list succeeded."""
        argv = self.opening()
        self.assertIn("--dangerously-skip-permissions", argv)
        self.assertNotIn("--allowedTools", argv)

    def test_only_looking_still_holds(self):
        """The guard on the one above. Widening a working turn is defensible only while the
        posture that exists to be narrow stays narrow — measured against the same CLI, a
        read turn asked to write was refused with 'Permission to use Write has been denied'
        and no file appeared."""
        argv = self.opening(posture="read")
        self.assertIn("--allowedTools", argv)
        self.assertNotIn("--dangerously-skip-permissions", argv)

    def test_the_allowlist_is_one_value_rather_than_many_words(self):
        """`--allowedTools` is variadic and swallows whatever follows it. Passed as many
        words it eats the next flag, and the error it produces points somewhere else
        entirely — measured again while probing this, where it ate the prompt itself and the
        CLI exited saying none had been given. Asked of `read`, which is the posture that
        still carries the flag."""
        argv = self.opening(posture="read")
        after = argv[argv.index("--allowedTools") + 1]
        self.assertNotIn(" ", after, "the allowlist would swallow the flag after it")
        self.assertIn(",", after)

    def test_a_posture_this_adapter_does_not_know_falls_to_the_narrowest_one(self):
        """R-PRV-27. The failure that matters is which way an unknown posture falls. `work`
        on this brain is `--dangerously-skip-permissions`, so falling open turns a typo — or
        a posture the seam gains before this adapter learns it — into a full permission
        bypass on an unattended schedule, with nothing said about it."""
        for unknown in ("reed", "plan", "READ", "read-only", "worrk", "none"):
            said = claude.posture_for(unknown)
            self.assertEqual("read", said, f"{unknown!r} should fall closed, not open")
            argv = self.opening(posture=said)
            self.assertIn("--allowedTools", argv)
            self.assertNotIn("--dangerously-skip-permissions", argv)

    def test_falling_closed_is_said_out_loud_rather_than_done_quietly(self):
        """A turn that lost tools it expected must be explicable. The narrowing goes to the
        stream that is ours, so it reaches whoever reads the run rather than only the log."""
        was, sys.stderr = sys.stderr, io.StringIO()
        try:
            claude.posture_for("reed")
            said = sys.stderr.getvalue()
        finally:
            sys.stderr = was
        self.assertIn("reed", said)
        self.assertIn("read", said)

    def test_the_two_postures_the_seam_has_are_passed_through_untouched(self):
        """The guard on the one above: failing closed must not narrow a posture that is
        perfectly good. An absent or empty posture is the seam's stated default, `work`,
        which is a decision rather than a mistake and is not narrowed either. Blank counts
        as absent, as it does for standing instructions two tests below — a variable set to
        spaces is a variable nobody set."""
        self.assertEqual("work", claude.posture_for("work"))
        self.assertEqual("read", claude.posture_for("read"))
        self.assertEqual("work", claude.posture_for(None))
        self.assertEqual("work", claude.posture_for(""))
        self.assertEqual("work", claude.posture_for("   \t "))

    def test_standing_instructions_are_added_and_never_substituted(self):
        """R-PRV-23. Measured: `--system-prompt` takes about 6,100 tokens of what this
        brain was built with away with it, while the rule still lands and the tools still
        work — so nothing reports the loss and the turn merely behaves differently."""
        argv = self.opening(preface="You are in a room. Others read this.")
        self.assertIn("--append-system-prompt", argv)
        self.assertNotIn("--system-prompt", argv)
        self.assertEqual("You are in a room. Others read this.",
                         argv[argv.index("--append-system-prompt") + 1])

    def test_nothing_in_this_adapter_reaches_for_the_flag_that_replaces(self):
        """Named in a comment saying why not to, which is the point of the comment. What
        must not exist anywhere is a line that *passes* it."""
        passing = re.findall(r"^[^#\n]*[\"']--system-prompt[\"']", AT.read_text(encoding="utf-8"),
                             re.M)
        self.assertEqual([], passing, "something in this adapter passes --system-prompt")

    def test_a_turn_with_nothing_standing_says_nothing(self):
        """An argument meaning nothing is one a brain may do something odd with."""
        self.assertNotIn("--append-system-prompt", self.opening(preface=None))
        self.assertNotIn("--append-system-prompt", self.opening(preface="   \n  "))

    def test_the_stream_this_adapter_asks_for_is_one_the_cli_will_give(self):
        """Measured: `--output-format stream-json` exits 1 under `-p` without `--verbose`,
        and at 2.1.219 the error named only the format."""
        argv = self.opening()
        self.assertIn("--verbose", argv)
        self.assertIn("-p", argv)
        self.assertEqual("stream-json", argv[argv.index("--input-format") + 1])
        self.assertEqual("stream-json", argv[argv.index("--output-format") + 1])

    def test_a_new_conversation_is_named_before_the_first_byte(self):
        """The handle exists before anything is sent, so a turn that dies mid-stream still
        leaves something to carry on from."""
        argv = self.opening()
        self.assertEqual("a-minted-id", argv[argv.index("--session-id") + 1])
        self.assertNotIn("--resume", argv)

    def test_a_conversation_being_carried_on_is_resumed_and_not_renamed(self):
        """`--session-id` names a *new* conversation; passing both would be asking this CLI
        to start and continue the same one."""
        argv = self.opening(resume="an-old-session")
        self.assertEqual("an-old-session", argv[argv.index("--resume") + 1])
        self.assertNotIn("--session-id", argv)

    def test_what_somebody_asked_is_never_an_argument(self):
        """It is readable through the process list otherwise, and kept in a shell's
        history. The prompt goes on stdin, which is also the only place `--allowedTools`
        cannot eat it."""
        argv = self.opening(preface="stand here")
        self.assertNotIn("-p", argv[argv.index("-p") + 1:], "the prompt looks like a flag value")
        self.assertIn("--input-format", argv)

    def test_what_an_owner_set_reaches_the_brain_unread(self):
        """R-PRV-16. Their words for their brain: a new option on this CLI is theirs to
        reach today rather than after a rundesk release."""
        argv = self.opening(extra={"flags": ["--effort", "high"]})
        self.assertEqual(["--effort", "high"], argv[-2:])

    def test_what_an_owner_set_wrongly_is_said_rather_than_guessed_at(self):
        self.assertEqual([], claude._flags({"flags": "--effort high"}))
        self.assertEqual([], claude._flags({"flags": [1, 2]}))
        self.assertEqual([], claude._flags({}))

    def test_a_model_nobody_asked_for_is_not_claimed(self):
        self.assertNotIn("--model", self.opening())
        self.assertEqual("a-model", self.opening(model="a-model")[
            self.opening(model="a-model").index("--model") + 1])


class WhichConfigurationDirectoryATurnUses(unittest.TestCase):
    """Measured at 2.1.220: setting `CLAUDE_CONFIG_DIR` does not redirect this brain's
    login, it removes one — `claude auth status` answers `loggedIn: false` with the
    variable set to the very directory it defaults to. So isolating an agent into a private
    home is, on this brain, the same act as logging it out, and the decision has to be
    asked rather than assumed.

    Driven with the asking replaced, so none of it needs a brain or an account."""

    def answering(self, private, machine):
        return lambda where: private if where else machine

    def test_an_agent_with_a_login_of_its_own_is_kept_to_it(self):
        """The isolated case, and the one worth having: nothing is shared."""
        self.assertEqual("/a/home", claude._config_dir(
            "/a/home", self.answering(private=True, machine=True)))

    def test_an_agent_with_no_login_uses_the_machines_rather_than_failing(self):
        """What the shipped codex adapter does unconditionally — it never sets its own
        home variable at all — so this is the repository's precedent rather than a new
        liberty. It is the difference between an agent that answers and one that cannot
        start, and it is said on stderr rather than done quietly."""
        self.assertIsNone(claude._config_dir(
            "/a/home", self.answering(private=False, machine=True)))

    def test_when_nothing_is_signed_in_the_agent_keeps_its_own_home(self):
        """So the turn fails naming the home to log *in* to, rather than pointing somebody
        at a machine login that does not exist either."""
        self.assertEqual("/a/home", claude._config_dir(
            "/a/home", self.answering(private=False, machine=False)))

    def test_a_turn_with_no_private_home_at_all_leaves_the_variable_alone(self):
        self.assertIsNone(claude._config_dir(None, self.answering(True, True)))

    def test_the_one_thing_this_brain_needs_that_rundesk_does_not_pass_is_supplied(self):
        """`USER` is what this brain's keychain lookup is keyed on, and the environment
        rundesk builds does not carry it — so on a signed-in machine it reports
        `loggedIn: false` with no config directory involved at all. Measured by bisecting:
        `USER` alone flips it, and `LOGNAME`, `SHELL`, `TMPDIR`, `XPC_SERVICE_NAME` and
        `__CF_USER_TEXT_ENCODING` all leave it false.

        It is resolved from the password database rather than read from an environment
        that does not have it, and it lives in this adapter because which variable a brain
        wants is that brain's business — in the core it would be this vendor in the seam."""
        said = claude._whose({"HOME": "/somewhere", "PATH": "/usr/bin"})
        self.assertTrue(said.get("USER"), "the brain is given no account name to look up")
        self.assertEqual("/somewhere", said["HOME"], "the rest of the environment moved")

    def test_an_account_name_rundesk_did_pass_is_left_alone(self):
        self.assertEqual("someone-else",
                         claude._whose({"USER": "someone-else"})["USER"])

    def test_a_brain_that_cannot_answer_the_question_is_read_as_signed_out(self):
        """Anything unreadable fails towards saying what to run, which is recoverable —
        rather than towards silence, which is not."""
        was = claude.CLAUDE
        claude.CLAUDE = "/nonexistent/claude-that-is-not-there"
        self.addCleanup(setattr, claude, "CLAUDE", was)
        self.assertFalse(claude._signed_in(None))


class WhatThisBrainCanDo(unittest.TestCase):
    """R-PRV-15 — declared, and only what was measured."""

    def test_it_says_what_it_can_do_and_every_answer_is_yes_or_no(self):
        self.assertEqual(sorted(provider.CAPABILITIES), sorted(claude.CAN))
        for what, said in claude.CAN.items():
            self.assertIsInstance(said, bool, f"{what} is not a yes or a no")

    def test_it_claims_the_interrupt_protocol_as_mid_turn_steering(self):
        """R-PRV-19. A control interrupt plus a new message changes the active work."""
        self.assertTrue(claude.CAN["steer"])

    def test_the_protocol_initializes_then_interrupts_before_the_later_word(self):
        words = claude.Words("count to ten", io.StringIO(
            '{"type":"say","text":"actually, stop at three"}\n'))
        output, control = Sink(), claude.Control()
        thread = threading.Thread(
            target=claude._fed,
            args=(output, words, claude.threading.Event(), control))
        thread.start()

        def records():
            return [json.loads(line) for line in output.getvalue().splitlines()]

        for request in ("rundesk_1", "rundesk_2"):
            limit = time.monotonic() + 1
            while not any(one.get("request_id") == request for one in records()):
                self.assertLess(time.monotonic(), limit, "the control request was not sent")
                time.sleep(0.001)
            control.heard({"type": "control_response", "response": {
                "subtype": "success", "request_id": request, "response": {}}})
            if request == "rundesk_2":
                self.assertTrue(control.interrupted(),
                                "the interrupted request's result was not drained")
        thread.join(timeout=1)
        self.assertFalse(thread.is_alive())

        said = records()
        self.assertEqual(["control_request", "user", "control_request", "user"],
                         [one["type"] for one in said])
        self.assertEqual("initialize", said[0]["request"]["subtype"])
        self.assertEqual("count to ten", said[1]["message"]["content"])
        self.assertEqual("interrupt", said[2]["request"]["subtype"])
        self.assertEqual("actually, stop at three", said[3]["message"]["content"],
                         "the adapter silently changed what the run recorded")

    def test_an_interrupted_result_is_not_the_end_and_its_usage_is_not_lost(self):
        control = claude.Control()
        control._interrupted_results = 1
        interrupted = {"type": "result", "usage": {
            "input_tokens": 3, "output_tokens": 5}}
        final = {"type": "result", "usage": {
            "input_tokens": 7, "output_tokens": 11}}
        self.assertTrue(control.interrupted())
        control.counted(interrupted)
        self.assertEqual({"input_tokens": 10, "output_tokens": 16},
                         control.with_usage(final)["usage"])

    def test_a_control_response_is_kept_out_of_the_provider_record_stream(self):
        control = claude.Control()
        self.assertTrue(control.heard({"type": "control_response", "response": {
            "subtype": "success", "request_id": "not-ours"}}))

    def test_a_refused_interrupt_does_not_consume_the_real_ending(self):
        output, control, accepted = Sink(), claude.Control(), []
        thread = threading.Thread(
            target=lambda: accepted.append(control.request(output, "interrupt")))
        thread.start()
        limit = time.monotonic() + 1
        while not output.getvalue():
            self.assertLess(time.monotonic(), limit, "the interrupt request was not sent")
            time.sleep(0.001)
        request = json.loads(output.getvalue())["request_id"]
        control.heard({"type": "control_response", "response": {
            "subtype": "error", "request_id": request, "error": "not active"}})
        thread.join(timeout=1)
        self.assertEqual([False], accepted)
        self.assertFalse(control.interrupted(),
                         "the next real result would be discarded as an interruption")

    def test_it_claims_the_four_things_the_golden_proves(self):
        for what in ("tools", "resume", "usage", "model"):
            self.assertTrue(claude.CAN[what], f"{what} is proven by the golden and not claimed")


class WhenTheActiveClaudeRequestIsSteered(unittest.TestCase):
    """The whole adapter/CLI exchange, using a deterministic local stand-in."""

    FAKE = textwrap.dedent("""\
        import json
        import sys

        def read():
            return json.loads(sys.stdin.readline())

        def write(record):
            print(json.dumps(record), flush=True)

        initialize = read()
        write({"type": "control_response", "response": {
            "subtype": "success", "request_id": initialize["request_id"], "response": {}}})

        first = read()
        write({"type": "system", "subtype": "init", "session_id": "same-session",
               "model": "claude-test"})
        write({"type": "assistant", "session_id": "same-session",
               "message": {"content": [{"type": "text", "text": "working on the first"}]}})

        interrupt = read()
        write({"type": "control_response", "response": {
            "subtype": "success", "request_id": interrupt["request_id"], "response": {}}})
        write({"type": "user", "message": {"content": [{
            "type": "tool_result", "tool_use_id": "tool-before-steer",
            "content": "The user doesn't want to proceed with this tool use.",
            "is_error": True
        }]}, "tool_result_meta": [{
            "id": "tool-before-steer", "non_execution_kind": "user-rejected"
        }]})
        write({"type": "result", "subtype": "error_during_execution", "is_error": True,
               "session_id": "same-session", "result": "Request interrupted by user",
               "usage": {"input_tokens": 3, "output_tokens": 5}})

        replacement = read()
        write({"type": "assistant", "session_id": "same-session",
               "message": {"content": [{"type": "text", "text": "followed the correction"}]}})
        write({"type": "result", "subtype": "success", "is_error": False,
               "session_id": "same-session",
               "usage": {"input_tokens": 7, "output_tokens": 11}})
        """)

    def test_one_process_is_interrupted_and_continues_with_the_new_instruction(self):
        words = claude.Words("do the first thing", io.StringIO(
            '{"type":"say","text":"do this instead"}\n'))
        reported = []
        with tempfile.TemporaryDirectory() as directory:
            fake = Path(directory) / "fake_claude.py"
            fake.write_text(self.FAKE, encoding="utf-8")
            with mock.patch.object(claude, "say",
                                   side_effect=lambda **record: reported.append(record)):
                code, lost = claude._turn(
                    [sys.executable, str(fake)], directory, words, dict(os.environ),
                    "same-session")

        self.assertEqual((0, False), (code, lost))
        self.assertEqual(["working on the first", "followed the correction"],
                         [one["text"] for one in only(reported, "text")])
        self.assertEqual([], only(reported, "result"),
                         "the canceled tool was reported as a failed command")
        self.assertEqual(1, len(only(reported, "done")),
                         "the interrupted request was mistaken for Rundesk's turn ending")
        self.assertTrue(only(reported, "done")[0]["ok"])
        self.assertEqual("same-session", only(reported, "done")[0]["session"])
        usage = only(reported, "usage")
        self.assertEqual(1, len(usage))
        self.assertEqual((10, 16), (usage[0]["input"], usage[0]["output"]),
                         "work before the interruption disappeared from the turn's cost")

if __name__ == "__main__":
    unittest.main(verbosity=2)
