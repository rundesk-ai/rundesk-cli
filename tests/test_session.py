"""Where a conversation got to — the rows of agent-run about carrying one on.

Nothing here starts a brain. A handle is a string rundesk never reads, and the whole
subject is which conversation and which brain it is kept under.

Run: python3 tests/test_session.py
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from rundesk import session  # noqa: E402


class WithAnAgentsOwnDirectory(unittest.TestCase):
    def setUp(self):
        self.where = Path(tempfile.mkdtemp(prefix="rundesk-session-"))
        self.addCleanup(shutil.rmtree, self.where, True)


class CarryingAConversationOn(WithAnAgentsOwnDirectory):
    def test_a_conversation_continues_from_the_handle_its_brain_last_reported(self):
        """R-RUN-11 — the whole point: a second turn picks up where the first left off,
        without rundesk knowing what a handle means."""
        self.assertIsNone(session.of(self.where, "codex", "terminal"))
        session.remember(self.where, "codex", "terminal", "thread-019f")
        self.assertEqual("thread-019f", session.of(self.where, "codex", "terminal"))

    def test_a_handle_is_kept_for_one_conversation_and_one_brain_together(self):
        """R-RUN-12 — kept for the conversation alone, changing an agent's provider hands
        one brain's session to the next, which is what the build this replaces does."""
        session.remember(self.where, "codex", "terminal", "thread-019f")
        self.assertIsNone(session.of(self.where, "claude", "terminal"),
                          "one brain was handed another brain's session")
        self.assertIsNone(session.of(self.where, "codex", "operations"),
                          "one conversation was handed another conversation's session")

    def test_the_brain_a_handle_belongs_to_is_the_shape_of_the_book(self):
        """R-RUN-12 — the pairing is the file's shape rather than a rule to remember, so
        dropping the brain from the key is not a mistake that can be made here."""
        session.remember(self.where, "codex", "terminal", "one")
        session.remember(self.where, "/opt/my-brain", "terminal", "two")
        written = json.loads(session.book(self.where).read_text())
        self.assertEqual({"codex": {"terminal": "one"},
                          "/opt/my-brain": {"terminal": "two"}}, written)

    def test_a_brain_that_reported_no_handle_leaves_nothing_kept(self):
        """R-RUN-11 — an adapter that cannot carry a conversation on says nothing, and
        nothing is what should then be remembered about it."""
        self.assertFalse(session.remember(self.where, "codex", "terminal", ""))
        self.assertIsNone(session.of(self.where, "codex", "terminal"))
        self.assertFalse(session.book(self.where).exists())

    def test_a_later_turn_replaces_what_an_earlier_one_reported(self):
        """R-RUN-11 — a conversation has one place it got to, and it is the last one."""
        session.remember(self.where, "codex", "terminal", "first")
        session.remember(self.where, "codex", "terminal", "second")
        self.assertEqual("second", session.of(self.where, "codex", "terminal"))

    def test_a_conversation_can_be_started_fresh_without_touching_the_others(self):
        """R-RUN-14 — an owner asking one conversation to start again is asking about
        that one, and taking the others with it would be a surprise nobody asked for."""
        session.remember(self.where, "codex", "terminal", "one")
        session.remember(self.where, "codex", "operations", "two")
        session.forget(self.where, "codex", "terminal")
        self.assertIsNone(session.of(self.where, "codex", "terminal"))
        self.assertEqual("two", session.of(self.where, "codex", "operations"))


class WhenTheBookIsLost(WithAnAgentsOwnDirectory):
    def test_losing_what_a_conversation_was_continuing_costs_the_next_turn_its_context(self):
        """R-RUN-14 — and nothing else. That is the whole reason this is a small file
        rather than anything larger."""
        session.remember(self.where, "codex", "terminal", "thread-019f")
        session.book(self.where).unlink()
        self.assertIsNone(session.of(self.where, "codex", "terminal"))
        self.assertTrue(session.remember(self.where, "codex", "terminal", "a-new-one"))
        self.assertEqual("a-new-one", session.of(self.where, "codex", "terminal"))

    def test_a_book_that_cannot_be_read_is_not_an_empty_one(self):
        """R-RUN-14 — writing an empty book over an unreadable one throws away every
        other conversation to save this one, and leaves nothing for a person to look at."""
        session.book(self.where).write_text("{ this was never JSON", encoding="utf-8")
        self.assertIsNone(session.of(self.where, "codex", "terminal"))
        self.assertFalse(session.remember(self.where, "codex", "terminal", "a-handle"),
                         "it reported keeping a handle it could not keep")
        self.assertEqual("{ this was never JSON",
                         session.book(self.where).read_text(),
                         "an unreadable book was written over rather than left alone")

    def test_a_book_holding_something_that_is_not_a_book_is_read_as_nothing(self):
        """R-RUN-14 — a list where an object should be is as unreadable as a stray
        character, and asking it for a conversation must not raise in the middle of a
        turn."""
        session.book(self.where).write_text('["not a book"]', encoding="utf-8")
        self.assertIsNone(session.of(self.where, "codex", "terminal"))
        session.book(self.where).write_text('{"codex": "not a brains book"}',
                                            encoding="utf-8")
        self.assertIsNone(session.of(self.where, "codex", "terminal"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
