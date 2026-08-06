"""An adapter that is running: what is read off it, what is said to it, and how it ends.

Every program here is a `python3 -c` that prints a line or sleeps. Nothing needs a brain, an account
or a network — the properties being proved are about pipes, threads and clocks, and those are the
same whatever is on the other end.

Run directly: `python3 tests/test_providers_streaming.py`
"""

import contextlib
import sys
import time
import unittest

import support
from rundesk.providers import streaming
from rundesk.utils import lines, programs

#: Long enough for a `python3 -c` that prints a line to have printed it on a loaded machine, and
#: short enough that a case which will never pass fails while somebody is still watching.
PATIENCE = 10.0

#: Prints what it was given, one line each, and leaves.
SAYS = """
import sys
for said in {each!r}:
    print(said, flush=True)
"""

#: Says one thing, then never says another. What a wedged brain looks like.
GOES_QUIET = """
import sys, time
print("first", flush=True)
time.sleep({for_seconds!r})
"""

#: Never stops saying things. What the silence window cannot see and the ceiling can.
KEEPS_TALKING = """
import sys, time
while True:
    print("still here", flush=True)
    time.sleep(0.01)
"""

#: Reads its input to the end before it answers at all — the shape `no_more` exists for.
ANSWERS_AT_THE_END = """
import sys
said = sys.stdin.read()
print("heard " + str(len(said.splitlines())), flush=True)
"""

#: Answers each line as it arrives, so a case can prove a word reached a *running* program.
ANSWERS_EACH = """
import sys
for said in sys.stdin:
    print("heard " + said.strip(), flush=True)
    sys.stdout.flush()
"""

#: Writes to its error stream and nowhere else. Working, and silent on the stream anybody watches.
ONLY_COMPLAINS = """
import sys, time
for _ in range({many!r}):
    print("working", file=sys.stderr, flush=True)
    time.sleep({every!r})
"""


class Streaming(support.Isolated):
    """Every case starts a real child and takes it away again, however the case ended."""

    def setUp(self):
        super().setUp()
        self.started = []
        self.addCleanup(self.stop_everything)

    def stop_everything(self):
        """One child that will not stop must not hide the others, so each is asked on its own."""
        for one in self.started:
            with contextlib.suppress(Exception):
                one.stop(gently_for=0.2, firmly_for=1.0, settling_for=0.05)

    def given(self, body: str, **also) -> streaming.Stream:
        """A running program, read as an adapter, taken away on the way out of the case."""
        one = streaming.started([sys.executable, "-c", body],
                                errors=self.home / "stderr.log", **also)
        self.started.append(one)
        return one


class WhatItSays(Streaming):
    def test_every_line_arrives_in_order(self):
        one = self.given(SAYS.format(each=["first", "second", "third"]))
        self.assertEqual(list(one.records()), ["first\n", "second\n", "third\n"])

    def test_a_program_that_says_nothing_ends_the_stream(self):
        one = self.given("pass")
        self.assertEqual(list(one.records()), [])
        self.assertIsNone(one.stop_reason)

    def test_a_slow_reader_still_receives_everything(self):
        """The thread reads ahead so a turn that spends a fifth of a second on a record — which a
        channel post easily does — slows nothing but itself."""
        one = self.given(SAYS.format(each=[str(n) for n in range(20)]))
        got = []
        for said in one.records():
            time.sleep(0.01)
            got.append(said)
        self.assertEqual(len(got), 20)

    def test_a_line_that_will_not_fit_is_a_gap_and_the_lines_after_it_survive(self):
        """The cap reaches the reader. `utils.lines` proves the framing; this proves it is used."""
        one = self.given(SAYS.format(each=["x" * 40, "after"]), line_at_most=16)
        got = list(one.records())
        self.assertEqual(got, [lines.Gap(1, lines.TOO_LONG), "after\n"])


class WhenItGoesQuiet(Streaming):
    def test_saying_nothing_for_too_long_ends_it_and_says_so(self):
        one = self.given(GOES_QUIET.format(for_seconds=30), silence=0.6)
        got = list(one.records())
        self.assertEqual(got, ["first\n"])
        self.assertIn("said nothing", one.stop_reason)

    def test_ending_a_quiet_program_does_not_wait_for_it_to_finish(self):
        """The defect this was written for was a hang, and only a clock can see it.

        Closing the pipe before signalling waits on the io lock the reading thread holds for the
        length of a `readline` — which returns only when the program says something or leaves. This
        program has thirty seconds of sleeping left, and a genuinely wedged one has for ever, inside
        a gateway shutdown with twenty-five seconds to live.
        """
        one = self.given(GOES_QUIET.format(for_seconds=30), silence=0.6)
        began = time.monotonic()
        list(one.records())
        took = time.monotonic() - began
        self.assertLess(took, 10.0,
                        f"ending a program that had gone quiet took {took:.1f}s — it waited for "
                        "the program instead of ending it")

    def test_writing_only_to_the_error_stream_is_not_silence(self):
        """A brain working steadily and reporting only diagnostics is plainly busy, and looks silent
        on the one stream anybody watches."""
        one = self.given(ONLY_COMPLAINS.format(many=12, every=0.1), silence=0.6)
        began = time.monotonic()
        self.assertEqual(list(one.records()), [])
        self.assertIsNone(one.stop_reason,
                          "a program writing to stderr throughout was taken for wedged")
        self.assertGreater(time.monotonic() - began, 0.6,
                           "the program ended before the silence window had even elapsed")

    def test_a_program_that_never_stops_talking_meets_the_ceiling(self):
        """Silence cannot see a program wedged in a loop that keeps announcing itself."""
        one = self.given(KEEPS_TALKING, silence=30.0, ceiling=0.7)
        got = list(one.records())
        self.assertTrue(got)
        self.assertIn("still running", one.stop_reason)


class SayingSomethingToIt(Streaming):
    def test_a_word_reaches_a_running_program(self):
        one = self.given(ANSWERS_EACH)
        heard = one.records()
        self.assertTrue(one.say("hello"))
        self.assertEqual(next(heard), "heard hello\n")
        self.assertTrue(one.say("again"))
        self.assertEqual(next(heard), "heard again\n")

    def test_telling_it_there_is_no_more_lets_it_answer(self):
        """A program that reads its input to the end is waiting for exactly this, and ending it
        instead would take it away mid-answer."""
        one = self.given(ANSWERS_AT_THE_END)
        one.say("one")
        one.say("two")
        one.no_more()
        self.assertEqual(list(one.records()), ["heard 2\n"])

    def test_saying_something_after_it_has_gone_is_an_answer_and_not_a_failure(self):
        one = self.given("pass")
        self.assertEqual(list(one.records()), [])
        self.assertFalse(one.say("anybody there?"))

    def test_telling_it_there_is_no_more_twice_is_allowed(self):
        one = self.given(ANSWERS_AT_THE_END)
        one.no_more()
        one.no_more()
        self.assertEqual(list(one.records()), ["heard 0\n"])


class WhenTheTurnCannotKeepUp(Streaming):
    def test_records_lost_to_a_full_queue_are_said_where_they_were_lost(self):
        """The queue is never waited on: waiting is the deadlock this shape exists to prevent, so a
        record is lost instead — and a loss nobody is told about is a wrong answer, not a smaller
        one."""
        one = self.given(SAYS.format(each=[str(n) for n in range(400)]), held_at_most=2)
        heard = one.records()
        next(heard)                                     # start the reader, then fall behind it
        time.sleep(0.5)
        got = list(heard)
        gaps = [said for said in got if isinstance(said, lines.Gap)]
        said = [one for one in got if isinstance(one, str)]
        self.assertTrue(gaps, "400 lines into a queue of 2 lost nothing, which cannot be true")
        self.assertEqual(gaps[0].reason, streaming.FELL_BEHIND)
        self.assertGreater(gaps[0].lost_count, 0)
        self.assertLess(len(said), 400, "nothing was lost, so the queue was waited on")

    def test_what_survived_still_arrives_in_the_order_it_was_said(self):
        """A loss must not reorder what is left, or a reader cannot trust any of it."""
        one = self.given(SAYS.format(each=[str(n) for n in range(400)]), held_at_most=2)
        heard = one.records()
        next(heard)
        time.sleep(0.5)
        said = [int(one) for one in heard if isinstance(one, str)]
        self.assertEqual(said, sorted(said))


class EndingIt(Streaming):
    def test_stopping_twice_is_allowed(self):
        one = self.given(KEEPS_TALKING, ceiling=0.3)
        list(one.records())
        self.assertEqual(one.stop(gently_for=0.2, firmly_for=1.0), "")

    def test_abandoning_the_records_still_takes_the_program_away(self):
        """A caller that walks away from the iterator is otherwise how a process is left running with
        nobody holding it."""
        one = self.given(KEEPS_TALKING)
        heard = one.records()
        next(heard)
        heard.close()
        self.assertTrue(support.waited_until(lambda: not programs.alive(one.talking.pid), PATIENCE),
                        "the program was still running after its records were abandoned")

    def test_what_it_said_went_wrong_is_readable_and_bounded(self):
        one = self.given(ONLY_COMPLAINS.format(many=40, every=0.0), silence=5.0)
        list(one.records())
        tail = one.errors_tail(at_most_lines=5)
        self.assertEqual(len(tail), 5)
        self.assertEqual(tail[-1], "working")

    def test_a_program_that_left_says_what_it_came_to(self):
        one = self.given("raise SystemExit(3)")
        list(one.records())
        self.assertTrue(support.waited_until(lambda: one.outcome().over, PATIENCE))
        self.assertEqual(one.outcome().code, 3)


if __name__ == "__main__":
    unittest.main()
