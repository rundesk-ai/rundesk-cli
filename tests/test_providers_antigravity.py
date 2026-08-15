"""The antigravity adapter, against a stream a real `agy` once produced.

**No account, no token, no network.** The four `tests/samples/antigravity-*.jsonl` files are what
`agy --output-format stream-json` said during sanitized real turns: a 1.1.8 tool turn and fresh,
resumed, and tool-using 1.1.13 turns. `tests/samples/a-printing-brain` says them again on demand. So
the adapter is checked against vendor output rather than a stand-in written to agree with it, while
the suite never reaches a vendor.

**What the fixture is for is drift.** The day this vendor changes its stream, this file goes red with
the reading that broke, and `cli-versions.lock` says which version the fixture came from.

**Where a case writes its own stream, it says so.** Compaction, soft denial, and malformed-stream
edges remain constructed in the scratch root. Fresh and resumed arithmetic are also checked against
the captured 1.1.13 streams.

The adapter is run as the program it is, through the environment it is really given. Nothing here
imports it — it has no importable shape, deliberately, and a case that reached inside it would be
proving something the seam does not promise.

Run directly: `python3 tests/test_providers_antigravity.py`
"""

import json
import os
import subprocess
import unittest

import support

#: The adapter under test, and the two files that let it run with no vendor on the machine.
ADAPTER = support.CHECKOUT / "src" / "providers" / "antigravity"
CAPTURED = support.CHECKOUT / "tests" / "samples" / "antigravity-1.1.8.jsonl"
CURRENT = support.CHECKOUT / "tests" / "samples" / "antigravity-1.1.13.jsonl"
CURRENT_RESUMED = support.CHECKOUT / "tests" / "samples" / "antigravity-1.1.13-resumed.jsonl"
CURRENT_TOOLS = support.CHECKOUT / "tests" / "samples" / "antigravity-1.1.13-tools.jsonl"
A_BRAIN = support.CHECKOUT / "tests" / "samples" / "a-printing-brain"

#: The conversation the capture is of, and the model it names. Spelled out rather than read off the
#: fixture, so a fixture that changed underneath makes a case fail rather than agree with itself.
CONVERSATION = "conversation-alpha"
THE_MODEL = "gemini-3.6-flash-low"

#: How long the adapter may take to translate a capture. It does no waiting of its own here, so this
#: is a ceiling on something that finishes in hundredths and never a duration anything relies on.
PATIENCE = 60.0

#: A `PATH` with no vendor on it **and an interpreter still on it**. Pointing it at nothing at all
#: does not test a missing brain — it tests a missing `python3`, because that is what this adapter's
#: own first line goes looking for, so the program under test never starts and the case passes for
#: the wrong reason.
NO_VENDOR = "/usr/bin:/bin"

#: Every word rundesk has a column for. Written out rather than imported, because an adapter is a
#: program on the far side of a pipe and a suite that imported the core's list would be checking that
#: a file agrees with itself.
FAILURE_CODES = {"signed_out", "no_access", "no_credit", "usage_exhausted", "rate_limited",
                 "context_exceeded", "upstream_error", "offline", "refused", "cancelled",
                 "timed_out", "crashed"}

#: The ten words a `did` may be, for the same reason.
THE_TEN = {"read", "search", "run", "edit", "list", "make", "delegate", "memory", "rules",
           "identity"}


def a_line(**event):
    return json.dumps(event)


def a_step(**step):
    return a_line(event="step_update", step_update=step)


def a_result(**result):
    return a_line(event="result", result=result)


class Antigravity(support.Isolated):
    """One adapter, run as a program, against whatever stream a case hands it."""

    def brain(self, captured=CAPTURED, **told):
        """A directory holding one program called `agy`, put on the front of `PATH`. The adapter
        looks for its brain by name, exactly as it does on a real machine."""
        instead = self.home / "bin"
        instead.mkdir(parents=True, exist_ok=True)
        (instead / "agy").write_bytes(A_BRAIN.read_bytes())
        (instead / "agy").chmod(0o755)
        told.setdefault("PATH", f"{instead}:{NO_VENDOR}")
        told.setdefault("CAPTURED", str(captured))
        return told

    def stream(self, name: str, *lines) -> str:
        """A stream a case wrote itself, in the scratch root and never among the captures."""
        where = self.home / "streams"
        where.mkdir(parents=True, exist_ok=True)
        at = where / name
        at.write_text("".join(one + "\n" for one in lines), encoding="utf-8")
        return str(at)

    def replayed(self, prompt="Read note.txt and tell me the number in it.", captured=CAPTURED,
                 **also):
        """Run the adapter against a stream and hand back what it said, what became of it, and every
        way the brain was invoked."""
        where = self.home / "cwd"
        where.mkdir(parents=True, exist_ok=True)
        # One file per run of the adapter, never one shared between them: what makes the retry
        # provable is that *this* run started the brain twice, and a file two runs appended to
        # cannot tell that apart from two runs starting it once each.
        self.runs = getattr(self, "runs", 0) + 1
        recorded = self.home / f"invocations-{self.runs}.jsonl"
        told = self.brain(captured=captured, RECORDED=str(recorded), RUNDESK_CWD=str(where),
                          RUNDESK_ACCESS_MODE="work", RUNDESK_AGENT="cole", RUNDESK_RUN="1",
                          RUNDESK_CONTINUITY="AGENTS.md=rules,MEMORY.md=memory")
        told.update({name: value for name, value in also.items() if value is not None})
        for name, value in also.items():
            if value is None:
                told.pop(name, None)
        got = subprocess.run([str(ADAPTER)], input=prompt, capture_output=True, text=True,
                             timeout=PATIENCE, env=told, check=False)
        said = [json.loads(one) for one in got.stdout.splitlines() if one.strip()]
        ran = ([json.loads(one) for one in recorded.read_text(encoding="utf-8").splitlines()]
               if recorded.exists() else [])
        return said, got, ran

    def kinds(self, said):
        return [one["type"] for one in said]

    def only(self, said, kind):
        return [one for one in said if one["type"] == kind]

    def the_ending(self, said):
        endings = self.only(said, "done")
        self.assertEqual(1, len(endings), f"a turn ends exactly once, not {len(endings)} times")
        self.assertIs(endings[0], said[-1], "the record that ends a turn is the last one said")
        return endings[0]


class WhatItSaysItCanDo(Antigravity):
    """Offline, quick, deterministic, and claiming only what was demonstrated."""

    def asked(self, **told):
        got = subprocess.run([str(ADAPTER), "--capabilities"], capture_output=True, text=True,
                             timeout=PATIENCE, env=told, check=False)
        self.assertEqual(0, got.returncode, got.stderr)
        return json.loads(got.stdout)

    def test_it_answers_with_no_vendor_on_the_machine_at_all(self):
        """The one place rundesk runs an unvetted program before a turn has been admitted, so it may
        not need an account, a network, or the brain itself to be installed."""
        self.assertEqual({"tools": True, "resume": True, "model": False, "usage": True,
                          "steer": False},
                         self.asked(PATH=NO_VENDOR))

    def test_the_same_answer_every_time(self):
        self.assertEqual(self.asked(PATH=NO_VENDOR), self.asked(PATH=NO_VENDOR))

    def test_it_never_claims_it_can_be_steered(self):
        """There is no documented headless channel that takes a word after the piped prompt.
        Declaring it would leave rundesk holding this adapter's input open for a brain that reads its
        input to the end and then never looks again."""
        self.assertFalse(self.asked(PATH=NO_VENDOR)["steer"])

    def test_it_offers_no_additional_accounts(self):
        """This brain signs in through the machine's own keyring with no supported way to keep a
        second account apart from the first, so an alias would share one login while claiming not
        to."""
        self.assertNotIn("account_aliases", self.asked(PATH=NO_VENDOR))

    def test_the_version_it_found_is_volunteered_beside_the_five(self):
        """Whatever an adapter says here is kept against every turn, which is what explains a turn
        six months later."""
        instead = self.home / "bin"
        instead.mkdir(parents=True, exist_ok=True)
        (instead / "agy").write_text("#!/bin/sh\nprintf '9.9.9\\n'\n", encoding="utf-8")
        (instead / "agy").chmod(0o755)
        self.assertEqual("9.9.9", self.asked(PATH=f"{instead}:{NO_VENDOR}")["antigravity_cli"])

    def test_a_version_it_could_not_read_is_not_a_reason_to_fail(self):
        instead = self.home / "bin"
        instead.mkdir(parents=True, exist_ok=True)
        (instead / "agy").write_text("#!/bin/sh\nexit 3\n", encoding="utf-8")
        (instead / "agy").chmod(0o755)
        answer = self.asked(PATH=f"{instead}:{NO_VENDOR}")
        self.assertNotIn("antigravity_cli", answer)
        self.assertTrue(answer["tools"])


class OneCapturedTurn(Antigravity):
    """The whole of one real turn, read the way rundesk reads it."""

    def setUp(self):
        super().setUp()
        self.said, self.got, self.ran = self.replayed()

    def test_it_says_what_happened_in_the_order_it_happened(self):
        self.assertEqual(["text", "tool", "result", "text", "text", "usage", "done"],
                         self.kinds(self.said))
        self.assertEqual(0, self.got.returncode, self.got.stderr)

    def test_what_the_agent_said_arrives_as_the_pieces_it_was_written_in(self):
        """This brain writes a delta at a time and never restates a finished thought, so marking a
        piece `whole` would publish half a sentence to whoever is watching the turn go past."""
        for one in self.only(self.said, "text"):
            self.assertNotIn("whole", one)
        self.assertEqual("I\u2019ll check the README. Pocket Atlas turns place notes into a browsable "
                         "HTML page.\n",
                         "".join(one["text"] for one in self.only(self.said, "text")))

    def test_a_tool_is_paired_with_what_it_came_to(self):
        self.assertEqual({"type": "tool", "id": "agy:2", "name": "view_file", "did": "read"},
                         self.only(self.said, "tool")[0])
        self.assertEqual({"type": "result", "id": "agy:2", "ok": True,
                          "summary": "view_file finished"},
                         self.only(self.said, "result")[0])

    def test_every_verb_it_uses_is_one_of_the_ten(self):
        for one in self.only(self.said, "tool"):
            with self.subTest(name=one.get("name")):
                self.assertIn(one.get("did"), THE_TEN)

    def test_the_bill_is_the_steps_and_not_the_terminal_restatement(self):
        """Every step that carries usage is part of it, framing ones included: the checkpoint's 118
        input tokens are as real as the response's 3,272, and on this turn the steps sum to exactly
        what the terminal line restates."""
        self.assertEqual({"type": "usage", "input_tokens": 3390, "output_tokens": 380,
                          "cache_read_tokens": 16274, "context_tokens": 19546,
                          "model_name": THE_MODEL},
                         self.only(self.said, "usage")[0])

    def test_a_quantity_this_brain_never_reports_stays_absent(self):
        """Summing an absent figure into zero says it wrote nothing to the cache, which is a
        measurement nobody made."""
        self.assertNotIn("cache_write_tokens", self.only(self.said, "usage")[0])

    def test_the_turn_ends_once_carrying_the_conversation_it_opened(self):
        self.assertEqual({"type": "done", "ok": True, "session_id": CONVERSATION},
                         self.the_ending(self.said))

    def test_nothing_says_a_file_was_made_for_anybody(self):
        """A `file` record is what gets attached to a message on a channel. This brain names files it
        read and wrote and never one it made for a person, so guessing would mail somebody their own
        repository."""
        self.assertEqual([], self.only(self.said, "file"))

    def test_it_marks_no_answer_because_this_brain_names_none(self):
        """Its reply is one run of deltas with no phase in it, so rundesk's own fallback — the last
        thought after the last tool — is a better reading than a mark this adapter would invent."""
        self.assertFalse(any(one.get("final") for one in self.said))

    def test_the_current_cli_reports_real_tool_activity_without_paths_crossing_the_seam(self):
        said, _, _ = self.replayed(captured=CURRENT_TOOLS)
        tools = self.only(said, "tool")
        self.assertEqual(2, len(tools))
        self.assertTrue(all(one.get("did") == "read" for one in tools))
        self.assertFalse(any("/workspace" in json.dumps(one) for one in said))
        self.assertEqual("TOOL-PROBE-OK\n",
                         "".join(one["text"] for one in self.only(said, "text")))


class TheCommandItRuns(Antigravity):
    """What is on the command line, and what may never be."""

    def argv(self, **also):
        _, _, ran = self.replayed(**also)
        return ran[0]["argv"]

    def test_the_prompt_is_never_an_argument(self):
        """Every process on the machine can read a command line, and this brain's own `-p` takes the
        next word as its prompt — so a prompt that reached argv would be both readable by anybody and
        able to swallow the flag behind it."""
        secret = "the number in the vault is 41"
        _, _, ran = self.replayed(prompt=secret)
        self.assertEqual(secret, ran[0]["prompt"])
        self.assertNotIn(secret, ran[0]["argv"])
        self.assertFalse(any(secret in word for word in ran[0]["argv"]))
        for word in ("-p", "--print", "--prompt"):
            self.assertNotIn(word, ran[0]["argv"])

    def test_what_rundesk_wants_said_first_travels_in_the_prompt_and_not_on_argv(self):
        preface = "Prefer the shortest true answer."
        _, _, ran = self.replayed(RUNDESK_PREFACE=preface)
        self.assertIn(preface, ran[0]["prompt"])
        self.assertTrue(ran[0]["prompt"].endswith("Read note.txt and tell me the number in it."))
        self.assertFalse(any(preface in word for word in ran[0]["argv"]))

    def test_a_fresh_turn_binds_the_directory_it_was_told_to_stand_in(self):
        """Without this, an unseen working directory keeps the stream's stated `cwd` while the tools
        stand in this brain's own scratch project — and nothing in the stream says so."""
        argv = self.argv()
        self.assertIn("--new-project", argv)
        self.assertNotIn("--conversation", argv)

    def test_a_carried_conversation_is_named_exactly_and_binds_no_new_project(self):
        argv = self.argv(RUNDESK_RESUME=CONVERSATION)
        self.assertEqual(CONVERSATION, argv[argv.index("--conversation") + 1])
        self.assertNotIn("--new-project", argv)

    def test_the_model_is_asked_for_only_when_rundesk_named_one(self):
        self.assertNotIn("--model", self.argv())
        argv = self.argv(RUNDESK_MODEL=THE_MODEL)
        self.assertEqual(THE_MODEL, argv[argv.index("--model") + 1])

    def test_the_stream_is_the_one_this_adapter_can_read(self):
        argv = self.argv()
        self.assertEqual("stream-json", argv[argv.index("--output-format") + 1])

    def test_the_vendors_own_five_minute_clock_is_moved_past_rundesks_own_bounds(self):
        """Print mode gives up after five minutes by default, which would cut short every turn longer
        than one. Two clocks disagreeing is how a turn dies with nothing written down."""
        argv = self.argv()
        self.assertEqual("48h0m0s", argv[argv.index("--print-timeout") + 1],
                         "spelled the way this brain spells its own default, which prints as 5m0s")

    def test_the_brains_own_log_does_not_land_in_the_agents_home(self):
        argv = self.argv()
        self.assertEqual(os.devnull, argv[argv.index("--log-file") + 1])

    def test_it_stands_where_rundesk_told_it_to(self):
        _, _, ran = self.replayed()
        self.assertEqual(str((self.home / "cwd").resolve()),
                         str(os.path.realpath(ran[0]["cwd"])))


class WhatAccessMeansHere(Antigravity):
    """A request, and never a boundary rundesk could not keep."""

    def argv(self, mode):
        _, _, ran = self.replayed(RUNDESK_ACCESS_MODE=mode)
        return ran[0]["argv"]

    def test_read_is_mapped_onto_this_brains_own_read_only_workflow(self):
        self.assertEqual("plan", self.argv("read")[self.argv("read").index("--mode") + 1])

    def test_work_is_mapped_onto_the_one_that_edits(self):
        argv = self.argv("work")
        self.assertEqual("accept-edits", argv[argv.index("--mode") + 1])

    def test_a_word_this_release_does_not_know_cannot_silently_grant_work_access(self):
        said, got, ran = self.replayed(RUNDESK_ACCESS_MODE="paranoid")
        ending = self.the_ending(said)
        self.assertFalse(ending["ok"])
        self.assertEqual("crashed", ending["failure_code"])
        self.assertIn("unknown access mode", ending["failure_message"])
        self.assertNotEqual(0, got.returncode)
        self.assertEqual([], ran)

    def test_a_missing_access_mode_cannot_silently_grant_work_access(self):
        said, got, ran = self.replayed(RUNDESK_ACCESS_MODE=None)
        ending = self.the_ending(said)
        self.assertFalse(ending["ok"])
        self.assertEqual("crashed", ending["failure_code"])
        self.assertIn("unknown access mode", ending["failure_message"])
        self.assertNotEqual(0, got.returncode)
        self.assertEqual([], ran)

    def test_no_containment_is_claimed_on_either_of_them(self):
        """`--sandbox` is the vendor's OS containment. Passing it would imply a boundary rundesk does
        not enforce, over a turn that must run this install's own command and write the files the
        agent lives by."""
        for mode in ("read", "work"):
            with self.subTest(mode=mode):
                self.assertNotIn("--sandbox", self.argv(mode))

    def test_approval_is_skipped_deliberately_and_on_both_of_them(self):
        """Print mode has no channel an approval could be asked or given through, so withholding this
        does not make a turn safer — it makes it a soft denial that exits zero claiming success."""
        for mode in ("read", "work"):
            with self.subTest(mode=mode):
                self.assertIn("--dangerously-skip-permissions", self.argv(mode))


class WhatTheOwnerMayAdd(Antigravity):
    """Vendor options an owner set, and the ones this adapter will not hand over."""

    def test_an_option_this_release_never_heard_of_is_passed_straight_through(self):
        _, _, ran = self.replayed(RUNDESK_SETTINGS=json.dumps({"flags": ["--effort", "high"]}))
        argv = ran[0]["argv"]
        self.assertEqual("high", argv[argv.index("--effort") + 1])

    def test_a_flag_that_decides_access_cannot_be_taken_over_from_outside(self):
        said = json.dumps({"flags": ["--mode", "accept-edits", "--sandbox", "--effort", "low"]})
        _, got, ran = self.replayed(RUNDESK_ACCESS_MODE="read", RUNDESK_SETTINGS=said)
        argv = ran[0]["argv"]
        self.assertEqual("plan", argv[argv.index("--mode") + 1])
        self.assertNotIn("--sandbox", argv)
        self.assertEqual("low", argv[argv.index("--effort") + 1])
        self.assertIn("decided by rundesk", got.stderr)

    def test_ignoring_a_flag_ignores_its_value_with_it(self):
        """A stray `stream-json` left behind by a dropped `--output-format` is a positional argument
        this brain would read as something else entirely."""
        said = json.dumps({"flags": ["--output-format", "text", "--effort", "high"]})
        _, _, ran = self.replayed(RUNDESK_SETTINGS=said)
        argv = ran[0]["argv"]
        self.assertEqual("stream-json", argv[argv.index("--output-format") + 1])
        self.assertNotIn("text", argv)
        self.assertIn("--effort", argv)

    def test_dropping_a_switch_does_not_eat_the_flag_behind_it(self):
        said = json.dumps({"flags": ["--new-project", "--effort", "high"]})
        _, _, ran = self.replayed(RUNDESK_SETTINGS=said)
        self.assertIn("--effort", ran[0]["argv"])

    def test_what_was_set_being_unreadable_is_not_a_failed_turn(self):
        for setting in ("not json at all", "[]", '"words"'):
            with self.subTest(setting=setting):
                said, _, _ = self.replayed(RUNDESK_SETTINGS=setting)
                self.assertTrue(self.the_ending(said)["ok"])

    def test_flags_that_are_not_a_list_of_words_are_ignored_rather_than_guessed_at(self):
        said, got, ran = self.replayed(RUNDESK_SETTINGS=json.dumps({"flags": ["--effort", 2]}))
        self.assertTrue(self.the_ending(said)["ok"])
        self.assertNotIn("--effort", ran[0]["argv"])
        self.assertIn("list of strings", got.stderr)


class WhatAResumedTurnCost(Antigravity):
    """The reading that would over-report every conversation anybody carried on.

    The constructed stream below makes deliberately distinct values easy to read; the real current
    resumed capture in the following case independently proves the same relationship. Per-step
    blocks are this invocation's deltas and the terminal block is the conversation's running total.
    """

    RESUMED = (
        a_line(event="init", conversation_id=CONVERSATION, init={"model": THE_MODEL}),
        a_step(conversation_id=CONVERSATION, step_index=9, state="DONE",
               step_type="agent_response", text_delta="Twelve.",
               usage={"input_tokens": 12, "output_tokens": 3, "cache_read_tokens": 40}),
        a_result(conversation_id=CONVERSATION, status="SUCCESS", response="Twelve.",
                 usage={"input_tokens": 999, "output_tokens": 888, "cache_read_tokens": 777}),
    )

    def test_the_conversations_running_total_is_not_billed_against_one_turn(self):
        """A nonzero baseline is the whole point: a turn that began at nothing reports the same
        numbers whether a total is subtracted or ignored, so it proves neither."""
        said, _, _ = self.replayed(captured=self.stream("resumed.jsonl", *self.RESUMED),
                                   RUNDESK_RESUME=CONVERSATION)
        self.assertEqual({"type": "usage", "input_tokens": 12, "output_tokens": 3,
                          "cache_read_tokens": 40, "context_tokens": 52, "model_name": THE_MODEL},
                         self.only(said, "usage")[0])

    def test_the_current_captured_resume_reports_only_the_second_turn(self):
        """A real 1.1.13 resume has a 42,726-token terminal running total and a 21,925-token
        step-level turn. Only the latter belongs to this invocation."""
        said, _, _ = self.replayed(captured=CURRENT_RESUMED,
                                   RUNDESK_RESUME="conversation-current")
        self.assertEqual({"type": "usage", "input_tokens": 21925, "output_tokens": 79,
                          "cache_read_tokens": 0, "context_tokens": 21925},
                         self.only(said, "usage")[0])
        self.assertEqual("REMEMBERED\n",
                         "".join(one["text"] for one in self.only(said, "text")))

    def test_the_current_stream_does_not_invent_the_model_that_answered(self):
        said, _, _ = self.replayed(captured=CURRENT)
        self.assertNotIn("model_name", self.only(said, "usage")[0])

    def test_a_fresh_turn_that_reported_no_steps_falls_back_to_what_it_ended_with(self):
        """On a fresh turn the terminal block is this turn and nothing else, so a stream that carried
        no step usage still has its cost reported rather than lost."""
        stream = self.stream(
            "fresh-total.jsonl",
            a_line(event="init", conversation_id=CONVERSATION, init={"model": THE_MODEL}),
            a_result(conversation_id=CONVERSATION, status="SUCCESS", response="One whole answer.",
                     usage={"input_tokens": 4, "output_tokens": 2, "cache_read_tokens": 1}))
        said, _, _ = self.replayed(captured=stream)
        self.assertEqual({"type": "usage", "input_tokens": 4, "output_tokens": 2,
                          "cache_read_tokens": 1, "model_name": THE_MODEL},
                         self.only(said, "usage")[0])

    def test_the_same_stream_resumed_reports_nothing_rather_than_the_whole_history(self):
        """The other half of the same reading, and the one that costs money when it is wrong."""
        stream = self.stream(
            "resumed-total.jsonl",
            a_line(event="init", conversation_id=CONVERSATION, init={"model": THE_MODEL}),
            a_result(conversation_id=CONVERSATION, status="SUCCESS", response="One whole answer.",
                     usage={"input_tokens": 400000, "output_tokens": 2, "cache_read_tokens": 1}))
        said, _, _ = self.replayed(captured=stream, RUNDESK_RESUME=CONVERSATION)
        counted = self.only(said, "usage")
        self.assertEqual([{"type": "usage", "model_name": THE_MODEL}], counted)
        self.assertNotIn("input_tokens", counted[0])

    def test_nothing_measured_at_all_leaves_no_usage_record_to_read(self):
        """Zero and unknown are different answers, and a spend limit reading the first for the second
        would never fire."""
        stream = self.stream(
            "silent.jsonl",
            a_line(event="init", conversation_id=CONVERSATION, init={}),
            a_result(conversation_id=CONVERSATION, status="SUCCESS", response="Quiet."))
        said, _, _ = self.replayed(captured=stream)
        self.assertEqual([], self.only(said, "usage"))


class HowBigTheConversationGot(Antigravity):
    """A level, not a quantity — which is a different arithmetic from the bill beside it."""

    def ended_at(self, name, *responses, resume=None):
        lines = [a_line(event="init", conversation_id=CONVERSATION, init={"model": THE_MODEL})]
        for at, (belongs_to, counted) in enumerate(responses):
            lines.append(a_step(conversation_id=belongs_to, step_index=at, state="DONE",
                                step_type="agent_response", text_delta="…", usage=counted))
        lines.append(a_result(conversation_id=CONVERSATION, status="SUCCESS", response="…"))
        said, _, _ = self.replayed(captured=self.stream(name, *lines),
                                   **({"RUNDESK_RESUME": resume} if resume else {}))
        return self.only(said, "usage")[0]

    def test_a_turn_of_several_responses_reports_the_level_it_ended_at(self):
        counted = self.ended_at(
            "levels.jsonl",
            (CONVERSATION, {"input_tokens": 7000, "cache_read_tokens": 11000}),
            (CONVERSATION, {"input_tokens": 9000, "cache_read_tokens": 15000}))
        self.assertEqual(24000, counted["context_tokens"])

    def test_a_compacted_conversation_is_reported_smaller_than_the_one_before_it(self):
        """The behaviour a gauge must have and a total cannot: adding these would invent a number
        nothing measured and hide the compaction that is the only interesting thing in the turn."""
        counted = self.ended_at(
            "compacted.jsonl",
            (CONVERSATION, {"input_tokens": 18000, "cache_read_tokens": 30000}),
            (CONVERSATION, {"input_tokens": 4000, "cache_read_tokens": 8000}))
        self.assertEqual(12000, counted["context_tokens"])

    def test_a_subagents_own_conversation_is_not_the_size_of_this_one(self):
        counted = self.ended_at(
            "child.jsonl",
            (CONVERSATION, {"input_tokens": 9000, "cache_read_tokens": 15000}),
            ("a-child-conversation", {"input_tokens": 400000, "cache_read_tokens": 500000}))
        self.assertEqual(24000, counted["context_tokens"])

    def test_a_stream_that_never_said_how_big_it_was_claims_no_size(self):
        stream = self.stream(
            "sizeless.jsonl",
            a_line(event="init", conversation_id=CONVERSATION, init={"model": THE_MODEL}),
            a_result(conversation_id=CONVERSATION, status="SUCCESS", response="…",
                     usage={"input_tokens": 4, "output_tokens": 2}))
        said, _, _ = self.replayed(captured=stream)
        self.assertNotIn("context_tokens", self.only(said, "usage")[0])


class WhenItSaysItWorkedAndDidNot(Antigravity):
    """The one place this adapter contradicts the vendor's own word, and how narrow it is."""

    def denied(self, name, response, then_said=()):
        lines = [a_line(event="init", conversation_id=CONVERSATION, init={"model": THE_MODEL}),
                 a_step(conversation_id=CONVERSATION, step_index=3, state="ACTIVE",
                        step_type="tool", tool_name="write_to_file",
                        tool_info={"name": "write_to_file",
                                   "parameters": {"AbsolutePath": "/somewhere/notes.md"}}),
                 a_step(conversation_id=CONVERSATION, step_index=3, state="ERROR",
                        step_type="tool", tool_name="write_to_file",
                        tool_info={"name": "write_to_file",
                                   "error": {"type": "TOOL_ERROR",
                                             "message": "User denied write_file(/private/notes.md)"}})]
        for at, text in enumerate(then_said):
            lines.append(a_step(conversation_id=CONVERSATION, step_index=4 + at, state="ACTIVE",
                                step_type="agent_response", text_delta=text))
        lines.append(a_result(conversation_id=CONVERSATION, status="SUCCESS", response=response))
        said, got, _ = self.replayed(captured=self.stream(name, *lines))
        return said, got

    def test_a_failed_tool_and_no_answer_is_not_a_turn_that_worked(self):
        """Measured at 1.1.8: a headless soft denial ends `SUCCESS` with an empty response, exits
        zero, and leaves the filesystem untouched. Reported as it stands, that is a turn the owner is
        told succeeded and which did nothing."""
        said, _ = self.denied("denied.jsonl", "")
        ending = self.the_ending(said)
        self.assertFalse(ending["ok"])
        self.assertIn("TOOL_ERROR", ending["failure_message"])

    def test_a_failed_tool_it_recovered_from_is_an_ordinary_working_turn(self):
        """Recovering from a tool that failed is ordinary work, and the correction has to be narrow
        enough not to fail one."""
        said, _ = self.denied("recovered.jsonl", "I could not write it, so here it is instead.",
                              then_said=("I could not write it, so here it is instead.",))
        self.assertTrue(self.the_ending(said)["ok"])

    def test_what_a_tool_was_working_on_does_not_travel_with_the_failure(self):
        """A tool's own message carries the path, command or URL it failed at, and a summary is
        stored and shown."""
        said, _ = self.denied("private.jsonl", "")
        for one in self.only(said, "result"):
            self.assertNotIn("/private/notes.md", one["summary"])
        self.assertNotIn("/private/notes.md", json.dumps(said))

    def test_it_names_no_failure_word_it_has_no_evidence_for(self):
        """Only `SUCCESS` was ever measured off this brain's terminal line, so there is no vocabulary
        here to map — and a word guessed from prose is wrong on the first release that rewords one."""
        said, _ = self.denied("wordless.jsonl", "")
        self.assertNotIn("failure_code", self.the_ending(said))


class WhenTheConversationIsGone(Antigravity):
    """An unknown id does not fail here — it silently becomes a different conversation."""

    def setUp(self):
        super().setUp()
        self.said, self.got, self.ran = self.replayed(RUNDESK_RESUME="a-conversation-it-forgot")

    def test_it_notices_it_was_answered_by_a_conversation_nobody_asked_for(self):
        self.assertIn("no longer has conversation a-conversation-it-forgot", self.got.stderr)

    def test_it_asks_again_from_nothing_rather_than_working_in_a_scratch_project(self):
        self.assertEqual(2, len(self.ran))
        self.assertEqual("a-conversation-it-forgot",
                         self.ran[0]["argv"][self.ran[0]["argv"].index("--conversation") + 1])
        self.assertIn("--new-project", self.ran[1]["argv"])
        self.assertNotIn("--conversation", self.ran[1]["argv"])

    def test_the_question_is_asked_again_whole(self):
        self.assertEqual(self.ran[0]["prompt"], self.ran[1]["prompt"])

    def test_the_first_attempt_leaves_nothing_of_itself_behind(self):
        """The evidence arrives on the first line, before the model has done anything, which is what
        makes stopping there free of a second helping of everything the retry says."""
        self.assertEqual(["text", "tool", "result", "text", "text", "usage", "done"],
                         self.kinds(self.said))

    def test_the_turn_ends_once_and_says_it_worked(self):
        ending = self.the_ending(self.said)
        self.assertTrue(ending["ok"])
        self.assertEqual(CONVERSATION, ending["session_id"])
        self.assertEqual(0, self.got.returncode, self.got.stderr)

    def test_a_conversation_it_still_has_is_not_started_again(self):
        _, _, ran = self.replayed(RUNDESK_RESUME=CONVERSATION)
        self.assertEqual(1, len(ran))


class WhenSomethingGoesWrong(Antigravity):
    """A turn that ends badly still ends, and says which side it was."""

    def test_a_brain_that_is_not_on_this_machine_ends_the_turn(self):
        got = subprocess.run([str(ADAPTER)], input="hello", capture_output=True, text=True,
                             timeout=PATIENCE, check=False,
                             env={"PATH": NO_VENDOR, "RUNDESK_CWD": str(self.home),
                                  "RUNDESK_ACCESS_MODE": "work"})
        said = [json.loads(one) for one in got.stdout.splitlines() if one.strip()]
        ending = self.the_ending(said)
        self.assertFalse(ending["ok"])
        self.assertEqual("crashed", ending["failure_code"])
        self.assertNotEqual(0, got.returncode)

    def test_a_stream_that_simply_stopped_is_ended_by_this_side(self):
        """Exiting having said nothing is the failure that looks most like a success."""
        stream = self.stream("cut-off.jsonl",
                             a_line(event="init", conversation_id=CONVERSATION, init={}),
                             a_step(conversation_id=CONVERSATION, step_index=1, state="ACTIVE",
                                    step_type="agent_response", text_delta="Half a thou"))
        said, got, _ = self.replayed(captured=stream, EXIT_CODE="9",
                                     TROUBLE="the model connection dropped")
        ending = self.the_ending(said)
        self.assertFalse(ending["ok"])
        self.assertEqual("crashed", ending["failure_code"])
        self.assertEqual("the model connection dropped", ending["failure_message"])
        self.assertNotEqual(0, got.returncode)

    def test_a_brain_that_said_nothing_at_all_is_still_a_turn_that_ended(self):
        said, _, _ = self.replayed(captured=self.stream("nothing.jsonl"), EXIT_CODE="4")
        ending = self.the_ending(said)
        self.assertFalse(ending["ok"])
        self.assertIn("exit 4", ending["failure_message"])

    def test_rundesk_sending_no_prompt_ends_the_turn_rather_than_asking_nothing(self):
        said, got, ran = self.replayed(prompt="   \n  ")
        ending = self.the_ending(said)
        self.assertFalse(ending["ok"])
        self.assertEqual("crashed", ending["failure_code"])
        self.assertEqual([], ran, "no brain is started to be asked nothing")
        self.assertNotEqual(0, got.returncode)

    def test_a_failing_turn_still_carries_the_conversation_it_opened(self):
        """This brain reports the conversation it opened rather than being told one, so it exists —
        and carrying it on is how the next turn keeps what came before it."""
        stream = self.stream(
            "failed.jsonl",
            a_line(event="init", conversation_id=CONVERSATION, init={}),
            a_result(conversation_id=CONVERSATION, status="ERROR", response="",
                     error="the model refused to continue"))
        said, _, _ = self.replayed(captured=stream)
        ending = self.the_ending(said)
        self.assertFalse(ending["ok"])
        self.assertEqual(CONVERSATION, ending["session_id"])
        self.assertEqual("the model refused to continue", ending["failure_message"])

    def test_every_word_it_ever_writes_is_one_rundesk_has_a_column_for(self):
        for stream, told in (("cut-off-2.jsonl", {"EXIT_CODE": "9"}),):
            said, _, _ = self.replayed(captured=self.stream(stream), **told)
            for one in self.only(said, "done"):
                if "failure_code" in one:
                    self.assertIn(one["failure_code"], FAILURE_CODES)


class WhatItDoesNotUnderstand(Antigravity):
    """Vendor drift stays in the raw stream and never becomes an invented record."""

    def test_a_line_that_is_not_a_record_is_dropped_rather_than_guessed_at(self):
        stream = self.stream("drift.jsonl",
                             "this is not json at all",
                             "[1, 2, 3]",
                             a_line(event="a-kind-from-next-release", whatever=1),
                             a_line(event="init", conversation_id=CONVERSATION, init={}),
                             a_step(conversation_id=CONVERSATION, step_index=1, state="DONE",
                                    step_type="system_message", text="ignore me"),
                             a_result(conversation_id=CONVERSATION, status="SUCCESS",
                                      response="Still fine."))
        said, got, _ = self.replayed(captured=stream)
        self.assertEqual(["text", "done"], self.kinds(said))
        self.assertTrue(self.the_ending(said)["ok"])
        self.assertEqual(0, got.returncode, got.stderr)

    def test_a_nested_object_that_arrived_as_nothing_does_not_end_the_turn(self):
        stream = self.stream("nulls.jsonl",
                             a_line(event="init", conversation_id=CONVERSATION, init=None),
                             a_line(event="step_update", step_update=None),
                             a_result(conversation_id=CONVERSATION, status="SUCCESS", response="Ok."))
        said, _, _ = self.replayed(captured=stream)
        self.assertTrue(self.the_ending(said)["ok"])

    def test_a_tool_this_release_never_heard_of_is_named_and_given_no_verb(self):
        """A reader shown nothing is better off than one taught to believe a word that means
        something else here."""
        stream = self.stream("newtool.jsonl",
                             a_line(event="init", conversation_id=CONVERSATION, init={}),
                             a_step(conversation_id=CONVERSATION, step_index=4, state="ACTIVE",
                                    step_type="tool", tool_name="quantum_search"),
                             a_result(conversation_id=CONVERSATION, status="SUCCESS", response="."))
        said, _, _ = self.replayed(captured=stream)
        self.assertEqual({"type": "tool", "id": "agy:4", "name": "quantum_search"},
                         self.only(said, "tool")[0])


class WhatTheAgentLivesBy(Antigravity):
    """An agent rewriting what it *is* between turns is different news from a working file changing."""

    def edited(self, at, parameter="AbsolutePath"):
        stream = self.stream(
            f"edit-{abs(hash(at))}.jsonl",
            a_line(event="init", conversation_id=CONVERSATION, init={}),
            a_step(conversation_id=CONVERSATION, step_index=1, state="ACTIVE", step_type="tool",
                   tool_name="write_to_file",
                   tool_info={"name": "write_to_file", "parameters": {parameter: at}}),
            a_result(conversation_id=CONVERSATION, status="SUCCESS", response="."))
        said, _, _ = self.replayed(captured=stream)
        return self.only(said, "tool")[0]["did"]

    def test_the_files_it_lives_by_are_told_apart_from_the_work(self):
        where = self.home / "cwd"
        self.assertEqual("rules", self.edited(str(where / "AGENTS.md")))
        self.assertEqual("memory", self.edited(str(where / "MEMORY.md")))

    def test_the_current_write_tool_target_names_a_continuity_file(self):
        """Measured at 1.1.13: `write_to_file` names its absolute destination `TargetFile`."""
        where = self.home / "cwd"
        self.assertEqual("memory", self.edited(str(where / "MEMORY.md"), "TargetFile"))

    def test_a_files_name_is_not_the_test(self):
        """Every checkout on the machine has an `AGENTS.md`, and an agent editing one in a repository
        has not rewritten its own rules."""
        elsewhere = self.home / "cwd" / "a-project"
        elsewhere.mkdir(parents=True, exist_ok=True)
        self.assertEqual("edit", self.edited(str(elsewhere / "AGENTS.md")))

    def test_an_ordinary_file_is_an_ordinary_edit(self):
        self.assertEqual("edit", self.edited(str(self.home / "cwd" / "notes.md")))


class WhatItKeepsAndWhatItLeavesAlone(Antigravity):
    def test_everything_the_brain_said_is_kept_verbatim_where_rundesk_asked(self):
        """Rundesk sees what the *adapter* reported and never what the brain said, so a vendor
        changing its output shape otherwise shows up as records quietly going missing with nothing at
        all to compare against."""
        raw = self.home / "raw" / "raw.jsonl"
        raw.parent.mkdir(parents=True, exist_ok=True)
        self.replayed(RUNDESK_RAW=str(raw))
        self.assertEqual(CAPTURED.read_text(encoding="utf-8").splitlines(),
                         raw.read_text(encoding="utf-8").splitlines())

    def test_somewhere_it_cannot_keep_a_copy_is_still_a_whole_turn(self):
        said, got, _ = self.replayed(RUNDESK_RAW=str(self.home / "not-there" / "raw.jsonl"))
        self.assertTrue(self.the_ending(said)["ok"])
        self.assertIn("could not be kept", got.stderr)

    def test_it_neither_makes_nor_prunes_the_skill_links_rundesk_owns(self):
        """Standing a skill where a brain finds it is rundesk's own work and this brain's root is one
        it already writes. An adapter doing it again during a turn would race the thing that owns it,
        and pruning would take links rundesk had just made."""
        where = self.home / "cwd"
        where.mkdir(parents=True, exist_ok=True)
        granted = self.home / "granted"
        (granted / "writing-plans").mkdir(parents=True, exist_ok=True)
        theirs = where / ".agents" / "skills"
        theirs.mkdir(parents=True, exist_ok=True)
        (theirs / "writing-plans").symlink_to(granted / "writing-plans")
        (theirs / "one-of-their-own").mkdir()

        self.replayed(RUNDESK_SKILLS=str(granted))

        self.assertTrue((theirs / "writing-plans").is_symlink())
        self.assertTrue((theirs / "one-of-their-own").is_dir())
        self.assertEqual({"writing-plans", "one-of-their-own"}, set(os.listdir(theirs)))

    def test_it_makes_no_vendor_directory_in_a_home_that_had_none(self):
        self.replayed(RUNDESK_SKILLS=str(self.home / "granted"))
        self.assertFalse((self.home / "cwd" / ".agents").exists())


class WhatItNeverDoes(Antigravity):
    def test_no_credential_of_the_owners_is_read_copied_or_exported(self):
        """This brain looks the owner's login up in the machine's own keyring. Naming a credential
        anywhere in this file would be a claim to have touched one."""
        said = ADAPTER.read_text(encoding="utf-8").lower()
        for named in ("google_application_credentials", "oauth", "access_token", "refresh_token",
                      "api_key", "keychain", "keyring", "client_secret"):
            with self.subTest(named=named):
                self.assertNotIn(named + " =", said)
                self.assertNotIn(f'"{named}"', said)
                self.assertNotIn(f"'{named}'", said)

    def test_it_asks_this_brain_not_to_update_itself_in_the_middle_of_a_turn(self):
        instead = self.home / "another-bin"
        instead.mkdir(parents=True, exist_ok=True)
        seen = self.home / "environment.json"
        (instead / "agy").write_text(
            "#!/usr/bin/env python3\n"
            "import json, os, sys\n"
            "sys.stdin.read()\n"
            f"open({str(seen)!r}, 'w').write(json.dumps(dict(os.environ)))\n"
            "print(json.dumps({'event': 'result', 'result': "
            "{'conversation_id': 'c', 'status': 'SUCCESS', 'response': 'ok'}}))\n",
            encoding="utf-8")
        (instead / "agy").chmod(0o755)
        said, _, _ = self.replayed(PATH=f"{instead}:{NO_VENDOR}")
        self.assertTrue(self.the_ending(said)["ok"])
        handed = json.loads(seen.read_text(encoding="utf-8"))
        self.assertEqual("true", handed["AGY_CLI_DISABLE_AUTO_UPDATE"])
        self.assertTrue(handed.get("USER"), "the keyring lookup needs the account name back")

    def test_the_seams_own_names_are_the_only_ones_it_reads(self):
        """A name rundesk decided is a name an owner's value may never take, so an adapter inventing
        one of its own puts a variable nothing documents between an owner and a working turn."""
        said = ADAPTER.read_text(encoding="utf-8")
        known = {"RUNDESK_CWD", "RUNDESK_PROVIDER_HOME", "RUNDESK_AGENT", "RUNDESK_RUN",
                 "RUNDESK_ACCESS_MODE", "RUNDESK_HOME", "RUNDESK_COMMAND", "RUNDESK_SKILLS",
                 "RUNDESK_CONTINUITY", "RUNDESK_RAW", "RUNDESK_MODEL", "RUNDESK_RESUME",
                 "RUNDESK_SETTINGS", "RUNDESK_PREFACE", "RUNDESK_DELEGATION"}
        for word in said.split('"'):
            if word.startswith("RUNDESK_"):
                with self.subTest(word=word):
                    self.assertIn(word, known)


if __name__ == "__main__":
    unittest.main()
