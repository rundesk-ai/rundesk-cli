"""A channel on a real gateway process — the adapter it starts, and what leaves through it.

Split out of `tests/test_gateway_host.py`, which it shares a harness with through
`fixtures_gateways`. Two files rather than one because `scripts/suites` parallelises whole files and
this half is the slower of the two; together they are the same cases the one file ran.

`tests/test_channels_hosting.py` proves everything hosting an adapter promises on its own. What is
here is only what a *supervised process* adds — that a channel cannot stop a gateway starting, that
what leaves through one really leaves, and that a stop takes the adapter with it.

Run directly: `python3 tests/test_gateway_channels.py`
"""

import datetime
import json
import os
import shutil
import signal
import unittest
from pathlib import Path
from typing import List
from unittest import mock

from fixtures_gateways import AN_ADAPTER, WithAChannel

import support
from rundesk import __version__
from rundesk.agents import directory, records
from rundesk.channels import arriving, hosting
from rundesk.channels import kept as channels
from rundesk.core import config, secrets
from rundesk.delegations import kept as delegations_kept
from rundesk.exits import OK
from rundesk.gateways import host, maintenance, standing
from rundesk.providers import kept as turns_kept
from rundesk.providers import protocol
from rundesk.schedules import due, kept
from rundesk.skills import grants, library

#: One whose platform says no to everything: every delivery comes back a `failed` carrying a reason
#: rather than a receipt. A rate limit and a permission the bot was never granted are the two that
#: really happen, and both arrive in exactly this shape.
AN_ADAPTER_THAT_IS_REFUSED = """#!/usr/bin/env python3
import json, os, signal, sys
if "--capabilities" in sys.argv:
    print(json.dumps({"stream": True, "max_text": 2000})); raise SystemExit(0)
signal.signal(signal.SIGTERM, signal.SIG_IGN)
print(json.dumps({"say": "ready", "as": "a-bot"}), flush=True)
for line in sys.stdin:
    try:
        record = json.loads(line)
    except ValueError:
        continue
    if record.get("do") == "stop":
        break
    if record.get("do") == "deliver":
        print(json.dumps({"say": "failed", "id": record.get("id"),
                          "why": "would not take it: 429 Too Many Requests"}), flush=True)
"""


AN_ADAPTER_THAT_RECORDS_DELEGATIONS = """#!/usr/bin/env python3
import json, os, signal, sys
if "--capabilities" in sys.argv:
    print(json.dumps({"stream": True, "max_text": 2000})); raise SystemExit(0)
signal.signal(signal.SIGTERM, signal.SIG_IGN)
settings = json.loads(os.environ.get("RUNDESK_SETTINGS") or "{}")
print(json.dumps({"say": "ready", "as": "a-bot"}), flush=True)
for line in sys.stdin:
    try:
        record = json.loads(line)
    except ValueError:
        continue
    if record.get("do") == "stop":
        break
    if record.get("do") == "delegation":
        with open(settings["heard"], "a") as writing:
            writing.write(json.dumps(record) + "\\n")
"""


#: One that will not connect without its credential and never says what it was. `78` is `EX_CONFIG`,
#: which is what a missing token is — so a gateway that failed to resolve one has an adapter that
#: dies rather than one that connects anonymously, and the notified channel simply never says
#: anything. That silence is the assertion, and it costs no value being written anywhere.
#: A value long enough that `secrets.hinted` would show three characters of each end, so a case
#: asserting the whole thing appears nowhere is asserting something that could fail.
A_BOT_TOKEN = "MTIzNDU2Nzg5-coles-own-bot-token"

AN_ADAPTER_THAT_NEEDS_ITS_CREDENTIAL = """#!/usr/bin/env python3
import json, os, signal, sys
if "--capabilities" in sys.argv:
    print(json.dumps({"stream": True, "max_text": 2000})); raise SystemExit(0)
signal.signal(signal.SIGTERM, signal.SIG_IGN)
settings = json.loads(os.environ.get("RUNDESK_SETTINGS") or "{}")
if not os.environ.get("DISCORD_BOT_TOKEN"):
    sys.stderr.write("no credential reached this adapter\\n")
    raise SystemExit(78)
print(json.dumps({"say": "ready", "as": "a-bot"}), flush=True)
for line in sys.stdin:
    try:
        record = json.loads(line)
    except ValueError:
        continue
    if record.get("do") == "stop":
        break
    if record.get("do") == "deliver":
        with open(settings["heard"], "a") as writing:
            writing.write(record.get("place", "") + " :: " + record.get("text", "") + "\\n")
"""


class TheChannelsItHosts(WithAChannel):
    """A real gateway, a real channel, and the adapter it really starts.

    The second tenant, wired through the same gateway process every other case here uses.
    `tests/test_channels_hosting.py` proves everything hosting an adapter promises on its own; what
    is here is only what a *supervised process* adds — that a channel cannot stop a gateway starting,
    that what leaves through one really leaves, and that a stop takes the adapter with it.
    """

    def a_hosted_channel(self, body: str = AN_ADAPTER) -> hosting.Watching:
        """The adapter hosted in *this* process, so a case can call `_told` and read its answer.

        Every other case here drives a real gateway subprocess, which is what proves supervision.
        These two are about what one function answers, and its answer cannot be read across a fork.
        """
        self.an_adapter(body=body)
        self.a_channel()
        where = standing.logs_at(self.at)
        watching = hosting.looked(self.name, where, hosting.Watching({}, {}, {}))
        self.addCleanup(hosting.stopping, self.name, where, watching, 4.0)
        self.assertTrue(support.waited_until(
            lambda: hosting.connected(watching, "discord"), self.PATIENCE),
            "the adapter never connected")
        return watching

    def where_it_logs(self):
        return standing.logs_at(self.at)

    def test_a_notice_the_platform_refused_is_not_reported_as_told(self):
        # **`TOLD` meant *written to a pipe*, and a caller deciding whether to write something down
        # read it as *a person saw this*.** The goodbye is the measured case: it waits a round trip
        # precisely because the adapter is signalled a moment later, and a platform refusing it came
        # back indistinguishable from one that took it — so a gateway could report that it had said
        # farewell when the words were refused.
        watching = self.a_hosted_channel(body=AN_ADAPTER_THAT_IS_REFUSED)
        self.assertEqual(host.REFUSED,
                         host._told(self.name, self.where_it_logs(), watching, host.WENT_DOWN,
                                    landed_within=3.0))

    def test_a_notice_nobody_refused_is_still_told(self):
        # Silence goes on reading as landed: an adapter is free to acknowledge nothing at all, and
        # this one does exactly that. Treating *nothing said* as a refusal would report a failure
        # for every whole adapter that simply does not answer.
        #
        # A short ceiling on purpose. This one is waiting for something that never arrives, so the
        # whole of it is spent — and every second of it is a second the rest of this file's
        # `waited_until` ceilings are competing with on a loaded runner.
        watching = self.a_hosted_channel()
        self.assertEqual(host.TOLD,
                         host._told(self.name, self.where_it_logs(), watching, host.WENT_DOWN,
                                    landed_within=0.5))

    def test_a_refused_notice_is_said_once_and_not_twice(self):
        # A caller that hands a list in is going to say what it makes of the refusal — the scheduled
        # report says which files it then went without — so this saying it as well would be two
        # accounts of one refusal. Said here only when nobody asked.
        watching = self.a_hosted_channel(body=AN_ADAPTER_THAT_IS_REFUSED)
        asked_for: List[str] = []
        self.assertEqual(host.REFUSED,
                         host._told(self.name, self.where_it_logs(), watching, host.WENT_DOWN,
                                    landed_within=3.0, refusals=asked_for))
        self.assertEqual(1, len(asked_for), "the caller that asked for the reason never got it")
        self.assertNotIn("the notice for", self.its_log(),
                         "a refusal somebody asked for was announced a second time as well")

        # Asked of this sentence and not of the reason, which `hosting._refused` already writes for
        # every refusal either way — an assertion on "429" alone would stay green with the whole of
        # this branch deleted.
        host._told(self.name, self.where_it_logs(), watching, host.WENT_DOWN, landed_within=2.0)
        self.assertIn(f"the notice for {self.name} was refused", self.its_log(),
                      "a refusal nobody asked for reached nobody at all")

    def test_a_gateway_starts_the_adapter_for_a_configured_channel(self):
        self.an_adapter()
        self.a_channel()
        self.a_running_gateway(beat=self.A_SHORT_BEAT)
        self.assertTrue(support.waited_until(
            lambda: "channel discord: started as pid" in self.its_log(), self.PATIENCE),
            f"no adapter was ever started. It said: {self.its_log()}")
        self.assertTrue(support.waited_until(
            lambda: hosting.still_running(self.name, "discord"), self.PATIENCE),
            "the claim was never taken, so nothing is holding this channel")

    def test_a_gateway_that_came_up_says_so_through_the_channel_that_is_told_things(self):
        # Not into the log — a person who wanted to know their gateway is back is not reading a file
        # on the machine it is running on. The one channel marked `notified` is where it lands.
        self.an_adapter()
        self.a_channel()
        self.a_running_gateway(beat=self.A_SHORT_BEAT)
        self.assertTrue(support.waited_until(lambda: host.CAME_UP in self.was_heard(),
                                             self.PATIENCE),
                        f"nobody was told. It said: {self.its_log()}")
        self.assertIn("1180 ::", self.was_heard(), "it went somewhere other than the told place")
        # **A colour and a word, and nothing under it.** A version and a process id are what
        # somebody debugging wants and they are in the log, where debugging is done; on a channel
        # they are noise arriving in the middle of a conversation.
        self.assertNotIn(__version__, self.was_heard())
        self.assertNotIn(str(self.name) + " on", self.was_heard())

    def test_a_gateway_returning_from_an_update_names_and_links_the_installed_release(self):
        self.an_adapter()
        self.a_channel()
        notes = f"https://github.com/rundesk-ai/rundesk-cli/releases/tag/v{__version__}"
        maintenance.installed(self.at, __version__, notes)

        self.a_running_gateway(beat=self.A_SHORT_BEAT)

        expected = maintenance.INSTALLED.format(version=__version__, notes=notes)
        self.assertTrue(support.waited_until(lambda: expected in self.was_heard(), self.PATIENCE),
                        f"nobody was told. It said: {self.its_log()}")
        self.assertNotIn(host.CAME_UP, self.was_heard())
        self.assertFalse((self.at / maintenance.MARKER).exists())

    def test_an_agent_that_tells_nobody_anything_is_a_gateway_that_says_nothing(self):
        # `delivery.notice` answers `None`, which is an ordinary answer rather than a failure: an
        # agent with no notified channel is one somebody configured to be quiet.
        self.an_adapter()
        self.a_channel(told=False)
        child = self.a_running_gateway(beat=self.A_SHORT_BEAT)
        self.assertTrue(support.waited_until(
            lambda: "channel discord: started as pid" in self.its_log(), self.PATIENCE),
            f"no adapter was ever started. It said: {self.its_log()}")

        self.several_beats()

        self.assertEqual("", self.was_heard(), "it told a channel nobody marked as the told one")
        self.assertIsNone(child.poll(), "having nobody to tell ended the gateway")

    def test_a_gateway_asked_to_stop_says_so_through_the_channel_before_it_goes(self):
        # It has to leave *before* the stack unwinds, because unwinding it is what closes the
        # adapter the notice leaves through.
        self.an_adapter()
        self.a_channel()
        child = self.a_running_gateway(beat=self.A_SHORT_BEAT)
        self.assertTrue(support.waited_until(lambda: host.CAME_UP in self.was_heard(),
                                             self.PATIENCE), self.its_log())

        os.kill(child.pid, signal.SIGTERM)
        self.assertTrue(support.waited_until(lambda: child.poll() is not None, self.PATIENCE))

        self.assertTrue(support.waited_until(
            lambda: host.WENT_DOWN in self.was_heard(), self.PATIENCE),
            f"it went down without telling anybody. It heard: {self.was_heard()}")
        self.assertEqual(OK, child.returncode)

    def test_a_credential_of_this_agents_own_survives_a_full_stop_and_start(self):
        # **The release gate for per-agent credentials, asked of a supervised process.** Everything
        # about resolution is proved in `tests/test_channels_credentials.py` and
        # `tests/test_channels_hosting.py`; what only this can prove is that a whole gateway going
        # away and a whole new one coming up resolves it again — the adapter here exits `EX_CONFIG`
        # without a token, so a second gateway that failed to resolve one is a notified channel that
        # never says a word.
        #
        # Only the agent's own name is set. The install-wide one holds nothing at all, so nothing
        # here can pass on the fallback.
        secrets.stated("DISCORD_BOT_TOKEN__COLE", A_BOT_TOKEN)
        self.an_adapter(body=AN_ADAPTER_THAT_NEEDS_ITS_CREDENTIAL)
        self.a_channel(needing=("DISCORD_BOT_TOKEN",))

        first = self.a_running_gateway(beat=self.A_SHORT_BEAT)
        self.assertTrue(support.waited_until(lambda: host.CAME_UP in self.was_heard(),
                                             self.PATIENCE),
                        f"the notified channel never connected. It said: {self.its_log()}")

        os.kill(first.pid, signal.SIGTERM)
        self.assertTrue(support.waited_until(lambda: first.poll() is not None, self.PATIENCE))
        self.assertTrue(support.waited_until(
            lambda: not hosting.still_running(self.name, "discord"), self.PATIENCE),
            "the adapter outlived the gateway that started it")
        self.heard.unlink()

        self.a_running_gateway(beat=self.A_SHORT_BEAT)
        self.assertTrue(support.waited_until(lambda: host.CAME_UP in self.was_heard(),
                                             self.PATIENCE),
                        f"the notified channel never reconnected. It said: {self.its_log()}")

    def test_a_gateway_returning_from_an_update_reconnects_on_the_agents_own_credential(self):
        # **The update handoff carries no credential, and must not need to.** What crosses between
        # the old gateway and the new one is a small intent file beside the agent; the sealed store
        # is under `data/`, which an update never touches. So the returning release resolves the
        # value again from nothing but the store — and the proof is that a channel whose adapter
        # exits `EX_CONFIG` without a token still reaches the notified place.
        secrets.stated("DISCORD_BOT_TOKEN__COLE", A_BOT_TOKEN)
        self.an_adapter(body=AN_ADAPTER_THAT_NEEDS_ITS_CREDENTIAL)
        self.a_channel(needing=("DISCORD_BOT_TOKEN",))
        notes = f"https://github.com/rundesk-ai/rundesk-cli/releases/tag/v{__version__}"
        maintenance.installed(self.at, __version__, notes)

        self.a_running_gateway(beat=self.A_SHORT_BEAT)

        expected = maintenance.INSTALLED.format(version=__version__, notes=notes)
        self.assertTrue(support.waited_until(lambda: expected in self.was_heard(), self.PATIENCE),
                        f"the channel never came back after an update. It said: {self.its_log()}")
        self.assertNotIn(A_BOT_TOKEN, self.was_heard() + self.its_log() + self.what_it_said())

    def test_nothing_a_gateway_writes_anywhere_holds_the_credential_it_resolved(self):
        # Read out of every place a value could leak from a supervised run: the process output a
        # supervisor captures, the agent's own day log, the adapter's error file, and what really
        # went out through the channel.
        secrets.stated("DISCORD_BOT_TOKEN__COLE", A_BOT_TOKEN)
        self.an_adapter(body=AN_ADAPTER_THAT_NEEDS_ITS_CREDENTIAL)
        self.a_channel(needing=("DISCORD_BOT_TOKEN",))
        self.a_running_gateway(beat=self.A_SHORT_BEAT)
        self.assertTrue(support.waited_until(lambda: host.CAME_UP in self.was_heard(),
                                             self.PATIENCE), self.its_log())

        errors = hosting.errors_of(self.name, "discord")
        written = "".join([
            self.what_it_said(), self.its_log(), self.was_heard(),
            errors.read_text(encoding="utf-8", errors="replace") if errors.exists() else "",
            json.dumps(channels.one(self.name, "discord")),
        ])
        self.assertNotIn(A_BOT_TOKEN, written)
        # And the value is not copied under a second name either — one place keeps it, and
        # `channels.credentials` resolves rather than duplicates.
        self.assertEqual(["DISCORD_BOT_TOKEN__COLE"],
                         [one for one in secrets.names() if one.startswith("DISCORD_BOT_TOKEN")])

    def test_a_gateway_stood_down_for_an_update_uses_the_maintenance_notice(self):
        self.an_adapter()
        self.a_channel()
        child = self.a_running_gateway(beat=self.A_SHORT_BEAT)
        self.assertTrue(support.waited_until(lambda: host.CAME_UP in self.was_heard(),
                                             self.PATIENCE), self.its_log())
        maintenance.installing(self.at, "0.37.0")

        os.kill(child.pid, signal.SIGTERM)
        self.assertTrue(support.waited_until(lambda: child.poll() is not None, self.PATIENCE))

        self.assertTrue(support.waited_until(
            lambda: maintenance.INSTALLING in self.was_heard(), self.PATIENCE),
            f"it went down without the update notice. It heard: {self.was_heard()}")
        self.assertNotIn(host.WENT_DOWN, self.was_heard())
        self.assertFalse((self.at / maintenance.MARKER).exists())

    def test_a_schedule_that_failed_is_told_and_one_that_worked_is_not(self):
        # **The restraint is the guarantee.** A notice for every successful nightly job is how
        # somebody learns to ignore the channel, and the one they then miss is this one — so the
        # case asserts the silence as hard as it asserts the sentence, with a schedule that really
        # did complete standing beside the one that really did fail.
        self.an_adapter()
        self.a_channel()
        # Finish second on purpose: the assertion must observe both children, not inherit whichever
        # completion order this runner happened to schedule.
        kept.added(self.name, "good", {
            "cron": "* * * * *", "command": "/bin/sh -c 'sleep 2; echo it worked'"})
        kept.added(self.name, "bad", {"cron": "* * * * *",
                                      "command": "/bin/sh -c 'echo it went wrong >&2; exit 3'"})
        self.a_running_gateway(beat=self.A_SHORT_BEAT)

        def both_finished() -> bool:
            return ("schedule bad failed with exit 3" in self.was_heard()
                    and "schedule good completed" in self.its_log())

        self.assertTrue(support.waited_until(
            both_finished, self.PATIENCE),
            f"the schedules did not both finish. It heard: {self.was_heard()}. "
            f"Its log said: {self.its_log()}")
        self.assertIn("schedule good completed", self.its_log(),
                      "the schedule that worked never finished, so its silence proves nothing")
        self.assertNotIn("schedule good", self.was_heard(),
                         "a schedule that worked perfectly was announced to a person")

    def test_a_channel_whose_adapter_is_not_installed_never_stops_a_gateway_starting(self):
        # **Nothing about a channel is in `_may_not_run`.** A platform that is down, a credential
        # that has expired, an adapter somebody never installed — every one of those is a condition
        # a gateway should be up and complaining about, and a refusal here would take an agent's
        # whole gateway away over a misconfiguration in one of its channels.
        self.a_channel()                                 # and deliberately no adapter written
        child = self.a_running_gateway(beat=self.A_SHORT_BEAT)

        self.assertTrue(support.waited_until(
            lambda: "channel discord: did not start" in self.its_log(), self.PATIENCE),
            f"it never even tried. It said: {self.its_log()}")
        self.several_beats()
        self.assertIsNone(child.poll(), "a channel that could not start ended the gateway")
        self.assertEqual(standing.ONLINE, standing.standing(self.at).how)

    def test_an_orderly_stop_takes_the_adapter_it_started_with_it(self):
        # An adapter is in a session of its own, so launchd's group-wide cleanup of this job cannot
        # reach it either: if the gateway does not stop it, nothing ever will and the next gateway
        # finds the channel claimed by something nobody can account for.
        self.an_adapter()
        self.a_channel()
        child = self.a_running_gateway(beat=self.A_SHORT_BEAT)
        # **Waited for by the line the gateway writes, not by the claim** — the same race
        # `TheScheduleItHosts` records, and it bites harder here. The claim is taken *before* the
        # adapter is spawned, so `still_running` answers yes for the instant the gateway itself
        # holds it and there is nothing yet to stop; a case that signalled there raised `Stopped`
        # inside `_started`, and the gateway went down having taken hold of nothing at all.
        self.assertTrue(support.waited_until(
            lambda: "channel discord: started as pid" in self.its_log(), self.PATIENCE),
            f"the adapter never came up. It said: {self.its_log()}")

        os.kill(child.pid, signal.SIGTERM)
        self.assertTrue(support.waited_until(lambda: child.poll() is not None, self.PATIENCE))

        self.assertIn("stopped with this gateway", self.its_log())
        self.assertFalse(hosting.still_running(self.name, "discord"),
                         "the gateway stopped and left its adapter running with nobody holding it")

    def a_grant(self, name: str) -> Path:
        """A skill standing in this agent's own directory. Made by hand, because what the loop
        watches is the directory and not the command that usually writes it — which is the whole
        reason it watches rather than being told."""
        stands = grants.where(self.name) / name
        stands.mkdir(parents=True, exist_ok=True)
        (stands / library.DECLARED).write_text(
            f"---\nname: {name}\ndescription: Something. Use when something.\n---\n",
            encoding="utf-8")
        return stands

    def test_a_skill_the_agent_gained_is_told_through_the_channel_that_is_told_things(self):
        self.an_adapter()
        self.a_channel()
        self.a_grant("jira")                       # held before it starts, so the first look is quiet
        child = self.a_running_gateway(beat=self.A_SHORT_BEAT)
        self.assertTrue(support.waited_until(lambda: host.CAME_UP in self.was_heard(),
                                             self.PATIENCE))

        self.a_grant("writing-plans")

        self.assertTrue(
            support.waited_until(
                lambda: "🧩 Skill granted — `writing-plans`" in self.was_heard(), self.PATIENCE),
            f"nothing was said about it. It heard: {self.was_heard()}")
        self.assertIn("1180 ::", self.was_heard())
        self.assertIsNone(child.poll(), "the gateway went down saying it")

    def test_a_skill_the_agent_lost_is_told_the_same_way(self):
        self.an_adapter()
        self.a_channel()
        self.a_grant("jira")
        self.a_running_gateway(beat=self.A_SHORT_BEAT)
        self.assertTrue(support.waited_until(lambda: host.CAME_UP in self.was_heard(),
                                             self.PATIENCE))

        shutil.rmtree(grants.where(self.name) / "jira")

        self.assertTrue(
            support.waited_until(lambda: "🗑️ Skill revoked — `jira`" in self.was_heard(),
                                 self.PATIENCE),
            f"nothing was said about it. It heard: {self.was_heard()}")

    def test_a_first_look_after_an_upgrade_announces_nothing(self):
        # Two grants already standing and nothing written down: the gateway comes up, says so, and
        # says nothing whatever about skills the agent has held all along.
        self.an_adapter()
        self.a_channel()
        self.a_grant("jira")
        self.a_grant("writing-plans")

        child = self.a_running_gateway(beat=self.A_SHORT_BEAT)
        self.assertTrue(support.waited_until(lambda: host.CAME_UP in self.was_heard(),
                                             self.PATIENCE))
        self.several_beats()

        self.assertNotIn("Skill", self.was_heard())
        self.assertIsNone(child.poll())

    def test_a_change_is_told_once_however_many_beats_pass(self):
        # The rule this loop shares with every other one here: none of them may say the same thing
        # every fifteen seconds.
        self.an_adapter()
        self.a_channel()
        self.a_grant("jira")
        self.a_running_gateway(beat=self.A_SHORT_BEAT)
        self.assertTrue(support.waited_until(lambda: host.CAME_UP in self.was_heard(),
                                             self.PATIENCE))
        self.a_grant("writing-plans")
        self.assertTrue(support.waited_until(
            lambda: "writing-plans" in self.was_heard(), self.PATIENCE))

        self.several_beats()

        self.assertEqual(1, self.was_heard().count("🧩 Skill granted — `writing-plans`"))

    def test_an_agent_that_tells_nobody_anything_hears_nothing_about_its_skills(self):
        self.an_adapter()
        self.a_channel(told=False)
        self.a_grant("jira")
        child = self.a_running_gateway(beat=self.A_SHORT_BEAT)
        self.several_beats()

        self.a_grant("writing-plans")
        self.several_beats()

        self.assertEqual("", self.was_heard())
        self.assertIsNone(child.poll(), "the gateway went down over having nobody to tell")


class AStoppedDelegationAcrossGatewayPasses(WithAChannel):
    """The target settles the stop; the delegator emits it without waking a review turn."""

    def test_requested_stop_is_durably_stopped_and_never_answered_or_reviewed(self):
        target = "trace"
        directory.made(target, support.A_STAND_IN)
        parent = arriving.recorded(
            self.name, "discord", "1180", "2207", "delegate the audit", "message-1")
        parent_turn = turns_kept.add_turn(self.name, {
            "conversation_id": parent.conversation,
            "provider_name": support.A_STAND_IN,
            "access_mode": protocol.ACCESS_WORK,
        })
        turns_kept.finish_turn(self.name, parent_turn, turns_kept.DONE)
        delegation_id = "del-1-stopme"
        arriving.recorded_for_a_delegation(
            target, self.name, parent_turn, "audit it", delegation_id=delegation_id)
        delegations_kept.made(
            self.name, delegation_id, target, parent.conversation, parent_turn)
        self.assertTrue(delegations_kept.stop_asked(self.name, delegation_id))

        self.an_adapter(body=AN_ADAPTER_THAT_RECORDS_DELEGATIONS)
        self.a_channel()
        self.a_running_gateway(beat=0.05)
        self.assertTrue(support.waited_until(
            lambda: "channel discord: connected" in self.its_log(), self.PATIENCE),
            f"the delegator's channel never connected. It said: {self.its_log()}")
        turns_before = len(turns_kept.list_turns(self.name))

        self.hosting(name=target, out=self.home / "trace-gateway.out", beat=0.05)
        self.assertTrue(support.waited_until(
            lambda: bool(turns_kept.list_turns(target))
            and turns_kept.list_turns(target)[0]["turn_status"] == turns_kept.STOPPED,
            self.PATIENCE), "the target gateway never settled the requested stop")

        self.assertTrue(support.waited_until(
            lambda: delegations_kept.one(self.name, delegation_id).stopped_at is not None,
            self.PATIENCE), "the delegator gateway never persisted the stopped outcome")
        self.assertTrue(support.waited_until(
            lambda: '"state": "stopped"' in self.was_heard(), self.PATIENCE),
            f"the delegator gateway never emitted stopped. It heard: {self.was_heard()}. "
            f"It said: {self.its_log()}")

        one = delegations_kept.one(self.name, delegation_id)
        self.assertIsNotNone(one.stopped_at)
        self.assertIsNone(one.answered_at)
        self.assertNotIn('"state": "answered"', self.was_heard())
        self.assertEqual(turns_before, len(turns_kept.list_turns(self.name)),
                         "settling a stop woke a review turn")

        code, out, err = self.rundesk("asked", "--agent", self.name)
        self.assertEqual(OK, code, err)
        self.assertIn("stopped", out)
        self.assertNotIn("answered", out)


#: One that answers a delivery the way a real platform's adapter does — with what the platform then
#: called the message — and writes down whether rundesk asked it to be posted as a reply. Both are
#: needed here: the acknowledgement is the only moment rundesk can learn the id, and the `reply_to`
#: is the whole of what makes a report arrive underneath the notice rather than loose in a room.
AN_ADAPTER_THAT_NAMES_WHAT_IT_POSTED = """#!/usr/bin/env python3
import json, os, signal, sys
if "--capabilities" in sys.argv:
    print(json.dumps({"stream": True, "max_text": 2000})); raise SystemExit(0)
signal.signal(signal.SIGTERM, signal.SIG_IGN)
settings = json.loads(os.environ.get("RUNDESK_SETTINGS") or "{}")
print(json.dumps({"say": "ready", "as": "a-bot"}), flush=True)
posted = 0
for line in sys.stdin:
    try:
        record = json.loads(line)
    except ValueError:
        continue
    if record.get("do") == "stop":
        break
    if record.get("do") == "deliver":
        posted += 1
        named = "msg-%d" % posted
        with open(settings["heard"], "a") as writing:
            writing.write(json.dumps({"place": record.get("place", ""),
                                      "text": record.get("text", ""),
                                      "files": record.get("files", []),
                                      "notice": record.get("notice"),
                                      "reply_to": record.get("reply_to"),
                                      "to": record.get("to"),
                                      "threaded": record.get("threaded"),
                                      "external_id": named}) + "\\n")
        print(json.dumps({"say": "delivered", "id": record.get("id"),
                          "external_id": named}), flush=True)
"""


class WhatAScheduledRunSaysOnASurface(WithAChannel):
    """R-SCH-46. The clock's work, reaching the place its owner already looks.

    Work that ran at three in the morning is no use in an account nobody opens until they think to.
    So a run that somebody will be shown the answer to says when it begins, and its report arrives
    underneath that notice — one message at the start, one at the end, and nothing in between.
    """

    def a_stand_in_brain(self) -> str:
        """A real provider adapter on this install, so a scheduled turn genuinely answers."""
        records.stated(directory.records(self.name), {"provider_name": support.A_STAND_IN})
        return support.A_STAND_IN

    def what_was_posted(self) -> List[dict]:
        """Every delivery the adapter really took, as objects, oldest first."""
        if not self.heard.exists():
            return []
        return [json.loads(one) for one in self.heard.read_text(encoding="utf-8").splitlines()
                if one.strip()]

    def of_a_schedule(self) -> List[dict]:
        """Only what was posted about the schedule, so the gateway's own hello is not counted."""
        return [one for one in self.what_was_posted()
                if host.CAME_UP not in one["text"] and host.WENT_DOWN not in one["text"]]

    def a_gateway_running_one_schedule(self, prompt: str = "Post the weekday client update."):
        """A gateway whose channel is **already connected** before its schedule comes due.

        The order is the case's whole setup and not a convenience. A schedule is read off the
        records on every beat, so adding the row after the adapter has said `ready` is what puts the
        run in the ordinary condition — a gateway that has been up for a while. Added before, the
        first beat fires it while the adapter is still importing its platform's library, and what
        this class is about would be tested against a gateway that had nobody to talk to.
        """
        self.an_adapter(body=AN_ADAPTER_THAT_NAMES_WHAT_IT_POSTED)
        self.a_channel()
        self.a_stand_in_brain()
        child = self.a_running_gateway(beat=self.A_SHORT_BEAT)
        self.assertTrue(support.waited_until(
            lambda: "channel discord: connected" in self.its_log(), self.PATIENCE),
            f"the adapter never connected. It said: {self.its_log()}")
        kept.added(self.name, "weekday-client-update", {"cron": "* * * * *", "prompt": prompt})
        return child

    def test_it_says_it_has_begun_the_moment_the_run_starts(self):
        self.a_gateway_running_one_schedule()
        self.assertTrue(support.waited_until(
            lambda: any("Working on 'weekday-client-update'" in one["text"]
                        for one in self.of_a_schedule()), self.PATIENCE),
            f"nobody was told the run had begun. It heard: {self.what_was_posted()}. "
            f"It said: {self.its_log()}")

    def test_the_words_are_the_ones_rundesk_promises(self):
        self.a_gateway_running_one_schedule()
        self.assertTrue(support.waited_until(lambda: len(self.of_a_schedule()) >= 1,
                                             self.PATIENCE), self.its_log())
        self.assertEqual("💻 Working on 'weekday-client-update' — I will report back when it "
                         "is done.", self.of_a_schedule()[0]["text"])

    def test_the_answer_comes_back_as_a_reply_to_that_notice(self):
        """The whole point of announcing through a seam that answers: a report arriving twenty
        minutes later beside answers to other questions, anchored to nothing, is worse than none."""
        self.a_gateway_running_one_schedule()
        self.assertTrue(support.waited_until(lambda: len(self.of_a_schedule()) >= 2,
                                             self.PATIENCE),
            f"the run never reported. It heard: {self.what_was_posted()}. "
            f"It said: {self.its_log()}")
        began, reported = self.of_a_schedule()[0], self.of_a_schedule()[1]
        self.assertEqual(began["external_id"], reported["reply_to"],
                         "the report did not quote the notice that said the run had begun")

    def test_the_announcement_and_report_are_both_unsolicited_notices(self):
        self.a_gateway_running_one_schedule()
        self.assertTrue(support.waited_until(lambda: len(self.of_a_schedule()) >= 2,
                                             self.PATIENCE), self.its_log())
        began, reported = self.of_a_schedule()[0], self.of_a_schedule()[1]
        self.assertIs(began["notice"], True)
        self.assertIs(reported["notice"], True)

    def test_what_is_reported_is_what_the_agent_answered(self):
        """Not that a process exited zero. What an owner wants at six in the morning is what the
        agent found."""
        self.a_gateway_running_one_schedule()
        self.assertTrue(support.waited_until(lambda: len(self.of_a_schedule()) >= 2,
                                             self.PATIENCE), self.its_log())
        said = self.of_a_schedule()[1]["text"]
        self.assertIn("Post the weekday client update.", said,
                      f"the report was not the agent's own answer: {said!r}")

    def test_an_initial_turn_that_delegated_does_not_post_before_its_review(self):
        began = datetime.datetime(2026, 8, 4, 9, 0, tzinfo=datetime.timezone.utc)
        landed = arriving.recorded_for_a_schedule(
            self.name, "nightly", "review overnight work", when=began, invocation="run-1")
        turn = turns_kept.add_turn(self.name, {
            "conversation_id": landed.conversation, "schedule_name": "nightly",
            "provider_name": support.A_STAND_IN, "access_mode": protocol.ACCESS_WORK,
        }, when=began)
        delegations_kept.made(
            self.name, "del-nightly-aabbcc", "trace", landed.conversation, turn, now=began)

        with mock.patch.object(host, "_told") as told:
            host._Notices(
                self.name, standing.logs_at(self.at),
                lambda: hosting.Watching({}, {}, {})).reported(
                    "nightly", "msg-1", "done", config.moment_of(began))

        told.assert_not_called()

    def test_a_fast_delegation_reviewed_inside_the_initial_turn_reports_normally(self):
        began = datetime.datetime(2026, 8, 4, 9, 0, tzinfo=datetime.timezone.utc)
        landed = arriving.recorded_for_a_schedule(
            self.name, "nightly", "review overnight work", when=began, invocation="run-1")
        turn = turns_kept.add_turn(self.name, {
            "conversation_id": landed.conversation, "schedule_name": "nightly",
            "provider_name": support.A_STAND_IN, "access_mode": protocol.ACCESS_WORK,
        }, when=began)
        delegations_kept.made(
            self.name, "del-nightly-aabbcc", "trace", landed.conversation, turn, now=began)
        result = arriving.said_by_rundesk_into(
            self.name, landed.conversation, "trace returned", when=began,
            external_id="delegation-result:del-nightly-aabbcc:answer-1")
        arriving.handled_by_turn(self.name, landed.conversation, (result.message,), turn)
        arriving.said_by_agent_into(
            self.name, landed.conversation, "Reviewed final report.", turn=turn, when=began)

        with mock.patch.object(host, "_told") as told:
            host._Notices(
                self.name, standing.logs_at(self.at),
                lambda: hosting.Watching({}, {}, {})).reported(
                    "nightly", "msg-1", "done", config.moment_of(began))

        told.assert_called_once()
        self.assertEqual("Reviewed final report.", told.call_args.args[3])

    def test_a_run_posts_only_a_notice_and_a_report_and_never_its_activity(self):
        """A scheduled turn runs in a process of its own that holds no channel, so there is nothing
        for its working notes to be posted through. The property is where the work runs rather than
        a filter somebody has to maintain — and this is what proves it stays that way.

        **Asserted as a shape rather than as a count.** This schedule is due every minute, so a run
        can begin while the case is still looking; counting messages would then go red for a gateway
        behaving perfectly. What must hold however many times it fires is that every single thing
        reaching the surface is either a notice or an answer to one — never a line about a tool that
        was run, a file that was read, or a thought.
        """
        self.a_gateway_running_one_schedule()
        self.assertTrue(support.waited_until(lambda: len(self.of_a_schedule()) >= 2,
                                             self.PATIENCE), self.its_log())
        self.assertTrue(support.waited_until(
            lambda: "schedule weekday-client-update completed" in self.its_log(), self.PATIENCE),
            f"the run never finished. It said: {self.its_log()}")
        self.several_beats()

        notices = {one["external_id"] for one in self.of_a_schedule()
                   if one["text"].startswith("💻 Working on")}
        self.assertTrue(notices, "nothing ever said a run had begun")
        for one in self.of_a_schedule():
            with self.subTest(said=one["text"][:40]):
                self.assertTrue(one["external_id"] in notices or one["reply_to"] in notices,
                                f"something that was neither a notice nor an answer to one "
                                f"reached the surface: {one['text']!r}")

    def test_it_all_lands_in_the_place_the_agent_is_told_things(self):
        self.a_gateway_running_one_schedule()
        self.assertTrue(support.waited_until(lambda: len(self.of_a_schedule()) >= 2,
                                             self.PATIENCE), self.its_log())
        self.assertEqual({"1180"}, {one["place"] for one in self.of_a_schedule()})

    def test_a_run_that_failed_never_reports_the_last_run_s_answer_as_its_own(self):
        """**The real `_Notices`, against a real database.** A schedule that answered on Monday and
        failed on Tuesday without saying anything must not report Monday's legacy answer as its own.
        Reported unbounded, the old report goes out under Tuesday's notice and Tuesday's failure is
        never mentioned: an answer nobody earned, reported as fact."""
        self.an_adapter(body=AN_ADAPTER_THAT_NAMES_WHAT_IT_POSTED)
        self.a_channel()
        monday = datetime.datetime(2026, 8, 3, 9, 0, tzinfo=datetime.timezone.utc)
        arriving.said_by_agent(self.name, arriving.FROM_SCHEDULE, "nightly",
                               "Monday's report: all clear.", when=monday)
        logs_at = standing.logs_at(self.at)
        watching = hosting.looked(self.name, logs_at, hosting.Watching({}, {}, {}))
        self.addCleanup(hosting.stopping, self.name, logs_at, watching, 4.0)
        self.assertTrue(support.waited_until(
            lambda: hosting.connected(watching, "discord"), self.PATIENCE))

        notices = host._Notices(self.name, logs_at, lambda: watching)
        notices.reported("nightly", "msg-1", "failed",
                         config.moment_of(datetime.datetime(2026, 8, 4, 9, 0,
                                                            tzinfo=datetime.timezone.utc)))

        self.assertTrue(support.waited_until(lambda: len(self.what_was_posted()) >= 1,
                                             self.PATIENCE), "nothing was reported at all")
        said = self.what_was_posted()[-1]["text"]
        self.assertNotIn("Monday's report", said,
                         "a failed run reported an earlier run's answer as its own")
        self.assertIn("failed", said)

    def test_a_run_that_did_answer_reports_that_answer(self):
        """The bound may not be so tight that a run's own answer falls outside it — the case above
        would pass just as well against a `reported` that never reads the records at all."""
        self.an_adapter(body=AN_ADAPTER_THAT_NAMES_WHAT_IT_POSTED)
        self.a_channel()
        began = datetime.datetime(2026, 8, 4, 9, 0, tzinfo=datetime.timezone.utc)
        arriving.said_by_agent(self.name, arriving.FROM_SCHEDULE, "nightly", "Tuesday's report.",
                               when=datetime.datetime(2026, 8, 4, 9, 5,
                                                      tzinfo=datetime.timezone.utc))
        logs_at = standing.logs_at(self.at)
        watching = hosting.looked(self.name, logs_at, hosting.Watching({}, {}, {}))
        self.addCleanup(hosting.stopping, self.name, logs_at, watching, 4.0)
        self.assertTrue(support.waited_until(
            lambda: hosting.connected(watching, "discord"), self.PATIENCE))

        host._Notices(self.name, logs_at, lambda: watching).reported(
            "nightly", "msg-1", "done", config.moment_of(began))

        self.assertTrue(support.waited_until(lambda: len(self.what_was_posted()) >= 1,
                                             self.PATIENCE), "nothing was reported at all")
        self.assertIn("Tuesday's report.", self.what_was_posted()[-1]["text"])

    def test_a_scheduled_reports_local_link_is_attached_without_exposing_the_path(self):
        self.an_adapter(body=AN_ADAPTER_THAT_NAMES_WHAT_IT_POSTED)
        self.a_channel()
        at = self.home / "reports" / "Quarterly Preview.pdf"
        at.parent.mkdir(parents=True)
        at.write_bytes(b"a small pdf")
        began = datetime.datetime(2026, 8, 4, 9, 0, tzinfo=datetime.timezone.utc)
        arriving.said_by_agent(
            self.name, arriving.FROM_SCHEDULE, "nightly",
            f"Report: [the PDF](<file://{str(at).replace(' ', '%20')}>)",
            when=datetime.datetime(2026, 8, 4, 9, 5, tzinfo=datetime.timezone.utc))
        logs_at = standing.logs_at(self.at)
        watching = hosting.looked(self.name, logs_at, hosting.Watching({}, {}, {}))
        self.addCleanup(hosting.stopping, self.name, logs_at, watching, 4.0)
        self.assertTrue(support.waited_until(
            lambda: hosting.connected(watching, "discord"), self.PATIENCE))

        host._Notices(self.name, logs_at, lambda: watching).reported(
            "nightly", "msg-1", "done", config.moment_of(began))

        self.assertTrue(support.waited_until(lambda: self.what_was_posted(), self.PATIENCE))
        posted = self.what_was_posted()[-1]
        self.assertEqual(["Quarterly-Preview.pdf"],
                         [one["name"] for one in posted["files"]])
        self.assertNotIn("file://", posted["text"])
        self.assertNotIn(str(at), posted["text"])

    def test_a_scheduled_artifact_refused_by_the_adapter_falls_back_to_text(self):
        self.a_channel()
        at = self.home / "reports" / "preview.png"
        at.parent.mkdir(parents=True)
        at.write_bytes(b"pixels")
        began = datetime.datetime(2026, 8, 4, 9, 0, tzinfo=datetime.timezone.utc)
        arriving.said_by_agent(
            self.name, arriving.FROM_SCHEDULE, "nightly", f"Result: [preview]({at})",
            when=datetime.datetime(2026, 8, 4, 9, 5, tzinfo=datetime.timezone.utc))
        calls = []
        told = host._told
        self.addCleanup(setattr, host, "_told", told)

        def refusing(name, where, watching, saying, landed_within=0.0, answering=None,
                     sending=(), refusals=None, aimed=None, threaded=False):
            calls.append({"text": saying, "within": landed_within,
                          "sending": tuple(sending), "answering": answering,
                          "aimed": aimed, "threaded": threaded})
            if sending and refusals is not None:
                refusals.append("the file changed after approval")
            return host.TOLD

        host._told = refusing
        host._Notices(
            self.name, standing.logs_at(self.at),
            lambda: hosting.Watching({}, {}, {})).reported(
                "nightly", "msg-1", "done", config.moment_of(began))

        self.assertEqual(2, len(calls))
        self.assertGreater(calls[0]["within"], 0)
        self.assertTrue(calls[0]["sending"])
        self.assertFalse(calls[1]["sending"])
        self.assertIn("Could not attach: preview.png", calls[1]["text"])
        self.assertNotIn(str(at), calls[1]["text"])

    def test_a_long_scheduled_report_retries_only_its_refused_final_piece(self):
        self.a_channel()
        at = self.home / "reports" / "preview.png"
        at.parent.mkdir(parents=True)
        at.write_bytes(b"pixels")
        began = datetime.datetime(2026, 8, 4, 9, 0, tzinfo=datetime.timezone.utc)
        said = "BEGIN\n" + "x" * 5000 + f"\nEND [preview]({at})"
        arriving.said_by_agent(
            self.name, arriving.FROM_SCHEDULE, "nightly", said,
            when=datetime.datetime(2026, 8, 4, 9, 5, tzinfo=datetime.timezone.utc))
        calls = []
        told = host._told
        self.addCleanup(setattr, host, "_told", told)

        def refusing(name, where, watching, saying, landed_within=0.0, answering=None,
                     sending=(), refusals=None, aimed=None, threaded=False):
            calls.append({"text": saying, "answering": answering,
                          "aimed": aimed, "threaded": threaded})
            if sending and refusals is not None:
                refusals.append("the file changed after approval")
            return host.TOLD

        host._told = refusing
        host._Notices(
            self.name, standing.logs_at(self.at),
            lambda: hosting.Watching({}, {}, {})).reported(
                "nightly", "msg-1", "done", config.moment_of(began))

        self.assertEqual(2, len(calls))
        self.assertIn("BEGIN", calls[0]["text"])
        self.assertNotIn("BEGIN", calls[1]["text"])
        self.assertIn("END preview", calls[1]["text"])
        self.assertEqual("msg-1", calls[0]["answering"])
        self.assertIsNone(calls[1]["answering"])

    def test_a_split_reports_attach_failure_stays_in_the_thread_the_report_is_in(self):
        """R-SNT-19. A place target whose report was long enough to split and whose file the
        adapter would not take — the one combination that put the failure line in the room.

        **Both halves are asserted, because either alone passes while the line still lands in the
        room.** `hosting.told` writes `threaded` only beside the message it hangs off, so a
        `threaded` with no `answering` is dropped on the way through and the line stands loose in a
        room somebody else's — beside a report sitting in a thread, which is exactly what
        `docs/concepts/schedules.md` says a targeted run does not do.

        Dropping the anchor is right where there is no thread: it stops a split report quoting the
        notice twice, which `test_a_long_scheduled_report_retries_only_its_refused_final_piece`
        holds for the untargeted run beside this one.
        """
        self.a_channel()
        at = self.home / "reports" / "preview.png"
        at.parent.mkdir(parents=True)
        at.write_bytes(b"pixels")
        began = datetime.datetime(2026, 8, 4, 9, 0, tzinfo=datetime.timezone.utc)
        said = "BEGIN\n" + "x" * 5000 + f"\nEND [preview]({at})"
        arriving.said_by_agent(
            self.name, arriving.FROM_SCHEDULE, "nightly", said,
            when=datetime.datetime(2026, 8, 4, 9, 5, tzinfo=datetime.timezone.utc))
        calls = []
        told = host._told
        self.addCleanup(setattr, host, "_told", told)

        def refusing(name, where, watching, saying, landed_within=0.0, answering=None,
                     sending=(), refusals=None, aimed=None, threaded=""):
            calls.append({"text": saying, "answering": answering, "threaded": threaded})
            if sending and refusals is not None:
                refusals.append("the file changed after approval")
            return host.TOLD

        host._told = refusing
        host._Notices(
            self.name, standing.logs_at(self.at),
            lambda: hosting.Watching({}, {}, {})).reported(
                "nightly", "msg-1", "done", config.moment_of(began),
                aimed=due.Target(channel="discord", place="C0OPS"))

        self.assertEqual(2, len(calls))
        self.assertIn("Could not attach: preview.png", calls[1]["text"])
        self.assertEqual(("msg-1", "nightly"), (calls[0]["answering"], calls[0]["threaded"]),
                         "the report itself did not open the thread")
        self.assertEqual(("msg-1", "nightly"), (calls[1]["answering"], calls[1]["threaded"]),
                         "the attach failure left the thread its own report stands in")

    def test_a_schedule_that_starts_a_program_says_neither(self):
        """It has no answer to report, so promising to report back is a promise rundesk does not
        keep — and a successful program stays as quiet as it always did."""
        self.an_adapter(body=AN_ADAPTER_THAT_NAMES_WHAT_IT_POSTED)
        self.a_channel()
        kept.added(self.name, "tick", {"cron": "* * * * *", "command": "/bin/echo it worked"})
        self.a_running_gateway(beat=self.A_SHORT_BEAT)
        self.assertTrue(support.waited_until(
            lambda: "schedule tick completed" in self.its_log(), self.PATIENCE),
            f"the schedule never ran, so its silence proves nothing. It said: {self.its_log()}")
        self.several_beats()
        self.assertEqual([], self.of_a_schedule(),
                         f"a program schedule reached the surface: {self.of_a_schedule()}")


class WhereAScheduledRunReports(WhatAScheduledRunSaysOnASurface):
    """R-SCH-59. A schedule that named its own destination, through a real gateway.

    Every layer between the clock and the platform is real here: the row on disk, the firing, the one
    resolver, the record that crosses the seam, and a child adapter that writes down exactly what it
    was asked to deliver. What this proves that the narrower suites cannot is that the destination
    survives the whole of that path — a schedule aimed somewhere is aimed there at both ends of its
    run, and one aimed nowhere is byte-for-byte the run it always was.
    """

    def a_gateway_running_one_targeted_schedule(self, **aimed):
        """The same gateway, with the schedule naming where it reports.

        The row is written directly rather than through the command, because what is under test is
        the delivery path — `tests/test_schedules_command.py` owns the checks that decide whether a
        destination may be written at all.
        """
        self.an_adapter(body=AN_ADAPTER_THAT_NAMES_WHAT_IT_POSTED)
        self.a_channel()
        self.a_stand_in_brain()
        child = self.a_running_gateway(beat=self.A_SHORT_BEAT)
        self.assertTrue(support.waited_until(
            lambda: "channel discord: connected" in self.its_log(), self.PATIENCE),
            f"the adapter never connected. It said: {self.its_log()}")
        kept.added(self.name, "weekday-client-update",
                   dict({"cron": "* * * * *", "prompt": "Post the weekday client update."},
                        **aimed))
        return child

    def both_messages(self):
        """The notice and the report, once both have really reached the adapter."""
        self.assertTrue(support.waited_until(lambda: len(self.of_a_schedule()) >= 2,
                                             self.PATIENCE),
                        f"the run never reported. It heard: {self.what_was_posted()}. "
                        f"It said: {self.its_log()}")
        return self.of_a_schedule()[0], self.of_a_schedule()[1]

    def test_the_notice_goes_to_the_place_the_schedule_named(self):
        self.a_gateway_running_one_targeted_schedule(
            channel="discord", channel_place_id="C0OPS")
        began, _reported = self.both_messages()
        self.assertEqual({"place": "C0OPS"}, began["to"])

    def test_the_notified_channels_own_place_is_not_sent_beside_it(self):
        # The one thing that would let an adapter deliver to the wrong one: two answers to *where*,
        # and the one it would reach for is the agent's own.
        self.a_gateway_running_one_targeted_schedule(
            channel="discord", channel_place_id="C0OPS")
        began, _reported = self.both_messages()
        self.assertEqual("", began["place"])

    def test_the_report_goes_to_the_same_place_as_the_notice(self):
        self.a_gateway_running_one_targeted_schedule(
            channel="discord", channel_place_id="C0OPS")
        began, reported = self.both_messages()
        # Both named rather than only compared with each other: two `None`s agree, and a report
        # that quietly went to the notified channel would pass a comparison and fail an owner.
        self.assertEqual({"place": "C0OPS"}, began["to"])
        self.assertEqual({"place": "C0OPS"}, reported["to"])
        self.assertEqual(began["external_id"], reported["reply_to"])

    def test_the_report_asks_for_a_thread_named_after_the_run(self):
        self.a_gateway_running_one_targeted_schedule(
            channel="discord", channel_place_id="C0OPS")
        _began, reported = self.both_messages()
        self.assertEqual("weekday-client-update", reported["threaded"])

    def test_a_notice_never_asks_for_a_thread_of_its_own(self):
        # The thread hangs off the notice, so the notice cannot already be in one.
        self.a_gateway_running_one_targeted_schedule(
            channel="discord", channel_place_id="C0OPS")
        began, _reported = self.both_messages()
        self.assertIsNone(began["threaded"])

    def test_a_direct_message_target_gets_the_platforms_own_presentation(self):
        # A direct conversation *is* the exchange, so there is nothing to open and nothing to open
        # it off — the report is a reply to the notice, exactly as it has always been.
        self.a_gateway_running_one_targeted_schedule(
            channel="discord", channel_sender_id="2207")
        began, reported = self.both_messages()
        self.assertEqual({"sender": "2207"}, began["to"])
        self.assertEqual({"sender": "2207"}, reported["to"])
        self.assertIsNone(reported["threaded"])
        self.assertEqual(began["external_id"], reported["reply_to"])

    def test_a_schedule_that_named_nothing_is_the_run_it_always_was(self):
        self.a_gateway_running_one_targeted_schedule()
        began, reported = self.both_messages()
        for one in (began, reported):
            self.assertIsNone(one["to"])
            self.assertIsNone(one["threaded"])
            self.assertEqual("1180", one["place"])

    def test_a_quiet_run_still_reports_to_the_destination_it_named(self):
        # Nothing said on the way, and the final message posted in the named place anyway.
        # Nothing between the notice and the report ever reaches a surface for a scheduled run,
        # so *quiet* is the ordinary condition here rather than an edge of one.
        self.a_gateway_running_one_targeted_schedule(
            channel="discord", channel_place_id="C0OPS")
        _began, reported = self.both_messages()
        self.assertEqual({"place": "C0OPS"}, reported["to"])
        self.assertEqual(2, len(self.of_a_schedule()),
                         f"a scheduled run said something other than its two messages: "
                         f"{self.of_a_schedule()}")


if __name__ == "__main__":
    unittest.main()
