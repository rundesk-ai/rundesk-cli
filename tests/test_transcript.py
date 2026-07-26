"""What a run leaves behind — every row of agent-run that is about the account itself.

Nothing here starts a brain or reaches the network. An account is a file, and the whole
point of it is that it can be read with nothing else running.

Run: python3 tests/test_transcript.py
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from rundesk import agent, transcript  # noqa: E402


class WithSomewhereToKeepRuns(unittest.TestCase):
    """A run directory of this case's own, and a clock it decides."""

    def setUp(self):
        self.runs = Path(tempfile.mkdtemp(prefix="rundesk-runs-"))
        self.addCleanup(shutil.rmtree, self.runs, True)
        self.clock = [1_700_000_000.0]

    def now(self) -> float:
        self.clock[0] += 1
        return self.clock[0]

    def writer(self, run: str | None = None, agent_name: str = "ava") -> transcript.Writer:
        made = transcript.Writer(self.runs, run or self.allocate(), agent_name, now=self.now)
        self.addCleanup(made.close)
        return made

    def allocate(self) -> str:
        picked = iter("wxyz")
        return transcript.allocate(self.runs, pick=lambda _: next(picked))


class EveryRunHasAnIdOfItsOwn(WithSomewhereToKeepRuns):
    def test_every_run_has_an_id_of_its_own(self):
        """R-RUN-1"""
        every = {transcript.allocate(self.runs) for _ in range(20)}
        self.assertEqual(20, len(every), "two runs were given one id")

    def test_a_runs_place_in_the_order_does_not_depend_on_a_clock(self):
        """R-RUN-7 — numbered rather than stamped, so the order runs were admitted in
        survives a clock that went backwards and a machine in another timezone."""
        made = [transcript.allocate(self.runs) for _ in range(12)]
        self.assertEqual([str(n) for n in range(1, 13)],
                         [one.partition("-")[0] for one in made])

    def test_runs_are_read_back_in_the_order_they_were_admitted(self):
        """R-RUN-8 — run ten sorts before run nine as text, and an account read in the
        wrong order is worse than no account."""
        made = [transcript.allocate(self.runs) for _ in range(12)]
        self.assertEqual(made, transcript.known(self.runs))

    def test_a_lost_count_never_hands_out_a_name_that_is_taken(self):
        """R-RUN-1 — the count beside the runs is a hint and the directory is the truth.
        Losing the hint must not quietly write a second run into the first one's file.

        The mark is fixed here on purpose. Left random it hides the very thing under
        test: a second run numbered one gets a different mark, so no two names collide
        and the case passes with nothing checking the directory at all."""
        same = lambda _: "a"  # noqa: E731 — so a lost count really does repeat a name
        made = [transcript.allocate(self.runs, pick=same) for _ in range(3)]
        self.assertEqual(["1-aaaa", "2-aaaa", "3-aaaa"], made)
        (self.runs / transcript.ALLOCATING).unlink()
        after = transcript.allocate(self.runs, pick=same)
        self.assertNotIn(after, made, "a name already taken was handed out again")
        self.assertEqual(["1-aaaa", "2-aaaa", "3-aaaa", after], transcript.known(self.runs))


class WhatARunWritesDown(WithSomewhereToKeepRuns):
    def test_a_runs_account_records_every_event_in_the_order_it_happened(self):
        """R-RUN-4"""
        writing = self.writer()
        for n in range(5):
            writing.add(event={"type": "text", "text": f"n{n}"})
        said = transcript.read(self.runs, writing.run)
        self.assertEqual([1, 2, 3, 4, 5], [one["seq"] for one in said])
        self.assertEqual(["n0", "n1", "n2", "n3", "n4"],
                         [one["event"]["text"] for one in said])

    def test_a_runs_account_is_added_to_and_never_rewritten(self):
        """R-RUN-5 — an account that can be rewritten is one that can be made to say
        something else afterwards, which is the one thing an account may not be."""
        writing = self.writer()
        writing.add(event={"type": "text", "text": "first"})
        at = self.runs / (writing.run + transcript.ACCOUNT)
        was = at.read_text()
        writing.add(event={"type": "done", "ok": True})
        self.assertTrue(at.read_text().startswith(was), "what was written was rewritten")

    def test_the_order_of_a_runs_account_does_not_depend_on_a_clock(self):
        """R-RUN-7 — a clock that goes backwards, which is an ordinary thing for a clock
        to do, must not reorder what happened."""
        going_back = iter([500.0, 400.0, 300.0])
        writing = transcript.Writer(self.runs, self.allocate(), "ava",
                                    now=lambda: next(going_back))
        self.addCleanup(writing.close)
        for n in range(3):
            writing.add(event={"type": "text", "text": f"n{n}"})
        said = transcript.read(self.runs, writing.run)
        self.assertEqual([1, 2, 3], [one["seq"] for one in said])
        self.assertEqual(["n0", "n1", "n2"], [one["event"]["text"] for one in said])

    def test_two_accounts_of_one_conversation_read_in_the_order_the_work_happened(self):
        """R-RUN-8 — a conversation is more than one run, and reading them together has
        to give the order the work really happened in."""
        first, second = self.writer(), self.writer()
        first.add(event={"type": "text", "text": "earlier"})
        second.add(event={"type": "text", "text": "later"})
        together = [(run, one["seq"], one["event"]["text"])
                    for run in transcript.known(self.runs)
                    for one in transcript.read(self.runs, run)]
        self.assertEqual([(first.run, 1, "earlier"), (second.run, 1, "later")], together)

    def test_a_runs_account_outlives_the_gateway_that_wrote_it(self):
        """R-RUN-10 — the whole point. An agent that worked all night is only worth
        having if what it did can be read back, and nothing has to be running to do it."""
        writing = self.writer()
        writing.add(event={"type": "done", "ok": True})
        writing.close()
        said = transcript.read(self.runs, writing.run)
        self.assertEqual([{"type": "done", "ok": True}],
                         [one["event"] for one in said])

    def test_an_account_torn_by_a_machine_going_down_is_still_an_account(self):
        """R-RUN-4 — a record half written by a machine that lost power is the last one,
        and everything before it happened. Refusing the file loses all of it."""
        writing = self.writer()
        writing.add(event={"type": "text", "text": "before"})
        writing.close()
        at = self.runs / (writing.run + transcript.ACCOUNT)
        with open(at, "a", encoding="utf-8") as torn:
            torn.write('{"run": "x", "seq": 2, "at')
        said = transcript.read(self.runs, writing.run)
        self.assertEqual(1, len(said))
        self.assertEqual("before", said[0]["event"]["text"])


class WhatTheBrainItselfSaid(WithSomewhereToKeepRuns):
    def test_everything_a_brain_said_is_kept_exactly_as_it_said_it(self):
        """R-RUN-6 — a format that drifts has to be visible as drift rather than as a
        silent gap, and the only thing that can show that is what actually arrived."""
        writing = self.writer()
        writing.add(event={"type": "text", "text": "hello"},
                    raw=b'{"type":"item.completed","item":{"text":"hello"}}')
        writing.add(raw=b'{"type":"something.new","shape":"orion"}')
        self.assertEqual(
            b'{"type":"item.completed","item":{"text":"hello"}}\n'
            b'{"type":"something.new","shape":"orion"}\n',
            transcript.raw(self.runs, writing.run))

    def test_a_record_rundesk_did_not_understand_is_still_in_the_run_afterwards(self):
        """R-PRV-5 — a brain that can only grow when we release is one we have made
        slower than we are. Its place in the order is kept, nothing is claimed about it,
        and what it actually said is there to be read."""
        writing = self.writer()
        writing.add(raw=b'{"type":"constellation"}')
        writing.add(event={"type": "done", "ok": True}, raw=b'{"type":"done"}')
        said = transcript.read(self.runs, writing.run)
        self.assertEqual(2, len(said), "it lost the record's place in the order")
        self.assertNotIn("event", said[0], "it passed off a record it does not understand")
        self.assertIn(b"constellation", transcript.raw(self.runs, writing.run))
        self.assertEqual([{"type": "done", "ok": True}],
                         transcript.events(self.runs, writing.run))

    def test_what_a_brain_said_went_wrong_is_kept_and_kept_out_of_the_account(self):
        """R-PRV-6 — it is where a brain says why it died, and a reader that could not
        tell it from the work would be reading warnings as results."""
        writing = self.writer()
        writing.went_wrong(b"could not reach the model")
        writing.add(event={"type": "done", "ok": False})
        self.assertEqual(b"could not reach the model\n",
                         transcript.raw(self.runs, writing.run, transcript.ERRORS))
        self.assertEqual([{"type": "done", "ok": False}],
                         transcript.events(self.runs, writing.run))

    def test_what_a_brain_said_can_be_thrown_away_while_the_account_stands(self):
        """R-RUN-5, R-RUN-10 — what a brain said is most of the bytes and the least of
        the meaning. Kept in its own file, a retention policy can one day take it by
        deleting a file, which is not the same as rewriting one."""
        writing = self.writer()
        writing.add(event={"type": "text", "text": "kept"}, raw=b'{"vendor":"noise"}')
        writing.went_wrong(b"a warning nobody needs a year later")
        # An adapter may have written what its own brain said beside these; nothing here
        # does, so the case takes whichever of them a run turned out to have.
        (self.runs / (writing.run + transcript.BRAIN)).write_bytes(b'{"vendor":"own words"}\n')
        writing.close()
        for which in transcript.KEPT:
            (self.runs / (writing.run + which)).unlink()
        self.assertEqual([{"type": "text", "text": "kept"}],
                         transcript.events(self.runs, writing.run))
        for which in transcript.KEPT:
            self.assertEqual(b"", transcript.raw(self.runs, writing.run, which))


class WhatAnAgentKeepsAnAccountIn(unittest.TestCase):
    """The account stands with the agent's own things, and lasts as long as they do."""

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

    def test_an_agent_is_made_with_somewhere_to_keep_what_it_did(self):
        """R-RUN-2 — made with the agent rather than on first use, so the one list that
        making and diagnosing both read covers it."""
        self.assertTrue(agent.runs_home("ava", self.where).is_dir())
        self.assertIn("runs", agent.made_of("ava", self.where))
        self.assertEqual([], agent.diagnosed("ava", self.where, root=self.before))

    def test_where_an_agent_keeps_what_it_did_is_not_where_its_gateway_keeps_what_it_is_doing(self):
        """R-RUN-10 — one is emptied when a gateway stops and the other is what an owner
        still has afterwards. One letter apart and opposite in lifetime."""
        self.assertNotEqual(agent.run_home("ava", self.where),
                            agent.runs_home("ava", self.where))

    def test_taking_an_agent_away_keeps_the_account_of_what_it_did(self):
        """R-AGW-5 — a reinstall after trouble is exactly when the account of the trouble
        matters most, and it was being deleted by the command run to fix the trouble."""
        writing = transcript.Writer(agent.runs_home("ava", self.where), "1-abcd", "ava")
        writing.add(event={"type": "done", "ok": True})
        writing.close()
        agent.forget("ava", self.where)
        self.assertEqual(["1-abcd"], transcript.known(agent.runs_home("ava", self.where)))

    def test_a_removal_asked_for_the_account_too_takes_what_a_run_did(self):
        """R-AGW-5 — asked for out loud, and then everything goes."""
        writing = transcript.Writer(agent.runs_home("ava", self.where), "1-abcd", "ava")
        writing.add(event={"type": "done", "ok": True})
        writing.close()
        taken = agent.forget("ava", self.where, history=True)
        self.assertIn("runs/", taken)
        self.assertFalse(agent.runs_home("ava", self.where).exists())

    def test_one_agents_account_is_not_another_agents(self):
        """R-AGT-7 — an account is what an agent did, and two of them sharing one would
        make either unreadable."""
        agent.add("bo", self.where)
        self.assertNotEqual(agent.runs_home("ava", self.where),
                            agent.runs_home("bo", self.where))

    def test_every_place_an_agent_resolves_includes_where_its_account_goes(self):
        """R-AGT-14 — an owner asking where an agent keeps things is asking about all of
        them, and one left out of that answer is one nobody knows to look at."""
        said = json.dumps({what: str(at) for what, at
                           in agent.paths("ava", self.where).items()})
        self.assertIn("runs", said)


if __name__ == "__main__":
    unittest.main(verbosity=2)
