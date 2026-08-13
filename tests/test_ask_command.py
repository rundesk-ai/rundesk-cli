"""`rundesk ask` — a person typing, and what that person is shown while a turn runs.

Driven through `self.rundesk(...)`, so the real parser and the real dispatch answer every case. A
case that called `cmd_ask` directly would prove the module and not the command: the flag it spelled,
the exit code the shell reads, and the words on the screen are exactly the parts a direct call skips.

**This is the attended way in.** A gateway answers a channel and the clock starts a schedule; this is
somebody at a keyboard, and it is the only caller with anybody to take a mid-turn word from. So what
is proved here is mostly about the person: that the answer arrives, that a failure says whether
waiting will help, that a vendor's vocabulary never reaches the screen, and that asking again carries
the same exchange on rather than starting a new one.

Run directly: `python3 tests/test_ask_command.py`
"""

import json
import os
import threading
import unittest
from contextlib import contextmanager
from unittest import mock

import support
from rundesk.agents import delegating, directory, records
from rundesk.channels import arriving
from rundesk.delegations import admitting
from rundesk.delegations import kept as delegations
from rundesk.exits import FAILED, OK, USAGE
from rundesk.gateways import standing
from rundesk.providers import accounts, adapters, kept
from rundesk.utils import locking


class Asking(support.Isolated):

    def setUp(self):
        super().setUp()
        self.agent = "cole"
        directory.made(self.agent, support.A_STAND_IN)

    def asked(self, *more):
        return self.rundesk("ask", self.agent, "what changed today?", *more)


class OneQuestionAndItsAnswer(Asking):

    def test_the_answer_is_printed_and_the_shell_reads_success(self):
        code, out, err = self.asked()
        self.assertEqual(OK, code, err)
        self.assertIn("what changed today?", out)

    def test_what_it_cost_and_which_turn_it_was_are_said_underneath(self):
        """Somebody who has just spent money on a question is told what it cost, and given the one
        thing that leads to everything else about that run."""
        code, out, _err = self.asked()
        self.assertEqual(OK, code)
        self.assertIn("turn 1", out)
        self.assertIn("in", out)

    def test_quiet_prints_the_answer_and_nothing_around_it(self):
        """For a pipe. A cost line in the middle of somebody's data is the thing that makes a
        command unusable from a script."""
        code, out, _err = self.asked("--quiet")
        self.assertEqual(OK, code)
        self.assertNotIn("turn 1", out)
        self.assertIn("what changed today?", out)

    def test_the_question_and_the_answer_are_both_written_down(self):
        self.asked()
        conversation = kept.get_turn(self.agent, 1)["conversation_id"]
        said = arriving.messages(self.agent, conversation)
        self.assertEqual([arriving.BY_USER, arriving.BY_AGENT],
                         [one["author"] for one in said][:2])

    def test_the_answer_carries_the_turn_that_said_it(self):
        """The one join between what was said and what it cost. Without it nobody can get from a
        sentence in the history to the run that produced it."""
        self.asked()
        conversation = kept.get_turn(self.agent, 1)["conversation_id"]
        said = [one for one in arriving.messages(self.agent, conversation)
                if one["author"] == arriving.BY_AGENT]
        self.assertEqual(1, said[0]["turn_id"])


class WhatItShowsWhileItWorks(Asking):

    def test_a_tool_is_named_by_what_it_did_and_never_by_the_brains_word_for_it(self):
        """The same act is `Bash` on one brain, `shell` on the next and `run_terminal_command` on a
        third. A surface that printed any of them would carry that vendor's vocabulary for ever."""
        code, out, _err = self.asked()
        self.assertEqual(OK, code)
        self.assertIn("read", out)

    def test_what_it_is_thinking_is_off_by_default_and_on_when_asked(self):
        """Reasoning is long, and a terminal that printed all of it would bury the answer."""
        _code, quiet, _err = self.asked()
        _code, loud, _err = self.rundesk("ask", self.agent, "what changed today?", "--fresh",
                                         "--thinking")
        self.assertLess(len(quiet), len(loud))

    def test_account_news_is_shown_apart_from_the_work(self):
        """**Not this turn's activity and not an outcome**: a turn carrying one may have succeeded."""
        code, out, _err = self.asked()
        self.assertEqual(OK, code)
        self.assertIn("allowance", out)


class WhenItCouldNotAnswer(Asking):

    def test_it_exits_non_zero_and_says_what_the_brain_said(self):
        self.a_stand_in_told(self.agent, fail_with="rate_limited")
        code, _out, err = self.asked()
        self.assertEqual(FAILED, code)
        self.assertIn("the stand-in was told to fail", err)

    def test_it_says_whether_waiting_will_help(self):
        self.a_stand_in_told(self.agent, fail_with="rate_limited")
        _code, _out, err = self.asked()
        self.assertIn("later may work", err)

    def test_it_says_when_waiting_will_not_help(self):
        self.a_stand_in_told(self.agent, fail_with="signed_out")
        _code, _out, err = self.asked()
        self.assertIn("will not clear on its own", err)

    def test_it_says_where_to_read_what_the_turn_did(self):
        self.a_stand_in_told(self.agent, fail_with="upstream_error")
        _code, _out, err = self.asked()
        self.assertIn(f"rundesk turns {self.agent} 1", err)

    def test_a_turn_that_ended_with_nothing_said_is_not_a_turn_that_worked(self):
        """Exit zero having said nothing is the failure that looks most like a success."""
        self.a_stand_in_told(self.agent, say_nothing_and_finish=True)
        code, _out, err = self.asked()
        self.assertEqual(FAILED, code)
        self.assertIn("did not answer", err)

    def test_an_adapter_that_will_not_start_says_so_before_anything_is_written(self):
        records.stated(directory.records(self.agent), {"provider_name": "nothing-stands-here"})
        code, _out, err = self.asked()
        self.assertEqual(FAILED, code)
        self.assertIn("looked in", err)
        self.assertEqual([], kept.list_turns(self.agent))


class OneConversationPerAgent(Asking):

    def test_asking_again_carries_the_same_exchange_on(self):
        """Which is what a person means by asking again."""
        self.asked()
        self.rundesk("ask", self.agent, "and now?")
        first, second = (kept.get_turn(self.agent, one)["conversation_id"] for one in (1, 2))
        self.assertEqual(first, second)

    def test_fresh_starts_a_new_one_on_the_brain_and_keeps_the_same_history(self):
        """**Two different things.** The exchange a person reads back is rundesk's; what the brain
        remembers is the brain's, and `--fresh` drops only the second."""
        self.asked()
        self.rundesk("ask", self.agent, "and now?", "--fresh")
        first, second = (kept.get_turn(self.agent, one) for one in (1, 2))
        self.assertEqual(first["conversation_id"], second["conversation_id"])
        self.assertEqual(0, second["session_resumed"])

    def test_a_second_turn_in_a_busy_conversation_is_refused_rather_than_queued(self):
        """The claim is the kernel's, so this competes correctly with a gateway answering the same
        agent on a channel, with no coordination between the two."""
        from rundesk.providers import turns
        landed = arriving.asked_at_a_terminal(self.agent, "the first")
        with turns.claiming(self.agent, landed.conversation):
            code, _out, err = self.asked()
        self.assertEqual(FAILED, code)
        self.assertIn(f"rundesk turns {self.agent}", err)


class WhenTheCommandLineIsWrong(Asking):

    def test_an_agent_that_is_not_there_says_what_to_type(self):
        code, _out, err = self.rundesk("ask", "nobody", "hello")
        self.assertEqual(FAILED, code)
        self.assertIn("rundesk agents", err)

    def test_asking_nothing_at_all_is_the_command_line_being_wrong(self):
        code, _out, _err = self.rundesk("ask", self.agent)
        self.assertEqual(USAGE, code)

    def test_a_prompt_of_only_spaces_is_refused_rather_than_sent(self):
        code, _out, err = self.rundesk("ask", self.agent, "   ")
        self.assertEqual(FAILED, code)
        self.assertIn("nothing to ask", err)

    def test_a_person_cannot_apply_a_delegation_provider_to_an_ordinary_turn(self):
        code, _out, err = self.asked("--provider", "codex")
        self.assertEqual(FAILED, code)
        self.assertIn("scoped to work one agent delegates", err)
        self.assertEqual([], kept.list_turns(self.agent))


class WhenOneAgentAsksAnother(support.Isolated):
    """The configured scope is enforced at admission, not merely hidden from the prompt."""

    def setUp(self):
        super().setUp()
        for agent in ("ava", "forge", "trace"):
            directory.made(agent, support.A_STAND_IN)
        parent = arriving.asked_at_a_terminal("ava", "delegate the bounded work")
        with records.writing(directory.records("ava")) as conn:
            conn.execute(
                "INSERT INTO turns (conversation_id, provider_name, access_mode, turn_status,"
                " created_at) VALUES (?, ?, ?, ?, ?)",
                (parent.conversation, support.A_STAND_IN, "work", "working",
                 "2026-08-10T00:00:00Z"))
            self.turn = int(conn.execute("SELECT id FROM turns").fetchone()[0])

    def ask_from_ava(self, target, *more):
        with mock.patch.dict(os.environ, {admitting.AGENT: "ava",
                                          admitting.RUN: str(self.turn)}), \
                standing.holding(directory.where(target)):
            return self.rundesk("ask", target, "audit the exporter", *more)

    def test_an_allowed_target_is_admitted(self):
        records.stated(directory.records("ava"),
                       {"delegates_to": json.dumps(["forge"])})

        code, out, err = self.ask_from_ava("forge")

        self.assertEqual(OK, code, err)
        self.assertIn("handed to forge", out)
        self.assertEqual(["forge"], [one.to_agent for one in delegations.every("ava")])

    def test_a_scoped_provider_and_model_are_admitted_without_changing_the_target(self):
        before = records.read(directory.records("forge"))

        code, out, err = self.ask_from_ava(
            "forge", "--provider", "codex", "--model", "gpt-scoped")

        self.assertEqual(OK, code, err)
        self.assertIn("handed to forge", out)
        one = delegations.every("ava")[0]
        self.assertEqual(("codex", "gpt-scoped", "codex", "gpt-scoped"),
                         (one.requested_provider_name, one.requested_model_name,
                          one.provider_name, one.model_name))
        self.assertEqual(before, records.read(directory.records("forge")))

    def test_a_scoped_alias_is_immutable_provenance_without_changing_the_target_default(self):
        account = accounts.registered(support.A_STAND_IN, "work")
        before = records.read(directory.records("forge"))

        with mock.patch.object(
                adapters, "capabilities", return_value={"account_aliases": True}):
            code, out, err = self.ask_from_ava(
                "forge", "--provider", support.A_STAND_IN, "--alias", "work")

        self.assertEqual(OK, code, err)
        self.assertIn("handed to forge", out)
        one = delegations.every("ava")[0]
        self.assertEqual(
            ("work", "work"),
            (one.requested_provider_alias, one.provider_alias))
        self.assertEqual(account.home, accounts.account_home(one.provider_name, one.provider_alias))
        self.assertEqual(before, records.read(directory.records("forge")))

    def test_a_missing_explicit_alias_is_refused_before_either_delegation_write(self):
        with mock.patch.object(
                adapters, "capabilities", return_value={"account_aliases": True}), \
                mock.patch("rundesk.commands.ask.arriving.recorded_for_a_delegation") as recorded:
            code, _out, err = self.ask_from_ava(
                "forge", "--provider", support.A_STAND_IN, "--alias", "missing")
        self.assertEqual(FAILED, code)
        self.assertIn("not a registered alias", err)
        recorded.assert_not_called()
        self.assertEqual([], delegations.every("ava"))

    def test_model_only_captures_the_target_provider_and_requested_model(self):
        before = records.read(directory.records("forge"))

        code, _out, err = self.ask_from_ava("forge", "--model", "gpt-scoped")

        self.assertEqual(OK, code, err)
        one = delegations.every("ava")[0]
        self.assertEqual((None, "gpt-scoped", support.A_STAND_IN, "gpt-scoped"),
                         (one.requested_provider_name, one.requested_model_name,
                          one.provider_name, one.model_name))
        self.assertEqual(before, records.read(directory.records("forge")))

    def test_provider_only_uses_that_providers_default_model(self):
        records.stated(directory.records("forge"), {"model_name": "configured-model"})
        before = records.read(directory.records("forge"))

        code, _out, err = self.ask_from_ava("forge", "--provider", "codex")

        self.assertEqual(OK, code, err)
        one = delegations.every("ava")[0]
        self.assertEqual(("codex", None, "codex", None),
                         (one.requested_provider_name, one.requested_model_name,
                          one.provider_name, one.model_name))
        self.assertEqual(before, records.read(directory.records("forge")))

    def test_an_unavailable_override_is_refused_before_either_write(self):
        before = records.read(directory.records("forge"))
        with mock.patch("rundesk.commands.ask.arriving.recorded_for_a_delegation") as recorded:
            code, out, err = self.ask_from_ava(
                "forge", "--provider", "nothing-stands-here")

        self.assertEqual(FAILED, code)
        self.assertEqual("", out)
        self.assertIn("nothing-stands-here", err)
        recorded.assert_not_called()
        self.assertEqual([], delegations.every("ava"))
        self.assertEqual(before, records.read(directory.records("forge")))

    def test_no_override_captures_the_target_defaults_at_admission(self):
        records.stated(directory.records("forge"), {"model_name": "configured-model"})
        self.assertEqual(OK, self.ask_from_ava("forge")[0])
        one = delegations.every("ava")[0]
        self.assertEqual((None, None, support.A_STAND_IN, "configured-model"),
                         (one.requested_provider_name, one.requested_model_name,
                          one.provider_name, one.model_name))

    def test_relative_requested_provider_spelling_is_distinct_from_effective_path(self):
        provider = self.home / "relative-provider"
        provider.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        provider.chmod(0o755)
        here = os.getcwd()
        os.chdir(str(self.home))
        self.addCleanup(os.chdir, here)

        code, _out, err = self.ask_from_ava(
            "forge", "--provider", "./relative-provider")

        self.assertEqual(OK, code, err)
        one = delegations.every("ava")[0]
        self.assertEqual("./relative-provider", one.requested_provider_name)
        self.assertEqual(str(provider.resolve()), one.provider_name)

    def test_relative_alias_configuration_admission_and_removal_share_canonical_identity(self):
        provider = self.home / "relative-provider"
        provider.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        provider.chmod(0o755)
        here = os.getcwd()
        os.chdir(str(self.home))
        self.addCleanup(os.chdir, here)
        account = accounts.registered(str(provider.resolve()), "work")

        with mock.patch.object(
                adapters, "capabilities", return_value={"account_aliases": True}):
            code, _out, err = self.rundesk(
                "agents", "configure", "forge", "--provider", "./relative-provider",
                "--alias", "work")
            self.assertEqual(OK, code, err)
            self.assertEqual(
                (str(provider.resolve()), "work"),
                (records.read(directory.records("forge"))["provider_name"],
                 records.read(directory.records("forge"))["provider_alias"]))

            code, _out, err = self.rundesk(
                "providers", "aliases", "remove", str(provider.resolve()), "work", "--confirm")
            self.assertEqual(FAILED, code)
            self.assertIn("configured default", err)

            code, _out, err = self.ask_from_ava("forge")
            self.assertEqual(OK, code, err)
            one = delegations.every("ava")[0]
            self.assertEqual((None, None),
                             (one.requested_provider_name, one.requested_provider_alias))
            self.assertEqual((str(provider.resolve()), "work"),
                             (one.provider_name, one.provider_alias))
            self.assertEqual(account.home, accounts.account_home(
                one.provider_name, one.provider_alias))

            records.stated(directory.records("forge"), {
                "provider_name": support.A_STAND_IN, "provider_alias": None})
            code, _out, err = self.rundesk(
                "providers", "aliases", "remove", "./relative-provider", "work", "--confirm")
        self.assertEqual(FAILED, code)
        self.assertIn(one.delegation_id, err)
        self.assertTrue(account.home.exists())

    def test_an_unlisted_target_is_refused_before_either_delegation_write(self):
        records.stated(directory.records("ava"),
                       {"delegates_to": json.dumps(["forge"])})
        with mock.patch("rundesk.commands.ask.arriving.recorded_for_a_delegation") as recorded:
            code, out, err = self.ask_from_ava("trace")

        self.assertEqual(FAILED, code)
        self.assertEqual("", out)
        self.assertIn("trace", err)
        self.assertIn("not configured to delegate to trace", err)
        recorded.assert_not_called()
        self.assertEqual([], delegations.every("ava"))

    def test_an_empty_scope_refuses_every_target_before_writing(self):
        records.stated(directory.records("ava"), {"delegates_to": "[]"})
        with mock.patch("rundesk.commands.ask.arriving.recorded_for_a_delegation") as recorded:
            code, _out, err = self.ask_from_ava("forge")

        self.assertEqual(FAILED, code)
        self.assertIn("not configured to delegate to forge", err)
        recorded.assert_not_called()
        self.assertEqual([], delegations.every("ava"))

    def test_a_completed_revocation_cannot_be_followed_by_stale_authority_admission(self):
        records.stated(directory.records("ava"),
                       {"delegates_to": json.dumps(["forge"])})
        scope_read = threading.Event()
        release_admission = threading.Event()
        revocation_waiting = threading.Event()
        order = []
        results = {}
        original_scope = delegating.scope_of
        original_lock = locking.only_one

        def paused_scope(agent):
            scope = original_scope(agent)
            scope_read.set()
            self.assertTrue(release_admission.wait(2))
            return scope

        @contextmanager
        def observed_lock(*args, **kwargs):
            if threading.current_thread().name == "revocation":
                revocation_waiting.set()
            with original_lock(*args, **kwargs) as waited:
                yield waited

        def admit():
            results["admit"] = self.ask_from_ava("forge")
            order.append("admitted")

        def revoke():
            results["revoke"] = self.rundesk(
                "agents", "configure", "ava", "--delegate-to-none")
            order.append("revoked")

        with mock.patch("rundesk.commands.ask.delegating.scope_of", side_effect=paused_scope), \
                mock.patch.object(locking, "only_one", side_effect=observed_lock):
            admission = threading.Thread(target=admit, name="admission")
            revocation = threading.Thread(target=revoke, name="revocation")
            admission.start()
            self.assertTrue(scope_read.wait(2))
            revocation.start()
            self.assertTrue(revocation_waiting.wait(2))
            release_admission.set()
            admission.join(2)
            revocation.join(2)

        self.assertFalse(admission.is_alive())
        self.assertFalse(revocation.is_alive())
        self.assertEqual(["admitted", "revoked"], order)
        self.assertEqual(OK, results["admit"][0], results["admit"][2])
        self.assertEqual(OK, results["revoke"][0], results["revoke"][2])
        self.assertEqual([], json.loads(
            records.read(directory.records("ava"))["delegates_to"]))


if __name__ == "__main__":
    unittest.main()
