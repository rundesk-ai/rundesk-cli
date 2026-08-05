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
import fcntl
import io
import os
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

import support
from rundesk.utils import files, locking, programs, terminal
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

    def waited_until(self, wanted, patience=5.0):
        """Wait for a condition rather than sleeping a guessed amount."""
        ceiling = time.monotonic() + patience
        while time.monotonic() < ceiling:
            if wanted():
                return True
            time.sleep(0.02)
        return False

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
        self.assertTrue(self.waited_until(
            lambda: self.log.exists() and "the gateway is up" in self.log.read_text()))

    def test_the_error_stream_lands_in_the_same_log(self):
        self.given_running("import sys; sys.stderr.write('went wrong\\n')")
        self.assertTrue(self.waited_until(
            lambda: self.log.exists() and "went wrong" in self.log.read_text()))

    def test_a_restart_adds_to_the_history_rather_than_replacing_it(self):
        self.given_running("print('first')")
        self.assertTrue(self.waited_until(lambda: "first" in self.log.read_text()))
        self.given_running("print('second')")
        self.assertTrue(self.waited_until(lambda: "second" in self.log.read_text()))
        self.assertIn("first", self.log.read_text(), "the log was replaced, not appended to")

    def test_it_is_started_in_a_session_of_its_own(self):
        # The flag everything else rests on: its own session and process group, so signalling the
        # group reaches everything it started.
        pid = self.given_running("import time; time.sleep(30)")
        self.assertEqual(pid, os.getpgid(pid), "it is not the leader of its own group")
        self.assertNotEqual(os.getpgrp(), os.getpgid(pid))

    def test_it_does_not_wait_on_a_terminal_nobody_is_watching(self):
        self.given_running("import sys; print('read', len(sys.stdin.read()))")
        self.assertTrue(self.waited_until(
            lambda: self.log.exists() and "read 0" in self.log.read_text()))

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
        self.assertTrue(self.waited_until(marker.exists), "the child never started")
        child = int(marker.read_text())
        self.assertTrue(programs.alive(child))

        self.assertEqual("", programs.stop(pid, 2.0, 2.0))

        self.assertTrue(self.waited_until(lambda: not programs.alive(pid)))
        self.assertTrue(self.waited_until(lambda: not programs.alive(child)),
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
        self.assertTrue(self.waited_until(ready.exists), "the handler was never installed")

        self.assertEqual("", programs.stop(pid, 3.0, 2.0))

        self.assertTrue(goodbye.exists(), "it was killed outright rather than asked first")

    def test_a_program_that_ignores_being_asked_is_told(self):
        pid = self.given_running(
            "import signal, time;"
            "signal.signal(signal.SIGTERM, signal.SIG_IGN);"
            "time.sleep(60)")
        self.assertTrue(self.waited_until(lambda: programs.alive(pid)))
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
        self.assertTrue(self.waited_until(stubborn.exists), "the stubborn child never started")

        self.assertEqual("", programs.stop(pid, 0.5, 3.0))

        # Nothing may be left in the group once this has said it stopped.
        with self.assertRaises(ProcessLookupError):
            os.killpg(pid, 0)

    def test_a_child_that_exited_on_its_own_stops_reading_as_alive(self):
        # Without collecting it, `alive` answers True for ever: a zombie answers signal 0 exactly
        # like a running program. A supervisor shaped `while alive(pid)` would spin on a program
        # that finished in a millisecond, and every short-lived child would hold a table slot.
        pid = self.given_running("pass")
        self.assertTrue(self.waited_until(lambda: not programs.alive(pid)),
                        "it read as alive long after it had exited")

    def test_a_leader_that_has_already_been_collected_still_stops_its_group(self):
        # The ordinary shape of a program that backgrounds something: the launcher starts its
        # worker and exits at once. Once that leader has been collected `getpgid` can no longer
        # resolve it — but the group it led outlives it and still holds the worker. Reading "cannot
        # ask" as "nothing left" said stopped in milliseconds and abandoned the worker.
        pid = programs.start(["sh", "-c", "sleep 60 & exit 0"], self.log)
        self.started.append(pid)
        self.assertTrue(self.waited_until(lambda: not programs.alive(pid)),
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


if __name__ == "__main__":
    unittest.main()
