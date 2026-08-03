"""Slack, as an agent is reached on it — every row of channel-slack.

**Nothing here reaches Slack.** What is tested is the policy: which messages are for this
agent and where the answer goes, what a mark means, how an answer too long for one message
is broken up, how ordinary Markdown becomes the dialect Slack renders, and what each of the
seam's records looks like once this surface has decided how to show it. The wire itself — a
socket, a rate limit, a permission — is what the canary against a private workspace is for,
and what a fake can never prove.

The adapter is loaded by path rather than imported as a module, because it is not one: it
is a program, which is the whole point of the seam. If `slack_sdk` is not installed the
whole file skips, since the adapter refuses to load without it and says so.

Run: python3 tests/test_slack.py
"""

from __future__ import annotations

import asyncio
import importlib.machinery
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _code_of(adapter: str) -> str:
    """One adapter with its prose taken out, for a case about what it *does*.

    Every docstring here names what this surface deliberately does not do, so a case that
    searched the whole file would be answered by the sentence explaining the absence.
    """
    import ast
    at = ROOT / "src" / "channels" / adapter
    tree = ast.parse(at.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)) and ast.get_docstring(node):
            node.body = node.body[1:] or [ast.Pass()]
    return ast.unparse(tree)
sys.path.insert(0, str(ROOT / "src"))

#: The install's own virtualenv, exactly as the adapter finds it.
for _packages in sorted((ROOT / ".venv" / "lib").glob("python3.*/site-packages")):
    sys.path.insert(0, str(_packages))

#: The seam itself, because which fields reach this surface is decided there and rendered
#: here — and a list kept in two places is a list that disagrees with itself (R-CH-13).
from rundesk import channel  # noqa: E402


def _adapter():
    """The adapter, loaded from its path — it is a program, not a module."""
    at = ROOT / "src" / "channels" / "slack"
    # **Asked before anything else, and on every machine.** Whether the file is there does
    # not depend on the dependency, so this is the one check that still fails where the
    # skip is legitimate — which is precisely where an adapter moving goes unnoticed: CI
    # runs with an empty virtualenv, so a suite that only noticed a missing adapter when
    # `slack_sdk` was installed would go on skipping there for ever.
    if not at.is_file():
        raise RuntimeError(
            f"test_slack cannot find the adapter it tests at {at} — this is not a skip")
    loader = importlib.machinery.SourceFileLoader("rundesk_slack", str(at))
    spec = importlib.util.spec_from_loader("rundesk_slack", loader)
    made = importlib.util.module_from_spec(spec)
    loader.exec_module(made)
    return made


#: Whether the one thing that may legitimately be missing is missing. **Asked of the
#: dependency itself, never inferred from how the adapter failed** — the adapter catches its
#: own absent import, says so as a record, and exits, so it never raises anything a caller
#: could tell apart from being broken.
try:  # pragma: no cover - the presence of a dependency is not a branch worth covering
    import slack_sdk as _installed
except ModuleNotFoundError:
    _installed = None

try:
    slack = _adapter()
except BaseException as why:  # pragma: no cover - proved by the install
    if _installed is None:
        slack = None
        WHY = "slack_sdk is not installed — run ./install.sh"
    else:
        # **Anything else is this suite being broken, and it must say so.** A skip and a
        # pass read identically, so the only defence is refusing to skip for a reason that
        # is not the one skipping is for.
        raise RuntimeError(
            f"test_slack cannot load the adapter it tests, which is not a skip: {why}"
        ) from why
else:
    WHY = ""

needs_slack = unittest.skipIf(slack is None, WHY or "slack_sdk is not installed")


# -- the fakes ---------------------------------------------------------------------------


class FakeSlack:
    """Slack's Web API, remembering what it was asked and answering what it was told to.

    Every method a real `WebClient` exposes that this adapter calls, and nothing else: a
    fake with a method the adapter never uses is a fake that would go on passing after the
    adapter stopped calling it.
    """

    def __init__(self, **answers):
        self.calls = []
        self.answers = {
            "auth_test": {"user_id": "UBOT", "bot_id": "BBOT", "user": "winston",
                          "team": "Acme", "team_id": "T1"},
            "chat_postMessage": {"ok": True, "ts": "1700.0001"},
            "chat_update": {"ok": True},
            "reactions_add": {"ok": True},
            "reactions_remove": {"ok": True},
            "conversations_open": {"channel": {"id": "D1"}},
            "conversations_replies": {"messages": []},
            "conversations_list": {"channels": []},
            "conversations_info": {"channel": {}},
            "users_info": {"user": {"profile": {"display_name": "Tim"}}},
            "files_upload_v2": {"ok": True},
        }
        self.answers.update(answers)
        self.refuse = {}

    def fail_next(self, method: str, why: str = "boom") -> None:
        """Make one call fail, so a refusal is a case rather than an accident."""
        self.refuse[method] = why

    def _record(self, method: str, **arguments):
        self.calls.append((method, arguments))
        if method in self.refuse:
            raise RuntimeError(self.refuse.pop(method))
        return self.answers[method]

    def __getattr__(self, method: str):
        if method.startswith("_") or method not in self.__dict__.get("answers", {}):
            answers = object.__getattribute__(self, "answers")
            if method not in answers:
                raise AttributeError(method)
        return lambda **arguments: self._record(method, **arguments)

    # Named explicitly as well, so a typo in the adapter is an AttributeError here rather
    # than a silently recorded call nobody made.
    def named(self, method: str):
        return [arguments for called, arguments in self.calls if called == method]


def an_agent(fake=None, **chose):
    """One adapter, wired to a fake and to nothing else."""
    settings = chose.pop("settings", {})
    allow = chose.pop("allow", "U1")
    argv = chose.pop("argv", [])
    said = slack.settled(slack.options(argv), settings, allow)
    for what, value in chose.items():
        setattr(said, what, value)
    client = slack.Agent(said, web=fake or FakeSlack())
    client.me, client.bot_id = "UBOT", "BBOT"
    client.team, client.team_id = "Acme", "T1"
    return client


def a_message(**event):
    """One `message` event, in the shape Socket Mode delivers it."""
    said = {"type": "message", "channel": "C1", "user": "U1", "text": "hello",
            "ts": "1700.0001"}
    said.update(event)
    return said


def a_command(**payload):
    """One slash command payload."""
    said = {"command": "/rundesk", "channel_id": "C1", "user_id": "U1", "text": "status",
            "trigger_id": "TR1", "response_url": "https://slack.test/respond"}
    said.update(payload)
    return said


def said_by(client, coroutine):
    """Run one thing, and collect every record the adapter wrote to stdout."""
    written = []
    real = slack.say
    slack.say = lambda **it: written.append(it)
    try:
        asyncio.run(coroutine)
    finally:
        slack.say = real
    return written


def privately(client):
    """Everything the adapter answered a command with, without an HTTP request."""
    answered = []

    async def instead(answer, said):
        answered.append((answer, said))

    client._privately = instead
    return answered


# -- who it answers ------------------------------------------------------------------------


@needs_slack
class WhoItAnswers(unittest.TestCase):
    """R-SLK-1 to R-SLK-4 — the five cases, and the two that are easy to get wrong."""

    def test_being_named_in_a_channel_puts_the_turn_in_a_thread(self):
        """R-SLK-1 — the turn happens in a thread under the message that named it, so one
        thread is one conversation and one session."""
        self.assertEqual("open-thread", slack.where_to_answer(
            direct=False, in_thread=False, ours=False, mentioned=True))

    def test_an_agent_stays_silent_in_a_shared_channel_until_it_is_named(self):
        """R-SLK-2 — an agent that answered everything said in a shared room would be
        answering conversations it was never part of."""
        self.assertEqual("ignore", slack.where_to_answer(
            direct=False, in_thread=False, ours=False, mentioned=False))

    def test_inside_a_thread_it_has_answered_in_it_answers_without_being_named(self):
        """R-SLK-3 — the thread *is* the conversation."""
        self.assertEqual("here", slack.where_to_answer(
            direct=False, in_thread=True, ours=True, mentioned=False))

    def test_it_does_not_answer_in_somebody_elses_thread_unless_named(self):
        """R-SLK-2, R-SLK-3 — a thread this agent has never spoken in is somebody else's
        conversation, and Slack threads fill with people who are not talking to a bot."""
        self.assertEqual("ignore", slack.where_to_answer(
            direct=False, in_thread=True, ours=False, mentioned=False))

    def test_named_inside_a_thread_it_answers_there_rather_than_starting_another(self):
        """R-SLK-1 — Slack threads do not nest, and an agent that tried would be posting
        into the channel behind everybody's back."""
        self.assertEqual("here", slack.where_to_answer(
            direct=False, in_thread=True, ours=False, mentioned=True))

    def test_in_a_one_to_one_conversation_it_answers_where_it_was_spoken_to(self):
        """R-SLK-4 — nobody else is there, and a thread in a direct message helps no
        one."""
        self.assertEqual("here", slack.where_to_answer(
            direct=True, in_thread=False, ours=False, mentioned=False))


@needs_slack
class WhereItListens(unittest.TestCase):
    """R-SLK-1, R-SLK-2, R-SLK-4 — the places an owner said this agent may be reached."""

    def test_a_thread_belongs_to_the_channel_it_is_in(self):
        """R-SLK-1 — a thread is asked about by its channel, never by its root timestamp:
        an owner confining an agent to one channel meant the conversations under it too."""
        self.assertTrue(slack.within(False, belongs_to="C1", listens_in="C1", dms=False))
        self.assertFalse(slack.within(False, belongs_to="C9", listens_in="C1", dms=False),
                         "a thread in another channel was answered in")

    def test_an_agent_confined_to_a_workspace_answers_anywhere_in_it(self):
        """R-SLK-2 — naming a workspace and no channel is a choice, not an omission."""
        self.assertTrue(slack.within(False, belongs_to="C9", listens_in=None, dms=False,
                                     a_workspace="T1"))

    def test_a_direct_message_channel_takes_only_direct_messages(self):
        """R-SLK-2, R-CAD-15 — one `add` makes one channel per kind of place, so the room
        has a channel of its own with its own allowed list. Both matching would mean the
        agent answers one message twice, from two processes, neither aware of the other."""
        self.assertFalse(slack.within(False, belongs_to="C9", listens_in=None, dms=True),
                         "the direct-message channel also took a message in a room")
        self.assertTrue(slack.within(True, belongs_to=None, listens_in=None, dms=True))

    def test_naming_a_channel_still_narrows_it_to_that_channel(self):
        """R-SLK-2 — the point of naming one is an agent in this room and not the next one
        along."""
        self.assertTrue(slack.within(False, belongs_to="C1", listens_in="C1", dms=False,
                                     a_workspace="T1"))
        self.assertFalse(slack.within(False, belongs_to="C9", listens_in="C1", dms=False,
                                      a_workspace="T1"))

    def test_a_direct_message_is_answered_only_when_that_is_what_was_asked_for(self):
        """R-SLK-4 — a channel pointed at a room is not also a channel for private
        messages."""
        self.assertTrue(slack.within(True, belongs_to=None, listens_in=None, dms=True))
        self.assertFalse(slack.within(True, belongs_to=None, listens_in="C1", dms=False))

    def test_a_direct_message_is_recognised_from_the_id_alone(self):
        """Slack names a direct message `D…`, and that is the one thing every payload
        carries — `channel_type` is absent on a slash command, so a check that needed it
        would have taken a command in a DM for one in a room."""
        self.assertTrue(slack._a_direct_message("D123"))
        self.assertFalse(slack._a_direct_message("C123"))
        self.assertFalse(slack._a_direct_message(""))


# -- what arrives --------------------------------------------------------------------------


@needs_slack
class WhatArrives(unittest.TestCase):
    """R-SLK-1 to R-SLK-4, R-SLK-21, R-SLK-34 — the `arrived` record and what is in it."""

    def _arrived(self, client, event):
        return [one for one in said_by(client, client.on_message(event))
                if one.get("type") == "arrived"]

    def test_a_named_message_in_a_channel_arrives_keyed_by_its_new_thread(self):
        """R-SLK-1 — the conversation is the channel and the message that named it, so the
        thread the answer goes into is one session of its own."""
        client = an_agent(dm=False)
        [said] = self._arrived(client, a_message(text="<@UBOT> what changed?"))
        self.assertEqual("C1:1700.0001", said["conversation"])
        self.assertEqual("1700.0001", said["ref"])
        self.assertFalse(said["direct"])
        self.assertEqual("what changed?", said["text"],
                         "our own naming was left in what the brain was asked")

    def test_a_direct_message_arrives_keyed_by_its_channel_and_is_never_threaded(self):
        """R-SLK-4 — a direct message is answered where it was spoken to, and a thread in
        one would put the reply somewhere the person has to go and find."""
        client = an_agent(dm=True)
        [said] = self._arrived(client, a_message(channel="D1", text="hello"))
        self.assertEqual("D1", said["conversation"])
        self.assertTrue(said["direct"])

    def test_an_unnamed_message_in_a_channel_arrives_at_nothing(self):
        """R-SLK-2 — silence in a shared channel until it is named."""
        client = an_agent(dm=False)
        self.assertEqual([], self._arrived(client, a_message(text="morning all")))

    def test_a_message_in_a_thread_it_has_answered_in_needs_no_naming(self):
        """R-SLK-3 — being named once opened the thread; naming it again in its own thread
        is a thing nobody would think to do."""
        fake = FakeSlack(conversations_replies={
            "messages": [{"user": "U1", "text": "start"}, {"user": "UBOT", "text": "hi"}]})
        client = an_agent(fake, dm=False)
        [said] = self._arrived(client, a_message(thread_ts="1699.0001", ts="1700.0002",
                                                 text="and the other thing"))
        self.assertEqual("C1:1699.0001", said["conversation"])

    def test_a_message_in_a_thread_it_has_never_answered_in_is_ignored(self):
        """R-SLK-2 — a thread full of people talking to each other is not this agent's."""
        fake = FakeSlack(conversations_replies={
            "messages": [{"user": "U1"}, {"user": "U2"}]})
        client = an_agent(fake, dm=False)
        self.assertEqual([], self._arrived(client, a_message(thread_ts="1699.0001",
                                                            ts="1700.0002",
                                                            text="just us")))

    def test_a_thread_is_asked_about_once_and_then_remembered(self):
        """A busy thread would otherwise cost one call per message — two, because the same
        fetch answers both whether the thread is ours and what its root said — for the
        whole life of a process that runs for weeks."""
        fake = FakeSlack(conversations_replies={
            "messages": [{"user": "U1"}, {"user": "UBOT"}]})
        client = an_agent(fake, dm=False)
        for nth in range(3):
            self._arrived(client, a_message(thread_ts="1699.0001", ts=f"1700.000{nth}",
                                            text="more"))
        self.assertEqual(1, len(fake.named("conversations_replies")),
                         "the thread was looked up again for a message in it")

    def test_a_message_from_this_bot_is_never_answered(self):
        """A bot answering its own message is a loop, and the only thing stopping one."""
        client = an_agent(dm=False)
        self.assertEqual([], self._arrived(client, a_message(user="UBOT",
                                                            text="<@UBOT> hi")))
        self.assertEqual([], self._arrived(client, a_message(bot_id="B9",
                                                            text="<@UBOT> hi")))

    def test_an_edit_or_a_join_notice_is_not_somebody_speaking(self):
        """Slack delivers both on the same event a message arrives on, and answering one
        is answering nothing."""
        client = an_agent(dm=False)
        for subtype in ("message_changed", "message_deleted", "channel_join"):
            self.assertEqual([], self._arrived(
                client, a_message(subtype=subtype, text="<@UBOT> hi")),
                f"{subtype} was taken for a message")

    def test_an_app_mention_is_not_taken_as_well_as_the_message(self):
        """A bot subscribed to `app_mention` and `message.channels` is told about one
        mention twice, and a turn run twice is a turn charged twice."""
        client = an_agent(dm=False)
        self.assertEqual([], self._arrived(
            client, a_message(type="app_mention", text="<@UBOT> hi")))

    def test_a_message_from_somebody_not_allowed_costs_nothing_at_all(self):
        """R-CAD-16 — whether they may be answered is rundesk's, and it still decides it.
        What this stops is *working* for them first: asking Slack about threads, pulling
        down what they attached, reacting where a room can see it."""
        fake = FakeSlack()
        client = an_agent(fake, dm=False)
        self.assertEqual([], self._arrived(
            client, a_message(user="USTRANGER", text="<@UBOT> hi",
                              thread_ts="1699.1", ts="1700.2")))
        self.assertEqual([], fake.calls, "Slack was called for somebody never answerable")

    def test_the_same_message_is_never_reported_twice(self):
        """Socket Mode redelivers what it was not acknowledged for, and a redelivery that
        reached the seam would run and bill the same turn again."""
        client = an_agent(dm=False)
        event = a_message(text="<@UBOT> once")
        self.assertEqual(1, len(self._arrived(client, event)))
        self.assertEqual([], self._arrived(client, event))

    def test_an_envelope_is_acknowledged_before_anything_else_happens(self):
        """R-SLK-11 — Slack allows three seconds and resends what it was not acknowledged
        for, so anything done before the acknowledgement is done again on the retry."""
        client = an_agent(dm=False)
        order = []

        class Socket:
            def send_socket_mode_response(self, response):
                order.append("acknowledged")

        client.socket, client.loop = Socket(), None
        client.envelope(_an_envelope("events_api", {"event": a_message()}))
        self.assertEqual(["acknowledged"], order)

    def test_an_envelope_already_handled_is_dropped(self):
        """The other half of the same guarantee: acknowledged twice is fine, acted on
        twice is not."""
        client = an_agent(dm=False)
        request = _an_envelope("events_api", {"event": a_message(text="<@UBOT> hi")})
        self.assertEqual(1, len(said_by(client, client.arrived(request))))
        self.assertEqual([], said_by(client, client.arrived(request)))

    def test_slack_says_which_room_and_which_person_a_message_came_from(self):
        """R-SLK-21 — an id told a brain nothing, so it answered a room of forty people in
        exactly the voice it used for a direct message."""
        client = an_agent(dm=False, rooms={"C1": "ops"})
        [said] = self._arrived(client, a_message(text="<@UBOT> what changed?"))
        self.assertEqual("the thread 'what changed?' under #ops in the Acme workspace",
                         said["where"])
        self.assertEqual("Tim", said["called"])
        self.assertEqual({"channel": "#ops", "workspace": "Acme",
                          "thread": "what changed?"}, said["parts"])

    def test_a_direct_message_is_named_as_one_rather_than_as_a_channel(self):
        """R-SLK-21 — a direct message has no room and no workspace worth naming, and
        saying `#D1` would name a thing nobody has ever seen written down."""
        client = an_agent(dm=True)
        [said] = self._arrived(client, a_message(channel="D1"))
        self.assertEqual("a direct message", said["where"])
        self.assertEqual({}, said["parts"])
        self.assertEqual("a direct message", said["channel_name"])
        self.assertEqual("", said["channel_parent_name"])

    def test_slack_maps_its_places_to_the_shared_channel_hierarchy(self):
        """R-SLK-21 — a workspace is a parent place and a thread is a nested conversation,
        neither of which teaches rundesk a Slack noun."""
        client = an_agent(dm=False, rooms={"C1": "ops"})
        [said] = self._arrived(client, a_message(text="<@UBOT> go"))
        self.assertEqual("ops", said["channel_name"])
        self.assertEqual("C1", said["channel_id"])
        self.assertEqual("Acme", said["channel_parent_name"])
        self.assertEqual("T1", said["channel_parent_id"])
        self.assertEqual("1700.0001", said["channel_thread_id"])

    def test_a_threaded_reply_carries_the_message_it_is_under(self):
        """R-SLK-34 — Slack has no reply reference of its own; being in a thread *is* the
        reference, so the parent is what a person reading it is oriented by."""
        fake = FakeSlack(conversations_replies={
            "messages": [{"user": "U2", "text": "Nightly report…"}, {"user": "UBOT"}]})
        client = an_agent(fake, dm=False)
        [said] = self._arrived(client, a_message(thread_ts="1699.1", ts="1700.2",
                                                 text="and this?"))
        self.assertEqual("1699.1", said["reply_to"]["id"])
        self.assertTrue(said["reply_to"]["resolved"])
        self.assertEqual("Nightly report…", said["reply_to"]["text"])

    def test_a_parent_that_cannot_be_fetched_still_reports_the_arrival(self):
        """R-SLK-34 — a thread whose root was deleted is still a thread somebody is
        talking in, and losing the message would be worse than losing the orientation."""
        fake = FakeSlack(conversations_replies={
            "messages": [{"user": "U1"}, {"user": "UBOT"}]})
        client = an_agent(fake, dm=False)

        async def nothing(*_a, **_k):
            return {"messages": []}

        client.call = nothing
        client.ours["C1:1699.1"] = True
        [said] = self._arrived(client, a_message(thread_ts="1699.1", ts="1700.2",
                                                 text="still here"))
        self.assertEqual({"id": "1699.1", "resolved": False}, said["reply_to"])

    def test_a_message_with_nothing_in_it_is_not_an_arrival(self):
        """A message needs words or something attached; an empty one is a notification
        that says nothing."""
        client = an_agent(dm=False)
        self.assertEqual([], self._arrived(client, a_message(text="<@UBOT>")))


def _an_envelope(kind, payload):
    class Envelope:
        def __init__(self):
            self.type, self.payload, self.envelope_id = kind, payload, "E1"
    return Envelope()


# -- files coming in --------------------------------------------------------------------


@needs_slack
class FilesComingIn(unittest.TestCase):
    """R-CH-17 — what somebody attached, on this machine, where the agent can read it."""

    def setUp(self):
        self.where = tempfile.TemporaryDirectory()
        self.addCleanup(self.where.cleanup)
        os.environ["RUNDESK_CHANNEL_HOME"] = self.where.name
        self.addCleanup(os.environ.pop, "RUNDESK_CHANNEL_HOME", None)

    def _fetch(self, client, files):
        return asyncio.run(client._fetch(a_message(files=files)))

    def test_a_file_is_brought_in_and_reported_by_its_own_name(self):
        client = an_agent(dm=True)
        client._download = lambda link, at: Path(at).write_bytes(b"hello")
        [one] = self._fetch(client, [{"name": "report.csv",
                                      "url_private_download": "https://slack.test/f"}])
        self.assertEqual("report.csv", one["name"])
        self.assertTrue(Path(one["at"]).is_absolute())
        self.assertEqual(b"hello", Path(one["at"]).read_bytes())

    def test_two_files_rebuilding_to_one_name_land_as_two_files(self):
        """R-CH-17 — `report v2.csv` and `report-v2.csv` rebuild identically, so the second
        was written over the first and the agent was handed two names that were one file."""
        client = an_agent(dm=True)
        client._download = lambda link, at: Path(at).write_bytes(b"x")
        brought = self._fetch(client, [
            {"name": "report v2.csv", "url_private_download": "https://slack.test/a"},
            {"name": "report-v2.csv", "url_private_download": "https://slack.test/b"}])
        self.assertEqual(2, len(brought))
        self.assertNotEqual(brought[0]["at"], brought[1]["at"])

    def test_a_filename_cannot_become_a_path(self):
        """A filename is somebody else's text, and it must not be able to leave the
        directory this message's attachments are put in."""
        client = an_agent(dm=True)
        client._download = lambda link, at: Path(at).write_bytes(b"x")
        [one] = self._fetch(client, [{"name": "../../etc/passwd",
                                      "url_private_download": "https://slack.test/f"}])
        self.assertIn("attachments", one["at"])
        self.assertNotIn("..", one["at"])

    def test_a_file_too_big_is_refused_and_the_others_still_arrive(self):
        client = an_agent(dm=True)
        client._download = lambda link, at: Path(at).write_bytes(b"x")
        brought = self._fetch(client, [
            {"name": "huge.bin", "size": slack.ATTACHED_BYTES + 1,
             "url_private_download": "https://slack.test/a"},
            {"name": "small.txt", "url_private_download": "https://slack.test/b"}])
        self.assertEqual(["small.txt"], [one["name"] for one in brought])

    def test_a_download_that_fails_does_not_lose_the_message(self):
        client = an_agent(dm=True)

        def refuse(link, at):
            raise OSError("no")

        client._download = refuse
        self.assertEqual([], self._fetch(client, [
            {"name": "a.txt", "url_private_download": "https://slack.test/a"}]))

    def test_no_more_than_this_channel_carries(self):
        """An agent's own directory is not somewhere anybody who can message it gets to
        fill."""
        client = an_agent(dm=True)
        client._download = lambda link, at: Path(at).write_bytes(b"x")
        brought = self._fetch(client, [
            {"name": f"f{nth}.txt", "url_private_download": "https://slack.test/f"}
            for nth in range(slack.ATTACHED_MOST + 5)])
        self.assertEqual(slack.ATTACHED_MOST, len(brought))


# -- what one turn looks like -------------------------------------------------------------


@needs_slack
class WhatOneTurnLooksLike(unittest.TestCase):
    """R-SLK-5, 7, 8, 9, 13, 17, 24, 28, 29, 31, 33, 40, 41 — a turn, as it is shown."""

    def _turn(self, fake=None, **chose):
        client = an_agent(fake or FakeSlack(), **chose)
        return client, client.web

    def _told(self, client, *records):
        async def all_of_them():
            for one in records:
                await client.told(one)
        return said_by(client, all_of_them())

    def test_a_message_taken_up_is_marked_as_seen(self):
        """R-SLK-5 — Slack has no typing indicator a bot may raise, so this mark is the
        whole of what says a turn is running."""
        client, fake = self._turn(dm=False)
        self._told(client, {"type": "state", "conversation": "C1:1700.1",
                            "state": "taken", "ref": "1700.1"})
        self.assertEqual([{"channel": "C1", "name": "eyes", "timestamp": "1700.1"}],
                         fake.named("reactions_add"))

    def test_how_it_ended_replaces_that_it_was_seen(self):
        """R-SLK-8 — leaving 👀 up beside ✅ says the opposite of what happened, and Slack
        has no replace, so it is an add and a remove in that order."""
        client, fake = self._turn(dm=False)
        self._told(client,
                   {"type": "state", "conversation": "C1:1700.1", "state": "taken",
                    "ref": "1700.1"},
                   {"type": "state", "conversation": "C1:1700.1", "state": "finished",
                    "ref": "1700.1"})
        self.assertEqual(["eyes", "white_check_mark"],
                         [one["name"] for one in fake.named("reactions_add")])
        self.assertEqual(["eyes"],
                         [one["name"] for one in fake.named("reactions_remove")])

    def test_a_running_turn_keeps_its_seen_mark_until_it_ends(self):
        """R-SLK-6 — Slack has no typing indicator a bot may renew, so the mark put on when
        the turn was taken is the whole of what says it is still going. Taking it off on
        `running` would leave a turn that looks like nothing happened for however long it
        runs."""
        client, fake = self._turn(dm=False)
        self._told(client,
                   {"type": "state", "conversation": "C1:1700.1", "state": "taken",
                    "ref": "1700.1"},
                   {"type": "state", "conversation": "C1:1700.1", "state": "running",
                    "ref": "1700.1"})
        self.assertEqual([], fake.named("reactions_remove"))
        self.assertEqual(["eyes"], [one["name"] for one in fake.named("reactions_add")])

    def test_a_remark_said_mid_turn_does_not_unmark_the_turn(self):
        """R-SLK-6 — the agent saying something on its way to an answer is not the answer,
        and a turn that lost its only running indicator halfway through would read as
        finished with nothing under it."""
        client, fake = self._turn(dm=False)
        self._told(client,
                   {"type": "state", "conversation": "C1:1700.1", "state": "taken",
                    "ref": "1700.1"},
                   {"type": "said", "conversation": "C1:1700.1", "text": "still going"})
        self.assertEqual([], fake.named("reactions_remove"))

    def test_every_state_the_seam_decides_has_something_to_show_for_it(self):
        """R-SLK-7 — the system decides which state a turn is in; this file decides only
        what each looks like, and a state with no mark would be a turn that vanished."""
        self.assertEqual({"finished", "stopped", "failed"}, set(slack.MARKS))
        self.assertEqual(3, len(set(slack.MARKS.values())),
                         "two states share a mark, so they cannot be told apart")

    def test_stopping_and_failing_are_not_the_same_mark(self):
        """R-SLK-9 — somebody stopping a turn and a turn falling over are different news."""
        self.assertNotEqual(slack.MARKS["stopped"], slack.MARKS["failed"])

    def test_a_turn_that_failed_says_what_failed(self):
        """R-SLK-9 — a ⚠️ with nothing under it is a turn nobody can act on."""
        client, fake = self._turn(dm=False)
        self._told(client, {"type": "state", "conversation": "C1:1700.1",
                            "state": "failed", "ref": "1700.1",
                            "why": "the provider exited 1"})
        self.assertIn("the provider exited 1",
                      fake.named("chat_postMessage")[0]["text"])

    def test_an_answer_that_fits_is_one_message(self):
        """R-SLK-13 — nothing is split that does not have to be."""
        client, fake = self._turn(dm=True)
        self._told(client, {"type": "answer", "conversation": "D1", "text": "short",
                            "provider": "claude"})
        self.assertEqual(1, len(fake.named("chat_postMessage")))

    def test_an_answer_too_long_is_broken_at_a_line_where_there_is_one(self):
        """R-SLK-13 — a break at a newline keeps a code block or a list readable."""
        first, rest = slack.split_at("a" * 100 + "\n" + "b" * 100, 150)
        self.assertEqual("a" * 100, first)
        self.assertEqual("b" * 100, rest)

    def test_an_answer_with_nowhere_to_break_is_cut_rather_than_dropped(self):
        """R-SLK-13 — a word that does not fit is still a word that has to go
        somewhere."""
        first, rest = slack.split_at("a" * 300, 100)
        self.assertEqual(100, len(first))
        self.assertEqual(200, len(rest))

    def test_nothing_is_lost_however_many_messages_it_takes(self):
        """R-SLK-13 — the one thing splitting must never do is lose a character."""
        whole, pieces = "x" * 9000, []
        rest = whole
        while rest:
            piece, rest = slack.split_at(rest, slack.LIMIT)
            pieces.append(piece)
        self.assertEqual(whole, "".join(pieces))

    def test_the_limit_is_under_what_slack_recommends(self):
        """R-SLK-13 — Slack recommends four thousand characters in a message's text, and
        splitting at a line break needs room to do it in."""
        self.assertLess(slack.LIMIT, 4000)

    def test_what_a_turn_cost_is_shown_as_one_line_above_the_answer(self):
        """R-SLK-17, R-SLK-33 — a long answer pushes anything after it off a phone screen,
        so which brain ran the turn and what it cost go above it."""
        client, fake = self._turn(dm=True)
        self._told(client,
                   {"type": "usage", "conversation": "D1", "input": 1200, "output": 340,
                    "cached": 8000},
                   {"type": "answer", "conversation": "D1", "text": "the answer",
                    "provider": "claude", "elapsed": 12})
        [wrote] = fake.named("chat_postMessage")
        stats, _, body = wrote["text"].partition("\n")
        self.assertTrue(stats.startswith("_") and stats.endswith("_"),
                        "the completion line is not in the quietest register Slack has")
        self.assertIn("claude", stats)
        self.assertIn("12s elapsed", stats)
        self.assertEqual("the answer", body)

    def test_the_footer_leads_with_how_big_the_conversation_is(self):
        """R-SLK-29 — a footer is read to decide one thing, whether to start a fresh
        conversation, and none of the billed quantities answers it."""
        self.assertEqual("· 9.2k session · 340 output", slack._as_a_line(
            {"type": "usage", "session": 9200, "output": 340, "input": 2, "cached": 8000}))

    def test_a_brain_that_reports_no_conversation_size_gets_what_it_always_got(self):
        """R-SLK-29 — absent means "could not tell", on either side."""
        self.assertEqual("· 1.2k input · 340 output · 8k cached", slack._as_a_line(
            {"type": "usage", "input": 1200, "output": 340, "cached": 8000}))

    def test_a_turn_that_reported_no_cost_still_says_how_long_it_took(self):
        """R-SLK-24 — the clock is this adapter's, and a turn with no usage is still a turn
        somebody waited for."""
        client, fake = self._turn(dm=True)
        self._told(client, {"type": "answer", "conversation": "D1", "text": "done",
                            "provider": "codex", "elapsed": 95})
        self.assertIn("_codex · 1m elapsed_", fake.named("chat_postMessage")[0]["text"])

    def test_elapsed_time_runs_from_taken_and_a_repeat_does_not_restart_it(self):
        """R-SLK-24 — a repeated `taken` would otherwise reset a measurement that had
        already begun."""
        ticks = iter([100.0, 101.0, 130.0])
        held = slack.Live(clock=lambda: next(ticks))
        self.assertIsNone(held.started)
        held.started = held.clock()
        self.assertEqual(100.0, held.started)

    def test_a_small_count_is_not_rounded_into_a_zero(self):
        """R-SLK-17 — a turn that answered in thirteen tokens reporting `0k output` is a
        measurement, stated plainly, and wrong."""
        self.assertEqual("13", slack._amount(13))
        self.assertEqual("1.2k", slack._amount(1200))
        self.assertEqual("15.4M", slack._amount(15425000))

    def test_an_answer_names_who_asked_in_a_room_and_nobody_in_a_direct_message(self):
        """R-SLK-31, R-SLK-40 — the tint picks one message out of a busy room; a direct
        message has one human in it and every message in it is already theirs."""
        client, fake = self._turn(dm=False)
        self._told(client, {"type": "answer", "conversation": "C1:1700.1",
                            "text": "there", "provider": "claude", "user": "U1"})
        self.assertIn("<@U1>", fake.named("chat_postMessage")[0]["text"])

        client, fake = self._turn(dm=True)
        self._told(client, {"type": "answer", "conversation": "D1", "text": "there",
                            "provider": "claude", "user": "U1"})
        self.assertNotIn("<@U1>", fake.named("chat_postMessage")[0]["text"])

    def test_a_name_written_into_an_answer_stands_under_the_completion_line(self):
        """R-SLK-41 — the completion line is the one line meant to sit quietly out of the
        way, and a mention in front of it makes it the loudest thing in the message."""
        said = slack._mentioning("U1", "_claude · 3s elapsed_\nthe answer")
        self.assertTrue(said.startswith("_claude · 3s elapsed_\n<@U1> "))

    def test_only_the_first_piece_of_a_split_answer_names_anybody(self):
        """R-SLK-31 — five notifications for one reply is four too many."""
        client, fake = self._turn(dm=False)
        self._told(client, {"type": "answer", "conversation": "C1:1700.1", "user": "U1",
                            "text": "y" * (slack.LIMIT + 200), "provider": "claude"})
        wrote = [one["text"] for one in fake.named("chat_postMessage")]
        self.assertEqual(2, len(wrote))
        self.assertEqual(1, sum("<@U1>" in one for one in wrote))

    def test_a_remark_said_mid_turn_names_nobody(self):
        """R-SLK-31 — a surface where everything is tinted has tinted nothing."""
        client, fake = self._turn(dm=False)
        self._told(client, {"type": "said", "conversation": "C1:1700.1",
                            "text": "I'll look at the logs.", "user": "U1"})
        self.assertNotIn("<@U1>", fake.named("chat_postMessage")[0]["text"])

    def test_an_answer_is_written_into_the_thread_the_turn_is_in(self):
        """R-SLK-28 — the answer belongs under the question, which on Slack is the thread
        rather than a quote."""
        client, fake = self._turn(dm=False)
        self._told(client, {"type": "answer", "conversation": "C1:1700.1", "text": "so",
                            "provider": "claude"})
        self.assertEqual("1700.1", fake.named("chat_postMessage")[0]["thread_ts"])

    def test_an_answer_in_a_direct_message_starts_no_thread(self):
        """R-SLK-4 — a thread in a one-to-one conversation puts the reply somewhere the
        person has to go and find."""
        client, fake = self._turn(dm=True)
        self._told(client, {"type": "answer", "conversation": "D1", "text": "so",
                            "provider": "claude"})
        self.assertNotIn("thread_ts", fake.named("chat_postMessage")[0])

    def test_a_terminal_notice_does_not_erase_a_newer_running_turn(self):
        """R-SLK-35 — an unattended run's presentation is kept apart from a person's."""
        client, fake = self._turn(dm=False)
        self._told(client, {"type": "state", "conversation": "C1:1700.1",
                            "state": "taken", "ref": "1700.1"})
        running = client.live["C1:1700.1"]
        self._told(client, {"type": "said", "conversation": "C1:1700.1",
                            "schedule": "nightly", "text": "done", "began": False})
        self.assertIs(running, client.live.get("C1:1700.1"),
                      "a schedule's notice threw away a person's running turn")


# -- showing the work ---------------------------------------------------------------------


@needs_slack
class ShowingTheWork(unittest.TestCase):
    """R-SLK-20 — broad activity, compactly, and only what the seam's vocabulary allows."""

    def test_every_verb_the_seam_defines_has_a_mark_and_a_word(self):
        """A verb with no mark would silently show as the fallback, so this is checked
        against the seam rather than trusted to stay in step with it."""
        verbs = set(channel.TOOL_VERBS) if hasattr(channel, "TOOL_VERBS") else {
            "read", "search", "run", "edit", "list", "make", "delegate",
            "memory", "rules", "identity"}
        self.assertEqual(verbs, set(slack.DID), "a verb has no mark on this surface")
        self.assertEqual(verbs, set(slack.SHOWN), "a verb has no words on this surface")
        self.assertEqual(verbs, set(slack.FAILED), "a verb has no failure wording")

    def test_the_three_continuity_verbs_are_marked_apart_from_editing(self):
        """R-PRV-29 — a file the agent was working on and a file the agent lives by are the
        same pencil and different news."""
        for what in ("memory", "rules", "identity"):
            self.assertNotEqual(slack.DID["edit"], slack.DID[what])

    def test_an_unknown_tool_uses_thinking_instead_of_a_vendors_name(self):
        """A brain that gave no verb is doing something this vocabulary has no word for
        yet, and its own identifier is not a translation of that."""
        self.assertEqual("💭 thinking", slack._as_a_line(
            {"type": "tool", "name": "commandExecution"}))

    def test_a_tools_own_name_is_never_shown(self):
        """One vendor's identifiers in front of somebody who has never heard of that
        vendor is a vocabulary this file would carry forever."""
        said = slack._as_a_line({"type": "tool", "did": "run", "name": "Bash"})
        self.assertNotIn("Bash", said)
        self.assertIn("ran command", said)

    def test_a_tool_failure_never_publishes_its_private_details(self):
        """R-SLK-9, R-SLK-20 — a command or a path may be private, and the run's own
        account is where the detail stays."""
        said = slack._activity_line(
            {"type": "result", "id": "1", "ok": False,
             "summary": "cat /etc/shadow: permission denied"}, {"1": {"did": "run"}})
        self.assertEqual("⚠ command failed", said)
        self.assertNotIn("shadow", said)

    def test_consecutive_activity_is_one_line_with_a_count(self):
        """R-SLK-20 — eleven lines saying the agent read a file is worse than one saying it
        read eleven."""
        grouped = slack._group_activity([], ["📖 read file"] * 3)
        self.assertEqual("📖 read file *(x3)*", slack._render_activity(grouped))

    def test_only_consecutive_activity_is_counted(self):
        """R-SLK-20 — a count that jumped over something else would be a count of a thing
        that did not happen."""
        grouped = slack._group_activity([], ["📖 read file", "💻 ran command",
                                             "📖 read file"])
        self.assertEqual("📖 read file\n💻 ran command\n📖 read file",
                         slack._render_activity(grouped))

    def test_an_intervening_message_breaks_a_count(self):
        """R-SLK-20 — something else was said in between, so the next line starts a new
        count rather than joining one across it."""
        grouped = slack._group_activity([], ["📖 read file", None, "📖 read file"])
        self.assertEqual([("📖 read file", 1), ("📖 read file", 1)], grouped)

    def test_a_subagent_start_and_finish_are_two_broad_categories(self):
        """R-SLK-20 — handing work over and getting it back are different news."""
        tools = {}
        started = slack._activity_line(
            {"type": "tool", "id": "1", "did": "delegate", "who": "researcher"}, tools)
        finished = slack._activity_line({"type": "result", "id": "1", "ok": True}, tools)
        self.assertIn("delegated to subagent", started)
        self.assertIn("subagent finished", finished)

    def test_a_safe_subagent_name_is_shown_without_its_provider_path(self):
        """A label somebody wrote as an absolute path must not be posted with every
        component of it still readable."""
        said = slack._activity_line(
            {"type": "tool", "id": "1", "did": "delegate",
             "who": "/opt/secret/place/researcher"}, {})
        self.assertIn("researcher", said)
        self.assertNotIn("/opt", said)

    def test_named_subagents_still_collapse_as_one_broad_category(self):
        """Names are useful on one helper; listing every name defeats compact counting."""
        lines = ["🤖 delegated to subagent: a", "🤖 delegated to subagent: b"]
        self.assertEqual([("🤖 delegated to subagent", 2)],
                         slack._group_activity([], lines))

    def test_thinking_is_a_broad_category_and_never_the_thought_itself(self):
        """What the agent was thinking is not this surface's to publish."""
        said = slack._as_a_line({"type": "think", "text": "The error is in the parser."})
        self.assertEqual("💭 thinking", said)
        self.assertNotIn("parser", said)

    def test_a_long_commentary_keeps_the_newest_and_says_it_dropped_the_rest(self):
        """Slack refuses a message past its own limit, and a turn that ran fifty tools
        would otherwise write one that cannot be sent at all."""
        groups = [(f"💻 ran command {nth}", 1) for nth in range(400)]
        shown, kept = slack._bounded_activity(groups)
        self.assertLessEqual(len(shown), slack.ACTIVITY_CHARS + 8)
        self.assertTrue(shown.startswith("…\n"), "nothing said that lines were dropped")
        self.assertIn("399", shown, "the newest line was the one dropped")

    def test_showing_the_work_is_off_when_the_owner_turned_it_off(self):
        """R-SLK-20 — rundesk owns the decision and this file obeys it."""
        client = an_agent(FakeSlack(), dm=True, activity=slack.OFF)
        held = slack.Live()
        asyncio.run(client._doing({"type": "tool", "conversation": "D1", "did": "run"},
                                  held))
        self.assertEqual([], held.pending)

    def test_what_a_turn_cost_is_kept_even_when_the_work_is_not_shown(self):
        """R-SLK-17 — the cost goes above the answer whatever else is shown."""
        client = an_agent(FakeSlack(), dm=True, activity=slack.OFF)
        held = slack.Live()
        asyncio.run(client._doing(
            {"type": "usage", "conversation": "D1", "output": 340}, held))
        self.assertIn("340 output", held.cost)


# -- Slack's dialect ------------------------------------------------------------------------


@needs_slack
class TheDialectProseIsIn(unittest.TestCase):
    """Slack's `mrkdwn` is not Markdown, and an agent writes Markdown."""

    def test_bold_and_italics_are_slacks_and_not_markdowns(self):
        self.assertEqual("*bold* and _italic_", slack.to_mrkdwn("**bold** and *italic*"))

    def test_bold_is_not_read_back_as_italic(self):
        """Slack spells bold with the one asterisk Markdown spells italic with, so a rule
        that converted bold first and italic second read its own output back."""
        self.assertEqual("*bold*", slack.to_mrkdwn("**bold**"))
        self.assertEqual("*bold*", slack.to_mrkdwn("__bold__"))

    def test_a_link_is_written_the_way_slack_writes_one(self):
        self.assertEqual("<https://x|the docs>",
                         slack.to_mrkdwn("[the docs](https://x)"))

    def test_a_heading_becomes_bold_because_slack_has_none(self):
        """A line beginning with a hash renders as a literal hash, which reads as noise
        rather than as structure."""
        self.assertEqual("*What changed*", slack.to_mrkdwn("## What changed"))

    def test_nothing_inside_a_fenced_code_block_is_touched(self):
        """A shell line full of asterisks is not emphasis, and rewriting one is rewriting
        the thing somebody asked for."""
        said = slack.to_mrkdwn("```\nrm -rf **/*.pyc\n[a](b)\n```")
        self.assertIn("rm -rf **/*.pyc", said)
        self.assertIn("[a](b)", said)

    def test_nothing_inside_inline_code_is_touched(self):
        self.assertEqual("`a**b`", slack.to_mrkdwn("`a**b`"))

    def test_arithmetic_is_not_mistaken_for_emphasis(self):
        self.assertEqual("2*3*4", slack.to_mrkdwn("2*3*4"))

    def test_an_answer_reaches_slack_in_slacks_dialect(self):
        """The whole point: what the brain wrote is what a person reads."""
        client = an_agent(FakeSlack(), dm=True)
        said_by(client, client.told({"type": "answer", "conversation": "D1",
                                     "text": "**done** — see [here](https://x)",
                                     "provider": "claude"}))
        wrote = client.web.named("chat_postMessage")[0]["text"]
        self.assertIn("*done*", wrote)
        self.assertIn("<https://x|here>", wrote)
        self.assertNotIn("**", wrote)

    def test_slacks_reserved_characters_are_escaped_wherever_they_appear(self):
        """R-SLK-45 — `<…>` is Slack's own syntax for a link, a mention and a broadcast,
        and it is read as that in a fence and in inline code as much as in prose. So an
        ordinary answer carrying a generic, a comparison or a shell redirect arrived with
        the angle-bracketed part eaten."""
        self.assertEqual("Map&lt;string, int&gt;", slack.to_mrkdwn("Map<string, int>"))
        self.assertEqual("a &amp;&amp; b", slack.to_mrkdwn("a && b"))
        # A fence is not a shelter: Slack reads its reserved characters inside one too.
        self.assertEqual("```\nif (a &lt; b) {}\n```",
                         slack.to_mrkdwn("```\nif (a < b) {}\n```"))
        self.assertEqual("`List&lt;int&gt;`", slack.to_mrkdwn("`List<int>`"))

    def test_a_broadcast_an_agent_only_mentioned_does_not_notify_the_room(self):
        """R-SLK-45 — the one that is worse than garbled. An agent quoting Slack's own
        syntax, or reporting a string it found, sent a notification to everybody in the
        room; nothing in the turn asked for it and nobody there could tell."""
        for shouting in ("<!channel>", "<!here>", "<!everyone>"):
            said = slack.to_mrkdwn(f"the log line was {shouting}")
            self.assertNotIn(shouting, said, "an answer addressed the whole room")
            self.assertIn("&lt;!", said)

    def test_what_the_translation_builds_is_not_escaped_a_second_time(self):
        """R-SLK-45 — escaping is done on the way *in*, because everything the translation
        builds is ours: a link Slack must read as a link, with the ampersand inside its
        own URL still escaped the way Slack asks for."""
        said = slack.to_mrkdwn("see [docs](https://x.com/a?b=1&c=2)")
        self.assertEqual("see <https://x.com/a?b=1&amp;c=2|docs>", said)
        client = an_agent(FakeSlack(), dm=True)
        said_by(client, client.told({"type": "answer", "conversation": "D1",
                                     "text": "use Map<string, int>", "provider": "claude"}))
        wrote = client.web.named("chat_postMessage")[0]["text"]
        self.assertIn("Map&lt;string, int&gt;", wrote)
        # The mention this adapter writes itself is Slack's syntax and stays intact.
        self.assertNotIn("&lt;@", wrote)


# -- Slack's own commands -------------------------------------------------------------------


@needs_slack
class SlacksOwnCommands(unittest.TestCase):
    """R-SLK-10, R-SLK-11, R-SLK-12, R-SLK-22, R-SLK-23, R-SLK-25."""

    def _ran(self, client, text, **payload):
        """One command, typed where this adapter is configured to hear it."""
        payload.setdefault("channel_id", "D1" if client.chose.dm else "C1")
        answered = privately(client)
        said = said_by(client, client.on_command(a_command(text=text, **payload)))
        return said, answered

    def test_every_word_it_offers_is_a_gesture_the_seam_defines(self):
        """R-SLK-10 — a command that did something the seam has no word for would be this
        surface inventing a gesture."""
        self.assertEqual({"stop", "forget", "restart"},
                         {control for _n, _d, control, _s in slack.CONTROL_WORDS})
        self.assertLessEqual({query for _n, _d, query in slack.QUERY_WORDS},
                             {"status", "version", "agents", "help", "skills",
                              "schedules", "roles"})

    def test_every_word_is_described_where_it_is_offered(self):
        """R-SLK-10 — a command nobody can discover is a command nobody uses."""
        for name, describes, _control, _ack in slack.CONTROL_WORDS:
            self.assertTrue(describes.strip(), f"{name} is offered without a description")
        for name, describes, _query in slack.QUERY_WORDS:
            self.assertTrue(describes.strip(), f"{name} is offered without a description")

    def test_it_is_one_command_and_not_one_per_gesture(self):
        """A slash command name is unique across a Slack workspace and the last app to
        register one wins it, so eleven names would take `/stop` from every other app and
        stop two Rundesk agents sharing a workspace."""
        client = an_agent(FakeSlack(), dm=True)
        self.assertEqual("/rundesk", client.chose.command)

    def test_a_new_session_and_stopping_a_turn_are_different_gestures(self):
        """R-SLK-10 — forgetting where a conversation got to is not stopping the turn
        running in it."""
        client = an_agent(FakeSlack(), dm=True)
        [said], _ = self._ran(client, "stop")
        self.assertEqual("stop", said["control"])
        [said], _ = self._ran(client, "new")
        self.assertEqual("forget", said["control"])

    def test_a_control_is_acknowledged_and_never_answered_with_the_turn(self):
        """R-SLK-12 — answering a stop by publishing what the turn had written so far is
        how a half-finished sentence gets posted as though it were the reply."""
        client = an_agent(FakeSlack(), dm=True)
        [said], answered = self._ran(client, "stop")
        self.assertEqual("control", said["type"])
        self.assertEqual(1, len(answered))
        self.assertIn("stopping", answered[0][1])

    def test_a_read_only_question_is_reported_for_authorization_and_held(self):
        """R-SLK-22 — rundesk authorizes it and answers; this file only correlates."""
        client = an_agent(FakeSlack(), dm=True)
        [said], answered = self._ran(client, "status")
        self.assertEqual("query", said["type"])
        self.assertEqual("status", said["query"])
        self.assertEqual("TR1", said["ref"])
        self.assertEqual([], answered, "a question was answered before rundesk had")
        self.assertIn("TR1", client.asked)

    def test_a_gateway_answer_completes_the_exact_command_that_asked(self):
        """R-SLK-22 — and privately, because gateway information is the owner's."""
        client = an_agent(FakeSlack(), dm=True)
        answered = privately(client)
        said_by(client, client.on_command(a_command(text="status", channel_id="D1")))
        said_by(client, client.told({"type": "query-result", "conversation": "D1",
                                     "query": "status", "ref": "TR1",
                                     "text": "winston: RUNNING"}))
        self.assertEqual([("https://slack.test/respond", "winston: RUNNING")], answered)
        self.assertNotIn("TR1", client.asked, "the correlation outlived its answer")

    def test_a_question_from_somebody_not_allowed_is_refused_before_it_is_reported(self):
        """Advisory only — rundesk checks again — but a command that hung for ever for
        somebody rundesk will correctly answer with silence is a command that looks
        broken."""
        client = an_agent(FakeSlack(), dm=True, allow="U1")
        said, answered = self._ran(client, "status", user_id="USTRANGER")
        self.assertEqual([], said)
        self.assertIn("not available to you", answered[0][1])

    def test_an_unknown_word_is_answered_with_what_it_knows_and_reported_as_nothing(self):
        """R-SLK-22 — turning a typed word into an argument is how a read-only surface
        becomes a command runner."""
        client = an_agent(FakeSlack(), dm=True)
        said, answered = self._ran(client, "rm -rf /")
        self.assertEqual([], said)
        self.assertIn("understands", answered[0][1])

    def test_one_command_belongs_to_exactly_one_configured_surface(self):
        """R-SLK-23 — one bot may have a direct-message channel and a room channel
        connected together, and Slack delivers the command to both."""
        rooms = an_agent(FakeSlack(), dm=False, channel="C1")
        dms = an_agent(FakeSlack(), dm=True)
        in_a_room = a_command(channel_id="C1", text="stop")
        self.assertEqual(1, len(said_by(rooms, rooms.on_command(dict(in_a_room)))))
        self.assertEqual([], said_by(dms, dms.on_command(dict(in_a_room))))

    def test_a_provider_change_is_offered_only_on_a_single_user_channel(self):
        """R-SLK-25 — membership in a shared room is not agent administration."""
        shared = an_agent(FakeSlack(), dm=False, allow="U1,U2")
        answered = privately(shared)
        said = said_by(shared, shared.on_command(a_command(text="provider claude",
                                                           channel_id="C1")))
        self.assertEqual([], said)
        self.assertIn("not available to you", answered[0][1])

    def test_a_provider_change_is_reported_and_never_decided_here(self):
        """R-SLK-25 — this file reports what was typed; rundesk proves the adapter runs,
        changes the default and forgets the sessions, in one transaction."""
        client = an_agent(FakeSlack(), dm=True, allow="U1")
        [said], _ = self._ran(client, "provider claude")
        self.assertEqual("configure", said["type"])
        self.assertEqual("claude", said["provider"])

    def test_a_provider_change_result_completes_the_private_command(self):
        """R-SLK-25 — and privately, for the same reason the question was."""
        client = an_agent(FakeSlack(), dm=True, allow="U1")
        answered = privately(client)
        said_by(client, client.on_command(a_command(text="provider claude",
                                                   channel_id="D1")))
        said_by(client, client.told({"type": "configure-result", "conversation": "D1",
                                     "ref": "TR1",
                                     "text": "Default provider changed to claude."}))
        self.assertIn("changed to claude", answered[-1][1])

    def test_a_command_named_for_another_app_is_not_ours(self):
        """An owner who renamed this agent's command has said which one is theirs."""
        client = an_agent(FakeSlack(), dm=True, argv=["--command", "winston"])
        self.assertEqual("/winston", client.chose.command)
        self.assertEqual([], said_by(client, client.on_command(
            a_command(command="/other", text="stop", channel_id="D1"))))


# -- notices, schedules and named places ----------------------------------------------------


@needs_slack
class NoticesAndSchedules(unittest.TestCase):
    """R-SLK-15, R-SLK-30, R-SLK-38, R-SLK-39, and a room nobody has spoken in yet."""

    def test_a_notice_for_the_owner_reaches_them_and_starts_no_conversation(self):
        """R-SLK-38 — rundesk's own bookkeeping about the agent, for the owner alone."""
        client = an_agent(FakeSlack(), dm=True, allow="U1,U2")
        said_by(client, client.told({"type": "owner-notice", "text": "🧩 Skill added"}))
        self.assertEqual([{"users": "U1"}], client.web.named("conversations_open"))
        self.assertEqual("D1", client.web.named("chat_postMessage")[0]["channel"])

    def test_a_notice_naming_somebody_is_carried_to_that_person(self):
        """R-SLK-39 — an introduction is for the person who has just arrived."""
        client = an_agent(FakeSlack(), dm=True, allow="U1,U2")
        said_by(client, client.told({"type": "owner-notice", "text": "Hello",
                                     "user": "U2"}))
        self.assertEqual([{"users": "U2"}], client.web.named("conversations_open"))

    def test_a_notice_naming_somebody_this_channel_does_not_allow_is_refused(self):
        """R-SLK-39 — a bot that would message any id it was handed is one bug away from
        messaging a stranger."""
        client = an_agent(FakeSlack(), dm=True, allow="U1")
        said_by(client, client.told({"type": "owner-notice", "text": "Hello",
                                     "user": "USTRANGER"}))
        self.assertEqual([], client.web.named("conversations_open"))

    def test_a_notice_too_long_for_one_message_is_split(self):
        """R-SLK-13 — a catalog removal takes away every skill it brought at once."""
        client = an_agent(FakeSlack(), dm=True, allow="U1")
        said_by(client, client.told({"type": "owner-notice",
                                     "text": "z" * (slack.LIMIT + 100)}))
        self.assertEqual(2, len(client.web.named("chat_postMessage")))

    def test_a_notice_with_nothing_in_it_is_not_sent(self):
        client = an_agent(FakeSlack(), dm=True, allow="U1")
        said_by(client, client.told({"type": "owner-notice", "text": ""}))
        self.assertEqual([], client.web.named("chat_postMessage"))

    def test_a_scheduled_report_is_a_reply_to_the_message_that_said_it_started(self):
        """R-SLK-30 — an owner scrolling a busy conversation sees an outcome attached to
        the thing that started it rather than floating loose."""
        client = an_agent(FakeSlack(), dm=True)
        said_by(client, client.told(
            {"type": "said", "conversation": "D1", "schedule": "nightly", "began": True,
             "text": "💻 Working on 'nightly'…"}))
        said_by(client, client.told(
            {"type": "said", "conversation": "D1", "schedule": "nightly",
             "text": "Nothing broke overnight."}))
        wrote = client.web.named("chat_postMessage")
        self.assertEqual(2, len(wrote))
        self.assertNotIn("thread_ts", wrote[0])
        self.assertEqual("1700.0001", wrote[1]["thread_ts"])

    def test_a_report_for_a_schedule_nobody_announced_quotes_nothing(self):
        """R-SLK-30 — a name nothing is held for is posted plainly, which is what every
        scheduled report did before there were notices."""
        client = an_agent(FakeSlack(), dm=True)
        said_by(client, client.told(
            {"type": "said", "conversation": "D1", "schedule": "nightly",
             "text": "Nothing broke."}))
        self.assertNotIn("thread_ts", client.web.named("chat_postMessage")[0])

    def test_an_ordinary_remark_quotes_nothing(self):
        """R-SLK-30 — quoting the question on every remark buries the question."""
        client = an_agent(FakeSlack(), dm=True)
        said_by(client, client.told({"type": "said", "conversation": "D1",
                                     "text": "I'll look at the logs."}))
        self.assertNotIn("thread_ts", client.web.named("chat_postMessage")[0])

    def test_a_notice_that_could_not_be_posted_is_not_held(self):
        """R-SLK-30 — otherwise the next report replies into nothing."""
        fake = FakeSlack()
        fake.fail_next("chat_postMessage")
        client = an_agent(fake, dm=True)
        said_by(client, client.told(
            {"type": "said", "conversation": "D1", "schedule": "nightly", "began": True,
             "text": "starting"}))
        self.assertNotIn("nightly", client.started)

    def test_a_place_named_by_word_is_resolved_to_a_room(self):
        """R-CAD-16 — a place is the only way to reach a room nobody has spoken in yet,
        because rundesk has no conversation for one."""
        client = an_agent(FakeSlack(), dm=False, rooms={"C9": "operations"})
        found, why = asyncio.run(client._room_named("#operations"))
        self.assertEqual("C9", found)
        self.assertIsNone(why)

    def test_a_place_is_matched_with_or_without_its_hash_and_whatever_the_case(self):
        """The hash is how Slack writes a channel and is not part of the name."""
        self.assertTrue(slack.room_matches("#Operations", "operations"))
        self.assertTrue(slack.room_matches("operations", "operations"))
        self.assertFalse(slack.room_matches("ops", "operations"))

    def test_a_room_channel_never_opens_a_private_message_for_a_person(self):
        """R-CAD-16 — a schedule must not message somebody because an id failed as a
        room."""
        client = an_agent(FakeSlack(), dm=False, allow="U1")
        found, why = asyncio.run(client._room_named("U1"))
        self.assertIsNone(found)
        self.assertIn("writes in rooms", why)

    def test_a_direct_message_place_naming_a_stranger_is_declined_and_said(self):
        """R-CAD-16 — and a refusal must not read like a typo, or an owner goes hunting
        for a wrong id."""
        client = an_agent(FakeSlack(), dm=True, allow="U1")
        found, why = asyncio.run(client._room_named("USTRANGER"))
        self.assertIsNone(found)
        self.assertIn("allowed list", why)

    def test_a_direct_message_place_naming_an_allowed_person_opens_one(self):
        client = an_agent(FakeSlack(), dm=True, allow="U1")
        found, _why = asyncio.run(client._room_named("U1"))
        self.assertEqual("D1", found)


# -- files going out ---------------------------------------------------------------------


@needs_slack
class FilesGoingOut(unittest.TestCase):
    """R-SLK-18, R-SLK-19 — what the agent made, uploaded rather than described."""

    def setUp(self):
        self.where = tempfile.TemporaryDirectory()
        self.addCleanup(self.where.cleanup)
        # macOS puts a temporary directory under `/var`, which is itself a symlink — and
        # refusing a symlink in every component is exactly what the reader under test does.
        self.at = Path(self.where.name).resolve()

    def _made(self, body=b"chart"):
        import hashlib
        at = self.at / "chart.png"
        at.write_bytes(body)
        return {"name": "chart.png", "at": str(at), "bytes": len(body),
                "sha256": hashlib.sha256(body).hexdigest()}

    def test_a_file_the_agent_made_is_uploaded(self):
        """R-SLK-19 — the image inline, not a path in prose the reader cannot open."""
        client = an_agent(FakeSlack(), dm=True)
        said_by(client, client.told({"type": "answer", "conversation": "D1",
                                     "text": "here it is", "provider": "claude",
                                     "attachments": [self._made()]}))
        [uploaded] = client.web.named("files_upload_v2")
        self.assertEqual("chart.png", uploaded["filename"])
        self.assertEqual(b"chart", uploaded["content"])

    def test_a_file_whose_digest_does_not_match_is_dropped_and_the_answer_arrives(self):
        """A concurrent turn replacing an approved file between the check and the send is
        exactly what verifying the snapshot exists to stop."""
        client = an_agent(FakeSlack(), dm=True)
        declared = self._made()
        declared["sha256"] = "0" * 64
        said_by(client, client.told({"type": "answer", "conversation": "D1",
                                     "text": "here", "provider": "claude",
                                     "attachments": [declared]}))
        self.assertEqual([], client.web.named("files_upload_v2"))
        self.assertEqual(1, len(client.web.named("chat_postMessage")))

    def test_a_file_whose_size_does_not_match_is_dropped(self):
        declared = self._made()
        declared["bytes"] = 999
        self.assertIsNone(slack._outbound_attachment(declared))

    def test_a_relative_path_is_never_opened(self):
        self.assertIsNone(slack._outbound_attachment(
            {"name": "x", "at": "chart.png", "bytes": 5, "sha256": "0" * 64}))

    def test_a_symlink_in_any_component_is_refused(self):
        """Refusing the traversal is what stops a parent directory being swapped for one
        that points somewhere else between the check and the read."""
        import hashlib
        real = self.at / "real.txt"
        real.write_bytes(b"x")
        link = self.at / "link.txt"
        link.symlink_to(real)
        self.assertIsNone(slack._outbound_attachment(
            {"name": "link.txt", "at": str(link), "bytes": 1,
             "sha256": hashlib.sha256(b"x").hexdigest()}))

    def test_an_answer_too_long_to_read_as_messages_is_attached_instead(self):
        """R-SLK-18 — past a certain length an answer is a document, and a dozen numbered
        fragments is not something anybody reads."""
        client = an_agent(FakeSlack(), dm=False)
        said_by(client, client.told(
            {"type": "answer", "conversation": "C1:1700.1", "user": "U1",
             "text": "y" * (slack.LIMIT * slack.ATTACH_AFTER + 10), "provider": "claude"}))
        [uploaded] = client.web.named("files_upload_v2")
        self.assertEqual("answer.md", uploaded["filename"])
        [covering] = client.web.named("chat_postMessage")
        self.assertIn("<@U1>", covering["text"],
                      "an answer attached as a file named nobody")


# -- what an owner configured ---------------------------------------------------------------


@needs_slack
class WhatAnOwnerConfigured(unittest.TestCase):
    """R-CAD-9, R-CAD-11, R-CAD-12, R-CAD-15 — `--check`, and what is written down."""

    def test_an_owner_who_said_nothing_gets_the_shipped_defaults(self):
        """A function of its arguments and nothing else, so what an owner ends up with can
        be read by a case rather than by opening a socket."""
        said = slack.settled(slack.options([]), {}, "U1")
        self.assertEqual(slack.GROWS, said.activity)
        self.assertEqual("/rundesk", said.command)
        self.assertEqual(slack.BOT_TOKEN_FROM, said.token_from)
        self.assertEqual(slack.APP_TOKEN_FROM, said.app_token_from)
        self.assertEqual(["U1"], said.allow)

    def test_a_stale_activity_off_in_a_record_does_not_silence_the_channel(self):
        """Rundesk owns whether commentary is shown and already withholds every activity
        record when the channel switch is off. A second `off` kept here would leave records
        saying the channel is on while the adapter silently drops every line."""
        said = slack.settled(slack.options([]), {"activity": slack.OFF}, "U1")
        self.assertEqual(slack.GROWS, said.activity)

    def test_a_command_written_without_its_slash_still_works(self):
        said = slack.settled(slack.options(["--command", "winston"]), {}, "U1")
        self.assertEqual("/winston", said.command)

    def test_nothing_said_means_both_kinds_of_place(self):
        """R-CAD-15 — a bot is reachable in both, and asking an owner which they meant is
        asking them to say something this can find out for itself."""
        self.assertEqual((True, True), slack.wanted(slack.options([])))

    def test_naming_direct_messages_leaves_the_rooms_out(self):
        self.assertEqual((True, False), slack.wanted(slack.options(["--dm"])))

    def test_naming_a_room_leaves_direct_messages_out(self):
        self.assertEqual((False, True), slack.wanted(slack.options(["--channel", "C1"])))
        self.assertEqual((False, True),
                         slack.wanted(slack.options(["--workspace", "T1"])))

    def test_the_settings_of_one_shape_say_nothing_about_the_other(self):
        """R-CAD-15 — the direct-message channel is told nothing about a room, so it cannot
        drift into answering in one, and neither can be widened by editing the other."""
        chose = slack.settled(slack.options([]), {}, "U1")
        dms = slack._shape(chose, slack.DMS, "direct messages", dm=True)
        rooms = slack._shape(chose, slack.ROOMS, "#ops", channel="C1")
        self.assertNotIn("channel", dms["settings"])
        self.assertNotIn("dm", rooms["settings"])

    def test_no_credential_is_ever_written_into_the_settings(self):
        """R-CAD-12 — the record is a file that outlives this process."""
        chose = slack.settled(slack.options([]), {}, "U1")
        chose.bot_token = "xoxb-secret"
        shape = slack._shape(chose, slack.DMS, "direct messages", dm=True)
        self.assertNotIn("xoxb-secret", json.dumps(shape))
        for value in shape["settings"].values():
            self.assertNotIn("xoxb", str(value))

    def test_both_credentials_are_named_and_only_named(self):
        """R-CAD-11 — Slack opens its socket with one credential and calls its API with
        another, and the seam normalises a list precisely so a surface like this one can be
        reached at all."""
        answered = _checked([])
        self.assertFalse(answered["ok"])
        self.assertEqual([slack.BOT_TOKEN_FROM, slack.APP_TOKEN_FROM],
                         answered["secret"]["env"])
        self.assertEqual({"env": [slack.BOT_TOKEN_FROM, slack.APP_TOKEN_FROM],
                          "files": [slack.BOT_TOKEN_FILE, slack.APP_TOKEN_FILE]},
                         channel.named(answered["secret"]),
                         "the seam does not carry both names this adapter needs")

    def test_both_credentials_have_a_file_to_be_taken_into(self):
        """R-CAD-11 — a credential is taken and kept for an owner who has not placed it,
        and a surface needing two needs two files. `channels add` writes what the adapter
        named; naming nothing meant rundesk wrote one file however many were needed, and
        the app-level token was left for the owner to place by hand — which is a channel
        that proved itself at the terminal and cannot sign in at start-up."""
        named = channel.named(_checked([])["secret"])
        self.assertEqual([slack.BOT_TOKEN_FILE, slack.APP_TOKEN_FILE], named["files"],
                         "the app-level token has nowhere to be taken into")
        self.assertEqual(len(named["env"]), len(named["files"]),
                         "a credential was named with no file, or the other way round")
        # The files it says rundesk should write are the files it reads back itself.
        self.assertEqual([slack.BOT_TOKEN_FILE, slack.APP_TOKEN_FILE],
                         named["files"], "it reads one place and asks to be given another")

    def test_an_option_it_does_not_understand_is_refused_by_name(self):
        """R-CAD-9 — a misconfigured channel must be found while somebody is standing at a
        terminal."""
        answered = _checked(["--nonsense"], bot="x", app="y")
        self.assertFalse(answered["ok"])
        self.assertIn("--nonsense", answered["why"])

    def test_a_considered_refusal_still_exits_zero(self):
        """R-CAD-9 — what is read is the answer, not the code; a program that dies without
        printing one failed rather than refused, and an owner is shown the difference."""
        self.assertEqual(0, _check_code([]))

    def test_the_fills_a_shape_declares_are_the_ones_an_owner_may_write(self):
        """R-CAD-15 — declared so a misspelt one is refused when it is written rather than
        left quietly blank."""
        self.assertEqual((), slack.FILLS[slack.DMS])
        self.assertEqual(("channel", "workspace", "thread"), slack.FILLS[slack.ROOMS])


def _run_check(argv, bot="", app=""):
    """Run `--check` with whatever credentials are set, and collect what it printed."""
    written, code = [], None
    real = slack.say
    slack.say = lambda **it: written.append(it)
    kept = {name: os.environ.get(name) for name in
            (slack.BOT_TOKEN_FROM, slack.APP_TOKEN_FROM, "RUNDESK_CHANNEL_HOME")}
    try:
        with tempfile.TemporaryDirectory() as empty:
            os.environ["RUNDESK_CHANNEL_HOME"] = empty
            for name, value in ((slack.BOT_TOKEN_FROM, bot), (slack.APP_TOKEN_FROM, app)):
                if value:
                    os.environ[name] = value
                else:
                    os.environ.pop(name, None)
            chose = slack.settled(slack.options(argv), {}, "U1")
            code = asyncio.run(slack.check(chose))
    finally:
        slack.say = real
        for name, value in kept.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
    return written, code


def _checked(argv, bot="", app=""):
    written, _code = _run_check(argv, bot, app)
    return written[0]


def _check_code(argv, bot="", app=""):
    _written, code = _run_check(argv, bot, app)
    return code


# -- coming up and going down ----------------------------------------------------------------


@needs_slack
class ComingUpAndGoingDown(unittest.TestCase):
    """R-SLK-15, R-SLK-16, R-SLK-26, R-SLK-27."""

    def setUp(self):
        self.home = tempfile.TemporaryDirectory()
        self.addCleanup(self.home.cleanup)
        os.environ["RUNDESK_HOME"] = self.home.name
        os.environ["RUNDESK_GATEWAY"] = "g1"
        self.addCleanup(os.environ.pop, "RUNDESK_HOME", None)
        self.addCleanup(os.environ.pop, "RUNDESK_GATEWAY", None)

    def test_the_owner_is_told_once_however_many_adapters_a_gateway_runs(self):
        """R-SLK-15 — an agent reachable both by direct message and in rooms runs two of
        these, and two greetings a minute apart read as a restart in between."""
        first, second = an_agent(FakeSlack(), dm=True), an_agent(FakeSlack(), dm=False)
        said_by(first, first.opened())
        said_by(second, second.opened())
        self.assertEqual(1, len(first.web.named("chat_postMessage")))
        self.assertEqual(0, len(second.web.named("chat_postMessage")))

    def test_the_record_goes_out_every_time_even_when_the_message_does_not(self):
        """R-SLK-15 — `ready` is how a quiet agent is told from a deaf one, and it is not
        the same claim as "the gateway came up"."""
        client = an_agent(FakeSlack(), dm=True)
        first = said_by(client, client.opened())
        second = said_by(client, client.opened())
        self.assertEqual([{"type": "ready"}], first)
        self.assertEqual([{"type": "ready"}], second)
        self.assertEqual(1, len(client.web.named("chat_postMessage")))

    def test_an_ordinary_startup_adds_no_update_wording_and_no_release_link(self):
        """R-SLK-27 — a reconnection is not a release, and a version offered here would
        read as one having just been installed."""
        client = an_agent(FakeSlack(), dm=True)
        said_by(client, client.opened())
        [wrote] = client.web.named("chat_postMessage")
        self.assertIn("Gateway online", wrote["text"])
        self.assertNotIn("update", wrote["text"])

    def test_a_gateway_returning_from_an_update_links_the_version_now_listening(self):
        """R-SLK-26 — the only place an owner is certain to be told which release is now
        listening, and the only one that can link it."""
        marker = Path(self.home.name) / "maintenance"
        marker.write_text("x")
        os.environ["RUNDESK_MAINTENANCE"] = str(marker)
        os.environ["RUNDESK_VERSION"] = "0.33.0"
        os.environ["RUNDESK_RELEASE_URL"] = "https://example.test/v0.33.0"
        self.addCleanup(os.environ.pop, "RUNDESK_MAINTENANCE", None)
        self.addCleanup(os.environ.pop, "RUNDESK_VERSION", None)
        self.addCleanup(os.environ.pop, "RUNDESK_RELEASE_URL", None)
        client = an_agent(FakeSlack(), dm=True)
        said_by(client, client.opened())
        [wrote] = client.web.named("chat_postMessage")
        self.assertIn("I'm back", wrote["text"])
        self.assertIn("<https://example.test/v0.33.0|v0.33.0>", wrote["text"])
        self.assertFalse(marker.exists(), "the maintenance marker outlived the notice")

    def test_a_gateway_told_only_a_version_still_names_it(self):
        """R-SLK-26 — an install with no release URL says the version in plain text rather
        than saying nothing at all."""
        os.environ["RUNDESK_VERSION"] = "0.33.0"
        os.environ.pop("RUNDESK_RELEASE_URL", None)
        self.addCleanup(os.environ.pop, "RUNDESK_VERSION", None)
        self.assertEqual("v0.33.0", slack._running_release())

    def test_the_goodbye_is_said_before_the_socket_closes(self):
        """R-SLK-15, R-SLK-16 — an owner who cannot be reached must not cost the clean
        close, and the bot going on showing as active after the gateway has gone is what a
        dropped socket looks like."""
        order = []

        class Socket:
            def close(self):
                order.append("closed")

        client = an_agent(FakeSlack(), dm=True)
        client.socket = Socket()
        real = client._tell_the_owner

        async def watched(said, who=None):
            order.append("told")
            await real(said, who)

        client._tell_the_owner = watched
        asyncio.run(client.going())
        self.assertEqual(["told", "closed"], order)

    def test_presence_is_not_something_this_file_sets(self):
        """R-SLK-16 — `users.setPresence` is a user-token method; a bot follows its socket,
        which is this program's own lifetime. A call here could only ever fail."""
        self.assertNotIn("users_setPresence", _code_of("slack"))

    def test_no_typing_indicator_is_attempted(self):
        """Slack has no generic typing indicator for a bot, and the one that exists forces
        the Agents/AI Apps thread-only UI onto every conversation. Declared, not
        attempted."""
        self.assertNotIn("assistant_threads_setStatus", _code_of("slack"))


# -- what this file must not do ---------------------------------------------------------------


@needs_slack
class TheSeamHoldsBothWays(unittest.TestCase):
    """R-CAD-13 — everything about this platform is in that file, and nothing else."""

    def test_the_adapter_imports_nothing_from_rundesk(self):
        """A channel is a program rundesk runs, never code it loads — and an adapter that
        imported the core would be the seam failing quietly."""
        code = _code_of("slack")
        self.assertNotIn("from rundesk", code)
        self.assertNotIn("import rundesk", code)

    def test_nothing_in_rundesk_names_this_adapter(self):
        """The other half: adding a surface is writing a program against a published
        contract rather than extending a core."""
        for at in (ROOT / "src" / "rundesk").rglob("*.py"):
            source = at.read_text(encoding="utf-8")
            for line in source.splitlines():
                if "slack" in line.lower() and not line.lstrip().startswith(("#", '"', "'")):
                    self.assertNotIn("channels/slack", line,
                                     f"{at.name} reaches into the Slack adapter")

    def test_the_adapter_is_a_program_and_not_a_module(self):
        at = ROOT / "src" / "channels" / "slack"
        self.assertTrue(os.access(at, os.X_OK), "the adapter is not executable")
        self.assertTrue(at.read_text(encoding="utf-8").startswith("#!/usr/bin/env python3"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
