"""The grok adapter, against a stream a real grok once produced.

**No account, no token, no network.** `tests/samples/grok-acp-0.2.118.jsonl` is what `grok agent
stdio` said during one real turn on 2026-08-06, captured whole and scrubbed of anything naming a
machine or an owner; `tests/samples/an-acp-brain` says it again on demand. So every reading this
adapter makes is checked against the vendor rather than against a stand-in written to agree with it
— which is the one thing a hand-written fake cannot do — and the suite still never reaches a vendor,
which is both this repository's rule and a terms one.

**What the fixture is for is drift.** The day this vendor changes its stream, this file goes red
with the reading that broke, and `cli-versions.lock` says which version the fixture came from.
Without it the first sign would be an agent behaving oddly with nothing to compare against.

The adapter is run as the program it is, through the environment it is really given. Nothing here
imports it — it has no importable shape, deliberately, and a case that reached inside it would be
proving something the seam does not promise.

Run directly: `python3 tests/test_providers_grok.py`
"""

import json
import subprocess
import unittest

import support

#: The adapter under test, and the two files that let it run with no vendor on the machine.
ADAPTER = support.CHECKOUT / "src" / "providers" / "grok"
CAPTURED = support.CHECKOUT / "tests" / "samples" / "grok-acp-0.2.118.jsonl"
A_BRAIN = support.CHECKOUT / "tests" / "samples" / "an-acp-brain"

#: A second turn, on a conversation that had already cost 12,472 tokens when it began. **The first
#: capture cannot prove what a resumed turn does** — carrying a conversation on replays every update
#: the previous turn made, including its reply and the line that ended it, and a fixture that never
#: resumed has none of that in it.
RESUMED = support.CHECKOUT / "tests" / "samples" / "grok-acp-0.2.118-resumed.jsonl"

#: The conversation `RESUMED` was captured on. Asking for it is what makes the adapter load rather
#: than open, which is the whole point of that capture.
CARRIED_ON = "019fd7fe-abad-72d1-9812-b49c1c7020ec"

#: How long the adapter may take to translate a capture. It does no waiting of its own here, so this
#: is a ceiling on something that finishes in hundredths and never a duration anything relies on.
PATIENCE = 60.0

#: A `PATH` with no vendor on it **and an interpreter still on it**. Pointing it at nothing at all
#: does not test a missing brain — it tests a missing `python3`, because that is what this adapter's
#: own first line goes looking for, so the program under test never starts and the case passes for
#: the wrong reason. This is the shape of a machine where the CLI was simply never installed.
NO_VENDOR = "/usr/bin:/bin"


def replayed(home, prompt="Read note.txt and tell me the number in it.", captured=CAPTURED,
             steering=None, **also):
    """Run the adapter against the capture and hand back every record it made, in order."""
    where = home / "cwd"
    where.mkdir(parents=True, exist_ok=True)
    # A directory holding one program called `grok`, put on the front of `PATH`. The adapter looks
    # for its brain by name, exactly as it does on a real machine.
    instead = home / "bin"
    instead.mkdir(parents=True, exist_ok=True)
    (instead / "grok").write_bytes(A_BRAIN.read_bytes())
    (instead / "grok").chmod(0o755)

    told = {"PATH": f"{instead}:/usr/bin:/bin", "CAPTURED": str(captured),
            "RUNDESK_CWD": str(where), "RUNDESK_ACCESS_MODE": "work",
            "RUNDESK_AGENT": "cole", "RUNDESK_RUN": "1",
            "RUNDESK_CONTINUITY": "AGENTS.md=rules,MEMORY.md=memory"}
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


def a_conversation(*between, prompt_answered=True):
    """A made-up stream in the shape a real one has: a handshake, then a turn.

    **The reply to the prompt is what ends a turn that said nothing else**, so a stream without one
    is a brain that answered and then went silent — which rundesk's own window is what answers, not
    the adapter's, so a suite built on one waits for ever rather than failing. Every case that wants
    a turn to *end* needs this shape; the one case that wants a brain to vanish mid-turn asks for it
    by name.
    """
    lines = [
        json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": 1}}),
        json.dumps({"jsonrpc": "2.0", "id": 2, "result": {"sessionId": "s-1"}}),
        *between,
    ]
    if prompt_answered:
        lines.append(json.dumps({"jsonrpc": "2.0", "id": 3,
                                 "result": {"stopReason": "end_turn"}}))
    return lines


def an_update(**update):
    """One notification carrying one session update, as this brain sends them."""
    return json.dumps({"jsonrpc": "2.0", "method": "session/update",
                       "params": {"sessionId": "s-1", "update": update}})


class Capabilities(support.Isolated):
    """Asked offline, with no account and no network, and the same answer every time."""

    def answered(self, path=NO_VENDOR):
        got = subprocess.run([str(ADAPTER), "--capabilities"], capture_output=True, text=True,
                             timeout=PATIENCE, env={"PATH": path}, check=False)
        return got, json.loads(got.stdout)

    def test_it_says_it_can_do_all_five(self):
        """`steer` among them. It was a no while nothing had been measured to take more words into a
        turn already running; a cancel and a fresh ask were then driven against a real account and
        the turn came back answering the later word."""
        _got, can = self.answered()
        self.assertEqual({"tools": True, "resume": True, "model": True, "usage": True,
                          "steer": True},
                         {k: v for k, v in can.items() if k in
                          ("tools", "resume", "model", "usage", "steer")})

    def test_it_answers_with_no_vendor_on_the_machine_at_all(self):
        """A version it could not read does not change what the adapter can do, so the answer still
        arrives and simply does not carry one."""
        got, can = self.answered(path=NO_VENDOR)
        self.assertEqual(0, got.returncode)
        self.assertTrue(can["tools"])
        self.assertNotIn("grok_cli", can)


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

    def test_the_done_carries_the_handle_to_carry_it_on_with(self):
        self.assertEqual(CARRIED_ON, self.said[-1]["session_id"])

    def test_a_tool_and_its_result_are_paired_by_the_brains_own_id(self):
        tool, result = only(self.said, "tool")[0], only(self.said, "result")[0]
        self.assertEqual(tool["id"], result["id"])
        self.assertTrue(result["ok"])

    def test_a_tool_is_named_by_its_machine_name_and_not_by_what_a_person_reads(self):
        """**The two are different words on this brain.** A call starts as `read_file` and is
        updated to ``Read `note.txt` ``, so a table keyed on the readable one stops matching the
        moment the vendor makes its titles friendlier."""
        self.assertEqual("read_file", only(self.said, "tool")[0]["name"])
        self.assertEqual("read", only(self.said, "tool")[0]["did"])

    def test_reasoning_arrives_as_finished_thoughts_and_never_one_record_per_token(self):
        """This brain reasons a token at a time and nothing restates it. A record each would write a
        row per token into the turn's records; the first fragment alone — which is what the build
        this replaces reported — turns a paragraph of reasoning into the word `The`."""
        thoughts = only(self.said, "think")
        self.assertEqual(2, len(thoughts), "one record per run of reasoning, not per fragment")
        for one in thoughts:
            self.assertTrue(one["whole"])
            self.assertGreater(len(one["text"]), 20, "a thought was cut down to its first fragment")
        self.assertIn("note.txt", thoughts[0]["text"])

    def test_a_run_of_reasoning_is_ended_by_going_to_work(self):
        """Reasoning either side of a tool call is two thoughts, not one — the brain stopped
        thinking in order to do something, which is where one thought ends and the next begins."""
        order = [one["type"] for one in self.said if one["type"] in ("think", "tool")]
        self.assertEqual(["think", "tool", "think"], order[:3])

    def test_what_the_agent_said_arrives_as_fragments_because_nothing_restates_it(self):
        """The opposite decision from `think`, and for the opposite reason: `text` is the one kind
        rundesk gathers into a message rather than keeping as rows, so fragments cost nothing and
        letting a surface stream them is worth having."""
        spoken = only(self.said, "text")
        self.assertTrue(spoken, "the brain's reply never arrived")
        for one in spoken:
            self.assertNotIn("whole", one)
        self.assertIn("41", "".join(one["text"] for one in spoken))

    def test_the_fresh_input_has_the_cached_reads_taken_out_of_it(self):
        """**The measured reading, and the one that costs money if it is wrong.** This brain's
        `inputTokens` already contains its cached reads — this turn reported 12,472 for 6,328 fresh
        against 6,144 cached — so passing it through as sent bills the cache twice at the standard
        rate."""
        counted = only(self.said, "usage")[0]
        self.assertEqual(6144, counted["cache_read_tokens"])
        self.assertEqual(6328, counted["input_tokens"])
        self.assertEqual(63, counted["output_tokens"])

    def test_how_big_the_conversation_ended_is_a_level_and_not_one_of_the_costs(self):
        counted = only(self.said, "usage")[0]
        self.assertEqual(6393, counted["context_tokens"])
        self.assertNotEqual(counted["context_tokens"],
                            counted["input_tokens"] + counted["cache_read_tokens"])

    def test_the_model_that_actually_answered_is_named(self):
        self.assertEqual("grok-4.5-build", only(self.said, "usage")[0]["model_name"])

    def test_nothing_this_brain_cannot_report_is_reported(self):
        """It gives no allowance and names nothing it made, so saying either would be inventing."""
        self.assertEqual([], only(self.said, "limit"))
        self.assertEqual([], only(self.said, "file"))

    def test_somewhere_it_cannot_keep_the_raw_stream_does_not_cost_the_turn(self):
        """**Offered, never required** — and that has to be true of the failure as well as of the
        absence. Opened bare, this raised out of the one place a turn has nothing to say for itself:
        the brain is already started and the guard that promises a `done` has not been entered, so
        there were no records at all, a traceback, and a vendor process left behind.
        """
        said, got = replayed(self.home, RUNDESK_RAW=str(self.home / "not-a-dir" / "raw.jsonl"))
        self.assertEqual(1, len(only(said, "done")))
        self.assertTrue(said[-1]["ok"], "a turn failed over a copy nobody needed")
        self.assertEqual(0, got.returncode)
        self.assertIn("could not be kept", got.stderr)

    def test_what_the_brain_itself_printed_is_kept_verbatim_when_somewhere_was_offered(self):
        """Rundesk sees what the *adapter* reported and never what the brain said, so without this a
        vendor changing its stream shows up as records quietly going missing."""
        at = self.home / "raw.jsonl"
        said, _got = replayed(self.home, RUNDESK_RAW=str(at))
        kept = at.read_text(encoding="utf-8").splitlines()
        self.assertGreater(len(kept), len(said), "the raw stream held less than the adapter said")
        self.assertTrue(any("turn_completed" in one for one in kept))


class ATurnOnAConversationThatWasCarriedOn(support.Isolated):
    """The capture that begins from nothing cannot prove any of this."""

    def setUp(self):
        super().setUp()
        self.said, self.got = replayed(self.home, prompt="What number did you just tell me?",
                                       captured=RESUMED, RUNDESK_RESUME=CARRIED_ON)

    def test_it_ends_once_and_carries_the_conversation_it_was_given(self):
        self.assertEqual(1, len(only(self.said, "done")))
        self.assertTrue(self.said[-1]["ok"])
        self.assertEqual(CARRIED_ON, self.said[-1]["session_id"])

    def test_the_previous_turn_is_not_said_again(self):
        """**Carrying a conversation on replays it.** The capture holds two `turn_completed` lines —
        the one the load replayed and the one this turn earned — so an adapter that reported what
        arrived before its own prompt would say the last answer again and mark the turn finished
        before it had asked anything."""
        self.assertEqual(2, sum(1 for line in RESUMED.read_text(encoding="utf-8").splitlines()
                                if "turn_completed" in line),
                         "this fixture is only worth having while it replays a previous turn")
        self.assertEqual(1, len(only(self.said, "usage")), "the replayed turn's cost was reported")

    def test_only_this_turns_share_is_reported(self):
        """This brain reports a resumed turn's own cost rather than the conversation's running
        total — 6,502 where turn one had reported 12,472 — so nothing is subtracted here."""
        counted = only(self.said, "usage")[0]
        self.assertEqual(6374, counted["input_tokens"])
        self.assertEqual(128, counted["cache_read_tokens"])
        self.assertEqual(29, counted["output_tokens"])


class WhatItAsksTheBrainFor(support.Isolated):
    """What goes *out* is half the contract, and the capture cannot check it. This can."""

    def spoke(self, then=(), **also):
        """Every request the adapter sent, read off a brain that writes down what it was told.

        `then` is what rundesk says *after* the prompt — the words a steer is made of. Named rather
        than swept up with the environment, because everything else here becomes a variable the
        adapter is started with and a list is not one.
        """
        where = self.home / "cwd"
        where.mkdir(parents=True, exist_ok=True)
        instead = self.home / "bin"
        instead.mkdir(parents=True, exist_ok=True)
        heard = self.home / "heard.jsonl"
        (instead / "grok").write_text('''#!/usr/bin/env python3
import json, os, sys
with open(os.environ["HEARD"], "a") as writing:
    writing.write(json.dumps({"argv": sys.argv[1:]}) + "\\n")
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
        print(json.dumps({"jsonrpc": "2.0", "id": said["id"], "result": {
            "protocolVersion": 1,
            "authMethods": [{"id": "cached_token"}],
            "_meta": {"defaultAuthMethodId": "cached_token"}}}), flush=True)
    elif said.get("method") == "authenticate":
        print(json.dumps({"jsonrpc": "2.0", "id": said["id"], "result": {}}), flush=True)
    elif said.get("method") in ("session/new", "session/load"):
        print(json.dumps({"jsonrpc": "2.0", "id": said["id"],
                          "result": {"sessionId": "s-1"}}), flush=True)
    elif said.get("method") == "session/prompt":
        print(json.dumps({"jsonrpc": "2.0", "method": "_x.ai/session_notification",
                          "params": {"sessionId": "s-1", "update": {
                              "sessionUpdate": "turn_completed", "stop_reason": "end_turn",
                              "usage": {"inputTokens": 10, "outputTokens": 2}}}}), flush=True)
        print(json.dumps({"jsonrpc": "2.0", "id": said["id"],
                          "result": {"stopReason": "end_turn"}}), flush=True)
''', encoding="utf-8")
        (instead / "grok").chmod(0o755)
        heard.write_text("", encoding="utf-8")
        told = {"PATH": f"{instead}:/usr/bin:/bin", "HEARD": str(heard),
                "RUNDESK_CWD": str(where), "RUNDESK_ACCESS_MODE": "work",
                "RUNDESK_AGENT": "cole", "RUNDESK_RUN": "1"}
        told.update(also)
        subprocess.run([str(ADAPTER)],
                       input="".join(json.dumps(one) + "\n" for one in
                                     [{"type": "say", "text": "hello"}, *then]),
                       capture_output=True, text=True, timeout=PATIENCE, env=told, check=False)
        return [json.loads(one) for one in heard.read_text(encoding="utf-8").splitlines()
                if one.strip()]

    def sent(self, method):
        return [one for one in self.spoken if one.get("method") == method]

    def argv(self):
        return next(one for one in self.spoken if "argv" in one)["argv"]

    def setUp(self):
        super().setUp()
        self.spoken = None

    def test_it_asks_for_the_transport_the_vendor_documents(self):
        self.spoken = self.spoke()
        self.assertEqual(["agent", "--always-approve", "stdio"], self.argv()[-3:])

    def test_one_conversation_never_answers_out_of_another(self):
        """**`--no-memory` is not a preference.** Without it this brain answers from conversations
        it was never handed, which makes a resume handle meaningless and lets one agent's turn read
        another's."""
        self.spoken = self.spoke()
        self.assertIn("--no-memory", self.argv())

    def test_a_headless_turn_is_not_left_waiting_for_somebody_to_approve_a_tool(self):
        """Three permission flags on this command line do nothing at all; this is the one that
        applies. Without it a turn reaching any tool ends as cancelled with exit 0."""
        self.spoken = self.spoke()
        self.assertEqual("bypassPermissions",
                         self.argv()[self.argv().index("--permission-mode") + 1])

    def test_every_turn_gets_the_whole_tool_set(self):
        """The owner's decision. A conversation opened as no agent of ours gets every built-in, so
        what must *not* be sent is a profile scoping it."""
        self.spoken = self.spoke()
        opened = self.sent("session/new")[0]["params"]
        self.assertNotIn("agentProfile", opened.get("_meta") or {})

    def test_a_narrower_access_mode_does_not_quietly_narrow_the_turn(self):
        """**The teeth on the decision above.** `RUNDESK_ACCESS_MODE` is a word the seam carries and
        this adapter deliberately ignores, so the case that matters is the one where it is set to
        the narrow value."""
        self.spoken = self.spoke(RUNDESK_ACCESS_MODE="read")
        opened = self.sent("session/new")[0]["params"]
        self.assertNotIn("agentProfile", opened.get("_meta") or {})
        for flag in ("--tools", "--allow", "--deny", "--sandbox"):
            self.assertNotIn(flag, self.argv(), f"{flag} reads as a boundary and enforces none")

    def test_a_word_arriving_mid_turn_stops_the_ask_before_replacing_it(self):
        """**A second ask does not steer this brain, it queues behind the first.** Measured against
        a real account: one sent mid-turn sat in the queue while the first ran, then ran as a turn
        of its own — two answers to what the owner meant as one changed instruction.

        So a later word cancels first. What this pins down is the order, which is the part that goes
        wrong silently: a replacement sent before the cancel lands behind the very ask it was meant
        to replace, and the turn answers the question the owner had already moved on from.
        """
        self.spoken = self.spoke(then=[{"type": "say", "text": "instead, say only: STEERED",
                                        "context": "mid-turn"}])
        order = [one.get("method") for one in self.spoken if one.get("method")]
        self.assertIn("session/cancel", order, "a later word was sent without stopping the turn")
        stopped = order.index("session/cancel")
        asks = [at for at, method in enumerate(order) if method == "session/prompt"]
        self.assertEqual(2, len(asks), "the replacement was never asked")
        self.assertLess(asks[0], stopped, "the turn was stopped before it had been asked anything")
        self.assertLess(stopped, asks[1], "the replacement queued behind the ask it replaced")

    def test_rundesks_own_words_are_carried_apart_from_the_persons(self):
        """A bare line appended to a running turn is refused by real brains as suspected prompt
        injection, so rundesk's context goes first and marked — and what the person said is
        unaltered beneath it."""
        self.spoken = self.spoke(then=[{"type": "say", "text": "stop",
                                        "context": "guidance from rundesk"}])
        asks = [one for one in self.spoken if one.get("method") == "session/prompt"]
        self.assertEqual("[rundesk] guidance from rundesk\n\nstop",
                         asks[-1]["params"]["prompt"][0]["text"])

    def test_the_client_offers_no_services_of_its_own(self):
        """Advertising a filesystem or a terminal makes this brain send the work back and wait for
        us to do it, which is a turn that never finishes."""
        self.spoken = self.spoke()
        self.assertEqual({}, self.sent("initialize")[0]["params"]["clientCapabilities"])

    def test_the_preface_is_added_to_the_brains_instructions_and_never_replaces_them(self):
        self.spoken = self.spoke(RUNDESK_PREFACE="stand up straight")
        self.assertEqual("stand up straight",
                         self.sent("session/new")[0]["params"]["_meta"]["rules"])

    def test_a_carried_on_conversation_carries_no_preface_because_it_already_has_one(self):
        """Standing instructions bind when a conversation is created, so re-sending them on a load
        would be words nobody reads."""
        self.spoken = self.spoke(RUNDESK_PREFACE="stand up straight", RUNDESK_RESUME="s-1")
        self.assertEqual([], self.sent("session/new"))
        loaded = self.sent("session/load")[0]["params"]
        self.assertNotIn("rules", loaded.get("_meta") or {})

    def test_the_model_asked_for_is_passed_on_and_an_unset_one_is_left_out(self):
        self.spoken = self.spoke(RUNDESK_MODEL="grok-4.5")
        self.assertEqual("grok-4.5", self.argv()[self.argv().index("-m") + 1])
        self.spoken = self.spoke()
        self.assertNotIn("-m", self.argv())

    def test_the_prompt_never_goes_on_the_command_line(self):
        """Every process on the machine can read one."""
        self.spoken = self.spoke()
        self.assertNotIn("hello", " ".join(self.argv()))

    def test_an_agents_skills_are_offered_where_this_brain_looks(self):
        skills = self.home / "skills"
        (skills / "a-skill").mkdir(parents=True)
        self.spoke(RUNDESK_SKILLS=str(skills))
        stood = self.home / "cwd" / ".grok" / "skills" / "a-skill"
        self.assertTrue(stood.is_symlink(), "a granted skill was not presented")
        self.assertTrue(stood.resolve().is_dir())

    def test_an_agent_granted_none_has_no_vendor_directory_to_explain(self):
        self.spoke(RUNDESK_SKILLS=str(self.home / "nothing-here"))
        self.assertFalse((self.home / "cwd" / ".grok").exists())


class WhenItCannotRunAtAll(support.Isolated):

    def test_a_brain_that_is_not_on_the_machine_is_said_as_a_done_and_never_as_silence(self):
        """**Rundesk reading no `done` at all is a turn nobody can explain**, so even the failure
        that happens before anything starts is said in the one shape rundesk can act on."""
        got = subprocess.run([str(ADAPTER)],
                             input=json.dumps({"type": "say", "text": "hello"}) + "\n",
                             capture_output=True, text=True,
                             timeout=PATIENCE, check=False,
                             env={"PATH": NO_VENDOR, "RUNDESK_CWD": str(self.home)})
        said = [json.loads(one) for one in got.stdout.splitlines() if one.strip()]
        self.assertEqual(1, len(said))
        self.assertEqual("done", said[0]["type"])
        self.assertFalse(said[0]["ok"])
        self.assertEqual("crashed", said[0]["failure_code"])
        self.assertNotEqual(0, got.returncode, "this side went wrong, so the program did too")


class AStreamThisSideCannotRead(support.Isolated):
    """What a turn does when the brain stops making sense, which is the shape most likely to be met
    in the wild and least likely to be captured."""

    def a_stream(self, lines, **also):
        at = self.home / "made-up.jsonl"
        at.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return replayed(self.home, captured=at, **also)

    def test_a_server_that_simply_stopped_is_said_rather_than_reported_as_success(self):
        """**Exiting zero having said nothing is the failure that looks most like a success.**"""
        said, got = self.a_stream(a_conversation(prompt_answered=False), THEN_DIE="1")
        self.assertEqual("done", said[-1]["type"])
        self.assertFalse(said[-1]["ok"])
        self.assertNotEqual(0, got.returncode)
        # **This is the path where two threads arrive at once.** A brain that dies mid-turn is seen
        # by the thread reading it and by the thread that asked at the same instant, and each used
        # to ask `have we finished?` for itself — so both could pass before either answered, and
        # rundesk was handed two endings for one turn. It would not have reproduced often.
        self.assertEqual(1, len(only(said, "done")), "one turn ended twice")

    def test_a_line_too_long_to_hold_is_dropped_whole_and_the_turn_carries_on(self):
        """**Half a record is not a smaller record, it is a corrupt one** — nothing downstream could
        tell that apart from the brain talking nonsense."""
        said, _got = self.a_stream(a_conversation(
            an_update(sessionUpdate="agent_message_chunk",
                      content={"type": "text", "text": "y" * (1024 * 1024 + 64)}),
            an_update(sessionUpdate="turn_completed", stop_reason="end_turn", usage={}),
        ))
        self.assertEqual([], only(said, "text"), "a line past the bound was reported")
        self.assertEqual("done", said[-1]["type"])
        self.assertTrue(said[-1]["ok"], "a line nobody could hold ended a turn that was fine")

    def test_a_line_that_will_not_parse_leaves_the_records_around_it_alone(self):
        said, _got = self.a_stream(a_conversation(
            "{not json at all",
            an_update(sessionUpdate="agent_message_chunk", content={"type": "text", "text": "41"}),
            an_update(sessionUpdate="turn_completed", stop_reason="end_turn", usage={}),
        ))
        self.assertEqual("41", "".join(one["text"] for one in only(said, "text")))
        self.assertTrue(said[-1]["ok"])


class EveryWayTheTurnCanEnd(support.Isolated):

    def ended_as(self, stopped):
        at = self.home / "ended.jsonl"
        at.write_text("\n".join(a_conversation(
            an_update(sessionUpdate="turn_completed", stop_reason=stopped, usage={}),
        )) + "\n", encoding="utf-8")
        said, got = replayed(self.home, captured=at)
        return said[-1], got

    def test_a_turn_that_finished_is_a_turn_that_worked(self):
        ended, got = self.ended_as("end_turn")
        self.assertTrue(ended["ok"])
        self.assertEqual(0, got.returncode)

    def test_a_turn_ends_exactly_once_however_it_ends(self):
        """Both the reply to the asking and the notification can end a turn, and either may arrive
        first. Whichever is second must add nothing."""
        for stopped in ("end_turn", "cancelled", "refusal"):
            with self.subTest(stopped=stopped):
                at = self.home / "ended.jsonl"
                at.write_text("\n".join(a_conversation(
                    an_update(sessionUpdate="turn_completed", stop_reason=stopped, usage={}),
                )) + "\n", encoding="utf-8")
                said, _got = replayed(self.home, captured=at)
                self.assertEqual(1, len(only(said, "done")), "one turn ended twice")
                self.assertLessEqual(len(only(said, "usage")), 1, "one turn was billed twice")

    def test_a_turn_somebody_stopped_is_cancelled_and_not_an_error(self):
        ended, _got = self.ended_as("cancelled")
        self.assertFalse(ended["ok"])
        self.assertEqual("cancelled", ended["failure_code"])

    def test_a_brain_that_declined_the_work_says_so_as_a_decision(self):
        ended, _got = self.ended_as("refusal")
        self.assertEqual("refused", ended["failure_code"])

    def test_a_way_of_stopping_this_release_never_heard_of_carries_no_word(self):
        """**A word guessed from a message is a word that is wrong on the first vendor that rewords
        one**, and a wrong word in a column nothing can audit is worse than an absent one."""
        ended, _got = self.ended_as("something_new")
        self.assertFalse(ended["ok"])
        self.assertNotIn("failure_code", ended)
        self.assertIn("something_new", ended["failure_message"])

    def test_the_program_still_did_its_job_when_the_brain_reported_a_failure(self):
        """The exit code says what became of the **program**, never what became of the turn."""
        _ended, got = self.ended_as("cancelled")
        self.assertEqual(0, got.returncode)


class WhenItIsSteeredMidTurn(support.Isolated):
    """A word that arrives while the brain is working, and what becomes of the ask it replaced.

    **Written rather than captured, and that is a real limit worth stating.** The other cases here
    replay a stream a real grok produced, which is what makes them evidence about the vendor rather
    than about a fixture. This one cannot: a steer is caused by a `session/cancel` that carries no
    request id, so the ordering a capture would have to be released in is not one the replay can
    reconstruct from the capture alone. What is proved here is the *mapping* — that a cancelled ask
    is not this turn's ending, and that what it cost is still billed. That the sequence works
    against the vendor was driven live against a real account, and the ask-order it produces is
    pinned by `test_a_word_arriving_mid_turn_stops_the_ask_before_replacing_it`.
    """

    #: A brain that behaves the way the real one was measured to: an ask runs until it is
    #: cancelled, a cancel settles it as `cancelled`, and a later ask is answered on its own.
    BRAIN = """#!/usr/bin/env python3
import json, sys

asks = []
for line in sys.stdin:
    try:
        said = json.loads(line)
    except ValueError:
        continue
    method, which = said.get("method"), said.get("id")
    def out(one):
        print(json.dumps(one), flush=True)
    def update(**u):
        out({"jsonrpc": "2.0", "method": "session/update",
             "params": {"sessionId": "s-1", "update": u, "_meta": {"totalTokens": 900}}})
    if method == "initialize":
        out({"jsonrpc": "2.0", "id": which, "result": {"protocolVersion": 1}})
    elif method == "session/new":
        out({"jsonrpc": "2.0", "id": which, "result": {"sessionId": "s-1"}})
    elif method == "session/prompt":
        asks.append(which)
        if len(asks) == 1:
            update(sessionUpdate="agent_message_chunk",
                   content={"type": "text", "text": "counting"})
        else:
            update(sessionUpdate="agent_message_chunk",
                   content={"type": "text", "text": "STEERED"})
            update(sessionUpdate="turn_completed", stop_reason="end_turn",
                   usage={"inputTokens": 40, "outputTokens": 6})
            out({"jsonrpc": "2.0", "id": which, "result": {"stopReason": "end_turn"}})
    elif method == "session/cancel":
        update(sessionUpdate="turn_completed", stop_reason="cancelled",
               usage={"inputTokens": 100, "outputTokens": 20})
        out({"jsonrpc": "2.0", "id": asks[0], "result": {"stopReason": "cancelled"}})
"""

    def setUp(self):
        super().setUp()
        where = self.home / "cwd"
        where.mkdir(parents=True, exist_ok=True)
        instead = self.home / "bin"
        instead.mkdir(parents=True, exist_ok=True)
        (instead / "grok").write_text(self.BRAIN, encoding="utf-8")
        (instead / "grok").chmod(0o755)
        self.got = subprocess.run(
            [str(ADAPTER)],
            input="".join(json.dumps(one) + "\n" for one in (
                {"type": "say", "text": "count to thirty"},
                {"type": "say", "text": "stop, say STEERED", "context": "mid-turn"})),
            capture_output=True, text=True, timeout=PATIENCE, check=False,
            env={"PATH": f"{instead}:/usr/bin:/bin", "RUNDESK_CWD": str(where),
                 "RUNDESK_AGENT": "cole", "RUNDESK_RUN": "1"})
        self.said = [json.loads(one) for one in self.got.stdout.splitlines() if one.strip()]

    def test_the_word_that_arrived_mid_turn_reached_the_brain_inside_the_same_turn(self):
        self.assertIn("STEERED", "".join(one["text"] for one in only(self.said, "text")))

    def test_it_is_still_one_turn_and_one_ending(self):
        """**A cancelled ask settles like any other.** Reporting it would end the turn before the
        replacement had been asked, and the owner would be told their agent was cancelled."""
        self.assertEqual(1, len(only(self.said, "done")), "one turn ended more than once")
        self.assertTrue(self.said[-1]["ok"])

    def test_a_stopped_ask_is_not_reported_as_a_turn_that_failed(self):
        self.assertNotIn("failure_code", self.said[-1])
        self.assertEqual(0, self.got.returncode)

    def test_what_the_stopped_ask_cost_is_still_billed(self):
        """20 output tokens were spent before the cancel and 6 after it. Dropping the first would
        under-report every steered turn, and the owner was charged for both."""
        counted = only(self.said, "usage")
        self.assertEqual(1, len(counted), "one turn was billed twice")
        self.assertEqual(26, counted[0]["output_tokens"])
        self.assertEqual(140, counted[0]["input_tokens"])


class TheVersionItWasWrittenAgainst(support.Isolated):
    """A capture with no version beside it is a fixture nobody can act on."""

    def test_the_lock_names_the_version_every_capture_came_from(self):
        lock = (support.CHECKOUT / "cli-versions.lock").read_text(encoding="utf-8")
        self.assertIn("grok 0.2.118", lock)
        for one in (CAPTURED, RESUMED):
            self.assertIn(one.name, lock, f"{one.name} is not named in cli-versions.lock")


if __name__ == "__main__":
    unittest.main()
