"""The codex adapter, against a stream a real codex once produced.

**No account, no token, no network.** `tests/samples/codex-app-server-0.146.0.jsonl` is what
`codex app-server` said during one real turn on 2026-08-06, captured whole and scrubbed of paths;
`tests/samples/a-captured-brain` says it again on demand. So every reading this adapter makes is
checked against the vendor rather than against a stand-in written to agree with it — which is the
one thing a hand-written fake cannot do — and the suite still never reaches a vendor, which is both
this repository's rule and a terms one.

**What the fixture is for is drift.** The day codex changes its stream, this file goes red with the
reading that broke, and `cli-versions.lock` says which version the fixture came from. Without it the
first sign would be an agent behaving oddly with nothing to compare against.

The adapter is run as the program it is, through the environment it is really given. Nothing here
imports it — it has no importable shape, deliberately, and a case that reached inside it would be
proving something the seam does not promise.

Run directly: `python3 tests/test_providers_codex.py`
"""

import json
import subprocess
import unittest

import support

#: The adapter under test, and the two files that let it run with no vendor on the machine.
ADAPTER = support.CHECKOUT / "src" / "providers" / "codex"
CAPTURED = support.CHECKOUT / "tests" / "samples" / "codex-app-server-0.146.0.jsonl"

#: A second turn, on a thread that had already cost 30,890 tokens when it began. **The first capture
#: cannot prove the usage arithmetic** — a turn that begins at zero reports the same numbers whether
#: the baseline is subtracted or ignored — so the case that would over-report every turn of every
#: resumed conversation needs a capture that did not start from nothing.
RESUMED = support.CHECKOUT / "tests" / "samples" / "codex-app-server-0.146.0-resumed.jsonl"

#: One stream per way the vendor's own schema says a turn can fail. **Not captures** — provoking a
#: revoked credential or a spent allowance means abusing an account, and a test that reached a
#: vendor is refused here anyway. Each is the vendor's documented error name in the vendor's
#: documented shape, so what is proved is the mapping and not the wording of a message.
FAILURES = support.CHECKOUT / "tests" / "samples" / "codex-failures"
A_BRAIN = support.CHECKOUT / "tests" / "samples" / "a-captured-brain"

#: How long the adapter may take to translate a capture. It does no waiting of its own here, so this
#: is a ceiling on something that finishes in hundredths and never a duration anything relies on.
PATIENCE = 60.0


def replayed(home, prompt="Read note.txt and tell me the number in it.", captured=CAPTURED,
             steering=None, **also):
    """Run the adapter against the capture and hand back every record it made, in order."""
    where = home / "cwd"
    where.mkdir(parents=True, exist_ok=True)
    # A directory holding one program called `codex`, put on the front of `PATH`. The adapter looks
    # for its brain by name, exactly as it does on a real machine.
    instead = home / "bin"
    instead.mkdir(parents=True, exist_ok=True)
    (instead / "codex").write_bytes(A_BRAIN.read_bytes())
    (instead / "codex").chmod(0o755)

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
    said = []
    for line in got.stdout.splitlines():
        if line.strip():
            said.append(json.loads(line))
    return said, got


class Capabilities(support.Isolated):
    """Asked offline, with no account and no network, and the same answer every time."""

    def asked(self):
        got = subprocess.run([str(ADAPTER), "--capabilities"], capture_output=True, text=True,
                             timeout=PATIENCE, env={"PATH": "/usr/bin:/bin"}, check=False)
        return json.loads(got.stdout)

    def test_it_says_it_can_do_all_five(self):
        self.assertEqual({"tools": True, "resume": True, "model": True, "usage": True,
                          "steer": True},
                         {one: self.asked()[one] for one in
                          ("tools", "resume", "model", "usage", "steer")})

    def test_it_answers_with_no_vendor_on_the_machine_at_all(self):
        """`--capabilities` is what lets an absence be a fact rather than a guess, so it must not
        need the brain to be installed to say what the adapter can do."""
        self.assertNotIn("codex_cli", self.asked())


class OneCapturedTurn(support.Isolated):

    def setUp(self):
        super().setUp()
        self.said, self.got = replayed(self.home)

    def of_type(self, kind):
        return [one for one in self.said if one.get("type") == kind]

    def test_it_ends_with_exactly_one_done_and_exits_zero(self):
        """**A turn always ends with a `done`.** Rundesk reading none at all is a turn nobody can
        explain."""
        self.assertEqual(0, self.got.returncode, self.got.stderr[-2000:])
        self.assertEqual(1, len(self.of_type("done")))
        self.assertIs(self.said[-1], self.of_type("done")[0])

    def test_the_done_says_it_worked_and_carries_the_handle_to_carry_it_on_with(self):
        done = self.of_type("done")[0]
        self.assertTrue(done["ok"])
        self.assertEqual("019fd763-7c7a-7521-bcc9-1b560b60709d", done["session_id"])

    def test_what_the_agent_said_comes_back_whole_and_never_a_fragment_at_a_time(self):
        """The brain streams a word at a time; a reply that rewrites itself in place is unreadable,
        so what is reported is the finished thing."""
        text = self.of_type("text")
        self.assertTrue(all(one["whole"] for one in text))
        self.assertIn("41", [one["text"] for one in text])

    def test_the_working_out_and_the_answer_both_arrive(self):
        """Codex says something in `commentary` before it uses a tool and answers in `final_answer`
        at the end. Both are things the agent said."""
        self.assertEqual(2, len(self.of_type("text")))

    def test_a_command_is_reported_by_what_it_did_and_not_by_the_brains_word_for_it(self):
        """It ran `sed -n '1,40p' note.txt`. **`read`** is the word rundesk carries, because the
        same act is `Bash` on one brain and `run_terminal_command` on the next."""
        tool = self.of_type("tool")[0]
        self.assertEqual("read", tool["did"])
        self.assertIn("sed", tool["name"])

    def test_a_tool_and_its_result_are_paired_by_the_brains_own_id(self):
        self.assertEqual(self.of_type("tool")[0]["id"], self.of_type("result")[0]["id"])

    def test_a_result_says_whether_it_worked_and_what_it_reported(self):
        result = self.of_type("result")[0]
        self.assertTrue(result["ok"])
        self.assertIn("exit 0", result["summary"])
        self.assertIn("the answer is 41", result["summary"])

    def test_the_turns_own_share_of_the_conversation_is_reported_and_never_the_thread_total(self):
        """The brain reports a running total for the whole conversation. This turn's share is the
        total at the end less the baseline, and the baseline is recovered from the turn's own first
        update — which is what stops the first turn of a resumed thread being billed for all of it.
        """
        usage = self.of_type("usage")[0]
        self.assertEqual(30709, usage["input_tokens"])
        self.assertEqual(123, usage["output_tokens"])
        self.assertEqual(22016, usage["cache_read_tokens"])

    def test_how_big_the_conversation_ended_is_a_level_and_not_one_of_the_costs(self):
        self.assertEqual(15428, self.of_type("usage")[0]["context_tokens"])

    def test_the_model_that_actually_answered_is_named(self):
        self.assertEqual("gpt-5.6-sol", self.of_type("usage")[0]["model_name"])

    def test_account_state_is_reported_apart_from_the_work(self):
        """News about the account, never about the work: this turn carrying one *succeeded*."""
        limit = self.of_type("limit")[0]
        self.assertEqual(73, limit["percent_left"])
        self.assertEqual("2026-08-08T03:33:24Z", limit["resets_at"])

    def test_an_unchanged_allowance_is_not_reported_twice(self):
        """The brain reports it after every model request. The same percentage twice is not news."""
        self.assertEqual(1, len(self.of_type("limit")))

    def test_nothing_a_person_would_recognise_as_a_vendors_word_reaches_a_record(self):
        """Every record is in rundesk's vocabulary. A brain's own words stay in the raw stream."""
        said = json.dumps(self.said)
        for theirs in ("agentMessage", "commandExecution", "threadId", "turnId", "codexErrorInfo"):
            self.assertNotIn(theirs, said)

    def test_what_the_brain_itself_printed_is_kept_verbatim_when_somewhere_was_offered(self):
        """Rundesk sees what the *adapter* reported and never what the brain said, so a vendor
        changing its stream would otherwise show up as records quietly going missing."""
        raw = self.home / "raw.jsonl"
        said, _got = replayed(self.home, **{"RUNDESK_RAW": str(raw)})
        self.assertTrue(said)
        kept = raw.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(CAPTURED.read_text(encoding="utf-8").strip().splitlines()), len(kept))


class WhatItAsksTheBrainFor(support.Isolated):
    """What goes *out* is half the contract, and the capture cannot check it. This can."""

    def spoke(self, **also):
        """Every request the adapter sent, read off a brain that writes down what it was told."""
        where = self.home / "cwd"
        where.mkdir(parents=True, exist_ok=True)
        instead = self.home / "bin"
        instead.mkdir(parents=True, exist_ok=True)
        heard = self.home / "heard.jsonl"
        (instead / "codex").write_text('''#!/usr/bin/env python3
import json, os, sys
if "--capabilities" in sys.argv[1:]:
    print('{"tools": true}'); raise SystemExit(0)
for line in sys.stdin:
    with open(os.environ["HEARD"], "a") as writing:
        writing.write(line)
    try:
        said = json.loads(line)
    except ValueError:
        continue
    if said.get("method") == "initialize":
        print(json.dumps({"id": said["id"], "result": {}}), flush=True)
    elif said.get("method") in ("thread/start", "thread/resume"):
        print(json.dumps({"id": said["id"], "result": {"thread": {"id": "t-1"}, "model": "m-1"}}),
              flush=True)
    elif said.get("method") == "turn/start":
        print(json.dumps({"id": said["id"], "result": {}}), flush=True)
        print(json.dumps({"method": "turn/completed",
                          "params": {"threadId": "t-1",
                                     "turn": {"id": "u-1", "status": "completed"}}}), flush=True)
''', encoding="utf-8")
        (instead / "codex").chmod(0o755)
        heard.write_text("", encoding="utf-8")
        told = {"PATH": f"{instead}:/usr/bin:/bin", "HEARD": str(heard),
                "RUNDESK_CWD": str(where), "RUNDESK_ACCESS_MODE": "work",
                "RUNDESK_AGENT": "cole", "RUNDESK_RUN": "1"}
        told.update(also)
        subprocess.run([str(ADAPTER)], input=json.dumps({"type": "say", "text": "hello"}) + "\n",
                       capture_output=True, text=True, timeout=PATIENCE, env=told, check=False)
        return [json.loads(one) for one in heard.read_text(encoding="utf-8").splitlines()
                if one.strip()]

    def sent(self, method):
        return [one for one in self.spoken if one.get("method") == method]

    def setUp(self):
        super().setUp()
        self.spoken = None

    def test_it_says_who_it_is_and_never_pretends_to_be_somebody_else(self):
        self.spoken = self.spoke()
        self.assertEqual("rundesk", self.sent("initialize")[0]["params"]["clientInfo"]["name"])

    def test_the_owners_thread_list_shows_where_the_thread_came_from(self):
        self.spoken = self.spoke()
        self.assertEqual("rundesk", self.sent("thread/start")[0]["params"]["threadSource"])

    def test_every_turn_asks_the_brain_for_the_whole_machine(self):
        """The owner's decision, and the adapter says so in one place rather than deriving it.

        Both spellings are asserted because the brain's own schema has two — a mode where a thread
        is opened and a policy object where a turn is started — and getting one right while the
        other stayed narrow would be a turn that could read everything and write nothing.
        """
        self.spoken = self.spoke()
        self.assertEqual("danger-full-access", self.sent("thread/start")[0]["params"]["sandbox"])
        self.assertEqual({"type": "dangerFullAccess"},
                         self.sent("turn/start")[0]["params"]["sandboxPolicy"])

    def test_a_narrower_access_mode_does_not_quietly_narrow_the_turn(self):
        """**The teeth on the decision above.** `RUNDESK_ACCESS_MODE` is a word the seam still
        carries and this adapter deliberately ignores, so the case that matters is the one where it
        is set to the narrow value: a turn that came back scoped would mean the ignoring had been
        undone somewhere, which is exactly the kind of change that looks like a tidy-up.
        """
        self.spoken = self.spoke(RUNDESK_ACCESS_MODE="read")
        self.assertEqual("danger-full-access", self.sent("thread/start")[0]["params"]["sandbox"])
        self.assertEqual({"type": "dangerFullAccess"},
                         self.sent("turn/start")[0]["params"]["sandboxPolicy"])

    def test_the_preface_is_added_to_the_brains_instructions_and_never_replaces_them(self):
        """`baseInstructions` replaces what the brain was built with. Sending an owner's paragraph
        there does not add a paragraph — it deletes the brain and leaves the paragraph, nothing
        reports it, and the turn merely behaves strangely."""
        self.spoken = self.spoke(RUNDESK_PREFACE="stand up straight")
        params = self.sent("thread/start")[0]["params"]
        self.assertEqual("stand up straight", params["developerInstructions"])
        self.assertNotIn("baseInstructions", params)

    def test_a_resumed_conversation_carries_no_preface_because_the_brain_would_ignore_one(self):
        """Measured against 0.146.0 three ways: bound at `thread/start`, obeyed after a resume that
        does not re-send it, and accepted-then-ignored when a different one is sent on the resume.
        **An argument accepted and then dropped is worse than one never sent**, because it reads
        like it works and somebody rewording it watches nothing happen."""
        self.spoken = self.spoke(RUNDESK_RESUME="t-0", RUNDESK_PREFACE="stand up straight")
        self.assertEqual([], self.sent("thread/start"))
        params = self.sent("thread/resume")[0]["params"]
        self.assertEqual("t-0", params["threadId"])
        self.assertNotIn("developerInstructions", params)

    def test_the_model_asked_for_is_passed_on_and_an_unset_one_is_left_out(self):
        self.spoken = self.spoke(RUNDESK_MODEL="a-particular-one")
        self.assertEqual("a-particular-one", self.sent("thread/start")[0]["params"]["model"])
        self.spoken = self.spoke()
        self.assertNotIn("model", self.sent("thread/start")[0]["params"])

    def test_reasoning_is_asked_for_or_the_brain_thinks_in_silence(self):
        """Without it no `think` record ever arrives, and the seam carries nothing of how a turn
        reached its answer."""
        self.spoken = self.spoke()
        self.assertEqual("auto", self.sent("turn/start")[0]["params"]["summary"])

    def test_an_agents_skills_are_offered_where_the_brain_looks_and_nothing_is_written_anywhere(self):
        """The brain has a call for exactly this, so there is no directory of ours in somebody's
        home to explain and nothing to remove afterwards."""
        skills = self.home / "skills"
        (skills / "a-skill").mkdir(parents=True)
        self.spoken = self.spoke(RUNDESK_SKILLS=str(skills))
        self.assertEqual([str(skills.resolve())],
                         self.sent("skills/extraRoots/set")[0]["params"]["extraRoots"])

    def test_an_agent_granted_none_is_offered_none_rather_than_an_empty_root(self):
        self.spoken = self.spoke(RUNDESK_SKILLS=str(self.home / "nothing-here"))
        self.assertEqual([], self.sent("skills/extraRoots/set"))


class WhenItCannotRunAtAll(support.Isolated):

    def test_a_brain_that_is_not_on_the_machine_is_said_as_a_done_and_never_as_silence(self):
        """**Rundesk reading no `done` at all is a turn nobody can explain**, so even the failure
        that happens before anything starts says so in the one way rundesk can act on."""
        got = subprocess.run([str(ADAPTER)], input='{"type": "say", "text": "hello"}\n',
                             capture_output=True, text=True, timeout=PATIENCE,
                             env={"PATH": f"{self.home}:/usr/bin:/bin",
                                  "RUNDESK_CWD": str(self.home)},
                             check=False)
        self.assertNotEqual(0, got.returncode)
        said = [json.loads(one) for one in got.stdout.splitlines() if one.strip()]
        self.assertEqual("done", said[-1]["type"])
        self.assertFalse(said[-1]["ok"])
        self.assertEqual("crashed", said[-1]["failure_code"])


class ATurnOnAConversationThatHadAlreadyCost(support.Isolated):
    """The arithmetic that decides whether an owner's account of their own spending is true.

    The brain reports a running total for the whole conversation, so a turn's own share is the total
    at the end less what it was before the turn began — and *before it began* is not written down
    anywhere. It is recovered from the turn's own first update as `total - last`, which needs no
    file, nothing kept between runs, and nothing that can go stale.

    This capture began at 30,890. Ignore the baseline and the turn reports 78,531 input tokens
    instead of 47,783 — which is what the build this replaces did to the first turn of every
    existing thread after a restart.
    """

    def setUp(self):
        super().setUp()
        # The capture is of a steered turn, so this steers: the fourth request the adapter makes
        # is what the capture's fourth reply answers, and a run that never steered would leave one
        # unanswered.
        self.said, self.got = replayed(self.home, captured=RESUMED,
                                       steering="stop and say HALTED")

    def of_type(self, kind):
        return [one for one in self.said if one.get("type") == kind]

    def test_only_this_turns_share_is_reported(self):
        usage = self.of_type("usage")[0]
        self.assertEqual(47783, usage["input_tokens"])
        self.assertEqual(1267, usage["output_tokens"])

    def test_how_big_the_conversation_ended_is_the_whole_of_it_and_not_this_turns_share(self):
        """A **level**, not a quantity: it is how much was sent to the model, and it goes *down*
        when a conversation is compacted, which no running total can."""
        self.assertEqual(16790, self.of_type("usage")[0]["context_tokens"])

    def test_it_ends_done_and_carries_the_thread_it_was_resumed_on(self):
        done = self.of_type("done")[0]
        self.assertTrue(done["ok"])
        self.assertEqual("019fd764-b833-76e3-ba83-29f07ab39d3f", done["session_id"])

    def test_a_stream_of_fragments_becomes_the_finished_message_and_never_a_record_each(self):
        """The brain streamed eleven hundred deltas while it wrote this. A reply that rewrites
        itself in place is unreadable, so what is reported is each thing it *finished* saying — two
        of them here, because the steer landed while it was still writing the first."""
        said = [one["text"] for one in self.of_type("text")]
        self.assertEqual(2, len(said))
        self.assertEqual("HALTED", said[-1])

    def test_the_word_that_arrived_mid_turn_reached_the_brain_inside_the_same_turn(self):
        """Not a second turn: `expectedTurnId` is a precondition, so a steer aimed at a turn that
        has already finished is refused rather than quietly starting a new one."""
        self.assertEqual(1, len(self.of_type("done")))
        self.assertEqual("HALTED", self.of_type("text")[-1]["text"])


class EveryWayTheBrainSaysItFailed(support.Isolated):
    """The closed word for each of the vendor's own, and **never one guessed from the prose**.

    A word inferred from a failure message is a word that is wrong on the first vendor that rewords
    one — and the whole value of a closed set is that a person reading a failure does not have to
    know a vendor's error strings to know whether to wait or to act.
    """

    def done_of(self, named):
        # **The brain exits when it has said its piece**, which is what a server that reported a
        # fatal error actually does — and what makes the adapter's own last guard reachable.
        said, got = replayed(self.home, captured=FAILURES / f"{named}.jsonl", THEN_DIE="1")
        self.assertTrue(said, f"{named} produced no records at all")
        self.assertEqual("done", said[-1]["type"], f"{named} did not end with a done")
        return said[-1], got

    def test_each_of_the_brains_own_names_becomes_the_right_closed_word(self):
        for named, wanted in (("unauthorized", "signed_out"),
                              ("usage-limit", "usage_exhausted"),
                              ("session-budget", "usage_exhausted"),
                              ("context-window", "context_exceeded"),
                              ("server-overloaded", "rate_limited"),
                              ("internal-server-error", "upstream_error"),
                              ("cyber-policy", "refused"),
                              ("sandbox", "no_access"),
                              ("offline", "offline"),
                              ("stream-disconnected", "upstream_error")):
            with self.subTest(named=named):
                done, _got = self.done_of(named)
                self.assertFalse(done["ok"])
                self.assertEqual(wanted, done["failure_code"])

    def test_the_status_behind_a_failed_connection_is_more_specific_than_the_kind(self):
        """A 401 on a failed connection is a credential and not a network, and a 402 is a card.
        Reporting either as `offline` would tell somebody to wait for something that will not
        change on its own."""
        for named, wanted in (("unauthorized-by-status", "signed_out"),
                              ("no-credit-by-status", "no_credit"),
                              ("rate-limited-by-status", "rate_limited")):
            with self.subTest(named=named):
                self.assertEqual(wanted, self.done_of(named)[0]["failure_code"])

    def test_a_name_this_release_has_never_heard_of_carries_no_word_and_keeps_the_message(self):
        """**A word left out is better than a wrong one.** A vendor inventing a failure mode must
        not have it filed under the nearest fit, because a reader can exhaust a closed set and
        cannot exhaust one with a wrong member in it."""
        done, _got = self.done_of("one-nobody-has-heard-of")
        self.assertFalse(done["ok"])
        self.assertNotIn("failure_code", done)
        self.assertEqual("the vendor said no", done["failure_message"])

    def test_a_turn_the_brain_is_going_to_retry_itself_has_not_failed(self):
        """`willRetry` means the brain is handling it. A turn recorded as failed because of a blip
        it recovered from is an account of the work that is untrue."""
        done, _got = self.done_of("retried-and-then-worked")
        self.assertTrue(done["ok"])
        self.assertNotIn("failure_code", done)

    def test_a_turn_somebody_stopped_is_cancelled_and_not_an_error(self):
        done, _got = self.done_of("interrupted")
        self.assertFalse(done["ok"])
        self.assertEqual("cancelled", done["failure_code"])

    def test_every_word_it_can_produce_is_one_rundesk_knows(self):
        """The seam drops a word it does not know, so an adapter inventing one reports nothing at
        all. Checked against the closed set rather than against a copy of it kept here."""
        from rundesk.providers import protocol
        for named in sorted(one.stem for one in FAILURES.iterdir()):
            with self.subTest(named=named):
                said = self.done_of(named)[0].get("failure_code")
                if said is not None:
                    self.assertIn(said, protocol.FAILURE_CODES)


class AStreamThisSideCannotRead(support.Isolated):
    """The two ways a stream breaks the *reading* rather than the meaning.

    Every other reader in this product is written against both, and each of them says it was
    measured somewhere first. The one shipped adapter was written against neither: it read its
    child with `for line in stdout` and strict decoding, so one byte of a binary file put the
    reading thread out and left the turn waiting on something that was never coming — silent for
    the length of rundesk's own window, half an hour, on ordinary tool output.
    """

    def test_a_byte_that_is_not_text_ends_the_turn_rather_than_stalling_it(self):
        """A coding agent reads binary files, and what a tool printed comes back inside the
        stream. The turn must come to *something*, quickly."""
        said, _got = replayed(self.home,
                              captured=FAILURES / "a-byte-that-is-not-text.jsonl")
        self.assertTrue(said, "the adapter said nothing at all")
        self.assertEqual("done", said[-1]["type"])

    def test_it_still_understands_the_records_around_the_bad_byte(self):
        """`errors="replace"` rather than a reader that gives up: one unreadable character must not
        cost every record after it."""
        said, _got = replayed(self.home, captured=FAILURES / "a-byte-that-is-not-text.jsonl")
        result = [one for one in said if one.get("type") == "result"]
        self.assertTrue(result, "the record carrying the bad byte was lost whole")
        self.assertIn("binary", result[0]["summary"],
                      "what surrounded the unreadable character went with it")
        self.assertTrue(said[-1]["ok"])

    def test_a_server_that_died_mid_record_still_ends_the_turn_in_words(self):
        """A crash or an OOM kill leaves half a record on the pipe with no newline after it.

        **Half a record is not a smaller record.** Handed on as though it were whole it is a
        corrupt one — and the parse that then fails is swallowed, so the turn goes quiet with
        nothing anywhere saying why. Rundesk can only call that `crashed` from the *absence* of a
        `done`, which is exactly the answer this adapter is supposed to save it from having to
        guess at.
        """
        said, got = replayed(self.home, THEN_DIE="1",
                             captured=FAILURES / "a-server-that-died-mid-record.jsonl")
        self.assertTrue(said, "the adapter said nothing at all")
        self.assertEqual("done", said[-1]["type"])
        self.assertFalse(said[-1]["ok"])
        self.assertNotEqual(0, got.returncode,
                            "the adapter exited well having never said what became of the turn")

    def test_a_server_that_simply_stopped_is_said_rather_than_reported_as_success(self):
        """**The likeliest crash of all**, and the one an earlier guard missed: the child exits or
        is killed before it completes a turn. Its pipe closes, which is not an exception — so a
        guard written only around the exceptions never fired, and rundesk was handed an adapter
        that exited cleanly having said nothing at all. That is the failure that looks most like a
        success, and this contract refuses it.
        """
        said, got = replayed(self.home, THEN_DIE="1",
                             captured=FAILURES / "a-server-that-just-stopped.jsonl")
        self.assertTrue(said, "the adapter exited having said nothing at all")
        self.assertEqual("done", said[-1]["type"])
        self.assertEqual("crashed", said[-1]["failure_code"])
        self.assertNotEqual(0, got.returncode)

    def test_a_record_with_no_terminator_after_it_is_not_treated_as_whole(self):
        """**Nothing can tell a complete record missing its newline from a truncated one that still
        parses.** So neither is handed on — the cost is losing a record that happened to be intact,
        and the alternative is reading half of one as though it were all of it, which nothing
        downstream could tell from the server talking nonsense.

        The record dropped here is the one that would have said the turn completed, so the turn
        comes back `crashed` rather than as a success nobody actually saw.
        """
        said, _got = replayed(self.home, THEN_DIE="1",
                              captured=FAILURES / "a-record-with-no-terminator.jsonl")
        self.assertEqual("done", said[-1]["type"])
        self.assertFalse(said[-1]["ok"],
                         "a line with no terminator after it was read as a whole record")

    def test_a_line_too_long_to_hold_is_dropped_whole_and_the_turn_carries_on(self):
        """**Half a record is not a smaller record, it is a corrupt one**, and the bound has to be
        inside the read: a check on how long a line is, made after the whole of it is held, is not
        a bound at all."""
        at = self.home / "a-line-that-does-not-fit.jsonl"
        at.write_text("\n".join([
            json.dumps({"id": 1, "result": {}}),
            json.dumps({"id": 2, "result": {"thread": {"id": "t-1"}}}),
            json.dumps({"id": 3, "result": {}}),
            # An answer too long to hold. Reported, it would be a `text` record; dropped whole, it
            # is not — which is the one observable difference between a bound and no bound.
            json.dumps({"method": "item/completed",
                        "params": {"threadId": "t-1", "turnId": "u-1",
                                   "item": {"type": "agentMessage", "id": "m",
                                            "text": "y" * (1024 * 1024 + 64)}}}),
            json.dumps({"method": "turn/completed",
                        "params": {"threadId": "t-1",
                                   "turn": {"id": "u-1", "status": "completed"}}}),
        ]) + "\n", encoding="utf-8")
        said, _got = replayed(self.home, captured=at)
        self.assertEqual([], [one for one in said if one.get("type") == "text"],
                         "a line past the bound was reported in pieces or held whole")
        self.assertEqual("done", said[-1]["type"])
        self.assertTrue(said[-1]["ok"], "a line nobody could hold ended a turn that was fine")


class TheVersionItWasWrittenAgainst(support.Isolated):
    """A fixture nobody can date is a fixture nobody can act on when it goes red."""

    def test_the_lock_names_the_version_the_capture_came_from(self):
        said = (support.CHECKOUT / "cli-versions.lock").read_text(encoding="utf-8")
        self.assertIn("codex-cli 0.146.0", said)
        self.assertIn(CAPTURED.name, said)
        self.assertIn(RESUMED.name, said)


if __name__ == "__main__":
    unittest.main()
