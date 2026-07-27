"""Live turn records expose safe identity and cleanly support concurrency."""

import json
import os
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from rundesk import activity, gateway  # noqa: E402


class ActiveTurns(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.run_home = pathlib.Path(self.temporary.name)

    def record(self, run, conversation):
        return {
            "run": run, "source": "channel", "surface": "discord",
            "conversation": conversation, "pid": os.getpid(), "since": 10.0,
            "prompt": "must never be kept", "arguments": ["--token", "secret"],
        }

    def test_simultaneous_turns_are_distinct_and_end_independently(self):
        """R-AGW-13"""
        activity.began(self.run_home, self.record("one", "room-1"))
        activity.began(self.run_home, self.record("two", "room-2"))
        self.assertEqual(["one", "two"], [row["run"] for row in activity.active(self.run_home)])
        activity.ended(self.run_home, "one")
        self.assertEqual(["two"], [row["run"] for row in activity.active(self.run_home)])

    def test_only_safe_identity_is_persisted(self):
        """R-AGW-14"""
        activity.began(self.run_home, self.record("one", "room-1"))
        written = json.loads(next((self.run_home / "turns").glob("*.json")).read_text())
        self.assertEqual(
            {"conversation", "pid", "run", "since", "source", "surface"},
            set(written),
        )

    def test_update_busy_reader_includes_provider_turns(self):
        activity.began(self.run_home, self.record("one", "room-1"))
        self.assertEqual(["turn:one"], gateway.what_is_running("ava", self.run_home))


if __name__ == "__main__":
    unittest.main()
