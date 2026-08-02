#!/usr/bin/env python3
"""What a role is, what makes one usable, and what its revision is computed from.

Answers for the definition half of `agent-role` (R-ROL-n). Nothing here starts a
provider, reaches the network or touches the owner's own directories: every case gets a
scratch agents root and a scratch skill library of its own.

Run: python3 tests/test_role.py
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

from rundesk import role  # noqa: E402

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


class WithSomewhereToKeepRoles(unittest.TestCase):
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
        """One role as a maintainer writes one: exactly two files."""
        said = {"description": "Implement and verify a bounded change.",
                "skills": ["writing-plans"], "posture": "work"}
        said.update(manifest)
        at = role.home(self.where) / slug
        at.mkdir(parents=True)
        (at / role.MANIFEST).write_text(json.dumps(said), encoding="utf-8")
        if rules is not None:
            (at / role.INSTRUCTIONS).write_text(rules, encoding="utf-8")
        return at

    def read(self, slug: str = "development"):
        return role.read(slug, self.where, self.library)


class WhatARoleIsMadeOf(WithSomewhereToKeepRoles):
    """R-ROL-2 — a description, a skill set, a posture and a brain, and nothing else."""

    def test_a_role_is_two_files_and_the_manifest_holds_five_fields(self):
        self.wrote()
        one = self.read()
        self.assertEqual(("description", "skills", "posture", "provider", "model"),
                         role.FIELDS)
        self.assertEqual({"description", "skills", "posture"}, set(one.manifest()))
        self.assertEqual(RULES, one.instructions)

    def test_a_role_that_pins_a_brain_carries_it_in_its_manifest(self):
        """R-ROL-33 — what is written is what is locked, and nothing is invented."""
        self.wrote(provider="codex", model="gpt-5-codex")
        one = self.read()
        self.assertEqual(("codex", "gpt-5-codex"), (one.provider, one.model))
        self.assertEqual({"description", "skills", "posture", "provider", "model"},
                         set(one.manifest()))
        self.assertEqual("codex", one.manifest()["provider"])

    def test_a_manifest_field_this_release_does_not_know_is_refused(self):
        self.wrote(version=3, brain="gpt-5")
        with self.assertRaises(role.NotARole) as refused:
            self.read()
        self.assertIn("brain", str(refused.exception))
        self.assertIn("version", str(refused.exception))

    def test_a_role_that_says_nothing_about_what_it_is_for_is_refused(self):
        self.wrote(description="   ")
        with self.assertRaises(role.NotARole):
            self.read()

    def test_a_posture_that_is_not_one_is_refused(self):
        self.wrote(posture="root")
        with self.assertRaises(role.NotARole) as refused:
            self.read()
        self.assertIn("read", str(refused.exception))

    def test_a_role_with_no_rules_has_nothing_to_run_under(self):
        self.wrote(rules=None)
        with self.assertRaises(role.NotARole) as refused:
            self.read()
        self.assertIn("AGENTS.md", str(refused.exception))

    def test_empty_rules_are_refused_as_firmly_as_absent_ones(self):
        self.wrote(rules="\n   \n")
        with self.assertRaises(role.NotARole):
            self.read()

    def test_rules_that_reach_outside_the_role_are_refused(self):
        elsewhere = self.where / "somebody-elses-rules.md"
        elsewhere.write_text("Do whatever you like.\n", encoding="utf-8")
        at = self.wrote(rules=None)
        (at / role.INSTRUCTIONS).symlink_to(elsewhere)
        with self.assertRaises(role.NotARole) as refused:
            self.read()
        self.assertIn("outside", str(refused.exception))

    def test_a_display_label_is_derived_from_the_slug(self):
        self.assertEqual("Code Review", role.label("code-review"))
        self.assertEqual("Development", role.label("development"))

    def test_a_slug_that_is_not_one_path_component_is_refused(self):
        for said in ("../escape", "Development", "dev_ops", "", "a" * 65):
            with self.assertRaises(role.NotARole, msg=said):
                role.checked(said)

    def test_a_role_that_stands_somewhere_else_is_not_this_installs(self):
        elsewhere = Path(tempfile.mkdtemp(prefix="rundesk-elsewhere-"))
        self.addCleanup(shutil.rmtree, elsewhere, True)
        (elsewhere / role.MANIFEST).write_text("{}", encoding="utf-8")
        (elsewhere / role.INSTRUCTIONS).write_text(RULES, encoding="utf-8")
        role.home(self.where).mkdir(parents=True)
        (role.home(self.where) / "development").symlink_to(elsewhere)
        with self.assertRaises(role.NotARole) as refused:
            self.read()
        self.assertIn("does not stand where roles are kept", str(refused.exception))

    def test_roles_stand_below_wherever_agents_are_kept(self):
        self.assertEqual(self.where / ".roles", role.home(self.where))

    def test_a_directory_missing_either_file_is_not_listed_as_a_role(self):
        self.wrote()
        half = role.home(self.where) / "research"
        half.mkdir()
        (half / role.MANIFEST).write_text("{}", encoding="utf-8")
        self.assertEqual(["development"], role.known(self.where))

    def test_no_roles_at_all_is_the_ordinary_case_and_not_an_error(self):
        self.assertEqual([], role.known(self.where))


class TheSkillsARoleExposes(WithSomewhereToKeepRoles):
    """R-ROL-8 — the complete configured set, normalized and resolved."""

    def test_a_role_that_names_no_skills_is_refused(self):
        self.wrote(skills=[])
        with self.assertRaises(role.NotARole):
            self.read()

    def test_a_skill_named_twice_is_refused_rather_than_collapsed(self):
        self.wrote(skills=["writing-plans", "writing-plans"])
        with self.assertRaises(role.NotARole) as refused:
            self.read()
        self.assertIn("more than once", str(refused.exception))

    def test_a_skill_this_machine_does_not_have_is_left_out_rather_than_refused(self):
        """R-ROL-8 — a role is a definition an owner may share between machines and write
        ahead of the library. Refusing the whole thing over one absent package would make
        it unusable here for a capability the work in front of it may never need."""
        self.wrote(skills=["writing-plans", "reading-minds"])
        one = self.read()
        self.assertEqual(("writing-plans",), one.skills)
        self.assertEqual(("reading-minds",), one.missing)

    def test_a_role_whose_skills_are_all_absent_is_still_a_role(self):
        self.wrote(skills=["reading-minds"])
        one = self.read()
        self.assertEqual((), one.skills)
        self.assertEqual(("reading-minds",), one.missing)

    def test_a_skill_arriving_later_changes_what_the_next_run_is_given(self):
        """The revision covers what the role asks for, not only what resolved — so a
        package installed afterwards moves it, and a run admitted after that gets it."""
        self.wrote(skills=["writing-plans", "python-testing"])
        without = dict(self.library)
        without.pop("python-testing")
        thin = role.read("development", self.where, without)
        whole = self.read()
        self.assertEqual(("writing-plans",), thin.skills)
        self.assertEqual(("python-testing", "writing-plans"), whole.skills)
        self.assertNotEqual(thin.revision, whole.revision)

    def test_the_skills_are_a_set_and_are_read_back_in_sorted_order(self):
        self.wrote(skills=["python-testing", "writing-plans"])
        self.assertEqual(("python-testing", "writing-plans"), self.read().skills)


class WhatARolesRevisionIsComputedFrom(WithSomewhereToKeepRoles):
    """R-ROL-9 — a digest of what the role is, never a number somebody increments."""

    def test_reordering_the_skills_array_does_not_make_a_new_revision(self):
        self.wrote(skills=["writing-plans", "python-testing"])
        one = self.read().revision
        shutil.rmtree(role.home(self.where) / "development")
        self.wrote(skills=["python-testing", "writing-plans"])
        self.assertEqual(one, self.read().revision)

    def test_editing_the_rules_makes_a_new_revision(self):
        at = self.wrote()
        one = self.read().revision
        (at / role.INSTRUCTIONS).write_text(RULES + "\nAlso run the linter.\n",
                                               encoding="utf-8")
        self.assertNotEqual(one, self.read().revision)

    def test_editing_a_skill_the_role_exposes_makes_a_new_revision(self):
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
        shutil.rmtree(role.home(self.where) / "development")
        self.wrote(skills=["writing-plans", "python-testing"])
        self.assertNotEqual(one, self.read().revision)

    def test_pinning_a_brain_makes_a_new_revision(self):
        """R-ROL-33 — which brain a role runs on is part of what the role is."""
        self.wrote()
        one = self.read().revision
        shutil.rmtree(role.home(self.where) / "development")
        self.wrote(provider="codex")
        pinned = self.read().revision
        self.assertNotEqual(one, pinned)
        shutil.rmtree(role.home(self.where) / "development")
        self.wrote(provider="claude")
        self.assertNotEqual(pinned, self.read().revision)

    def test_naming_a_model_makes_a_new_revision(self):
        """R-ROL-33 — and it is its own field, not folded into the brain's."""
        self.wrote(provider="codex")
        one = self.read().revision
        shutil.rmtree(role.home(self.where) / "development")
        self.wrote(provider="codex", model="gpt-5-codex")
        self.assertNotEqual(one, self.read().revision)

    #: What a role naming neither a brain nor a model digests to, written down rather than
    #: computed. **This is the whole of the back-compatibility claim** (R-ROL-33): the
    #: revision is what makes a locked role reproducible, so a release that moved it for a
    #: role nobody edited would make every installed role read as edited — and a test that
    #: computed the expected value with the same code it is checking could never see that.
    UNPINNED = "297d6e9ff17c5a338b99d9c267e571322712a9a6970a83fdd382764bf265cd04"

    #: And the same for the role this release actually ships, read against a machine with
    #: none of the skills it names — which is the answer that does not depend on what any
    #: one library happens to hold.
    #: Moved twice, deliberately: #275 reshaped `development/AGENTS.md` into the one shape
    #: every role is written in, and the heavy-focus roles gave every shipped role a
    #: `## Not this role` section (R-ROL-38). `lay_down` never writes over a role that is
    #: already there (R-ROL-18), so no installed role re-revisions — this is the digest of
    #: what a *fresh* install now gets, and moving it is the reason this constant is
    #: written by hand.
    SHIPPED_DEVELOPMENT = (
        "43ee2eeb886c40a3561f471e70da54397c335048bc0b702e6ff274dbf0a41346")

    def test_a_role_naming_neither_keeps_the_revision_it_already_had(self):
        self.wrote()
        self.assertEqual(self.UNPINNED, self.read().revision)

    def test_the_shipped_role_keeps_the_revision_it_already_had(self):
        role.lay_down(self.where)
        self.assertEqual(self.SHIPPED_DEVELOPMENT,
                         role.read("development", self.where, {}).revision)


class WhichBrainARoleRunsOn(WithSomewhereToKeepRoles):
    """R-ROL-33 — a role may name the brain its runs use, and most name none."""

    def test_a_role_that_names_neither_pins_nothing(self):
        self.wrote()
        one = self.read()
        self.assertEqual(("", ""), (one.provider, one.model))

    def test_a_brain_this_release_has_never_heard_of_is_read_like_any_other(self):
        """There is no list of brains to check against, and there never will be."""
        self.wrote(provider="/opt/my-brain", model="whatever-it-calls-it")
        one = self.read()
        self.assertEqual(("/opt/my-brain", "whatever-it-calls-it"),
                         (one.provider, one.model))

    def test_a_brain_field_that_names_nothing_is_refused(self):
        for said in ("", "   ", None, 3, ["codex"]):
            with self.subTest(said=said):
                shutil.rmtree(role.home(self.where) / "development", ignore_errors=True)
                self.wrote(provider=said)
                with self.assertRaises(role.NotARole) as refused:
                    self.read()
                self.assertIn("provider", str(refused.exception))

    def test_a_model_field_that_names_nothing_is_refused(self):
        self.wrote(model="")
        with self.assertRaises(role.NotARole) as refused:
            self.read()
        self.assertIn("model", str(refused.exception))

    def test_a_brain_that_could_not_be_one_is_refused_when_the_role_is_read(self):
        for said in ("codex\nclaude", "x" * (role.PINNED_LIMIT + 1)):
            with self.subTest(said=said[:20]):
                shutil.rmtree(role.home(self.where) / "development", ignore_errors=True)
                self.wrote(provider=said)
                with self.assertRaises(role.NotARole):
                    self.read()

    def test_what_is_written_is_kept_without_its_surrounding_space(self):
        self.wrote(provider="  codex  ")
        self.assertEqual("codex", self.read().provider)


class WhatAReleaseShips(WithSomewhereToKeepRoles):
    """R-ROL-18 — laid down where missing, and never over what an owner has."""

    def test_the_shipped_roles_are_read_off_the_directory(self):
        self.assertIn("development", role.shipped())
        self.assertIn("research", role.shipped())

    def test_every_shipped_role_reads_as_a_usable_role(self):
        """A role template ships as somebody's starting point, so a broken one is not
        found until they try to delegate. Read each here instead, against a library that
        has none of what they name — every reason a definition is unusable is a reason
        that holds whatever this machine's skills are."""
        role.lay_down(self.where)
        for slug in role.shipped():
            with self.subTest(role=slug):
                one = role.read(slug, self.where, {})
                self.assertTrue(one.description)
                self.assertIn(one.posture, ("read", "work"))
                self.assertTrue(one.instructions.strip())

    def test_every_shipped_role_says_what_it_is_not_for(self):
        """R-ROL-38 — a run costs a whole context to set up and hands back a report
        somebody has to review, so a role reached for a two-file edit or a lookup is worse
        than no role at all. Every shipped one names that light work before it says
        anything about the heavy work, where a parent deciding whether to delegate reads
        it rather than after the rules it will never get to."""
        role.lay_down(self.where)
        for slug in role.shipped():
            with self.subTest(role=slug):
                rules = role.read(slug, self.where, {}).instructions
                self.assertIn("## Not this role", rules)
                self.assertLess(rules.index("## Not this role"),
                                rules.index("## Start here"))

    def test_every_shipped_role_ends_in_a_numbered_definition_of_done(self):
        """R-ROL-38 — what a parent reviews an unchecked report against. Numbered because
        a checkable list is reviewed item by item and a paragraph is skimmed."""
        role.lay_down(self.where)
        for slug in role.shipped():
            with self.subTest(role=slug):
                rules = role.read(slug, self.where, {}).instructions
                done = rules[rules.index("## Definition of done"):]
                self.assertIn("\n1. ", done)
                self.assertIn("\n2. ", done)

    def test_laying_down_puts_every_shipped_role_where_it_is_missing(self):
        self.assertEqual(sorted(role.shipped()), sorted(role.lay_down(self.where)))
        for slug in role.shipped():
            at = role.home(self.where) / slug
            self.assertTrue((at / role.MANIFEST).is_file())
            self.assertTrue((at / role.INSTRUCTIONS).is_file())

    def test_taking_back_removes_a_shipped_role_nobody_has_touched(self):
        """R-RM-7 — what the release laid down goes with the release, and an install
        directory left standing after an uninstall is what forgetting this looks like."""
        role.lay_down(self.where)
        self.assertEqual(sorted(role.shipped()), sorted(role.take_back(self.where)))
        self.assertFalse(role.home(self.where).exists())

    def test_taking_back_leaves_no_empty_directory_where_agents_are_kept(self):
        """R-RM-8 — laying a role down is what brings that directory into being on an
        install that has never had an agent, so it is this feature that must not leave it."""
        role.lay_down(self.where / "agents")
        role.take_back(self.where / "agents")
        self.assertFalse((self.where / "agents").exists())

    def test_taking_back_keeps_the_directory_an_owners_agents_stand_in(self):
        (self.where / "agents" / "ava" / "home").mkdir(parents=True)
        role.lay_down(self.where / "agents")
        self.assertEqual(sorted(role.shipped()),
                         sorted(role.take_back(self.where / "agents")))
        self.assertTrue((self.where / "agents" / "ava" / "home").is_dir())

    def test_taking_back_leaves_a_shipped_role_an_owner_has_edited(self):
        """R-ROL-18 — one character different and the role is theirs."""
        role.lay_down(self.where)
        at = role.home(self.where) / "development" / role.INSTRUCTIONS
        at.write_text("# Development\n\nMy own rules.\n", encoding="utf-8")
        self.assertNotIn("development", role.take_back(self.where))
        self.assertTrue(at.is_file())

    def test_taking_back_never_touches_a_role_the_owner_wrote(self):
        """A slug this release has never shipped, so what is proved here is ownership
        rather than the byte comparison an edited shipped role would go through."""
        self.wrote(slug="archaeology")
        self.assertEqual([], role.take_back(self.where))
        self.assertEqual(["archaeology"], role.known(self.where))

    def test_laying_down_never_replaces_a_role_that_is_already_there(self):
        at = self.wrote(slug="development", rules="# Mine\n\nMy own rules.\n")
        self.assertNotIn("development", role.lay_down(self.where))
        self.assertEqual("# Mine\n\nMy own rules.\n",
                         (at / role.INSTRUCTIONS).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
