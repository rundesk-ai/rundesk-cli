"""Cutting what goes out to what the platform on the other end will take, and vetting what it carries.

The cutting is in one place on purpose. The build this replaces held the limit in each adapter, the
two drifted, and Slack fixed a splitting bug that Discord still has — so the case that pins the fix
is here rather than in either adapter, where it could only ever be right for one of them.

**Two of these are measurements rather than opinions.** `test_a_piece_carrying_an_open_block_still_
fits` is the exact text and the exact limit that came back four characters over — and an oversized
piece is not a cosmetic fault: the adapter refuses one outright as rundesk having failed to split,
and the delivery is dropped with nothing to retry it.

Run directly: `python3 tests/test_channels_delivery.py`
"""

import os
import unittest

import support
from rundesk.agents import directory
from rundesk.channels import delivery, files, kept


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

    def test_a_cut_that_lands_on_nothing_is_not_sent_as_an_empty_message(self):
        # A platform refuses an empty message, and the module says one is never made. Text that
        # begins with a newline used to produce exactly that as its first piece.
        for piece in delivery.split("\nsomething worth saying", 1):
            self.assertTrue(piece.strip(), "an empty piece was handed back to be delivered")

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

    def test_a_piece_carrying_an_open_block_still_fits(self):
        # **The measurement.** Room was kept for reopening a block at the start of a piece and never
        # for closing it again at the end, so this exact text at this exact limit came back as
        # [2002, 2004, 1008] — every piece past 2000, which the adapter refuses outright.
        said = delivery.FENCE + "\n" + "a" * 1994 + "\n" + "b" * 3000
        for at, piece in enumerate(delivery.split(said, 2000)):
            with self.subTest(piece=at):
                self.assertLessEqual(len(piece), 2000,
                                     "a piece wearing a fence was handed back past the limit")

    def test_the_last_piece_wears_its_reopening_fence_inside_the_limit_too(self):
        # The same overshoot arrived at from the other end, and it needs its own case: the tail is
        # not cut by the loop at all, so nothing kept room there for the fence that reopens the
        # block it continues. A hundred and ninety-two characters after the fence is what leaves a
        # remainder of exactly the limit, which is where four more characters are four too many.
        said = delivery.FENCE + "\n" + "a" * 192
        for at, piece in enumerate(delivery.split(said, 100)):
            with self.subTest(piece=at):
                self.assertLessEqual(len(piece), 100,
                                     "the last piece was handed back past the limit")


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


class WhatADeliveryMayCarry(support.Isolated):
    """The second of the three checks a file passes on its way out. The adapter makes the third."""

    def setUp(self):
        super().setUp()
        self.agent = "cole"
        directory.made(self.agent, "claude")

    def a_file(self, name="report.csv", body=b"one,two\n", where=None):
        at = (where or directory.home(self.agent)) / name
        at.parent.mkdir(parents=True, exist_ok=True)
        at.write_bytes(body)
        return at

    def test_a_file_the_agent_may_send_comes_back_weighed_and_digested(self):
        at = self.a_file()
        carrying = delivery.carried(self.agent, [str(at)])
        self.assertEqual([], carrying.refused)
        self.assertEqual(["report.csv"], [one.name for one in carrying.files])
        self.assertEqual(8, carrying.files[0].bytes)
        self.assertEqual(64, len(carrying.files[0].sha256))

    def test_one_it_may_not_send_is_a_sentence_rather_than_an_exception(self):
        # A delivery of four files of which one may not be sent is three files that still have to
        # arrive, plus a line somebody reads.
        elsewhere = self.a_file("theirs.txt", b"x", where=self.home / "somewhere")
        mine = self.a_file()
        carrying = delivery.carried(self.agent, [str(elsewhere), str(mine)])
        self.assertEqual(["report.csv"], [one.name for one in carrying.files])
        self.assertEqual(1, len(carrying.refused))
        self.assertIn(str(elsewhere), carrying.refused[0])

    def test_one_file_named_twice_is_one_file(self):
        at = self.a_file()
        self.assertEqual(1, len(delivery.carried(self.agent, [str(at), str(at)]).files))

    def test_no_more_of_them_are_carried_than_one_message_may_hold(self):
        named = [str(self.a_file(f"one-{nth}.txt", b"x")) for nth in range(files.PER_MESSAGE + 2)]
        carrying = delivery.carried(self.agent, named)
        self.assertEqual(files.PER_MESSAGE, len(carrying.files))
        self.assertEqual(2, len(carrying.refused))

    def test_a_file_that_moved_after_it_was_approved_is_the_adapters_to_catch(self):
        # What `carried` hands over is what the far side checks itself against, so the digest has to
        # be of the bytes that were there and not of the name.
        at = self.a_file("report.csv", b"the first")
        carrying = delivery.carried(self.agent, [str(at)])
        os.remove(str(at))
        self.a_file("report.csv", b"something else entirely")
        self.assertNotEqual(delivery.carried(self.agent, [str(at)]).files[0].sha256,
                            carrying.files[0].sha256)


if __name__ == "__main__":
    unittest.main()
