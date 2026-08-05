"""The bottom layer: keeping a small file safely, staging a replacement, and printing a table.

Nothing here knows what rundesk is, and neither do these cases — they are written against files and
strings rather than against installs, which is the point of the layer and the thing worth keeping
true. `test_layers.py` enforces that mechanically; this proves the functions actually work.

The weight is on `jsonfile`, because it is the only thing in the product holding somebody's state in
a place two processes can reach at once, and because both of its guarantees fail silently when they
fail at all: a half-written file reads as a corrupt one, and a corrupt one read as empty is state
already lost by the time anybody looks.

Run directly: `python3 tests/test_utils.py`
"""

import contextlib
import datetime
import fcntl
import io
import os
import select
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

import support
from rundesk.utils import files, locking, logs, programs, scripts, terminal
from rundesk.utils.terminal import as_table


class ATty(io.StringIO):
    """A stream that says it is a terminal, so the watching case can be driven without one.

    A real terminal cannot be had inside a test runner, and the alternative — asserting only the
    no-colour path — would leave everything this module actually emits unproven.
    """

    def isatty(self) -> bool:
        return True


def env_as_it_was(case, *names) -> None:
    """Put these variables back exactly as they were, whatever the case does to them.

    Restored rather than removed: `TERM` is a real variable a real shell set, and a case that took it
    away and never put it back would leave every later case in the same process running somewhere
    slightly different from where it thought it was.
    """
    was = {name: os.environ.get(name) for name in names}

    def back() -> None:
        for name, value in was.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    case.addCleanup(back)


def printed(head, rows, into=None) -> str:
    """What `as_table` puts on the screen, caught rather than eyeballed."""
    out = into if into is not None else io.StringIO()
    with contextlib.redirect_stdout(out):
        as_table(head, rows)
    return out.getvalue()


class ReadingASmallFile(support.Isolated):
    """`read` — three answers, and the two that must never be collapsed into one."""

    def setUp(self):
        super().setUp()
        self.at = self.home / "somewhere.json"
        self.at.parent.mkdir(parents=True, exist_ok=True)

    def test_a_file_nobody_wrote_says_so(self):
        self.assertEqual((files.MISSING, None), files.read_json(self.at))

    def test_a_file_that_will_not_parse_says_something_else(self):
        # The distinction the whole module is built on: an unreadable file is not an empty one.
        self.at.write_text("{ broken")
        self.assertEqual((files.UNREADABLE, None), files.read_json(self.at))

    def test_an_empty_file_is_unreadable_rather_than_an_empty_value(self):
        # Zero bytes is not `{}` — it is a write that did not happen, and reading it as an empty
        # value is how the next write erases what was there.
        self.at.write_text("")
        self.assertEqual(files.UNREADABLE, files.read_json(self.at)[0])

    def test_a_directory_where_a_file_should_be_is_unreadable(self):
        self.at.mkdir()
        self.assertEqual(files.UNREADABLE, files.read_json(self.at)[0])

    def test_a_file_that_cannot_be_opened_is_unreadable_rather_than_missing(self):
        if os.geteuid() == 0:
            self.skipTest("root can read a file with no permissions")
        files.write_json(self.at, {"a": 1})
        self.at.chmod(0o000)
        self.addCleanup(self.at.chmod, 0o600)
        self.assertEqual(files.UNREADABLE, files.read_json(self.at)[0])

    def test_a_value_that_was_written_comes_back(self):
        files.write_json(self.at, {"a": 1, "b": ["two", 3]})
        self.assertEqual((files.READ, {"a": 1, "b": ["two", 3]}), files.read_json(self.at))

    def test_it_reads_whatever_json_holds_and_not_only_a_mapping(self):
        for value in ([1, 2, 3], "a string", 7, True, None):
            with self.subTest(value=value):
                files.write_json(self.at, value)
                self.assertEqual((files.READ, value), files.read_json(self.at))

    def test_the_broken_answer_never_carries_a_value(self):
        # A caller that checked the value rather than the answer would otherwise see `None` from a
        # corrupt file and from a file holding `null`, which are not the same thing.
        self.at.write_text("{ broken")
        self.assertIsNone(files.read_json(self.at)[1])


class WritingASmallFile(support.Isolated):
    """`write` — whole, renamed into place, and never leaving a piece behind."""

    def setUp(self):
        super().setUp()
        self.at = self.home / "somewhere.json"

    def test_what_was_written_can_be_read_back(self):
        files.write_json(self.at, {"a": 1})
        self.assertEqual((files.READ, {"a": 1}), files.read_json(self.at))

    def test_it_makes_the_directory_it_is_writing_into(self):
        deep = self.home / "one" / "two" / "somewhere.json"
        files.write_json(deep, {"a": 1})
        self.assertTrue(deep.is_file())

    def test_it_leaves_no_piece_of_itself_behind(self):
        files.write_json(self.at, {"a": 1})
        self.assertEqual([], [one.name for one in self.at.parent.iterdir()
                              if one.name.startswith(".")])

    def test_it_stages_beside_the_target_so_the_rename_stays_on_one_filesystem(self):
        # `os.replace` is atomic only within a filesystem. Staging in a temp directory would be a
        # rename across one, which is a copy — and a copy is exactly what this avoids.
        seen = []
        really = os.replace

        def watching(src, dst):
            seen.append((Path(src).parent, Path(dst).parent))
            return really(src, dst)

        with mock.patch.object(files.os, "replace", side_effect=watching):
            files.write_json(self.at, {"a": 1})
        self.assertEqual([(self.at.parent, self.at.parent)], seen)

    def test_writing_again_replaces_what_was_there(self):
        files.write_json(self.at, {"a": 1})
        files.write_json(self.at, {"b": 2})
        self.assertEqual((files.READ, {"b": 2}), files.read_json(self.at))

    def test_it_is_written_so_a_person_can_read_and_diff_it(self):
        # Sorted and indented on purpose: this file is edited by hand and shown in bug reports.
        files.write_json(self.at, {"b": 2, "a": 1})
        self.assertEqual('{\n  "a": 1,\n  "b": 2\n}\n', self.at.read_text())

    def test_it_ends_with_a_newline(self):
        files.write_json(self.at, {"a": 1})
        self.assertTrue(self.at.read_text().endswith("\n"))


class ChangingOneSafely(support.Isolated):
    """`changing` — the read, the decision and the write, with nothing able to get between them."""

    def setUp(self):
        super().setUp()
        self.at = self.home / "somewhere.json"
        self.at.parent.mkdir(parents=True, exist_ok=True)

    def test_it_hands_over_what_is_there_and_writes_back_what_is_left(self):
        files.write_json(self.at, {"a": 1})
        with files.changing_json(self.at, empty={}) as held:
            self.assertEqual({"a": 1}, held[0])
            held[0] = {"a": 2}
        self.assertEqual((files.READ, {"a": 2}), files.read_json(self.at))

    def test_a_file_nobody_wrote_hands_over_what_the_caller_called_empty(self):
        with files.changing_json(self.at, empty={"fresh": True}) as held:
            self.assertEqual({"fresh": True}, held[0])
        self.assertEqual((files.READ, {"fresh": True}), files.read_json(self.at))

    def test_nothing_writes_over_a_value_it_could_not_read(self):
        # The guarantee. Handing back a blank slate here is how state is lost: something writes the
        # blank down, and what was there is gone with nothing having said so.
        self.at.write_text("{ broken")
        with self.assertRaises(ValueError):
            with files.changing_json(self.at, empty={}):
                pass
        self.assertEqual("{ broken", self.at.read_text(), "the unreadable value was overwritten")

    def test_a_decision_that_raised_writes_nothing(self):
        files.write_json(self.at, {"a": 1})
        with self.assertRaises(RuntimeError):
            with files.changing_json(self.at, empty={}) as held:
                held[0] = {"a": 999}
                raise RuntimeError("the caller thought better of it")
        self.assertEqual((files.READ, {"a": 1}), files.read_json(self.at))

    def test_leaving_the_value_alone_writes_it_back_unchanged(self):
        files.write_json(self.at, {"a": 1})
        with files.changing_json(self.at, empty={}):
            pass
        self.assertEqual((files.READ, {"a": 1}), files.read_json(self.at))

    def test_the_lock_is_its_own_file_and_never_the_value(self):
        # Locking the value's own file would truncate or create the thing being protected.
        with files.changing_json(self.at, empty={"a": 1}):
            self.assertTrue(self.at.with_name(f".{self.at.name}.lock").exists())

    def test_it_makes_the_directory_it_is_changing_in(self):
        deep = self.home / "one" / "two" / "somewhere.json"
        with files.changing_json(deep, empty={"a": 1}):
            pass
        self.assertTrue(deep.is_file())


class WhenSomethingElseIsChangingTheSameFile(support.Isolated):
    """A wait with an end, and a name for the thing that was waited for.

    Moved here with `jsonfile` itself: the ceiling belongs to the file-keeping module, and the case
    proving a *command* survives it stays with that command.
    """

    def setUp(self):
        super().setUp()
        self.at = self.home / "somewhere.json"
        self.at.parent.mkdir(parents=True, exist_ok=True)
        # Shortened so the ceiling can be met in milliseconds. Read inside `_taken` on every call
        # rather than bound at import, which is what makes this reachable at all.
        self.addCleanup(setattr, locking, "WAITING_SECONDS", locking.WAITING_SECONDS)
        locking.WAITING_SECONDS = 0.1

    def held_by_something_else(self):
        """Take the lock through a second descriptor, which flock treats as another holder."""
        lock = self.at.with_name(f".{self.at.name}.lock")
        holding = os.open(lock, os.O_CREAT | os.O_RDWR, 0o600)
        self.addCleanup(os.close, holding)
        fcntl.flock(holding, fcntl.LOCK_EX)
        return holding

    def test_it_gives_up_and_says_so_rather_than_waiting_for_ever(self):
        # A blocking wait cannot be interrupted and names nothing while it waits, so the command
        # somebody typed simply never returns. Without the ceiling this case does not fail — it
        # hangs, which is the failure being prevented.
        self.held_by_something_else()
        began = time.monotonic()
        with self.assertRaises(files.Stuck) as refused:
            with files.changing_json(self.at, empty={}):
                pass
        self.assertLess(time.monotonic() - began, 5, "it waited far past its own ceiling")
        self.assertIn(str(self.at), str(refused.exception))

    def test_the_caller_chooses_how_long_is_too_long(self):
        """How long is too long depends on what is held, so the caller says rather than the module.

        Measured before this existed: copying a 120MB `data/` of sixty thousand files held the
        install lock for 9.2 seconds against a ceiling of 10 — so a real install with a database per
        agent would have had an ordinary `backups save` refuse a concurrent command. The ceiling is
        not a constant one number can be right for.
        """
        self.held_by_something_else()
        lock = self.at.with_name(f".{self.at.name}.lock")

        began = time.monotonic()
        with self.assertRaises(locking.Stuck) as refused:
            with locking.only_one(lock, "a big copy", waiting=0.4):
                pass
        waited = time.monotonic() - began

        # It waited its own ceiling and not the module's, which is four times shorter.
        self.assertGreater(waited, 0.3, "it used WAITING_SECONDS and ignored what it was handed")
        self.assertLess(waited, 3, "it waited past the ceiling it was given")
        self.assertIn("0.4 seconds", str(refused.exception))
        self.assertIn("a big copy", str(refused.exception))

    def test_giving_up_does_not_claim_to_know_why(self):
        """The message a person reads when a large backup is running must not call it a fault.

        It said "this is not a busy machine — it is something that has gone wrong", which was true
        of a lock over one small JSON file and false of one held across a directory being copied.
        A confident wrong answer at the moment the machine is working correctly.
        """
        self.held_by_something_else()
        lock = self.at.with_name(f".{self.at.name}.lock")

        with self.assertRaises(locking.Stuck) as refused:
            with locking.only_one(lock, "this install", waiting=0.05):
                pass

        said = str(refused.exception)
        self.assertNotIn("gone wrong", said)
        self.assertIn("may still be running", said)

    def test_a_directory_that_moves_is_given_far_longer_than_a_file(self):
        # Not an arbitrary number: the ceiling for a whole-directory operation has to outlast the
        # 9.2 seconds one was measured taking, with room for an install many times larger.
        self.assertGreaterEqual(locking.WHILE_A_DIRECTORY_MOVES, 60.0)
        self.assertGreater(locking.WHILE_A_DIRECTORY_MOVES, locking.WAITING_SECONDS)

    def test_it_writes_nothing_when_it_could_not_have_the_file(self):
        files.write_json(self.at, {"a": 1})
        self.held_by_something_else()
        with self.assertRaises(files.Stuck):
            with files.changing_json(self.at, empty={}) as held:
                held[0] = {"a": 2}
        self.assertEqual((files.READ, {"a": 1}), files.read_json(self.at))

    def test_a_lock_that_comes_free_is_simply_taken(self):
        # The ordinary case, so the ceiling cannot be mistaken for a refusal to share.
        holding = self.held_by_something_else()
        fcntl.flock(holding, fcntl.LOCK_UN)
        with files.changing_json(self.at, empty={}) as held:
            held[0] = {"a": 3}
        self.assertEqual((files.READ, {"a": 3}), files.read_json(self.at))

    def test_the_lock_is_let_go_of_when_the_change_is_done(self):
        with files.changing_json(self.at, empty={"a": 1}):
            pass
        with files.changing_json(self.at, empty={}) as held:
            self.assertEqual({"a": 1}, held[0])

    def test_the_lock_is_let_go_of_even_when_the_change_raised(self):
        # The kernel drops it when the descriptor closes however the block ended, and `_only_one`
        # closes in a `finally` — otherwise one failed command would wedge every later one.
        with self.assertRaises(RuntimeError):
            with files.changing_json(self.at, empty={}):
                raise RuntimeError("no")
        with files.changing_json(self.at, empty={"after": True}) as held:
            self.assertEqual({"after": True}, held[0])


class WhetherANameMayBecomeAPath(support.Isolated):
    """`files.name_trouble` — a name becomes a directory, the lock beside it, and the log under it.

    Checked when a name is accepted rather than at each of the places it later turns into a path,
    because those are the places that cannot see what happened. The build this replaces recorded the
    failure exactly: a name containing a separator would put all three somewhere else entirely.
    """

    def test_an_ordinary_name_is_fine(self):
        for said in ("alan", "my-agent", "agent_1", "Alan", "a"):
            with self.subTest(said=said):
                self.assertEqual("", files.name_trouble(said))

    def test_nothing_is_not_a_name(self):
        for said in ("", "   ", "\t", "\n"):
            with self.subTest(said=repr(said)):
                self.assertNotEqual("", files.name_trouble(said))

    def test_a_separator_is_refused_because_it_moves_the_directory(self):
        for said in ("a/b", "/a", "a/", "a\\b", "a\x00b"):
            with self.subTest(said=repr(said)):
                why = files.name_trouble(said)
                self.assertNotEqual("", why, f"{said!r} would land somewhere else entirely")

    def test_the_directory_and_its_parent_are_not_names(self):
        # Anything written "under" these is written over something else.
        self.assertIn("directory", files.name_trouble("."))
        self.assertIn("directory", files.name_trouble(".."))

    def test_a_leading_dot_is_refused(self):
        # Staging entries and lock files are dotfiles, so a name starting with one could collide
        # with the machinery keeping it — and every walk in this layer skips them.
        for said in (".hidden", ".a.lock", ".incoming"):
            with self.subTest(said=said):
                self.assertIn("dot", files.name_trouble(said))

    def test_a_control_character_is_refused(self):
        # It cannot be typed back, cannot be read in a listing, and a terminal escape in a name is
        # a way to make output claim something it is not.
        for said in ("a\nb", "a\tb", "a\x1b[31mb", "a\x7fb"):
            with self.subTest(said=repr(said)):
                self.assertIn("control character", files.name_trouble(said))

    def test_a_name_the_filesystem_would_refuse_is_refused_with_a_sentence(self):
        self.assertEqual("", files.name_trouble("a" * files.LONGEST))
        self.assertIn("longer than", files.name_trouble("a" * (files.LONGEST + 1)))

    def test_length_is_counted_in_bytes_because_that_is_what_the_limit_counts(self):
        # One accented letter is two bytes, so a name well under the limit in characters can be
        # over it on disk — and finding that out as an errno three directories deep is no use.
        said = "é" * (files.LONGEST // 2 + 1)
        self.assertLess(len(said), files.LONGEST)
        self.assertIn("longer than", files.name_trouble(said))

    def test_what_a_person_may_reasonably_want_is_not_refused(self):
        # This module has an opinion about paths, not about names. Spaces and other languages work
        # on a filesystem and somebody may reasonably want them.
        for said in ("my agent", "Ada Lovelace", "agente", "エージェント", "café"):
            with self.subTest(said=said):
                self.assertEqual("", files.name_trouble(said))

    def test_it_answers_with_a_sentence_rather_than_a_code(self):
        # Every caller has to tell somebody what to type instead, and one left to invent the
        # wording is one that invents a different wording from everybody else.
        why = files.name_trouble("a/b")
        self.assertIn("name", why)
        self.assertGreater(len(why.split()), 4, "that is not a sentence anybody can act on")


class TakingTurns(support.Isolated):
    """`locking.only_one` — one at a time, with a ceiling, and re-entrant within one process."""

    def setUp(self):
        super().setUp()
        self.at = self.home / ".a.lock"
        self.addCleanup(setattr, locking, "WAITING_SECONDS", locking.WAITING_SECONDS)
        locking.WAITING_SECONDS = 0.1

    def held_by_something_else(self):
        holding = os.open(self.at, os.O_CREAT | os.O_RDWR, 0o600)
        self.addCleanup(os.close, holding)
        fcntl.flock(holding, fcntl.LOCK_EX)
        return holding

    def test_one_holder_at_a_time(self):
        self.held_by_something_else()
        with self.assertRaises(locking.Stuck) as refused:
            with locking.only_one(self.at, "the thing"):
                pass
        self.assertIn("the thing", str(refused.exception))

    def test_it_gives_up_rather_than_waiting_for_ever(self):
        self.held_by_something_else()
        began = time.monotonic()
        with self.assertRaises(locking.Stuck):
            with locking.only_one(self.at):
                pass
        self.assertLess(time.monotonic() - began, 5)

    def test_a_lock_that_comes_free_is_simply_taken(self):
        holding = self.held_by_something_else()
        fcntl.flock(holding, fcntl.LOCK_UN)
        with locking.only_one(self.at):
            pass

    def test_it_is_let_go_of_afterwards(self):
        with locking.only_one(self.at):
            pass
        with locking.only_one(self.at):
            pass

    def test_it_is_let_go_of_even_when_the_block_raised(self):
        with self.assertRaises(RuntimeError):
            with locking.only_one(self.at):
                raise RuntimeError("no")
        with locking.only_one(self.at):
            pass

    def test_holding_it_twice_in_one_process_does_not_wait_for_itself(self):
        # `flock` is held per open file description, so a second `open` in the same process
        # conflicts with the first exactly as another process would. An operation that holds this
        # and calls another that takes it would otherwise wait for itself until the ceiling.
        with locking.only_one(self.at):
            with locking.only_one(self.at):
                with locking.only_one(self.at):
                    pass

    def still_held(self) -> bool:
        """Whether anything holds the lock, asked through a descriptor of its own.

        Behaviour rather than bookkeeping: reaching into the counter would pin the shape of a
        private dict, and that shape has already changed once.
        """
        holding = os.open(self.at, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(holding, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(holding, fcntl.LOCK_UN)
            return False
        except OSError:
            return True
        finally:
            os.close(holding)

    def test_an_inner_block_ending_does_not_let_go_for_the_outer_one(self):
        with locking.only_one(self.at):
            with locking.only_one(self.at):
                pass
            self.assertTrue(self.still_held(), "an inner block released the outer one's lock")
        self.assertFalse(self.still_held())

    def test_another_thread_does_not_walk_into_a_lock_this_one_holds(self):
        # Counted per file alone, a second thread would find a count already there, take the fast
        # path, and never touch `flock` — two callers inside a section built to hold one. Nesting
        # is about a call stack, and a call stack belongs to a thread.
        what_happened = []

        def somebody_else():
            try:
                with locking.only_one(self.at):
                    what_happened.append("walked straight in")
            except locking.Stuck:
                what_happened.append("waited its turn")

        with locking.only_one(self.at):
            other = threading.Thread(target=somebody_else)
            other.start()
            other.join(5)
        self.assertEqual(["waited its turn"], what_happened)

    def test_the_same_lock_reached_by_another_name_is_the_same_lock(self):
        # Two spellings of one file are one file. Counted by the spelling, a symlinked root would
        # miss its own count, take a real `flock` on a descriptor this thread already holds, and
        # wait out the whole ceiling for itself.
        through = self.home / "by-another-name"
        through.symlink_to(self.home)
        with locking.only_one(self.at):
            with locking.only_one(through / self.at.name):
                pass

    def test_it_makes_the_directory_the_lock_stands_in(self):
        deep = self.home / "not" / "yet" / ".a.lock"
        with locking.only_one(deep):
            pass
        self.assertTrue(deep.exists())


class SettlingTheDirectory(support.Isolated):
    """`_settle` — asking the filesystem to record the rename, not only the bytes it moved."""

    def test_it_settles_a_directory_that_is_there(self):
        self.assertIsNone(files._settle(self.home))

    def test_a_directory_that_is_not_there_is_not_an_error(self):
        # Best-effort on purpose: durability is not worth turning a completed write into a failure.
        self.assertIsNone(files._settle(self.home / "never-made"))


class WhetherANameIsStaging(support.Isolated):
    """`staged` — what a walk has to skip, and what it must not."""

    def test_the_names_a_swap_uses_are_staging(self):
        for name in (files.INCOMING.format(name="app"), files.OUTGOING.format(name="app")):
            with self.subTest(name=name):
                self.assertTrue(files.staged(name))

    def test_an_ordinary_name_is_not(self):
        for name in ("app", "data", "2026-08-04T03-00-00Z", "README.md"):
            with self.subTest(name=name):
                self.assertFalse(files.staged(name))

    def test_a_hidden_file_that_is_not_staging_is_not(self):
        # `.gitignore` is not a swap in flight, and a walk that skipped it would be a move that
        # silently left one of the owner's files behind.
        for name in (".gitignore", ".DS_Store", ".config.json.lock"):
            with self.subTest(name=name):
                self.assertFalse(files.staged(name))

    def test_a_name_ending_that_way_without_the_leading_dot_is_not(self):
        # Somebody's own directory called `notes.incoming` is theirs, not a swap's.
        self.assertFalse(files.staged("notes.incoming"))
        self.assertFalse(files.staged("notes.outgoing"))

    def test_the_two_names_a_swap_uses_are_told_apart_from_each_other(self):
        self.assertNotEqual(files.INCOMING.format(name="app"), files.OUTGOING.format(name="app"))


class DiscardingAStagingEntry(support.Isolated):
    """`discard` — removes whatever kind of thing it was, and never raises."""

    def test_it_removes_a_directory(self):
        at = self.home / "a-directory"
        (at / "below").mkdir(parents=True)
        files.discard(at)
        self.assertFalse(at.exists())

    def test_it_removes_a_file(self):
        at = self.home / "a-file"
        at.write_text("something")
        files.discard(at)
        self.assertFalse(at.exists())

    def test_it_removes_a_link_without_following_it(self):
        # A link to a directory answers `is_dir()`, so removing it as one would delete what it
        # points at — which is somebody's real directory and was never the thing being staged.
        real = self.home / "the-real-one"
        (real / "below").mkdir(parents=True)
        link = self.home / "a-link"
        link.symlink_to(real)
        files.discard(link)
        self.assertFalse(link.exists() or link.is_symlink())
        self.assertTrue((real / "below").is_dir(), "it followed the link and deleted the target")

    def test_it_removes_a_link_pointing_at_nothing(self):
        link = self.home / "a-broken-link"
        link.symlink_to(self.home / "never-made")
        files.discard(link)
        self.assertFalse(link.is_symlink())

    def test_something_that_is_not_there_is_not_an_error(self):
        self.assertIsNone(files.discard(self.home / "never-made"))

    def test_it_does_not_raise_when_it_cannot_remove(self):
        # Litter is not worth turning a completed operation into a reported failure.
        if os.geteuid() == 0:
            self.skipTest("root may remove from a directory with no write permission")
        at = self.home / "held" / "a-file"
        at.parent.mkdir(parents=True)
        at.write_text("something")
        at.parent.chmod(0o500)
        self.addCleanup(at.parent.chmod, 0o700)
        self.assertIsNone(files.discard(at))


class ATerminalThatIsWatching(support.Isolated):
    """`wanted` — the four ways to say whether anything should be emitted at all."""

    def setUp(self):
        super().setUp()
        env_as_it_was(self, "NO_COLOR", "FORCE_COLOR", "TERM")
        for name in ("NO_COLOR", "FORCE_COLOR", "TERM"):
            os.environ.pop(name, None)

    def test_a_stream_that_is_not_a_terminal_gets_nothing(self):
        # The ordinary case for a pipe, a file, and every case in this suite.
        self.assertFalse(terminal.wanted(io.StringIO()))

    def test_a_stream_that_is_a_terminal_does(self):
        self.assertTrue(terminal.wanted(ATty()))

    def test_no_color_set_to_anything_at_all_means_no(self):
        # Including empty: the convention is that the variable *being set* is the answer, and a
        # person who exported it to nothing still meant it.
        for said in ("1", "", "no", "yes"):
            with self.subTest(NO_COLOR=said):
                os.environ["NO_COLOR"] = said
                self.assertFalse(terminal.wanted(ATty()))

    def test_force_color_means_yes_even_down_a_pipe(self):
        os.environ["FORCE_COLOR"] = "1"
        self.assertTrue(terminal.wanted(io.StringIO()))

    def test_no_color_beats_force_color(self):
        # Somebody who has turned this off globally has turned it off.
        os.environ["NO_COLOR"] = "1"
        os.environ["FORCE_COLOR"] = "1"
        self.assertFalse(terminal.wanted(ATty()))

    def test_a_terminal_that_cannot_do_this_gets_nothing(self):
        os.environ["TERM"] = "dumb"
        self.assertFalse(terminal.wanted(ATty()))

    def test_a_stream_that_cannot_say_is_not_a_yes(self):
        # Being unable to ask is not a quiet form of yes — the same rule the rest of the product
        # keeps, in the one place where getting it wrong only corrupts output.
        self.assertFalse(terminal.wanted(object()))
        closed = io.StringIO()
        closed.close()
        self.assertFalse(terminal.wanted(closed))

    def test_it_is_answered_on_every_call_and_never_bound_at_import(self):
        # The defect this is written against: a module that decided once, when it was imported,
        # answers about the world as it was before any test or any caller could change it.
        watching = ATty()
        self.assertTrue(terminal.wanted(watching))
        os.environ["NO_COLOR"] = "1"
        self.assertFalse(terminal.wanted(watching), "the answer was decided before the call")

    def test_it_asks_about_stdout_when_it_is_given_nothing(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertFalse(terminal.wanted())
        with contextlib.redirect_stdout(ATty()):
            self.assertTrue(terminal.wanted())


class WearingAStyle(support.Isolated):
    """`paint` and the five named ways of calling it."""

    def setUp(self):
        super().setUp()
        env_as_it_was(self, "NO_COLOR", "FORCE_COLOR")
        os.environ.pop("NO_COLOR", None)
        os.environ["FORCE_COLOR"] = "1"

    def test_it_wears_the_style_it_was_given(self):
        self.assertEqual("\x1b[31mFAILED\x1b[0m", terminal.paint("FAILED", "red"))

    def test_several_at_once_are_one_sequence_rather_than_nested_ones(self):
        self.assertEqual("\x1b[1;31mFAILED\x1b[0m", terminal.paint("FAILED", "bold", "red"))

    def test_each_named_one_is_the_style_it_says(self):
        for named, code in ((terminal.bold, "1"), (terminal.dim, "2"), (terminal.red, "31"),
                            (terminal.green, "32"), (terminal.yellow, "33")):
            with self.subTest(style=named.__name__):
                self.assertEqual(f"\x1b[{code}mx\x1b[0m", named("x"))

    def test_nobody_watching_gets_exactly_the_characters(self):
        # A script reading this wants the value, and an escape sequence in a captured name is not
        # decoration — it is a name that matches nothing.
        del os.environ["FORCE_COLOR"]
        self.assertEqual("FAILED", terminal.paint("FAILED", "red", stream=io.StringIO()))
        self.assertEqual("FAILED", terminal.red("FAILED", stream=io.StringIO()))

    def test_it_always_puts_the_terminal_back(self):
        self.assertTrue(terminal.paint("x", "red").endswith(terminal.RESET))

    def test_nothing_to_style_is_left_alone(self):
        self.assertEqual("", terminal.paint("", "red"))
        self.assertEqual("x", terminal.paint("x"))

    def test_a_style_that_is_not_one_is_refused_rather_than_dropped(self):
        # Dropping it would give back unstyled text, which looks exactly like the ordinary
        # nobody-is-watching answer — so the typo would be invisible to whoever made it.
        with self.assertRaises(ValueError) as refused:
            terminal.paint("x", "puce")
        self.assertIn("puce", str(refused.exception))

    def test_a_style_that_is_not_one_is_refused_even_with_nobody_watching(self):
        del os.environ["FORCE_COLOR"]
        with self.assertRaises(ValueError):
            terminal.paint("x", "puce", stream=io.StringIO())


class ReadingWhatIsThere(support.Isolated):
    """`plain` and `width` — what a machine gets, and what a person sees."""

    def test_plain_takes_every_sequence_out(self):
        self.assertEqual("FAILED", terminal.plain("\x1b[1;31mFAILED\x1b[0m"))

    def test_plain_leaves_ordinary_text_exactly_as_it_is(self):
        self.assertEqual("2026-08-04T03-00-00Z", terminal.plain("2026-08-04T03-00-00Z"))

    def test_width_is_what_a_person_sees_and_not_how_long_it_is(self):
        worn = "\x1b[1;31mFAILED\x1b[0m"
        self.assertEqual(6, terminal.width(worn))
        self.assertNotEqual(len(worn), terminal.width(worn))

    def test_width_of_ordinary_text_is_its_length(self):
        self.assertEqual(4, terminal.width("data"))


class StagingACopyOfSomething(support.Isolated):
    """`stage_copy` — one entry copied beside a target under a name no finished thing wears."""

    def setUp(self):
        super().setUp()
        self.into = self.home / "into"
        self.into.mkdir()

    def test_it_copies_a_directory_under_the_staged_name(self):
        entry = self.home / "a-directory"
        (entry / "below").mkdir(parents=True)
        (entry / "below" / "thing").write_text("kept")

        landed = files.stage_copy(entry, self.into)

        self.assertEqual(self.into / ".a-directory.incoming", landed)
        self.assertEqual("kept", (landed / "below" / "thing").read_text())

    def test_it_copies_a_file(self):
        entry = self.home / "a-file"
        entry.write_text("kept")
        self.assertEqual("kept", files.stage_copy(entry, self.into).read_text())

    def test_it_copies_a_link_as_a_link_rather_than_following_it(self):
        # `is_dir()` answers True for a link pointing at a directory, so a copy that asked only that
        # would walk through it and duplicate the tree on the other side — silently, and only for
        # the owner who had one.
        real = self.home / "the-real-one"
        (real / "below").mkdir(parents=True)
        entry = self.home / "a-link"
        entry.symlink_to(real)

        landed = files.stage_copy(entry, self.into)

        self.assertTrue(landed.is_symlink())
        self.assertFalse((landed / "below").is_dir() and not landed.is_symlink())

    def test_it_clears_a_stale_staging_entry_first(self):
        # Litter from a run that died is not a reason for the next one to fail.
        entry = self.home / "a-directory"
        (entry / "wanted").mkdir(parents=True)
        stale = self.into / ".a-directory.incoming"
        (stale / "left-behind").mkdir(parents=True)

        landed = files.stage_copy(entry, self.into)

        self.assertTrue((landed / "wanted").is_dir())
        self.assertFalse((landed / "left-behind").exists())

    def test_it_leaves_out_what_it_was_told_to(self):
        entry = self.home / "a-directory"
        entry.mkdir()
        (entry / "wanted").write_text("yes")
        (entry / "__pycache__").mkdir()

        landed = files.stage_copy(entry, self.into, ignore=lambda _where, names:
                            {one for one in names if one == "__pycache__"})

        self.assertTrue((landed / "wanted").is_file())
        self.assertFalse((landed / "__pycache__").exists())

    def test_what_it_lands_is_a_staging_name_and_not_a_finished_one(self):
        entry = self.home / "a-file"
        entry.write_text("kept")
        self.assertTrue(files.staged(files.stage_copy(entry, self.into).name))


class PrintingATable(support.Isolated):
    """`as_table` — columns to their widest cell, and nothing at all when there is nothing."""

    def test_columns_line_up_to_their_widest_cell(self):
        out = printed(("WHAT", "IS"), [("a", "1"), ("a-much-longer-name", "2")])
        first, second, third = out.splitlines()
        self.assertTrue(first.startswith("WHAT" + " " * 15))
        self.assertEqual(second.index("1"), third.index("2"))

    def test_the_heading_is_printed_above_the_rows(self):
        out = printed(("WHAT", "IS"), [("a", "1")])
        self.assertEqual(2, len(out.splitlines()))
        self.assertTrue(out.startswith("WHAT"))

    def test_a_heading_wider_than_its_column_still_lines_up(self):
        out = printed(("AN-EXTREMELY-WIDE-HEADING", "IS"), [("a", "1")])
        head, row = out.splitlines()
        self.assertEqual(head.index("IS"), row.index("1"))

    def test_nothing_at_all_is_printed_when_there_are_no_rows(self):
        # Not even the heading: a heading over an empty table reads as a listing that found nothing
        # and told you the shape of what it did not find. Whoever called this says the sentence.
        self.assertEqual("", printed(("WHAT", "IS"), []))

    def test_no_line_ends_in_spaces(self):
        for line in printed(("WHAT", "IS"), [("a-much-longer-name", "1"), ("a", "2")]).splitlines():
            with self.subTest(line=line):
                self.assertEqual(line, line.rstrip())

    def test_a_single_column_is_a_table_too(self):
        out = printed(("BACKUP",), [("2026-08-04T03-00-00Z",)])
        self.assertEqual(["BACKUP", "2026-08-04T03-00-00Z"], out.splitlines())

    def test_nothing_is_emitted_when_nobody_is_watching(self):
        # Everything else in this suite depends on this being true, and a script reading a listing
        # depends on it more.
        self.assertNotIn("\x1b", printed(("WHAT", "IS"), [("a", "1")]))

    def test_the_heading_is_bold_when_somebody_is_watching(self):
        head, row = printed(("WHAT", "IS"), [("a", "1")], into=ATty()).splitlines()
        self.assertTrue(head.startswith("\x1b["))
        self.assertEqual("WHAT  IS", terminal.plain(head))
        self.assertNotIn("\x1b", row, "an ordinary row was styled")

    def test_columns_line_up_when_a_cell_is_wearing_something(self):
        # The defect this exists to prevent: padding by `len()` counts the characters that draw
        # nothing, so the column is correct for plain text and ragged for anything styled — and
        # ragged only on somebody's real terminal, never in a captured test.
        worn = "\x1b[31ma\x1b[0m"
        head, first, second = printed(("WHAT", "IS"), [(worn, "1"), ("a-longer-cell", "2")]
                                      ).splitlines()
        self.assertEqual(terminal.plain(first).index("1"), terminal.plain(second).index("2"))
        self.assertEqual(terminal.plain(head).index("IS"), terminal.plain(first).index("1"))


class RunningAProgramThatAnswers(support.Isolated):
    """`programs.run` — the three answers `subprocess` gives as an exit code and two exceptions."""

    def test_a_program_that_ran_says_what_it_said(self):
        ended = programs.run([sys.executable, "-c", "print('hello')"], 10)
        self.assertEqual(0, ended.code)
        self.assertEqual("hello\n", ended.out)
        self.assertIsNone(ended.trouble)

    def test_a_program_that_failed_is_not_a_program_that_did_not_run(self):
        ended = programs.run([sys.executable, "-c", "import sys; sys.exit(3)"], 10)
        self.assertEqual(3, ended.code)
        self.assertIsNone(ended.trouble, "a program that ran and disagreed has no trouble")
        self.assertNotEqual(0, ended.code)

    def test_a_program_that_was_never_there_has_no_exit_code(self):
        # Reported as an exit code, this says the program ran and disagreed — a different fact
        # about the machine, which leads somebody somewhere else entirely.
        ended = programs.run([str(self.home / "never-installed")], 10)
        self.assertIsNone(ended.code)
        self.assertIn(programs.DID_NOT_START, ended.trouble)

    def test_a_program_that_would_not_finish_is_its_own_answer(self):
        ended = programs.run([sys.executable, "-c", "import time; time.sleep(30)"], 0.3)
        self.assertIsNone(ended.code)
        self.assertIn(programs.WOULD_NOT_FINISH, ended.trouble)

    def test_what_it_managed_to_say_before_it_hung_comes_back(self):
        ended = programs.run(
            [sys.executable, "-c", "import sys,time; print('said'); sys.stdout.flush(); time.sleep(30)"],
            # Generous on purpose: the sleep is never reached either way, so a wide ceiling costs
            # nothing, and a narrow one asks a loaded machine to start an interpreter in 500ms.
            3.0)
        self.assertIn("said", ended.out)

    def test_standard_input_is_never_inherited(self):
        # A program reading a terminal nobody is watching waits for ever, holding whatever its
        # parent held. Closed always, so reading it ends rather than hangs.
        ended = programs.run([sys.executable, "-c", "import sys; print(len(sys.stdin.read()))"], 10)
        self.assertEqual("0\n", ended.out)

    def test_what_it_wrote_to_the_error_stream_is_kept_apart(self):
        ended = programs.run([sys.executable, "-c", "import sys; sys.stderr.write('wrong')"], 10)
        self.assertEqual("", ended.out)
        self.assertIn("wrong", ended.err)

    def test_it_runs_where_it_was_told_to(self):
        ended = programs.run([sys.executable, "-c", "import os; print(os.getcwd())"], 10,
                             where=self.home)
        self.assertEqual(str(self.home), ended.out.strip())

    def test_a_child_holding_the_pipe_does_not_hold_the_answer(self):
        # The classic one: the program starts something of its own and exits immediately, and the
        # child inherits the capture pipe. Reading until the pipe closes waits for the child, not
        # the program — so a program that finished at once is reported as one that would not
        # finish, and the child is left running with nobody holding its id.
        began = time.monotonic()
        ended = programs.run(
            [sys.executable, "-c",
             "import subprocess, sys, warnings;"
             "warnings.simplefilter('ignore', ResourceWarning);"
             "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])"], 5.0)
        self.assertLess(time.monotonic() - began, 4.0,
                        "it waited on the child rather than on the program")
        self.assertIsNone(ended.trouble)
        self.assertEqual(0, ended.code)

    def test_a_program_that_could_not_be_started_is_said_rather_than_raised(self):
        for argv in ([str(self.home / "never-installed")], [], [str(self.home)]):
            with self.subTest(argv=argv):
                ended = programs.run(argv, 5.0)
                self.assertIsNone(ended.code)
                self.assertIn(programs.DID_NOT_START, ended.trouble)

    def test_nothing_the_program_does_comes_back_as_an_exception(self):
        # The whole point: "it was not there" is an answer to report, not a traceback to catch
        # again at every call site.
        for argv in ([str(self.home / "nope")], [sys.executable, "-c", "raise SystemExit(9)"]):
            with self.subTest(argv=argv):
                self.assertIsInstance(programs.run(argv, 10), programs.Ran)


class AProgramThatKeepsRunning(support.Isolated):
    """`start`, `alive` and `stop` — a gateway is not a command that answers."""

    #: How long these cases wait for a child before calling it a failure. Short, because every one
    #: of these children is a `python3 -c` that prints a line or sleeps: if five seconds were not
    #: enough, the answer is not more seconds.
    PATIENCE = 5.0

    def setUp(self):
        super().setUp()
        self.log = self.home / "logs" / "gateway.log"
        self.started = []
        self.addCleanup(self.stop_everything)

    def stop_everything(self):
        for pid in self.started:
            programs.stop(pid, 0.5, 1.0)

    def given_running(self, body: str) -> int:
        pid = programs.start([sys.executable, "-c", body], self.log)
        self.started.append(pid)
        return pid

    def test_a_long_lived_program_that_could_not_start_says_so_once(self):
        # Five different exceptions from the standard library for the same thing a caller has the
        # same response to. `run` says it in the answer it returns; a start has two outcomes rather
        # than three, so it says it by raising exactly one named thing.
        for argv, log in (
            ([str(self.home / "never-installed")], self.log),
            ([sys.executable, "-c", "pass"], self.home),          # the log path is a directory
            ([], self.log),
            ([str(self.home)], self.log),                          # not executable
        ):
            with self.subTest(argv=argv, log=str(log)):
                with self.assertRaises(programs.CouldNotStart):
                    programs.start(argv, log)

    def test_it_starts_and_is_alive(self):
        pid = self.given_running("import time; time.sleep(30)")
        self.assertTrue(programs.alive(pid))

    def test_what_it_says_is_appended_to_the_log(self):
        self.given_running("print('the gateway is up')")
        self.assertTrue(support.waited_until(
            lambda: self.log.exists() and "the gateway is up" in self.log.read_text(),
            self.PATIENCE))

    def test_the_error_stream_lands_in_the_same_log(self):
        self.given_running("import sys; sys.stderr.write('went wrong\\n')")
        self.assertTrue(support.waited_until(
            lambda: self.log.exists() and "went wrong" in self.log.read_text(), self.PATIENCE))

    def test_a_restart_adds_to_the_history_rather_than_replacing_it(self):
        self.given_running("print('first')")
        self.assertTrue(
            support.waited_until(lambda: "first" in self.log.read_text(), self.PATIENCE))
        self.given_running("print('second')")
        self.assertTrue(
            support.waited_until(lambda: "second" in self.log.read_text(), self.PATIENCE))
        self.assertIn("first", self.log.read_text(), "the log was replaced, not appended to")

    def test_it_is_started_in_a_session_of_its_own(self):
        # The flag everything else rests on: its own session and process group, so signalling the
        # group reaches everything it started.
        pid = self.given_running("import time; time.sleep(30)")
        self.assertEqual(pid, os.getpgid(pid), "it is not the leader of its own group")
        self.assertNotEqual(os.getpgrp(), os.getpgid(pid))

    def test_it_does_not_wait_on_a_terminal_nobody_is_watching(self):
        self.given_running("import sys; print('read', len(sys.stdin.read()))")
        self.assertTrue(support.waited_until(
            lambda: self.log.exists() and "read 0" in self.log.read_text(), self.PATIENCE))

    def test_stopping_it_stops_everything_it_started(self):
        # The reason for the session. Without it the child outlives the stop with nothing left
        # holding its id, so nobody can ever stop it — which is how a machine ends up with agent
        # processes running that no command anywhere can reach.
        marker = self.home / "the-child-is-up"
        pid = self.given_running(
            "import subprocess, sys, time, pathlib, warnings\n"
            "warnings.simplefilter('ignore', ResourceWarning)\n"
            "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
            f"pathlib.Path({str(marker)!r}).write_text(str(child.pid))\n"
            "time.sleep(60)\n")
        self.assertTrue(support.waited_until(marker.exists, self.PATIENCE),
                        "the child never started")
        child = int(marker.read_text())
        self.assertTrue(programs.alive(child))

        self.assertEqual("", programs.stop(pid, 2.0, 2.0))

        self.assertTrue(support.waited_until(lambda: not programs.alive(pid), self.PATIENCE))
        self.assertTrue(support.waited_until(lambda: not programs.alive(child), self.PATIENCE),
                        "the child outlived the stop, and nothing is left holding its id")

    def test_it_asks_before_it_insists(self):
        # A program that stops either way cannot tell the two apart, so this one proves which
        # signal arrived: it handles SIGTERM by tidying up and leaving. Killed outright, the note
        # is never written — and a gateway would lose whatever it was midway through.
        #
        # It says when its handler is installed, and this waits for that rather than for the
        # process to exist. A pid is alive from the instant of the fork, long before the
        # interpreter behind it has reached `signal.signal` — waiting on the wrong one sends the
        # signal into the gap and the default action takes the process with the handler unused.
        ready = self.home / "the-handler-is-installed"
        goodbye = self.home / "it-shut-down-tidily"
        pid = self.given_running(
            "import signal, sys, time, pathlib\n"
            "def leaving(*_):\n"
            f"    pathlib.Path({str(goodbye)!r}).write_text('tidied up')\n"
            "    sys.exit(0)\n"
            "signal.signal(signal.SIGTERM, leaving)\n"
            f"pathlib.Path({str(ready)!r}).write_text('ready')\n"
            "time.sleep(60)\n")
        self.assertTrue(support.waited_until(ready.exists, self.PATIENCE),
                        "the handler was never installed")

        self.assertEqual("", programs.stop(pid, 3.0, 2.0))

        self.assertTrue(goodbye.exists(), "it was killed outright rather than asked first")

    def test_a_program_that_ignores_being_asked_is_told(self):
        pid = self.given_running(
            "import signal, time;"
            "signal.signal(signal.SIGTERM, signal.SIG_IGN);"
            "time.sleep(60)")
        self.assertTrue(support.waited_until(lambda: programs.alive(pid), self.PATIENCE))
        self.assertEqual("", programs.stop(pid, 0.3, 3.0))
        self.assertFalse(programs.alive(pid))

    def test_a_child_that_exited_is_reaped_rather_than_left_a_zombie(self):
        # The surprising half is asserted first, because it is the reason `stop` reaps at all: a
        # child that has already exited is *still there* until somebody collects it, and a zombie
        # answers signal 0 exactly like a running process. A stop that only watched would wait out
        # its whole ceiling and then report a program still running that had exited immediately.
        #
        # This case caught its own predecessor: written as "wait until it is not alive", it could
        # never come true, and it had been passing only because the condition was mistyped into one
        # that was always true.
        pid = self.given_running("pass")
        self.assertTrue(programs.alive(pid))

        self.assertEqual("", programs.stop(pid, 2.0, 1.0),
                         "a program that has already gone is the state that was asked for")

        self.assertFalse(programs.alive(pid), "it was left in the table")

    def test_a_survivor_in_the_group_is_not_a_clean_stop(self):
        # The one that reported success while abandoning things. The leader dies to the first
        # signal; a sibling ignores it. Watching only the recorded pid, this returns "" in
        # milliseconds — and the sibling is then unreachable for ever, because the only id anybody
        # wrote down is the one that is now gone.
        stubborn = self.home / "the-stubborn-one-is-up"
        pid = self.given_running(
            "import os, signal, subprocess, sys, time, pathlib, warnings\n"
            "warnings.simplefilter('ignore', ResourceWarning)\n"
            "child = subprocess.Popen([sys.executable, '-c',\n"
            "  \"import signal, time, sys, pathlib;\"\n"
            "  \"signal.signal(signal.SIGTERM, signal.SIG_IGN);\"\n"
            f"  \"pathlib.Path({str(stubborn)!r}).write_text('up');\"\n"
            "  \"time.sleep(60)\"])\n"
            "time.sleep(60)\n")
        self.assertTrue(support.waited_until(stubborn.exists, self.PATIENCE),
                        "the stubborn child never started")

        self.assertEqual("", programs.stop(pid, 0.5, 3.0))

        # Nothing may be left in the group once this has said it stopped.
        with self.assertRaises(ProcessLookupError):
            os.killpg(pid, 0)

    def test_a_child_that_exited_on_its_own_stops_reading_as_alive(self):
        # Without collecting it, `alive` answers True for ever: a zombie answers signal 0 exactly
        # like a running program. A supervisor shaped `while alive(pid)` would spin on a program
        # that finished in a millisecond, and every short-lived child would hold a table slot.
        pid = self.given_running("pass")
        self.assertTrue(support.waited_until(lambda: not programs.alive(pid), self.PATIENCE),
                        "it read as alive long after it had exited")

    def test_a_leader_that_has_already_been_collected_still_stops_its_group(self):
        # The ordinary shape of a program that backgrounds something: the launcher starts its
        # worker and exits at once. Once that leader has been collected `getpgid` can no longer
        # resolve it — but the group it led outlives it and still holds the worker. Reading "cannot
        # ask" as "nothing left" said stopped in milliseconds and abandoned the worker.
        pid = programs.start(["sh", "-c", "sleep 60 & exit 0"], self.log)
        self.started.append(pid)
        self.assertTrue(support.waited_until(lambda: not programs.alive(pid), self.PATIENCE),
                        "the leader never exited")

        self.assertEqual("", programs.stop(pid, 2.0, 2.0))

        with self.assertRaises(ProcessLookupError):
            os.killpg(pid, 0)

    def test_stopping_this_command_s_own_group_is_refused(self):
        # `killpg` on our own group signals this very process and everything beside it. Reachable
        # by an honest mistake — a recorded id reused by something started from this shell.
        why = programs.stop(os.getpid(), 1.0, 1.0)
        self.assertIn("own process group", why)
        self.assertTrue(programs.alive(os.getpid()), "it signalled the test runner")

    def test_nothing_signals_a_process_that_could_not_be_one(self):
        for pid in (0, 1, -1):
            with self.subTest(pid=pid):
                self.assertFalse(programs.alive(pid))
                if pid <= 1:
                    self.assertNotEqual("", programs.stop(pid, 1.0, 1.0))

    def test_being_alive_is_about_a_number_and_not_an_identity(self):
        # Stated as a case so the limit is written down: ids are reused, and whoever recorded one
        # owns proving it is still the same program.
        pid = self.given_running("import time; time.sleep(30)")
        self.assertTrue(programs.alive(pid))
        self.assertFalse(programs.alive(2 ** 22))


class AProgramThisOneTalksTo(support.Isolated):
    """`talking` — a program that keeps running *and* is spoken to, which `start` deliberately is not.

    The third shape in the module. `run` waits for an answer and `start` detaches to a file; this
    keeps both ends of a conversation open for the life of a gateway, which is the one thing the
    block comment above `start` refuses to hand out by accident — because a pipe nobody drains fills
    and the program writing into it blocks for ever.

    So the last two cases here are a pair, and the second is the reason the first matters.
    """

    PATIENCE = 5.0

    def setUp(self):
        super().setUp()
        self.errors = self.home / "channels" / "discord" / "stderr.log"
        self.talking = []
        self.addCleanup(self.stop_everything)

    def stop_everything(self):
        for one in self.talking:
            for end in (one.stdout, one.stdin):
                with contextlib.suppress(OSError):
                    end.close()
            programs.stop(one.pid, 0.5, 1.0)

    def given_talking(self, body: str) -> programs.Talking:
        one = programs.talking([sys.executable, "-u", "-c", body], self.errors)
        self.talking.append(one)
        return one

    def a_line_from(self, stream, patience: float = 0.0) -> str:
        """One line, or a failure — and never a wait with no end.

        `readline()` on a pipe blocks for ever when the answer never comes, so a case written
        against a thing that stops answering does not fail, it **hangs**, and takes the whole run
        with it while saying nothing about why. Measured the first time these were broken on
        purpose: with line buffering removed, the run had to be killed at two minutes.

        `select` says only that a byte is there rather than that a whole line is, which is enough
        for children that print one short line at a time and is written down so nobody later reads
        it as more than it is.
        """
        ready, _, _ = select.select([stream], [], [], patience or self.PATIENCE)
        self.assertTrue(ready, "nothing was said within the time this case waits")
        return stream.readline()

    def test_a_program_that_could_not_start_says_so_the_way_start_does(self):
        for argv, errors in (
            ([str(self.home / "never-installed")], self.errors),
            ([sys.executable, "-c", "pass"], self.home),           # the error path is a directory
            ([], self.errors),
        ):
            with self.subTest(argv=argv):
                with self.assertRaises(programs.CouldNotStart):
                    programs.talking(argv, errors)

    def test_what_the_program_says_arrives_a_line_at_a_time(self):
        one = self.given_talking("print('{\"say\": \"ready\"}')")
        self.assertEqual('{"say": "ready"}\n', self.a_line_from(one.stdout))

    def test_what_is_written_to_it_is_heard(self):
        # The half `start` will not do at all: its stdin is DEVNULL, so a caller needing to send
        # something had nowhere to send it.
        one = self.given_talking(
            "import sys\n"
            "for line in sys.stdin:\n"
            "    print('heard', line.strip(), flush=True)\n")
        one.stdin.write("post this\n")
        one.stdin.flush()
        self.assertEqual("heard post this\n", self.a_line_from(one.stdout))

    def test_a_line_leaves_this_process_when_it_is_written(self):
        # Line buffered on purpose. Block buffered, the answer to one message waits behind the
        # answer to the next, which in a chat surface reads as the agent ignoring somebody.
        one = self.given_talking(
            "import sys\n"
            "for line in sys.stdin:\n"
            "    print('heard', line.strip(), flush=True)\n")
        for said in ("first", "second", "third"):
            # **Deliberately not flushed.** Under line buffering the newline is what sends it; block
            # buffered, this line would sit here until enough had piled up behind it, and a case
            # that flushed by hand would pass either way and prove nothing.
            one.stdin.write(f"{said}\n")
            self.assertEqual(f"heard {said}\n", self.a_line_from(one.stdout))

    def test_what_it_writes_to_the_error_stream_goes_to_the_file_and_not_the_stream(self):
        # They carry different things: stdout is a protocol nothing may interrupt, and one traceback
        # written across it is a line no reader can parse in the middle of a stream it is parsing.
        one = self.given_talking(
            "import sys\n"
            "sys.stderr.write('a traceback nobody can parse\\n')\n"
            "sys.stderr.flush()\n"
            "print('{\"say\": \"ready\"}')\n")
        self.assertEqual('{"say": "ready"}\n', self.a_line_from(one.stdout))
        self.assertTrue(support.waited_until(
            lambda: self.errors.exists() and "a traceback" in self.errors.read_text(),
            self.PATIENCE))

    def test_the_error_file_is_appended_to_rather_than_replaced(self):
        self.given_talking("import sys; sys.stderr.write('first\\n'); sys.stderr.flush()")
        self.assertTrue(support.waited_until(
            lambda: self.errors.exists() and "first" in self.errors.read_text(), self.PATIENCE))
        self.given_talking("import sys; sys.stderr.write('second\\n'); sys.stderr.flush()")
        self.assertTrue(support.waited_until(
            lambda: "second" in self.errors.read_text(), self.PATIENCE))
        self.assertIn("first", self.errors.read_text(), "the file was replaced, not appended to")

    def test_it_is_started_in_a_session_of_its_own(self):
        one = self.given_talking("import time; time.sleep(30)")
        self.assertEqual(one.pid, os.getpgid(one.pid), "it is not the leader of its own group")
        self.assertNotEqual(os.getpgrp(), os.getpgid(one.pid))

    def test_a_claim_handed_to_it_is_held_for_as_long_as_it_runs(self):
        # The same arrangement a firing uses: a flock belongs to the open file description, so one
        # taken here and passed down outlives this process and the kernel drops it however the child
        # ends — which a written-down pid can never do, because numbers are reused.
        def shut(descriptor):
            with contextlib.suppress(OSError):
                os.close(descriptor)

        claim = self.home / "channel.lock"
        held = os.open(str(claim), os.O_CREAT | os.O_RDWR, 0o600)
        self.addCleanup(shut, held)                        # in case the case fails before closing
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        one = programs.talking([sys.executable, "-c", "import time; time.sleep(30)"],
                               self.errors, holding=(held,))
        self.talking.append(one)
        os.close(held)                                     # this side lets go; the child still has it
        asking = os.open(str(claim), os.O_CREAT | os.O_RDWR, 0o600)
        self.addCleanup(os.close, asking)
        with self.assertRaises(OSError, msg="the claim was not held by the child"):
            fcntl.flock(asking, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def test_a_program_that_says_far_more_than_a_pipe_holds_is_read_in_full(self):
        # A pipe holds 64KB. This says about four times that and then one last line, so the last
        # line can only arrive if everything before it was drained rather than buffered somewhere.
        one = self.given_talking(
            "for n in range(4000):\n"
            "    print('x' * 64)\n"
            "print('the end')\n")
        last = ""
        for _ in range(4001):
            last = one.stdout.readline()
        self.assertEqual("the end\n", last)

    def test_a_program_nobody_reads_stops_where_it_stands(self):
        # The hazard the case above is written against, stated rather than implied: this is what
        # happens when the draining does not happen, and it is why whatever calls `talking` puts the
        # reading somewhere that cannot fall behind rather than on a loop that also sleeps.
        one = self.given_talking(
            "for n in range(4000):\n"
            "    print('x' * 64)\n"
            "print('the end')\n")
        self.assertFalse(support.waited_until(
            lambda: not programs.alive(one.pid), 0.5),
            "a program writing into a pipe nobody drains reached the end of it")


class ADirectoryOfNumberedScripts(support.Isolated):
    """`scripts` — what both levels of migration ask before they carry anything.

    Covered here as well as through each runner, because the runners disagree about what a script is
    handed and agree about everything this module does. A bug here is a bug in both of them.
    """

    def setUp(self) -> None:
        super().setUp()
        self.where = self.home / "steps"
        self.where.mkdir()

    def given(self, name: str, body: str = "def carry(*said):\n    pass\n") -> Path:
        (self.where / name).write_text(body, encoding="utf-8")
        return self.where / name

    def test_it_finds_them_rather_than_being_told_what_is_there(self):
        self.given("0002_second.py")
        self.given("0001_first.py")
        self.assertEqual(["0001_first", "0002_second"],
                         [one.id for one in scripts.found(self.where)])

    def test_they_run_in_the_order_their_number_gives_and_not_the_order_of_the_name(self):
        # Sorted by number rather than by filename, or `0010` would run before `0002`.
        self.given("0010_later.py")
        self.given("0002_earlier.py")
        self.assertEqual([2, 10], [one.order for one in scripts.found(self.where)])

    def test_anything_not_named_like_one_costs_nothing(self):
        # `__init__.py` is there in every real steps directory, and editors leave things behind.
        for name in ("__init__.py", "notes.py", "1_short.py", "0001-dashed.py", "0001_Caps.py"):
            self.given(name)
        self.assertEqual([], scripts.found(self.where))

    def test_two_sharing_a_number_are_refused_while_it_is_still_a_broken_checkout(self):
        # What happens the first time two branches each add a step and both take the next free
        # number. After it ships, every machine has already made a different arbitrary choice.
        self.given("0001_alpha.py")
        self.given("0001_beta.py")
        with self.assertRaises(scripts.Broken) as refused:
            scripts.found(self.where)
        self.assertIn("0001", str(refused.exception))

    def test_a_directory_that_is_not_there_has_no_scripts_rather_than_failing(self):
        # A release may legitimately ship none, and that is an answer.
        self.assertEqual([], scripts.found(self.home / "never-made"))

    def test_it_hands_back_the_one_function_the_script_exists_to_run(self):
        self.given("0001_counts.py", "seen = []\n\n\ndef carry(what):\n    seen.append(what)\n")
        carry = scripts.carrying(scripts.found(self.where)[0], "probe")
        carry("something")
        self.assertEqual(["something"], carry.__globals__["seen"])

    def test_a_script_with_nothing_to_run_is_refused_by_name(self):
        self.given("0001_empty.py", "value = 1\n")
        with self.assertRaises(scripts.Broken) as refused:
            scripts.carrying(scripts.found(self.where)[0], "probe")
        self.assertIn("0001_empty", str(refused.exception))

    def test_a_script_that_will_not_load_says_so_rather_than_raising_from_inside(self):
        self.given("0001_broken.py", "this is not python at all\n")
        with self.assertRaises(SyntaxError):
            scripts.carrying(scripts.found(self.where)[0], "probe")

    def test_nothing_is_left_on_the_import_path_afterwards(self):
        # A script is arbitrary code from a directory, not a module of this product's. Left
        # registered, the next thing importing that name would get this one instead.
        self.given("0001_leaves.py")
        before = set(sys.modules)
        scripts.carrying(scripts.found(self.where)[0], "probe")
        self.assertEqual(set(), set(sys.modules) - before)

    def test_two_runners_loading_the_same_number_do_not_collide(self):
        # The install and an agent both ship an `0001`, and both are loaded in one process during
        # an update. Named by the caller's prefix so one cannot be handed the other's module.
        self.given("0001_same.py", "which = 'from the steps directory'\n\n\ndef carry(*said):\n"
                                   "    pass\n")
        one = scripts.carrying(scripts.found(self.where)[0], "install")
        other = scripts.carrying(scripts.found(self.where)[0], "agent")
        self.assertIsNot(one, other)
        self.assertEqual(set(), set(sys.modules) & {"install_0001_same", "agent_0001_same"})


class Counting:
    """A file that says how much of itself was read.

    So that "it does not read the whole log to answer for the end of it" is something a case can
    observe, rather than a claim about how the code happens to be written today.
    """

    def __init__(self, handle, tally):
        self.handle, self.tally = handle, tally

    def read(self, *how_much):
        got = self.handle.read(*how_much)
        self.tally.append(len(got))
        return got

    def seek(self, *where):
        return self.handle.seek(*where)

    def tell(self) -> int:
        return self.handle.tell()

    def close(self) -> None:
        self.handle.close()

    def __enter__(self):
        return self

    def __exit__(self, *gone) -> bool:
        self.handle.close()
        return False


class WithSomewhereToWrite(support.Isolated):
    """A scratch log directory, and the means to put whole days in it."""

    #: Longer than the other suites wait, because what is waited for here is several processes
    #: appending to one file at once, and how long that takes is a property of the machine.
    PATIENCE = 30.0

    def setUp(self):
        super().setUp()
        self.where = self.home / "logs"

    def a_day(self, days_ago: int) -> datetime.datetime:
        """A moment that many whole days back, on the machine's own clock — which is what the file
        names are counted in."""
        return datetime.datetime.now().astimezone() - datetime.timedelta(days=days_ago)

    def in_a_timezone(self, named: str) -> None:
        """Put the machine in a timezone of this case's choosing, and put it back afterwards.

        The only way to meet a daylight-saving fall-back in a test rather than wait a year for one.
        Restored rather than removed: `TZ` is a real variable a real shell may have set, and the
        interpreter caches what it read until `tzset` is called again.
        """
        self.addCleanup(time.tzset)
        env_as_it_was(self, "TZ")
        os.environ["TZ"] = named
        time.tzset()

    def given_a_day(self, days_ago: int, *said: str) -> Path:
        """One day's file, written by hand so the order across days can be asserted exactly."""
        self.where.mkdir(parents=True, exist_ok=True)
        where = self.where / logs.named_for(self.a_day(days_ago))
        where.write_text("".join(f"{one}\n" for one in said), encoding="utf-8")
        return where


class ADayOfLines(WithSomewhereToWrite):
    """`logs.note` — one line, appended to the file named for the day it belongs to."""

    def test_the_line_lands_in_the_file_named_for_today(self):
        logs.note(self.where, "the backup finished")
        today = self.where / logs.named_for(self.a_day(0))
        self.assertIn("the backup finished", today.read_text())

    def test_a_line_says_when_it_was_and_how_serious_it_was(self):
        # `[when] LEVEL: what happened`, and the when is the clock on the machine's own menu bar —
        # the question somebody asks a log is "what happened at nine last night", and every other
        # account of the same machine answers in local time.
        logs.note(self.where, "could not reach GitHub", logs.WARNING)
        said = (self.where / logs.named_for(self.a_day(0))).read_text().strip()
        self.assertRegex(
            said,
            r"^\[\d{4}-\d\d-\d\d \d\d:\d\d:\d\d[+-]\d\d:\d\d\] WARNING:\s+could not reach GitHub$")

    def test_the_time_on_a_line_is_this_machine_s_own_with_its_offset(self):
        # Asserted against the clock rather than against a shape, because a stamp that merely looks
        # like a local time and is really UTC passes every regex anybody would write for it.
        logs.note(self.where, "something happened")
        said = (self.where / logs.named_for(self.a_day(0))).read_text().strip()
        stamped = datetime.datetime.fromisoformat(said[1:said.index("]")])

        here = datetime.datetime.now().astimezone()
        self.assertEqual(here.utcoffset(), stamped.utcoffset(), "the line carries no local offset")
        self.assertLess(abs((here - stamped).total_seconds()), 120,
                        "the time on the line is not the time it is here")

    def test_an_hour_that_happens_twice_is_two_different_lines(self):
        # The one real objection to a local timestamp, and what the offset answers. Across a
        # fall-back the clock reads 01:30 twice, an hour apart; without the offset those two are
        # the same text, in the hour somebody is most likely to be reading a log about something
        # odd. Driven rather than waited a year for.
        self.in_a_timezone("America/Los_Angeles")
        during = datetime.datetime(2026, 11, 1, 8, 30, tzinfo=datetime.timezone.utc)
        an_hour_later = during + datetime.timedelta(hours=1)

        logs.note(self.where, "the first one", when=during)
        logs.note(self.where, "the second one", when=an_hour_later)

        said = (self.where / "2026-11-01.log").read_text().splitlines()
        self.assertIn("[2026-11-01 01:30:00-07:00]", said[0])
        self.assertIn("[2026-11-01 01:30:00-08:00]", said[1])

    def test_the_levels_line_up_down_the_page(self):
        # A screen of these is read at a glance, and a column that moves about is a column nobody
        # can read down. `INFO:` and `WARNING:` are not the same width, so the short one is padded.
        for level in logs.LEVELS:
            logs.note(self.where, "something happened", level)
        said = (self.where / logs.named_for(self.a_day(0))).read_text().splitlines()
        self.assertEqual(len(logs.LEVELS), len(said))
        columns = {one.index("something happened") for one in said}
        self.assertEqual(1, len(columns),
                         f"the message starts at {sorted(columns)} down the page")

    def test_a_severity_this_vocabulary_does_not_have_is_never_written_through(self):
        # Four words and no fifth, or the column stops being something anybody can filter on. The
        # names somebody reaches for from outside the four are PSR-3's, three of which are graver
        # than ERROR — so an unclassifiable line is never shown to a person as a routine one.
        for said, expected in (("CRITICAL", logs.ERROR), ("EMERGENCY", logs.ERROR),
                               ("NOTICE", logs.ERROR), ("", logs.ERROR),
                               ("info", logs.INFO), (" warning ", logs.WARNING),
                               (logs.DEBUG, logs.DEBUG)):
            with self.subTest(level=said):
                where = self.where / logs.named_for(self.a_day(0))
                files.discard(where)
                logs.note(self.where, "something happened", said)
                self.assertRegex(where.read_text(), rf"^\[[^\]]+\] {expected}:\s+something")

    def test_it_appends_rather_than_replacing(self):
        # A log is mostly history. A write that replaced the day would leave the last line of it.
        for which in ("first", "second", "third"):
            logs.note(self.where, which)
        said = (self.where / logs.named_for(self.a_day(0))).read_text()
        self.assertEqual(3, len(said.strip().splitlines()))
        self.assertIn("first", said)

    def test_something_running_through_midnight_lands_in_two_days(self):
        # A long-lived process is the case a held-open handler gets wrong: it goes on writing into
        # yesterday's file for as long as it runs. The day comes from the moment, every time — and
        # from the machine's own midnight, so the name and the lines inside it agree about the day.
        midnight = datetime.datetime(2026, 8, 4, 23, 59, 59)
        logs.note(self.where, "before midnight", when=midnight)
        logs.note(self.where, "after midnight", when=midnight + datetime.timedelta(seconds=2))

        self.assertIn("before midnight", (self.where / "2026-08-04.log").read_text())
        self.assertIn("after midnight", (self.where / "2026-08-05.log").read_text())

    def test_the_day_in_the_name_is_the_day_on_the_lines_inside_it(self):
        # Half past eight in the evening in California is already tomorrow in UTC. A file named for
        # the UTC day would hold lines dated the day before, and somebody looking for last Tuesday
        # would open Wednesday and find Tuesday's evening in it.
        self.in_a_timezone("America/Los_Angeles")
        evening = datetime.datetime(2026, 8, 5, 3, 30, tzinfo=datetime.timezone.utc)

        logs.note(self.where, "still Tuesday evening here", when=evening)

        # Asked of the naming itself as well as of what `note` did with it, because `named_for` is
        # what anything reporting on a log calls, and it is handed whatever that caller had.
        self.assertEqual("2026-08-04.log", logs.named_for(evening))
        self.assertEqual(["2026-08-04.log"], [one.name for one in logs.kept(self.where)])
        self.assertIn("[2026-08-04 20:30:00-07:00]", (self.where / "2026-08-04.log").read_text())

    def test_it_makes_the_directory_it_writes_into(self):
        logs.note(self.home / "not" / "yet", "the first thing that happened")
        self.assertTrue((self.home / "not" / "yet").is_dir())

    def test_a_line_that_could_not_be_written_never_fails_what_was_being_done(self):
        # A log is an account of the work, not the work. A backup that could not write its own note
        # is a backup that succeeded, and saying otherwise turns a good run into a reported failure.
        support.not_as_root(self)
        self.where.mkdir(parents=True)
        self.addCleanup(self.where.chmod, 0o700)
        self.where.chmod(0o500)

        logs.note(self.where, "this cannot land anywhere")

        self.assertEqual([], list(self.where.iterdir()))

    def test_a_message_that_ends_in_a_newline_does_not_leave_a_blank_line(self):
        logs.note(self.where, "said with its own ending\n")
        said = (self.where / logs.named_for(self.a_day(0))).read_text()
        self.assertEqual(1, len(said.splitlines()))

    def test_a_day_is_only_readable_by_whoever_it_belongs_to(self):
        # A log holds what a program was doing and for whom. Created at the mode it should have
        # rather than tightened afterwards, which is a window with the lines already in it.
        logs.note(self.where, "something worth keeping to ourselves")
        mode = (self.where / logs.named_for(self.a_day(0))).stat().st_mode & 0o777
        self.assertEqual(files.ONLY_MINE, mode, oct(mode))


class WhenSeveralThingsWriteAtOnce(WithSomewhereToWrite):
    """The property the whole day-file scheme rests on: one write, one whole line."""

    #: Enough writers and enough lines that an interleaving would be met rather than missed, and
    #: lines long enough that half of one is unmistakable.
    WRITERS = 4
    EACH = 120
    LONG = 400

    def test_every_line_from_every_writer_arrives_whole(self):
        # Real processes rather than threads: the guarantee is the kernel's, that a write to a file
        # opened `O_APPEND` takes the offset and the bytes together. Most of this product is
        # short-lived processes and several of them run at once — a person typing a command while a
        # scheduled job runs — so this is the ordinary case rather than a stressed one.
        started = []
        self.addCleanup(lambda: [programs.stop(pid, 0.5, 1.0) for pid in started])
        for which in range(self.WRITERS):
            started.append(programs.start(
                [sys.executable, "-c", self.a_writer(which)], self.home / "what-they-said.log"))

        wanted = self.WRITERS * self.EACH
        self.assertTrue(
            support.waited_until(lambda: len(logs.tail(self.where, wanted * 2).lines) >= wanted,
                                 self.PATIENCE),
            "the writers never finished, or lines were lost")

        said = logs.tail(self.where, wanted * 2).lines
        self.assertEqual(wanted, len(said), "lines were lost or torn in half")
        for line in said:
            self.assertRegex(
                line,
                r"^\[\d{4}-\d\d-\d\d \d\d:\d\d:\d\d[+-]\d\d:\d\d\] INFO:\s+writer \d x{%d} line \d+$"
                % self.LONG,
                "a line was torn in half by another writer")

    def a_writer(self, which: int) -> str:
        """One process that does nothing but write lines into the same day as the others."""
        return (
            "import sys\n"
            f"sys.path.insert(0, {str(support.CHECKOUT / 'src')!r})\n"
            "from pathlib import Path\n"
            "from rundesk.utils import logs\n"
            f"where = Path({str(self.where)!r})\n"
            f"for line in range({self.EACH}):\n"
            f"    logs.note(where, 'writer {which} ' + 'x' * {self.LONG} + ' line %d' % line)\n")


class TheDaysThatAreKept(WithSomewhereToWrite):
    """`logs.kept` — what is ours to read, newest first, and what is somebody else's."""

    def test_the_days_come_back_newest_first(self):
        for how_long_ago in (3, 1, 2, 0):
            self.given_a_day(how_long_ago, "something happened")
        self.assertEqual([logs.named_for(self.a_day(which)) for which in (0, 1, 2, 3)],
                         [one.name for one in logs.kept(self.where)])

    def test_nothing_that_is_not_named_for_a_day_is_offered(self):
        # A directory a program writes into is a directory somebody else leaves a file in — and
        # launchd leaves two of its own beside these. Offered as logs, they would be read as ours
        # and swept as ours.
        self.where.mkdir(parents=True)
        for name in ("gateway.out", "gateway.err", "notes.log", ".log", "2026-8-4.log",
                     "2026-13-45.log", "2026-02-31.log", "2026-08-04.log.old", "readme.txt"):
            (self.where / name).write_text("not a day of this log")
        self.assertEqual([], logs.kept(self.where))

    def test_a_directory_nothing_has_written_in_offers_nothing(self):
        self.assertEqual([], logs.kept(self.home / "never-written-in"))

    def test_a_day_shaped_name_that_is_not_a_date_is_not_a_day(self):
        # `2026-02-31.log` has exactly the right shape and is not a date. Shape and value refuse
        # different things, so both are asked.
        self.assertIsNone(logs.the_day_of("2026-02-31.log"))
        self.assertIsNone(logs.the_day_of("notes.log"))
        self.assertEqual(datetime.date(2026, 8, 4), logs.the_day_of("2026-08-04.log"))


class ReadingBackTheEndOfALog(WithSomewhereToWrite):
    """`logs.tail` — the last lines across the days, in three answers rather than one."""

    def test_the_lines_come_back_exactly_as_they_were_written(self):
        # What a command prints and what a person greps must be the same text. Re-rendered on the
        # way out, the line somebody searched for is not the line they were shown.
        logs.note(self.where, "the gateway started", logs.INFO)
        logs.note(self.where, "it could not be carried onto this release", logs.ERROR)
        on_disk = (self.where / logs.named_for(self.a_day(0))).read_text().splitlines()

        self.assertEqual(on_disk, logs.tail(self.where, 20).lines)

    def test_it_hands_back_the_end_of_today_in_order(self):
        self.given_a_day(0, "first", "second", "third", "fourth")
        got = logs.tail(self.where, 2)
        self.assertEqual(logs.READ, got.how)
        self.assertEqual(["third", "fourth"], got.lines)

    def test_it_spans_the_days_oldest_first(self):
        # The whole point of reading more than one: the last twenty lines are the last twenty lines
        # even when nineteen of them were written yesterday.
        self.given_a_day(2, "two days ago")
        self.given_a_day(1, "yesterday")
        self.given_a_day(0, "today")
        self.assertEqual(["two days ago", "yesterday", "today"], logs.tail(self.where, 5).lines)

    def test_asking_for_more_lines_than_there_are_gives_what_there_is(self):
        self.given_a_day(1, "yesterday")
        self.given_a_day(0, "today")
        self.assertEqual(["yesterday", "today"], logs.tail(self.where, 500).lines)

    def test_a_directory_nothing_has_written_in_is_not_an_unreadable_one(self):
        got = logs.tail(self.home / "never-written-in", 20)
        self.assertEqual(logs.NOTHING_YET, got.how)
        self.assertEqual([], got.lines)
        self.assertIn("never-written-in", got.why)

    def test_a_directory_that_cannot_be_read_is_not_an_empty_one(self):
        # Writing is silent about failing, on purpose, so this is where a person finds out. Handed
        # back as "no lines yet", a permission problem reads as a program that has been quiet.
        support.not_as_root(self)
        self.given_a_day(0, "something happened")
        self.addCleanup(self.where.chmod, 0o700)
        self.where.chmod(0o000)

        got = logs.tail(self.where, 20)
        self.assertEqual(logs.UNREADABLE, got.how)
        self.assertEqual([], got.lines)
        self.assertIn(str(self.where), got.why)

    def test_one_day_that_cannot_be_read_stops_the_whole_answer(self):
        # Skipping it would hand back a tail with a hole in it, presented as the end of the log.
        support.not_as_root(self)
        older = self.given_a_day(1, "yesterday", "and again")
        self.given_a_day(0, "today")
        self.addCleanup(older.chmod, 0o600)
        older.chmod(0o000)

        self.assertEqual(logs.UNREADABLE, logs.tail(self.where, 3).how)

    def test_days_with_nothing_in_them_are_read_and_empty(self):
        # Told apart from a directory nothing has written in: a program that started and has said
        # nothing yet is a different report from one that has never run.
        self.given_a_day(0)
        got = logs.tail(self.where, 20)
        self.assertEqual(logs.READ, got.how)
        self.assertEqual([], got.lines)

    def test_asking_for_no_lines_at_all_is_not_an_error(self):
        self.given_a_day(0, "something")
        for how_many in (0, -1):
            with self.subTest(lines=how_many):
                got = logs.tail(self.where, how_many)
                self.assertEqual(logs.READ, got.how)
                self.assertEqual([], got.lines)

    def test_the_last_line_comes_back_even_when_nothing_ended_it(self):
        # A log is read while it is being written to, so the last line has no newline after it about
        # as often as it has one.
        self.where.mkdir(parents=True)
        (self.where / logs.named_for(self.a_day(0))).write_text("first\nhalf a line")
        self.assertEqual(["half a line"], logs.tail(self.where, 1).lines)

    def test_a_line_longer_than_one_read_still_comes_back_whole(self):
        # The walk backwards is in blocks, and a program logging a stack trace or a body it was
        # sent writes lines far longer than one.
        long_one = "x" * (logs.BLOCK_BYTES * 3)
        self.given_a_day(0, "before", long_one, "after")
        self.assertEqual([long_one, "after"], logs.tail(self.where, 2).lines)

    def test_nothing_that_is_not_a_day_is_read_back_as_one(self):
        self.given_a_day(0, "ours")
        (self.where / "gateway.err").write_text("launchd caught this\n")
        self.assertEqual(["ours"], logs.tail(self.where, 20).lines)

    def test_it_does_not_read_a_directory_of_days_to_answer_for_the_end_of_it(self):
        # A year of these is asked for its last five lines. Reading them to answer works on a
        # fixture and stops working on the machine this was written for.
        for how_long_ago in range(4):
            self.given_a_day(how_long_ago, *[f"day {how_long_ago} line {one}"
                                             for one in range(40000)])
        how_big = sum(one.stat().st_size for one in logs.kept(self.where))
        self.assertGreater(how_big, 2 * 1024 * 1024, "this is not enough log to prove anything")

        tally = []
        opening = open

        def counted(*where, **how):
            return Counting(opening(*where, **how), tally)

        with mock.patch.object(logs, "open", counted, create=True):
            got = logs.tail(self.where, 5)

        self.assertEqual([f"day 0 line {one}" for one in range(39995, 40000)], got.lines)
        self.assertLess(sum(tally), 100 * 1024,
                        f"it read {sum(tally)} bytes of {how_big} to answer for five lines")


class SweepingTheOldDaysAway(WithSomewhereToWrite):
    """`logs.swept` — retention counted in days, decided by the name, and nothing else touched."""

    def test_it_keeps_exactly_the_days_it_was_told_to(self):
        for how_long_ago in range(20):
            self.given_a_day(how_long_ago, "something happened")

        logs.swept(self.where, 14)

        self.assertEqual([logs.named_for(self.a_day(which)) for which in range(14)],
                         [one.name for one in logs.kept(self.where)])

    def test_what_it_hands_back_is_what_actually_went(self):
        for how_long_ago in (0, 30, 31):
            self.given_a_day(how_long_ago, "something happened")

        gone = logs.swept(self.where, 14)

        self.assertEqual({logs.named_for(self.a_day(30)), logs.named_for(self.a_day(31))},
                         {one.name for one in gone})
        for one in gone:
            self.assertFalse(one.exists())

    def test_it_decides_by_the_name_and_never_by_the_files_own_timestamp(self):
        # An mtime is changed by a copy, a restore, or a backup putting a file back — so a restore
        # would silently age out the logs it had just brought back, or keep a year of them, and
        # nothing anywhere would say which had happened.
        old = self.given_a_day(40, "this was a long time ago")
        os.utime(old, None)                      # as a restore would have left it: touched just now
        fresh = self.given_a_day(0, "this happened today")
        os.utime(fresh, (0, 0))                  # and this one looking ancient

        logs.swept(self.where, 14)

        self.assertFalse(old.exists(), "it swept by the timestamp rather than by the day")
        self.assertTrue(fresh.exists(), "it took today's log because the timestamp looked old")

    def test_it_leaves_alone_everything_it_cannot_read_as_a_day(self):
        # Somebody else's file in the same directory is not ours to delete — and two of them are
        # launchd's own capture, which is the only account of a start that died on the way up.
        self.given_a_day(0, "ours")
        self.where.mkdir(parents=True, exist_ok=True)
        theirs = []
        for name in ("gateway.out", "gateway.err", "notes.log", "2026-02-31.log", "keep-me.txt"):
            (self.where / name).write_text("not ours")
            theirs.append(self.where / name)

        self.assertEqual([], logs.swept(self.where, 1))

        for one in theirs:
            with self.subTest(file=one.name):
                self.assertTrue(one.exists())

    def test_a_retention_that_lost_its_value_removes_nothing(self):
        # A `0` arriving here is a configuration that lost its value somewhere, and reading it as
        # "keep none of it" would empty a log directory on the strength of a variable nobody set.
        for how_long_ago in (0, 100):
            self.given_a_day(how_long_ago, "something happened")
        for keeping in (0, -1):
            with self.subTest(keeping=keeping):
                self.assertEqual([], logs.swept(self.where, keeping))
                self.assertEqual(2, len(logs.kept(self.where)))

    def test_keeping_one_day_keeps_today(self):
        self.given_a_day(1, "yesterday")
        today = self.given_a_day(0, "today")

        logs.swept(self.where, 1)

        self.assertEqual([today.name], [one.name for one in logs.kept(self.where)])

    def test_a_day_from_the_future_is_never_swept(self):
        # A machine whose clock ran ahead once has a file dated next week in it. Sweeping it as
        # "not within the last fourteen days" would take the newest log there is.
        ahead = self.given_a_day(-3, "the clock was ahead")
        logs.swept(self.where, 14)
        self.assertTrue(ahead.exists())

    def test_sweeping_a_directory_that_is_not_there_is_not_an_error(self):
        self.assertEqual([], logs.swept(self.home / "never-written-in", 14))


class TheDescriptorSomebodyElseHolds(WithSomewhereToWrite):
    """What a rotation may and may not do to a file whose descriptor is not ours to close.

    **This is the assumption the whole of `logs.rotated` rests on, and it is measured here rather
    than believed.** A supervisor asked to capture a program's output opens the path itself,
    `O_CREAT|O_RDWR|O_APPEND`, and `exec`s the program with that descriptor already in place as its
    standard output — for launchd that is `xpcproxy`, recorded in `docs/research/launchd-on-macos.md`
    §8. Nothing here can ask launchd for its descriptor back, so these cases build the same
    structure: a parent opens the file exactly that way, a child inherits it, and the file is rotated
    underneath while the child is still holding it.

    Two facts come out of it and both decide the design. A descriptor follows the **inode**, so a
    file renamed out from under one leaves it writing somewhere nobody will ever look. And `O_APPEND`
    is what makes truncation safe, because every write under it goes to the current end — without it
    the next write lands at the offset the holder still has and leaves a hole of NUL bytes as long as
    everything that was there.

    The holder here is this process, because what is being asked about is the descriptor and not who
    has it. The other half — a descriptor *inherited* by a child that was `exec`ed with it already in
    place, which is exactly how a gateway gets its own — is proven against a real gateway process in
    `tests/test_gateway_host.py`.
    """

    def setUp(self):
        super().setUp()
        self.where.mkdir(parents=True, exist_ok=True)
        self.live = self.where / "gateway.out"
        self.aside = self.where / "gateway.out.1"

    def a_holder(self, of: Path) -> int:
        """A descriptor on `of`, opened the way a supervisor opens one and held the way one holds."""
        holding = os.open(of, os.O_CREAT | os.O_RDWR | os.O_APPEND, 0o644)
        self.addCleanup(os.close, holding)
        return holding

    def test_a_rename_leaves_the_holder_writing_where_nobody_will_ever_look(self):
        # The move `rotated` refuses to make, and the whole reason it refuses. The supervisor puts
        # the name back on the next start — that is the file everybody opens — and the process that
        # is running right now goes on writing into the inode that name used to mean.
        self.live.write_bytes(b"before\n")
        holding = self.a_holder(self.live)

        os.replace(self.live, self.aside)
        self.live.write_bytes(b"")                       # what the next spawn would create
        os.write(holding, b"after\n")

        self.assertEqual(b"", self.live.read_bytes(),
                         "the holder wrote into the live file, so a rename would have been safe")
        self.assertEqual(b"before\nafter\n", self.aside.read_bytes())

    def test_a_truncation_leaves_the_holder_writing_into_the_same_file(self):
        # Same inode, same name, same descriptor — and the line lands at zero rather than after a
        # hole, because the descriptor was opened `O_APPEND`.
        self.live.write_bytes(b"before\n")
        was = self.live.stat().st_ino
        holding = self.a_holder(self.live)

        os.truncate(self.live, 0)
        os.write(holding, b"after\n")

        self.assertEqual(b"after\n", self.live.read_bytes())
        self.assertEqual(was, self.live.stat().st_ino, "the file was replaced rather than emptied")

    def test_without_append_the_same_truncation_would_leave_a_hole_of_nul_bytes(self):
        # Why `O_APPEND` is stated as the condition it is rather than assumed. A holder that keeps
        # an offset of its own writes past the end of a truncated file, and what is in between is
        # NUL bytes: a capture that looks corrupt and is longer than anything anybody wrote.
        one = self.where / "not-appended"
        holding = os.open(one, os.O_CREAT | os.O_RDWR, 0o644)
        self.addCleanup(os.close, holding)
        os.write(holding, b"before\n")

        os.truncate(one, 0)
        os.write(holding, b"after\n")

        self.assertEqual(b"\0" * len("before\n") + b"after\n", one.read_bytes())

    def test_rotating_by_content_keeps_the_holder_writing_where_the_path_says(self):
        # The two facts above, put together as the thing `rotated` actually promises.
        self.live.write_bytes(b"x" * 200 + b"\n")
        holding = self.a_holder(self.live)

        self.assertEqual(self.aside, logs.rotated(self.live, 100, 3))
        os.write(holding, b"after\n")

        self.assertEqual(b"after\n", self.live.read_bytes())
        self.assertTrue(self.aside.read_bytes().startswith(b"x" * 100))


class RotatingAFileSomebodyElseWrote(WithSomewhereToWrite):
    """`logs.rotated` — the answer for a file this product does not name and does not write.

    Size rather than days, because size is the only thing measurable about content nobody here
    chose; content rather than name, because the descriptor belongs to somebody else. The module
    docstring says why neither of those is a preference.
    """

    def setUp(self):
        super().setUp()
        self.where.mkdir(parents=True, exist_ok=True)
        self.live = self.where / "gateway.out"
        self.aside = self.where / "gateway.out.1"

    def a_capture_of(self, size: int, first: bytes = b"") -> Path:
        """A capture of about that many bytes, optionally beginning with something recognisable."""
        line = b"a traceback nobody read\n"
        self.live.write_bytes(first + line * (max(0, size - len(first)) // len(line) + 1))
        return self.live

    def test_a_file_that_is_not_big_enough_yet_is_left_exactly_where_it_is(self):
        # The guarantee that keeps a gateway restarted every thirty seconds from rotating 2,880
        # times a day and rolling the evidence off the end within minutes.
        self.live.write_bytes(b"y" * 100)

        self.assertIsNone(logs.rotated(self.live, 100, 3), "it rotated a file the same size as the "
                                                           "threshold, which is not bigger than it")

        self.assertEqual(b"y" * 100, self.live.read_bytes())
        self.assertFalse(self.aside.exists())

    def test_the_content_moves_aside_and_the_file_itself_stays(self):
        one = self.a_capture_of(4096)
        was = one.stat().st_ino

        self.assertEqual(self.aside, logs.rotated(one, 1024, 3))

        self.assertEqual(0, one.stat().st_size)
        self.assertEqual(was, one.stat().st_ino, "the file was replaced rather than emptied")
        self.assertIn(b"a traceback nobody read", self.aside.read_bytes())

    def test_what_it_keeps_is_the_start_of_whatever_went_wrong(self):
        # The head and not the tail: the crash that started a loop is the one somebody is looking
        # for, and it is the one at the top of the file.
        self.a_capture_of(8192, first=b"the first thing that ever went wrong\n")

        logs.rotated(self.live, 1024, 3)

        self.assertTrue(self.aside.read_bytes().startswith(b"the first thing that ever went wrong"))

    def test_a_file_far_bigger_than_the_threshold_costs_the_same_and_says_what_went(self):
        # A program spilling into its own capture since March would otherwise make coming up cost
        # gigabytes. What is dropped is said out loud rather than left looking like the end of it.
        self.a_capture_of(200_000)

        logs.rotated(self.live, 1024, 3)

        kept = self.aside.read_bytes()
        self.assertLess(len(kept), 2048, "it copied the whole file")
        self.assertIn(b"the rest is not here", kept)
        self.assertIn(b"WARNING", kept)

    def test_every_generation_it_keeps_is_the_same_size_whatever_it_rotated(self):
        # `when_over` is one decision wearing two hats: how big a kept generation is, and therefore
        # the size at which a file has more in it than one generation holds. What that buys is a
        # total on disk that can be worked out from the two numbers and nothing else.
        for size in (2_000, 200_000):
            with self.subTest(size=size):
                self.a_capture_of(size)
                logs.rotated(self.live, 1024, 3)
                self.assertEqual(1024, len(self.aside.read_bytes().split(b"\n[")[0]))

    def test_what_it_dropped_is_said_with_both_numbers_in_it(self):
        # "This file was four gigabytes and you have the first quarter of a megabyte of it" is a
        # different thing to be told than a file that simply stops, which is what a silent cut is.
        self.a_capture_of(200_000)
        logs.rotated(self.live, 1024, 3)
        said = self.aside.read_bytes().decode()
        self.assertRegex(said, r"this file was 2\d\d,?\d\d\d bytes")
        self.assertIn("the first 1024", said)

    def test_only_so_many_are_ever_kept_however_many_times_it_rotates(self):
        for which in range(6):
            self.live.write_bytes(f"generation {which}\n".encode() + b"q" * 200)
            logs.rotated(self.live, 100, 2)

        self.assertTrue(self.aside.read_bytes().startswith(b"generation 5"))
        self.assertTrue((self.where / "gateway.out.2").read_bytes().startswith(b"generation 4"))
        self.assertFalse((self.where / "gateway.out.3").exists(), "it kept more than it was told to")

    def test_a_retention_that_lost_its_value_moves_nothing_and_empties_nothing(self):
        # The worst thing this function could do: truncate a file and keep no copy of it. A
        # `keeping` that arrived as `0` is a value that lost itself somewhere, exactly as in `swept`.
        for keeping in (0, -1):
            with self.subTest(keeping=keeping):
                self.live.write_bytes(b"w" * 500)
                self.assertIsNone(logs.rotated(self.live, 100, keeping))
                self.assertEqual(b"w" * 500, self.live.read_bytes())

    def test_a_file_nobody_has_written_is_not_an_error(self):
        self.assertIsNone(logs.rotated(self.where / "never-captured", 100, 3))

    def test_nothing_is_left_staged_behind_it(self):
        self.a_capture_of(4096)
        logs.rotated(self.live, 1024, 3)
        self.assertEqual([], [one.name for one in self.where.iterdir() if files.staged(one.name)])

    def test_what_it_keeps_is_only_readable_by_whoever_it_belongs_to(self):
        # A capture holds whatever a program printed, which is not necessarily fit for everybody on
        # the machine to read — and it is already in the file by the time a mode could be tightened.
        self.a_capture_of(4096)
        logs.rotated(self.live, 1024, 3)
        self.assertEqual(files.ONLY_MINE, self.aside.stat().st_mode & 0o777)

    def test_a_directory_that_cannot_be_written_leaves_the_file_untouched(self):
        support.not_as_root(self)
        self.a_capture_of(4096)
        self.where.chmod(0o500)
        self.addCleanup(self.where.chmod, 0o700)

        self.assertIsNone(logs.rotated(self.live, 1024, 3))

        self.assertGreater(self.live.stat().st_size, 1024, "it emptied a file it could not copy")

    def test_what_it_leaves_beside_the_days_is_never_read_as_one(self):
        # The two schemes stand in the same directory and must not reach into each other: a sweep
        # counted in days would otherwise take a capture, and a tail would read one back as a log.
        self.a_capture_of(4096)
        logs.rotated(self.live, 1024, 3)
        logs.note(self.where, "an ordinary line")

        self.assertEqual([logs.named_for(self.a_day(0))], [one.name for one in logs.kept(self.where)])
        self.assertEqual([], logs.swept(self.where, 1))
        self.assertTrue(self.aside.is_file(), "a sweep counted in days took a capture with it")


class WhetherANameStaysWhereItsThingsAreKept(support.Isolated):
    """`files.escapes` — the guard two callers use to refuse a name that reaches somewhere else.

    Tested here as well as through its callers, because it is the one function whose failure
    reintroduces a measured incident: a directory replaced by a symbolic link, where every individual
    removal below correctly refused to follow a link and the operation still reached somewhere that
    had nothing to do with rundesk.
    """

    def test_a_name_nothing_stands_under_yet_does_not_escape(self):
        # Which is what lets a thing be *made*: the check runs before the directory exists.
        self.assertFalse(files.escapes(self.home / "not-there-yet", self.home))

    def test_an_ordinary_child_does_not_escape(self):
        (self.home / "there").mkdir()
        self.assertFalse(files.escapes(self.home / "there", self.home))

    def test_a_parent_reached_through_a_link_does_not_escape_its_own_children(self):
        # Resolved on both sides. `/tmp` is `/private/tmp` on this platform, so comparing what was
        # typed would refuse an ordinary install.
        real = self.home / "real"
        real.mkdir()
        (real / "inside").mkdir()
        through = self.home / "through"
        through.symlink_to(real)
        self.assertFalse(files.escapes(through / "inside", through))

    def test_a_child_replaced_by_a_link_elsewhere_escapes(self):
        elsewhere = self.home / "elsewhere"
        elsewhere.mkdir()
        parent = self.home / "parent"
        parent.mkdir()
        (parent / "cole").symlink_to(elsewhere)
        self.assertTrue(files.escapes(parent / "cole", parent))

    def test_a_name_reaching_upward_escapes(self):
        parent = self.home / "parent"
        parent.mkdir()
        self.assertTrue(files.escapes(parent / ".." / "elsewhere", parent))


if __name__ == "__main__":
    unittest.main()
