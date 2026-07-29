#!/usr/bin/env python3
"""The account of a run: what is a record, what is a file, and what each survives.

Answers for the account half of `agent-run` (R-RUN-n). What a run *recorded* is rows and
is asked for through `store.py`; what the brain itself printed and what it said went wrong
are the two files beside it, because the path to one is handed to a program that may be a
shell script and the other is an operating-system pipe.

**The point of the split is what it costs to lose either.** Delete the files and every
account still reads; the reverse is not true, and nothing here lets it become true.

Nothing reaches the network or runs a brain: a run is written the way a turn writes one.

Run: python3 tests/test_transcript.py
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from rundesk import agent, store, transcript  # noqa: E402

AT = "2026-07-26T09:00:00Z"
LATER = "2026-07-26T10:00:00Z"


class WithAnAgentThatHasRun(unittest.TestCase):
    """One agent of this case's own, and nothing of the machine's within reach."""

    def setUp(self):
        self.where = Path(tempfile.mkdtemp(prefix="rundesk-agents-"))
        self.addCleanup(shutil.rmtree, self.where, True)
        self.before = Path(tempfile.mkdtemp(prefix="rundesk-before-"))
        self.addCleanup(shutil.rmtree, self.before, True)
        # **The data root as well, and it is not optional.** Everything else here
        # falls back to it, so a fixture that isolates the four and forgets this
        # one still reaches the owner's real library — `add` grants what the
        # release ships, and would link a scratch agent at what they actually have.
        for said, at in (("RUNDESK_DATA_DIR", self.before / "data"),
                         ("RUNDESK_AGENTS_DIR", self.where),
                         ("RUNDESK_RUN_DIR", self.before / "run"),
                         ("RUNDESK_LOG_DIR", self.before / "logs"),
                         ("RUNDESK_SCHEDULES_DIR", self.before / "schedules"),
                         ("RUNDESK_JOBS_DIR", self.before / "jobs")):
            self.addCleanup(os.environ.pop, said, None)
            os.environ[said] = str(at)
            at.mkdir(parents=True, exist_ok=True)
        agent.add("ava", self.where)
        # With a brain, because an agent that has none is now a fault every diagnosis
        # reports (R-AGT-18) — and one case here asks a freshly made agent to have nothing
        # wrong with it. A fixture that left it out would put that complaint into a case
        # about where an account is kept.
        agent.remember("ava", self.where, provider="codex")

    def kept(self, name: str = "ava") -> store.Store:
        return agent.records(name, self.where)

    def logs(self, name: str = "ava") -> Path:
        return agent.logs_home(name, self.where)

    def where_it_is(self, kept, space: str = "terminal") -> str:
        named = store.conversation_id("terminal", space)
        kept.opened(named, "terminal", "terminal", space, AT)
        return named

    def a_run(self, kept, conversation=None, **held) -> str:
        settled = dict(source="terminal", provider="codex", posture="work",
                       started_at=AT, conversation_id=conversation)
        settled.update(held)
        return kept.began(**settled)

    def printed(self, run: str, said: bytes = b'{"type":"text"}\n') -> Path:
        """What a brain printed, written where an adapter would write it."""
        at = transcript.printed(self.logs(), run)
        at.parent.mkdir(parents=True, exist_ok=True)
        at.write_bytes(said)
        return at


class EveryRunHasAnIdOfItsOwn(WithAnAgentThatHasRun):
    def test_every_run_has_an_id_of_its_own(self):
        """R-RUN-1 — what its account, its cost and its outcome are all found by."""
        kept = self.kept()
        named = [self.a_run(kept) for _ in range(5)]
        self.assertEqual(5, len(set(named)))
        for one in named:
            self.assertIsNotNone(kept.run(one))

    def test_a_runs_place_in_the_order_does_not_depend_on_a_clock(self):
        """R-RUN-7 — the number counts, and a machine whose clock went backwards between
        two runs still reads them in the order the work happened."""
        kept = self.kept()
        first = self.a_run(kept, started_at=LATER)
        second = self.a_run(kept, started_at=AT)     # earlier by the clock, later in fact
        self.assertLess(kept.run(first)["n"], kept.run(second)["n"])

    def test_runs_are_read_back_in_the_order_they_were_admitted(self):
        """R-RUN-8"""
        kept = self.kept()
        named = [self.a_run(kept) for _ in range(3)]
        self.assertEqual(named, [one["id"] for one in reversed(kept.runs())])

    def test_two_accounts_of_one_conversation_read_in_the_order_the_work_happened(self):
        """R-RUN-8 — two turns in one conversation, read as one history rather than as
        two piles somebody has to interleave."""
        kept = self.kept()
        here, elsewhere = self.where_it_is(kept), self.where_it_is(kept, "planning")
        first = self.a_run(kept, here)
        away = self.a_run(kept, elsewhere)
        second = self.a_run(kept, here)
        self.assertEqual([first, second],
                         [one["id"] for one in reversed(kept.runs(conversation_id=here))])
        self.assertNotIn(away, [one["id"] for one in kept.runs(conversation_id=here)])


class WhatARunWritesDown(WithAnAgentThatHasRun):
    def test_a_runs_account_records_every_event_in_the_order_it_happened(self):
        """R-RUN-4"""
        kept = self.kept()
        run = self.a_run(kept)
        for seq, kind in enumerate(("think", "tool", "result", "usage", "done"), start=1):
            kept.recorded(run, seq, AT, kind, event={"type": kind})
        self.assertEqual(["think", "tool", "result", "usage", "done"],
                         [one["kind"] for one in kept.records(run)])

    def test_a_runs_account_is_added_to_and_never_rewritten(self):
        """R-RUN-5 — a place in the order is claimed once. A second record taking one
        already taken is refused rather than replacing what stood there."""
        kept = self.kept()
        run = self.a_run(kept)
        kept.recorded(run, 1, AT, "think", event={"text": "first"})
        with self.assertRaises(Exception):
            kept.recorded(run, 1, LATER, "think", event={"text": "written over it"})
        self.assertEqual([{"text": "first"}], [one["event"] for one in kept.records(run)])

    def test_the_order_of_a_runs_account_does_not_depend_on_a_clock(self):
        """R-RUN-7 — `seq` is the order and a clock is not, so an account written by a
        machine whose clock went backwards still reads in the order the work was done."""
        kept = self.kept()
        run = self.a_run(kept)
        going_back = ("2026-07-26T09:00:03Z", "2026-07-26T09:00:02Z", "2026-07-26T09:00:01Z")
        for seq, at in zip((3, 2, 1), going_back):
            kept.recorded(run, seq, at, "think", event={"n": seq})
        self.assertEqual([1, 2, 3], [one["seq"] for one in kept.records(run)])

    def test_everything_a_brain_said_is_kept_exactly_as_it_said_it(self):
        """R-RUN-6 — beside what rundesk made of it, and in a row rather than only in a
        file, so a machine that swept what the brain printed still has every line."""
        kept = self.kept()
        run = self.a_run(kept)
        said = '{"type":"tool","name":"grep","extra":"nobody here knows"}'
        kept.recorded(run, 1, AT, "tool", event={"name": "grep"}, raw=said)
        self.assertEqual(said, kept.records(run)[0]["raw"])

    def test_a_record_rundesk_did_not_understand_is_still_in_the_run_afterwards(self):
        """R-RUN-6, R-PRV-5 — kept as `unknown` with its own words beside it, because a
        record nobody could read today is still there to be read next year."""
        kept = self.kept()
        run = self.a_run(kept)
        kept.recorded(run, 1, AT, "unknown", raw='{"type":"constellation","shape":"orion"}')
        one = kept.records(run)[0]
        self.assertEqual("unknown", one["kind"])
        self.assertIsNone(one["event"], "the seam claimed to have understood it")
        self.assertIn("orion", one["raw"])


class WhatTheBrainItselfSaid(WithAnAgentThatHasRun):
    """The two files, and the whole reason they are files."""

    def test_what_a_brain_said_went_wrong_is_kept_and_kept_out_of_the_account(self):
        """R-PRV-6 — an operating-system pipe, kept where a person can read it and out of
        the records, which are what a cost and a history are read from."""
        kept = self.kept()
        run = self.a_run(kept)
        at = transcript.beside(self.logs(), run)
        at.parent.mkdir(parents=True, exist_ok=True)
        at.write_bytes(b"a warning worth keeping\n")

        self.assertEqual(b"a warning worth keeping\n",
                         transcript.read(self.logs(), run, transcript.ERRORS))
        self.assertEqual([], kept.records(run), "what went wrong reached the account")

    def test_what_a_brain_said_can_be_thrown_away_while_the_account_stands(self):
        """R-RUN-5, R-STO-5 — the whole reason those files are separable. Deleting them
        is not rewriting an account, which is how both rules hold at once."""
        kept = self.kept()
        run = self.a_run(kept)
        kept.recorded(run, 1, AT, "tool", event={"name": "grep"}, raw='{"type":"tool"}')
        self.printed(run)

        shutil.rmtree(transcript.home(self.logs()))
        self.assertEqual(b"", transcript.read(self.logs(), run))
        self.assertEqual([("tool", '{"type":"tool"}')],
                         [(one["kind"], one["raw"]) for one in kept.records(run)])

    def test_both_files_of_one_run_are_named_in_one_place(self):
        """A second list is one that falls behind: what removing a run has to take and
        what writing it made must be the same answer."""
        self.assertEqual([transcript.printed(self.logs(), "1-abcd"),
                          transcript.beside(self.logs(), "1-abcd")],
                         transcript.kept(self.logs(), "1-abcd"))

    def test_what_is_on_disk_is_asked_of_the_disk_rather_than_of_the_records(self):
        """The two are compared rather than assumed to agree — a run whose file was swept
        is ordinary, and a file whose run is unknown is not."""
        kept = self.kept()
        run = self.a_run(kept)
        self.assertEqual([], transcript.known(self.logs()), "a run that printed nothing")
        self.printed(run)
        self.printed("9-zzzz")
        self.assertEqual([run, "9-zzzz"], sorted(transcript.known(self.logs())))
        self.assertEqual([run], [one["id"] for one in kept.runs()])


class WhatAnAgentPrintedIsBounded(WithAnAgentThatHasRun):
    """R-RUN-22, R-RUN-23 — reported (#101): nothing swept these and nothing bounded them.

    Measured on a two-day-old agent: 807 MB across 384 files against 7.7 MB of records,
    largest single transcript 51.9 MB, because a brain replays the whole prior thread when
    it attaches and every run writes those same bytes to disk again.
    """

    def a_long_one(self, run: str, ceiling: int) -> Path:
        """A transcript over the ceiling, whose every line says where in the file it is."""
        at = transcript.printed(self.logs(), run)
        at.parent.mkdir(parents=True, exist_ok=True)
        with open(at, "wb") as writing:
            line = 0
            while writing.tell() <= ceiling * 2:
                writing.write(b'{"type":"text","line":%d,"pad":"%s"}\n'
                              % (line, b"x" * 200))
                line += 1
        self.lines = line
        return at

    def test_what_a_brain_printed_is_cut_down_to_the_ceiling(self):
        """R-RUN-22 — a run whose transcript is tens of megabytes is not diagnosable by a
        person or a grep either way, and it is the same historical bytes every time."""
        run = self.a_run(self.kept())
        at = self.a_long_one(run, 64 * 1024)
        was = at.stat().st_size

        elided = transcript.trim(self.logs(), run, ceiling=64 * 1024)
        self.assertTrue(elided, "nothing was elided from a transcript over the ceiling")
        self.assertLessEqual(at.stat().st_size, 64 * 1024 + 512,
                             "the transcript is still over the ceiling")
        self.assertLess(at.stat().st_size, was)

    def test_the_end_of_a_run_is_what_is_kept_and_the_replay_is_what_goes(self):
        """The beginning is the handshake and the prior thread replayed back — already on
        disk under the runs it belongs to. The end is this turn, and its only copy."""
        run = self.a_run(self.kept())
        self.a_long_one(run, 64 * 1024)

        transcript.trim(self.logs(), run, ceiling=64 * 1024)
        lines = transcript.read(self.logs(), run).splitlines()
        self.assertEqual(self.lines - 1, json.loads(lines[-1])["line"],
                         "the end of the run did not survive")
        self.assertEqual(0, sum(1 for one in lines if b'"line":0' in one),
                         "the beginning was kept instead of the end")

    def test_what_was_cut_away_says_so_where_the_transcript_is_read(self):
        """Never a silent truncation. A file that simply begins mid-conversation is one a
        reader takes at face value, and this one deliberately does not hold everything."""
        run = self.a_run(self.kept())
        transcript.trim(self.logs(), self.a_long_one(run, 64 * 1024) and run,
                        ceiling=64 * 1024)
        first = json.loads(transcript.read(self.logs(), run).splitlines()[0])
        self.assertEqual("elided", first["type"])
        self.assertGreater(first["bytes"], 0)

    def test_every_line_left_is_still_a_whole_record(self):
        """Cutting at a byte offset lands mid-record, and a `.jsonl` whose first line is
        half a record is one nothing can read."""
        run = self.a_run(self.kept())
        self.a_long_one(run, 64 * 1024)
        transcript.trim(self.logs(), run, ceiling=64 * 1024)
        for line in transcript.read(self.logs(), run).splitlines():
            json.loads(line)

    def test_a_transcript_under_the_ceiling_is_left_exactly_as_it_is(self):
        """Doing nothing is the ordinary outcome, and rewriting a small file every turn
        would cost more than the ceiling saves."""
        run = self.a_run(self.kept())
        at = self.printed(run, b'{"type":"text"}\n')
        transcript.trim(self.logs(), run, ceiling=64 * 1024)
        self.assertEqual(b'{"type":"text"}\n', at.read_bytes())

    def test_a_transcript_that_is_not_there_is_not_an_error(self):
        """An adapter that keeps nothing is a perfectly good adapter, and reclaiming space
        is never allowed to be the reason a turn fails."""
        self.assertEqual(0, transcript.trim(self.logs(), "1-none"))

    def test_what_a_brain_printed_longer_ago_than_the_window_is_swept(self):
        """R-RUN-23 — the broom this module has always said it is swept by. These are
        diagnostics and may be destroyed to reclaim space without costing the account
        anything (R-STO-5); nothing swept them at all."""
        kept = self.kept()
        old, new = self.a_run(kept), self.a_run(kept)
        for run in (old, new):
            self.printed(run)
            transcript.beside(self.logs(), run).write_bytes(b"a warning\n")
        long_ago = time.time() - 30 * 86400
        os.utime(transcript.printed(self.logs(), old), (long_ago, long_ago))

        self.assertEqual([old], transcript.sweep(self.logs(), keep_days=7))
        self.assertEqual([new], transcript.known(self.logs()))
        self.assertFalse(transcript.beside(self.logs(), old).exists(),
                         "half of a run's files were left behind")
        self.assertTrue(transcript.beside(self.logs(), new).exists())

    def test_sweeping_what_a_brain_printed_leaves_every_account_readable(self):
        """R-STO-5 — the whole reason these are separable from the records. Sweeping is
        reclaiming space, and it must cost an owner nothing they need."""
        kept = self.kept()
        run = self.a_run(kept)
        kept.recorded(run, 1, AT, "tool", event={"name": "grep"}, raw='{"type":"tool"}')
        self.printed(run)
        long_ago = time.time() - 30 * 86400
        os.utime(transcript.printed(self.logs(), run), (long_ago, long_ago))

        self.assertEqual([run], transcript.sweep(self.logs(), keep_days=7))
        self.assertEqual([("tool", '{"type":"tool"}')],
                         [(one["kind"], one["raw"]) for one in kept.records(run)])
        self.assertEqual([run], [one["id"] for one in kept.runs()])

    def test_sweeping_where_nothing_was_ever_printed_is_ordinary(self):
        """An agent that has never run, and a window nobody set — neither is an error."""
        self.assertEqual([], transcript.sweep(self.logs()))
        self.printed(self.a_run(self.kept()))
        self.assertEqual([], transcript.sweep(self.logs(), keep_days=0),
                         "a window of nothing swept everything rather than nothing")


class WhatAnAgentKeepsAnAccountIn(WithAnAgentThatHasRun):
    """The account stands with the agent's own things, and lasts as long as they do."""

    def test_an_agent_is_made_with_somewhere_to_keep_what_it_did(self):
        """R-RUN-2 — made with the agent rather than on first use, so nothing has to
        decide, mid-turn, whether this is the first run there has ever been."""
        self.assertEqual([], self.kept().runs())
        self.assertEqual([], agent.diagnosed("ava", self.where, root=self.before))

    def test_where_an_agent_keeps_what_it_did_is_not_where_its_gateway_keeps_what_it_is_doing(self):
        """R-RUN-10 — one is emptied when a gateway stops and the other is what an owner
        still has afterwards."""
        self.assertNotEqual(agent.run_home("ava", self.where),
                            store.path_for(agent.directory("ava", self.where)))

    def test_one_agents_account_is_not_another_agents(self):
        """R-AGT-7 — an account is what one agent did, and two of them sharing one would
        put one agent's write lock in the other's way as well as its history."""
        agent.add("bo", self.where)
        mine = self.a_run(self.kept("ava"))
        self.assertEqual([mine], [one["id"] for one in self.kept("ava").runs()])
        self.assertEqual([], self.kept("bo").runs())

    def test_a_runs_account_outlives_the_gateway_that_wrote_it(self):
        """R-RUN-10 — nothing was running to record it and nothing has to be running to
        read it back. Opened fresh, with no turn and no gateway anywhere in reach."""
        kept = self.kept()
        run = self.a_run(kept)
        kept.recorded(run, 1, AT, "tool", event={"name": "grep"})
        kept.ended(run, LATER, "finished", tokens={"input": 10, "reported": True})

        back = store.Store(store.path_for(agent.directory("ava", self.where)))
        back.made()
        self.assertEqual("finished", back.run(run)["outcome"])
        self.assertEqual([("tool", {"name": "grep"})],
                         [(one["kind"], one["event"]) for one in back.records(run)])

    def test_taking_an_agent_away_takes_what_a_run_did(self):
        """R-AGW-5, R-RUN-10 — the account lasts as long as the agent and no longer. Left
        behind, it was inherited by whoever took the name next, which is a new agent
        standing on an old one's history."""
        kept = self.kept()
        run = self.a_run(kept)
        kept.recorded(run, 1, AT, "tool", event={"name": "grep"})
        self.printed(run)

        taken = agent.forget("ava", self.where)
        self.assertIn(store.NAME, taken)
        self.assertIn("logs/", taken, "what the brain printed was left behind")
        self.assertFalse(agent.directory("ava", self.where).exists())

    def test_every_place_an_agent_resolves_includes_where_its_account_goes(self):
        """R-AGT-14 — an owner asking where an agent keeps things is asking about all of
        them, and one left out of that answer is one nobody knows to look at."""
        said = agent.paths("ava", self.where)
        self.assertIn(store.path_for(said["agent"]),
                      [store.path_for(one) for one in said.values()])
        self.assertTrue(store.path_for(said["agent"]).is_file())


if __name__ == "__main__":
    unittest.main(verbosity=2)
