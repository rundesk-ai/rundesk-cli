#!/usr/bin/env python3
"""One isolated specialist execution: what it is admitted with, and what it owes after.

Answers for the execution half of `agent-role` (R-ROL-n). Nothing here starts a
provider or reaches the network: the turn is an argument, so what a role run is *told*
and *given* is asserted without a brain anywhere near it.

Run: python3 tests/test_role_run.py
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from rundesk import agent, config, instructions, role, store, turn  # noqa: E402
from rundesk import role_run as role_runs  # noqa: E402

RULES = "# Development\n\nDo the bounded task and report exactly what you verified.\n"
BRIEF = "Outcome: make the export work.\nAuthorization: edit and test, never publish.\n"
AT = "2026-08-01T09:00:00Z"


def a_skill(at: Path, name: str) -> Path:
    made = at / name
    made.mkdir(parents=True)
    (made / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: when to use it\n---\n\n# {name}\n",
        encoding="utf-8")
    return made


class Carried:
    """The turn, as a stand-in — it records what it was handed and answers well.

    The whole point of taking the turn as an argument: what a role execution is told,
    where it stands and what it is presented are asserted here, offline, with no brain.
    """

    def __init__(self, ok: bool = True, said: str = "I changed two files and ran the tests."):
        self.given: dict = {}
        self._ok = ok
        self._said = said

    async def __call__(self, name, prompt, named, **given):
        self.given = {"name": name, "prompt": prompt, "provider": named, **given}
        return turn.Outcome(
            run="7-abcd", ok=self._ok,
            reason="finished" if self._ok else "failed",
            said=[{"type": "text", "text": self._said, "whole": True}],
            tokens={"reported": True, "input": 10, "output": 5},
            handle="session-1",
            why=None if self._ok else "it could not be done",
        )


class WithAnAgentThatCanDelegate(unittest.TestCase):
    """An agent, a role it may reach for, and a turn of its own to delegate from."""

    def setUp(self):
        self.where = Path(tempfile.mkdtemp(prefix="rundesk-agents-"))
        self.addCleanup(shutil.rmtree, self.where, True)
        self.before = Path(tempfile.mkdtemp(prefix="rundesk-before-"))
        self.addCleanup(shutil.rmtree, self.before, True)
        for said, at in (("RUNDESK_DATA_DIR", self.before / "data"),
                         ("RUNDESK_AGENTS_DIR", self.where),
                         ("RUNDESK_RUN_DIR", self.before / "run"),
                         ("RUNDESK_LOG_DIR", self.before / "logs"),
                         ("RUNDESK_JOBS_DIR", self.before / "jobs")):
            self.addCleanup(os.environ.pop, said, None)
            os.environ[said] = str(at)
            at.mkdir(parents=True, exist_ok=True)
        config.ensure(self.before / "data")
        self.library_at = Path(tempfile.mkdtemp(prefix="rundesk-skills-"))
        self.addCleanup(shutil.rmtree, self.library_at, True)
        self.library = {"writing-plans": a_skill(self.library_at, "writing-plans")}
        # Resolved, because macOS reaches its temporary directory through a link and a
        # run records where it actually stood.
        self.target = Path(tempfile.mkdtemp(prefix="rundesk-project-")).resolve()
        self.addCleanup(shutil.rmtree, self.target, True)
        (self.target / "AGENTS.md").write_text("# The project's own rules\n",
                                               encoding="utf-8")
        agent.add("elena", self.where)
        agent.remember("elena", self.where, provider="codex")
        self.wrote()
        self.kept = agent.records("elena", self.where)
        # A surface this agent is actually reachable on. A role run reports back by
        # waking the agent where the request arrived, so admission refuses a turn that
        # happened somewhere nothing can answer into (R-ROL-15).
        self.kept.remember_channel("discord", "discord", ["2207"], AT)
        self.parent = self.a_turn()

    def wrote(self, slug: str = "development", rules: str = RULES, **manifest) -> Path:
        said = {"description": "Implement and verify a bounded change.",
                "skills": ["writing-plans"], "posture": "work"}
        said.update(manifest)
        at = role.home(self.where) / slug
        at.mkdir(parents=True, exist_ok=True)
        (at / role.MANIFEST).write_text(json.dumps(said), encoding="utf-8")
        (at / role.INSTRUCTIONS).write_text(rules, encoding="utf-8")
        return at

    def a_turn(self, source: str = "channel") -> str:
        """One ordinary turn of this agent's, in a conversation somebody is in."""
        where_it_is = store.conversation_id("discord", "general")
        self.kept.opened(where_it_is, "discord", "discord", "general", AT)
        return self.kept.began(source, "codex", "work", AT, conversation_id=where_it_is)

    def admit(self, **given):
        said = {"target": str(self.target), "where": self.where, "library": self.library}
        said.update(given)
        return role_runs.admit("elena", "development", BRIEF, self.parent, **said)

    def carried(self, admitted, **given):
        carry = Carried(**given)
        outcome = asyncio.run(role_runs.carry(
            "elena", admitted.id, where=self.where, carrying=carry))
        return carry, outcome


class WhatARunIsAdmittedWith(WithAnAgentThatCanDelegate):
    """R-ROL-4, R-ROL-10 — settled once, sealed on disk, and never changed after."""

    def test_admitting_locks_the_rules_the_manifest_the_brief_and_every_skill(self):
        admitted = self.admit()
        at = role_runs.paths("elena", admitted.id, self.where)
        self.assertEqual(RULES, at["rules"].read_text(encoding="utf-8"))
        self.assertEqual(BRIEF, at["brief"].read_text(encoding="utf-8"))
        self.assertEqual(
            {"description": "Implement and verify a bounded change.",
             "skills": ["writing-plans"], "posture": "work"},
            json.loads(at["manifest"].read_text(encoding="utf-8")))
        self.assertTrue((at["skills"] / "writing-plans" / "SKILL.md").is_file())
        self.assertTrue(at["workspace"].is_dir())

    def test_a_run_is_admitted_by_a_turn_belonging_to_the_agent_it_acts_for(self):
        with self.assertRaises(role_runs.NotDelegable) as refused:
            self.admit(parent_run="404-zzzz") if False else role_runs.admit(
                "elena", "development", BRIEF, "404-zzzz",
                target=str(self.target), where=self.where, library=self.library)
        self.assertIn("not a run of this agent", str(refused.exception))

    def test_what_the_records_say_a_run_was_admitted_with_matches_its_bundle(self):
        admitted = self.admit()
        row = self.kept.role_run(admitted.id)
        self.assertEqual("development", row["role"])
        self.assertEqual(["writing-plans"], row["skills"])
        self.assertEqual(str(self.target), row["target"])
        self.assertEqual(self.parent, row["parent_run"])
        self.assertEqual(store.ADMITTED, row["state"])
        self.assertEqual(admitted.revision, row["revision"])

    def test_a_brief_longer_than_the_ceiling_is_refused(self):
        with self.assertRaises(role_runs.NotDelegable) as refused:
            role_runs.admit("elena", "development", "x" * (role.BRIEF_LIMIT + 1),
                               self.parent, where=self.where, library=self.library)
        self.assertIn("bounded task", str(refused.exception))

    def test_a_run_with_no_brief_at_all_is_refused(self):
        with self.assertRaises(role_runs.NotDelegable):
            role_runs.admit("elena", "development", "  \n ", self.parent,
                               where=self.where, library=self.library)

    def test_a_target_that_is_not_a_directory_here_is_refused(self):
        with self.assertRaises(role_runs.NotDelegable) as refused:
            self.admit(target=str(self.target / "nowhere"))
        self.assertIn("no directory", str(refused.exception))

    def test_a_target_that_is_not_an_absolute_path_is_refused(self):
        with self.assertRaises(role_runs.NotDelegable):
            self.admit(target="../somewhere")

    def test_an_unusable_role_is_refused_before_anything_is_written(self):
        self.wrote(skills=["reading-minds"])
        with self.assertRaises(role_runs.NotDelegable):
            self.admit()
        self.assertEqual([], self.kept.role_runs())
        self.assertFalse(role_runs.home("elena", self.where).exists())

    def test_editing_the_shared_role_afterwards_leaves_this_run_alone(self):
        admitted = self.admit()
        self.wrote(rules="# Different\n\nDo something else entirely.\n")
        at = role_runs.paths("elena", admitted.id, self.where)
        self.assertEqual(RULES, at["rules"].read_text(encoding="utf-8"))
        row = self.kept.role_run(admitted.id)
        self.assertEqual(RULES, role_runs.verified("elena", row, self.where)["rules"])


class OneRoleLevelAndNoMore(WithAnAgentThatCanDelegate):
    """R-ROL-13 — a worker cannot delegate, and neither can the turn reviewing one."""

    def test_a_role_run_cannot_admit_another_role_run(self):
        admitted = self.admit()
        # The execution's own turn, in the conversation of its own that carrying one opens.
        where_it_is = store.conversation_id(turn.ROLE, admitted.id)
        self.kept.opened(where_it_is, turn.ROLE, turn.ROLE, admitted.id, AT)
        inside = self.kept.began("role", "codex", "work", AT,
                                 conversation_id=where_it_is, role_run=admitted.id)
        with self.assertRaises(role_runs.NotDelegable) as refused:
            role_runs.admit("elena", "development", BRIEF, inside,
                               where=self.where, library=self.library)
        self.assertIn("one level deep", str(refused.exception))

    def test_a_turn_woken_to_review_a_handoff_cannot_start_another_role_run(self):
        admitted = self.admit()
        self.carried(admitted)
        reviewing = self.a_turn()
        self.kept.role_reviewing(admitted.id, reviewing)
        with self.assertRaises(role_runs.NotDelegable) as refused:
            role_runs.admit("elena", "development", BRIEF, reviewing,
                               where=self.where, library=self.library)
        self.assertIn("review", str(refused.exception))

    def test_the_recursion_marker_is_told_to_the_brain_as_well_as_recorded(self):
        admitted = self.admit()
        carry, _ = self.carried(admitted)
        self.assertEqual(admitted.id, carry.given["context"].role_run)


class WhatARoleExecutionIsToldAndGiven(WithAnAgentThatCanDelegate):
    """R-ROL-5, R-ROL-6, R-ROL-7, R-ROL-8 — the floor, the brief, the place, the skills."""

    def test_the_execution_stands_in_the_target_project(self):
        admitted = self.admit()
        carry, _ = self.carried(admitted)
        self.assertEqual(self.target.resolve(), carry.given["context"].cwd)

    def test_a_run_with_no_project_stands_in_its_own_locked_home(self):
        admitted = self.admit(target=None)
        carry, _ = self.carried(admitted)
        at = role_runs.paths("elena", admitted.id, self.where)
        self.assertEqual(at["home"], carry.given["context"].cwd)

    def test_the_execution_is_presented_the_runs_own_locked_skill_snapshot(self):
        admitted = self.admit()
        carry, _ = self.carried(admitted)
        at = role_runs.paths("elena", admitted.id, self.where)
        self.assertEqual(at["skills"], carry.given["context"].skills)
        self.assertNotEqual(agent.skills("elena", self.where),
                            carry.given["context"].skills)

    def test_the_brief_is_the_prompt_and_the_conversation_is_never_forwarded(self):
        admitted = self.admit()
        carry, _ = self.carried(admitted)
        self.assertEqual(BRIEF, carry.given["prompt"])

    def test_the_preface_carries_the_floor_then_the_role_rules_then_the_task(self):
        admitted = self.admit()
        carry, _ = self.carried(admitted)
        told = carry.given["preface"]
        self.assertLess(told.index("You are working as"), told.index("# Development"))
        self.assertLess(told.index("# Development"), told.index("## This execution"))
        self.assertIn(RULES.strip(), told)
        self.assertIn(admitted.id, told)

    def test_the_role_rules_reach_the_brain_exactly_as_they_were_locked(self):
        self.wrote(rules="# Development\n\nUse {agent_home} literally, braces and all.\n")
        admitted = self.admit()
        carry, _ = self.carried(admitted)
        self.assertIn("Use {agent_home} literally, braces and all.",
                      carry.given["preface"])

    def test_no_named_agent_identity_memory_or_operating_rules_reach_the_worker(self):
        admitted = self.admit()
        carry, _ = self.carried(admitted)
        told = carry.given["preface"]
        for absent in ("Rundesk agent operating rules", "MEMORY.md", "SOUL.md",
                       "rundesk schedules", "managing-rundesk",
                       str(agent.home("elena", self.where))):
            self.assertNotIn(absent, told, absent)

    def test_the_floor_says_whose_behalf_this_is_on_and_refuses_impersonation(self):
        admitted = self.admit()
        carry, _ = self.carried(admitted)
        told = carry.given["preface"]
        self.assertIn("on behalf of the named agent elena", told)
        self.assertIn("Never speak as the person who asked", told)
        self.assertIn("Starting another Rundesk role run is refused", told)

    def test_the_execution_runs_under_the_roles_own_posture(self):
        self.wrote(posture="read")
        admitted = self.admit()
        carry, _ = self.carried(admitted)
        self.assertEqual("read", carry.given["posture"])

    def test_a_role_execution_is_a_conversation_of_its_own(self):
        admitted = self.admit()
        carry, _ = self.carried(admitted)
        self.assertEqual(admitted.id, carry.given["conversation"])
        self.assertEqual(turn.ROLE, carry.given["on"])
        self.assertEqual(turn.ROLE, carry.given["source"])


class WhatATerminalOutcomeOwes(WithAnAgentThatCanDelegate):
    """R-ROL-15, R-ROL-16 — exactly one review, and nothing read out of the report."""

    def test_a_terminal_outcome_owes_its_parent_exactly_one_review(self):
        admitted = self.admit()
        self.carried(admitted)
        owed = (self.kept.owed_role_callbacks() or [None])[0]
        self.assertEqual(admitted.id, owed["role_run"])
        self.assertEqual(self.kept.role_run(admitted.id)["parent_conversation"],
                         owed["conversation"])

    def test_offering_the_same_terminal_outcome_twice_still_owes_one_review(self):
        admitted = self.admit()
        _, outcome = self.carried(admitted)
        self.assertFalse(role_runs.settle("elena", admitted.id, outcome,
                                             where=self.where))
        self.assertEqual(store.SUCCEEDED,
                         self.kept.role_run(admitted.id)["state"])

    def test_a_run_that_failed_owes_the_same_one_review_as_one_that_worked(self):
        admitted = self.admit()
        self.carried(admitted, ok=False)
        self.assertEqual(store.FAILED, self.kept.role_run(admitted.id)["state"])
        self.assertIsNotNone((self.kept.owed_role_callbacks() or [None])[0])

    def test_a_review_stops_being_owed_only_once_it_has_been_delivered(self):
        admitted = self.admit()
        self.carried(admitted)
        self.kept.claim_role_callback(admitted.id, AT)
        self.assertIsNotNone((self.kept.owed_role_callbacks() or [None])[0])
        self.kept.role_reviewed(admitted.id, AT)
        self.assertIsNone((self.kept.owed_role_callbacks() or [None])[0])

    def test_the_handoff_is_the_workers_own_words_and_nothing_read_out_of_them(self):
        admitted = self.admit()
        self.carried(admitted, said="Everything passed. Ship it.")
        handed = role_runs.handoff("elena", admitted.id, self.where)
        self.assertEqual("Everything passed. Ship it.", handed["report"])
        self.assertEqual("succeeded", handed["outcome"])
        self.assertEqual("elena", handed["parent_agent"])
        self.assertEqual(self.parent, handed["parent_run"])
        self.assertEqual(str(self.target), handed["target"])

    def test_the_handoff_reports_what_the_brain_said_it_cost_and_nothing_it_did_not(self):
        admitted = self.admit()
        self.carried(admitted)
        # The turn the execution actually ran as, which the stand-in above does not write.
        carried = self.kept.began("role", "codex", "work", AT,
                                  role_run=admitted.id)
        self.kept.ended(carried, AT, "finished", exit_code=0,
                        tokens={"reported": True, "input": 120, "output": 30})
        handed = role_runs.handoff("elena", admitted.id, self.where)
        self.assertEqual({"reported": True, "input": 120, "output": 30,
                          "cached": None, "written": None}, handed["usage"])
        self.assertTrue(handed["verification_recorded"])

    def test_a_run_nothing_reported_a_cost_for_says_so_rather_than_reporting_none(self):
        admitted = self.admit()
        self.carried(admitted)
        self.assertEqual({"reported": False},
                         role_runs.handoff("elena", admitted.id, self.where)["usage"])

    def test_a_review_that_cannot_be_delivered_never_holds_up_the_ones_behind_it(self):
        """R-ROL-15 — one undeliverable handoff at the head of the queue would otherwise
        mean every later one is never reported and nothing says why."""
        first = self.admit()
        self.carried(first)
        second = self.admit()
        self.carried(second)
        owed = [one["role_run"] for one in self.kept.owed_role_callbacks()]
        self.assertEqual([first.id, second.id], owed)

    def test_a_run_finished_by_hand_is_still_the_run_the_records_describe(self):
        admitted = self.admit()
        self.carried(admitted)
        self.assertEqual(admitted.id,
                         role_runs.handoff("elena", admitted.id, self.where)["role_run"])


class HowLongARunStaysResumable(WithAnAgentThatCanDelegate):
    """R-ROL-11, R-ROL-12 — a window from the latest activity, and what expiry leaves."""

    def test_the_retention_window_is_measured_from_the_latest_activity(self):
        admitted = self.admit()
        row = self.kept.role_run(admitted.id)
        began = store.moment(row["admitted_at"])
        until = store.moment(row["retained_until"])
        self.assertEqual(role_runs.RETAINED_DAYS, (until - began).days)
        self.kept.role_active(admitted.id, "2026-08-05T09:00:00Z",
                                 "2026-08-19T09:00:00Z")
        self.assertEqual("2026-08-19T09:00:00Z",
                         self.kept.role_run(admitted.id)["retained_until"])

    def test_a_run_inside_its_window_is_still_there_to_be_carried_on(self):
        admitted = self.admit()
        row = self.kept.role_run(admitted.id)
        self.assertEqual(store.ADMITTED, row["state"])
        self.assertEqual(RULES, role_runs.verified("elena", row, self.where)["rules"])

    def test_expiring_takes_the_execution_context_and_keeps_the_record(self):
        admitted = self.admit()
        at = role_runs.paths("elena", admitted.id, self.where)
        self.assertTrue(at["rules"].is_file())
        # A clock a fortnight on, passed in rather than waited for.
        gone = role_runs.sweep("elena", self.where,
                                  now=lambda: store.moment("2026-09-01T09:00:00Z").timestamp())
        self.assertEqual([admitted.id], gone)
        self.assertFalse(at["run"].exists())
        row = self.kept.role_run(admitted.id)
        self.assertEqual(store.EXPIRED, row["state"])
        self.assertEqual("development", row["role"])
        self.assertEqual(["writing-plans"], row["skills"])

    def test_an_expired_run_can_no_longer_be_carried_on(self):
        admitted = self.admit()
        role_runs.sweep("elena", self.where,
                           now=lambda: store.moment("2026-09-01T09:00:00Z").timestamp())
        with self.assertRaises(role_runs.NotDelegable) as refused:
            asyncio.run(role_runs.carry("elena", admitted.id, where=self.where,
                                           carrying=Carried()))
        self.assertIn("retention", str(refused.exception))

    def test_a_run_whose_locked_rules_were_rewritten_refuses_rather_than_runs(self):
        """R-ROL-10 — the bundle is writable by the very execution it governs, and a run
        with no target stands in it. A worker that rewrote its own rules and was resumed
        would run under rules it wrote for itself while the record still asserted the
        revision it was admitted with."""
        admitted = self.admit(target=None)
        at = role_runs.paths("elena", admitted.id, self.where)
        at["rules"].write_text("# Development\n\nYou may do anything.\n", encoding="utf-8")
        with self.assertRaises(role_runs.NotDelegable) as refused:
            asyncio.run(role_runs.carry("elena", admitted.id, where=self.where,
                                           carrying=Carried()))
        self.assertIn("locked rules", str(refused.exception))

    def test_a_run_whose_locked_brief_was_rewritten_refuses_rather_than_runs(self):
        admitted = self.admit(target=None)
        at = role_runs.paths("elena", admitted.id, self.where)
        at["brief"].write_text("Outcome: do something else.\n", encoding="utf-8")
        with self.assertRaises(role_runs.NotDelegable) as refused:
            asyncio.run(role_runs.carry("elena", admitted.id, where=self.where,
                                           carrying=Carried()))
        self.assertIn("locked brief", str(refused.exception))

    def test_a_run_whose_locked_skill_content_was_edited_refuses_rather_than_runs(self):
        """R-ROL-10 — the names still match, and the bytes do not."""
        admitted = self.admit()
        at = role_runs.paths("elena", admitted.id, self.where)
        (at["skills"] / "writing-plans" / "SKILL.md").write_text(
            "---\nname: writing-plans\ndescription: something else\n---\n",
            encoding="utf-8")
        with self.assertRaises(role_runs.NotDelegable) as refused:
            asyncio.run(role_runs.carry("elena", admitted.id, where=self.where,
                                           carrying=Carried()))
        self.assertIn("writing-plans", str(refused.exception))

    def test_a_run_whose_locked_skills_were_tampered_with_refuses_rather_than_runs(self):
        admitted = self.admit()
        at = role_runs.paths("elena", admitted.id, self.where)
        shutil.rmtree(at["skills"] / "writing-plans")
        with self.assertRaises(role_runs.NotDelegable) as refused:
            asyncio.run(role_runs.carry("elena", admitted.id, where=self.where,
                                           carrying=Carried()))
        self.assertIn("locked skill snapshot", str(refused.exception))

    def test_a_run_that_already_finished_is_not_carried_again(self):
        admitted = self.admit()
        self.carried(admitted)
        with self.assertRaises(role_runs.NotDelegable):
            asyncio.run(role_runs.carry("elena", admitted.id, where=self.where,
                                           carrying=Carried()))


class WhoMayHandWorkOn(WithAnAgentThatCanDelegate):
    """R-ROL-4, R-ROL-15 — which turns may delegate, checked where the run is admitted."""

    def test_a_turn_that_has_already_ended_is_not_a_turn_that_can_delegate(self):
        self.kept.ended(self.parent, AT, "finished", exit_code=0)
        with self.assertRaises(role_runs.NotDelegable) as refused:
            self.admit()
        self.assertIn("already ended", str(refused.exception))

    def test_a_turn_on_no_surface_the_agent_is_reachable_on_cannot_delegate(self):
        """The review is delivered by waking the agent where the request arrived. A turn
        from a terminal has no such surface, and a run admitted from one would be owed a
        review for ever with nobody ever told."""
        where_it_is = store.conversation_id("terminal", "terminal")
        self.kept.opened(where_it_is, "terminal", "terminal", "terminal", AT)
        typed = self.kept.began("terminal", "codex", "work", AT,
                                conversation_id=where_it_is)
        with self.assertRaises(role_runs.NotDelegable) as refused:
            role_runs.admit("elena", "development", BRIEF, typed,
                               where=self.where, library=self.library)
        self.assertIn("nowhere to report the work back to", str(refused.exception))
        self.assertEqual([], self.kept.role_runs())

    def test_a_role_run_cannot_work_inside_the_agents_own_home(self):
        """R-ROL-5 — standing there would hand the worker that agent's rules, memory and
        identity by the ordinary mechanism, with nothing in the preface to show for it."""
        for inside in (agent.home("elena", self.where),
                       agent.workspace("elena", self.where)):
            with self.assertRaises(role_runs.NotDelegable, msg=str(inside)) as refused:
                self.admit(target=str(inside))
            self.assertIn("agent's own home", str(refused.exception))

    def test_a_role_never_widens_the_authority_its_parent_turn_had(self):
        """A role asking to change the machine, from a turn that was only allowed to
        read it, is asking for authority nobody granted."""
        where_it_is = store.conversation_id("discord", "general")
        looking = self.kept.began("channel", "codex", "read", AT,
                                  conversation_id=where_it_is)
        admitted = role_runs.admit("elena", "development", BRIEF, looking,
                                      target=str(self.target), where=self.where,
                                      library=self.library)
        self.assertEqual("read", admitted.posture)
        self.assertEqual("read", self.kept.role_run(admitted.id)["posture"])
        carry, _ = self.carried(admitted)
        self.assertEqual("read", carry.given["posture"])

    def test_a_role_may_still_narrow_what_its_parent_turn_could_do(self):
        self.wrote(posture="read")
        admitted = self.admit()
        self.assertEqual("read", admitted.posture)


class WhenCarryingGoesWrong(WithAnAgentThatCanDelegate):
    """R-ROL-15 — every way an execution can fail ends it truthfully, and tells its parent.

    Driven through `agent.playing`, which is the boundary a gateway actually calls: a
    root left unsettled is one picked up again on every look for ever while nobody is ever
    told, and that is the failure this covers rather than any particular exception.
    """

    def carrying(self, raises):
        async def went_wrong(*_said, **_given):
            raise raises
        return agent.playing("elena", self.where, carry=went_wrong)

    def test_a_brain_that_is_no_longer_there_ends_the_run_and_owes_a_review(self):
        """A role run carries on with the brain its parent turn resolved. One that has
        since been removed from the machine raises before anything is started — and the
        run must not be left `working` for a gateway to pick up again for ever."""
        where_it_is = store.conversation_id("discord", "general")
        gone = self.kept.began("channel", str(self.where / "no-such-brain"), "work", AT,
                               conversation_id=where_it_is)
        admitted = role_runs.admit("elena", "development", BRIEF, gone,
                                      target=str(self.target), where=self.where,
                                      library=self.library)
        # The real turn, deliberately: it raises `NotRunnable` before it starts anything,
        # so this reaches no provider and no network.
        asyncio.run(agent.playing("elena", self.where).carry(admitted.id))
        row = self.kept.role_run(admitted.id)
        self.assertEqual(store.FAILED, row["state"])
        self.assertIn("no-such-brain", row["report"])
        self.assertEqual([admitted.id],
                         [one["role_run"] for one in self.kept.owed_role_callbacks()])

    def test_anything_else_that_goes_wrong_ends_the_run_and_owes_a_review(self):
        admitted = self.admit()
        asyncio.run(self.carrying(FileNotFoundError("that directory has moved"))
                    .carry(admitted.id))
        row = self.kept.role_run(admitted.id)
        self.assertEqual(store.FAILED, row["state"])
        self.assertIn("moved", row["report"])
        self.assertIsNotNone(self.kept.owed_role_callbacks())

    def test_a_run_a_gateway_was_cancelled_out_of_is_left_to_be_carried_on(self):
        """A gateway standing down is the ordinary way this happens, and the run's
        provider session is the conversation's — so the next gateway carries it on."""
        admitted = self.admit()
        with self.assertRaises(asyncio.CancelledError):
            asyncio.run(self.carrying(asyncio.CancelledError()).carry(admitted.id))
        self.assertEqual(store.WORKING, self.kept.role_run(admitted.id)["state"])
        self.assertEqual([], self.kept.owed_role_callbacks())
        self.assertEqual([admitted.id],
                         [one["id"] for one in agent.playing("elena", self.where).waiting()])

    def test_a_failed_run_is_not_carried_again_on_the_next_look(self):
        admitted = self.admit()
        asyncio.run(self.carrying(RuntimeError("no")).carry(admitted.id))
        self.assertEqual([], agent.playing("elena", self.where).waiting())


class WhatARunLeavesInTheTargetProject(WithAnAgentThatCanDelegate):
    """R-ROL-22 — a worker stands in somebody's repository and leaves it as it found it.

    Every adapter measured presents skills beside the directory it stands in, so a run that
    simply ended left a vendor directory in that checkout holding links into a bundle that
    is swept after a fortnight — dangling ones, in a repository the worker was told not to
    disturb.
    """

    def presented(self, admitted, at=".agents/skills"):
        """What an adapter does on its way in, as the shipped adapters actually do it."""
        skills = role_runs.paths("elena", admitted.id, self.where)["skills"]
        stood = self.target / at
        stood.mkdir(parents=True)
        for one in sorted(skills.iterdir()):
            (stood / one.name).symlink_to(one)
        return stood

    def test_what_an_adapter_stood_in_the_target_is_taken_back_when_the_run_ends(self):
        admitted = self.admit()
        stood = self.presented(admitted)
        self.assertTrue((stood / "writing-plans").is_symlink())

        self.carried(admitted)

        self.assertFalse(stood.exists())
        self.assertFalse((self.target / ".agents").exists())
        self.assertTrue((self.target / "AGENTS.md").is_file())

    def test_taking_them_back_works_wherever_a_brain_put_them(self):
        """Vendor-neutral: this knows nothing about which directory any brain uses, only
        that a link resolves inside this run's own snapshot."""
        for at in (".claude/skills", ".grok/skills", ".agents/skills"):
            admitted = self.admit()
            stood = self.presented(admitted, at=at)
            self.carried(admitted)
            self.assertFalse(stood.exists(), at)
            self.assertFalse((self.target / at.split("/")[0]).exists(), at)

    def test_nothing_of_the_owners_is_taken_back_with_them(self):
        admitted = self.admit()
        stood = self.presented(admitted)
        (stood / "theirs").mkdir()
        (stood / "theirs" / "SKILL.md").write_text("---\nname: theirs\n---\n",
                                                   encoding="utf-8")
        elsewhere = self.target / ".agents" / "settings.json"
        elsewhere.write_text("{}", encoding="utf-8")

        self.carried(admitted)

        self.assertFalse((stood / "writing-plans").exists())
        self.assertTrue((stood / "theirs" / "SKILL.md").is_file())
        self.assertTrue(elsewhere.is_file())

    def test_a_link_that_points_anywhere_else_is_left_exactly_as_it_is(self):
        admitted = self.admit()
        stood = self.target / ".agents" / "skills"
        stood.mkdir(parents=True)
        somewhere = self.target / "their-own-skill"
        somewhere.mkdir()
        (stood / "their-own-skill").symlink_to(somewhere)

        self.carried(admitted)

        self.assertTrue((stood / "their-own-skill").is_symlink())

    def test_a_run_with_no_project_has_nothing_in_anybodys_checkout_to_take_back(self):
        admitted = self.admit(target=None)
        self.assertEqual([], role_runs.unpresent(
            None, role_runs.paths("elena", admitted.id, self.where)["skills"]))

    def test_an_expired_run_takes_its_links_out_of_the_project_too(self):
        """A run its gateway never got to finish still stood links in somebody's project."""
        admitted = self.admit()
        stood = self.presented(admitted)
        role_runs.sweep("elena", self.where,
                           now=lambda: store.moment("2026-09-01T09:00:00Z").timestamp())
        self.assertFalse(stood.exists())
        self.assertFalse((self.target / ".agents").exists())


class SayingSomethingToWorkInFlight(WithAnAgentThatCanDelegate):
    """R-ROL-23 — the parent guides an execution it is carrying, through the seam a turn
    already has for a word said mid-turn."""

    async def taken(self, admitted, every=0):
        """Whatever the steering source yields before it would wait for more."""
        said = []
        source = role_runs.steering("elena", admitted.id, self.where, every=every)
        try:
            for _ in range(20):
                said.append(await asyncio.wait_for(source.__anext__(), 1))
        except asyncio.TimeoutError:
            pass
        finally:
            await source.aclose()
        return [one.text for one in said]

    def test_what_the_parent_says_reaches_the_work_in_flight_in_order(self):
        admitted = self.admit()
        self.kept.role_working(admitted.id, AT, role_runs.retained_until())
        role_runs.say("elena", admitted.id, "check the header row too")
        role_runs.say("elena", admitted.id, "and quote every field")
        self.assertEqual(["check the header row too", "and quote every field"],
                         asyncio.run(self.taken(admitted)))

    def test_a_word_reaches_one_turn_and_never_a_second(self):
        admitted = self.admit()
        self.kept.role_working(admitted.id, AT, role_runs.retained_until())
        role_runs.say("elena", admitted.id, "check the header row")
        self.assertEqual(["check the header row"], asyncio.run(self.taken(admitted)))
        self.assertEqual([], asyncio.run(self.taken(admitted)))

    def test_saying_something_to_a_run_that_is_not_working_says_which_verb_was_wanted(self):
        admitted = self.admit()
        self.carried(admitted)
        with self.assertRaises(role_runs.NotDelegable) as refused:
            role_runs.say("elena", admitted.id, "one more thing")
        self.assertIn("resume it", str(refused.exception))

    def test_nothing_at_all_is_not_something_to_say(self):
        admitted = self.admit()
        self.kept.role_working(admitted.id, AT, role_runs.retained_until())
        with self.assertRaises(role_runs.NotDelegable):
            role_runs.say("elena", admitted.id, "   \n ")

    def test_a_whole_second_task_is_not_a_word_said_into_one(self):
        admitted = self.admit()
        self.kept.role_working(admitted.id, AT, role_runs.retained_until())
        with self.assertRaises(role_runs.NotDelegable) as refused:
            role_runs.say("elena", admitted.id, "x" * (role.BRIEF_LIMIT + 1))
        self.assertIn("role run of its own", str(refused.exception))

    def test_a_brain_that_cannot_be_sent_to_refuses_rather_than_queueing_unread(self):
        """R-ROL-23 — two of the four brains that ship say plainly that nothing reaches
        them after the prompt. A word taken for one of those is a word that sits unread
        while the command that took it reported success."""
        admitted = self.admit()
        where_it_is = store.conversation_id(turn.ROLE, admitted.id)
        self.kept.opened(where_it_is, turn.ROLE, turn.ROLE, admitted.id, AT)
        self.kept.began("role", "grok", "work", AT, conversation_id=where_it_is,
                        can={"steer": False}, role_run=admitted.id)
        self.kept.role_working(admitted.id, AT, role_runs.retained_until())
        with self.assertRaises(role_runs.NotDelegable) as refused:
            role_runs.say("elena", admitted.id, "also quote every field")
        self.assertIn("cannot be sent to while it works", str(refused.exception))
        self.assertEqual(0, self.kept.words_waiting(admitted.id))

    def test_a_brain_that_can_be_sent_to_takes_it(self):
        admitted = self.admit()
        where_it_is = store.conversation_id(turn.ROLE, admitted.id)
        self.kept.opened(where_it_is, turn.ROLE, turn.ROLE, admitted.id, AT)
        self.kept.began("role", "codex", "work", AT, conversation_id=where_it_is,
                        can={"steer": True}, role_run=admitted.id)
        self.kept.role_working(admitted.id, AT, role_runs.retained_until())
        role_runs.say("elena", admitted.id, "also quote every field")
        self.assertEqual(1, self.kept.words_waiting(admitted.id))

    def test_what_is_said_before_it_starts_is_part_of_what_it_is_asked(self):
        """Nothing knows yet what brain will carry it, and one that cannot be sent to
        would never read this at the steering seam. Folded into the prompt, it reaches
        every brain."""
        admitted = self.admit()
        role_runs.say("elena", admitted.id, "and quote every field")
        carry, _ = self.carried(admitted)
        self.assertTrue(carry.given["prompt"].startswith(BRIEF))
        self.assertIn("and quote every field", carry.given["prompt"])

    def test_a_run_carrying_work_is_handed_its_parents_words_by_the_turn(self):
        admitted = self.admit()
        carry, _ = self.carried(admitted)
        self.assertIsNotNone(carry.given["steering"])

    def test_what_is_waiting_to_be_said_is_something_a_listing_can_show(self):
        admitted = self.admit()
        self.kept.role_working(admitted.id, AT, role_runs.retained_until())
        role_runs.say("elena", admitted.id, "one thing")
        self.assertEqual(1, self.kept.words_waiting(admitted.id))
        self.kept.words_for_role(admitted.id, AT)
        self.assertEqual(0, self.kept.words_waiting(admitted.id))


class EndingOneBeforeItFinishes(WithAnAgentThatCanDelegate):
    """R-ROL-24 — a person asked for this to end, which is not a gateway going down."""

    def test_asking_a_running_execution_to_stop_is_recorded_for_whatever_carries_it(self):
        admitted = self.admit()
        self.kept.role_working(admitted.id, AT, role_runs.retained_until())
        self.assertTrue(role_runs.stop("elena", admitted.id))
        self.assertIsNotNone(self.kept.role_run(admitted.id)["stop_asked_at"])
        self.assertEqual([admitted.id],
                         [one["id"] for one in agent.playing("elena", self.where).stopping()])

    def test_a_run_nothing_has_started_is_settled_without_a_provider(self):
        admitted = self.admit()
        role_runs.stop("elena", admitted.id)
        agent.playing("elena", self.where).stopped(admitted.id)
        row = self.kept.role_run(admitted.id)
        self.assertEqual(store.STOPPED, row["state"])
        self.assertEqual([admitted.id],
                         [one["role_run"] for one in self.kept.owed_role_callbacks()])

    def test_a_stopped_execution_settles_as_stopped_rather_than_carried_on(self):
        """A cancellation is how both a stop and a shutdown arrive. Only one of them means
        the run should not start again on the way back up."""
        admitted = self.admit()
        role_runs.stop("elena", admitted.id)

        async def cancelled(*_said, **_given):
            raise asyncio.CancelledError()

        asyncio.run(agent.playing("elena", self.where, carry=cancelled).carry(admitted.id))
        self.assertEqual(store.STOPPED, self.kept.role_run(admitted.id)["state"])
        self.assertEqual([], agent.playing("elena", self.where).waiting())

    def test_a_gateway_standing_down_is_still_not_a_stop(self):
        admitted = self.admit()

        async def cancelled(*_said, **_given):
            raise asyncio.CancelledError()

        with self.assertRaises(asyncio.CancelledError):
            asyncio.run(agent.playing("elena", self.where, carry=cancelled).carry(admitted.id))
        self.assertEqual(store.WORKING, self.kept.role_run(admitted.id)["state"])

    def test_stopping_one_that_is_already_over_says_so_rather_than_pretending(self):
        admitted = self.admit()
        self.carried(admitted)
        self.assertFalse(role_runs.stop("elena", admitted.id))

    def test_a_stopped_run_owes_its_parent_the_same_one_review(self):
        admitted = self.admit()
        role_runs.stop("elena", admitted.id)
        agent.playing("elena", self.where).stopped(admitted.id)
        self.assertEqual(1, len(self.kept.owed_role_callbacks()))


class CarryingAFinishedOneOn(WithAnAgentThatCanDelegate):
    """R-ROL-25 — more work, in the session it already has, with its locks unchanged."""

    def test_resuming_puts_it_back_in_hand_and_asks_the_further_task(self):
        admitted = self.admit()
        self.carried(admitted)
        role_runs.resume("elena", admitted.id, "now add the header row")
        self.assertEqual(store.ADMITTED, self.kept.role_run(admitted.id)["state"])
        self.assertEqual([admitted.id],
                         [one["id"] for one in agent.playing("elena", self.where).waiting()])
        carry, _ = self.carried(admitted)
        self.assertEqual("now add the header row", carry.given["prompt"])

    def test_the_first_turn_is_asked_the_brief_and_the_next_is_asked_what_was_said(self):
        admitted = self.admit()
        first, _ = self.carried(admitted)
        self.assertEqual(BRIEF, first.given["prompt"])
        role_runs.resume("elena", admitted.id, "now add the header row")
        second, _ = self.carried(admitted)
        self.assertNotEqual(BRIEF, second.given["prompt"])

    def test_resuming_leaves_the_locked_bundle_exactly_as_it_was(self):
        admitted = self.admit()
        self.carried(admitted)
        role_runs.resume("elena", admitted.id, "now add the header row")
        at = role_runs.paths("elena", admitted.id, self.where)
        self.assertEqual(BRIEF, at["brief"].read_text(encoding="utf-8"))
        self.assertEqual(RULES, at["rules"].read_text(encoding="utf-8"))
        row = self.kept.role_run(admitted.id)
        self.assertEqual(RULES, role_runs.verified("elena", row, self.where)["rules"])

    def test_being_asked_for_again_starts_the_retention_window_again(self):
        admitted = self.admit()
        self.carried(admitted)
        was = self.kept.role_run(admitted.id)["retained_until"]
        role_runs.resume("elena", admitted.id, "more", now=lambda: 1785700000.0)
        self.assertNotEqual(was, self.kept.role_run(admitted.id)["retained_until"])

    def test_resuming_one_that_is_still_running_says_which_verb_was_wanted(self):
        admitted = self.admit()
        self.kept.role_working(admitted.id, AT, role_runs.retained_until())
        with self.assertRaises(role_runs.NotDelegable) as refused:
            role_runs.resume("elena", admitted.id, "more")
        self.assertIn("say it", str(refused.exception))

    def test_an_expired_run_refuses_all_three(self):
        admitted = self.admit()
        role_runs.sweep("elena", self.where,
                        now=lambda: store.moment("2026-09-01T09:00:00Z").timestamp())
        for doing in (lambda: role_runs.say("elena", admitted.id, "more"),
                      lambda: role_runs.stop("elena", admitted.id),
                      lambda: role_runs.resume("elena", admitted.id, "more")):
            with self.assertRaises(role_runs.NotDelegable) as refused:
                doing()
            self.assertIn("retention", str(refused.exception))

    def test_a_resumed_run_that_finishes_owes_its_parent_another_review(self):
        admitted = self.admit()
        self.carried(admitted)
        self.kept.role_reviewed(admitted.id, AT)
        self.assertEqual([], self.kept.owed_role_callbacks())
        role_runs.resume("elena", admitted.id, "now add the header row")
        self.carried(admitted)
        self.assertEqual([admitted.id],
                         [one["role_run"] for one in self.kept.owed_role_callbacks()])


class WhatAPersonIsShown(WithAnAgentThatCanDelegate):
    """R-ROL-17 — an owner's private paths stay in the records."""

    def test_what_a_role_run_shows_carries_no_local_path(self):
        admitted = self.admit()
        shown = role_runs.shown(self.kept.role_run(admitted.id))
        self.assertEqual(self.target.name, shown["target"])
        self.assertNotIn(str(self.target.parent), json.dumps(shown))

    def test_a_label_is_short_safe_and_never_the_brief(self):
        self.assertEqual("Applicant export",
                         role_runs.safe_label("Applicant export", "Development"))
        self.assertEqual("Development", role_runs.safe_label("", "Development"))
        self.assertNotIn("`", role_runs.safe_label("`rm -rf /`", "Development"))
        self.assertLessEqual(len(role_runs.safe_label("x " * 200, "Development")), 60)

    def test_a_listing_says_whether_a_review_is_still_owed_and_how_often_it_was_tried(self):
        admitted = self.admit()
        self.assertEqual({"owed": False, "attempts": 0},
                         role_runs.owed_review("elena", admitted.id, self.where))
        self.carried(admitted)
        self.kept.claim_role_callback(admitted.id, AT)
        self.assertEqual({"owed": True, "attempts": 1},
                         role_runs.owed_review("elena", admitted.id, self.where))
        self.kept.role_reviewed(admitted.id, AT)
        self.assertEqual({"owed": False, "attempts": 0},
                         role_runs.owed_review("elena", admitted.id, self.where))

    def test_a_listing_says_which_revision_and_which_skills_a_run_used(self):
        admitted = self.admit()
        shown = role_runs.shown(self.kept.role_run(admitted.id))
        self.assertEqual(admitted.revision[:12], shown["revision"])
        self.assertEqual(["writing-plans"], shown["skills"])


if __name__ == "__main__":
    unittest.main()
