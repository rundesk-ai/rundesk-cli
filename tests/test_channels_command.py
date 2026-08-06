"""The `channels` verb group, driven as somebody typing it.

Every case here goes through `cli.main` and asserts on what a person or a script would see: the exit
code, what landed on stdout, what landed on stderr. Nothing looks at internals — those are held by
the suites for each module — and nothing asserts on a credential's value, because none is ever
printed.

**The adapters are real programs on disk and never a stand-in for one.** The whole point of the seam
is that an adapter is something the operating system runs rather than something Python imports, so a
fake would prove nothing about the part that matters: that `--check` really decides whether a channel
is written down, that what the owner typed after `--` reaches the program exactly, and that the allow
list reaches it before it has signed in. `tests/test_channels_adapters.py` makes the same choice for
the same reason.

The exit codes are the part worth being careful about. A listing that found nothing exits zero; a
`--confirm` that was left off exits non-zero having taken nothing, because a script reading zero would
take it for done; and `doctor` exits non-zero when anything is wrong, so it can be gated on.

Run directly: `python3 tests/test_channels_command.py`
"""

import json
import unittest
from typing import List
from unittest import mock

import support
from rundesk.agents import directory
from rundesk.channels import adapters, hosting, kept
from rundesk.core import paths, secrets

#: An adapter that answers everything, and answers it out of what it was actually handed.
#:
#: It refuses with no credential **and names the variable it looked in**, which is how `add` learns
#: what to ask somebody for; it refuses with no allow list, which is how a case sees that
#: `RUNDESK_ALLOW` reached it; and what it says it reached is built from both, so nothing here can
#: pass by describing a connection it never made.
A_WORKING_ADAPTER = """#!/bin/sh
case "$1" in
  --capabilities) echo '{"stream": true, "max_text": 2000}' ;;
  --check)
    if [ -z "$A_TOKEN" ]; then
      echo '{"ok": false, "why": "there is no token — nothing set A_TOKEN",
             "secret": {"env": ["A_TOKEN"]}}'
    elif [ -z "$RUNDESK_ALLOW" ]; then
      echo '{"ok": false, "why": "nothing said who may reach this agent"}'
    else
      shift
      printf '{"ok": true, "describes": "a bot, reaching %s", "notify_place": "1180",
               "settings": {"typed": "%s"}, "secret": {"env": ["A_TOKEN"]},
               "invite": "https://example.invalid/invite"}\\n' "$RUNDESK_ALLOW" "$*"
    fi ;;
esac
exit 0
"""

#: One that connects, is told no, and names nothing to set — there is nothing to prompt for and
#: nothing to be done but read the sentence.
AN_ADAPTER_THAT_REFUSES = """#!/bin/sh
[ "$1" = "--check" ] && echo '{"ok": false, "why": "that token is not a bot"}'
exit 0
"""

#: One that needs no account at all. A channel is not obliged to have a credential, and a run that
#: prompted for one anyway would be reading from a terminal nobody is at.
AN_ADAPTER_THAT_NEEDS_NOTHING = """#!/bin/sh
case "$1" in
  --capabilities) echo '{"stream": false}' ;;
  --check) echo '{"ok": true, "describes": "a thing with no account", "settings": {}}' ;;
esac
exit 0
"""

#: A value long enough that `secrets.hinted` would show three characters of each end of it — so a
#: case asserting the whole thing never appears is asserting something that could fail.
A_TOKEN = "MTIzNDU2Nzg5-a-real-looking-bot-token"


class Channels(support.Isolated):
    """A scratch install with an agent, and somewhere for adapters to stand that is not the repo."""

    def setUp(self) -> None:
        super().setUp()
        # **`app/src` is stood up first, and that is not decoration.** `paths.code()` answers with
        # the *checkout* when the scratch root has no installed program tree — so without this, a
        # case writing a shipped adapter writes it into the repository somebody is working in.
        # `tests/test_channels_adapters.py` records that happening: two fixture programs landed in
        # `src/channels/` beside real source.
        (paths.home() / "app" / "src").mkdir(parents=True, exist_ok=True)
        self.shipped = paths.code() / adapters.SHIPPED_IN
        self.shipped.mkdir(parents=True, exist_ok=True)
        self.assertTrue(support.CHECKOUT not in self.shipped.parents,
                        "a case was about to write an adapter into the checkout")
        directory.made("alan", "claude")

    def an_adapter(self, kind: str = "chat", body: str = A_WORKING_ADAPTER):
        at = self.shipped / kind
        at.write_text(body, encoding="utf-8")
        at.chmod(0o755)
        return at

    def typing(self, *said):
        """Answer each prompt in turn, the way somebody at a terminal would.

        An empty one is an assertion in itself: a run that prompts when it should not raises
        `StopIteration` rather than quietly reading from whatever is on the other end of fd 0.
        """
        return mock.patch("rundesk.commands.env.typed", side_effect=list(said))

    def connect(self, *more: str, kind: str = "chat", token: str = A_TOKEN):
        """Add a channel the way somebody would, answering the one prompt it asks."""
        with self.typing(token):
            return self.rundesk("channels", "add", "alan", kind, "--allow", "1180", *more)

    def a_channel(self, *more: str, kind: str = "chat"):
        self.an_adapter(kind)
        code, _out, err = self.connect(*more, kind=kind)
        self.assertEqual(0, code, err)


class WhatAnEmptyInstallSays(Channels):
    def test_a_listing_that_found_nothing_exits_zero_and_says_what_to_type(self):
        code, out, err = self.rundesk("channels")
        self.assertEqual(0, code)
        self.assertIn(str(paths.agents()), out)
        self.assertIn("rundesk channels add", out)
        self.assertEqual("", err)

    def test_the_bare_verb_and_list_are_the_same_thing(self):
        self.assertEqual(self.rundesk("channels"), self.rundesk("channels", "list"))

    def test_one_agents_listing_says_it_is_that_agents(self):
        # "no channels" and "no channels *for this agent*" are different things to learn.
        code, out, _err = self.rundesk("channels", "list", "alan")
        self.assertEqual(0, code)
        self.assertIn("channels for alan", out)

    def test_a_name_that_is_not_an_agent_is_refused(self):
        code, _out, err = self.rundesk("channels", "list", "nobody")
        self.assertEqual(1, code)
        self.assertIn("nobody is not an agent", err)

    def test_doctor_with_nothing_connected_exits_zero(self):
        code, out, _err = self.rundesk("channels", "doctor")
        self.assertEqual(0, code)
        self.assertIn("nothing is connected", out)


class ConnectingAnAgent(Channels):
    def test_without_allow_it_refuses_and_says_the_whole_command_to_type(self):
        # Required by the verb rather than by argparse: argparse's own refusal names a flag and does
        # not say whose id to go and find.
        self.an_adapter()
        code, out, err = self.rundesk("channels", "add", "alan", "chat")
        self.assertEqual(1, code)
        self.assertEqual("", out)
        self.assertIn("--allow <id>", err)
        self.assertIn("nothing was added", err)
        self.assertEqual([], kept.all("alan"))

    def test_an_allow_that_is_empty_is_told_apart_from_one_that_was_left_off(self):
        # Almost always a shell variable that was never set, which is exactly the case where being
        # told to type the flag again does not help.
        self.an_adapter()
        code, _out, err = self.rundesk("channels", "add", "alan", "chat", "--allow", "")
        self.assertEqual(1, code)
        self.assertIn("nothing in it", err)
        self.assertEqual([], kept.all("alan"))

    def test_an_adapter_nothing_stands_under_says_where_it_looked(self):
        code, _out, err = self.rundesk("channels", "add", "alan", "nowhere", "--allow", "1180")
        self.assertEqual(1, code)
        self.assertIn(str(self.shipped), err)
        self.assertEqual([], kept.all("alan"))

    def test_it_asks_for_the_credential_the_adapter_named_and_then_connects(self):
        self.an_adapter()
        with self.typing(A_TOKEN):
            code, out, err = self.rundesk("channels", "add", "alan", "chat", "--allow", "1180")
        self.assertEqual(0, code, err)
        self.assertIn("A_TOKEN", out, "the name it asked for was never said")
        self.assertIn("alan is connected to chat", out)
        self.assertEqual(["chat"], [str(one["kind"]) for one in kept.all("alan")])

    def test_the_value_that_was_typed_is_never_printed(self):
        self.an_adapter()
        with self.typing(A_TOKEN):
            _code, out, err = self.rundesk("channels", "add", "alan", "chat", "--allow", "1180")
        self.assertNotIn(A_TOKEN, out + err)

    def test_the_allow_list_reaches_the_adapter_before_it_signs_in(self):
        # `RUNDESK_ALLOW` is not only a hosting-time fact: an adapter reports where unprompted things
        # would land by opening that conversation, so one handed no list refuses. The fixture builds
        # what it says it reached out of the list, so this cannot pass without it having arrived.
        self.a_channel()
        self.assertEqual("a bot, reaching 1180", kept.one("alan", "chat")["describes"])

    def test_what_the_owner_gave_the_adapter_reaches_it_exactly(self):
        self.a_channel("--with", "--room 9930")
        self.assertEqual({"typed": "--room 9930"},
                         json.loads(kept.one("alan", "chat")["settings"]))

    def test_options_nobody_could_read_are_refused_where_they_were_typed(self):
        # `shlex` hands an unbalanced quote back as no words at all, which is indistinguishable from
        # having said nothing — so the adapter would answer about a connection nobody described.
        self.an_adapter()
        with self.typing():
            code, _out, err = self.rundesk("channels", "add", "alan", "chat",
                                           "--allow", "1180", "--with", "--room '9930")
        self.assertEqual(1, code)
        self.assertIn("quoting", err)
        self.assertEqual([], kept.all("alan"))

    def test_the_name_the_credential_is_kept_under_is_recorded(self):
        # Recorded and never re-derived: `channels.hosting` hands the adapter each recorded name back
        # with its value under that same name, so a name worked out a second time anywhere is a
        # channel that passes `--check` and finds nothing when it is hosted.
        self.a_channel()
        self.assertEqual(["A_TOKEN"], json.loads(kept.one("alan", "chat")["secret_names"]))
        self.assertTrue(secrets.placed("A_TOKEN"))

    def test_nothing_is_written_down_when_the_adapter_will_not_connect(self):
        self.an_adapter(body=AN_ADAPTER_THAT_REFUSES)
        with self.typing():
            code, out, err = self.rundesk("channels", "add", "alan", "chat", "--allow", "1180")
        self.assertEqual(1, code)
        self.assertEqual("", out)
        self.assertIn("that token is not a bot", err)
        self.assertEqual([], kept.all("alan"), "a channel was written for a connection never made")

    def test_an_adapter_that_needs_no_account_is_never_prompted_for_one(self):
        self.an_adapter(body=AN_ADAPTER_THAT_NEEDS_NOTHING)
        with self.typing():                     # any prompt at all raises StopIteration
            code, out, err = self.rundesk("channels", "add", "alan", "chat", "--allow", "1180")
        self.assertEqual(0, code, err)
        self.assertIn("a thing with no account", out)

    def test_typing_nothing_for_a_value_nothing_holds_leaves_the_channel_unwritten(self):
        self.an_adapter()
        with self.typing(None):
            code, _out, err = self.rundesk("channels", "add", "alan", "chat", "--allow", "1180")
        self.assertEqual(1, code)
        self.assertIn("rundesk env set A_TOKEN", err)
        self.assertEqual([], kept.all("alan"))

    def test_a_value_this_install_already_keeps_is_said_out_loud_and_kept_by_typing_nothing(self):
        # The name belongs to the adapter and is the same for every agent using it, so a second
        # channel naming it is a second channel using one credential. Said rather than written over.
        secrets.stated("A_TOKEN", A_TOKEN)
        self.an_adapter()
        with self.typing(None):
            code, out, err = self.rundesk("channels", "add", "alan", "chat", "--allow", "1180")
        self.assertEqual(0, code, err)
        self.assertIn("already set on this install", out)

    def test_what_the_adapter_can_do_is_asked_offline_and_reported(self):
        # Asked with no credential anywhere near it, so that a fidelity difference is a fact rather
        # than a guess — a surface that cannot edit a message told apart from one that can and did
        # not.
        self.an_adapter()
        with self.typing(A_TOKEN):
            _code, out, _err = self.rundesk("channels", "add", "alan", "chat", "--allow", "1180")
        self.assertIn("max_text=2000", out)

    def test_the_invite_it_reported_is_printed_so_the_bot_can_be_added_somewhere(self):
        self.an_adapter()
        with self.typing(A_TOKEN):
            _code, out, _err = self.rundesk("channels", "add", "alan", "chat", "--allow", "1180")
        self.assertIn("https://example.invalid/invite", out)

    def test_connecting_the_same_platform_twice_is_refused_rather_than_replaced(self):
        self.a_channel()
        with self.typing(None):
            code, _out, err = self.rundesk("channels", "add", "alan", "chat", "--allow", "1180")
        self.assertEqual(1, code)
        self.assertIn("already connected", err)

    def test_notify_marks_it_as_the_one_unprompted_things_go_to(self):
        self.a_channel("--notify")
        told = kept.told("alan")
        self.assertIsNotNone(told)
        self.assertEqual("chat", told["kind"])
        self.assertEqual("1180", told["notify_place"])

    def test_without_notify_the_agent_tells_nobody_anything(self):
        self.a_channel()
        self.assertIsNone(kept.told("alan"))

    def test_a_name_that_is_not_an_agent_is_refused_before_any_program_runs(self):
        self.an_adapter()
        with self.typing():
            code, _out, err = self.rundesk("channels", "add", "nobody", "chat", "--allow", "1180")
        self.assertEqual(1, code)
        self.assertIn("nobody is not an agent", err)


class WhatAListingSays(Channels):
    def setUp(self) -> None:
        super().setUp()
        self.a_channel()

    def test_it_shows_the_channel_and_who_may_reach_it(self):
        code, out, _err = self.rundesk("channels")
        self.assertEqual(0, code)
        self.assertIn("chat", out)
        self.assertIn("alan", out)

    def test_a_channel_nothing_is_hosting_is_not_reported_as_connected(self):
        _code, out, _err = self.rundesk("channels", "list", "alan")
        self.assertIn("not connected", out)

    def test_standing_is_the_claim_the_kernel_holds_and_not_the_record(self):
        # Asked of the lock, exactly as `gateways` asks it: a record holds a pid, and a pid whose
        # process is gone is a number that now belongs to something else.
        with hosting.claiming("alan", "chat"):
            _code, out, _err = self.rundesk("channels", "list", "alan")
        self.assertIn("connected", out)
        self.assertNotIn("not connected", out)

    def test_a_record_left_by_something_that_is_gone_does_not_make_it_connected(self):
        hosting.record_of("alan", "chat").parent.mkdir(parents=True, exist_ok=True)
        hosting.record_of("alan", "chat").write_text('{"kind": "chat", "pid": 424242}',
                                                     encoding="utf-8")
        _code, out, _err = self.rundesk("channels", "list", "alan")
        self.assertIn("not connected", out)
        self.assertNotIn("424242", out)


class WhatOneChannelSays(Channels):
    def setUp(self) -> None:
        super().setUp()
        self.a_channel()

    def test_it_reads_back_everything_the_channel_was_given(self):
        code, out, _err = self.rundesk("channels", "show", "alan", "chat")
        self.assertEqual(0, code)
        self.assertIn("a bot, reaching 1180", out)
        self.assertIn("1180", out)
        self.assertIn(str(self.shipped / "chat"), out)

    def test_a_credential_is_described_as_set_and_never_shown(self):
        _code, out, err = self.rundesk("channels", "show", "alan", "chat")
        self.assertIn("A_TOKEN (set)", out)
        self.assertNotIn(A_TOKEN, out + err)

    def test_a_credential_that_is_no_longer_readable_says_so_rather_than_nothing(self):
        secrets.cleared("A_TOKEN")
        _code, out, _err = self.rundesk("channels", "show", "alan", "chat")
        self.assertIn("A_TOKEN (NOT SET)", out)

    def test_a_platform_this_agent_is_not_connected_to_is_refused(self):
        code, _out, err = self.rundesk("channels", "show", "alan", "slack")
        self.assertEqual(1, code)
        self.assertIn("alan has no slack channel", err)


class ChangingWhoMayReachIt(Channels):
    def setUp(self) -> None:
        super().setUp()
        self.a_channel()

    def test_naming_nothing_to_change_is_refused_rather_than_reported_as_a_success(self):
        code, out, err = self.rundesk("channels", "configure", "alan", "chat")
        self.assertEqual(1, code)
        self.assertEqual("", out)
        self.assertIn("nothing was named to change", err)

    def test_allow_adds_somebody(self):
        code, out, err = self.rundesk("channels", "configure", "alan", "chat", "--allow", "2207")
        self.assertEqual(0, code, err)
        self.assertIn("2207", out)
        self.assertEqual(["1180", "2207"], kept.who_may_reach(kept.one("alan", "chat")))

    def test_deny_takes_somebody_away(self):
        self.rundesk("channels", "configure", "alan", "chat", "--allow", "2207")
        code, _out, err = self.rundesk("channels", "configure", "alan", "chat", "--deny", "1180")
        self.assertEqual(0, code, err)
        self.assertEqual(["2207"], kept.who_may_reach(kept.one("alan", "chat")))

    def test_denying_somebody_who_was_never_there_is_refused(self):
        # Answering "done" would leave somebody believing they had taken away access they had not.
        code, _out, err = self.rundesk("channels", "configure", "alan", "chat", "--deny", "9999")
        self.assertEqual(1, code)
        self.assertIn("9999", err)
        self.assertEqual(["1180"], kept.who_may_reach(kept.one("alan", "chat")))

    def test_taking_the_last_one_away_is_refused(self):
        code, _out, err = self.rundesk("channels", "configure", "alan", "chat", "--deny", "1180")
        self.assertEqual(1, code)
        self.assertIn("nobody", err)
        self.assertEqual(["1180"], kept.who_may_reach(kept.one("alan", "chat")))

    def test_one_id_named_on_both_sides_is_refused_before_anything_is_written(self):
        code, _out, err = self.rundesk("channels", "configure", "alan", "chat",
                                       "--allow", "1180", "--deny", "1180")
        self.assertEqual(1, code)
        self.assertIn("both", err)
        self.assertEqual(["1180"], kept.who_may_reach(kept.one("alan", "chat")))

    def test_notify_marks_a_channel_that_was_not_the_told_one(self):
        code, _out, err = self.rundesk("channels", "configure", "alan", "chat", "--notify")
        self.assertEqual(0, code, err)
        self.assertEqual("chat", kept.told("alan")["kind"])


class AskingItToConnectAgain(Channels):
    def setUp(self) -> None:
        super().setUp()
        self.a_channel()

    def test_it_says_what_it_reached_and_changes_nothing(self):
        code, out, err = self.rundesk("channels", "test", "alan", "chat")
        self.assertEqual(0, code, err)
        self.assertIn("reached a bot, reaching 1180", out)
        self.assertEqual(["1180"], kept.who_may_reach(kept.one("alan", "chat")))

    def test_a_credential_that_is_gone_is_a_failure_rather_than_a_quiet_pass(self):
        secrets.cleared("A_TOKEN")
        code, out, err = self.rundesk("channels", "test", "alan", "chat")
        self.assertEqual(1, code)
        self.assertEqual("", out)
        self.assertIn("A_TOKEN", err)

    def test_an_adapter_that_has_gone_is_named_rather_than_crashed_on(self):
        (self.shipped / "chat").unlink()
        code, _out, err = self.rundesk("channels", "test", "alan", "chat")
        self.assertEqual(1, code)
        self.assertIn(str(self.shipped), err)


class TakingAChannelAway(Channels):
    def setUp(self) -> None:
        super().setUp()
        self.a_channel()

    def test_without_confirm_it_says_what_it_would_take_and_takes_none_of_it(self):
        code, out, err = self.rundesk("channels", "remove", "alan", "chat")
        self.assertEqual(1, code)
        self.assertEqual("", out, "a preview on stdout is a refusal a script reads as the answer")
        self.assertIn("nothing was removed", err)
        self.assertIn("--confirm", err)
        self.assertEqual(["chat"], [str(one["kind"]) for one in kept.all("alan")])

    def test_the_preview_says_what_it_would_keep_as_well_as_what_it_would_take(self):
        _code, _out, err = self.rundesk("channels", "remove", "alan", "chat")
        self.assertIn("A_TOKEN", err)
        self.assertIn(str(hosting.at("alan", "chat")), err)

    def test_with_confirm_it_takes_the_connection_and_keeps_the_credential(self):
        code, out, err = self.rundesk("channels", "remove", "alan", "chat", "--confirm")
        self.assertEqual(0, code, err)
        self.assertIn("no longer connected to chat", out)
        self.assertEqual([], kept.all("alan"))
        self.assertTrue(secrets.placed("A_TOKEN"),
                        "a removal took a credential no backup can put back")

    def test_removing_one_that_is_not_there_is_a_failure(self):
        code, _out, err = self.rundesk("channels", "remove", "alan", "slack", "--confirm")
        self.assertEqual(1, code)
        self.assertIn("alan has no slack channel", err)


class WhatCannotBeUsed(Channels):
    def setUp(self) -> None:
        super().setUp()
        self.a_channel()

    def test_a_channel_that_can_reach_something_is_ready_and_exits_zero(self):
        code, out, err = self.rundesk("channels", "doctor")
        self.assertEqual(0, code, err)
        self.assertIn("READY", out)
        self.assertIn("all 1 of them are ready", out)

    def test_a_missing_credential_is_blocked_and_names_the_command_that_sets_it(self):
        secrets.cleared("A_TOKEN")
        code, out, err = self.rundesk("channels", "doctor")
        self.assertEqual(1, code)
        self.assertIn("BLOCKED", out)
        self.assertIn("rundesk env set A_TOKEN", err)

    def test_an_adapter_that_has_gone_is_dangling(self):
        (self.shipped / "chat").unlink()
        code, out, err = self.rundesk("channels", "doctor")
        self.assertEqual(1, code)
        self.assertIn("DANGLING", out)
        self.assertIn("rundesk channels remove alan chat --confirm", err)

    def test_a_credential_the_platform_no_longer_accepts_is_unreachable(self):
        # The failure this verb exists to find, and nothing on this machine can tell it from a
        # working one: the adapter has to be asked.
        self.an_adapter(body=AN_ADAPTER_THAT_REFUSES)
        code, out, err = self.rundesk("channels", "doctor")
        self.assertEqual(1, code)
        self.assertIn("UNREACHABLE", out)
        self.assertIn("that token is not a bot", out)
        self.assertIn("rundesk channels test alan chat", err)

    def test_the_findings_are_on_stdout_and_the_summary_on_stderr(self):
        # So a script can read one and ignore the other — and the findings are flushed first, or the
        # summary appears above what it summarises when both are merged into one pipe.
        secrets.cleared("A_TOKEN")
        _code, out, err = self.rundesk("channels", "doctor")
        self.assertIn("BLOCKED", out)
        self.assertNotIn("BLOCKED", err)
        self.assertIn("cannot be used", err)
        self.assertNotIn("cannot be used", out)

    def test_one_agent_can_be_asked_about_on_its_own(self):
        code, _out, err = self.rundesk("channels", "doctor", "alan")
        self.assertEqual(0, code, err)

    def test_a_name_that_is_not_an_agent_is_refused(self):
        code, _out, err = self.rundesk("channels", "doctor", "nobody")
        self.assertEqual(1, code)
        self.assertIn("nobody is not an agent", err)


class TheShapeOfTheGroup(Channels):
    def test_the_help_names_the_group(self):
        _code, out, _err = self.rundesk("--help")
        self.assertIn("channels", out)

    def test_every_sub_verb_is_wired_to_something(self):
        # The `AssertionError` at the bottom of `cmd_channels` is what catches one registered on the
        # parser and answered by nothing, and this is what makes sure it never has to.
        from rundesk import cli
        registered: List[str] = []
        for action in cli.build_parser()._actions:
            if isinstance(action, cli.Subcommands) and "channels" in action.choices:
                for one in action.choices["channels"]._actions:
                    if isinstance(one, cli.Subcommands):
                        registered.extend(one.choices)
        self.assertTrue(registered)
        for verb in sorted(set(registered)):
            with self.subTest(verb=verb):
                # Driven with nothing else, so most of these refuse — what is being checked is that
                # none of them reaches the `AssertionError`, which would come out as a traceback.
                code, _out, _err = self.rundesk("channels", verb, "x", "y")
                self.assertIn(code, (0, 1, 2))


if __name__ == "__main__":
    unittest.main()
