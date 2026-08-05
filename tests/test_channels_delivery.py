"""Cutting what goes out to what the platform on the other end will take.

The cutting is in one place on purpose. The build this replaces held the limit in each adapter, the
two drifted, and Slack fixed a splitting bug that Discord still has — so the case that pins the fix
is here rather than in either adapter, where it could only ever be right for one of them.

Run directly: `python3 tests/test_channels_delivery.py`
"""

import unittest

import support
from rundesk.agents import directory
from rundesk.channels import delivery, kept


class Splitting(support.Isolated):
    """No agent and no records — cutting text is arithmetic and needs neither."""

    def test_something_short_enough_is_one_message(self):
        self.assertEqual(["hello"], delivery.split("hello", 2000))

    def test_nothing_at_all_is_nothing_to_send(self):
        # A platform refuses an empty message, and the refusal arrives as a failed delivery for
        # something nobody needed sent.
        for said in ("", "   ", "\n\n"):
            with self.subTest(said=repr(said)):
                self.assertEqual([], delivery.split(said, 2000))

    def test_it_is_cut_at_a_line_boundary_when_one_is_near_enough(self):
        said = "aaaa\nbbbb\ncccc\n"
        self.assertEqual(["aaaa\nbbbb", "cccc"], delivery.split(said, 12))

    def test_no_piece_is_ever_longer_than_the_limit(self):
        said = "\n".join(f"line {nth} " + "x" * 40 for nth in range(50))
        for piece in delivery.split(said, 200):
            self.assertLessEqual(len(piece), 200)

    def test_a_boundary_too_near_the_start_is_not_taken(self):
        # **The bug Slack found and Discord still has.** One short line followed by a very long one:
        # cutting at the last newline sends the short line alone — which in the old build carried
        # the mention, so the notification was a message with nothing in it.
        said = "done\n" + "x" * 500
        pieces = delivery.split(said, 100)
        self.assertNotEqual("done", pieces[0], "a completion line was sent as a message of its own")
        self.assertEqual(100, len(pieces[0]))

    def test_everything_that_went_in_comes_out(self):
        said = "\n".join(f"line {nth}" for nth in range(200))
        rejoined = "\n".join(delivery.split(said, 120))
        for nth in range(200):
            self.assertIn(f"line {nth}", rejoined)


class SplittingAroundCode(Splitting):
    """A block split across two messages renders as one broken block and a page of plain text."""

    def test_a_fence_left_open_is_closed_and_opened_again(self):
        said = "```\n" + "\n".join("x" * 30 for _ in range(20)) + "\n```"
        pieces = delivery.split(said, 200)
        self.assertGreater(len(pieces), 1, "this case needs more than one piece to mean anything")
        self.assertTrue(pieces[0].endswith(delivery.FENCE), "the first piece left a block open")
        self.assertTrue(pieces[1].startswith(delivery.FENCE), "the second piece did not reopen it")

    def test_every_piece_of_a_split_block_is_balanced(self):
        said = "before\n```\n" + "\n".join("y" * 30 for _ in range(20)) + "\n```\nafter"
        for at, piece in enumerate(delivery.split(said, 200)):
            with self.subTest(piece=at):
                self.assertEqual(0, sum(1 for line in piece.splitlines()
                                        if line.startswith(delivery.FENCE)) % 2,
                                 "a piece was sent with a block still open in it")

    def test_text_with_no_code_in_it_gains_no_fences(self):
        said = "\n".join(f"line {nth}" for nth in range(100))
        for piece in delivery.split(said, 120):
            self.assertNotIn(delivery.FENCE, piece)


class WhereANoticeGoes(support.Isolated):

    def setUp(self):
        super().setUp()
        self.agent = "cole"
        directory.made(self.agent, "claude")

    def a_channel(self, kind="discord", told=False, place="1180"):
        kept.added(self.agent, kind, {"describes": kind, "allowed": '["2207"]'})
        if told:
            kept.telling(self.agent, kind, place)

    def test_it_goes_to_the_channel_that_was_marked(self):
        self.a_channel("discord", told=True, place="1180")
        telling = delivery.notice(self.agent, "gateway up")
        self.assertEqual("discord", telling.kind)
        self.assertEqual("1180", telling.place)
        self.assertEqual(["gateway up"], telling.pieces)

    def test_an_agent_that_tells_nobody_anything_is_not_a_failure(self):
        # Somebody who configured no notified channel asked for silence, so a caller writes nothing
        # and reports nothing rather than treating a quiet install as broken.
        self.a_channel("discord", told=False)
        self.assertIsNone(delivery.notice(self.agent, "gateway up"))

    def test_an_agent_with_no_channels_at_all_is_not_a_failure(self):
        self.assertIsNone(delivery.notice(self.agent, "gateway up"))

    def test_a_long_notice_is_cut_the_same_way_as_anything_else(self):
        self.a_channel("discord", told=True)
        telling = delivery.notice(self.agent, "\n".join("x" * 30 for _ in range(50)), at_most=200)
        self.assertGreater(len(telling.pieces), 1)
        for piece in telling.pieces:
            self.assertLessEqual(len(piece), 200)


if __name__ == "__main__":
    unittest.main()
