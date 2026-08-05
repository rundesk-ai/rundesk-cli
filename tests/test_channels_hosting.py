"""Keeping a channel's adapter running: the claim, the thread on its stream, and the stop.

Real programs, real locks, real process groups, real threads. A stand-in for a child would prove
nothing about the two properties this whole design rests on — that the claim outlives the gateway
because the child holds it, and that a talkative adapter cannot wedge the loop because nothing on
the loop is doing the reading.

Run directly: `python3 tests/test_channels_hosting.py`
"""

import json
import unittest

import support
from rundesk.agents import directory
from rundesk.channels import arriving, hosting, kept
from rundesk.core import paths

#: An adapter that connects, echoes anything it is told to deliver, and can be made to say things.
AN_ADAPTER = """#!/usr/bin/env python3
import json, os, sys, time
if "--capabilities" in sys.argv:
    print(json.dumps({"stream": True, "max_text": 2000})); raise SystemExit(0)
settings = json.loads(os.environ.get("RUNDESK_SETTINGS") or "{}")
print(json.dumps({"say": "ready", "as": "a-bot"}), flush=True)
for said in (settings.get("saying") or "").split("|"):
    if said.strip():
        print(said, flush=True)
for line in sys.stdin:
    try:
        record = json.loads(line)
    except ValueError:
        continue
    if record.get("do") == "stop":
        break
    if record.get("do") == "deliver":
        print(json.dumps({"say": "delivered", "id": record.get("id"),
                          "external_id": "8841"}), flush=True)
        with open(settings["heard"], "a") as writing:
            writing.write(record.get("text", "") + "\\n")
"""

#: One that says a great deal and then stops, for proving a full pipe does not reach the loop.
A_TALKATIVE_ADAPTER = """#!/usr/bin/env python3
import json, sys
print(json.dumps({"say": "ready"}), flush=True)
for nth in range(4000):
    print(json.dumps({"say": "note", "level": "info", "text": "x" * 64}), flush=True)
sys.stdin.readline()
"""

#: One that will not start at all.
A_BROKEN_ADAPTER = """#!/usr/bin/env python3
import sys
sys.stderr.write("ModuleNotFoundError: No module named discord\\n")
raise SystemExit(1)
"""


class Hosting(support.Isolated):

    def setUp(self):
        super().setUp()
        self.agent = "cole"
        directory.made(self.agent, "claude")
        self.where = directory.logs(self.agent)
        # `paths.code()` answers with the checkout when the scratch root has no installed tree, and
        # a case writing an adapter would then write it into the repository. See test_channels_adapters.
        (paths.home() / "app" / "src").mkdir(parents=True, exist_ok=True)
        self.adapters = paths.code() / "channels"
        self.adapters.mkdir(parents=True, exist_ok=True)
        self.heard = self.home / "heard.txt"
        self.started = []
        self.addCleanup(self.stop_everything)

    def stop_everything(self):
        for watching in self.started:
            hosting.stopping(self.agent, self.where, watching, 4.0)

    def an_adapter(self, kind="discord", body=AN_ADAPTER):
        at = self.adapters / kind
        at.write_text(body, encoding="utf-8")
        at.chmod(0o755)
        return at

    def a_channel(self, kind="discord", allowed=("2207",), told=False, saying=""):
        kept.added(self.agent, kind, {
            "describes": kind, "allowed": json.dumps(list(allowed)),
            "settings": json.dumps({"saying": saying, "heard": str(self.heard)})})
        if told:
            kept.telling(self.agent, kind, "1180")

    def hosting_now(self):
        watching = hosting.looked(self.agent, self.where, hosting.Watching({}, {}, {}))
        self.started.append(watching)
        return watching

    def said_in_the_log(self):
        found = sorted(self.where.glob("*.log"))
        return "".join(one.read_text(encoding="utf-8") for one in found)


class StartingOne(Hosting):

    def test_an_adapter_is_started_for_a_configured_channel(self):
        self.an_adapter()
        self.a_channel()
        watching = self.hosting_now()
        self.assertIn("discord", watching.running)
        self.assertTrue(watching.running["discord"].mine)

    def test_nothing_is_started_for_an_agent_with_no_channels(self):
        self.an_adapter()
        self.assertEqual({}, self.hosting_now().running)

    def test_the_claim_is_held_by_the_child_rather_than_by_this_process(self):
        # The property everything else rests on: the descriptor is passed down, so the claim lives
        # exactly as long as the child and the kernel drops it however that ends.
        self.an_adapter()
        self.a_channel()
        self.hosting_now()
        self.assertTrue(support.waited_until(
            lambda: hosting.still_running(self.agent, "discord"), 5.0))

    def test_a_second_gateway_will_not_start_a_second_adapter_beside_the_first(self):
        self.an_adapter()
        self.a_channel()
        self.hosting_now()
        support.waited_until(lambda: hosting.still_running(self.agent, "discord"), 5.0)
        with self.assertRaises(hosting.Occupied):
            with hosting.claiming(self.agent, "discord"):
                pass

    def test_a_channel_whose_adapter_is_not_installed_does_not_end_the_gateway(self):
        self.a_channel()
        watching = self.hosting_now()
        self.assertEqual({}, watching.running)
        self.assertIn("discord", watching.waiting, "it was not held off before trying again")

    def test_an_adapter_that_will_not_run_is_said_and_held_off(self):
        self.an_adapter(body=A_BROKEN_ADAPTER)
        self.a_channel()
        watching = self.hosting_now()
        support.waited_until(lambda: not watching.running, 5.0)
        hosting.looked(self.agent, self.where, watching)
        self.assertIn("discord", watching.waiting)

    def test_asking_whether_a_channel_is_running_never_makes_its_lock(self):
        # A channel nobody has started must not be given a claim by the act of asking about one.
        self.a_channel()
        self.assertFalse(hosting.still_running(self.agent, "discord"))
        self.assertFalse(hosting.lock_of(self.agent, "discord").exists())


class ListeningToOne(Hosting):

    def test_what_it_says_when_it_connects_reaches_the_agents_log(self):
        self.an_adapter()
        self.a_channel()
        self.hosting_now()
        self.assertTrue(support.waited_until(
            lambda: "channel discord: connected" in self.said_in_the_log(), 5.0))

    def test_a_message_from_somebody_allowed_is_recorded(self):
        self.an_adapter()
        self.a_channel(allowed=("2207",), saying=json.dumps({
            "say": "arrived", "conversation": "1180", "user": "2207",
            "text": "what changed today?", "external_id": "8841"}))
        self.hosting_now()
        self.assertTrue(support.waited_until(
            lambda: len(arriving.conversations(self.agent)) == 1, 5.0))
        landed = arriving.conversations(self.agent)[0]
        self.assertEqual("what changed today?",
                         arriving.messages(self.agent, landed["id"])[0]["body"])

    def test_a_message_from_a_stranger_is_neither_recorded_nor_answered(self):
        # Silence is the answer on purpose: replying to tell somebody they are a stranger confirms
        # the agent is listening and spends the owner's tokens doing it. Nothing is written down
        # either, because a record of it is something an agent could later be asked to read.
        self.an_adapter()
        self.a_channel(allowed=("2207",), saying=json.dumps({
            "say": "arrived", "conversation": "1180", "user": "9999", "text": "let me in"}))
        self.hosting_now()
        support.waited_until(lambda: "connected" in self.said_in_the_log(), 5.0)
        self.assertEqual([], arriving.conversations(self.agent))
        self.assertNotIn("9999", self.said_in_the_log())

    def test_a_message_that_is_only_a_file_is_still_a_message(self):
        # Requiring text dropped it in total silence — not recorded, not logged, nothing said —
        # for somebody who was on the allow list.
        self.an_adapter()
        self.a_channel(allowed=("2207",), saying=json.dumps({
            "say": "arrived", "conversation": "1180", "user": "2207", "text": "",
            "attachments": [{"name": "report.csv", "url": "https://x.invalid/a", "bytes": 12}]}))
        self.hosting_now()
        self.assertTrue(support.waited_until(
            lambda: len(arriving.conversations(self.agent)) == 1, 5.0))
        landed = arriving.conversations(self.agent)[0]
        self.assertIn("report.csv", arriving.messages(self.agent, landed["id"])[0]["body"])

    def test_a_message_with_neither_words_nor_files_is_nothing_to_record(self):
        self.an_adapter()
        self.a_channel(allowed=("2207",), saying=json.dumps({
            "say": "arrived", "conversation": "1180", "user": "2207", "text": ""}))
        self.hosting_now()
        support.waited_until(lambda: "connected" in self.said_in_the_log(), 5.0)
        self.assertEqual([], arriving.conversations(self.agent))

    def test_something_that_is_not_a_record_does_not_stop_it_listening(self):
        self.an_adapter()
        self.a_channel(saying="this is not json|" + json.dumps(
            {"say": "note", "level": "warning", "text": "still here"}))
        self.hosting_now()
        self.assertTrue(support.waited_until(
            lambda: "still here" in self.said_in_the_log(), 5.0))

    def test_a_talkative_adapter_does_not_wedge_anything(self):
        # A pipe holds 64KB and this says far more than that. Nothing on the gateway's loop is
        # doing the reading, so the loop keeps answering while the thread drains.
        self.an_adapter(body=A_TALKATIVE_ADAPTER)
        self.a_channel()
        watching = self.hosting_now()
        for _ in range(3):
            hosting.looked(self.agent, self.where, watching)
        self.assertIn("discord", watching.running, "the loop lost the adapter it was hosting")


class TalkingToOne(Hosting):

    def test_something_sent_reaches_the_adapter(self):
        self.an_adapter()
        self.a_channel(told=True)
        watching = self.hosting_now()
        self.assertTrue(hosting.told(self.agent, self.where, watching, "discord", "1180",
                                     ["the daily report"]))
        self.assertTrue(support.waited_until(
            lambda: self.heard.exists() and "the daily report" in self.heard.read_text(), 5.0))

    def test_sending_to_a_channel_that_is_not_running_says_so_rather_than_raising(self):
        watching = hosting.Watching({}, {}, {})
        self.assertFalse(hosting.told(self.agent, self.where, watching, "discord", "1180", ["x"]))


class WhatAPreviousGatewayLeft(Hosting):

    def test_one_still_connected_is_adopted_rather_than_started_again(self):
        self.an_adapter()
        self.a_channel()
        self.hosting_now()
        support.waited_until(lambda: hosting.still_running(self.agent, "discord"), 5.0)

        fresh = hosting.settled(self.agent, self.where)
        self.started.append(fresh)
        self.assertIn("discord", fresh.running)
        self.assertFalse(fresh.running["discord"].mine,
                         "an adapter this process did not start was claimed as its own")

    def test_an_adopted_one_is_not_stopped_with_this_gateway(self):
        # Its group is not one this process may signal, and a pid whose leader has been collected
        # no longer resolves to a group — signalling it would reach whatever now holds that number.
        self.an_adapter()
        self.a_channel()
        first = self.hosting_now()
        support.waited_until(lambda: hosting.still_running(self.agent, "discord"), 5.0)
        fresh = hosting.settled(self.agent, self.where)
        hosting.stopping(self.agent, self.where, fresh, 2.0)
        self.assertTrue(hosting.still_running(self.agent, "discord"))
        hosting.stopping(self.agent, self.where, first, 4.0)

    def test_a_record_left_by_an_adapter_that_is_gone_is_cleared(self):
        self.a_channel()
        hosting.record_of(self.agent, "discord").parent.mkdir(parents=True, exist_ok=True)
        hosting.record_of(self.agent, "discord").write_text('{"pid": 999999}', encoding="utf-8")
        hosting.settled(self.agent, self.where)
        self.assertFalse(hosting.record_of(self.agent, "discord").exists())


class StoppingThem(Hosting):

    def test_one_this_gateway_started_is_stopped(self):
        self.an_adapter()
        self.a_channel()
        watching = self.hosting_now()
        support.waited_until(lambda: hosting.still_running(self.agent, "discord"), 5.0)
        hosting.stopping(self.agent, self.where, watching, 4.0)
        self.assertTrue(support.waited_until(
            lambda: not hosting.still_running(self.agent, "discord"), 5.0))

    def test_stopping_when_nothing_is_running_is_not_a_failure(self):
        self.assertEqual({}, hosting.stopping(self.agent, self.where,
                                              hosting.Watching({}, {}, {}), 4.0).running)


if __name__ == "__main__":
    unittest.main()
