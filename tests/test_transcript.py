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

import os
import shutil
import sys
import tempfile
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
        for said, at in (("RUNDESK_AGENTS_DIR", self.where),
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
