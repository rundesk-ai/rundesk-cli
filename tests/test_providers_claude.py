"""The claude adapter, against a stream a real claude once produced.

**No account, no token, no network.** `tests/samples/claude-2.1.223.jsonl` is what `claude -p` said
during one real turn on 2026-08-06, captured whole and scrubbed of anything naming a machine or an
owner; `tests/samples/a-streaming-brain` says it again on demand. So every reading this adapter
makes is checked against the vendor rather than against a stand-in written to agree with it — which
is the one thing a hand-written fake cannot do — and the suite still never reaches a vendor, which is
both this repository's rule and a terms one.

**What the fixture is for is drift.** The day this vendor changes its stream, this file goes red
with the reading that broke, and `cli-versions.lock` says which version the fixture came from.

The adapter is run as the program it is, through the environment it is really given. Nothing here
imports it — it has no importable shape, deliberately, and a case that reached inside it would be
proving something the seam does not promise.

Run directly: `python3 tests/test_providers_claude.py`
"""

import json
import subprocess
import unittest

import support

#: The adapter under test, and the two files that let it run with no vendor on the machine.
ADAPTER = support.CHECKOUT / "src" / "providers" / "claude"
CAPTURED = support.CHECKOUT / "tests" / "samples" / "claude-2.1.223.jsonl"
A_BRAIN = support.CHECKOUT / "tests" / "samples" / "a-streaming-brain"

#: A real steered exchange: a turn asked to do something long, an interrupt, and a replacement that
#: ends it. **Nothing else can prove steering** — what makes it observable is that the brain says
#: `result` twice, once for the request that was stopped and once for the one that finished.
STEERED = support.CHECKOUT / "tests" / "samples" / "claude-2.1.223-steered.jsonl"

#: How long the adapter may take to translate a capture. It does no waiting of its own here, so this
#: is a ceiling on something that finishes in hundredths and never a duration anything relies on.
PATIENCE = 60.0

#: A `PATH` with no vendor on it **and an interpreter still on it**. Pointing it at nothing at all
#: does not test a missing brain — it tests a missing `python3`, because that is what this adapter's
#: own first line goes looking for, so the program under test never starts and the case passes for
#: the wrong reason.
NO_VENDOR = "/usr/bin:/bin"

#: What this brain says when a turn stopped for a reason the seam has a word for, and the word.
#: **The prose is the only place it puts one** — a turn stopped by a limit arrives as an ordinary
#: failure with no field saying which kind it was.
HOW_IT_FAILS = (
    ("Claude AI usage limit reached", "usage_exhausted"),
    ("rate limit exceeded, please slow down", "rate_limited"),
    ("Your credit balance is too low", "no_credit"),
    ("Invalid API key · Please run /login", "signed_out"),
    ("prompt is too long: 300000 tokens", "context_exceeded"),
    ("This model does not have access for your account", "no_access"),
    ("Internal server error", "upstream_error"),
    ("fetch failed: ECONNREFUSED", "offline"),
)

#: Every word rundesk has a column for. Written out rather than imported, because an adapter is a
#: program on the far side of a pipe and a suite that imported the core's list would be checking
#: that a file agrees with itself.
FAILURE_CODES = {"signed_out", "no_access", "no_credit", "usage_exhausted", "rate_limited",
                 "context_exceeded", "upstream_error", "offline", "refused", "cancelled",
                 "timed_out", "crashed"}


def replayed(home, prompt="Read note.txt and tell me the number in it.", captured=CAPTURED,
             steering=None, **also):
    """Run the adapter against the capture and hand back every record it made, in order."""
    where = home / "cwd"
    where.mkdir(parents=True, exist_ok=True)
    # A directory holding one program called `claude`, put on the front of `PATH`. The adapter looks
    # for its brain by name, exactly as it does on a real machine.
    instead = home / "bin"
    instead.mkdir(parents=True, exist_ok=True)
    (instead / "claude").write_bytes(A_BRAIN.read_bytes())
    (instead / "claude").chmod(0o755)

    told = {"PATH": f"{instead}:/usr/bin:/bin", "CAPTURED": str(captured),
            "RUNDESK_CWD": str(where), "RUNDESK_ACCESS_MODE": "work",
            "RUNDESK_AGENT": "cole", "RUNDESK_RUN": "1",
            "RUNDESK_CONTINUITY": "AGENTS.md=rules,MEMORY.md=memory,SOUL.md=identity"}
    told.update(also)
    saying = [{"type": "say", "text": prompt}]
    if steering:
        saying.append({"type": "say", "text": steering, "context": "mid-turn"})
    got = subprocess.run([str(ADAPTER)],
                         input="".join(json.dumps(one) + "\n" for one in saying),
                         capture_output=True, text=True, timeout=PATIENCE, env=told, check=False)
    said = [json.loads(one) for one in got.stdout.splitlines() if one.strip()]
    return said, got


def only(said, kind):
    return [one for one in said if one.get("type") == kind]


def a_turn(*lines, ok=True, result="41", usage=None):
    """One made-up turn in the shape this brain streams one: what it said, then how it ended."""
    ending = {"type": "result", "subtype": "success" if ok else "error_during_execution",
              "is_error": not ok, "result": result, "session_id": "s-1",
              "usage": usage if usage is not None else {"output_tokens": 1}}
    return [*lines, json.dumps(ending)]


def it_said(text):
    return json.dumps({"type": "assistant", "parent_tool_use_id": None,
                       "message": {"role": "assistant", "usage": {"input_tokens": 1},
                                   "content": [{"type": "text", "text": text}]}})


class Capabilities(support.Isolated):
    """Asked offline, with no account and no network, and the same answer every time."""

    def answered(self, path=NO_VENDOR):
        got = subprocess.run([str(ADAPTER), "--capabilities"], capture_output=True, text=True,
                             timeout=PATIENCE, env={"PATH": path}, check=False)
        return got, json.loads(got.stdout)

    def test_it_says_it_can_do_all_five(self):
        """`steer` among them, and it is the one that changes how a turn is *run* rather than what
        is recorded of it — so it is claimed only because the whole sequence was driven."""
        _got, can = self.answered()
        self.assertEqual({"tools": True, "resume": True, "model": True, "usage": True,
                          "steer": True},
                         {k: v for k, v in can.items() if k in
                          ("tools", "resume", "model", "usage", "steer")})

    def test_it_answers_with_no_vendor_on_the_machine_at_all(self):
        got, can = self.answered()
        self.assertEqual(0, got.returncode)
        self.assertTrue(can["tools"])
        self.assertNotIn("claude_cli", can)


class OneCapturedTurn(support.Isolated):
    """One real turn, replayed, and every reading the adapter makes of it."""

    def setUp(self):
        super().setUp()
        self.said, self.got = replayed(self.home)

    def test_it_ends_with_exactly_one_done_and_exits_zero(self):
        self.assertEqual(1, len(only(self.said, "done")), "a turn must end exactly once")
        self.assertEqual("done", self.said[-1]["type"])
        self.assertTrue(self.said[-1]["ok"])
        self.assertEqual(0, self.got.returncode)

    def test_what_the_agent_said_comes_back_whole_and_never_a_fragment_at_a_time(self):
        spoken = only(self.said, "text")
        self.assertEqual(["41"], [one["text"] for one in spoken])
        self.assertTrue(spoken[0]["whole"])

    def test_the_answer_is_not_said_twice(self):
        """It arrives as a whole `assistant` block **and** again inside `result.result`. Reporting
        both would give whoever asked the answer twice."""
        self.assertEqual(1, len(only(self.said, "text")))

    def test_a_tool_and_its_result_are_paired_by_the_brains_own_id(self):
        tool, result = only(self.said, "tool")[0], only(self.said, "result")[0]
        self.assertEqual(tool["id"], result["id"])
        self.assertEqual("Read", tool["name"])
        self.assertEqual("read", tool["did"])
        self.assertTrue(result["ok"])

    def test_the_input_side_is_where_the_turn_ended_and_not_every_request_added_up(self):
        """**The reading that costs money if it is wrong.** A prompt is re-sent on every request a
        turn makes, so the final line counts it once per request: this turn's `result` says 40,328
        cache reads where the conversation it ended on was 25,046. A longer measured turn reported
        fifteen million, which is a bill and not anything about a turn."""
        counted = only(self.said, "usage")[0]
        self.assertEqual(25046, counted["cache_read_tokens"])
        self.assertEqual(2, counted["input_tokens"])
        self.assertEqual(125, counted["cache_write_tokens"])

    def test_output_is_the_total_because_output_is_never_sent_twice(self):
        """The other half of the same reading: every token is generated once, so the final line's
        total is exactly what the turn wrote."""
        self.assertEqual(112, only(self.said, "usage")[0]["output_tokens"])

    def test_the_three_input_quantities_are_kept_apart_because_they_bill_apart(self):
        counted = only(self.said, "usage")[0]
        self.assertEqual(3, len({"input_tokens", "cache_read_tokens", "cache_write_tokens"}
                                & set(counted)))

    def test_how_big_the_conversation_ended_is_a_level_and_not_one_of_the_costs(self):
        """The three input pieces put back together: one prompt, at the moment the turn ended."""
        counted = only(self.said, "usage")[0]
        self.assertEqual(25173, counted["context_tokens"])
        self.assertEqual(counted["input_tokens"] + counted["cache_read_tokens"]
                         + counted["cache_write_tokens"], counted["context_tokens"])

    def test_the_model_that_actually_answered_is_named_off_the_line_that_names_one(self):
        """Never off the usage block: that names **two**, because a smaller model runs beside the
        one that was asked for."""
        self.assertEqual("claude-opus-5[1m]", only(self.said, "usage")[0]["model_name"])

    def test_account_state_is_reported_apart_from_the_work(self):
        """A turn carrying one of these may have succeeded — it is news about the account."""
        allowance = only(self.said, "limit")
        self.assertEqual(1, len(allowance))
        self.assertEqual("2026-08-06T18:00:00Z", allowance[0]["resets_at"])
        self.assertTrue(self.said[-1]["ok"], "an allowance was treated as a failure")

    def test_no_percentage_is_claimed_because_this_brain_reports_none(self):
        """**A figure nobody measured is a figure somebody plans around.** This brain's allowance
        object carries a status, a window name and a reset time, and no number of anything."""
        self.assertNotIn("percent_left", only(self.said, "limit")[0])

    def test_nothing_it_cannot_honestly_report_is_reported(self):
        """It names a file it *touched*, never one it made for a person, and a `file` record is what
        gets attached to a message on a channel."""
        self.assertEqual([], only(self.said, "file"))

    def test_what_the_brain_itself_printed_is_kept_verbatim_when_somewhere_was_offered(self):
        at = self.home / "raw.jsonl"
        said, _got = replayed(self.home, RUNDESK_RAW=str(at))
        kept = at.read_text(encoding="utf-8").splitlines()
        self.assertGreater(len(kept), 0)
        self.assertTrue(any('"rate_limit_event"' in one for one in kept))
        self.assertGreater(len(kept), len(only(said, "text")))


class WhenItIsSteeredMidTurn(support.Isolated):
    """A real interrupted exchange. **Nothing short of one proves any of this.**"""

    def setUp(self):
        super().setUp()
        self.said, self.got = replayed(self.home, prompt="run three long commands",
                                       captured=STEERED, steering="stop, say STEERED")

    def test_the_word_that_arrived_mid_turn_reached_the_brain_inside_the_same_turn(self):
        self.assertEqual("STEERED", only(self.said, "text")[-1]["text"])

    def test_it_is_still_one_turn_and_one_ending(self):
        """**Ordinary input queues.** Sending a second message to a working brain asks for another
        turn rather than steering it, and the owner gets two answers to one question. The capture
        holds two `result` lines because the interrupt really did end a request; only one of them
        is this turn's ending."""
        self.assertEqual(2, sum(1 for line in STEERED.read_text(encoding="utf-8").splitlines()
                                if '"type": "result"' in line or '"type":"result"' in line),
                         "this fixture is only worth having while it holds an interrupted request")
        self.assertEqual(1, len(only(self.said, "done")))
        self.assertTrue(self.said[-1]["ok"])

    def test_a_stopped_request_is_not_reported_as_a_turn_that_failed(self):
        """The interrupted `result` says `error_during_execution`. It is the part of the work that
        was stopped, not the turn's outcome."""
        self.assertEqual(0, self.got.returncode)
        self.assertNotIn("failure_code", self.said[-1])

    def test_what_the_stopped_request_cost_is_still_billed(self):
        """122 output tokens were spent before the interrupt and 6 after it. Dropping the first
        would under-report every steered turn, and the owner was charged for both."""
        self.assertEqual(128, only(self.said, "usage")[0]["output_tokens"])

    def test_a_tool_stopped_by_the_interrupt_is_not_reported_as_a_tool_that_failed(self):
        """Stopping an in-flight tool makes this brain emit an ordinary-looking failed result for
        it, and the field that used to mark it as a cancellation is no longer sent — so the only
        thing that tells them apart is that an interrupt is pending."""
        self.assertEqual([], [one for one in only(self.said, "result") if not one["ok"]])


class WhatItAsksTheBrainFor(support.Isolated):
    """What goes *out* is half the contract, and the capture cannot check it. This can."""

    def spoke(self, **also):
        """Every argument and every line the adapter sent, off a brain that writes down what it was
        told."""
        where = self.home / "cwd"
        where.mkdir(parents=True, exist_ok=True)
        instead = self.home / "bin"
        instead.mkdir(parents=True, exist_ok=True)
        (instead / "claude").write_bytes(A_BRAIN.read_bytes())
        (instead / "claude").chmod(0o755)
        heard = self.home / "heard.jsonl"
        heard.write_text("", encoding="utf-8")
        told = {"PATH": f"{instead}:/usr/bin:/bin", "HEARD": str(heard),
                "CAPTURED": str(CAPTURED), "RUNDESK_CWD": str(where),
                "RUNDESK_ACCESS_MODE": "work", "RUNDESK_AGENT": "cole", "RUNDESK_RUN": "1"}
        told.update(also)
        subprocess.run([str(ADAPTER)], input=json.dumps({"type": "say", "text": "hello"}) + "\n",
                       capture_output=True, text=True, timeout=PATIENCE, env=told, check=False)
        return [json.loads(one) for one in heard.read_text(encoding="utf-8").splitlines()
                if one.strip()]

    def setUp(self):
        super().setUp()
        self.spoken = None

    def argv(self):
        return next(one for one in self.spoken if "argv" in one)["argv"]

    def test_the_prompt_is_never_put_on_the_command_line(self):
        """Every process on the machine can read one — and this brain's tool flags are variadic
        besides, so a trailing positional is swallowed and the mistake is reported against the
        wrong argument."""
        self.spoken = self.spoke()
        self.assertNotIn("hello", " ".join(self.argv()))
        said = [one for one in self.spoken if one.get("type") == "user"]
        self.assertEqual("hello", said[0]["message"]["content"])

    def test_a_new_conversation_is_given_a_handle_before_the_first_byte(self):
        """Minted here rather than learned from a line that may never arrive."""
        self.spoken = self.spoke()
        self.assertIn("--session-id", self.argv())
        self.assertNotIn("--resume", self.argv())

    def test_a_conversation_being_carried_on_is_resumed_and_never_re_opened(self):
        self.spoken = self.spoke(RUNDESK_RESUME="abc-123")
        self.assertEqual("abc-123", self.argv()[self.argv().index("--resume") + 1])
        self.assertNotIn("--session-id", self.argv())

    def test_every_turn_gets_the_whole_machine(self):
        self.spoken = self.spoke()
        self.assertIn("--dangerously-skip-permissions", self.argv())

    def test_a_narrower_access_mode_does_not_quietly_narrow_the_turn(self):
        """**The teeth on the decision above.** `RUNDESK_ACCESS_MODE` is a word the seam carries and
        this adapter deliberately ignores, so the case that matters is the one where it is set to
        the narrow value."""
        self.spoken = self.spoke(RUNDESK_ACCESS_MODE="read")
        self.assertIn("--dangerously-skip-permissions", self.argv())
        self.assertNotIn("--allowedTools", self.argv())

    def test_the_preface_is_added_to_the_brains_instructions_and_never_replaces_them(self):
        """The replacing flag takes about 6,100 tokens of this brain's own instructions with it:
        nothing reports that, the tools keep working, and the turn merely behaves differently."""
        self.spoken = self.spoke(RUNDESK_PREFACE="stand up straight")
        self.assertEqual("stand up straight",
                         self.argv()[self.argv().index("--append-system-prompt") + 1])
        self.assertNotIn("--system-prompt", self.argv())

    def test_the_model_asked_for_is_passed_on_and_an_unset_one_is_left_out(self):
        self.spoken = self.spoke(RUNDESK_MODEL="claude-opus-5")
        self.assertEqual("claude-opus-5", self.argv()[self.argv().index("--model") + 1])
        self.spoken = self.spoke()
        self.assertNotIn("--model", self.argv())

    def test_the_control_protocol_is_opened_before_anything_is_said(self):
        """Steering is a sequence and not a write, and this is its first step."""
        self.spoken = self.spoke()
        asked = [one for one in self.spoken if one.get("type") == "control_request"]
        self.assertEqual("initialize", asked[0]["request"]["subtype"])

    def test_rundesks_own_words_are_carried_apart_from_the_persons(self):
        """A bare line appended to a running turn is refused by real brains as suspected prompt
        injection, so rundesk's context goes first and marked — and what the person said is
        unaltered beneath it."""
        where = self.home / "cwd"
        where.mkdir(parents=True, exist_ok=True)
        instead = self.home / "bin"
        instead.mkdir(parents=True, exist_ok=True)
        (instead / "claude").write_bytes(A_BRAIN.read_bytes())
        (instead / "claude").chmod(0o755)
        heard = self.home / "heard.jsonl"
        heard.write_text("", encoding="utf-8")
        subprocess.run(
            [str(ADAPTER)],
            input="".join(json.dumps(one) + "\n" for one in (
                {"type": "say", "text": "count to thirty"},
                {"type": "say", "text": "stop", "context": "guidance from rundesk"})),
            capture_output=True, text=True, timeout=PATIENCE, check=False,
            env={"PATH": f"{instead}:/usr/bin:/bin", "HEARD": str(heard),
                 "CAPTURED": str(STEERED), "RUNDESK_CWD": str(where),
                 "RUNDESK_AGENT": "cole", "RUNDESK_RUN": "1"})
        spoken = [json.loads(one) for one in heard.read_text(encoding="utf-8").splitlines()
                  if one.strip()]
        steered = [one for one in spoken if one.get("type") == "user"][-1]
        self.assertEqual("[rundesk] guidance from rundesk\n\nstop",
                         steered["message"]["content"])

    def test_an_agents_skills_are_offered_where_this_brain_looks(self):
        skills = self.home / "skills"
        (skills / "a-skill").mkdir(parents=True)
        self.spoke(RUNDESK_SKILLS=str(skills))
        stood = self.home / "cwd" / ".claude" / "skills" / "a-skill"
        self.assertTrue(stood.is_symlink(), "a granted skill was not presented")
        self.assertTrue(stood.resolve().is_dir())

    def test_an_agent_granted_none_has_no_vendor_directory_to_explain(self):
        self.spoke(RUNDESK_SKILLS=str(self.home / "nothing-here"))
        self.assertFalse((self.home / "cwd" / ".claude").exists())


class WhatAnAgentChangedOfItsOwn(support.Isolated):
    """An agent's own files being rewritten is different news from a working file being rewritten,
    and both arrive as the same `edit`."""

    def edited(self, at):
        where = self.home / "cwd"
        made = self.home / "edited.jsonl"
        made.write_text("\n".join(a_turn(json.dumps({
            "type": "assistant", "parent_tool_use_id": None,
            "message": {"role": "assistant", "usage": {},
                        "content": [{"type": "tool_use", "id": "t1", "name": "Edit",
                                     "input": {"file_path": str(where / at)
                                               if not str(at).startswith("/") else str(at)}}]}}),
        )) + "\n", encoding="utf-8")
        said, _got = replayed(self.home, captured=made)
        return only(said, "tool")[0]

    def test_rewriting_what_it_lives_by_is_said_as_what_it_is(self):
        self.assertEqual("rules", self.edited("AGENTS.md")["did"])
        self.assertEqual("memory", self.edited("MEMORY.md")["did"])
        self.assertEqual("identity", self.edited("SOUL.md")["did"])

    def test_a_files_name_is_not_the_test(self):
        """**Every checkout on the machine has an `AGENTS.md`**, and an agent editing one in a
        repository has not rewritten its own rules. Saying it did is worse than the plain `edit` it
        would otherwise get, because it is untrue."""
        somewhere = self.home / "a-checkout"
        somewhere.mkdir(parents=True, exist_ok=True)
        self.assertEqual("edit", self.edited(somewhere / "AGENTS.md")["did"])

    def test_an_ordinary_file_is_an_ordinary_edit(self):
        self.assertEqual("edit", self.edited("notes.txt")["did"])


class WhenItCannotRunAtAll(support.Isolated):

    def test_a_brain_that_is_not_on_the_machine_is_said_as_a_done_and_never_as_silence(self):
        """**Rundesk reading no `done` at all is a turn nobody can explain.**"""
        got = subprocess.run([str(ADAPTER)],
                             input=json.dumps({"type": "say", "text": "hello"}) + "\n",
                             capture_output=True, text=True, timeout=PATIENCE, check=False,
                             env={"PATH": NO_VENDOR, "RUNDESK_CWD": str(self.home)})
        said = [json.loads(one) for one in got.stdout.splitlines() if one.strip()]
        self.assertEqual(1, len(said))
        self.assertEqual("done", said[0]["type"])
        self.assertFalse(said[0]["ok"])
        self.assertEqual("crashed", said[0]["failure_code"])
        self.assertNotEqual(0, got.returncode)


class EveryWayTheBrainSaysItFailed(support.Isolated):

    def failed_with(self, said):
        at = self.home / "failed.jsonl"
        at.write_text("\n".join(a_turn(ok=False, result=said)) + "\n", encoding="utf-8")
        records, got = replayed(self.home, captured=at)
        return records[-1], got

    def test_each_of_the_brains_own_words_becomes_the_right_closed_word(self):
        for said, word in HOW_IT_FAILS:
            with self.subTest(said=said):
                ending, _got = self.failed_with(said)
                self.assertFalse(ending["ok"])
                self.assertEqual(word, ending["failure_code"])
                self.assertIn(said.split(":")[0][:12], ending["failure_message"])

    def test_a_failure_this_release_has_never_heard_of_carries_no_word_and_keeps_the_message(self):
        """**A word guessed from a message is a word that is wrong on the first release that
        rewords one**, and a wrong word in a column nothing can audit is worse than an absent one."""
        ending, _got = self.failed_with("the flux capacitor came loose")
        self.assertFalse(ending["ok"])
        self.assertNotIn("failure_code", ending)
        self.assertIn("flux capacitor", ending["failure_message"])

    def test_a_failed_turn_hands_back_no_handle_to_carry_it_on_with(self):
        """This adapter mints the id before the first byte, so a conversation whose turn failed may
        never have been created — and handing one back poisons every turn after it."""
        ending, _got = self.failed_with("something went wrong")
        self.assertNotIn("session_id", ending)

    def test_the_program_still_did_its_job_when_the_brain_reported_a_failure(self):
        """The exit code says what became of the **program**, never what became of the turn."""
        _ending, got = self.failed_with("usage limit reached")
        self.assertEqual(0, got.returncode)

    def test_every_word_it_can_produce_is_one_rundesk_knows(self):
        """**A word rundesk does not know is dropped rather than stored**, so one invented here
        would vanish silently rather than fail — which is why this asks what the adapter actually
        produces rather than what its source happens to contain."""
        produced = set()
        for said, _word in HOW_IT_FAILS:
            ending, _got = self.failed_with(said)
            produced.add(ending.get("failure_code"))
        self.assertTrue(produced <= FAILURE_CODES,
                        f"this adapter produces a word rundesk has no column for: "
                        f"{sorted(produced - FAILURE_CODES)}")


class AStreamThisSideCannotRead(support.Isolated):
    """What a turn does when the brain stops making sense, which is the shape most likely to be met
    in the wild and least likely to be captured."""

    def a_stream(self, lines, **also):
        at = self.home / "made-up.jsonl"
        at.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return replayed(self.home, captured=at, **also)

    def test_a_brain_that_simply_stopped_is_said_rather_than_reported_as_success(self):
        """**Exiting zero having said nothing is the failure that looks most like a success.**"""
        said, got = self.a_stream([it_said("half a th")], THEN_DIE="1")
        self.assertEqual("done", said[-1]["type"])
        self.assertFalse(said[-1]["ok"])
        self.assertEqual("crashed", said[-1]["failure_code"])
        self.assertNotEqual(0, got.returncode)

    def test_a_line_that_will_not_parse_leaves_the_records_around_it_alone(self):
        said, _got = self.a_stream(a_turn("{not json at all", it_said("41")))
        self.assertEqual(["41"], [one["text"] for one in only(said, "text")])
        self.assertTrue(said[-1]["ok"])

    def test_a_line_too_long_to_hold_is_dropped_whole_and_the_turn_carries_on(self):
        """**Half a record is not a smaller record, it is a corrupt one** — nothing downstream could
        tell that apart from the brain talking nonsense."""
        said, _got = self.a_stream(a_turn(it_said("y" * (1024 * 1024 + 64)), it_said("41")))
        self.assertEqual(["41"], [one["text"] for one in only(said, "text")],
                         "a line past the bound was reported, whole or in pieces")
        self.assertTrue(said[-1]["ok"])


class TheVersionItWasWrittenAgainst(support.Isolated):
    """A capture with no version beside it is a fixture nobody can act on."""

    def test_the_lock_names_the_version_every_capture_came_from(self):
        lock = (support.CHECKOUT / "cli-versions.lock").read_text(encoding="utf-8")
        self.assertIn("claude 2.1.223", lock)
        for one in (CAPTURED, STEERED):
            self.assertIn(one.name, lock, f"{one.name} is not named in cli-versions.lock")


if __name__ == "__main__":
    unittest.main()
