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
import time
import unittest
from pathlib import Path
from unittest import mock

import support
from rundesk.utils import exclusive, jsonfile, style
from rundesk.utils.staging import INCOMING, OUTGOING, discard, stage_copy, staged
from rundesk.utils.table import as_table


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
        self.assertEqual((jsonfile.MISSING, None), jsonfile.read(self.at))

    def test_a_file_that_will_not_parse_says_something_else(self):
        # The distinction the whole module is built on: an unreadable file is not an empty one.
        self.at.write_text("{ broken")
        self.assertEqual((jsonfile.UNREADABLE, None), jsonfile.read(self.at))

    def test_an_empty_file_is_unreadable_rather_than_an_empty_value(self):
        # Zero bytes is not `{}` — it is a write that did not happen, and reading it as an empty
        # value is how the next write erases what was there.
        self.at.write_text("")
        self.assertEqual(jsonfile.UNREADABLE, jsonfile.read(self.at)[0])

    def test_a_directory_where_a_file_should_be_is_unreadable(self):
        self.at.mkdir()
        self.assertEqual(jsonfile.UNREADABLE, jsonfile.read(self.at)[0])

    def test_a_file_that_cannot_be_opened_is_unreadable_rather_than_missing(self):
        if os.geteuid() == 0:
            self.skipTest("root can read a file with no permissions")
        jsonfile.write(self.at, {"a": 1})
        self.at.chmod(0o000)
        self.addCleanup(self.at.chmod, 0o600)
        self.assertEqual(jsonfile.UNREADABLE, jsonfile.read(self.at)[0])

    def test_a_value_that_was_written_comes_back(self):
        jsonfile.write(self.at, {"a": 1, "b": ["two", 3]})
        self.assertEqual((jsonfile.READ, {"a": 1, "b": ["two", 3]}), jsonfile.read(self.at))

    def test_it_reads_whatever_json_holds_and_not_only_a_mapping(self):
        for value in ([1, 2, 3], "a string", 7, True, None):
            with self.subTest(value=value):
                jsonfile.write(self.at, value)
                self.assertEqual((jsonfile.READ, value), jsonfile.read(self.at))

    def test_the_broken_answer_never_carries_a_value(self):
        # A caller that checked the value rather than the answer would otherwise see `None` from a
        # corrupt file and from a file holding `null`, which are not the same thing.
        self.at.write_text("{ broken")
        self.assertIsNone(jsonfile.read(self.at)[1])


class WritingASmallFile(support.Isolated):
    """`write` — whole, renamed into place, and never leaving a piece behind."""

    def setUp(self):
        super().setUp()
        self.at = self.home / "somewhere.json"

    def test_what_was_written_can_be_read_back(self):
        jsonfile.write(self.at, {"a": 1})
        self.assertEqual((jsonfile.READ, {"a": 1}), jsonfile.read(self.at))

    def test_it_makes_the_directory_it_is_writing_into(self):
        deep = self.home / "one" / "two" / "somewhere.json"
        jsonfile.write(deep, {"a": 1})
        self.assertTrue(deep.is_file())

    def test_it_leaves_no_piece_of_itself_behind(self):
        jsonfile.write(self.at, {"a": 1})
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

        with mock.patch.object(jsonfile.os, "replace", side_effect=watching):
            jsonfile.write(self.at, {"a": 1})
        self.assertEqual([(self.at.parent, self.at.parent)], seen)

    def test_writing_again_replaces_what_was_there(self):
        jsonfile.write(self.at, {"a": 1})
        jsonfile.write(self.at, {"b": 2})
        self.assertEqual((jsonfile.READ, {"b": 2}), jsonfile.read(self.at))

    def test_it_is_written_so_a_person_can_read_and_diff_it(self):
        # Sorted and indented on purpose: this file is edited by hand and shown in bug reports.
        jsonfile.write(self.at, {"b": 2, "a": 1})
        self.assertEqual('{\n  "a": 1,\n  "b": 2\n}\n', self.at.read_text())

    def test_it_ends_with_a_newline(self):
        jsonfile.write(self.at, {"a": 1})
        self.assertTrue(self.at.read_text().endswith("\n"))


class ChangingOneSafely(support.Isolated):
    """`changing` — the read, the decision and the write, with nothing able to get between them."""

    def setUp(self):
        super().setUp()
        self.at = self.home / "somewhere.json"
        self.at.parent.mkdir(parents=True, exist_ok=True)

    def test_it_hands_over_what_is_there_and_writes_back_what_is_left(self):
        jsonfile.write(self.at, {"a": 1})
        with jsonfile.changing(self.at, empty={}) as held:
            self.assertEqual({"a": 1}, held[0])
            held[0] = {"a": 2}
        self.assertEqual((jsonfile.READ, {"a": 2}), jsonfile.read(self.at))

    def test_a_file_nobody_wrote_hands_over_what_the_caller_called_empty(self):
        with jsonfile.changing(self.at, empty={"fresh": True}) as held:
            self.assertEqual({"fresh": True}, held[0])
        self.assertEqual((jsonfile.READ, {"fresh": True}), jsonfile.read(self.at))

    def test_nothing_writes_over_a_value_it_could_not_read(self):
        # The guarantee. Handing back a blank slate here is how state is lost: something writes the
        # blank down, and what was there is gone with nothing having said so.
        self.at.write_text("{ broken")
        with self.assertRaises(ValueError):
            with jsonfile.changing(self.at, empty={}):
                pass
        self.assertEqual("{ broken", self.at.read_text(), "the unreadable value was overwritten")

    def test_a_decision_that_raised_writes_nothing(self):
        jsonfile.write(self.at, {"a": 1})
        with self.assertRaises(RuntimeError):
            with jsonfile.changing(self.at, empty={}) as held:
                held[0] = {"a": 999}
                raise RuntimeError("the caller thought better of it")
        self.assertEqual((jsonfile.READ, {"a": 1}), jsonfile.read(self.at))

    def test_leaving_the_value_alone_writes_it_back_unchanged(self):
        jsonfile.write(self.at, {"a": 1})
        with jsonfile.changing(self.at, empty={}):
            pass
        self.assertEqual((jsonfile.READ, {"a": 1}), jsonfile.read(self.at))

    def test_the_lock_is_its_own_file_and_never_the_value(self):
        # Locking the value's own file would truncate or create the thing being protected.
        with jsonfile.changing(self.at, empty={"a": 1}):
            self.assertTrue(self.at.with_name(f".{self.at.name}.lock").exists())

    def test_it_makes_the_directory_it_is_changing_in(self):
        deep = self.home / "one" / "two" / "somewhere.json"
        with jsonfile.changing(deep, empty={"a": 1}):
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
        self.addCleanup(setattr, exclusive, "WAITING_SECONDS", exclusive.WAITING_SECONDS)
        exclusive.WAITING_SECONDS = 0.1

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
        with self.assertRaises(jsonfile.Stuck) as refused:
            with jsonfile.changing(self.at, empty={}):
                pass
        self.assertLess(time.monotonic() - began, 5, "it waited far past its own ceiling")
        self.assertIn(str(self.at), str(refused.exception))

    def test_it_writes_nothing_when_it_could_not_have_the_file(self):
        jsonfile.write(self.at, {"a": 1})
        self.held_by_something_else()
        with self.assertRaises(jsonfile.Stuck):
            with jsonfile.changing(self.at, empty={}) as held:
                held[0] = {"a": 2}
        self.assertEqual((jsonfile.READ, {"a": 1}), jsonfile.read(self.at))

    def test_a_lock_that_comes_free_is_simply_taken(self):
        # The ordinary case, so the ceiling cannot be mistaken for a refusal to share.
        holding = self.held_by_something_else()
        fcntl.flock(holding, fcntl.LOCK_UN)
        with jsonfile.changing(self.at, empty={}) as held:
            held[0] = {"a": 3}
        self.assertEqual((jsonfile.READ, {"a": 3}), jsonfile.read(self.at))

    def test_the_lock_is_let_go_of_when_the_change_is_done(self):
        with jsonfile.changing(self.at, empty={"a": 1}):
            pass
        with jsonfile.changing(self.at, empty={}) as held:
            self.assertEqual({"a": 1}, held[0])

    def test_the_lock_is_let_go_of_even_when_the_change_raised(self):
        # The kernel drops it when the descriptor closes however the block ended, and `_only_one`
        # closes in a `finally` — otherwise one failed command would wedge every later one.
        with self.assertRaises(RuntimeError):
            with jsonfile.changing(self.at, empty={}):
                raise RuntimeError("no")
        with jsonfile.changing(self.at, empty={"after": True}) as held:
            self.assertEqual({"after": True}, held[0])


class TakingTurns(support.Isolated):
    """`exclusive.only_one` — one at a time, with a ceiling, and re-entrant within one process."""

    def setUp(self):
        super().setUp()
        self.at = self.home / ".a.lock"
        self.addCleanup(setattr, exclusive, "WAITING_SECONDS", exclusive.WAITING_SECONDS)
        exclusive.WAITING_SECONDS = 0.1

    def held_by_something_else(self):
        holding = os.open(self.at, os.O_CREAT | os.O_RDWR, 0o600)
        self.addCleanup(os.close, holding)
        fcntl.flock(holding, fcntl.LOCK_EX)
        return holding

    def test_one_holder_at_a_time(self):
        self.held_by_something_else()
        with self.assertRaises(exclusive.Stuck) as refused:
            with exclusive.only_one(self.at, "the thing"):
                pass
        self.assertIn("the thing", str(refused.exception))

    def test_it_gives_up_rather_than_waiting_for_ever(self):
        self.held_by_something_else()
        began = time.monotonic()
        with self.assertRaises(exclusive.Stuck):
            with exclusive.only_one(self.at):
                pass
        self.assertLess(time.monotonic() - began, 5)

    def test_a_lock_that_comes_free_is_simply_taken(self):
        holding = self.held_by_something_else()
        fcntl.flock(holding, fcntl.LOCK_UN)
        with exclusive.only_one(self.at):
            pass

    def test_it_is_let_go_of_afterwards(self):
        with exclusive.only_one(self.at):
            pass
        with exclusive.only_one(self.at):
            pass

    def test_it_is_let_go_of_even_when_the_block_raised(self):
        with self.assertRaises(RuntimeError):
            with exclusive.only_one(self.at):
                raise RuntimeError("no")
        with exclusive.only_one(self.at):
            pass

    def test_holding_it_twice_in_one_process_does_not_wait_for_itself(self):
        # `flock` is held per open file description, so a second `open` in the same process
        # conflicts with the first exactly as another process would. An operation that holds this
        # and calls another that takes it would otherwise wait for itself until the ceiling.
        with exclusive.only_one(self.at):
            with exclusive.only_one(self.at):
                with exclusive.only_one(self.at):
                    pass

    def test_the_outermost_holder_is_the_one_that_lets_go(self):
        with exclusive.only_one(self.at):
            with exclusive.only_one(self.at):
                pass
            # still held here: an inner block ending must not release it for the outer one
            self.assertEqual(1, exclusive._HELD[str(self.at)])
        self.assertNotIn(str(self.at), exclusive._HELD)

    def test_it_makes_the_directory_the_lock_stands_in(self):
        deep = self.home / "not" / "yet" / ".a.lock"
        with exclusive.only_one(deep):
            pass
        self.assertTrue(deep.exists())


class SettlingTheDirectory(support.Isolated):
    """`_settle` — asking the filesystem to record the rename, not only the bytes it moved."""

    def test_it_settles_a_directory_that_is_there(self):
        self.assertIsNone(jsonfile._settle(self.home))

    def test_a_directory_that_is_not_there_is_not_an_error(self):
        # Best-effort on purpose: durability is not worth turning a completed write into a failure.
        self.assertIsNone(jsonfile._settle(self.home / "never-made"))


class WhetherANameIsStaging(support.Isolated):
    """`staged` — what a walk has to skip, and what it must not."""

    def test_the_names_a_swap_uses_are_staging(self):
        for name in (INCOMING.format(name="app"), OUTGOING.format(name="app")):
            with self.subTest(name=name):
                self.assertTrue(staged(name))

    def test_an_ordinary_name_is_not(self):
        for name in ("app", "data", "2026-08-04T03-00-00Z", "README.md"):
            with self.subTest(name=name):
                self.assertFalse(staged(name))

    def test_a_hidden_file_that_is_not_staging_is_not(self):
        # `.gitignore` is not a swap in flight, and a walk that skipped it would be a move that
        # silently left one of the owner's files behind.
        for name in (".gitignore", ".DS_Store", ".config.json.lock"):
            with self.subTest(name=name):
                self.assertFalse(staged(name))

    def test_a_name_ending_that_way_without_the_leading_dot_is_not(self):
        # Somebody's own directory called `notes.incoming` is theirs, not a swap's.
        self.assertFalse(staged("notes.incoming"))
        self.assertFalse(staged("notes.outgoing"))

    def test_the_two_names_a_swap_uses_are_told_apart_from_each_other(self):
        self.assertNotEqual(INCOMING.format(name="app"), OUTGOING.format(name="app"))


class DiscardingAStagingEntry(support.Isolated):
    """`discard` — removes whatever kind of thing it was, and never raises."""

    def test_it_removes_a_directory(self):
        at = self.home / "a-directory"
        (at / "below").mkdir(parents=True)
        discard(at)
        self.assertFalse(at.exists())

    def test_it_removes_a_file(self):
        at = self.home / "a-file"
        at.write_text("something")
        discard(at)
        self.assertFalse(at.exists())

    def test_it_removes_a_link_without_following_it(self):
        # A link to a directory answers `is_dir()`, so removing it as one would delete what it
        # points at — which is somebody's real directory and was never the thing being staged.
        real = self.home / "the-real-one"
        (real / "below").mkdir(parents=True)
        link = self.home / "a-link"
        link.symlink_to(real)
        discard(link)
        self.assertFalse(link.exists() or link.is_symlink())
        self.assertTrue((real / "below").is_dir(), "it followed the link and deleted the target")

    def test_it_removes_a_link_pointing_at_nothing(self):
        link = self.home / "a-broken-link"
        link.symlink_to(self.home / "never-made")
        discard(link)
        self.assertFalse(link.is_symlink())

    def test_something_that_is_not_there_is_not_an_error(self):
        self.assertIsNone(discard(self.home / "never-made"))

    def test_it_does_not_raise_when_it_cannot_remove(self):
        # Litter is not worth turning a completed operation into a reported failure.
        if os.geteuid() == 0:
            self.skipTest("root may remove from a directory with no write permission")
        at = self.home / "held" / "a-file"
        at.parent.mkdir(parents=True)
        at.write_text("something")
        at.parent.chmod(0o500)
        self.addCleanup(at.parent.chmod, 0o700)
        self.assertIsNone(discard(at))


class ATerminalThatIsWatching(support.Isolated):
    """`wanted` — the four ways to say whether anything should be emitted at all."""

    def setUp(self):
        super().setUp()
        env_as_it_was(self, "NO_COLOR", "FORCE_COLOR", "TERM")
        for name in ("NO_COLOR", "FORCE_COLOR", "TERM"):
            os.environ.pop(name, None)

    def test_a_stream_that_is_not_a_terminal_gets_nothing(self):
        # The ordinary case for a pipe, a file, and every case in this suite.
        self.assertFalse(style.wanted(io.StringIO()))

    def test_a_stream_that_is_a_terminal_does(self):
        self.assertTrue(style.wanted(ATty()))

    def test_no_color_set_to_anything_at_all_means_no(self):
        # Including empty: the convention is that the variable *being set* is the answer, and a
        # person who exported it to nothing still meant it.
        for said in ("1", "", "no", "yes"):
            with self.subTest(NO_COLOR=said):
                os.environ["NO_COLOR"] = said
                self.assertFalse(style.wanted(ATty()))

    def test_force_color_means_yes_even_down_a_pipe(self):
        os.environ["FORCE_COLOR"] = "1"
        self.assertTrue(style.wanted(io.StringIO()))

    def test_no_color_beats_force_color(self):
        # Somebody who has turned this off globally has turned it off.
        os.environ["NO_COLOR"] = "1"
        os.environ["FORCE_COLOR"] = "1"
        self.assertFalse(style.wanted(ATty()))

    def test_a_terminal_that_cannot_do_this_gets_nothing(self):
        os.environ["TERM"] = "dumb"
        self.assertFalse(style.wanted(ATty()))

    def test_a_stream_that_cannot_say_is_not_a_yes(self):
        # Being unable to ask is not a quiet form of yes — the same rule the rest of the product
        # keeps, in the one place where getting it wrong only corrupts output.
        self.assertFalse(style.wanted(object()))
        closed = io.StringIO()
        closed.close()
        self.assertFalse(style.wanted(closed))

    def test_it_is_answered_on_every_call_and_never_bound_at_import(self):
        # The defect this is written against: a module that decided once, when it was imported,
        # answers about the world as it was before any test or any caller could change it.
        watching = ATty()
        self.assertTrue(style.wanted(watching))
        os.environ["NO_COLOR"] = "1"
        self.assertFalse(style.wanted(watching), "the answer was decided before the call")

    def test_it_asks_about_stdout_when_it_is_given_nothing(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertFalse(style.wanted())
        with contextlib.redirect_stdout(ATty()):
            self.assertTrue(style.wanted())


class WearingAStyle(support.Isolated):
    """`paint` and the five named ways of calling it."""

    def setUp(self):
        super().setUp()
        env_as_it_was(self, "NO_COLOR", "FORCE_COLOR")
        os.environ.pop("NO_COLOR", None)
        os.environ["FORCE_COLOR"] = "1"

    def test_it_wears_the_style_it_was_given(self):
        self.assertEqual("\x1b[31mFAILED\x1b[0m", style.paint("FAILED", "red"))

    def test_several_at_once_are_one_sequence_rather_than_nested_ones(self):
        self.assertEqual("\x1b[1;31mFAILED\x1b[0m", style.paint("FAILED", "bold", "red"))

    def test_each_named_one_is_the_style_it_says(self):
        for named, code in ((style.bold, "1"), (style.dim, "2"), (style.red, "31"),
                            (style.green, "32"), (style.yellow, "33")):
            with self.subTest(style=named.__name__):
                self.assertEqual(f"\x1b[{code}mx\x1b[0m", named("x"))

    def test_nobody_watching_gets_exactly_the_characters(self):
        # A script reading this wants the value, and an escape sequence in a captured name is not
        # decoration — it is a name that matches nothing.
        del os.environ["FORCE_COLOR"]
        self.assertEqual("FAILED", style.paint("FAILED", "red", stream=io.StringIO()))
        self.assertEqual("FAILED", style.red("FAILED", stream=io.StringIO()))

    def test_it_always_puts_the_terminal_back(self):
        self.assertTrue(style.paint("x", "red").endswith(style.RESET))

    def test_nothing_to_style_is_left_alone(self):
        self.assertEqual("", style.paint("", "red"))
        self.assertEqual("x", style.paint("x"))

    def test_a_style_that_is_not_one_is_refused_rather_than_dropped(self):
        # Dropping it would give back unstyled text, which looks exactly like the ordinary
        # nobody-is-watching answer — so the typo would be invisible to whoever made it.
        with self.assertRaises(ValueError) as refused:
            style.paint("x", "puce")
        self.assertIn("puce", str(refused.exception))

    def test_a_style_that_is_not_one_is_refused_even_with_nobody_watching(self):
        del os.environ["FORCE_COLOR"]
        with self.assertRaises(ValueError):
            style.paint("x", "puce", stream=io.StringIO())


class ReadingWhatIsThere(support.Isolated):
    """`plain` and `width` — what a machine gets, and what a person sees."""

    def test_plain_takes_every_sequence_out(self):
        self.assertEqual("FAILED", style.plain("\x1b[1;31mFAILED\x1b[0m"))

    def test_plain_leaves_ordinary_text_exactly_as_it_is(self):
        self.assertEqual("2026-08-04T03-00-00Z", style.plain("2026-08-04T03-00-00Z"))

    def test_width_is_what_a_person_sees_and_not_how_long_it_is(self):
        worn = "\x1b[1;31mFAILED\x1b[0m"
        self.assertEqual(6, style.width(worn))
        self.assertNotEqual(len(worn), style.width(worn))

    def test_width_of_ordinary_text_is_its_length(self):
        self.assertEqual(4, style.width("data"))


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

        landed = stage_copy(entry, self.into)

        self.assertEqual(self.into / ".a-directory.incoming", landed)
        self.assertEqual("kept", (landed / "below" / "thing").read_text())

    def test_it_copies_a_file(self):
        entry = self.home / "a-file"
        entry.write_text("kept")
        self.assertEqual("kept", stage_copy(entry, self.into).read_text())

    def test_it_copies_a_link_as_a_link_rather_than_following_it(self):
        # `is_dir()` answers True for a link pointing at a directory, so a copy that asked only that
        # would walk through it and duplicate the tree on the other side — silently, and only for
        # the owner who had one.
        real = self.home / "the-real-one"
        (real / "below").mkdir(parents=True)
        entry = self.home / "a-link"
        entry.symlink_to(real)

        landed = stage_copy(entry, self.into)

        self.assertTrue(landed.is_symlink())
        self.assertFalse((landed / "below").is_dir() and not landed.is_symlink())

    def test_it_clears_a_stale_staging_entry_first(self):
        # Litter from a run that died is not a reason for the next one to fail.
        entry = self.home / "a-directory"
        (entry / "wanted").mkdir(parents=True)
        stale = self.into / ".a-directory.incoming"
        (stale / "left-behind").mkdir(parents=True)

        landed = stage_copy(entry, self.into)

        self.assertTrue((landed / "wanted").is_dir())
        self.assertFalse((landed / "left-behind").exists())

    def test_it_leaves_out_what_it_was_told_to(self):
        entry = self.home / "a-directory"
        entry.mkdir()
        (entry / "wanted").write_text("yes")
        (entry / "__pycache__").mkdir()

        landed = stage_copy(entry, self.into, ignore=lambda _where, names:
                            {one for one in names if one == "__pycache__"})

        self.assertTrue((landed / "wanted").is_file())
        self.assertFalse((landed / "__pycache__").exists())

    def test_what_it_lands_is_a_staging_name_and_not_a_finished_one(self):
        entry = self.home / "a-file"
        entry.write_text("kept")
        self.assertTrue(staged(stage_copy(entry, self.into).name))


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
        self.assertEqual("WHAT  IS", style.plain(head))
        self.assertNotIn("\x1b", row, "an ordinary row was styled")

    def test_columns_line_up_when_a_cell_is_wearing_something(self):
        # The defect this exists to prevent: padding by `len()` counts the characters that draw
        # nothing, so the column is correct for plain text and ragged for anything styled — and
        # ragged only on somebody's real terminal, never in a captured test.
        worn = "\x1b[31ma\x1b[0m"
        head, first, second = printed(("WHAT", "IS"), [(worn, "1"), ("a-longer-cell", "2")]
                                      ).splitlines()
        self.assertEqual(style.plain(first).index("1"), style.plain(second).index("2"))
        self.assertEqual(style.plain(head).index("IS"), style.plain(first).index("1"))


if __name__ == "__main__":
    unittest.main()
