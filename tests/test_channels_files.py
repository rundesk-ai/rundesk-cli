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

import errno
import hashlib
import os
import re
import shutil
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


class WhatTheAdapterFetched(Files):
    """The inbound half of the seam: what an adapter staged, taken over or refused.

    The adapter is a program on the far side of a pipe, so every one of these is about a path it
    named and this side did not: where it may stand, what it may be, and whether what is behind it
    is what the platform said it would be.
    """

    def staged(self, kind="discord", message="8841", named="0", body=b"one,two\n"):
        """One file where an adapter would have put it: inside the channel's own directory."""
        at = directory.channels(self.agent) / kind / "fetched" / message / named
        at.parent.mkdir(parents=True, exist_ok=True)
        at.write_bytes(body)
        return at

    def test_it_lands_under_the_day_and_the_message_with_the_platforms_own_name(self):
        at = self.staged()
        where = files.landed(self.agent, "discord", "8841",
                             {"name": "report.csv", "at": str(at), "bytes": 8},
                             datetime(2026, 8, 5))
        self.assertEqual("report.csv", where.name)
        self.assertEqual("8841", where.parent.name)
        self.assertEqual("2026-08-05", where.parent.parent.name)
        self.assertEqual(b"one,two\n", where.read_bytes())

    def test_the_name_a_platform_gave_it_is_flattened_here_and_de_collided_here(self):
        first = files.landed(self.agent, "discord", "8841",
                             {"name": "report v2.csv", "at": str(self.staged(named="0")),
                              "bytes": 8})
        second = files.landed(self.agent, "discord", "8841",
                              {"name": "report-v2.csv", "at": str(self.staged(named="1")),
                               "bytes": 8})
        self.assertNotEqual(first, second)
        self.assertNotIn("/", first.name)

    def test_what_was_staged_is_taken_away_once_it_has_landed(self):
        at = self.staged()
        files.landed(self.agent, "discord", "8841", {"name": "report.csv", "at": str(at),
                                                     "bytes": 8})
        self.assertFalse(at.exists(), "the channel's own directory kept a second copy of it")
        self.assertFalse(at.parent.exists(), "the message's staging directory was left behind")

    def test_one_that_could_not_be_taken_over_is_still_taken_away(self):
        # A platform sending a hundred unreadable files a day would otherwise fill a disk one
        # refusal at a time.
        at = self.staged(body=b"short")
        with self.assertRaises(files.Refused):
            files.landed(self.agent, "discord", "8841", {"name": "report.csv", "at": str(at),
                                                         "bytes": 4096})
        self.assertFalse(at.exists())

    def test_a_download_that_did_not_finish_is_not_a_file_that_arrived(self):
        # A fetch cut off part way leaves a perfectly readable file of the wrong length, and the
        # agent is then handed a name it can open and half of what somebody sent it.
        at = self.staged(body=b"the first eight of many")
        with self.assertRaises(files.Refused) as refused:
            files.landed(self.agent, "discord", "8841", {"name": "report.csv", "at": str(at),
                                                         "bytes": 900})
        self.assertIn("not what was sent", str(refused.exception))

    def test_a_file_from_outside_the_channels_own_directory_is_refused(self):
        # An adapter is a program rundesk starts, and a buggy one naming somewhere else entirely
        # would otherwise have rundesk copy it into the agent's reach — and then delete it.
        elsewhere = self.home / "outside" / "secrets.txt"
        elsewhere.parent.mkdir(parents=True, exist_ok=True)
        elsewhere.write_bytes(b"not yours")
        with self.assertRaises(files.Refused):
            files.landed(self.agent, "discord", "8841", {"name": "x", "at": str(elsewhere)})
        self.assertTrue(elsewhere.exists(), "a file it refused to take was removed anyway")

    def test_another_channels_directory_is_outside_this_ones(self):
        at = self.staged(kind="slack")
        with self.assertRaises(files.Refused):
            files.landed(self.agent, "discord", "8841", {"name": "x", "at": str(at)})

    def test_a_link_standing_where_the_staged_file_should_be_is_refused(self):
        elsewhere = self.home / "outside" / "real.txt"
        elsewhere.parent.mkdir(parents=True, exist_ok=True)
        elsewhere.write_bytes(b"somebody else's")
        pointing = directory.channels(self.agent) / "discord" / "fetched" / "8841" / "0"
        pointing.parent.mkdir(parents=True, exist_ok=True)
        pointing.symlink_to(elsewhere)
        with self.assertRaises(files.Refused):
            files.landed(self.agent, "discord", "8841", {"name": "x", "at": str(pointing)})
        self.assertTrue(elsewhere.exists())

    def test_a_relative_path_is_refused_because_it_cannot_be_contained(self):
        with self.assertRaises(files.Refused):
            files.landed(self.agent, "discord", "8841", {"name": "x", "at": "fetched/8841/0"})

    def test_one_that_was_never_written_is_refused_rather_than_landed_empty(self):
        at = directory.channels(self.agent) / "discord" / "fetched" / "8841" / "0"
        at.parent.mkdir(parents=True, exist_ok=True)
        with self.assertRaises(files.Refused):
            files.landed(self.agent, "discord", "8841", {"name": "x", "at": str(at)})

    def test_one_bigger_than_a_message_may_bring_is_refused(self):
        at = self.staged(body=b"x" * (files.EACH_AT_MOST + 1))
        with self.assertRaises(files.Refused):
            files.landed(self.agent, "discord", "8841", {"name": "big.bin", "at": str(at)})


class WhatMayBeSent(Files):

    def test_a_file_in_the_agents_own_home_is_weighed_and_digested(self):
        body = b"one,two\nthree,four\n"
        at = self.a_file("report.csv", body)
        sending = files.approved(str(at))
        self.assertEqual("report.csv", sending.name)
        self.assertEqual(len(body), sending.bytes)
        self.assertEqual(hashlib.sha256(body).hexdigest(), sending.sha256)

    def test_what_a_schedule_wrote_may_be_sent(self):
        at = self.a_file("nightly.out", b"it ran\n", where=directory.schedules(self.agent))
        self.assertEqual(7, files.approved(str(at)).bytes)

    def test_what_arrived_through_a_channel_may_be_sent_back(self):
        at = self.a_file("came-in.csv", b"x\n", where=self.a_day())
        self.assertEqual(2, files.approved(str(at)).bytes)

    def test_an_ordinary_file_anywhere_on_the_computer_may_be_sent_in_place(self):
        at = self.a_file("preview.png", b"pixels", where=self.home / "computer-use")
        sending = files.approved(str(at))
        self.assertEqual(at, sending.at)
        self.assertEqual(hashlib.sha256(b"pixels").hexdigest(), sending.sha256)

    def test_an_already_oversize_file_is_refused_before_it_is_hashed(self):
        at = self.a_file("huge.bin", b"")
        with at.open("r+b") as growing:
            growing.truncate(files.EACH_AT_MOST + 1)
        weighed = files._weighed
        self.addCleanup(setattr, files, "_weighed", weighed)
        files._weighed = lambda *_args, **_kwargs: self.fail("an oversize file was hashed")
        with self.assertRaises(files.Refused):
            files.approved(str(at))

    def test_a_file_that_grows_while_read_caps_work_at_the_limit(self):
        at = self.a_file("growing.bin", b"0123456789")
        held = os.open(str(at), os.O_RDONLY)
        self.addCleanup(os.close, held)
        size, _digest = files._weighed(held, at_most=5)
        self.assertEqual(6, size)

    def test_a_file_that_grows_after_the_initial_size_check_is_refused(self):
        at = self.a_file("growing-after-check.bin", b"12345")
        limit = files.EACH_AT_MOST
        ordinary = files._ordinary_file
        self.addCleanup(setattr, files, "EACH_AT_MOST", limit)
        self.addCleanup(setattr, files, "_ordinary_file", ordinary)
        files.EACH_AT_MOST = 5

        def growing(held, named):
            how = ordinary(held, named)
            with named.open("ab") as writing:
                writing.write(b"67890")
            return how

        files._ordinary_file = growing
        with self.assertRaises(files.Refused):
            files.approved(str(at))

    def test_a_relative_path_is_refused_because_it_cannot_be_checked(self):
        with self.assertRaises(files.Refused):
            files.approved("home/report.csv")

    def test_no_special_directory_is_needed_when_a_file_is_explicitly_declared(self):
        sending = files.approved(str(directory.records(self.agent)))
        self.assertEqual(directory.records(self.agent), sending.at)

    def test_a_link_standing_where_the_file_should_be_is_resolved_once(self):
        elsewhere = self.a_file("real.txt", b"x", where=self.home / "outside")
        pointing = directory.home(self.agent) / "looks-fine.txt"
        pointing.symlink_to(elsewhere)
        sending = files.approved(str(pointing))
        self.assertEqual(elsewhere.resolve(), sending.at)
        self.assertEqual("looks-fine.txt", sending.name)

    def test_a_link_on_a_directory_above_the_file_is_canonicalized_before_approval(self):
        outside = self.home / "outside"
        outside.mkdir(parents=True, exist_ok=True)
        (outside / "real.txt").write_bytes(b"somebody else's")
        pointing = directory.home(self.agent) / "ordinary"
        pointing.symlink_to(outside, target_is_directory=True)
        sending = files.approved(str(pointing / "real.txt"))
        self.assertEqual((outside / "real.txt").resolve(), sending.at)

    def test_a_symbolic_link_loop_is_a_refusal_instead_of_an_exception(self):
        loop = directory.home(self.agent) / "loop"
        loop.symlink_to(loop)
        with self.assertRaises(files.Refused):
            files.approved(str(loop))

    def test_a_relative_step_is_refused_before_canonicalization(self):
        # A declaration must name where the file actually stands. Navigation steps make its intent
        # ambiguous even though canonicalization could produce an ordinary absolute file.
        escaping = directory.home(self.agent) / ".." / directory.RECORDS
        with self.assertRaises(files.Refused):
            files.approved(str(escaping))

    def test_a_relative_step_is_refused_however_deep_it_reaches(self):
        for said in ("home/../../../etc/passwd", "home/./notes.md", "home/../../nina/home/x"):
            with self.subTest(said=said):
                with self.assertRaises(files.Refused):
                    files.approved(str(directory.where(self.agent) / said))

    def test_the_agents_home_is_not_a_boundary_for_an_explicit_file(self):
        at = directory.home(self.agent)
        shutil.rmtree(at)
        at.symlink_to(self.home)
        directory.made("nina", "claude")
        sending = files.approved(str(directory.records("nina")))
        self.assertEqual(directory.records("nina"), sending.at)

    def test_a_hardlink_is_still_the_exact_regular_file_it_names(self):
        pointing = directory.home(self.agent) / "notes.txt"
        os.link(str(directory.records(self.agent)), str(pointing))
        sending = files.approved(str(pointing))
        self.assertEqual(pointing, sending.at)

    def test_a_named_pipe_is_refused_rather_than_waited_on(self):
        # It used to wedge whatever thread asked, for ever: opening a FIFO for reading waits for a
        # writer that never comes, and refusing it afterwards is too late because the open blocks.
        pipe = directory.home(self.agent) / "pipe"
        os.mkfifo(str(pipe))
        opened = files.os.open
        final_flags = []
        self.addCleanup(setattr, files.os, "open", opened)

        def opening(name, flags, *args, **kwargs):
            if name == pipe.name:
                final_flags.append(flags)
                flags |= os.O_NONBLOCK
            return opened(name, flags, *args, **kwargs)

        files.os.open = opening
        with self.assertRaises(files.Refused):
            files.approved(str(pipe))
        self.assertTrue(final_flags[0] & os.O_NONBLOCK)

    def test_a_file_that_is_not_there_is_refused_rather_than_reported_empty(self):
        with self.assertRaises(files.Refused):
            files.approved(str(directory.home(self.agent) / "never-written"))

    def test_a_directory_is_not_a_file_to_send(self):
        with self.assertRaises(files.Refused):
            files.approved(str(directory.home(self.agent)))

    def test_a_directory_that_may_be_passed_through_and_not_listed_still_sends_its_file(self):
        """The incident, reduced to the part that can be measured on any machine.

        Passing through a directory and reading what is in it are two different permissions, and a
        walk needs only the first. Asked for the second, an ordinary readable file standing in a
        `--x` directory was refused — and the sentence written down said a symbolic link stood
        there.
        """
        box = self.home / "search-only"
        box.mkdir(parents=True, exist_ok=True)
        at = box / "preview.png"
        at.write_bytes(b"pixels")
        self.addCleanup(box.chmod, 0o755)
        box.chmod(0o311)
        sending = files.approved(str(at))
        self.assertEqual(at, sending.at)
        self.assertEqual(hashlib.sha256(b"pixels").hexdigest(), sending.sha256)


class WhatARefusalSays(Files):
    """**Which of the things it was**, because every one of these has a different thing to go and do.

    Written for one incident: a gateway that could not open a directory was told a symbolic link
    stood at it, about a directory that was not one and a file that was an ordinary readable PNG.
    Whoever read it went looking for a link that had never been there.
    """

    #: How a refusal about permissions names the component it is about. Taken exactly, because
    #: **a parent is a prefix of its own child**: every one of these sentences opens with the whole
    #: path being sent, so asking whether the directory is mentioned somewhere in the words is
    #: answered `yes` by a sentence blaming the file underneath it. That is the defect itself, and
    #: an `assertIn` cannot see it.
    BLAMED = re.compile(r"to be sent: (.+?) (?:cannot be searched by this process"
                        r"|refuses this process by its own permissions)")

    def a_walk(self, at):
        """The walk on its own, so a link *inside* a canonical path can be put there deliberately.

        `approved` canonicalizes before it walks, so the only way a component is a link by the time
        the walk reaches it is a replacement between the two — which is exactly what the walk is
        for, and what this reproduces without a race.
        """
        with self.assertRaises(files.Refused) as refused:
            files._opened_without_following(at)
        return str(refused.exception)

    def the_component_blamed(self, said):
        """The one component a refusal about permissions actually points at, and nothing near it."""
        found = self.BLAMED.search(said)
        self.assertIsNotNone(found, f"no component is named as the one refusing: {said}")
        return found.group(1)

    def losing_its_mode(self, box):
        """Take a directory's mode away the moment the walk is holding a descriptor on it.

        **This is `O_PATH`, reproduced without Linux.** `O_SEARCH` asks for search permission when
        it opens, so macOS refuses an unsearchable directory at the directory; `O_PATH` asks for
        nothing, so Linux opens it and refuses the *child* looked up through it. A descriptor held
        across a `chmod` puts any platform in the second state, which is also the real race — a
        directory whose mode changes mid-walk — so the case is a fact about both.
        """
        opened = files.os.open
        self.addCleanup(setattr, files.os, "open", opened)

        def dropping(name, flags, *args, **kwargs):
            held = opened(name, flags, *args, **kwargs)
            if name == box.name:
                box.chmod(0o000)
            return held

        files.os.open = dropping

    def test_a_directory_the_machine_refuses_this_process_is_not_reported_as_a_link(self):
        """The incident itself: a path that resolves, an open that is refused, and no link anywhere.

        `EPERM` on an open that `resolve` had no trouble with is the shape a macOS privacy refusal
        arrives in, and it cannot be produced on a developer's machine without spending one of the
        owner's real grants — so the refusal is put where the machine would put it. What is under
        test is the sentence, and the sentence is what was wrong.
        """
        box = self.home / "downloads-like"
        box.mkdir(parents=True, exist_ok=True)
        at = box / "preview.png"
        at.write_bytes(b"pixels")
        opened = files.os.open
        self.addCleanup(setattr, files.os, "open", opened)

        def refusing(name, flags, *args, **kwargs):
            if name == box.name:
                raise PermissionError(errno.EPERM, "Operation not permitted", name)
            return opened(name, flags, *args, **kwargs)

        files.os.open = refusing
        with self.assertRaises(files.Refused) as refused:
            files.approved(str(at))
        said = str(refused.exception)
        self.assertIn("EPERM", said, f"the errno the machine answered with was lost: {said}")
        self.assertIn(str(box), said, f"the component it stopped at was not named: {said}")
        self.assertNotIn("symbolic link", said,
                         f"a refusal to open was reported as a link: {said}")
        self.assertIn("lineage", said,
                      f"nothing said the grant is this process's rather than the machine's: {said}")

    def test_a_link_on_a_component_is_still_refused_and_still_called_one(self):
        outside = self.home / "outside"
        outside.mkdir(parents=True, exist_ok=True)
        (outside / "real.txt").write_bytes(b"somebody else's")
        pointing = self.home / "swapped"
        pointing.symlink_to(outside, target_is_directory=True)
        said = self.a_walk(pointing / "real.txt")
        self.assertIn("symbolic link", said)
        self.assertIn(str(pointing), said, f"the component holding the link was not named: {said}")

    def test_a_link_where_the_file_should_be_is_still_refused_and_still_called_one(self):
        (self.home / "real.txt").write_bytes(b"somebody else's")
        pointing = self.home / "swapped.txt"
        pointing.symlink_to(self.home / "real.txt")
        said = self.a_walk(pointing)
        self.assertIn("symbolic link", said)

    def test_a_component_that_went_away_says_so_rather_than_naming_a_link(self):
        said = self.a_walk(self.home / "never-was" / "preview.png")
        self.assertIn("ENOENT", said)
        self.assertNotIn("link", said)

    def test_something_that_is_not_a_directory_says_that_rather_than_naming_a_link(self):
        (self.home / "plain.txt").write_bytes(b"x")
        said = self.a_walk(self.home / "plain.txt" / "preview.png")
        self.assertIn("ENOTDIR", said)
        self.assertNotIn("link", said)

    def test_a_directory_that_cannot_be_searched_is_named_and_not_the_file_under_it(self):
        """The component the open failed on is not the component holding the mode bit.

        Held on a directory it may not search, the walk is refused when it looks the *file* up, so
        `EACCES` arrives carrying the file's name while the file itself is an ordinary readable
        PNG. Blaming it sends whoever reads the refusal to change permissions on the one thing that
        never refused anything.
        """
        box = self.home / "loses-its-mode"
        box.mkdir(parents=True, exist_ok=True)
        at = box / "preview.png"
        at.write_bytes(b"pixels")
        self.addCleanup(box.chmod, 0o755)
        self.losing_its_mode(box)
        said = self.a_walk(at)
        self.assertEqual(str(box), self.the_component_blamed(said),
                         f"the file was blamed for the mode bit on the directory above it: {said}")
        self.assertIn("EACCES", said, f"the errno the machine answered with was lost: {said}")
        self.assertNotIn("symbolic link", said, f"a mode bit was reported as a link: {said}")

    def test_a_directory_that_cannot_be_searched_is_named_and_not_the_directory_under_it(self):
        """The same again one component higher, where the name that arrives is a directory's.

        Worth its own case because the two are different call sites — the walk's loop and its final
        open — and a correction applied to one of them looks complete from the other.
        """
        inner = self.home / "outer" / "inner"
        inner.mkdir(parents=True, exist_ok=True)
        at = inner / "preview.png"
        at.write_bytes(b"pixels")
        self.addCleanup(inner.parent.chmod, 0o755)
        self.losing_its_mode(inner.parent)
        said = self.a_walk(at)
        self.assertEqual(str(inner.parent), self.the_component_blamed(said),
                         f"a directory was blamed for the mode bit on the one above it: {said}")
        self.assertIn("EACCES", said, f"the errno the machine answered with was lost: {said}")

    def test_a_directory_granting_no_search_is_named_the_same_on_either_platform(self):
        """One directory that grants nothing, and the refusal has to name it wherever it runs.

        `O_SEARCH` refuses this directory at itself and `O_PATH` opens it and refuses its child, so
        without asking which happened the same machine state produces two different sentences that
        blame two different components — and only one of them is true. This is the case that fails
        on Linux and passes on macOS if the two are not reconciled.
        """
        box = self.home / "no-search-at-all"
        box.mkdir(parents=True, exist_ok=True)
        at = box / "preview.png"
        at.write_bytes(b"pixels")
        self.addCleanup(box.chmod, 0o755)
        box.chmod(0o000)
        said = self.a_walk(at)
        self.assertEqual(str(box), self.the_component_blamed(said),
                         f"the component named is not the directory that refuses: {said}")
        self.assertIn("EACCES", said, f"the errno the machine answered with was lost: {said}")

    def test_a_file_that_may_not_be_read_is_still_blamed_on_itself(self):
        """The other side of the same question, so the correction cannot become blame-the-parent.

        A directory that searches perfectly and a file that refuses to open is the ordinary case,
        and moving *that* refusal onto the directory would be the same defect facing the other way.
        """
        at = self.home / "unreadable.png"
        at.write_bytes(b"pixels")
        self.addCleanup(at.chmod, 0o644)
        at.chmod(0o000)
        if os.geteuid() == 0:
            self.skipTest("a mode bit refuses nothing to root, so there is no refusal to word")
        said = self.a_walk(at)
        self.assertEqual(str(at), self.the_component_blamed(said),
                         f"a file's own mode bit was blamed on the directory above it: {said}")
        self.assertIn("EACCES", said, f"the errno the machine answered with was lost: {said}")

    def test_a_path_that_will_not_resolve_keeps_what_the_machine_said(self):
        box = self.home / "unsearchable"
        box.mkdir(parents=True, exist_ok=True)
        at = box / "preview.png"
        at.write_bytes(b"pixels")
        named = str(at)
        self.addCleanup(box.chmod, 0o755)
        box.chmod(0o600)                  # readable, not searchable: `resolve` itself is refused
        with self.assertRaises(files.Refused) as refused:
            files.approved(named)
        self.assertIn("EACCES", str(refused.exception))


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
