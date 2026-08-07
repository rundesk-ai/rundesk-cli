"""What answers a message, and what starts a scheduled turn — end to end, through both seams.

**Real programs on both sides.** A real channel adapter announces a message on its way up and is
handed the answer back down its own pipe; a real provider adapter takes the turn in between. Nothing
here stands in for either, because what is being proved is that two layers that may not import each
other meet correctly in the middle — and a stand-in for either end would prove only that this file
agrees with itself.

The three things that go wrong if this is not written down:

**A turn must not run on the thread reading a channel.** That thread cannot fall behind: a turn takes
minutes, and running one inline stops the channel reading anything for the length of it, including
the next message and including a `stop`. So `answer` returns at once and the case waits for the work
rather than for the call.

**A person waiting must never get silence.** A turn that failed still reaches them, in words that say
whether waiting will help — which is the whole point of a closed vocabulary reaching a surface that
has never heard of a vendor.

**A scheduled turn must not land in the exchange somebody types into.** It gets a conversation of its
own, keyed by the schedule's name; the build this replaces resumed the owner's own session and left
its prompt and its answer in the middle of it.

Run directly: `python3 tests/test_providers_answering.py`
"""

import contextlib
import json
import threading
import time
import unittest
from pathlib import Path

import support
from rundesk.agents import directory, records
from rundesk.channels import arriving, delivery, hosting
from rundesk.channels import hosting as answering_hosting
from rundesk.channels import kept as channels_kept
from rundesk.core import paths
from rundesk.providers import answering, kept, turns
from rundesk.schedules import kept as schedules_kept
from rundesk.utils import programs

#: How long a case waits for a real turn to finish on its own thread. A ceiling rather than a sleep,
#: so an ordinary run is through in tenths.
PATIENCE = 30.0

#: How long a case waits to be sure something is **not** going to happen.
#:
#: **Kept apart from `PATIENCE`, because a negative spends its ceiling in full every single time.**
#: `PATIENCE` is generous precisely because it is never reached; used to prove an absence it is
#: reached always, and one case proving a stranger started no turn cost thirty seconds of every run
#: of this suite — eleven per cent of the whole test wall clock, for one assertion.
#:
#: Twenty times what the positive cases beside it take, which is the margin that matters: they are
#: the measure of how long a turn takes to start when it is going to, and they settle in tenths.
NOT_GOING_TO_HAPPEN = 2.0

#: How long a case waits for a turn it started to be over before saying so out loud.
#:
#: **A turn is a thread, and where things are is one variable for the whole process.** Every location
#: this product reads is derived from `RUNDESK_HOME` on every call and cached nowhere, so a turn still
#: running after its case has ended does not go on writing into that case's root — it writes into
#: whatever root is current by then. That is the next case's scratch directory, or, in the moment
#: between one case putting the variable back and the next one setting it, **the owner's live
#: install**.
#:
#: Both have happened. `~/.rundesk/data/agents/cole/conversations/1/stderr.log` was written on a
#: developer's machine by this suite, through `providers.adapters.talking_to`, which makes the
#: directory a turn's error log stands in. And on CI the same `conversations/` directory appeared
#: under the *next* case's `data/agents/cole` between `directory.taken` saying the name was free and
#: the rename that lands the agent — so a staged agent was renamed onto a directory that was no
#: longer empty, and the case failed in `setUp` with `ENOTEMPTY` having never run.
#:
#: Generous, because it is never reached: a case that ends its own turn is through in hundredths, and
#: the longest any case here deliberately leaves running is a few seconds.
A_TURN_TO_END = 15.0

#: A channel adapter that announces one message on its way up and writes down everything rundesk
#: says back to it. **Everything, whole and unread** — half of what this file proves is what goes
#: *out* through that pipe: the four marks a turn puts on a message, and the answer.
AN_ADAPTER = """#!/usr/bin/env python3
import json, os, sys
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
    with open(settings["told"], "a") as writing:
        writing.write(line if line.endswith("\\n") else line + "\\n")
    if record.get("do") == "stop":
        break
    if record.get("do") == "deliver":
        # A platform that will not take the words answers the delivery just as surely as one that
        # does, and the two are told apart here and nowhere else.
        if settings.get("refuse"):
            print(json.dumps({"say": "failed", "id": record.get("id"),
                              "why": settings["refuse"]}), flush=True)
        else:
            print(json.dumps({"say": "delivered", "id": record.get("id"),
                              "external_id": "8841"}), flush=True)
"""


class Answering(support.Isolated):

    def setUp(self):
        super().setUp()
        self.agent = "cole"
        directory.made(self.agent, support.A_STAND_IN)
        self.where = directory.logs(self.agent)
        # `paths.code()` answers with the checkout when the scratch root has no installed tree, and
        # a case writing an adapter would then write it into the repository somebody is working in.
        (paths.home() / "app" / "src").mkdir(parents=True, exist_ok=True)
        self.adapters = paths.code() / "channels"
        self.adapters.mkdir(parents=True, exist_ok=True)
        self.told = self.home / "told.txt"
        self.watching = []
        self.pids = []
        # Read after the root is set and before the case can start anything, so what is running now
        # belongs to whoever started it and only what appears after this is this case's to end.
        self.already_running = set(threading.enumerate())
        self.addCleanup(self.stop_everything)

    def stop_everything(self):
        """End what this case started — by pid and by thread — however the case ended.

        Registered last, so it runs first: cleanups unwind in reverse, and every one after this puts
        the scratch root back or takes it away. Nothing of this case's may still be running by then.
        """
        for watching in self.watching:
            with contextlib.suppress(Exception):
                hosting.stopping(self.agent, self.where, watching, 4.0)
        for pid in self.pids:
            with contextlib.suppress(OSError):
                programs.stop(pid, gently_for=0.2, firmly_for=2.0)
        self.assert_nothing_this_case_started_outlives_it()

    def still_running(self):
        """Every thread this case started that has not finished."""
        return [one for one in threading.enumerate()
                if one not in self.already_running and one.is_alive()]

    def assert_nothing_this_case_started_outlives_it(self):
        """Wait for this case's own threads, and fail rather than let one reach the next root.

        **A turn returns before it has finished, on purpose** — that is what `OnAChannel.answer`
        guarantees and what one case here proves — so a case that asserts on the first thing a turn
        writes is over while the turn is still going. The thread is a daemon and nothing joins it.
        `A_TURN_TO_END` says what that costs: the next case's root, or the owner's own install.
        Stopping the adapters above is not enough, because a turn outlives the channel it came in on.

        **Failed rather than waited out quietly.** A thread that is still running here has already
        been given every reason to stop; letting the case pass would hand the next one a root that
        something else is writing into, and that failure lands on the wrong case with nothing in it
        pointing here.
        """
        ceiling = time.monotonic() + A_TURN_TO_END
        for one in self.still_running():
            one.join(max(0.0, ceiling - time.monotonic()))
        left = sorted(one.name for one in self.still_running())
        self.assertEqual([], left, "this case left something running, and every location rundesk "
                                   "reads is about to point somewhere else")

    def a_channel(self, saying="", allowed=("2207",), refuse=""):
        at = self.adapters / "discord"
        at.write_text(AN_ADAPTER, encoding="utf-8")
        at.chmod(0o755)
        channels_kept.added(self.agent, "discord", {
            "describes": "discord", "allowed": json.dumps(list(allowed)),
            "settings": json.dumps({"saying": saying, "told": str(self.told),
                                    "refuse": refuse})})

    def a_message_arrived(self, text="what changed today?", **also):
        said = {"say": "arrived", "conversation": "1180", "user": "2207",
                "text": text, "external_id": "8841"}
        said.update(also)
        return json.dumps(said)

    def hosting_now(self):
        """One pass of the gateway's loop, with the real thing that answers handed in."""
        watching = hosting.Watching({}, {}, {})
        answers = answering.OnAChannel(self.where, lambda: watching)
        hosting.looked(self.agent, self.where, watching, answering=answers)
        self.watching.append(watching)
        self.pids.extend(one.pid for one in watching.running.values() if one.pid)
        return watching

    def what_it_was_told(self):
        """Every record rundesk wrote to the adapter, as objects, oldest first."""
        if not self.told.exists():
            return []
        return [json.loads(line) for line in self.told.read_text(encoding="utf-8").splitlines()
                if line.strip()]

    def waited_until(self, whether, patience=PATIENCE):
        """Wait for something to become true, up to a ceiling.

        The ceiling is an argument because **proving an absence spends it in full**: a case waiting
        for something that is never going to happen wants `NOT_GOING_TO_HAPPEN`, not the generous
        one that costs nothing only because it is never reached.
        """
        return support.waited_until(whether, patience)

    def waited_for_a_turn(self, which=1):
        """Wait until this many turns have settled, then hand back the last of them."""
        def settled():
            there = kept.list_turns(self.agent)
            return len(there) >= which and all(one["ended_at"] for one in there)
        self.assertTrue(settled() or self.waited_until(settled), "no turn settled")
        return kept.list_turns(self.agent)[0]

    def marks(self):
        """The words rundesk put on the message, in the order it put them."""
        return [one.get("state") for one in self.what_it_was_told() if one.get("do") == "state"]

    def delivered(self):
        return [one.get("text") for one in self.what_it_was_told() if one.get("do") == "deliver"]

    def activity(self):
        """Every broad line the surface was shown while the turn was still running."""
        return [one for one in self.what_it_was_told() if one.get("do") == "activity"]

    def a_turn_is_running(self):
        """Whether a turn holds the claim in the channel's conversation. Looked up each time: the
        conversation does not exist until the first message in it has been written down."""
        found = arriving.standing_in(self.agent, "1180")
        return found is not None and turns.busy(self.agent, found)


class AMessageOnAChannelIsAnswered(Answering):

    def test_the_turn_runs_and_the_answer_goes_back_down_the_same_pipe(self):
        self.a_channel(saying=self.a_message_arrived())
        self.hosting_now()
        self.waited_for_a_turn()
        self.assertTrue(self.waited_until(lambda: self.delivered()),
                        "nothing was ever delivered to the channel")
        self.assertIn("what changed today?", " ".join(self.delivered()))

    def test_it_says_working_first_and_exactly_one_settled_word_after(self):
        """The four words `hosting` renders and never names. **`providers` owns them**, so a
        surface and the records cannot disagree about what happened to one run."""
        self.a_channel(saying=self.a_message_arrived())
        self.hosting_now()
        self.waited_for_a_turn()
        self.assertTrue(self.waited_until(lambda: answering.DONE in self.marks()))
        said = self.marks()
        self.assertEqual(answering.WORKING, said[said.index(answering.WORKING)])
        self.assertLess(said.index(answering.WORKING), said.index(answering.DONE))
        self.assertEqual(1, len([one for one in said if one in (answering.DONE,
                                                                answering.STOPPED,
                                                                answering.FAILED)]))

    def test_an_answer_the_platform_refused_is_never_marked_done(self):
        """**The mark says what a person can see, not what a brain managed.**

        A turn can succeed and its answer still reach nobody: a bot invited before a permission was
        asked for, a locked thread, a channel deleted mid-turn. The words were written to the pipe,
        the adapter said the platform would not take them, and that refusal reached one `WARNING`
        line and nothing else — so the mark was composed from the turn's own outcome and the
        question wore ✅ with the answer existing nowhere a person could reach.

        A brain that answered perfectly well is deliberately used here, so that what is being proved
        is the delivery and not the turn.
        """
        self.a_channel(saying=self.a_message_arrived(), refuse="Forbidden")
        self.hosting_now()
        self.waited_for_a_turn()
        self.assertTrue(self.waited_until(lambda: self.delivered()),
                        "nothing was ever delivered to the channel")
        settled = (answering.DONE, answering.STOPPED, answering.FAILED)
        self.assertTrue(self.waited_until(lambda: any(one in settled for one in self.marks())),
                        "the turn never settled on a mark")
        said = [one for one in self.marks() if one in settled]
        self.assertEqual([answering.FAILED], said,
                         "a refused delivery left the question marked as though it was answered")

    def test_a_turn_whose_answer_landed_is_still_marked_done(self):
        """The other half of the one above, and the reason it is a pair.

        A guard that reads a refusal out of silence would mark every turn failed on any adapter that
        acknowledges nothing — which the contract allows and calls a whole adapter. **Only an
        explicit refusal is news**, so the ordinary path has to stay green with the guard in place.
        """
        self.a_channel(saying=self.a_message_arrived())
        self.hosting_now()
        self.waited_for_a_turn()
        self.assertTrue(self.waited_until(lambda: answering.DONE in self.marks()),
                        "a delivery the platform took did not leave the question done")

    def test_the_answer_quotes_the_message_that_asked(self):
        """R-DIS-28. The reply is how a surface tells the one message somebody was waiting for from
        the running commentary around it — and on Discord it is what draws the platform's own
        emphasis. Every layer below took an `external_id` and this thread was started without one,
        so the whole mechanism was built and never fired."""
        self.a_channel(saying=self.a_message_arrived())
        self.hosting_now()
        self.waited_for_a_turn()
        self.assertTrue(self.waited_until(lambda: self.delivered()))
        quoting = [one for one in self.what_it_was_told()
                   if one.get("do") == "deliver" and one.get("reply_to")]
        self.assertEqual(1, len(quoting), "the answer did not quote the message that asked")
        self.assertEqual("8841", quoting[0]["reply_to"])

    def test_the_mark_saying_how_it_ended_goes_on_the_message_that_asked(self):
        """R-DIS-7, R-DIS-8. Sent without the message to put it on, every state crossed the seam
        correctly and the adapter had nothing to react to — so a turn was marked 👀 on arrival and
        never marked again, which reads as an agent that took the message up and forgot it."""
        self.a_channel(saying=self.a_message_arrived())
        self.hosting_now()
        self.waited_for_a_turn()
        self.assertTrue(self.waited_until(lambda: answering.DONE in self.marks()))
        settled = [one for one in self.what_it_was_told()
                   if one.get("do") == "state" and one.get("state") == answering.DONE]
        self.assertEqual("8841", settled[0].get("external_id"))

    def test_the_answer_carries_what_the_turn_cost_and_only_the_first_piece_does(self):
        """R-DIS-17, R-DIS-33. The provider leads, the brain here reports a conversation size so
        that leads the counts (R-DIS-29), and the clock is always known. Four cost lines on a
        four-piece answer is the same number said four times."""
        self.a_channel(saying=self.a_message_arrived())
        self.hosting_now()
        self.waited_for_a_turn()
        self.assertTrue(self.waited_until(lambda: self.delivered()))
        deliveries = [one for one in self.what_it_was_told() if one.get("do") == "deliver"]
        self.assertEqual(1, len([one for one in deliveries if one.get("cost")]))
        cost = deliveries[0]["cost"]
        # R-CH-28. Named, and never located: this brain is referred to by an absolute path, and the
        # line it appears on goes into a chat room.
        self.assertTrue(cost.startswith("a-stand-in ·"), cost)
        self.assertNotIn("/", cost)
        self.assertIn("9.2k session", cost)
        self.assertIn("1.5k output", cost)
        self.assertIn("elapsed", cost)
        # Cache writes stay in the turn's own record and never reach a surface.
        self.assertNotIn("written", cost)

    def test_room_for_the_cost_line_is_taken_out_before_the_words_are_cut(self):
        """The adapter refuses anything past its own limit outright, as rundesk having failed to
        split — which loses the delivery rather than trimming it. So the first piece plus the line
        that will be put above it has to fit, and the arithmetic is done on this side."""
        # The stand-in echoes what it was asked, so a long question is a long answer.
        self.a_channel(saying=self.a_message_arrived(text="x" * 3000))
        self.hosting_now()
        self.waited_for_a_turn()
        self.assertTrue(self.waited_until(
            lambda: len([one for one in self.what_it_was_told()
                         if one.get("do") == "deliver"]) > 1), "the answer was never split")
        first = next(one for one in self.what_it_was_told() if one.get("do") == "deliver")
        self.assertTrue(first.get("cost"), "the first piece carried no cost line")
        # What the adapter would build, measured against what it would refuse.
        self.assertLessEqual(len(first["cost"]) + len("-# ") + 1 + len(first["text"]),
                             delivery.WHEN_UNSAID)

    def test_what_the_agent_did_is_shown_while_the_turn_is_still_running(self):
        """R-CH-6, R-DIS-20. The sink existed and had no producer, so a channel saw nothing at all
        between the message arriving and the answer landing — minutes, on a real turn."""
        self.a_channel(saying=self.a_message_arrived())
        self.hosting_now()
        self.waited_for_a_turn()
        self.assertTrue(self.waited_until(lambda: self.activity()))
        self.assertIn("read", [one.get("did") for one in self.activity()])

    def test_activity_carries_what_it_did_and_never_what_the_tool_was_given(self):
        """R-CH-13. A command line and a path are somebody's private business, and this is posted
        into a room. The brain's own name for the tool is not sent either: a commentary reading
        `commandExecution` is one vendor's identifiers in front of somebody who never asked."""
        self.a_channel(saying=self.a_message_arrived())
        self.hosting_now()
        self.waited_for_a_turn()
        self.assertTrue(self.waited_until(lambda: self.activity()))
        allowed = {"do", "place", "did", "ok", "who"}
        for one in self.activity():
            self.assertEqual(set(), set(one) - allowed, f"{sorted(set(one) - allowed)} crossed")
        # The stand-in's tool is called `Read` and its result summarises `one file`. Neither may
        # appear anywhere in what the adapter was handed while the turn ran.
        while_running = [one for one in self.what_it_was_told() if one.get("do") == "activity"]
        self.assertNotIn("Read", json.dumps(while_running))
        self.assertNotIn("one file", json.dumps(while_running))

    def test_a_thought_is_shown_as_one_broad_line_and_never_as_the_thought(self):
        """A thought is the most private thing a brain produces and the least useful to show."""
        self.a_channel(saying=self.a_message_arrived())
        self.hosting_now()
        self.waited_for_a_turn()
        self.assertTrue(self.waited_until(lambda: self.activity()))
        thoughts = [one for one in self.activity() if not one.get("did")]
        self.assertTrue(thoughts, "the agent thinking was never shown")
        self.assertNotIn("reading what was asked", json.dumps(self.activity()))

    def test_a_finished_thing_said_mid_turn_is_shown_when_the_next_one_arrives(self):
        """R-CH-19. The last thing said is the answer, and that is only knowable once there is a
        next — so each whole remark is posted the moment another proves it was not the end."""
        self.a_stand_in_told(self.agent, remarks=["checking staging first", "now the database"])
        self.a_channel(saying=self.a_message_arrived())
        self.hosting_now()
        self.waited_for_a_turn()
        self.assertTrue(self.waited_until(lambda: len(self.delivered()) >= 3))
        said = self.delivered()
        self.assertEqual("checking staging first", said[0])
        self.assertEqual("now the database", said[1])
        self.assertIn("You asked:", said[2])

    def test_a_remark_is_plain_and_only_the_answer_is_the_answer(self):
        """R-CH-19, R-DIS-28. A thread where every line quotes the same message is unreadable, and
        marking one done for each remark would say the turn finished several times."""
        self.a_stand_in_told(self.agent, remarks=["one moment"])
        self.a_channel(saying=self.a_message_arrived())
        self.hosting_now()
        self.waited_for_a_turn()
        self.assertTrue(self.waited_until(lambda: len(self.delivered()) >= 2))
        posted = [one for one in self.what_it_was_told() if one.get("do") == "deliver"]
        self.assertEqual("one moment", posted[0]["text"])
        self.assertNotIn("reply_to", posted[0])
        self.assertNotIn("cost", posted[0])
        # And the last one is the answer, carrying both.
        self.assertEqual("8841", posted[-1]["reply_to"])
        self.assertTrue(posted[-1].get("cost"))

    def test_a_remark_already_posted_is_not_repeated_inside_the_answer(self):
        """R-CH-19. `protocol.last_thought` exists for exactly this and its docstring says so: a
        surface shown each finished remark as it landed has already had everything before the last
        one. Sending the whole reply posted every remark a second time, and it read as the agent
        repeating itself — caught by tracing the seam rather than by any case."""
        self.a_stand_in_told(self.agent, remarks=["checking staging first", "now the database"])
        self.a_channel(saying=self.a_message_arrived())
        self.hosting_now()
        self.waited_for_a_turn()
        self.assertTrue(self.waited_until(lambda: len(self.delivered()) >= 3))
        answer = next(one for one in self.what_it_was_told()
                      if one.get("do") == "deliver" and one.get("reply_to"))
        self.assertNotIn("checking staging first", answer["text"])
        self.assertNotIn("now the database", answer["text"])
        self.assertIn("You asked:", answer["text"])
        # And each remark was said exactly once, across everything the surface was handed.
        for once in ("checking staging first", "now the database"):
            self.assertEqual(1, self.delivered().count(once))

    def test_a_brain_that_says_one_whole_thing_posts_exactly_one_message(self):
        """The other half of the same rule. A brain that never says several finished things must not
        be made chattier by this existing — the held remark is the answer and is never posted twice."""
        self.a_channel(saying=self.a_message_arrived())
        self.hosting_now()
        self.waited_for_a_turn()
        self.assertTrue(self.waited_until(lambda: self.delivered()))
        self.assertEqual(1, len(self.delivered()), self.delivered())

    def test_a_turn_can_be_stopped_from_the_conversation_it_is_running_in(self):
        """R-CH-9. The brain and everything it started go, and the turn settles as `stopped` — which
        is the word the surface renders as ✋. Written by the same code that settles every other
        turn, so there is no second path that could disagree about what happened."""
        self.a_stand_in_told(self.agent, silent=30)
        self.a_channel(saying=self.a_message_arrived())
        watching = self.hosting_now()
        gestures = answering.Gestures(self.where, lambda: watching, lambda word: None,
                                      lambda agent: "online")
        self.assertTrue(self.waited_until(self.a_turn_is_running),
                        "no turn was ever running to stop")

        said = gestures.controlled(self.agent, "discord", "1180", "2207", answering_hosting.STOP)

        self.assertEqual("✋ Stopped.", said)
        turn = self.waited_for_a_turn()
        self.assertEqual(kept.STOPPED, turn["turn_status"])
        self.assertTrue(self.waited_until(lambda: answering.STOPPED in self.marks()))

    def test_a_turn_somebody_stopped_is_never_apologised_for(self):
        """The sentence for a turn that produced nothing exists because silence leaves a person
        unable to tell a broken agent from a slow one. Somebody who just pressed `/stop` knows
        exactly which this is, and the apology reads as a fault they caused."""
        self.a_stand_in_told(self.agent, silent=30)
        self.a_channel(saying=self.a_message_arrived())
        watching = self.hosting_now()
        gestures = answering.Gestures(self.where, lambda: watching, lambda word: None,
                                      lambda agent: "online")
        self.assertTrue(self.waited_until(self.a_turn_is_running))

        gestures.controlled(self.agent, "discord", "1180", "2207", answering_hosting.STOP)

        self.waited_for_a_turn()
        self.assertNotIn("could not answer", " ".join(self.delivered()))

    def test_stopping_where_nothing_is_running_says_so(self):
        self.a_channel()
        watching = self.hosting_now()
        gestures = answering.Gestures(self.where, lambda: watching, lambda word: None,
                                      lambda agent: "online")
        self.assertEqual("✋ Nothing is running here.",
                         gestures.controlled(self.agent, "discord", "1180", "2207",
                                             answering_hosting.STOP))

    def a_provider(self, named="other"):
        """A second brain this install really has, so a change of provider has somewhere to go."""
        where = paths.code() / "providers"
        where.mkdir(parents=True, exist_ok=True)
        at = where / named
        at.write_text(Path(support.A_STAND_IN).read_text(encoding="utf-8"), encoding="utf-8")
        at.chmod(0o755)
        return named

    def a_gesture(self, watching=None):
        return answering.Gestures(self.where, lambda: watching or hosting.Watching({}, {}, {}),
                                  lambda word: None, lambda agent: "online")

    def test_changing_the_brain_writes_it_down_for_every_turn_after(self):
        """R-CH-26. A provider is an agent-wide default, so this is what the *next* turn resolves —
        in this conversation, on every other channel, and for every schedule."""
        self.a_channel(allowed=("2207",))
        other = self.a_provider()
        said = self.a_gesture().configured(self.agent, "discord", "1180", "2207", other)
        self.assertIn(other, said)
        self.assertEqual(other, records.read(directory.records(self.agent))["provider_name"])

    def test_a_brain_this_install_does_not_have_is_refused_before_anything_is_written(self):
        """A default nothing stands behind is an agent whose every turn fails from the next message
        on, and the person who typed it would be the last to find out."""
        self.a_channel(allowed=("2207",))
        was = records.read(directory.records(self.agent))["provider_name"]
        said = self.a_gesture().configured(self.agent, "discord", "1180", "2207", "nonesuch")
        self.assertIn("no brain called", said)
        self.assertEqual(was, records.read(directory.records(self.agent))["provider_name"],
                         "a brain that does not exist was written down anyway")

    def test_a_shared_channel_cannot_change_what_the_agent_is_for_everybody(self):
        """Being on a shared room's allow list is authority to speak to the agent there, and it is
        not authority to change what the agent *is* for every other channel and schedule."""
        self.a_channel(allowed=("2207", "9999"))
        was = records.read(directory.records(self.agent))["provider_name"]
        said = self.a_gesture().configured(self.agent, "discord", "1180", "2207",
                                           self.a_provider())
        self.assertIn("one person", said)
        self.assertEqual(was, records.read(directory.records(self.agent))["provider_name"])

    def test_somebody_who_is_not_the_one_allowed_cannot_change_it(self):
        self.a_channel(allowed=("2207",))
        was = records.read(directory.records(self.agent))["provider_name"]
        said = self.a_gesture().configured(self.agent, "discord", "1180", "9999",
                                           self.a_provider())
        self.assertIn("one person", said)
        self.assertEqual(was, records.read(directory.records(self.agent))["provider_name"])

    def test_naming_nothing_says_what_to_type(self):
        self.a_channel(allowed=("2207",))
        self.assertIn("/provider",
                      self.a_gesture().configured(self.agent, "discord", "1180", "2207", "  "))

    def test_the_brain_it_already_answers_on_is_said_rather_than_written_again(self):
        self.a_channel(allowed=("2207",))
        was = records.read(directory.records(self.agent))["provider_name"]
        said = self.a_gesture().configured(self.agent, "discord", "1180", "2207", was)
        self.assertIn("already", said)

    def test_changing_brain_throws_away_every_handle_this_conversation_held(self):
        """Keying sessions by conversation *and* brain already makes the move itself fresh — the new
        one has no handle to resume. What it leaves is the **old** one, so moving back would
        silently pick up a conversation from before the change: somebody who changed brain and
        changed back has started again twice as far as they are concerned."""
        self.a_channel(allowed=("2207",))
        conversation = arriving.recorded(self.agent, "discord", "1180", "2207", "hello").conversation
        kept.save_session(self.agent, conversation, support.A_STAND_IN, "thread-old")

        other = self.a_provider()
        said = self.a_gesture().configured(self.agent, "discord", "1180", "2207", other)

        self.assertEqual(f"**{self.agent}** now uses **{other}**. This conversation starts fresh.",
                         said)
        self.assertIsNone(kept.get_session(self.agent, conversation, other),
                          "the new brain inherited a handle that was not its own")
        self.assertIsNone(kept.get_session(self.agent, conversation, support.A_STAND_IN),
                          "moving back would have resumed a conversation from before the change")

    def test_the_answer_is_recorded_as_a_message_carrying_the_turn_that_said_it(self):
        """What was said and what it cost are two questions, and this is the one join between them.
        Without it nobody can get from a sentence in the history to the turn that produced it."""
        self.a_channel(saying=self.a_message_arrived())
        self.hosting_now()
        turn = self.waited_for_a_turn()
        conversation = kept.get_turn(self.agent, turn["id"])["conversation_id"]

        def by_the_agent():
            return [one for one in arriving.messages(self.agent, conversation)
                    if one["author"] == arriving.BY_AGENT]
        self.assertTrue(by_the_agent() or self.waited_until(by_the_agent),
                        "the answer was never recorded as a message")
        self.assertEqual(turn["id"], by_the_agent()[0]["turn_id"])

    def test_the_thread_it_runs_on_is_not_the_one_reading_the_channel(self):
        """A turn takes minutes and that thread cannot fall behind — so `answer` returns at once,
        long before the turn it started has finished."""
        self.a_channel()
        watching = hosting.Watching({}, {}, {})
        answers = answering.OnAChannel(self.where, lambda: watching)
        landed = arriving.recorded(self.agent, "discord", "1180", "2207", "take your time")
        answers.answer(self.agent, "discord", "1180", "2207", "take your time", "8841", landed)
        # Nothing has settled yet, because nothing was waited for. If `answer` had run the turn
        # inline this line could not be reached before it finished.
        self.assertTrue(self.waited_until(lambda: kept.list_turns(self.agent)))

    def test_a_message_from_somebody_not_allowed_starts_no_turn_at_all(self):
        self.a_channel(allowed=("2207",),
                       saying=self.a_message_arrived(user="9999", text="let me in"))
        self.hosting_now()
        self.assertFalse(
            self.waited_until(lambda: kept.list_turns(self.agent), NOT_GOING_TO_HAPPEN),
            "a stranger's message reached a brain")


class ATurnThatMadeSomethingAndSaidNothing(Answering):
    """**A file counts as an answer** — `protocol.has_answer` says so, and the turn is `done`.

    The surface that delivers it decided otherwise: it looked only at the reply text, found none,
    and fell through to the sentence for a turn that failed. So an agent asked for a chart made the
    chart, the turn succeeded, and the person was sent *"I could not answer that"* with the chart
    attached to it.
    """

    def test_the_person_is_not_told_it_failed(self):
        self.a_stand_in_told(self.agent, made_a_file_and_said_nothing=True)
        self.a_channel(saying=self.a_message_arrived())
        self.hosting_now()
        turn = self.waited_for_a_turn()
        self.assertEqual(kept.DONE, turn["turn_status"])
        self.assertTrue(self.waited_until(lambda: answering.DONE in self.marks()))
        self.assertNotIn("could not answer", " ".join(self.delivered()))


class WhenTheBrainMadeSomethingForThePerson(Answering):
    """R-CH-31, end to end through both seams. **The whole outbound path was built and unreachable**
    — containment, `O_NOFOLLOW`, the digest, the adapter's re-open — with nothing able to produce a
    candidate, because no shipped adapter emits a `file` record and each explains why. The link in the
    answer is what closes it."""

    def files_sent(self):
        return [one for one in self.what_it_was_told()
                if one.get("do") == "deliver" and one.get("files")]

    def test_a_file_the_brain_linked_is_actually_sent(self):
        self.a_stand_in_told(self.agent, linked_a_file_it_made=True)
        self.a_channel(saying=self.a_message_arrived())
        self.hosting_now()
        self.waited_for_a_turn()
        self.assertTrue(self.waited_until(lambda: self.files_sent()),
                        "the brain linked a file it made and nothing was ever sent")
        carried = self.files_sent()[0]["files"]
        self.assertEqual(1, len(carried))
        self.assertEqual("a-chart.png", carried[0]["name"])
        self.assertEqual(len(b"not really a chart"), carried[0]["bytes"])
        self.assertTrue(carried[0]["sha256"], "a file crossed the seam with no digest to check it")

    def test_the_machine_path_is_never_posted_into_the_room(self):
        """**A path is the owner's own directory** and a reader cannot act on it. Left in the words,
        an answer publishes where somebody's home stands to whoever is in the room."""
        self.a_stand_in_told(self.agent, linked_a_file_it_made=True)
        self.a_channel(saying=self.a_message_arrived())
        self.hosting_now()
        self.waited_for_a_turn()
        self.assertTrue(self.waited_until(lambda: self.files_sent()))
        words = " ".join(self.delivered())
        self.assertIn("the chart", words, "the label was taken out along with the path")
        self.assertNotIn("a-chart.png", words, "the machine path was posted into the room")


class WhenTheBrainCouldNotAnswer(Answering):

    def test_somebody_waiting_is_told_rather_than_left_in_silence(self):
        """**Silence is the one thing that must not happen.** A person who asked a question and got
        nothing cannot tell a broken agent from a slow one."""
        self.a_stand_in_told(self.agent, fail_with="rate_limited")
        self.a_channel(saying=self.a_message_arrived())
        self.hosting_now()
        self.waited_for_a_turn()
        self.assertTrue(self.waited_until(lambda: self.delivered()), "nobody was told anything")
        self.assertIn("rate_limited", " ".join(self.delivered()))

    def test_it_says_whether_waiting_will_help_without_naming_a_vendor(self):
        self.a_stand_in_told(self.agent, fail_with="signed_out")
        self.a_channel(saying=self.a_message_arrived())
        self.hosting_now()
        self.waited_for_a_turn()
        self.assertTrue(self.waited_until(lambda: self.delivered()))
        self.assertIn("will not clear on its own", " ".join(self.delivered()))

    def test_the_message_is_marked_failed_and_never_left_working(self):
        self.a_stand_in_told(self.agent, fail_with="upstream_error")
        self.a_channel(saying=self.a_message_arrived())
        self.hosting_now()
        self.waited_for_a_turn()
        self.assertTrue(self.waited_until(lambda: answering.FAILED in self.marks()))

    def test_an_adapter_that_is_not_there_does_not_leave_the_message_working(self):
        """The turn cannot even begin, and that is exactly when a mark is most likely to be missed."""
        records.stated(directory.records(self.agent),
                       {"provider_name": "nothing-stands-here"})
        self.a_channel(saying=self.a_message_arrived())
        self.hosting_now()
        self.assertTrue(self.waited_until(lambda: answering.FAILED in self.marks()),
                        "a message was left saying it was being worked on")


class TwoTurnsInOneConversation(Answering):

    def test_a_message_arriving_mid_turn_is_said_into_the_turn_already_running(self):
        """**The requirement, and what a person in a room actually means.** Somebody adding to their
        own question while their agent works is not asking a second question — they are changing the
        one being answered. The build this replaces recorded the message and answered nobody, and
        the person was never told: they simply never got a reply to what they said second.
        """
        self.a_stand_in_told(self.agent, steer=True, silent="3")
        landed = arriving.recorded(self.agent, "discord", "1180", "2207", "the first")
        watching = hosting.Watching({}, {}, {})
        answers = answering.OnAChannel(self.where, lambda: watching)
        answers.answer(self.agent, "discord", "1180", "2207", "the first", "8841", landed)
        self.assertTrue(self.waited_until(lambda: turns.busy(self.agent, landed.conversation)),
                        "no turn ever started to steer")

        answers.answer(self.agent, "discord", "1180", "2207", "the second", "8842", landed)
        self.assertTrue(self.waited_until(
            lambda: "said into the turn already running" in self.said()),
            "a message that arrived mid-turn reached nobody")
        # **One turn, not two.** A second turn would answer the same person twice and cost twice.
        self.assertTrue(self.waited_until(lambda: len(kept.list_turns(self.agent)) == 1))

    def test_a_claim_no_running_turn_will_take_a_word_from_is_asked_again(self):
        """A conversation can be busy without there being a turn here to speak into — a person at a
        terminal holds the same claim, and so does a scheduled turn in a process of its own.

        **Nobody took the word, so the message is still unanswered**, and the build this replaces
        would have stopped there. It is offered again instead, because the way it was refused is
        also the way it stops being refused: the turn in front of it ends.
        """
        self.a_stand_in_told(self.agent, silent=True)
        landed = arriving.recorded(self.agent, "discord", "1180", "2207", "the first")
        watching = hosting.Watching({}, {}, {})
        answers = answering.OnAChannel(self.where, lambda: watching)
        with turns.claiming(self.agent, landed.conversation):
            answers.answer(self.agent, "discord", "1180", "2207", "the second", "8842", landed)
            self.assertTrue(self.waited_until(lambda: "stayed busy" in self.said()),
                            "a message nobody could take was neither answered nor reported")
        self.assertEqual([], kept.list_turns(self.agent))

    def said(self):
        found = list(self.where.glob("*.log"))
        return "".join(one.read_text(encoding="utf-8") for one in found)


class AScheduleThatAsksTheAgent(Answering):

    def a_schedule(self, name="nightly", prompt="what happened overnight?", **also):
        schedules_kept.added(self.agent, name, dict(
            {"cron": "* * * * *", "prompt": prompt}, **also))
        return name

    def test_it_gets_a_conversation_of_its_own_and_never_the_terminal_one(self):
        """A run at three in the morning must not land in the exchange somebody types into."""
        typed = arriving.asked_at_a_terminal(self.agent, "what are you doing?")
        got = answering.for_a_schedule(self.agent, self.a_schedule())
        self.assertTrue(got.worked)
        self.assertNotEqual(typed.conversation,
                            kept.get_turn(self.agent, got.turn)["conversation_id"])

    def test_two_runs_of_one_schedule_carry_the_same_conversation_on(self):
        """Keyed by the schedule's name, so a nightly job remembers last night."""
        name = self.a_schedule()
        first = answering.for_a_schedule(self.agent, name)
        second = answering.for_a_schedule(self.agent, name)
        self.assertEqual(kept.get_turn(self.agent, first.turn)["conversation_id"],
                         kept.get_turn(self.agent, second.turn)["conversation_id"])

    def test_the_turn_is_tied_to_the_schedule_that_caused_it(self):
        """*What has the nightly schedule been doing?* is a question with one answer only if this
        is written down at the moment the turn is admitted."""
        got = answering.for_a_schedule(self.agent, self.a_schedule())
        self.assertEqual(schedules_kept.one(self.agent, "nightly")["id"],
                         kept.get_turn(self.agent, got.turn)["schedule_id"])

    def test_one_that_names_a_program_is_refused_in_words_that_say_what_to_type(self):
        self.a_schedule("build", prompt=None, command="/bin/echo hi")
        with self.assertRaises(answering.Refused) as refused:
            answering.for_a_schedule(self.agent, "build")
        self.assertIn("rundesk schedules run", str(refused.exception))


if __name__ == "__main__":
    unittest.main()
