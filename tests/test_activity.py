"""Live turn records expose safe identity and cleanly support concurrency."""

import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from rundesk import activity, gateway  # noqa: E402

#: What the machine "said" about when a process began, in cases that supply the answer
#: rather than asking for it. A real `ps` reading would make two live readings of the same
#: moment the thing under test, which proves nothing and fails on a runner at a boundary.
WHEN = "when-this-turn-began"


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

    def began(self, run, conversation="room-1", started=None):
        activity.began(self.run_home, self.record(run, conversation),
                       started=started or (lambda pid: WHEN))

    def active(self, started=None):
        return activity.active(self.run_home, started=started or (lambda pid: WHEN))

    def kept(self):
        return sorted(p.name for p in (self.run_home / "turns").glob("*.json"))

    def test_simultaneous_turns_are_distinct_and_end_independently(self):
        """R-AGW-13"""
        self.began("one", "room-1")
        self.began("two", "room-2")
        self.assertEqual(["one", "two"], [row["run"] for row in self.active()])
        activity.ended(self.run_home, "one")
        self.assertEqual(["two"], [row["run"] for row in self.active()])

    def test_only_safe_identity_is_persisted(self):
        """R-AGW-14 — and `started` is a moment the machine reported, never a prompt."""
        self.began("one", "room-1")
        written = json.loads(next((self.run_home / "turns").glob("*.json")).read_text())
        self.assertEqual(
            {"conversation", "pid", "run", "since", "source", "started", "surface"},
            set(written),
        )

    def test_update_busy_reader_includes_provider_turns(self):
        """End to end through the real machine on purpose: the fingerprint has to survive
        being written by one call and read back by another, and that round trip is the
        subject here rather than something the case is working around."""
        activity.began(self.run_home, self.record("one", "room-1"))
        self.assertEqual(["turn:one"], gateway.what_is_running("ava", self.run_home))

    def test_a_turn_under_a_pid_the_machine_reissued_is_not_reported_as_live(self):
        """A gateway killed outright never reaches the `finally` that removes the record,
        and after a reboot the machine hands out low numbers first — so the pid written
        yesterday belongs to something else today. `os.kill(pid, 0)` answered yes, the dead
        turn was reported as still working, and that answer is what an update waits on
        before it may replace this install."""
        self.began("one", started=lambda pid: "when-the-turn-began")
        self.assertEqual([], self.active(started=lambda pid: "when-a-stranger-began"),
                         "a reissued pid was read as the turn that wrote the record")

    def test_a_turn_whose_process_is_gone_is_not_reported_as_live(self):
        gone = subprocess.Popen([sys.executable, "-c", ""])
        gone.wait()
        record = self.record("one", "room-1")
        record["pid"] = gone.pid
        activity.began(self.run_home, record, started=lambda pid: WHEN)
        self.assertEqual([], self.active())

    def test_a_row_nothing_can_parse_is_not_reported_as_live(self):
        self.began("one")
        next((self.run_home / "turns").glob("*.json")).write_text("{ not a record")
        self.assertEqual([], self.active())

    def test_a_probe_that_could_not_answer_does_not_drop_a_live_turn(self):
        """`started_at` reports None for a `ps` that timed out or a fork that failed under
        load — "I could not tell", not "a different process". Compared as an answer it is
        false of every recorded fingerprint, so one failed probe on a busy machine sweeps a
        running turn's record, `abandoned` marks the live run stopped, and the update that
        was waiting on that turn stops the gateway underneath it. The same conflation
        `gateway.CANNOT_BE_READ` exists to prevent, arrived at from the other side."""
        self.began("one", started=lambda pid: "when-the-turn-began")
        self.assertEqual(
            ["one"], [row["run"] for row in self.active(started=lambda pid: None)],
            "a probe that could not answer was read as a reissued pid")
        self.assertEqual([], activity.sweep(self.run_home, started=lambda pid: None))
        self.assertEqual(1, len(self.kept()), "it swept a turn it had just proved alive")

    def test_a_record_written_before_there_were_fingerprints_still_names_real_work(self):
        """Missing keeps the row and mismatched drops it — the asymmetry
        `gateway._end_left_running` already holds. An install brought forward while a turn
        was running has records with no `started` in them, and settling a turn that is
        genuinely alive is worse than carrying a dead one for one more look."""
        self.began("one")
        path = next((self.run_home / "turns").glob("*.json"))
        row = json.loads(path.read_text())
        del row["started"]
        path.write_text(json.dumps(row))
        self.assertEqual(
            ["one"],
            [r["run"] for r in self.active(started=lambda pid: "something-else-entirely")])

    def test_what_a_crashed_turn_left_behind_is_taken_away(self):
        """Nothing else in the product removes one. `ended` is called from the turn's own
        `finally`, which SIGKILL, an out-of-memory kill and a power cut all skip; release
        takes the record file and forget takes the record, the lock and the log. So one
        file per crashed turn stood for the life of the install."""
        self.began("one", started=lambda pid: "when-the-turn-began")
        self.assertEqual(1, len(self.kept()))
        went = activity.sweep(self.run_home, started=lambda pid: "when-a-stranger-began")
        self.assertEqual(1, len(went), "it said it swept nothing")
        self.assertEqual([], self.kept(), "the record it reported sweeping is still there")

    def test_a_turn_this_install_could_not_fingerprint_is_kept_while_its_pid_lives(self):
        """The accepted limit, written down so it is a decision rather than an oversight.

        A probe can fail at registration — `began` runs while the turn's own provider is
        being forked — and the row is then written with no fingerprint to compare. Such a
        row can never be told from a reused pid afterwards, so it is **kept for as long as
        that pid answers**, and an update may wait on a turn that has ended.

        Sweeping it instead was tried and reverted. Those rows always have a live pid — a
        dead one is already taken by the liveness check — so dropping them is not tidying
        up after a dead turn, it is deleting the record of a possibly-running one. Two
        independent paths proved it unsafe: an orphaned provider outliving the gateway that
        started it, and `rundesk ask`, which writes here from a standalone process holding
        no lock and having no gateway at all, so "the writer is proven gone" is never true
        of it. Keeping what cannot be proven is what `_anything_left`, `what_is_working`
        and `_end_left_running` all do; this is the same posture.
        """
        self.began("one", started=lambda pid: None)
        written = json.loads(next((self.run_home / "turns").glob("*.json")).read_text())
        self.assertIsNone(written["started"], "the probe was meant to have failed")
        self.assertEqual([], activity.sweep(self.run_home, started=lambda pid: WHEN),
                         "it deleted the record of a turn whose process is alive")
        self.assertEqual(1, len(self.kept()))

    def test_a_sweep_leaves_a_turn_that_is_still_running(self):
        """The half that keeps the sweep from being the bug: a live turn's record is what
        stops `abandoned` settling it, so taking one away would end a running turn's row."""
        self.began("one")
        self.assertEqual([], activity.sweep(self.run_home, started=lambda pid: WHEN))
        self.assertEqual(["one"], [row["run"] for row in self.active()])


if __name__ == "__main__":
    unittest.main()
