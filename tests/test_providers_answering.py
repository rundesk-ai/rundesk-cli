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
import unittest

import support
from rundesk.agents import directory, records
from rundesk.channels import arriving, hosting
from rundesk.channels import kept as channels_kept
from rundesk.core import paths
from rundesk.providers import answering, kept, turns
from rundesk.schedules import kept as schedules_kept
from rundesk.utils import programs

#: How long a case waits for a real turn to finish on its own thread. A ceiling rather than a sleep,
#: so an ordinary run is through in tenths.
PATIENCE = 30.0

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
        self.addCleanup(self.stop_everything)

    def stop_everything(self):
        """End what this case started, by pid, however the case ended."""
        for watching in self.watching:
            with contextlib.suppress(Exception):
                hosting.stopping(self.agent, self.where, watching, 4.0)
        for pid in self.pids:
            with contextlib.suppress(OSError):
                programs.stop(pid, gently_for=0.2, firmly_for=2.0)

    def a_channel(self, saying="", allowed=("2207",)):
        at = self.adapters / "discord"
        at.write_text(AN_ADAPTER, encoding="utf-8")
        at.chmod(0o755)
        channels_kept.added(self.agent, "discord", {
            "describes": "discord", "allowed": json.dumps(list(allowed)),
            "settings": json.dumps({"saying": saying, "told": str(self.told)})})

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

    def waited_until(self, whether):
        return support.waited_until(whether, PATIENCE)

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
        self.assertFalse(self.waited_until(lambda: kept.list_turns(self.agent), ),
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

    def test_the_second_is_refused_rather_than_queued_and_says_so_in_the_log(self):
        """The claim is the kernel's, so this competes correctly with a person at a terminal asking
        the same agent with no coordination between the two."""
        self.a_stand_in_told(self.agent, silent=True)
        landed = arriving.recorded(self.agent, "discord", "1180", "2207", "the first")
        watching = hosting.Watching({}, {}, {})
        answers = answering.OnAChannel(self.where, lambda: watching)
        with turns.claiming(self.agent, landed.conversation):
            answers.answer(self.agent, "discord", "1180", "2207", "the second", "8842", landed)
            self.assertTrue(self.waited_until(
                lambda: "already being answered" in self.said()),
                "a second turn was started in a conversation somebody was already answering in")
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
