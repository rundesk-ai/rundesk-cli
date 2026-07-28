"""Codex, as the brain rundesk ships an adapter for.

**Nothing here starts codex.** What is tested is the policy this adapter decides on its
own: where standing instructions go, and where they must never go. The wire — the
app-server protocol, a model, a token — is what the canary is for, and what a fake can
never prove.

Two things tested here were established by probing a real codex rather than by reading its
schema, and both are recorded in `.knowledge/MEMORY.md`:

- `developerInstructions` is *added* to what codex was built with. Given one, it obeyed it
  and its shell tool still worked. `baseInstructions`, sitting next to it, replaces them.
- It binds where a thread is *created*. Passed to `thread/resume` it is accepted and then
  ignored — the same rule was obeyed at `thread/start` and absent after a resume, in a
  fresh process, which is the shape rundesk actually runs.

The adapter is loaded by path rather than imported as a module, because it is not one: it
is a program, which is the whole point of the seam.

Run: python3 tests/test_codex.py
"""

from __future__ import annotations

import contextlib
import importlib.machinery
import importlib.util
import io
import json
import os
import re
import sys
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

AT = ROOT / "src" / "providers" / "codex"


def _adapter():
    """The adapter, loaded from its path — it is a program, not a module."""
    loader = importlib.machinery.SourceFileLoader("rundesk_codex", str(AT))
    spec = importlib.util.spec_from_loader("rundesk_codex", loader)
    made = importlib.util.module_from_spec(spec)
    loader.exec_module(made)
    return made


codex = _adapter()

# The seam's own words, to check this adapter answers for every one of them.
from rundesk import provider  # noqa: E402


class Asked:
    """A stand-in codex that remembers what it was asked, and agrees to everything."""

    def __init__(self, resume_works=True):
        self.asked: list = []
        self.resume_works = resume_works

    def ask(self, method, params=None):
        self.asked.append((method, dict(params or {})))
        return len(self.asked)

    def answered(self, which):
        method = self.asked[which - 1][0]
        if method == "thread/resume" and not self.resume_works:
            return None
        return {"result": {"thread": {"id": "a-thread"}}}

    def sent(self, method) -> dict | None:
        for one, params in self.asked:
            if one == method:
                return params
        return None


class WhenItHandsWorkToAHelper(unittest.TestCase):
    def test_one_delegation_is_reported_once(self):
        """R-PRV-8, R-PRV-21 — Codex reports one spawn as both child activity and the
        call that started it; counting both would claim that two subagents were made."""
        self.assertEqual("delegate", codex.DID.get("subAgentActivity"))
        self.assertNotIn("collabAgentToolCall", codex.DID)
        self.assertTrue(codex._quiet_activity(
            {"type": "collabAgentToolCall", "tool": "spawnAgent"}))

    def test_collaboration_bookkeeping_is_not_another_delegation(self):
        """R-PRV-8 — waiting for or closing a helper does not hand work to a new one."""
        for tool in ("spawnAgent", "sendInput", "resumeAgent", "wait", "closeAgent"):
            self.assertTrue(codex._quiet_activity(
                {"type": "collabAgentToolCall", "tool": tool}), tool)

    def test_finish_waits_for_the_child_turn_not_the_spawn_call(self):
        """R-PRV-8, R-PRV-25 — starting a child is not the child finishing its work."""
        held = object.__new__(codex.Codex)
        held.thread = "parent-thread"
        held.turn = "parent-turn"
        held.finished = threading.Event()
        held.ok = None
        held.why = None
        held.tokens = None
        held._tools = {}
        held._helpers = {}
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            held._ended({
                "type": "subAgentActivity", "kind": "started",
                "id": "activity-1", "agentThreadId": "child-thread",
                "agentPath": "/root/senior_code_reviewer",
            })
            held._began({
                "type": "collabAgentToolCall", "tool": "spawnAgent",
                "status": "inProgress", "id": "spawn-1",
            })
            held._ended({
                "type": "collabAgentToolCall", "tool": "spawnAgent",
                "status": "completed", "id": "spawn-1",
            })
            before_child = [json.loads(line) for line in output.getvalue().splitlines()]
            held._heard("turn/completed", {
                "threadId": "child-thread",
                "turn": {"id": "child-turn", "status": "completed"},
            })
        records = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual([{
            "type": "tool", "id": "subagent:child-thread",
            "name": "subAgentActivity", "did": "delegate",
            "who": "senior_code_reviewer",
        }], before_child)
        self.assertEqual({
            "type": "result", "id": "subagent:child-thread",
            "ok": True, "summary": "completed",
        }, records[-1])
        self.assertEqual(2, len(records))
        self.assertFalse(held.finished.is_set(), "the child completion ended its parent")

    def test_failed_collaboration_bookkeeping_is_not_hidden(self):
        """A helper still counts once, but a failed operation on it remains visible."""
        held = object.__new__(codex.Codex)
        held._tools = {}
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            held._ended({
                "type": "collabAgentToolCall", "tool": "wait",
                "status": "failed", "id": "wait-1",
            })
        records = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual(
            [{"type": "result", "id": "wait-1", "ok": False, "summary": "failed"}],
            records)

    def test_the_adapter_still_owns_its_cleanup(self):
        """Helper filtering may not accidentally move the turn cleanup out of Codex."""
        waited = []

        class Input:
            closed = True

        class Process:
            stdin = Input()

            def wait(self, timeout):
                waited.append(timeout)

        held = object.__new__(codex.Codex)
        held._proc = Process()
        held.end()
        self.assertEqual([10], waited)

    def test_a_child_agents_completion_does_not_end_the_parent_turn(self):
        """R-PRV-25 — child threads share the app-server stream. Their completion must
        not publish the parent's partial commentary as its final answer."""
        held = object.__new__(codex.Codex)
        held.thread = "parent-thread"
        held.turn = "parent-turn"
        held.finished = threading.Event()
        held.ok = None
        held.why = None
        held.tokens = None
        held._tools = {}
        held._helpers = {}

        held._heard("turn/completed", {
            "threadId": "child-thread",
            "turn": {"id": "child-turn", "status": "completed"},
        })
        self.assertFalse(held.finished.is_set(), "a child completion ended its parent")

        held._heard("turn/completed", {
            "threadId": "parent-thread",
            "turn": {"id": "parent-turn", "status": "completed"},
        })
        self.assertTrue(held.finished.is_set(), "the parent's own completion was ignored")


class WhereStandingInstructionsGo(unittest.TestCase):
    """R-PRV-23 — codex takes two kinds of instruction and only one of them is safe."""

    def setUp(self):
        self.was = os.environ.get("RUNDESK_PREFACE")
        self.addCleanup(self._put_back)

    def _put_back(self):
        if self.was is None:
            os.environ.pop("RUNDESK_PREFACE", None)
        else:
            os.environ["RUNDESK_PREFACE"] = self.was

    def told(self, said):
        if said is None:
            os.environ.pop("RUNDESK_PREFACE", None)
        else:
            os.environ["RUNDESK_PREFACE"] = said

    def opening(self, said, **how):
        self.told(said)
        return codex._opening(how.get("where", "/tmp"), how.get("posture", codex.SANDBOX["work"]),
                              how.get("model"), how.get("extra") or {})

    def test_standing_instructions_are_given_as_developer_instructions(self):
        """Probed against a real codex: given here it obeyed them *and* its shell tool
        still worked. That second half is the test — an instruction that arrives by
        breaking the brain is not an instruction that arrived."""
        self.assertEqual("You are in a room. Others read this.",
                         self.opening("You are in a room. Others read this.")
                         ["developerInstructions"])

    def test_what_codex_was_built_with_is_never_replaced(self):
        """`baseInstructions` sits next to the safe one and 'base' means base: what goes
        there stands in place of the instructions codex was built with, including the ones
        telling it how to use its own tools. Nothing reports it — the turn merely behaves
        strangely and the model gets the blame."""
        self.assertNotIn("baseInstructions", self.opening("You are in a room."))
        self.assertNotIn("baseInstructions", self.opening(None))
        # Named in a comment saying why not to, which is the point of the comment. What
        # must not exist anywhere is a line that *sets* it.
        setting = re.findall(r"^[^#\n]*baseInstructions[^\n]*=",
                             AT.read_text(encoding="utf-8"), re.M)
        self.assertEqual([], setting, "something in this adapter sets baseInstructions")

    def test_a_turn_with_nothing_standing_says_nothing(self):
        """An argument meaning nothing is one a brain may do something odd with, which is
        the rule the whole seam follows."""
        self.assertNotIn("developerInstructions", self.opening(None))
        self.assertNotIn("developerInstructions", self.opening("   \n  "))

    def test_the_rest_of_the_opening_is_unchanged_by_it(self):
        """Standing instructions are one more thing said while opening a conversation, not
        a different way of opening one."""
        got = self.opening("You are in a room.", model="a-model", extra={"config": {"a": 1}})
        self.assertEqual("/tmp", got["cwd"])
        self.assertEqual("a-model", got["model"])
        self.assertEqual({"a": 1}, got["config"])
        self.assertEqual({codex.SANDBOX["work"]: {}}, got["sandbox"])


class WhichConversationIsToldAndWhichIsNot(unittest.TestCase):
    """R-PRV-23 — a conversation keeps the wording it was opened with."""

    def opening(self):
        return {"cwd": "/tmp", "sandbox": {codex.SANDBOX["work"]: {}},
                "developerInstructions": "You are in a room."}

    def test_a_new_conversation_is_told_when_it_is_opened(self):
        """The one place codex reads them."""
        fake = Asked()
        codex._opened(fake, self.opening(), None)
        self.assertEqual("You are in a room.",
                         fake.sent("thread/start")["developerInstructions"])

    def test_a_conversation_being_carried_on_is_not_told_again(self):
        """Probed: passed to a resume they are accepted and then ignored. An argument that
        is quietly dropped is worse than one that was never sent, because it reads like it
        works — and an owner rewording an instruction would watch nothing happen with
        nothing to say why."""
        fake = Asked()
        codex._opened(fake, self.opening(), "an-old-thread")
        resumed = fake.sent("thread/resume")
        self.assertNotIn("developerInstructions", resumed)
        self.assertEqual("an-old-thread", resumed["threadId"])
        self.assertEqual("/tmp", resumed["cwd"], "the rest of the opening was lost with it")
        self.assertIsNone(fake.sent("thread/start"), "it opened a second conversation")

    def test_a_conversation_that_is_gone_is_opened_anew_and_told_then(self):
        """Losing a handle costs this turn its context, which is what losing a handle is
        supposed to cost. What it must not cost is the instructions — the new conversation
        is a new conversation, and is told like one."""
        fake = Asked(resume_works=False)
        codex._opened(fake, self.opening(), "a-thread-that-is-gone")
        self.assertEqual("You are in a room.",
                         fake.sent("thread/start")["developerInstructions"])


class HowMuchOfTheMachineATurnMayTouch(unittest.TestCase):
    """R-PRV-18 — rundesk says `read` or `work`, and what those mean here is this file's."""

    def test_working_means_the_agent_may_do_the_work(self):
        """It was `workspace-write`, an operating-system sandbox: no network from the shell,
        no keychain, and no writing outside the workspace. That made this brain the odd one
        of the three — `claude` and `grok` apply no sandbox at all and their `work` already
        grants a shell, an editor and a writer — so one word meant two very different things
        depending on which brain answered. It also overrode an owner who had set full access
        in their own Codex configuration, silently and on every turn."""
        self.assertEqual("danger-full-access", codex.SANDBOX["work"])

    def test_reading_is_still_the_constrained_one(self):
        """The guard on the one above. Widening `work` is only defensible while the posture
        that exists to be narrow stays narrow — otherwise there is no way left to ask for a
        turn that cannot change anything."""
        self.assertEqual("read-only", codex.SANDBOX["read"])

    def test_what_rundesk_can_say_is_what_this_brain_answers_for(self):
        """A posture the seam offers and this adapter has no answer for would fall through
        to a default and be honoured as something else entirely, which is the one failure a
        mapping like this can have."""
        self.assertEqual(sorted(provider.POSTURES), sorted(codex.SANDBOX))

    def test_the_sandbox_is_named_the_way_the_wire_accepts_it(self):
        """Measured rather than guessed: the schema calls this idea three things and only
        one is what `thread/start` takes — externally tagged and kebab-case, never
        `{"mode": …}` and never a bare string. Guessing a Codex field name has already cost
        this repository a whole feature, silently."""
        got = codex._opening("/tmp", codex.SANDBOX["work"], None, {})
        self.assertEqual({"danger-full-access": {}}, got["sandbox"])
        for named in codex.SANDBOX.values():
            self.assertRegex(named, r"^[a-z]+(-[a-z]+)*$")


if __name__ == "__main__":
    unittest.main(verbosity=2)
