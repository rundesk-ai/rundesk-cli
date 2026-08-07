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


class WhatATurnCost(unittest.TestCase):
    """The one line that stands above an answer. Arithmetic and wording — no agent, no records."""

    def test_the_whole_line_a_person_reads(self):
        # R-DIS-17, R-DIS-33, R-DIS-24. The provider leads, then what was billed, then the clock.
        self.assertEqual(
            "codex · 2.2k input · 481 output · 78k cached · 1m elapsed",
            delivery.stats(provider="codex", input_tokens=2151, output_tokens=481,
                           cached_tokens=78000, elapsed=63))

    def test_a_brain_that_said_how_big_the_conversation_got_leads_with_that(self):
        # R-DIS-29. A footer is read to decide whether to start fresh, and none of the billed
        # quantities answers that — fresh input is a handful of tokens on any warm turn.
        self.assertEqual(
            "stand-in · 122k session · 837 output · 28s elapsed",
            delivery.stats(provider="stand-in", input_tokens=2, output_tokens=837,
                           cached_tokens=121000, context_tokens=122000, elapsed=28))

    def test_cache_writes_are_never_shown(self):
        # R-DIS-17. They stay in the turn's own record; a fourth number here buys nothing acted on.
        # There is no parameter for one at all, which is the strongest form of never showing it.
        self.assertNotIn("written", delivery.stats(provider="codex", input_tokens=10,
                                                   output_tokens=20, cached_tokens=30, elapsed=1))

    def test_a_small_count_is_not_rounded_into_a_zero(self):
        # Everything was shown in thousands once, so a thirteen-token answer reported `0k output` —
        # a measurement, stated plainly, and wrong.
        self.assertIn("13 output", delivery.stats(output_tokens=13))
        self.assertNotIn("0k", delivery.stats(output_tokens=13))

    def test_a_count_in_the_millions_is_not_shown_in_thousands(self):
        # A cache read is counted once per request, so forty of them reported `15425k cached`.
        self.assertIn("15.4M cached", delivery.stats(cached_tokens=15425000))

    def test_the_thousands_boundary_keeps_one_decimal_and_then_drops_it(self):
        self.assertIn("1k input", delivery.stats(input_tokens=1000))
        self.assertIn("2.2k input", delivery.stats(input_tokens=2151))
        self.assertIn("78k input", delivery.stats(input_tokens=78000))

    def test_elapsed_is_compact_at_seconds_minutes_and_hours(self):
        self.assertEqual("28s elapsed", delivery.stats(elapsed=28))
        self.assertEqual("1m elapsed", delivery.stats(elapsed=63))
        self.assertEqual("2h elapsed", delivery.stats(elapsed=7300))

    def test_a_turn_that_reported_no_cost_says_nothing_about_it(self):
        # Zero and unknown are different answers, and a row of zeroes is the wrong one.
        self.assertEqual("codex · 4s elapsed", delivery.stats(provider="codex", elapsed=4))

    def test_nothing_known_at_all_is_no_line_rather_than_an_empty_one(self):
        self.assertEqual("", delivery.stats())

    def test_a_measured_zero_is_still_reported(self):
        # The other half of the same rule: a brain that counted and found nothing said so.
        self.assertIn("0 output", delivery.stats(output_tokens=0))


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
        carrying = delivery.carried([str(at)])
        self.assertEqual([], carrying.refused)
        self.assertEqual(["report.csv"], [one.name for one in carrying.files])
        self.assertEqual(8, carrying.files[0].bytes)
        self.assertEqual(64, len(carrying.files[0].sha256))

    def test_one_it_cannot_open_is_a_sentence_rather_than_an_exception(self):
        # A delivery of four files of which one may not be sent is three files that still have to
        # arrive, plus a line somebody reads.
        elsewhere = self.home / "somewhere" / "missing.txt"
        mine = self.a_file()
        carrying = delivery.carried([str(elsewhere), str(mine)])
        self.assertEqual(["report.csv"], [one.name for one in carrying.files])
        self.assertEqual(1, len(carrying.refused))
        self.assertIn(str(elsewhere), carrying.refused[0])

    def test_one_file_named_twice_is_one_file(self):
        at = self.a_file()
        self.assertEqual(1, len(delivery.carried([str(at), str(at)]).files))

    def test_two_names_for_one_file_are_one_attachment(self):
        at = self.a_file()
        alias = directory.home(self.agent) / "report-alias.csv"
        alias.symlink_to(at)
        carrying = delivery.carried([str(alias), str(at)])
        self.assertEqual(1, len(carrying.files))
        self.assertEqual(at.resolve(), carrying.files[0].at)

    def test_a_link_and_provider_record_alias_are_one_attachment(self):
        at = self.a_file()
        alias = directory.home(self.agent) / "report-alias.csv"
        alias.symlink_to(at)
        prepared = delivery.prepared(f"[report]({alias})", [str(at)])
        self.assertEqual(1, len(prepared.files))
        self.assertEqual(at.resolve(), prepared.files[0].at)

    def test_no_more_of_them_are_carried_than_one_message_may_hold(self):
        named = [str(self.a_file(f"one-{nth}.txt", b"x")) for nth in range(files.PER_MESSAGE + 2)]
        carrying = delivery.carried(named)
        self.assertEqual(files.PER_MESSAGE, len(carrying.files))
        self.assertEqual(2, len(carrying.refused))

    def test_an_alias_after_the_capacity_does_not_crowd_out_or_count_as_a_refusal(self):
        named = [self.a_file(f"one-{nth}.txt", b"x") for nth in range(files.PER_MESSAGE)]
        alias = directory.home(self.agent) / "alias.txt"
        alias.symlink_to(named[0])
        extra = self.a_file("extra.txt", b"x")
        carrying = delivery.carried([*(str(one) for one in named), str(alias), str(extra)])
        self.assertEqual(files.PER_MESSAGE, len(carrying.files))
        self.assertEqual(1, len(carrying.refused))

    def test_a_file_that_moved_after_it_was_approved_is_the_adapters_to_catch(self):
        # What `carried` hands over is what the far side checks itself against, so the digest has to
        # be of the bytes that were there and not of the name.
        at = self.a_file("report.csv", b"the first")
        carrying = delivery.carried([str(at)])
        os.remove(str(at))
        self.a_file("report.csv", b"something else entirely")
        self.assertNotEqual(delivery.carried([str(at)]).files[0].sha256,
                            carrying.files[0].sha256)


class HowABrainSaysSendThis(unittest.TestCase):
    """R-CH-31. **The link is the intent**, because no brain has one to report: every shipped adapter
    refuses to emit a `file` record, each saying that a stream names files *touched* and never the one
    made for the person who asked. Until this existed the whole outbound path was built, correct, and
    unreachable — seven links of eight, with nothing able to produce a candidate."""

    def test_a_linked_file_is_taken_and_only_its_label_is_left(self):
        """**The path never reaches the room.** Left in, an answer posts the owner's own home
        directory into a chat somebody else is reading, and a reader cannot act on it anyway."""
        said, paths = delivery.declared_in("Here it is: [the chart](/home/ava/chart.png)")
        self.assertEqual(["/home/ava/chart.png"], paths)
        self.assertEqual("Here it is: the chart", said)

    def test_a_path_with_spaces_may_be_wrapped_in_angle_brackets(self):
        said, paths = delivery.declared_in("done [it](</home/ava/a file.png>)")
        self.assertEqual(["/home/ava/a file.png"], paths)
        self.assertEqual("done it", said)

    def test_a_natural_unwrapped_path_may_contain_spaces_and_parentheses(self):
        said, paths = delivery.declared_in(
            "![preview](/tmp/artifacts/team status (final).svg)")
        self.assertEqual(["/tmp/artifacts/team status (final).svg"], paths)
        self.assertEqual("preview", said)

    def test_an_image_embed_is_an_attachment_without_a_stray_mark(self):
        said, paths = delivery.declared_in("Here is ![the preview](/home/ava/screen.png)")
        self.assertEqual(["/home/ava/screen.png"], paths)
        self.assertEqual("Here is the preview", said)

    def test_a_local_file_url_is_decoded_into_its_absolute_path(self):
        said, paths = delivery.declared_in(
            "[the PDF](file:///home/ava/Quarterly%20Preview.pdf)")
        self.assertEqual(["/home/ava/Quarterly Preview.pdf"], paths)
        self.assertEqual("the PDF", said)

    def test_a_percent_encoded_plain_path_is_decoded_too(self):
        said, paths = delivery.declared_in(
            "[the PDF](/tmp/Quarterly%20Preview.pdf)")
        self.assertEqual(["/tmp/Quarterly Preview.pdf"], paths)
        self.assertEqual("the PDF", said)

    def test_a_malformed_local_file_url_is_a_safe_refusal(self):
        prepared = delivery.prepared("[broken](file:///tmp/bad%00name.png)")
        self.assertEqual([], prepared.files)
        self.assertIn("Could not attach", prepared.text)
        self.assertNotIn("/tmp/", prepared.text)

    def test_a_rejected_local_file_url_never_leaks_its_destination(self):
        for said in (
                "[broken](file:///tmp/private%0Aname.png)",
                "[broken](file:///tmp/private.png?version=1)",
                "[broken](file://localhost/tmp/private.png)"):
            with self.subTest(said=said):
                prepared = delivery.prepared(said)
                self.assertEqual([], prepared.files)
                self.assertIn("Could not attach", prepared.text)
                self.assertNotIn("file://", prepared.text)
                self.assertNotIn("/tmp/", prepared.text)

    def test_a_provider_path_with_an_unencodable_character_is_a_safe_refusal(self):
        prepared = delivery.prepared("result", ["/tmp/bad\ud800name.png"])
        self.assertEqual([], prepared.files)
        self.assertIn("Could not attach", prepared.text)
        self.assertNotIn("/tmp/", prepared.text)

    def test_an_ordinary_web_link_is_left_exactly_as_it_was(self):
        """The common case by far, and the one a wrong rule would silently mangle."""
        for said in ("see [the docs](https://example.com/x)",
                     "see [it](./relative.png)",
                     "see [it](//example.com/x)"):
            with self.subTest(said=said):
                self.assertEqual((said, []), delivery.declared_in(said))

    def test_several_files_keep_the_order_they_were_named_in(self):
        said, paths = delivery.declared_in("[a](/tmp/a.png) then [b](/tmp/b.png)")
        self.assertEqual(["/tmp/a.png", "/tmp/b.png"], paths)
        self.assertEqual("a then b", said)

    def test_an_answer_naming_no_file_is_untouched(self):
        self.assertEqual(("just words", []), delivery.declared_in("just words"))

    def test_a_link_inside_a_fence_is_an_example_and_never_a_delivery(self):
        """**A brain taught this convention will show somebody the convention.** Read as live, an
        example did two wrong things at once: it was mangled into unformatted prose, and a path that
        happened to name a real file posted it to somebody who never asked for one."""
        said = "Like this:\n```\n[report](/tmp/real.png)\n```\nThat is the syntax."
        self.assertEqual((said, []), delivery.declared_in(said))

    def test_a_real_link_beside_a_fenced_example_is_still_taken(self):
        said, paths = delivery.declared_in(
            "```\n[example](/tmp/example.png)\n```\nHere it is: [the chart](/tmp/real.png)")
        self.assertEqual(["/tmp/real.png"], paths)
        self.assertIn("[example](/tmp/example.png)", said)
        self.assertIn("Here it is: the chart", said)

    def test_an_unclosed_fence_is_wrong_in_the_safe_direction(self):
        said = "look:\n```\n[report](/tmp/real.png)"
        self.assertEqual((said, []), delivery.declared_in(said))

    def test_a_path_with_parentheses_is_taken_whole(self):
        """`Copy (1).pdf` is what an operating system names a duplicate. Stopping at the first `)`
        captured half a path and left the other half loose in the answer somebody reads."""
        said, paths = delivery.declared_in("here is [the report](/Users/joe/file(1).png) enjoy")
        self.assertEqual(["/Users/joe/file(1).png"], paths)
        self.assertEqual("here is the report enjoy", said)

    def test_naming_a_file_reads_intent_without_opening_it(self):
        """Parsing strips a private path but leaves validation to `carried` one call later."""
        said, paths = delivery.declared_in("[passwords](/etc/passwd)")
        self.assertEqual(["/etc/passwd"], paths)
        self.assertEqual("passwords", said)


if __name__ == "__main__":
    unittest.main()
