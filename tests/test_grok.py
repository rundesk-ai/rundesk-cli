"""Grok, as the brain that proves the seam degrades rather than breaks.

**Nothing here starts grok.** What is driven is `tests/samples/grok-stream.jsonl` — 79
lines of real output, captured once against a real account and committed because it cost
money. So this suite needs no account, no token and no network.

This brain is the honest floor, and that is its whole value here. It reports **no tool
events at all** — measured at 0.2.111 by granting read tools, planting a file and asking
it to read one: it reported the contents and the stream carried only `text` and `thought`.
So four of the seven record kinds have no source, and the test that matters most is that
none of them is invented.

Three flags decide whether this adapter is honest and two of them are traps that were
already shipped once: `--permission-mode dontAsk` is accepted and silently ignored, and
`--sandbox` enforces nothing headless. The third, `--no-memory`, is what stops one
conversation reading another's — found only because a resume probe carried a control.

The adapter is loaded by path rather than imported as a module, because it is not one: it
is a program, which is the whole point of the seam.

Run: python3 tests/test_grok.py
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import os
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from rundesk import provider  # noqa: E402  — after the path is set, as every suite here does

AT = ROOT / "src" / "providers" / "grok"
GOLDEN = ROOT / "tests" / "samples" / "grok-stream.jsonl"


def _adapter():
    """The adapter, loaded from its path — it is a program, not a module."""
    loader = importlib.machinery.SourceFileLoader("rundesk_grok", str(AT))
    spec = importlib.util.spec_from_loader("rundesk_grok", loader)
    made = importlib.util.module_from_spec(spec)
    loader.exec_module(made)
    return made


grok = _adapter()


def carried(lines=None) -> tuple:
    """The whole golden stream, as the records the adapter makes of it."""
    seen = {"session": "minted-before-the-first-byte", "ended": False}
    said = []
    for line in (lines if lines is not None else GOLDEN.read_text(encoding="utf-8").splitlines()):
        said.extend(grok.records(line, seen))
    return said, seen


def only(said: list, kind: str) -> list:
    return [one for one in said if one["type"] == kind]


class WhatTheGoldenSaysBack(unittest.TestCase):
    """The stream, driven end to end, as the seam's own records."""

    def setUp(self):
        self.said, self.seen = carried()

    def test_a_brain_that_runs_no_tools_reports_none(self):
        """R-PRV-7, and the whole reason this brain is in the repository. Seventy-nine
        lines of a real turn, and there is nothing in them to report — so nothing is
        reported. A surface shows less rather than showing something invented."""
        self.assertEqual([], only(self.said, "tool"))
        self.assertEqual([], only(self.said, "result"))
        self.assertEqual([], only(self.said, "file"))
        self.assertFalse(grok.CAN["tools"], "it claims tools it has no way of reporting")

    def test_a_reply_still_being_written_is_never_called_finished(self):
        """R-PRV-22, from the other side to Claude's. This brain writes a token at a time
        and nothing in the stream ever restates it, so nothing it says is finished until
        the turn is. Marking one whole would show a sentence that then changed underneath
        whoever was reading it."""
        spoken = only(self.said, "text")
        self.assertEqual(37, len(spoken), "the reply is not arriving as fragments")
        for one in spoken:
            self.assertNotIn(provider.WHOLE, one, f"{one['text']!r} was called finished")

    def test_what_it_thought_is_never_reported_as_what_it_said(self):
        """`thought` and `text` are one field apart on the same shape, so anything scanning
        raw lines for `data` reports what the model merely considered as what it said."""
        self.assertEqual(1, len(only(self.said, "think")))
        self.assertEqual(37, len(only(self.said, "text")))
        spoken = "".join(one["text"] for one in only(self.said, "text"))
        self.assertEqual(215, len(spoken))
        self.assertNotIn("The", spoken[:3], "a thought has leaked into the reply")

    def test_token_sized_thought_fragments_are_one_broad_activity(self):
        """R-DIS-20 — Grok's 41 contiguous thought fragments are one reasoning phase, not
        41 separate activities for Discord to render as `thinking (x41)`."""
        thought = only(self.said, "think")
        self.assertEqual(1, len(thought))
        self.assertTrue(thought[0]["text"])

    def test_what_it_cost_is_taken_across_unchanged_and_cached_is_kept_apart(self):
        """Measured: `input_tokens` excludes `cache_read_input_tokens` — 13,373 + 5,248 +
        192 is exactly `total_tokens` — so the split this seam asks for is the split this
        brain reports and nothing is subtracted."""
        counted = only(self.said, "usage")
        self.assertEqual(1, len(counted))
        self.assertEqual(13373, counted[0]["input"])
        self.assertEqual(5248, counted[0]["cached"])
        self.assertEqual(192, counted[0]["output"])
        self.assertEqual(18813, counted[0]["input"] + counted[0]["cached"] + counted[0]["output"])

    def test_a_cache_figure_this_brain_never_gave_is_not_invented(self):
        """There is no cache-*creation* field at all here. An absent number means we could
        not tell, which is recorded differently from a zero — so nothing is put there."""
        source = AT.read_text(encoding="utf-8")
        self.assertNotIn("cache_creation", source,
                         "a field this brain does not report is being read")

    def test_the_model_that_answered_is_named_from_what_it_reported(self):
        """R-PRV-9. Read back rather than echoed from what was asked for: a silent model
        substitution would show up here and nowhere else."""
        self.assertEqual("grok-4.5-build", only(self.said, "usage")[0]["model"])

    def test_the_resume_handle_is_the_one_this_brain_reported(self):
        """R-PRV-17. Opaque to rundesk, and handed straight back next turn."""
        said = only(self.said, "done")
        self.assertEqual(1, len(said))
        self.assertTrue(said[0]["ok"])
        self.assertEqual("019f95ad-a32b-7922-a669-e6e26f978901", said[0]["session"])

    def test_everything_reported_is_a_record_the_seam_knows(self):
        for one in self.said:
            self.assertIn(one["type"], provider.RECORDS)
            self.assertIsNotNone(provider.understood(json.dumps(one)))


class WhenTheStreamGoesWrong(unittest.TestCase):
    """The paths a captured happy turn cannot reach."""

    def test_a_turn_that_did_not_end_cleanly_is_not_called_ok(self):
        """`EndTurn` is how a turn ends when nothing went wrong. Anything else — a limit,
        an interruption, a refusal — is a turn that did not finish, and saying otherwise
        would be reporting a success it did not earn."""
        for stopped in ("MaxTurns", "Aborted", "Refusal", ""):
            said = grok.records(json.dumps({
                "type": "end", "stopReason": stopped, "sessionId": "a-session",
                "usage": {"input_tokens": 1, "output_tokens": 1}}), {"session": "a-session"})
            ended = [one for one in said if one["type"] == "done"][0]
            self.assertFalse(ended["ok"], f"{stopped!r} was reported as having worked")
            self.assertIn("why", ended)

    def test_a_stream_that_stops_without_an_ending_says_so_rather_than_going_quiet(self):
        lines = GOLDEN.read_text(encoding="utf-8").splitlines()[:-1]
        said, seen = carried(lines)
        self.assertEqual([], only(said, "done"))
        self.assertFalse(seen["ended"])

    def test_a_line_that_is_not_a_record_at_all_is_understood_as_nothing(self):
        for said in ('{"type":"tex', "[1,2,3]", "42", "", "   ", "not json at all"):
            self.assertEqual([], grok.records(said, {"session": "x"}))

    def test_a_kind_this_brain_grows_later_is_dropped_rather_than_guessed_at(self):
        """Three kinds exist and there is no fourth. If one appears it is kept in the raw
        beside the run and reported to nobody, which is drift somebody can read rather than
        a shape this adapter invented a meaning for."""
        self.assertEqual([], grok.records(
            json.dumps({"type": "tool_call", "name": "read_file"}), {"session": "x"}))

    def test_a_turn_that_named_no_model_leaves_none_claimed(self):
        """R-PRV-9. Absent rather than empty: a model called empty-string is a claim."""
        said = grok.records(json.dumps({
            "type": "end", "stopReason": "EndTurn", "sessionId": "s",
            "usage": {"input_tokens": 1, "output_tokens": 1}}), {"session": "s"})
        counted = [one for one in said if one["type"] == "usage"][0]
        self.assertNotIn("model", counted)


class WhatTheAdapterDecidesOnItsOwn(unittest.TestCase):
    """The command line, which is where every one of this brain's traps lives."""

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
        return grok.opening(posture, model, resume, extra or {}, "a-minted-id", "/tmp/asked.txt")

    def test_a_flag_that_is_accepted_and_ignored_is_never_passed(self):
        """The failure this prevents shipped once: the adapter passed `--permission-mode
        dontAsk` for both postures, so an agent configured for full access was given every
        write tool and then denied all of them. It wrote nothing, explained itself in prose,
        and the turn reported success. Nothing in a suite could see it, because the flag
        was present and the argv looked deliberate."""
        for posture in ("read", "work"):
            argv = self.opening(posture=posture)
            self.assertNotIn("dontAsk", argv)

    def test_headless_tools_do_not_wait_for_an_approval_nobody_can_give(self):
        """A real working turn asked to inspect files emitted 37 thought fragments and
        ended `Cancelled` with exit 0: the default policy reached a tool approval, but this
        adapter has no interactive stdin. `bypassPermissions` is measured to apply, while
        the tool list below remains the posture boundary."""
        for posture in ("read", "work"):
            argv = self.opening(posture=posture)
            self.assertEqual("bypassPermissions",
                             argv[argv.index("--permission-mode") + 1])

    def test_a_flag_that_reads_like_a_guarantee_and_enforces_nothing_is_never_passed(self):
        """Measured: under `--sandbox read-only` this CLI created a file both through its
        own tool and through a shell redirect, and under `strict` it read a planted marker
        well outside the working directory."""
        for posture in ("read", "work"):
            self.assertNotIn("--sandbox", self.opening(posture=posture))
        passing = re.findall(r"^[^#\n]*[\"']--sandbox[\"']", AT.read_text(encoding="utf-8"), re.M)
        self.assertEqual([], passing, "something in this adapter passes --sandbox")

    def test_one_conversation_is_never_left_able_to_read_another(self):
        """Found only because a resume probe carried a control: a turn in a *fresh* session
        answered a question only the previous conversation could have set up, saying so as
        it went — 'checking recent sessions for what the second one refers to'. A private
        home does not stop it, because both conversations live in the same home."""
        for posture in ("read", "work"):
            self.assertIn("--no-memory", self.opening(posture=posture))
        self.assertIn("--no-memory", self.opening(resume="an-old-session"))

    def test_an_agent_is_separated_by_where_it_stands_rather_than_by_a_relocated_home(self):
        """Measured: this brain files its conversations under the directory a turn was run
        in — `~/.grok/sessions/%2FUsers%2F…%2F<agent home>` — exactly as Claude files them
        under `~/.claude/projects/<cwd slug>`. Rundesk already stands each turn in its own
        agent's home, so relocating `GROK_HOME` on top of that separated nothing further
        and cost a second login to create. The shipped codex adapter has never set its own
        either, and on Claude the equivalent variable removes the login outright."""
        source = AT.read_text(encoding="utf-8")
        setting = re.findall(r"^[^#\n]*GROK_HOME[^\n]*=", source, re.M)
        self.assertEqual([], setting, "something in this adapter relocates the brain's home")

    def test_a_turn_asked_to_only_look_is_given_a_tool_list_and_nothing_else(self):
        """R-PRV-18. The tool list is the only thing measured to scope this CLI, so it is
        the whole of how a posture is honoured."""
        argv = self.opening(posture="read")
        allowed = argv[argv.index("--tools") + 1].split(",")
        self.assertEqual(["read_file", "list_dir", "grep"], allowed)
        self.assertNotIn("run_terminal_command", allowed)
        self.assertNotIn("create_file", allowed)

    def test_a_read_only_turn_is_given_no_shell_at_all(self):
        """`run_terminal_command` is the only shell this CLI offers and it cannot be scoped
        to a command prefix, so there is no partial version to grant — and the sandbox that
        would have contained it does not hold."""
        argv = self.opening(posture="read")
        self.assertNotIn("run_terminal_command", argv[argv.index("--tools") + 1])

    def test_a_working_turn_is_given_no_list_at_all(self):
        """R-PRV-18. Leaving the flag off entirely is this CLI's way of saying every
        built-in, and a list of six names cannot stay complete — a tool it gains next
        release would be one a working turn was silently refused.

        Measured 2026-07-27 against 0.2.112: with no `--tools` a turn created a file, and
        with the read list it could not."""
        argv = self.opening()
        self.assertNotIn("--tools", argv)

    def test_the_tool_list_is_one_value_rather_than_many_flags(self):
        """`--allow` takes one rule per flag and rejects a space-separated list with
        `unknown tool prefix: …`. `--tools` takes the comma-separated built-in names.
        Asked of `read`, which is the posture that still carries it."""
        argv = self.opening(posture="read")
        self.assertNotIn("--allow", argv)
        self.assertIn(",", argv[argv.index("--tools") + 1])

    def test_standing_instructions_are_added_and_never_substituted(self):
        """R-PRV-23. `--rules` says it appends to the system prompt;
        `--system-prompt-override` says it overrides it. Adding is what standing
        instructions are."""
        argv = self.opening(preface="You are in a room. Others read this.")
        self.assertIn("--rules", argv)
        self.assertNotIn("--system-prompt-override", argv)
        self.assertEqual("You are in a room. Others read this.", argv[argv.index("--rules") + 1])
        passing = re.findall(r"^[^#\n]*[\"']--system-prompt-override[\"']",
                             AT.read_text(encoding="utf-8"), re.M)
        self.assertEqual([], passing, "something in this adapter passes the override")

    def test_a_turn_with_nothing_standing_says_nothing(self):
        self.assertNotIn("--rules", self.opening(preface=None))
        self.assertNotIn("--rules", self.opening(preface="   \n  "))

    def test_what_somebody_asked_is_never_an_argument(self):
        """Measured: `--prompt-file` carries a whole turn identically to `-p`. A flag's
        value is readable through the process list for the life of the turn, and what
        somebody asks their agent is not something to leave there."""
        argv = self.opening()
        self.assertIn("--prompt-file", argv)
        self.assertNotIn("-p", argv)
        self.assertEqual("/tmp/asked.txt", argv[argv.index("--prompt-file") + 1])

    def test_the_prompt_is_written_where_nobody_else_can_read_it(self):
        """The point of the file is that the prompt is not an argument; leaving it
        world-readable would give that back."""
        source = AT.read_text(encoding="utf-8")
        self.assertIn("S_IRUSR", source)
        self.assertIn("os.chmod", source)

    def test_a_new_conversation_is_named_before_the_first_byte(self):
        argv = self.opening()
        self.assertEqual("a-minted-id", argv[argv.index("--session-id") + 1])
        self.assertNotIn("--resume", argv)

    def test_a_conversation_being_carried_on_is_resumed_and_not_renamed(self):
        """`--session-id` names a *new* conversation and refuses an id that already exists,
        so the two are never passed together."""
        argv = self.opening(resume="an-old-session")
        self.assertEqual("an-old-session", argv[argv.index("--resume") + 1])
        self.assertNotIn("--session-id", argv)

    def test_the_stream_this_adapter_asks_for_is_the_one_it_can_read(self):
        self.assertEqual("streaming-json", self.opening()[
            self.opening().index("--output-format") + 1])

    def test_what_an_owner_set_reaches_the_brain_unread(self):
        """R-PRV-16."""
        self.assertEqual(["--reasoning-effort", "high"],
                         self.opening(extra={"flags": ["--reasoning-effort", "high"]})[-2:])

    def test_what_an_owner_set_wrongly_is_said_rather_than_guessed_at(self):
        self.assertEqual([], grok._flags({"flags": "--effort high"}))
        self.assertEqual([], grok._flags({"flags": [1, 2]}))

    def test_a_model_nobody_asked_for_is_not_claimed(self):
        self.assertNotIn("-m", self.opening())
        self.assertEqual("a-model", self.opening(model="a-model")[
            self.opening(model="a-model").index("-m") + 1])


class WhatThisBrainCanDo(unittest.TestCase):
    """R-PRV-15 — declared, and only what was measured."""

    def test_it_says_what_it_can_do_and_every_answer_is_yes_or_no(self):
        self.assertEqual(sorted(provider.CAPABILITIES), sorted(grok.CAN))
        for what, said in grok.CAN.items():
            self.assertIsInstance(said, bool, f"{what} is not a yes or a no")

    def test_it_claims_a_conversation_it_was_measured_to_carry_on(self):
        """Claimed because the round trip was run *and controlled*, not because a flag
        exists: turn two, told only 'the second one', named a codeword from turn one that a
        control session could not."""
        self.assertTrue(grok.CAN["resume"])

    def test_it_does_not_claim_the_two_things_it_cannot_do(self):
        self.assertFalse(grok.CAN["tools"])
        self.assertFalse(grok.CAN["steer"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
