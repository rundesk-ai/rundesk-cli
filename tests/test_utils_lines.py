"""Reading a stream one whole line at a time, and what happens to a line that cannot be given whole.

Every case here is a `StringIO`. That is the point of the module: the bound it promises used to be
provable only by starting a program that wrote 300 MB, which is why it went unproven long enough for
a real gateway to be ended by the kernel.

Run directly: `python3 tests/test_utils_lines.py`
"""

import io
import unittest

import support
from rundesk.utils import lines

#: Small enough that a case can write a line over it on one screen. Nothing here depends on the
#: value, so the cases read the same at a megabyte.
AT_MOST = 16


def everything(said: str, at_most: int = AT_MOST):
    """Everything `lines.read` yields for this text, as a list."""
    return list(lines.read(io.StringIO(said), at_most))


class WholeLines(support.Isolated):
    """What a well-behaved program produces."""

    def test_a_line_keeps_its_newline(self):
        self.assertEqual(everything("one\n"), ["one\n"])

    def test_lines_arrive_in_order(self):
        self.assertEqual(everything("one\ntwo\nthree\n"), ["one\n", "two\n", "three\n"])

    def test_a_stream_with_nothing_in_it_says_nothing(self):
        self.assertEqual(everything(""), [])

    def test_a_blank_line_is_a_line(self):
        self.assertEqual(everything("\n\n"), ["\n", "\n"])

    def test_a_line_exactly_at_the_cap_is_whole(self):
        """The boundary the `+ 1` in the read exists to make readable.

        A line of exactly `at_most` characters plus its newline comes back longer than `at_most`,
        and it fitted. Only a full read with **no** newline on the end was cut off.
        """
        said = "x" * AT_MOST + "\n"
        self.assertEqual(everything(said), [said])


class ALineThatWillNotFit(support.Isolated):
    """The failure this module exists for, and the one that must not cost the lines after it."""

    def test_an_over_long_line_is_a_gap_and_never_a_line(self):
        got = everything("x" * (AT_MOST + 5) + "\n")
        self.assertEqual(got, [lines.Gap(1, lines.TOO_LONG)])

    def test_the_framing_survives_it(self):
        """One enormous line must not cost every line after it."""
        got = everything("x" * (AT_MOST + 5) + "\nafter\n")
        self.assertEqual(got, [lines.Gap(1, lines.TOO_LONG), "after\n"])

    def test_a_gap_is_given_before_the_line_that_follows_it(self):
        """Where the loss happened is the whole of what a gap says."""
        got = everything("before\n" + "x" * (AT_MOST + 5) + "\nafter\n")
        self.assertEqual(got, ["before\n", lines.Gap(1, lines.TOO_LONG), "after\n"])

    def test_lines_that_will_not_fit_fold_into_one_gap(self):
        """A program in this state produces one per read, and a caller logging each would be writing
        the log the loss was meant to be visible in."""
        too_long = "x" * (AT_MOST + 5) + "\n"
        self.assertEqual(everything(too_long * 3), [lines.Gap(3, lines.TOO_LONG)])

    def test_a_line_between_them_ends_the_folding(self):
        too_long = "x" * (AT_MOST + 5) + "\n"
        got = everything(too_long * 2 + "middle\n" + too_long)
        self.assertEqual(got, [lines.Gap(2, lines.TOO_LONG), "middle\n",
                               lines.Gap(1, lines.TOO_LONG)])

    def test_one_line_with_no_newline_at_all_is_read_to_the_end(self):
        """The 300 MB case, in miniature: the whole stream is one line that never ends."""
        self.assertEqual(everything("x" * (AT_MOST * 4)), [lines.Gap(1, lines.TOO_LONG)])


class AStreamThatStopsMidLine(support.Isolated):
    """A program killed mid-sentence, told apart from one that forgot a terminator."""

    def test_the_last_partial_line_is_a_gap_and_never_a_line(self):
        self.assertEqual(everything("one\ntwo"), ["one\n", lines.Gap(1, lines.UNTERMINATED)])

    def test_a_loss_of_another_kind_before_it_is_still_said(self):
        """The defect this case was written for: the finished gap was replaced rather than said, so
        a program that wrote a line too long and *then* died mid-sentence reported one loss."""
        got = everything("x" * (AT_MOST + 5) + "\ntail")
        self.assertEqual(got, [lines.Gap(1, lines.TOO_LONG),
                               lines.Gap(1, lines.UNTERMINATED)])

    def test_a_stream_ending_on_a_newline_leaves_no_gap(self):
        self.assertEqual(everything("one\n"), ["one\n"])


class SayingSoWhileItIsStillHappening(support.Isolated):
    """A gap can only be yielded between lines, and a program writing one endless line never
    reaches the next line.

    So the reader is bounded in memory and **completely silent about why nothing is arriving**,
    which is the state somebody is most likely to be staring at. `noticing` is what a caller uses to
    say so while it is still happening rather than after it stops.
    """

    def test_it_is_told_the_moment_a_line_is_refused_and_not_after_it_is_drained(self):
        heard = []

        class OneEndlessLine:
            """A stream whose line never ends. Reading past it never returns, which is the point."""

            def __init__(self):
                self.reads = 0

            def readline(self, at_most):
                self.reads += 1
                if self.reads > 3:
                    raise AssertionError("the reader read past the refusal without saying anything")
                return "x" * at_most

        with self.assertRaises(AssertionError):
            list(lines.read(OneEndlessLine(), AT_MOST, noticing=heard.append))
        self.assertEqual([lines.TOO_LONG], heard)

    def test_it_is_told_when_a_stream_stops_mid_line(self):
        heard = []
        list(lines.read(io.StringIO("one\ntwo"), AT_MOST, noticing=heard.append))
        self.assertEqual([lines.UNTERMINATED], heard)

    def test_a_caller_that_wants_none_of_it_is_the_ordinary_case(self):
        self.assertEqual(["one\n"], everything("one\n"))


if __name__ == "__main__":
    unittest.main()
