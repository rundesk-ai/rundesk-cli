"""`rundesk providers` — what a person types, and what a person is shown.

Driven through `self.rundesk(...)`, so the real parser and the real dispatch answer every case. A
case that called `cmd_providers` directly would prove the module and not the command: the sub-verb it
registered, the flag it spelled, and the exit code the shell reads are exactly the parts a direct
call skips.

Four verbs, and they are asked for four different reasons. **`list` and `check` are the offline
pair** — what can this install run, and what does one of them say it can do — and neither needs an
account, a network or an agent. **`instructions` is the prompt in front of somebody**, which is the
only way the standing words an agent works under can be read, tweaked and compared against a turn
that has already happened. **`run` is what a firing starts**, and it is on the command surface
because a schedule that cannot be tried by hand is a schedule nobody can debug.

Run directly: `python3 tests/test_providers_command.py`
"""

import threading
import unittest
from contextlib import contextmanager
from types import SimpleNamespace
from unittest import mock

import support
from rundesk.agents import directory, records
from rundesk.channels import arriving
from rundesk.commands import agents as agents_command
from rundesk.commands import providers as providers_command
from rundesk.core import paths
from rundesk.exits import FAILED, OK, USAGE
from rundesk.gateways import standing
from rundesk.providers import adapters, instructions, kept, turns
from rundesk.schedules import kept as schedules_kept
from rundesk.skills import grants
from rundesk.utils import locking

#: The smallest legitimate adapter: it answers `--capabilities` and can do nothing.
SAYS_NOTHING = """#!/bin/sh
printf '%s\\n' '{}'
"""


class Providers(support.Isolated):

    def setUp(self):
        super().setUp()
        # `paths.code()` answers with the checkout until an install exists, so a case that wrote an
        # adapter without this would write it into the repository somebody is working in — and
        # `list` would answer with whatever this release happens to ship.
        (paths.home() / "app" / "src").mkdir(parents=True, exist_ok=True)
        self.shipped = paths.code() / adapters.SHIPPED_IN
        self.shipped.mkdir(parents=True, exist_ok=True)

    def an_adapter(self, named="a-brain", body=SAYS_NOTHING, runnable=True):
        at = self.shipped / named
        at.write_text(body, encoding="utf-8")
        at.chmod(0o755 if runnable else 0o644)
        return at

    def an_agent(self, named="cole", provider=support.A_STAND_IN):
        directory.made(named, provider)
        return named


class Listing(Providers):

    def test_an_install_with_none_says_so_and_says_where_they_go(self):
        # `as_table` prints nothing at all when there are no rows, headings included — so a listing
        # that leant on it would print nothing and leave "there are none" to be inferred silence.
        code, out, _err = self.rundesk("providers")
        self.assertEqual(OK, code)
        self.assertIn("no provider adapter here yet", out)
        self.assertIn(str(paths.data() / adapters.GIVEN_IN), out)

    def test_each_one_is_shown_with_the_program_behind_it(self):
        """The program, not just the name: two installs on one machine is the case where knowing
        *which* file answers to a name is the whole question."""
        made = self.an_adapter("a-brain")
        code, out, _err = self.rundesk("providers", "list")
        self.assertEqual(OK, code)
        self.assertIn("a-brain", out)
        self.assertIn(str(made), out)

    def test_a_file_that_cannot_be_run_is_not_offered_as_one(self):
        self.an_adapter("half-installed", runnable=False)
        code, out, _err = self.rundesk("providers")
        self.assertEqual(OK, code)
        self.assertNotIn("half-installed", out)


class Checking(Providers):

    def test_it_shows_each_capability_as_yes_or_no_and_never_only_the_yeses(self):
        """**Absent means no**, and a person has to be able to see the no. A list of what a brain
        can do, with the rest left out, reads as a shorter list of capabilities rather than as a
        complete answer."""
        self.an_adapter("a-brain", SAYS_NOTHING)
        code, out, _err = self.rundesk("providers", "check", "a-brain")
        self.assertEqual(OK, code)
        for can in ("tools", "resume", "model", "usage", "steer"):
            self.assertIn(can, out)
        self.assertIn("no", out)

    def test_whatever_it_volunteered_is_shown_apart_from_what_was_asked(self):
        """A version an adapter reports is the thing that explains a turn six months later, and it
        is kept because it was said — not because this release knows what it means."""
        self.an_adapter("a-brain", """#!/bin/sh
printf '%s\\n' '{"tools": true, "codex_cli": "0.146.0"}'
""")
        code, out, _err = self.rundesk("providers", "check", "a-brain")
        self.assertEqual(OK, code)
        self.assertIn("rundesk did not ask", out)
        self.assertIn("0.146.0", out)

    def test_a_name_nothing_stands_behind_fails_and_says_where_it_looked(self):
        code, _out, err = self.rundesk("providers", "check", "nowhere")
        self.assertEqual(FAILED, code)
        self.assertIn("looked in", err)

    def test_asking_with_no_name_is_the_command_line_being_wrong(self):
        code, _out, _err = self.rundesk("providers", "check")
        self.assertEqual(USAGE, code)


class AccountAliases(Providers):
    ADAPTER = """#!/bin/sh
if [ "$1" = "--capabilities" ]; then
  printf '%s\\n' '{"account_aliases": true}'
elif [ "$1" = "--account-status" ]; then
  printf '%s\\n' '{"state": "authenticated"}'
elif [ "$1" = "--account-login" ] || [ "$1" = "--account-logout" ]; then
  exit 0
else
  exit 2
fi
"""

    def setUp(self):
        super().setUp()
        self.an_adapter("a-brain", self.ADAPTER)

    def test_add_list_status_login_and_logout_use_only_normalized_state(self):
        code, out, err = self.rundesk("providers", "aliases", "add", "a-brain", "work")
        self.assertEqual(OK, code, err)
        self.assertIn("authenticated", out)

        code, out, err = self.rundesk("providers", "aliases", "list", "a-brain")
        self.assertEqual(OK, code, err)
        self.assertIn("work", out)

        for words in (("status", "a-brain", "--alias", "work"),
                      ("login", "a-brain", "--alias", "work")):
            with self.subTest(words=words):
                code, out, err = self.rundesk("providers", *words)
                self.assertEqual(OK, code, err)
                self.assertIn("authenticated", out)

        code, _out, err = self.rundesk(
            "providers", "logout", "a-brain", "--alias", "work")
        self.assertEqual(FAILED, code)
        self.assertIn("nothing was logged out", err)

    def test_remove_requires_confirmation_and_refuses_an_agent_default(self):
        self.rundesk("providers", "aliases", "add", "a-brain", "work")
        agent = self.an_agent(provider="a-brain")
        records.stated(directory.records(agent), {"provider_alias": "work"})

        code, _out, err = self.rundesk(
            "providers", "aliases", "remove", "a-brain", "work", "--confirm")
        self.assertEqual(FAILED, code)
        self.assertIn("configured default", err)

    def test_logout_refuses_to_change_an_active_turns_account_boundary(self):
        self.rundesk("providers", "aliases", "add", "a-brain", "work")
        self.an_agent(provider="a-brain")
        active = {"provider_name": "a-brain", "provider_alias": "work",
                  "conversation_id": 7}
        with mock.patch.object(kept, "list_unfinished_turns", return_value=[active]), \
                mock.patch.object(turns, "standing", return_value=True), \
                mock.patch.object(adapters, "account_logout") as logged_out:
            code, _out, err = self.rundesk(
                "providers", "logout", "a-brain", "--alias", "work", "--confirm")
        self.assertEqual(FAILED, code)
        self.assertIn("active turn", err)
        logged_out.assert_not_called()

    def test_login_is_allowed_while_an_admitted_turn_keeps_its_selection(self):
        self.an_agent(provider="a-brain")
        active = {"provider_name": "a-brain", "provider_alias": None,
                  "conversation_id": 7}
        with mock.patch.object(kept, "list_unfinished_turns", return_value=[active]), \
                mock.patch.object(turns, "standing", return_value=True), \
                mock.patch.object(
                    adapters, "account_login", return_value="authenticated") as logged_in:
            code, _out, err = self.rundesk("providers", "login", "a-brain")
        self.assertEqual(OK, code, err)
        logged_in.assert_called_once()

    def test_logout_serializes_with_the_durable_turn_admission_decision(self):
        """A turn cannot resolve an account while provider-owned logout invalidates it."""
        agent = self.an_agent(provider="a-brain")
        conversation = arriving.asked_at_a_terminal(agent, "wait for authentication").conversation
        logout_entered = threading.Event()
        release_logout = threading.Event()
        admission_waiting = threading.Event()
        order = []
        results = {}
        lock_paths = {}
        original_lock = locking.only_one

        def paused_logout(*_args):
            logout_entered.set()
            self.assertTrue(release_logout.wait(2))
            order.append("logout")
            return "signed_out"

        @contextmanager
        def observed_lock(*args, **kwargs):
            lock_paths[threading.current_thread().name] = args[0].resolve()
            if threading.current_thread().name == "admission":
                admission_waiting.set()
            with original_lock(*args, **kwargs) as waited:
                yield waited

        def logout():
            results["logout"] = providers_command._account_logout("a-brain", None, True)

        def admit():
            results["admission"] = turns._admit(turns.Request(
                agent=agent, prompt="wait for authentication", conversation=conversation))
            order.append("admission")

        with mock.patch.object(adapters, "account_logout", side_effect=paused_logout), \
                mock.patch.object(locking, "only_one", side_effect=observed_lock):
            logout_thread = threading.Thread(target=logout, name="logout")
            admission_thread = threading.Thread(target=admit, name="admission")
            logout_thread.start()
            self.assertTrue(logout_entered.wait(2))
            admission_thread.start()
            self.assertTrue(admission_waiting.wait(2))
            self.assertEqual([], kept.list_turns(agent),
                             "turn admission crossed the provider authentication change")
            release_logout.set()
            logout_thread.join(2)
            admission_thread.join(2)

        self.assertFalse(logout_thread.is_alive())
        self.assertFalse(admission_thread.is_alive())
        self.assertEqual(["logout", "admission"], order)
        self.assertEqual(lock_paths["logout"], lock_paths["admission"])
        self.assertEqual(OK, results["logout"])
        self.assertEqual(1, len(kept.list_turns(agent)))

    def test_alias_removal_waits_for_configuration_validation_and_its_write(self):
        account = providers_command.accounts.registered("a-brain", "work")
        agent = self.an_agent(provider="a-brain")
        alias_checked = threading.Event()
        release_configuration = threading.Event()
        removal_waiting = threading.Event()
        results = {}
        lock_paths = {}
        original_check = agents_command._checked_alias
        original_lock = locking.only_one

        def paused_check(provider, alias):
            original_check(provider, alias)
            alias_checked.set()
            self.assertTrue(release_configuration.wait(2))

        @contextmanager
        def observed_lock(*args, **kwargs):
            lock_paths[threading.current_thread().name] = args[0].resolve()
            if threading.current_thread().name == "removal":
                removal_waiting.set()
            with original_lock(*args, **kwargs) as waited:
                yield waited

        def configure():
            results["configure"] = agents_command._configured(
                agent, "a-brain", provider_alias="work")

        def remove():
            results["remove"] = providers_command._aliases(SimpleNamespace(
                alias_what="remove", provider="a-brain", alias="work", confirm=True))

        with mock.patch.object(agents_command, "_checked_alias", side_effect=paused_check), \
                mock.patch.object(locking, "only_one", side_effect=observed_lock):
            configuration = threading.Thread(target=configure, name="configuration")
            removal = threading.Thread(target=remove, name="removal")
            configuration.start()
            self.assertTrue(alias_checked.wait(2))
            removal.start()
            self.assertTrue(removal_waiting.wait(2))
            self.assertTrue(account.home.exists())
            release_configuration.set()
            configuration.join(2)
            removal.join(2)

        self.assertFalse(configuration.is_alive())
        self.assertFalse(removal.is_alive())
        self.assertEqual(lock_paths["configuration"], lock_paths["removal"])
        self.assertEqual(OK, results["configure"])
        self.assertEqual(FAILED, results["remove"])
        self.assertEqual("work", records.read(directory.records(agent))["provider_alias"])
        self.assertTrue(account.home.exists())

    def test_default_is_reserved_for_the_implicit_provider_account(self):
        code, _out, err = self.rundesk(
            "providers", "aliases", "add", "a-brain", "default")
        self.assertEqual(FAILED, code)
        self.assertIn("reserved", err)


class Instructions(Providers):
    """The standing words an agent works under, in front of somebody who can change them."""

    def test_it_prints_the_prompt_with_what_each_layer_cost(self):
        agent = self.an_agent()
        code, out, err = self.rundesk("providers", "instructions", agent)
        self.assertEqual(OK, code, err)
        self.assertIn("core", out)
        self.assertIn("bytes", out)

    def test_the_situation_changes_what_is_said(self):
        """A person asking and a schedule falling due are different situations, and an agent that
        could not tell them apart would answer a clock as though somebody were waiting."""
        agent = self.an_agent()
        _code, asked, _err = self.rundesk("providers", "instructions", agent,
                                          "--situation", "person")
        _code, due, _err = self.rundesk("providers", "instructions", agent,
                                        "--situation", "schedule")
        self.assertNotEqual(asked, due)

    def test_the_preview_includes_current_teammate_skill_names(self):
        agent = self.an_agent("ava")
        directory.made("reviewer", support.A_STAND_IN, "Reviews production risk.")
        skill = grants.where("reviewer") / "senior-code-reviewer"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text("---\nname: senior-code-reviewer\n"
                                         "description: Reviews risk.\n---\n", encoding="utf-8")
        with standing.holding(directory.where("reviewer")):
            code, out, err = self.rundesk("providers", "instructions", agent)
        self.assertEqual(OK, code, err)
        self.assertIn("Reviews production risk.", out)
        self.assertIn("skills: senior-code-reviewer", out)

    def test_a_schedule_preview_includes_the_same_current_team_as_a_scheduled_turn(self):
        agent = self.an_agent("ava")
        directory.made("reviewer", support.A_STAND_IN, "Reviews production risk.")
        with standing.holding(directory.where("reviewer")):
            code, out, err = self.rundesk(
                "providers", "instructions", agent, "--situation", "schedule")
        self.assertEqual(OK, code, err)
        self.assertIn("Reviews production risk.", out)
        self.assertIn("Who else is here", out)

    def test_an_inbound_only_preview_omits_the_complete_named_agent_layer(self):
        agent = self.an_agent("ava")
        directory.made("reviewer", support.A_STAND_IN, "Reviews production risk.")
        records.stated(directory.records(agent), {"delegates_to": "[]"})
        with standing.holding(directory.where("reviewer")):
            code, out, err = self.rundesk("providers", "instructions", agent)
        self.assertEqual(OK, code, err)
        self.assertNotIn("Who else is here", out)
        self.assertNotIn('"$RUNDESK_COMMAND" ask <agent>', out)

    def test_a_delegation_preview_does_not_scan_or_show_the_team(self):
        agent = self.an_agent("ava")
        with mock.patch("rundesk.commands.providers.team.for_agent",
                        side_effect=AssertionError("team was inspected")):
            code, out, err = self.rundesk(
                "providers", "instructions", agent, "--situation", "agent")
        self.assertEqual(OK, code, err)
        self.assertNotIn("Who else is here", out)
        self.assertNotIn("\nagents", out)

    def test_a_past_turn_is_recomposed_and_compared_rather_than_read_back(self):
        """The fingerprint is re-derived, so changed composition is never shown as historical."""
        agent = self.an_agent()
        code, _out, err = self.rundesk("ask", agent, "what changed today?")
        self.assertEqual(OK, code, err)
        code, out, err = self.rundesk("providers", "instructions", agent, "--turn", "1")
        self.assertEqual(OK, code, err)
        self.assertIn("turn 1", out)
        self.assertIn("unchanged since it ran", out)
        self.assertIn(agent, out)

    def test_a_past_turn_uses_its_teammate_snapshot_after_the_gateway_stops(self):
        agent = self.an_agent("ava")
        directory.made("reviewer", support.A_STAND_IN, "Reviews production risk.")
        with standing.holding(directory.where("reviewer")):
            code, _out, err = self.rundesk("ask", agent, "what changed today?")
        self.assertEqual(OK, code, err)

        code, out, err = self.rundesk("providers", "instructions", agent, "--turn", "1")
        self.assertEqual(OK, code, err)
        self.assertIn("Reviews production risk.", out)
        self.assertIn("unchanged since it ran", out)

    def test_a_historical_record_without_a_team_snapshot_reports_drift(self):
        agent = self.an_agent("ava")
        directory.made("reviewer", support.A_STAND_IN, "Reviews production risk.")
        with standing.holding(directory.where("reviewer")):
            code, _out, err = self.rundesk("ask", agent, "what changed today?")
        self.assertEqual(OK, code, err)
        with records.writing(directory.records(agent)) as conn:
            conn.execute("UPDATE turn_records SET event_data = '{}'"
                         " WHERE turn_id = 1 AND record_type = 'instructions'")

        code, out, err = self.rundesk("providers", "instructions", agent, "--turn", "1")
        self.assertEqual(OK, code, err)
        self.assertIn("composes a different prompt", out)

    def test_a_release_that_composes_something_else_says_so_rather_than_showing_today(self):
        """A fingerprint catches changed static composition around the stored volatile inputs."""
        agent = self.an_agent()
        self.rundesk("ask", agent, "what changed today?")
        with mock.patch.object(instructions, "CORE", instructions.CORE + "\n\nAnd one more rule."):
            code, out, err = self.rundesk("providers", "instructions", agent, "--turn", "1")
        self.assertEqual(OK, code, err)
        self.assertIn("composes a different prompt", out)
        self.assertIn("today's words", out)

    def test_a_turn_asked_for_without_an_agent_says_what_to_type(self):
        code, _out, err = self.rundesk("providers", "instructions", "--turn", "1")
        self.assertEqual(FAILED, code)
        self.assertIn("--turn", err)

    def test_a_turn_that_is_not_there_fails_rather_than_composing_something(self):
        agent = self.an_agent()
        code, _out, err = self.rundesk("providers", "instructions", agent, "--turn", "9")
        self.assertEqual(FAILED, code)
        self.assertTrue(err.strip(), "a turn that is not there was refused in silence")

    def test_an_agent_that_is_not_there_fails_and_says_what_to_type(self):
        code, _out, err = self.rundesk("providers", "instructions", "nobody")
        self.assertEqual(FAILED, code)
        self.assertIn("rundesk agents", err)


class Running(Providers):
    """`providers run` — one scheduled turn, taken here. What a firing starts."""

    def a_schedule(self, agent, name="nightly", prompt="what happened overnight?", **also):
        schedules_kept.added(agent, name, dict({"cron": "* * * * *", "prompt": prompt},
                                               **also))
        return name

    def test_it_takes_the_turn_and_says_what_became_of_it(self):
        agent = self.an_agent()
        self.a_schedule(agent)
        code, _out, err = self.rundesk("providers", "run", agent, "--schedule", "nightly")
        self.assertEqual(OK, code, err)
        there = kept.list_turns(agent)
        self.assertEqual(1, len(there))
        self.assertEqual("done", there[0]["turn_status"])

    def test_the_turn_it_took_is_tied_to_the_schedule_that_caused_it(self):
        agent = self.an_agent()
        self.a_schedule(agent)
        self.rundesk("providers", "run", agent, "--schedule", "nightly")
        turn = kept.list_turns(agent)[0]
        self.assertEqual(schedules_kept.one(agent, "nightly")["id"], turn["schedule_id"])

    def test_a_schedule_that_names_a_program_is_refused_and_says_what_to_type(self):
        agent = self.an_agent()
        self.a_schedule(agent, "build", prompt=None, command="/bin/echo hi")
        code, _out, err = self.rundesk("providers", "run", agent, "--schedule", "build")
        self.assertEqual(FAILED, code)
        self.assertIn("rundesk schedules run", err)

    def test_a_brain_that_could_not_answer_exits_non_zero(self):
        """The number a supervisor reads. A firing recorded as having worked when it did not is
        worse than one recorded as having failed."""
        agent = self.an_agent()
        self.a_stand_in_told(agent, fail_with="upstream_error")
        self.a_schedule(agent)
        code, _out, err = self.rundesk("providers", "run", agent, "--schedule", "nightly")
        self.assertEqual(FAILED, code)
        self.assertIn("upstream_error", err)

    def test_a_schedule_that_is_not_there_fails_rather_than_running_nothing_quietly(self):
        agent = self.an_agent()
        code, _out, err = self.rundesk("providers", "run", agent, "--schedule", "nowhere")
        self.assertEqual(FAILED, code)
        self.assertIn("nowhere", err)


if __name__ == "__main__":
    unittest.main()
