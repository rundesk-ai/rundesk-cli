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

from rundesk import config, skill

#: What this release really declares and really ships, taken at import — every class below
#: points `skill.SHIPPED` at a scratch directory, so by the time a test runs neither can be
#: read off the module any more.
REALLY_RENAMED = dict(skill.RENAMED)
REALLY_SHIPPED = skill.SHIPPED
REALLY_RETIRED = tuple(skill.RETIRED)


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
    def test_the_provider_given_library_is_the_one_a_nested_command_reports(self):
        was = os.environ.get("RUNDESK_SKILL_LIBRARY")
        os.environ["RUNDESK_SKILL_LIBRARY"] = str(self.library)
        self.addCleanup(lambda: os.environ.__setitem__("RUNDESK_SKILL_LIBRARY", was)
                        if was is not None else os.environ.pop("RUNDESK_SKILL_LIBRARY", None))
        self.assertEqual(self.library, skill.home())

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

    def test_a_new_built_in_name_does_not_claim_an_owner_skill(self):
        """R-AGT-30 — matching a newly shipped name is not proof of ownership."""
        theirs = a_skill(self.library, "later-addition", says="an owner's work")
        was = (theirs / "SKILL.md").read_text()
        a_skill(self.release, "later-addition", says="the release's words")

        self.assertEqual([], skill.lay_down(self.library, force=True))
        self.assertEqual(was, (theirs / "SKILL.md").read_text(),
                         "an update replaced an owner skill with a new built-in")

    def test_take_back_leaves_a_shipped_name_the_install_did_not_lay_down(self):
        """R-RM-7 — uninstall ownership is proved by a marker, not the release's names."""
        theirs = a_skill(self.library, "later-addition", says="an owner's work")
        a_skill(self.release, "later-addition", says="the release's words")

        self.assertEqual([], skill.take_back(self.library))
        self.assertTrue((theirs / "SKILL.md").is_file(),
                        "uninstall took an owner skill it had preserved")

    def test_every_known_historical_fingerprint_can_acquire_the_marker(self):
        """R-AGT-30 — a direct update may skip releases without stranding a built-in."""
        self.assertIn(
            "eeea76bac1c12db493ad823b1d89d4d42740ab7b17173459b3c0705353332466",
            skill.LEGACY["building-a-channel-adapter"],
            "the v0.9 channel adapter can no longer be recognized by a direct update")
        old = a_skill(self.library, "writing-skills", says="historical words")
        fingerprint = skill._fingerprint(old)
        was = skill.LEGACY
        skill.LEGACY = {"writing-skills": ("another release", fingerprint)}
        self.addCleanup(setattr, skill, "LEGACY", was)
        a_skill(self.release, "writing-skills", says="current words")

        self.assertEqual(["writing-skills"], skill.lay_down(self.library, force=True))
        self.assertTrue((old / skill.OWNED).is_file())
        self.assertIn("current words", (old / skill.NAMED).read_text())

    def test_a_library_that_cannot_be_written_to_does_not_break_the_install(self):
        """R-AGT-30 — an install that otherwise worked says what is wrong in words, and a
        diagnosis reports the missing skill; it does not traceback out of the middle."""
        a_skill(self.release, "writing-skills")
        blocked = self.where / "read-only" / "skills"
        blocked.mkdir(parents=True)
        blocked.chmod(0o500)
        self.addCleanup(blocked.chmod, 0o700)
        self.assertEqual([], skill.lay_down(blocked))


class WhatARenameDoes(WithALibrary):
    """A built-in this release ships under a name an earlier one did not use.

    The failure this guards is quiet rather than loud: `lay_down` alone leaves the old
    directory standing with the old text in it and every grant of it still resolving, so
    an agent reads superseded instructions and nothing anywhere says so.
    """

    def setUp(self):
        super().setUp()
        self.release = self.where / "app" / "src" / "templates" / "skills"
        self.release.mkdir(parents=True)
        was_shipped, was_renamed = skill.SHIPPED, skill.RENAMED
        skill.SHIPPED = self.release
        skill.RENAMED = {"reporting-a-bug": "filing-issues"}
        was_retired = skill.RETIRED
        skill.RETIRED = ("building-adapters",)
        self.addCleanup(setattr, skill, "SHIPPED", was_shipped)
        self.addCleanup(setattr, skill, "RENAMED", was_renamed)
        self.addCleanup(setattr, skill, "RETIRED", was_retired)

    def _both_names(self):
        """The old built-in laid down, then the release renaming it."""
        a_skill(self.release, "reporting-a-bug", says="the old words")
        skill.lay_down(self.library)
        shutil.rmtree(self.release / "reporting-a-bug")
        a_skill(self.release, "filing-issues", says="the new words")
        skill.lay_down(self.library)

    def test_every_rename_names_a_skill_this_release_ships(self):
        """R-AGT-35 — a rename pointing at a name nobody ships carries every grant of the
        old one into nothing. Asserted against the real directory rather than the scratch
        one, because the value being checked is the declaration this release makes."""
        really_shipped = tuple(sorted(
            one.name for one in REALLY_SHIPPED.iterdir()
            if (one / skill.NAMED).is_file()))
        for old in REALLY_RETIRED:
            self.assertNotIn(old, really_shipped,
                             f"{old} is both retired and still shipped")
        for old, new in REALLY_RENAMED.items():
            self.assertIn(new, really_shipped,
                          f"{old} was renamed to {new}, which this release does not ship")
            self.assertNotIn(old, really_shipped,
                             f"{old} is both retired and still shipped")

    def test_no_shipped_instruction_names_a_skill_this_release_retired(self):
        """R-AGT-35 — the rename has to reach the words as well as the directory.

        Every file here is copied onto an owner's machine and read by a brain as an
        instruction. One naming a skill this release renamed away sends the agent to
        `rundesk skills grant <me> <old name>`, which answers `there is no skill called
        <old name>` — on every install, from the day it lands. Asserted against the real
        templates and the real declaration, because those are what ship.
        """
        gone = set(REALLY_RENAMED) | set(REALLY_RETIRED)
        shipped_text = sorted(
            one for one in (REALLY_SHIPPED.parent).rglob("*.md") if one.is_file())
        self.assertTrue(shipped_text, "no shipped instruction text was found to check")
        named = []
        for page in shipped_text:
            for number, line in enumerate(page.read_text(encoding="utf-8").splitlines(), 1):
                named += [f"{page.name}:{number} names `{one}`"
                          for one in sorted(gone) if f"`{one}`" in line]
        self.assertEqual([], named)

    def test_a_renamed_built_in_is_taken_out_of_the_library(self):
        """R-AGT-35 — left there it is not a broken link but a working one, pointing at
        text the release has replaced."""
        self._both_names()
        self.assertEqual(["reporting-a-bug"], skill.retire(self.library))
        self.assertFalse((self.library / "reporting-a-bug").exists())
        self.assertIn("the new words",
                      (self.library / "filing-issues" / skill.NAMED).read_text())

    def test_a_grant_of_a_renamed_built_in_becomes_a_grant_of_the_new_name(self):
        """R-AGT-35 — an agent that held it goes on holding it, under the name it now has."""
        self._both_names()
        skill.grant(self.mine, "reporting-a-bug", self.library)

        skill.retire(self.library, holding=(self.mine,))

        self.assertEqual(["filing-issues"], skill.granted(self.mine))
        self.assertTrue((self.mine / "filing-issues" / skill.NAMED).is_file(),
                        "the carried grant does not resolve to the new skill")

    def test_a_rename_never_hands_the_new_skill_to_an_agent_without_the_old(self):
        """R-AGT-35 — a grant is carried, never handed out. Nothing records that a grant
        was taken away, so anything that gave the new name to everybody would hand back,
        on every update, the skill an owner had just revoked."""
        self._both_names()

        skill.retire(self.library, holding=(self.mine,))

        self.assertEqual([], skill.granted(self.mine))

    def test_a_skill_the_owner_wrote_under_the_old_name_is_never_retired(self):
        """R-AGT-29, R-AGT-35 — a rename in a release must be incapable of taking away
        work somebody did, whatever they happened to call it."""
        a_skill(self.release, "filing-issues")
        skill.lay_down(self.library)
        theirs = a_skill(self.library, "reporting-a-bug", says="a month of work")
        skill.grant(self.mine, "reporting-a-bug", self.library)

        self.assertEqual([], skill.retire(self.library, holding=(self.mine,)))

        self.assertEqual("a month of work\n", (theirs / skill.NAMED).read_text().splitlines()[-1]
                         + "\n")
        self.assertEqual(["reporting-a-bug"], skill.granted(self.mine))

    def test_a_skill_the_owner_wrote_under_the_new_name_is_not_the_rename_landing(self):
        """R-AGT-29, R-AGT-35 — the destructive half of the same rule, and the only case
        here where getting it wrong cannot be undone.

        A release introduces names nobody was ever warned off, so an owner can already
        have written a skill called what a built-in is being renamed *to*. `lay_down`
        asks whose that directory is and correctly leaves it alone. Asking only whether
        the name stands reads their work as the rename having landed: the built-in is
        deleted, every agent holding it is handed a link to their unrelated file under
        the name the built-in had, and no later release puts it back — nothing ships the
        old name again and `lay_down` skips the new one for as long as their directory
        stands.
        """
        a_skill(self.release, "reporting-a-bug", says="the manual")
        skill.lay_down(self.library)
        theirs = a_skill(self.library, "filing-issues", says="a month of work")
        skill.grant(self.mine, "reporting-a-bug", self.library)
        shutil.rmtree(self.release / "reporting-a-bug")
        a_skill(self.release, "filing-issues", says="the new words")
        skill.lay_down(self.library, force=True)   # skips theirs, which is the point

        self.assertEqual([], skill.retire(self.library, holding=(self.mine,)))

        self.assertIn("the manual",
                      (self.library / "reporting-a-bug" / skill.NAMED).read_text(),
                      "the built-in was deleted with nothing of ours standing in its place")
        self.assertIn("a month of work", (theirs / skill.NAMED).read_text())
        self.assertEqual(["reporting-a-bug"], skill.granted(self.mine))
        self.assertIn("the manual", (self.mine / "reporting-a-bug" / skill.NAMED).read_text(),
                      "the agent's grant was repointed at a skill the owner wrote")

    def test_nothing_is_carried_until_the_new_name_is_in_the_library(self):
        """R-AGT-35 — a library that could not be written to leaves the new name absent,
        and a grant carried into nothing is a skill the agent no longer has."""
        a_skill(self.release, "reporting-a-bug")
        skill.lay_down(self.library)
        skill.grant(self.mine, "reporting-a-bug", self.library)

        self.assertEqual([], skill.retire(self.library, holding=(self.mine,)))

        self.assertEqual(["reporting-a-bug"], skill.granted(self.mine))
        self.assertTrue((self.library / "reporting-a-bug").is_dir())

    def test_a_built_in_this_release_dropped_is_taken_out_of_the_library(self):
        """R-AGT-35 — a built-in with no successor: what it held is documentation now, and
        leaving the directory means a library that grows a stale copy every release."""
        a_skill(self.release, "building-adapters", says="the old guide")
        skill.lay_down(self.library)
        shutil.rmtree(self.release / "building-adapters")

        self.assertEqual(["building-adapters"], skill.retire(self.library))
        self.assertFalse((self.library / "building-adapters").exists())

    def test_a_grant_of_a_dropped_built_in_is_taken_away_rather_than_left_pointing_at_nothing(self):
        """R-AGT-35 — a link to a directory that has gone is skipped in silence by every
        brain, so the agent keeps a grant that does nothing and nobody is told."""
        a_skill(self.release, "building-adapters")
        skill.lay_down(self.library)
        skill.grant(self.mine, "building-adapters", self.library)
        shutil.rmtree(self.release / "building-adapters")

        skill.retire(self.library, holding=(self.mine,))

        self.assertEqual([], skill.granted(self.mine))
        self.assertFalse((self.mine / "building-adapters").is_symlink())

    def test_uninstalling_takes_a_renamed_built_in_too(self):
        """R-RM-7 — one this release no longer ships by name is still a piece of rundesk,
        and leaving it keeps the whole install directory standing."""
        self._both_names()

        self.assertEqual(["filing-issues", "reporting-a-bug"],
                         sorted(skill.take_back(self.library)))
        self.assertFalse(self.library.exists(), "the library was left standing")


class WhatEachShippedAdapterPlaces(WithALibrary):
    """The `_present` every shipped adapter has, driven for real against a scratch home.

    Loaded out of the adapter files rather than reimplemented here, because they are
    programs rather than modules — nothing imports them, so the only way to hold three
    near-identical copies to one behaviour is to run each one. Triplicated and untested is
    where three copies quietly come apart.
    """

    BRAINS = {"claude": ".claude/skills", "codex": ".agents/skills", "grok": ".grok/skills"}

    def loaded(self, brain: str):
        import importlib.machinery
        import importlib.util
        at = Path(__file__).resolve().parent.parent / "src" / "providers" / brain
        loader = importlib.machinery.SourceFileLoader(f"rundesk_{brain}_probe", str(at))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        made = importlib.util.module_from_spec(spec)
        loader.exec_module(made)
        return made

    def standing(self, brain: str):
        """One agent home, with the granted skills placed by that brain's own adapter."""
        home = self.where / "data" / "agents" / "ava" / "home"
        home.mkdir(parents=True, exist_ok=True)
        was = os.environ.get("RUNDESK_SKILLS")
        os.environ["RUNDESK_SKILLS"] = str(self.mine)
        self.addCleanup(lambda: os.environ.__setitem__("RUNDESK_SKILLS", was)
                        if was is not None else os.environ.pop("RUNDESK_SKILLS", None))
        self.loaded(brain)._present(str(home))
        return home / self.BRAINS[brain]

    def test_every_shipped_adapter_places_a_granted_skill_where_its_brain_looks(self):
        """R-PRV-24 — measured per brain: claude reads only .claude/skills, codex reads
        .agents/skills, grok its own .grok/skills. A skill placed anywhere else is one no
        brain ever indexes, and nothing about the turn says so."""
        a_skill(self.library, "deploy")
        skill.grant(self.mine, "deploy", self.library)
        for brain in self.BRAINS:
            with self.subTest(brain=brain):
                root = self.standing(brain)
                self.assertTrue((root / "deploy" / "SKILL.md").is_file(),
                                f"{brain} would not find the skill its agent was given")

    def test_no_adapter_makes_a_directory_for_an_agent_given_nothing(self):
        """R-PRV-24 — an agent with no skills should have no vendor directory in its home
        to explain, and an empty one reads as a brain that was configured and did nothing."""
        for brain in self.BRAINS:
            with self.subTest(brain=brain):
                self.assertFalse(self.standing(brain).exists())

    def test_placing_twice_changes_nothing(self):
        """R-PRV-24 — it runs before every turn, so it has to be a no-op on the second."""
        a_skill(self.library, "deploy")
        skill.grant(self.mine, "deploy", self.library)
        for brain in self.BRAINS:
            with self.subTest(brain=brain):
                first = self.standing(brain)
                was = os.readlink(first / "deploy")
                self.standing(brain)
                self.assertEqual(was, os.readlink(first / "deploy"))

    def test_a_revoked_skill_stops_being_placed(self):
        """R-PRV-24 — revoking has to reach the brain, or a skill an owner took away goes
        on being read for as long as the agent lives."""
        a_skill(self.library, "deploy")
        skill.grant(self.mine, "deploy", self.library)
        for brain in self.BRAINS:
            with self.subTest(brain=brain):
                root = self.standing(brain)
                self.assertTrue((root / "deploy").is_symlink())
                skill.revoke(self.mine, "deploy", self.library)
                self.standing(brain)
                self.assertFalse((root / "deploy").exists(),
                                 f"{brain} still places a skill that was revoked")
                skill.grant(self.mine, "deploy", self.library)   # for the next brain

    def test_no_adapter_removes_an_owners_own_link_whose_target_is_briefly_away(self):
        """R-PRV-24 — the sharpest one. An owner may hand-place a link here to a skill of
        their own; a target on an unmounted drive, or mid-move, makes it look exactly like
        a grant that was revoked. Deleting on dangling alone took those, on every turn."""
        a_skill(self.library, "deploy")
        skill.grant(self.mine, "deploy", self.library)
        for brain in self.BRAINS:
            with self.subTest(brain=brain):
                root = self.standing(brain)
                away = a_skill(self.where / "their-drive", "personal")
                theirs = root / "personal"
                theirs.symlink_to(away)
                shutil.rmtree(self.where / "their-drive")      # the drive goes away
                self.standing(brain)
                self.assertTrue(theirs.is_symlink(),
                                f"{brain} deleted an owner's link while its target was away")

    def test_no_adapter_removes_something_it_did_not_place(self):
        """R-PRV-24 — the pruning is the only line here that can destroy anything. A
        directory somebody wrote by hand into the brain's own root is theirs."""
        a_skill(self.library, "deploy")
        skill.grant(self.mine, "deploy", self.library)
        for brain in self.BRAINS:
            with self.subTest(brain=brain):
                root = self.standing(brain)
                theirs = a_skill(root, "hand-written")
                self.standing(brain)
                self.assertTrue((theirs / "SKILL.md").is_file(),
                                f"{brain} deleted something it did not place")


class WhatARevokeCannotReach(WithALibrary):
    """The confinement every one of these rests on, probed from the outside.

    `Path("/a/b") / "/elsewhere"` is `/elsewhere` — the left side is discarded — so a name
    that arrives from a command line and is joined without being looked at first is a way
    to name any file on the machine, and `revoke` unlinks what it is given.
    """

    def test_a_name_that_is_a_path_cannot_reach_out_of_the_agents_own_directory(self):
        """R-AGT-29 — reachable by typing a path where a name goes, which is a thing
        somebody does by pasting. It deleted an owner's own symlink from their desktop."""
        a_skill(self.library, "deploy")
        theirs = self.where / "somewhere-else.lnk"
        theirs.symlink_to(self.library / "deploy")
        for typed in (str(theirs), "../somewhere-else.lnk", "/etc/hosts", "..", "", "."):
            with self.subTest(typed=typed):
                with self.assertRaises(skill.Unknown):
                    skill.revoke(self.mine, typed, self.library)
        self.assertTrue(theirs.is_symlink(), "revoking reached outside the agent's own")

    def test_a_name_that_is_a_path_cannot_be_granted_either(self):
        """R-AGT-29 — the same door on the way in, or `grant` becomes how you reach what
        `revoke` refused to."""
        a_skill(self.library, "deploy")
        with self.assertRaises(skill.Unknown):
            skill.grant(self.mine, "../deploy", self.library)


class WhenBringingOneForwardGoesWrong(WithALibrary):
    def setUp(self):
        super().setUp()
        self.release = self.where / "app" / "src" / "templates" / "skills"
        self.release.mkdir(parents=True)
        was = skill.SHIPPED
        skill.SHIPPED = self.release
        self.addCleanup(setattr, skill, "SHIPPED", was)

    def test_a_refresh_that_fails_leaves_the_version_that_was_working(self):
        """R-AGT-30 — removing the old one and copying the new one in its place leaves,
        if anything fails between the two, a directory that exists and is not a skill: no
        brain indexes it, the grant still resolves, and nothing reports it."""
        a_skill(self.release, "writing-skills", says="the old words")
        skill.lay_down(self.library)
        a_skill(self.release, "writing-skills", says="the new words")
        real = shutil.copytree

        def dies(*args, **kw):
            raise OSError("no space left on device")

        shutil.copytree = dies
        self.addCleanup(setattr, shutil, "copytree", real)
        self.assertEqual([], skill.lay_down(self.library, force=True))
        shutil.copytree = real
        self.assertIsNone(skill.valid(self.library / "writing-skills"),
                          "a failed refresh left something no brain would index")
        self.assertIn("the old words",
                      (self.library / "writing-skills" / "SKILL.md").read_text())

    def test_a_half_written_skill_is_not_left_in_the_library(self):
        """R-AGT-30 — what a failed refresh assembles under another name is not a skill
        anybody is offered, and does not linger as one."""
        a_skill(self.release, "writing-skills")
        real = shutil.copytree
        shutil.copytree = lambda *a, **k: (_ for _ in ()).throw(OSError("full"))
        self.addCleanup(setattr, shutil, "copytree", real)
        skill.lay_down(self.library)
        shutil.copytree = real
        self.assertEqual({}, skill.library(self.library))
        self.assertEqual([], [one for one in self.library.iterdir()])


class WhatMakingAnAgentGrants(WithALibrary):
    """The bootstrap, and the one thing it must not undo."""

    def setUp(self):
        super().setUp()
        from rundesk import agent as agents
        self.agents = agents
        self.release = self.where / "app" / "src" / "templates" / "skills"
        self.release.mkdir(parents=True)
        was = skill.SHIPPED
        skill.SHIPPED = self.release
        self.addCleanup(setattr, skill, "SHIPPED", was)
        a_skill(self.release, "writing-skills")
        skill.lay_down(self.library)
        # What a new agent is given is stated rather than "everything shipped" (R-AGT-36),
        # so the scratch release has to be named or nothing here is granted at all.
        (self.where / "data").mkdir(parents=True, exist_ok=True)
        (self.where / "data" / "config.json").write_text(
            '{"skills": {"granted": ["writing-skills"]}}\n', encoding="utf-8")
        for name, at in (("RUNDESK_DATA_DIR", self.where / "data"),
                         ("RUNDESK_SKILL_LIBRARY", self.library),
                         ("RUNDESK_AGENTS_DIR", self.where / "data" / "agents"),
                         ("RUNDESK_RUN_DIR", self.where / "run"),
                         ("RUNDESK_LOG_DIR", self.where / "logs")):
            had = os.environ.get(name)
            os.environ[name] = str(at)
            self.addCleanup(lambda n=name, h=had: os.environ.__setitem__(n, h)
                            if h is not None else os.environ.pop(n, None))

    def test_a_new_agent_is_given_what_the_release_ships(self):
        """R-AGT-27, R-AGT-36 — the bootstrap: an agent starts with what it needs to work
        rundesk at all, because it cannot use `skills grant` to give itself the skill that
        explains what granting is."""
        self.agents.add("ava")
        self.assertIn("writing-skills", skill.granted(self.agents.skills("ava")))

    def test_a_new_agent_is_given_what_the_configuration_says(self):
        """R-AGT-36 — a release ships more than every agent should carry, and a skill an
        agent never reaches for is not free: its description is read on every turn."""
        a_skill(self.release, "later-addition")
        skill.lay_down(self.library)

        self.agents.add("ava")

        self.assertEqual(["writing-skills"], skill.granted(self.agents.skills("ava")),
                         "an agent was given a skill the configuration did not name")

    def test_an_agent_is_made_with_the_skills_written_into_a_new_configuration(self):
        """R-AGT-36 — the required set is the four an agent needs to work with rundesk
        itself, written where the owner and the command both read it."""
        (self.where / "data" / "config.json").unlink()
        config.ensure(self.where / "data")
        required = config.INITIAL["skills"]["granted"]
        for called in required:
            a_skill(self.release, called)
        skill.lay_down(self.library)

        self.agents.add("ava")

        self.assertEqual(sorted(required), skill.granted(self.agents.skills("ava")))

    def test_an_owner_who_wants_no_skills_granted_gets_none(self):
        """R-AGT-36 — an empty list is a thing somebody stated, and turning it back into
        the default is the quiet override this whole file exists to prevent."""
        (self.where / "data" / "config.json").write_text(
            '{"skills": {"granted": []}}\n', encoding="utf-8")

        self.agents.add("ava")

        self.assertEqual([], skill.granted(self.agents.skills("ava")))

    def test_a_configuration_that_cannot_be_read_refuses_to_make_the_agent(self):
        """R-AGT-36 — never treated as absent: the skills this agent would be given are
        stated there, and making it without them is an owner's decision silently ignored."""
        (self.where / "data" / "config.json").write_text("{ not json\n", encoding="utf-8")

        with self.assertRaises(config.Unreadable):
            self.agents.add("ava")

    def test_a_diagnosis_judges_an_agent_against_what_is_configured(self):
        """R-AGT-36 — judged against every shipped skill instead, a diagnosis would report
        every skill the owner deliberately kept off the default set as missing."""
        a_skill(self.release, "later-addition")
        skill.lay_down(self.library)
        self.agents.add("ava")

        complained = [one for one in self.agents.diagnosed("ava")
                      if "later-addition" in str(one)]

        self.assertEqual([], complained,
                         "a diagnosis asked for a skill the configuration never named")

class NothingHereReachesTheOwnersOwn(unittest.TestCase):
    """The guard on every fixture in this repository that isolates rundesk's directories.

    Making an agent now grants what the release ships, and a grant is a link into the
    library — so a suite that isolated the four directories an agent keeps and forgot the
    root they all fall back to would link a scratch agent at the *owner's* real library and
    pass while doing it. `MEMORY.md` records the same shape costing three real agents in a
    live install, under the older `RUNDESK_HOME` versus `RUNDESK_AGENTS_DIR` confusion.
    """

    def test_every_place_an_agent_resolves_is_under_the_data_root_it_was_given(self):
        """R-AGT-27, R-AGT-28 — a directory this suite did not name is one it cannot have
        isolated, and the failure is silent: the case passes and the owner's library is
        what was read."""
        import rundesk
        from rundesk import agent as agents
        where = Path(tempfile.mkdtemp(prefix="rundesk-isolation-"))
        self.addCleanup(shutil.rmtree, where, ignore_errors=True)
        was = os.environ.get("RUNDESK_DATA_DIR")
        os.environ["RUNDESK_DATA_DIR"] = str(where / "data")
        self.addCleanup(lambda: os.environ.__setitem__("RUNDESK_DATA_DIR", was)
                        if was is not None else os.environ.pop("RUNDESK_DATA_DIR", None))
        was_library = os.environ.get("RUNDESK_SKILL_LIBRARY")
        os.environ["RUNDESK_SKILL_LIBRARY"] = str(where / "data" / "skills")
        self.addCleanup(lambda: os.environ.__setitem__("RUNDESK_SKILL_LIBRARY", was_library)
                        if was_library is not None
                        else os.environ.pop("RUNDESK_SKILL_LIBRARY", None))
        for name in ("RUNDESK_AGENTS_DIR", "RUNDESK_RUN_DIR", "RUNDESK_LOG_DIR"):
            had = os.environ.pop(name, None)
            if had is not None:
                self.addCleanup(os.environ.__setitem__, name, had)
        root = (where / "data").resolve()
        for what, at in (("data", rundesk.data_home()), ("agents", agents.agents_home()),
                         ("skills", skill.home())):
            self.assertEqual(root, at.resolve() if what == "data" else at.resolve().parent,
                             f"{what} resolves outside the data root it was given")


if __name__ == "__main__":
    unittest.main()
