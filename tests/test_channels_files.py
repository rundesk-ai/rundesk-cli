"""What may cross the channel seam in each direction, and what is swept when nobody is looking.

Real files, real symbolic links, real directories. The outbound half is a security check and a
stand-in for a filesystem would prove nothing about it — the whole question is what the operating
system does when a component of a path is a link, which is not a thing that can be mocked into being
true.

**The case that matters most is the link on a *parent*.** Checking only the final component leaves
the interesting attack working perfectly, and it is the one somebody writing this in a hurry gets
wrong.

Run directly: `python3 tests/test_channels_files.py`
"""

import hashlib
import os
import unittest
from datetime import date, datetime

import support
from rundesk.agents import directory
from rundesk.channels import files


class Files(support.Isolated):
    """An agent with somewhere for its channels and its home to stand."""

    def setUp(self):
        super().setUp()
        self.agent = "cole"
        directory.made(self.agent, "claude")

    def a_file(self, name="report.csv", body=b"one,two\n", where=None):
        at = (where or directory.home(self.agent)) / name
        at.parent.mkdir(parents=True, exist_ok=True)
        at.write_bytes(body)
        return at

    def a_day(self, kind="discord", day="2026-08-05"):
        at = directory.channels(self.agent) / kind / files.ARRIVED_IN / day
        at.mkdir(parents=True, exist_ok=True)
        return at


class WhereWhatArrivesLands(Files):

    def test_the_day_is_in_the_path_so_a_sweep_can_read_it(self):
        at = files.arrived_at(self.agent, "discord", "8841", datetime(2026, 8, 5, 14, 0))
        self.assertEqual("8841", at.name)
        self.assertEqual("2026-08-05", at.parent.name)
        self.assertEqual(files.ARRIVED_IN, at.parent.parent.name)

    def test_a_message_id_from_a_platform_is_flattened_like_any_other_name(self):
        at = files.arrived_at(self.agent, "discord", "../../etc", datetime(2026, 8, 5))
        self.assertNotIn("..", at.parts)


class WhatArrivesIsWrittenSafely(Files):

    def test_a_name_that_could_reach_out_of_the_directory_cannot(self):
        into = self.a_day()
        at = files.written(into, "../../../etc/passwd", b"nope")
        self.assertEqual(into, at.parent)
        self.assertNotIn("..", at.name)

    def test_two_names_that_flatten_alike_do_not_overwrite_each_other(self):
        # The one sanitising alone misses. In the previous build the second overwrote the first,
        # and the agent then opened exactly the name it was given and read somebody else's file.
        into = self.a_day()
        first = files.written(into, "report v2.csv", b"the first")
        second = files.written(into, "report-v2.csv", b"the second")
        self.assertNotEqual(first, second)
        self.assertEqual(b"the first", first.read_bytes())
        self.assertEqual(b"the second", second.read_bytes())

    def test_a_name_that_flattens_to_nothing_still_gets_one(self):
        at = files.written(self.a_day(), "///", b"something")
        self.assertTrue(at.name)

    def test_a_file_bigger_than_one_message_may_bring_is_refused(self):
        with self.assertRaises(files.Refused):
            files.written(self.a_day(), "big.bin", b"x" * (files.EACH_AT_MOST + 1))


class WhatMayBeSent(Files):

    def test_a_file_in_the_agents_own_home_is_weighed_and_digested(self):
        body = b"one,two\nthree,four\n"
        at = self.a_file("report.csv", body)
        sending = files.approved(self.agent, str(at))
        self.assertEqual("report.csv", sending.name)
        self.assertEqual(len(body), sending.bytes)
        self.assertEqual(hashlib.sha256(body).hexdigest(), sending.sha256)

    def test_what_a_schedule_wrote_may_be_sent(self):
        at = self.a_file("nightly.out", b"it ran\n", where=directory.schedules(self.agent))
        self.assertEqual(7, files.approved(self.agent, str(at)).bytes)

    def test_what_arrived_through_a_channel_may_be_sent_back(self):
        at = self.a_file("came-in.csv", b"x\n", where=self.a_day())
        self.assertEqual(2, files.approved(self.agent, str(at)).bytes)

    def test_a_relative_path_is_refused_because_it_cannot_be_checked(self):
        with self.assertRaises(files.Refused):
            files.approved(self.agent, "home/report.csv")

    def test_the_agents_own_records_may_never_be_sent(self):
        # `state.db` is the agent's entire history, and it stands beside the directories that may.
        with self.assertRaises(files.Refused):
            files.approved(self.agent, str(directory.records(self.agent)))

    def test_somewhere_else_entirely_is_refused(self):
        elsewhere = self.a_file("secrets.txt", b"x", where=self.home / "somewhere")
        with self.assertRaises(files.Refused):
            files.approved(self.agent, str(elsewhere))

    def test_another_agents_home_is_refused(self):
        directory.made("nina", "claude")
        theirs = self.a_file("theirs.csv", b"x", where=directory.home("nina"))
        with self.assertRaises(files.Refused):
            files.approved(self.agent, str(theirs))

    def test_a_link_standing_where_the_file_should_be_is_refused(self):
        elsewhere = self.a_file("real.txt", b"x", where=self.home / "outside")
        pointing = directory.home(self.agent) / "looks-fine.txt"
        pointing.symlink_to(elsewhere)
        with self.assertRaises(files.Refused):
            files.approved(self.agent, str(pointing))

    def test_a_link_on_a_directory_above_the_file_is_refused(self):
        # **The case that decides whether this check is real.** Opening only the last component
        # with O_NOFOLLOW leaves this working perfectly: the name is an ordinary file, and a
        # directory two steps up is what redirects the whole path.
        outside = self.home / "outside"
        outside.mkdir(parents=True, exist_ok=True)
        (outside / "real.txt").write_bytes(b"somebody else's")
        pointing = directory.home(self.agent) / "ordinary"
        pointing.symlink_to(outside, target_is_directory=True)
        with self.assertRaises(files.Refused):
            files.approved(self.agent, str(pointing / "real.txt"))

    def test_a_relative_step_cannot_walk_out_of_a_permitted_root(self):
        # **A working exploit before this was refused.** `Path.parents` collapses nothing, so this
        # path has `home/` among its parents and read as contained; `O_NOFOLLOW` refuses a symlink
        # and `..` is not one, so the walk stepped out and returned the agent's whole history.
        escaping = directory.home(self.agent) / ".." / directory.RECORDS
        with self.assertRaises(files.Refused):
            files.approved(self.agent, str(escaping))

    def test_a_relative_step_is_refused_however_deep_it_reaches(self):
        for said in ("home/../../../etc/passwd", "home/./notes.md", "home/../../nina/home/x"):
            with self.subTest(said=said):
                with self.assertRaises(files.Refused):
                    files.approved(self.agent, str(directory.where(self.agent) / said))

    def test_a_file_that_is_not_there_is_refused_rather_than_reported_empty(self):
        with self.assertRaises(files.Refused):
            files.approved(self.agent, str(directory.home(self.agent) / "never-written"))

    def test_a_directory_is_not_a_file_to_send(self):
        with self.assertRaises(files.Refused):
            files.approved(self.agent, str(directory.home(self.agent)))


class WhatIsSweptAway(Files):

    def test_a_day_older_than_the_keeping_goes(self):
        old = self.a_day(day="2026-01-01")
        (old / "8841").mkdir()
        gone = files.swept(self.agent, "discord", keeping=60, today=date(2026, 8, 5))
        self.assertEqual([old], gone)
        self.assertFalse(old.exists())

    def test_a_day_inside_the_keeping_stays(self):
        recent = self.a_day(day="2026-08-01")
        self.assertEqual([], files.swept(self.agent, "discord", keeping=60,
                                         today=date(2026, 8, 5)))
        self.assertTrue(recent.exists())

    def test_the_edge_is_counted_in_whole_days(self):
        for day, still_there in (("2026-06-07", True), ("2026-06-06", False)):
            with self.subTest(day=day):
                at = self.a_day(day=day)
                files.swept(self.agent, "discord", keeping=60, today=date(2026, 8, 5))
                self.assertEqual(still_there, at.exists())

    def test_a_directory_that_is_not_a_day_is_somebody_elses(self):
        mine = self.a_day(day="notes")
        files.swept(self.agent, "discord", keeping=1, today=date(2026, 8, 5))
        self.assertTrue(mine.exists())

    def test_a_date_that_is_shaped_right_and_is_not_one_is_left_alone(self):
        mine = self.a_day(day="2026-02-31")
        files.swept(self.agent, "discord", keeping=1, today=date(2026, 8, 5))
        self.assertTrue(mine.exists())

    def test_a_channel_that_has_never_received_anything_sweeps_nothing_and_does_not_fail(self):
        self.assertEqual([], files.swept(self.agent, "discord"))

    def test_keeping_nothing_is_refused_rather_than_taken_as_remove_everything(self):
        at = self.a_day(day="2026-01-01")
        self.assertEqual([], files.swept(self.agent, "discord", keeping=0))
        self.assertTrue(at.exists())

    def test_a_day_it_cannot_remove_does_not_end_the_sweep(self):
        # Sweeping is tidying, and tidying may never end a gateway.
        stuck = self.a_day(day="2026-01-01")
        (stuck / "8841").mkdir()
        os.chmod(stuck, 0o500)
        self.addCleanup(os.chmod, stuck, 0o700)
        later = self.a_day(day="2026-01-02")
        gone = files.swept(self.agent, "discord", keeping=60, today=date(2026, 8, 5))
        self.assertIn(later, gone)


if __name__ == "__main__":
    unittest.main()
