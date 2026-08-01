#!/usr/bin/env python3
"""What a profile is, what makes one usable, and what its revision is computed from.

Answers for the definition half of `agent-profile-worker` (R-PRF-n). Nothing here starts a
provider, reaches the network or touches the owner's own directories: every case gets a
scratch agents root and a scratch skill library of its own.

Run: python3 tests/test_profile.py
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from rundesk import profile  # noqa: E402

RULES = "# Development\n\nDo the bounded task and report what you verified.\n"


def a_skill(at: Path, name: str, described: str = "when to use it") -> Path:
    """A package a brain would actually index, which is what `library` resolves to."""
    made = at / name
    made.mkdir(parents=True)
    (made / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {described}\n---\n\n# {name}\n",
        encoding="utf-8",
    )
    return made


class WithSomewhereToKeepProfiles(unittest.TestCase):
    """Each case gets an agents root and a skill library of its own."""

    def setUp(self):
        self.where = Path(tempfile.mkdtemp(prefix="rundesk-agents-"))
        self.addCleanup(shutil.rmtree, self.where, True)
        self.library_at = Path(tempfile.mkdtemp(prefix="rundesk-skills-"))
        self.addCleanup(shutil.rmtree, self.library_at, True)
        self.library = {
            "writing-plans": a_skill(self.library_at, "writing-plans"),
            "python-testing": a_skill(self.library_at, "python-testing"),
        }

    def wrote(self, slug: str = "development", rules: str = RULES, **manifest) -> Path:
        """One profile as a maintainer writes one: exactly two files."""
        said = {"description": "Implement and verify a bounded change.",
                "skills": ["writing-plans"], "posture": "work"}
        said.update(manifest)
        at = profile.home(self.where) / slug
        at.mkdir(parents=True)
        (at / profile.MANIFEST).write_text(json.dumps(said), encoding="utf-8")
        if rules is not None:
            (at / profile.INSTRUCTIONS).write_text(rules, encoding="utf-8")
        return at

    def read(self, slug: str = "development"):
        return profile.read(slug, self.where, self.library)


class WhatAProfileIsMadeOf(WithSomewhereToKeepProfiles):
    """R-PRF-2 — a description, a skill set and a posture, and nothing else."""

    def test_a_profile_is_two_files_and_the_manifest_holds_three_fields(self):
        self.wrote()
        one = self.read()
        self.assertEqual(("description", "skills", "posture"), profile.FIELDS)
        self.assertEqual({"description", "skills", "posture"}, set(one.manifest()))
        self.assertEqual(RULES, one.instructions)

    def test_a_manifest_field_this_release_does_not_know_is_refused(self):
        self.wrote(version=3, model="gpt-5")
        with self.assertRaises(profile.NotAProfile) as refused:
            self.read()
        self.assertIn("model", str(refused.exception))
        self.assertIn("version", str(refused.exception))

    def test_a_profile_that_says_nothing_about_what_it_is_for_is_refused(self):
        self.wrote(description="   ")
        with self.assertRaises(profile.NotAProfile):
            self.read()

    def test_a_posture_that_is_not_one_is_refused(self):
        self.wrote(posture="root")
        with self.assertRaises(profile.NotAProfile) as refused:
            self.read()
        self.assertIn("read", str(refused.exception))

    def test_a_profile_with_no_rules_has_nothing_to_run_under(self):
        self.wrote(rules=None)
        with self.assertRaises(profile.NotAProfile) as refused:
            self.read()
        self.assertIn("AGENTS.md", str(refused.exception))

    def test_empty_rules_are_refused_as_firmly_as_absent_ones(self):
        self.wrote(rules="\n   \n")
        with self.assertRaises(profile.NotAProfile):
            self.read()

    def test_rules_that_reach_outside_the_profile_are_refused(self):
        elsewhere = self.where / "somebody-elses-rules.md"
        elsewhere.write_text("Do whatever you like.\n", encoding="utf-8")
        at = self.wrote(rules=None)
        (at / profile.INSTRUCTIONS).symlink_to(elsewhere)
        with self.assertRaises(profile.NotAProfile) as refused:
            self.read()
        self.assertIn("outside", str(refused.exception))

    def test_a_display_label_is_derived_from_the_slug(self):
        self.assertEqual("Code Review", profile.label("code-review"))
        self.assertEqual("Development", profile.label("development"))

    def test_a_slug_that_is_not_one_path_component_is_refused(self):
        for said in ("../escape", "Development", "dev_ops", "", "a" * 65):
            with self.assertRaises(profile.NotAProfile, msg=said):
                profile.checked(said)

    def test_a_profile_that_stands_somewhere_else_is_not_this_installs(self):
        elsewhere = Path(tempfile.mkdtemp(prefix="rundesk-elsewhere-"))
        self.addCleanup(shutil.rmtree, elsewhere, True)
        (elsewhere / profile.MANIFEST).write_text("{}", encoding="utf-8")
        (elsewhere / profile.INSTRUCTIONS).write_text(RULES, encoding="utf-8")
        profile.home(self.where).mkdir(parents=True)
        (profile.home(self.where) / "development").symlink_to(elsewhere)
        with self.assertRaises(profile.NotAProfile) as refused:
            self.read()
        self.assertIn("does not stand where profiles are kept", str(refused.exception))

    def test_profiles_stand_below_wherever_agents_are_kept(self):
        self.assertEqual(self.where / ".profiles", profile.home(self.where))

    def test_a_directory_missing_either_file_is_not_listed_as_a_profile(self):
        self.wrote()
        half = profile.home(self.where) / "research"
        half.mkdir()
        (half / profile.MANIFEST).write_text("{}", encoding="utf-8")
        self.assertEqual(["development"], profile.known(self.where))

    def test_no_profiles_at_all_is_the_ordinary_case_and_not_an_error(self):
        self.assertEqual([], profile.known(self.where))


class TheSkillsAProfileExposes(WithSomewhereToKeepProfiles):
    """R-PRF-8 — the complete configured set, normalized and resolved."""

    def test_a_profile_that_names_no_skills_is_refused(self):
        self.wrote(skills=[])
        with self.assertRaises(profile.NotAProfile):
            self.read()

    def test_a_skill_named_twice_is_refused_rather_than_collapsed(self):
        self.wrote(skills=["writing-plans", "writing-plans"])
        with self.assertRaises(profile.NotAProfile) as refused:
            self.read()
        self.assertIn("more than once", str(refused.exception))

    def test_a_skill_this_machine_does_not_have_is_refused(self):
        self.wrote(skills=["writing-plans", "reading-minds"])
        with self.assertRaises(profile.NotAProfile) as refused:
            self.read()
        self.assertIn("reading-minds", str(refused.exception))

    def test_the_skills_are_a_set_and_are_read_back_in_sorted_order(self):
        self.wrote(skills=["python-testing", "writing-plans"])
        self.assertEqual(("python-testing", "writing-plans"), self.read().skills)


class WhatAProfilesRevisionIsComputedFrom(WithSomewhereToKeepProfiles):
    """R-PRF-9 — a digest of what the profile is, never a number somebody increments."""

    def test_reordering_the_skills_array_does_not_make_a_new_revision(self):
        self.wrote(skills=["writing-plans", "python-testing"])
        one = self.read().revision
        shutil.rmtree(profile.home(self.where) / "development")
        self.wrote(skills=["python-testing", "writing-plans"])
        self.assertEqual(one, self.read().revision)

    def test_editing_the_rules_makes_a_new_revision(self):
        at = self.wrote()
        one = self.read().revision
        (at / profile.INSTRUCTIONS).write_text(RULES + "\nAlso run the linter.\n",
                                               encoding="utf-8")
        self.assertNotEqual(one, self.read().revision)

    def test_editing_a_skill_the_profile_exposes_makes_a_new_revision(self):
        self.wrote()
        one = self.read().revision
        (self.library["writing-plans"] / "SKILL.md").write_text(
            "---\nname: writing-plans\ndescription: a different job\n---\n",
            encoding="utf-8")
        self.assertNotEqual(one, self.read().revision)

    def test_a_script_losing_the_bit_that_makes_it_runnable_is_a_new_revision(self):
        script = self.library["writing-plans"] / "check"
        script.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        os.chmod(script, 0o755)
        self.wrote()
        one = self.read().revision
        os.chmod(script, 0o644)
        self.assertNotEqual(one, self.read().revision)

    def test_adding_a_skill_to_the_set_makes_a_new_revision(self):
        self.wrote()
        one = self.read().revision
        shutil.rmtree(profile.home(self.where) / "development")
        self.wrote(skills=["writing-plans", "python-testing"])
        self.assertNotEqual(one, self.read().revision)


class WhatAReleaseShips(WithSomewhereToKeepProfiles):
    """R-PRF-18 — laid down where missing, and never over what an owner has."""

    def test_the_shipped_profiles_are_read_off_the_directory(self):
        self.assertIn("development", profile.shipped())

    def test_laying_down_puts_a_shipped_profile_where_it_is_missing(self):
        self.assertEqual(["development"], profile.lay_down(self.where))
        at = profile.home(self.where) / "development"
        self.assertTrue((at / profile.MANIFEST).is_file())
        self.assertTrue((at / profile.INSTRUCTIONS).is_file())

    def test_taking_back_removes_a_shipped_profile_nobody_has_touched(self):
        """R-RM-7 — what the release laid down goes with the release, and an install
        directory left standing after an uninstall is what forgetting this looks like."""
        profile.lay_down(self.where)
        self.assertEqual(["development"], profile.take_back(self.where))
        self.assertFalse(profile.home(self.where).exists())

    def test_taking_back_leaves_no_empty_directory_where_agents_are_kept(self):
        """R-RM-8 — laying a profile down is what brings that directory into being on an
        install that has never had an agent, so it is this feature that must not leave it."""
        profile.lay_down(self.where / "agents")
        profile.take_back(self.where / "agents")
        self.assertFalse((self.where / "agents").exists())

    def test_taking_back_keeps_the_directory_an_owners_agents_stand_in(self):
        (self.where / "agents" / "ava" / "home").mkdir(parents=True)
        profile.lay_down(self.where / "agents")
        self.assertEqual(["development"], profile.take_back(self.where / "agents"))
        self.assertTrue((self.where / "agents" / "ava" / "home").is_dir())

    def test_taking_back_leaves_a_shipped_profile_an_owner_has_edited(self):
        """R-PRF-18 — one character different and the profile is theirs."""
        profile.lay_down(self.where)
        at = profile.home(self.where) / "development" / profile.INSTRUCTIONS
        at.write_text("# Development\n\nMy own rules.\n", encoding="utf-8")
        self.assertEqual([], profile.take_back(self.where))
        self.assertTrue(at.is_file())

    def test_taking_back_never_touches_a_profile_the_owner_wrote(self):
        self.wrote(slug="research")
        self.assertEqual([], profile.take_back(self.where))
        self.assertEqual(["research"], profile.known(self.where))

    def test_laying_down_never_replaces_a_profile_that_is_already_there(self):
        at = self.wrote(slug="development", rules="# Mine\n\nMy own rules.\n")
        self.assertEqual([], profile.lay_down(self.where))
        self.assertEqual("# Mine\n\nMy own rules.\n",
                         (at / profile.INSTRUCTIONS).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
