#!/usr/bin/env python3
"""One isolated specialist execution: what it is admitted with, and what it owes after.

Answers for the execution half of `agent-profile-worker` (R-PRF-n). Nothing here starts a
provider or reaches the network: the turn is an argument, so what a profile run is *told*
and *given* is asserted without a brain anywhere near it.

Run: python3 tests/test_profile_run.py
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

from rundesk import agent, config, instructions, profile, store, turn  # noqa: E402
from rundesk import profile_run as profile_runs  # noqa: E402

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

    The whole point of taking the turn as an argument: what a profile execution is told,
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
    """An agent, a profile it may reach for, and a turn of its own to delegate from."""

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
        self.parent = self.a_turn()

    def wrote(self, slug: str = "development", rules: str = RULES, **manifest) -> Path:
        said = {"description": "Implement and verify a bounded change.",
                "skills": ["writing-plans"], "posture": "work"}
        said.update(manifest)
        at = profile.home(self.where) / slug
        at.mkdir(parents=True, exist_ok=True)
        (at / profile.MANIFEST).write_text(json.dumps(said), encoding="utf-8")
        (at / profile.INSTRUCTIONS).write_text(rules, encoding="utf-8")
        return at

    def a_turn(self, source: str = "channel") -> str:
        """One ordinary turn of this agent's, in a conversation somebody is in."""
        where_it_is = store.conversation_id("discord", "general")
        self.kept.opened(where_it_is, "discord", "discord", "general", AT)
        return self.kept.began(source, "codex", "work", AT, conversation_id=where_it_is)

    def admit(self, **given):
        said = {"target": str(self.target), "where": self.where, "library": self.library}
        said.update(given)
        return profile_runs.admit("elena", "development", BRIEF, self.parent, **said)

    def carried(self, admitted, **given):
        carry = Carried(**given)
        outcome = asyncio.run(profile_runs.carry(
            "elena", admitted.id, where=self.where, carrying=carry))
        return carry, outcome


class WhatARunIsAdmittedWith(WithAnAgentThatCanDelegate):
    """R-PRF-4, R-PRF-10 — settled once, sealed on disk, and never changed after."""

    def test_admitting_locks_the_rules_the_manifest_the_brief_and_every_skill(self):
        admitted = self.admit()
        at = profile_runs.paths("elena", admitted.id, self.where)
        self.assertEqual(RULES, at["rules"].read_text(encoding="utf-8"))
        self.assertEqual(BRIEF, at["brief"].read_text(encoding="utf-8"))
        self.assertEqual(
            {"description": "Implement and verify a bounded change.",
             "skills": ["writing-plans"], "posture": "work"},
            json.loads(at["manifest"].read_text(encoding="utf-8")))
        self.assertTrue((at["skills"] / "writing-plans" / "SKILL.md").is_file())
        self.assertTrue(at["workspace"].is_dir())

    def test_a_run_is_admitted_by_a_turn_belonging_to_the_agent_it_acts_for(self):
        with self.assertRaises(profile_runs.NotDelegable) as refused:
            self.admit(parent_run="404-zzzz") if False else profile_runs.admit(
                "elena", "development", BRIEF, "404-zzzz",
                target=str(self.target), where=self.where, library=self.library)
        self.assertIn("not a run of this agent", str(refused.exception))

    def test_what_the_records_say_a_run_was_admitted_with_matches_its_bundle(self):
        admitted = self.admit()
        row = self.kept.profile_run(admitted.id)
        self.assertEqual("development", row["profile"])
        self.assertEqual(["writing-plans"], row["skills"])
        self.assertEqual(str(self.target), row["target"])
        self.assertEqual(self.parent, row["parent_run"])
        self.assertEqual(store.ADMITTED, row["state"])
        self.assertEqual(admitted.revision, row["revision"])

    def test_a_brief_longer_than_the_ceiling_is_refused(self):
        with self.assertRaises(profile_runs.NotDelegable) as refused:
            profile_runs.admit("elena", "development", "x" * (profile.BRIEF_LIMIT + 1),
                               self.parent, where=self.where, library=self.library)
        self.assertIn("bounded task", str(refused.exception))

    def test_a_run_with_no_brief_at_all_is_refused(self):
        with self.assertRaises(profile_runs.NotDelegable):
            profile_runs.admit("elena", "development", "  \n ", self.parent,
                               where=self.where, library=self.library)

    def test_a_target_that_is_not_a_directory_here_is_refused(self):
        with self.assertRaises(profile_runs.NotDelegable) as refused:
            self.admit(target=str(self.target / "nowhere"))
        self.assertIn("no directory", str(refused.exception))

    def test_a_target_that_is_not_an_absolute_path_is_refused(self):
        with self.assertRaises(profile_runs.NotDelegable):
            self.admit(target="../somewhere")

    def test_an_unusable_profile_is_refused_before_anything_is_written(self):
        self.wrote(skills=["reading-minds"])
        with self.assertRaises(profile_runs.NotDelegable):
            self.admit()
        self.assertEqual([], self.kept.profile_runs())
        self.assertFalse(profile_runs.home("elena", self.where).exists())

    def test_editing_the_shared_profile_afterwards_leaves_this_run_alone(self):
        admitted = self.admit()
        self.wrote(rules="# Different\n\nDo something else entirely.\n")
        at = profile_runs.paths("elena", admitted.id, self.where)
        self.assertEqual(RULES, at["rules"].read_text(encoding="utf-8"))
        row = self.kept.profile_run(admitted.id)
        self.assertEqual(RULES, profile_runs.verified("elena", row, self.where)["rules"])


class OneProfileLevelAndNoMore(WithAnAgentThatCanDelegate):
    """R-PRF-13 — a worker cannot delegate, and neither can the turn reviewing one."""

    def test_a_profile_run_cannot_admit_another_profile_run(self):
        admitted = self.admit()
        # The execution's own turn, in the conversation of its own that carrying one opens.
        where_it_is = store.conversation_id(turn.PROFILE, admitted.id)
        self.kept.opened(where_it_is, turn.PROFILE, turn.PROFILE, admitted.id, AT)
        inside = self.kept.began("profile", "codex", "work", AT,
                                 conversation_id=where_it_is, profile_run=admitted.id)
        with self.assertRaises(profile_runs.NotDelegable) as refused:
            profile_runs.admit("elena", "development", BRIEF, inside,
                               where=self.where, library=self.library)
        self.assertIn("one level deep", str(refused.exception))

    def test_a_turn_woken_to_review_a_handoff_cannot_start_another_profile_run(self):
        admitted = self.admit()
        self.carried(admitted)
        reviewing = self.a_turn()
        self.kept.profile_reviewing(admitted.id, reviewing)
        with self.assertRaises(profile_runs.NotDelegable) as refused:
            profile_runs.admit("elena", "development", BRIEF, reviewing,
                               where=self.where, library=self.library)
        self.assertIn("review", str(refused.exception))

    def test_the_recursion_marker_is_told_to_the_brain_as_well_as_recorded(self):
        admitted = self.admit()
        carry, _ = self.carried(admitted)
        self.assertEqual(admitted.id, carry.given["context"].profile_run)


class WhatAProfileExecutionIsToldAndGiven(WithAnAgentThatCanDelegate):
    """R-PRF-5, R-PRF-6, R-PRF-7, R-PRF-8 — the floor, the brief, the place, the skills."""

    def test_the_execution_stands_in_the_target_project(self):
        admitted = self.admit()
        carry, _ = self.carried(admitted)
        self.assertEqual(self.target.resolve(), carry.given["context"].cwd)

    def test_a_run_with_no_project_stands_in_its_own_locked_home(self):
        admitted = self.admit(target=None)
        carry, _ = self.carried(admitted)
        at = profile_runs.paths("elena", admitted.id, self.where)
        self.assertEqual(at["home"], carry.given["context"].cwd)

    def test_the_execution_is_presented_the_runs_own_locked_skill_snapshot(self):
        admitted = self.admit()
        carry, _ = self.carried(admitted)
        at = profile_runs.paths("elena", admitted.id, self.where)
        self.assertEqual(at["skills"], carry.given["context"].skills)
        self.assertNotEqual(agent.skills("elena", self.where),
                            carry.given["context"].skills)

    def test_the_brief_is_the_prompt_and_the_conversation_is_never_forwarded(self):
        admitted = self.admit()
        carry, _ = self.carried(admitted)
        self.assertEqual(BRIEF, carry.given["prompt"])

    def test_the_preface_carries_the_floor_then_the_profile_rules_then_the_task(self):
        admitted = self.admit()
        carry, _ = self.carried(admitted)
        told = carry.given["preface"]
        self.assertLess(told.index("You are a profile worker"), told.index("# Development"))
        self.assertLess(told.index("# Development"), told.index("## This execution"))
        self.assertIn(RULES.strip(), told)
        self.assertIn(admitted.id, told)

    def test_the_profile_rules_reach_the_brain_exactly_as_they_were_locked(self):
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
        self.assertIn("may not start another Rundesk profile run", told)

    def test_the_execution_runs_under_the_profiles_own_posture(self):
        self.wrote(posture="read")
        admitted = self.admit()
        carry, _ = self.carried(admitted)
        self.assertEqual("read", carry.given["posture"])

    def test_a_profile_execution_is_a_conversation_of_its_own(self):
        admitted = self.admit()
        carry, _ = self.carried(admitted)
        self.assertEqual(admitted.id, carry.given["conversation"])
        self.assertEqual(turn.PROFILE, carry.given["on"])
        self.assertEqual(turn.PROFILE, carry.given["source"])


class WhatATerminalOutcomeOwes(WithAnAgentThatCanDelegate):
    """R-PRF-15, R-PRF-16 — exactly one review, and nothing read out of the report."""

    def test_a_terminal_outcome_owes_its_parent_exactly_one_review(self):
        admitted = self.admit()
        self.carried(admitted)
        owed = self.kept.owed_profile_callback()
        self.assertEqual(admitted.id, owed["profile_run"])
        self.assertEqual(self.kept.profile_run(admitted.id)["parent_conversation"],
                         owed["conversation"])

    def test_offering_the_same_terminal_outcome_twice_still_owes_one_review(self):
        admitted = self.admit()
        _, outcome = self.carried(admitted)
        self.assertFalse(profile_runs.settle("elena", admitted.id, outcome,
                                             where=self.where))
        self.assertEqual(store.SUCCEEDED,
                         self.kept.profile_run(admitted.id)["state"])

    def test_a_run_that_failed_owes_the_same_one_review_as_one_that_worked(self):
        admitted = self.admit()
        self.carried(admitted, ok=False)
        self.assertEqual(store.FAILED, self.kept.profile_run(admitted.id)["state"])
        self.assertIsNotNone(self.kept.owed_profile_callback())

    def test_a_review_stops_being_owed_only_once_it_has_been_delivered(self):
        admitted = self.admit()
        self.carried(admitted)
        self.kept.claim_profile_callback(admitted.id, AT)
        self.assertIsNotNone(self.kept.owed_profile_callback())
        self.kept.profile_reviewed(admitted.id, AT)
        self.assertIsNone(self.kept.owed_profile_callback())

    def test_the_handoff_is_the_workers_own_words_and_nothing_read_out_of_them(self):
        admitted = self.admit()
        self.carried(admitted, said="Everything passed. Ship it.")
        handed = profile_runs.handoff("elena", admitted.id, self.where)
        self.assertEqual("Everything passed. Ship it.", handed["report"])
        self.assertEqual("succeeded", handed["outcome"])
        self.assertEqual("elena", handed["parent_agent"])
        self.assertEqual(self.parent, handed["parent_run"])
        self.assertEqual(str(self.target), handed["target"])

    def test_the_handoff_reports_what_the_brain_said_it_cost_and_nothing_it_did_not(self):
        admitted = self.admit()
        self.carried(admitted)
        # The turn the execution actually ran as, which the stand-in above does not write.
        carried = self.kept.began("profile", "codex", "work", AT,
                                  profile_run=admitted.id)
        self.kept.ended(carried, AT, "finished", exit_code=0,
                        tokens={"reported": True, "input": 120, "output": 30})
        handed = profile_runs.handoff("elena", admitted.id, self.where)
        self.assertEqual({"reported": True, "input": 120, "output": 30,
                          "cached": None, "written": None}, handed["usage"])
        self.assertTrue(handed["verification_recorded"])

    def test_a_run_nothing_reported_a_cost_for_says_so_rather_than_reporting_none(self):
        admitted = self.admit()
        self.carried(admitted)
        self.assertEqual({"reported": False},
                         profile_runs.handoff("elena", admitted.id, self.where)["usage"])

    def test_a_run_finished_by_hand_is_still_the_run_the_records_describe(self):
        admitted = self.admit()
        self.carried(admitted)
        self.assertEqual(admitted.id,
                         profile_runs.handoff("elena", admitted.id, self.where)["profile_run"])


class HowLongARunStaysResumable(WithAnAgentThatCanDelegate):
    """R-PRF-11, R-PRF-12 — a window from the latest activity, and what expiry leaves."""

    def test_the_retention_window_is_measured_from_the_latest_activity(self):
        admitted = self.admit()
        row = self.kept.profile_run(admitted.id)
        began = store.moment(row["admitted_at"])
        until = store.moment(row["retained_until"])
        self.assertEqual(profile_runs.RETAINED_DAYS, (until - began).days)
        self.kept.profile_active(admitted.id, "2026-08-05T09:00:00Z",
                                 "2026-08-19T09:00:00Z")
        self.assertEqual("2026-08-19T09:00:00Z",
                         self.kept.profile_run(admitted.id)["retained_until"])

    def test_a_run_inside_its_window_is_resumable(self):
        admitted = self.admit()
        self.assertTrue(profile_runs.resumable(self.kept.profile_run(admitted.id)))

    def test_expiring_takes_the_execution_context_and_keeps_the_record(self):
        admitted = self.admit()
        at = profile_runs.paths("elena", admitted.id, self.where)
        self.assertTrue(at["rules"].is_file())
        # A clock a fortnight on, passed in rather than waited for.
        gone = profile_runs.sweep("elena", self.where,
                                  now=lambda: store.moment("2026-09-01T09:00:00Z").timestamp())
        self.assertEqual([admitted.id], gone)
        self.assertFalse(at["run"].exists())
        row = self.kept.profile_run(admitted.id)
        self.assertEqual(store.EXPIRED, row["state"])
        self.assertEqual("development", row["profile"])
        self.assertIsNone(row["handle"])

    def test_an_expired_run_can_no_longer_be_carried_on(self):
        admitted = self.admit()
        profile_runs.sweep("elena", self.where,
                           now=lambda: store.moment("2026-09-01T09:00:00Z").timestamp())
        with self.assertRaises(profile_runs.NotDelegable) as refused:
            asyncio.run(profile_runs.carry("elena", admitted.id, where=self.where,
                                           carrying=Carried()))
        self.assertIn("retention", str(refused.exception))

    def test_a_run_whose_locked_skills_were_tampered_with_refuses_rather_than_runs(self):
        admitted = self.admit()
        at = profile_runs.paths("elena", admitted.id, self.where)
        shutil.rmtree(at["skills"] / "writing-plans")
        with self.assertRaises(profile_runs.NotDelegable) as refused:
            asyncio.run(profile_runs.carry("elena", admitted.id, where=self.where,
                                           carrying=Carried()))
        self.assertIn("locked skill snapshot", str(refused.exception))

    def test_a_run_that_already_finished_is_not_carried_again(self):
        admitted = self.admit()
        self.carried(admitted)
        with self.assertRaises(profile_runs.NotDelegable):
            asyncio.run(profile_runs.carry("elena", admitted.id, where=self.where,
                                           carrying=Carried()))


class WhatAPersonIsShown(WithAnAgentThatCanDelegate):
    """R-PRF-17 — an owner's private paths stay in the records."""

    def test_what_a_profile_run_shows_carries_no_local_path(self):
        admitted = self.admit()
        shown = profile_runs.shown(self.kept.profile_run(admitted.id))
        self.assertEqual(self.target.name, shown["target"])
        self.assertNotIn(str(self.target.parent), json.dumps(shown))

    def test_a_label_is_short_safe_and_never_the_brief(self):
        self.assertEqual("Applicant export",
                         profile_runs.safe_label("Applicant export", "Development"))
        self.assertEqual("Development", profile_runs.safe_label("", "Development"))
        self.assertNotIn("`", profile_runs.safe_label("`rm -rf /`", "Development"))
        self.assertLessEqual(len(profile_runs.safe_label("x " * 200, "Development")), 60)

    def test_a_listing_says_which_revision_and_which_skills_a_run_used(self):
        admitted = self.admit()
        shown = profile_runs.shown(self.kept.profile_run(admitted.id))
        self.assertEqual(admitted.revision[:12], shown["revision"])
        self.assertEqual(["writing-plans"], shown["skills"])


if __name__ == "__main__":
    unittest.main()
