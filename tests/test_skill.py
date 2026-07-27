"""The library of skills, and which agent was given which — every row of the skills work.

Offline and complete: nothing here reaches a brain, because what a brain does with a skill
is a probe's question and is answered in `.knowledge/research/`. What is answered here is
everything that happens before one runs — what the library holds, what a grant is, and
what granting and revoking are incapable of touching.
"""

from __future__ import annotations

import os
import sys
import tempfile
import shutil
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from rundesk import skill


def a_skill(at: Path, name: str, described: str = None, says: str = "") -> Path:
    """One skill on disk, in the shape every brain reads."""
    made = at / name
    made.mkdir(parents=True, exist_ok=True)
    described = "Gives the codename. Use when asked for the codename." if described is None \
        else described
    (made / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {described}\n---\n\n{says or 'Do the thing.'}\n",
        encoding="utf-8")
    return made


class WithALibrary(unittest.TestCase):
    """A library and an agent's own skills directory, both scratch."""

    def setUp(self):
        self.where = Path(tempfile.mkdtemp(prefix="rundesk-skills-"))
        self.addCleanup(shutil.rmtree, self.where, ignore_errors=True)
        self.library = self.where / "data" / "skills"
        self.library.mkdir(parents=True)
        self.mine = self.where / "data" / "agents" / "ava" / "home" / "skills"
        self.mine.mkdir(parents=True)


class WhatTheLibraryHolds(WithALibrary):
    def test_a_directory_with_no_skill_file_is_not_a_skill(self):
        """R-AGT-27 — an owner half way through writing one has not broken anything, and
        a brain would not index it either."""
        a_skill(self.library, "deploy")
        (self.library / "started-and-stopped").mkdir()
        self.assertEqual(["deploy"], sorted(skill.library(self.library)))

    def test_a_library_that_is_not_there_is_an_owner_who_has_made_none(self):
        """R-AGT-27 — never an error: a fresh install has no library until something is
        laid down in it, and everything that reads one has to survive that."""
        self.assertEqual({}, skill.library(self.where / "nothing here"))

    def test_every_skill_is_named_by_the_directory_it_stands_in(self):
        """R-AGT-27 — the name is what an agent is granted by, so it is read off the
        directory rather than out of the file, which could disagree with it."""
        a_skill(self.library, "deploy")
        self.assertEqual(self.library / "deploy", skill.library(self.library)["deploy"])


class WhatMakesASkill(WithALibrary):
    def test_a_name_the_brains_would_refuse_is_refused_here(self):
        """R-AGT-27 — grok will not index an underscore, so a skill named with one exists,
        is granted, is placed, and never fires. Refusing it is the only honest answer."""
        made = a_skill(self.library, "deploy")
        wrong = self.library / "deploy_thing"
        made.rename(wrong)
        self.assertIn("lowercase letters", skill.valid(wrong) or "")

    def test_a_skill_that_says_nothing_about_when_to_use_it_is_refused(self):
        """R-AGT-27 — the description is the whole of what a brain sees every turn. One
        that is empty is a skill nothing would ever reach for."""
        made = a_skill(self.library, "deploy", described="   ")
        self.assertIn("says nothing about when to use it", skill.valid(made) or "")

    def test_a_skill_naming_itself_something_else_is_refused(self):
        """R-AGT-27 — a brain indexes the frontmatter and finds the directory, or the
        other way about. Either way it is granted under one word and answers to another."""
        made = a_skill(self.library, "deploy")
        (made / "SKILL.md").write_text(
            "---\nname: something-else\ndescription: Anything.\n---\n\nx\n", encoding="utf-8")
        self.assertIn("the name and the directory have to be the same word",
                      skill.valid(made) or "")

    def test_a_description_past_the_limit_is_refused(self):
        """R-AGT-27 — the limit is the specification's, and past it the description is
        truncated by the loader rather than refused, so what triggers the skill is a
        sentence nobody wrote."""
        made = a_skill(self.library, "deploy", described="x" * (skill.DESCRIBED_LIMIT + 1))
        self.assertIn("longer than", skill.valid(made) or "")

    def test_a_skill_with_no_frontmatter_at_all_is_refused(self):
        """R-AGT-27 — a plain Markdown file in a directory is not a skill, and every brain
        would skip it silently."""
        made = self.library / "deploy"
        made.mkdir()
        (made / "SKILL.md").write_text("# Deploy\n\nDo the thing.\n", encoding="utf-8")
        self.assertIn("frontmatter", skill.valid(made) or "")

    def test_a_skill_that_is_all_of_those_things_is_one(self):
        """R-AGT-27 — the case that has to pass, or every refusal above is untested."""
        self.assertIsNone(skill.valid(a_skill(self.library, "deploy")))


class GivingAnAgentASkill(WithALibrary):
    def test_an_agent_is_given_a_skill_by_it_standing_in_its_own_directory(self):
        """R-AGT-28 — the grant is the directory rather than a record of one, so there is
        no second copy to disagree with what a brain will actually find."""
        a_skill(self.library, "deploy")
        skill.grant(self.mine, "deploy", self.library)
        self.assertEqual(["deploy"], skill.granted(self.mine))
        self.assertTrue((self.mine / "deploy" / "SKILL.md").is_file(),
                        "the grant does not reach the skill it names")

    def test_a_grant_is_a_link_so_editing_the_library_reaches_every_agent(self):
        """R-AGT-28 — a copy would be a second place for the same skill to be wrong, and
        an owner improving one would have to remember who had it."""
        made = a_skill(self.library, "deploy")
        skill.grant(self.mine, "deploy", self.library)
        (made / "SKILL.md").write_text(
            "---\nname: deploy\ndescription: Changed.\n---\n\nnew words\n", encoding="utf-8")
        self.assertIn("new words", (self.mine / "deploy" / "SKILL.md").read_text())

    def test_a_grant_survives_the_agent_directory_being_moved(self):
        """R-AGT-28 — written relative, so copying an agent to another machine does not
        leave every skill pointing at where the old one kept its library."""
        a_skill(self.library, "deploy")
        skill.grant(self.mine, "deploy", self.library)
        self.assertFalse(os.path.isabs(os.readlink(self.mine / "deploy")),
                         "the grant is written as an absolute path")

    def test_granting_a_skill_nobody_has_says_so(self):
        """R-AGT-28 — and says it rather than making an empty directory that reads as a
        skill an agent has and cannot use."""
        with self.assertRaises(skill.Unknown):
            skill.grant(self.mine, "not-a-thing", self.library)
        self.assertEqual([], skill.granted(self.mine))

    def test_granting_something_no_brain_would_index_is_refused(self):
        """R-AGT-28 — the check happens where the grant does, so an owner hears about it
        when they type the name rather than never."""
        a_skill(self.library, "deploy", described="")
        with self.assertRaises(skill.NotASkill):
            skill.grant(self.mine, "deploy", self.library)

    def test_granting_twice_leaves_one_grant(self):
        """R-AGT-28 — an owner repairing a half-removed agent types the same line again."""
        a_skill(self.library, "deploy")
        skill.grant(self.mine, "deploy", self.library)
        skill.grant(self.mine, "deploy", self.library)
        self.assertEqual(["deploy"], skill.granted(self.mine))

    def test_one_agents_skills_are_never_anothers(self):
        """R-AGT-28 — two agents, two directories, and a brain reads the one it stands in.
        This is the whole of how they are kept apart."""
        other = self.where / "data" / "agents" / "winston" / "home" / "skills"
        other.mkdir(parents=True)
        a_skill(self.library, "deploy")
        a_skill(self.library, "payroll")
        skill.grant(self.mine, "deploy", self.library)
        skill.grant(other, "payroll", self.library)
        self.assertEqual(["deploy"], skill.granted(self.mine))
        self.assertEqual(["payroll"], skill.granted(other))


class TakingASkillAway(WithALibrary):
    def test_revoking_takes_the_grant_and_leaves_the_skill(self):
        """R-AGT-29 — the library is the source of truth, so taking a skill from one agent
        cannot be how every other agent loses it."""
        a_skill(self.library, "deploy")
        skill.grant(self.mine, "deploy", self.library)
        skill.revoke(self.mine, "deploy", self.library)
        self.assertEqual([], skill.granted(self.mine))
        self.assertTrue((self.library / "deploy" / "SKILL.md").is_file(),
                        "revoking reached into the library")

    def test_revoking_what_was_never_granted_says_so(self):
        """R-AGT-29 — rather than reporting a success it did not earn."""
        with self.assertRaises(skill.Unknown):
            skill.revoke(self.mine, "deploy", self.library)

    def test_revoking_will_not_remove_a_directory_somebody_wrote_by_hand(self):
        """R-AGT-29 — the sharp one. An owner who put a skill straight into the agent's own
        directory has written work that rundesk never placed, and `revoke` has to be
        *incapable* of deleting it rather than careful about it."""
        theirs = a_skill(self.mine, "deploy")
        with self.assertRaises(skill.InTheWay):
            skill.revoke(self.mine, "deploy", self.library)
        self.assertTrue((theirs / "SKILL.md").is_file(), "revoking deleted an owner's own work")

    def test_revoking_will_not_follow_a_link_out_of_the_library(self):
        """R-AGT-29 — a link an owner made to somewhere else on their disk is theirs, and
        removing it is not rundesk's to do just because it stands in this directory."""
        elsewhere = a_skill(self.where / "their-own", "deploy")
        (self.mine / "deploy").symlink_to(elsewhere)
        with self.assertRaises(skill.InTheWay):
            skill.revoke(self.mine, "deploy", self.library)
        self.assertTrue((self.mine / "deploy").is_symlink(), "revoking took an owner's link")

    def test_granting_over_something_rundesk_did_not_place_is_refused(self):
        """R-AGT-29 — the same rule on the way in, or `grant` becomes the way to delete
        what `revoke` refused to."""
        theirs = a_skill(self.mine, "deploy")
        a_skill(self.library, "deploy")
        with self.assertRaises(skill.InTheWay):
            skill.grant(self.mine, "deploy", self.library)
        self.assertFalse((self.mine / "deploy").is_symlink())
        self.assertTrue((theirs / "SKILL.md").is_file())


class BringingTheBuiltInsForward(WithALibrary):
    """What an install lays down and an update brings forward.

    The shipped directory is replaced for the duration rather than mocked, because what is
    under test is precisely that the set is read off a directory and never off a list.
    """

    def setUp(self):
        super().setUp()
        self.release = self.where / "app" / "src" / "templates" / "skills"
        self.release.mkdir(parents=True)
        was = skill.SHIPPED
        skill.SHIPPED = self.release
        self.addCleanup(setattr, skill, "SHIPPED", was)

    def test_what_a_release_ships_is_read_off_the_directory(self):
        """R-AGT-30 — a list kept in code disagrees with the directory the day somebody
        adds a skill and forgets it, and the disagreement is invisible: a built-in never
        laid down is just a skill nobody has."""
        a_skill(self.release, "writing-skills")
        a_skill(self.release, "later-addition")
        self.assertEqual(("later-addition", "writing-skills"), skill.shipped())

    def test_installing_lays_the_built_ins_down(self):
        """R-AGT-30 — an owner has them without doing anything, which is the whole point
        of one being built in."""
        a_skill(self.release, "writing-skills")
        self.assertEqual(["writing-skills"], skill.lay_down(self.library))
        self.assertTrue((self.library / "writing-skills" / "SKILL.md").is_file())

    def test_installing_again_leaves_what_is_already_there(self):
        """R-AGT-30 — a second install is not a thing that overwrites work, which is the
        same promise making an agent again already makes (R-AGT-4)."""
        a_skill(self.release, "writing-skills")
        skill.lay_down(self.library)
        (self.library / "writing-skills" / "SKILL.md").write_text("theirs\n", encoding="utf-8")
        self.assertEqual([], skill.lay_down(self.library))
        self.assertEqual("theirs\n", (self.library / "writing-skills" / "SKILL.md").read_text())

    def test_updating_brings_a_built_in_forward(self):
        """R-AGT-30 — this is what "always the latest version" is, and it is the reason a
        built-in is rundesk's file rather than a copy an owner then owns."""
        a_skill(self.release, "writing-skills", says="the old words")
        skill.lay_down(self.library)
        a_skill(self.release, "writing-skills", says="the new words")
        self.assertEqual(["writing-skills"], skill.lay_down(self.library, force=True))
        self.assertIn("the new words",
                      (self.library / "writing-skills" / "SKILL.md").read_text())

    def test_updating_never_touches_a_skill_an_owner_wrote(self):
        """R-AGT-30 — the other half, and the one with the teeth. A refresh that reached
        anything not shipped would be an update deleting somebody's work."""
        a_skill(self.release, "writing-skills")
        theirs = a_skill(self.library, "our-deploy-notes", says="a month of work")
        was = (theirs / "SKILL.md").read_text()
        skill.lay_down(self.library, force=True)
        self.assertEqual(was, (theirs / "SKILL.md").read_text(),
                         "an update reached a skill the owner wrote")

    def test_a_library_that_cannot_be_written_to_does_not_break_the_install(self):
        """R-AGT-30 — an install that otherwise worked says what is wrong in words, and a
        diagnosis reports the missing skill; it does not traceback out of the middle."""
        a_skill(self.release, "writing-skills")
        blocked = self.where / "read-only" / "skills"
        blocked.mkdir(parents=True)
        blocked.chmod(0o500)
        self.addCleanup(blocked.chmod, 0o700)
        self.assertEqual([], skill.lay_down(blocked))


if __name__ == "__main__":
    unittest.main()
