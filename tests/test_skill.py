"""The library of skills, and which agent was given which — every row of the skills work.

Offline and complete: nothing here reaches a brain, because what a brain does with a skill
is a probe's question and is answered in `.knowledge/research/`. What is answered here is
everything that happens before one runs — what the library holds, what a grant is, and
what granting and revoking are incapable of touching.
"""

from __future__ import annotations

import json
import os
import fcntl
import subprocess
import sys
import tempfile
import shutil
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from rundesk import config, skill

#: What this release really ships, taken at import — every class below points
#: `skill.SHIPPED` at a scratch directory while it runs.
REALLY_SHIPPED = skill.SHIPPED
REPOSITORY = REALLY_SHIPPED.parents[2]


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


def a_complete_skill(at: Path, name: str) -> Path:
    """One Agent Skills package, including every standard resource directory."""
    made = a_skill(at, name, says=(
        f'Run "$RUNDESK_SKILLS/{name}/scripts/{name}" and read '
        "references/usage.md only when it fails."))
    command = made / "scripts" / name
    command.parent.mkdir()
    command.write_text("#!/bin/sh\nprintf 'ready\\n'\n", encoding="utf-8")
    command.chmod(0o751)
    references = made / "references"
    references.mkdir()
    (references / "usage.md").write_text("# Usage\n\nKeep it bounded.\n", encoding="utf-8")
    assets = made / "assets"
    assets.mkdir()
    (assets / "report.txt").write_text("{{ result }}\n", encoding="utf-8")
    data = made / "data"
    data.mkdir()
    (data / "schema.json").write_text('{"version": 1}\n', encoding="utf-8")
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


class WhatTheShippedAuthoringSkillSays(unittest.TestCase):
    def test_skill_authoring_guidance_defines_complete_packages(self):
        """R-AGT-44 — Rundesk's own reusable format ships with Rundesk."""
        page = (REALLY_SHIPPED / "writing-skills" / "SKILL.md").read_text()
        for expected in (
                "scripts/", "references/", "assets/",
                '"$RUNDESK_SKILLS/<name>/scripts/<command>"',
                "do not put a companion command in the shared script library"):
            with self.subTest(expected=expected):
                self.assertIn(expected, page)

    def test_skill_authoring_guidance_matches_verification_and_form_to_the_failure(self):
        """R-AGT-47 — reusable guidance is tested as the kind of guidance it is, and
        changes the observed failure instead of adding generic rules."""
        page = (REALLY_SHIPPED / "writing-skills" / "SKILL.md").read_text()
        for expected in (
                "Discipline skill", "Technique skill", "Pattern skill", "Reference skill",
                "positive contract", "required slot", "observable condition",
                "exact rationalizations", "become a shortcut"):
            with self.subTest(expected=expected):
                self.assertIn(expected, page)
        for excluded in (
                "superpowers:", "~/.claude", "~/.agents", "Graphviz", "persuasion",
                "Delete means delete", "REQUIRED BACKGROUND", "pressure scenario with subagent"):
            with self.subTest(excluded=excluded):
                self.assertNotIn(excluded, page)

    def test_plan_guidance_keeps_executable_plans_in_the_agent_workspace(self):
        """R-AGT-51 — a plan has one discoverable home and enough verified detail for a
        later worker without inheriting this conversation."""
        page = (REALLY_SHIPPED / "writing-plans" / "SKILL.md").read_text()
        for expected in (
                "<workspace>/plans/YYYY-MM-DD-<short-topic>.md",
                "Create `plans/` if an older workspace",
                "exact paths", "exact command", "Map every requirement",
                "Do not begin implementation unless"):
            with self.subTest(expected=expected):
                self.assertIn(expected, page)
        for excluded in ("superpowers:", "docs/superpowers", "REQUIRED SUB-SKILL"):
            with self.subTest(excluded=excluded):
                self.assertNotIn(excluded, page)

    def test_workspace_organization_guidance_keeps_processes_tidy_and_repositories_outside(self):
        """R-AGT-45, R-AGT-50 — release-default agents keep coordination artifacts tidy
        without turning their workspace into another project directory."""
        page = (REALLY_SHIPPED / "organizing-workspaces" / "SKILL.md").read_text()
        for expected in (
                "plans/", "MEMORY.md", "AGENTS.md", "one canonical home",
                "Do not clone a project", "git worktree list --porcelain",
                "git worktree remove <exact-path>", "Age alone is not evidence",
                "no project repository, `.git` directory, or project worktree"):
            with self.subTest(expected=expected):
                self.assertIn(expected, page)
        for excluded in (
                "~/.claude", "~/.agents", "docs/superpowers",
                "## Build a routing map", "## Directory", "## Relationships"):
            with self.subTest(excluded=excluded):
                self.assertNotIn(excluded, page)

    def test_management_skill_names_drop_the_redundant_rundesk_qualifier(self):
        """R-AGT-49 — shipped management guidance keeps the capability while its owned
        package and grants follow the shorter name."""
        for old, new in (
                ("managing-rundesk-backups", "managing-backups"),
                ("managing-rundesk-schedules", "managing-schedules")):
            with self.subTest(old=old, new=new):
                self.assertEqual(new, skill.RENAMED[old])
                self.assertFalse((REALLY_SHIPPED / old).exists())
                # **Followed to the end, because a rename may itself have been renamed.**
                # Backups became a section of `managing-rundesk` rather than a skill, so
                # the capability an old grant resolves to is two hops away and only the
                # last one still ships a package.
                carries = new
                while carries in skill.RENAMED:
                    carries = skill.RENAMED[carries]
                page = (REALLY_SHIPPED / carries / "SKILL.md").read_text()
                self.assertIn(f"name: {carries}", page)

    def test_release_guidance_discovers_each_repositorys_release_contract(self):
        """R-AGT-53 — releasing is one process across repositories, so the shipped guidance
        asks each repository for its own contract instead of carrying this one's."""
        page = (REALLY_SHIPPED / "publishing-github-releases" / "SKILL.md").read_text()
        for expected in (
                "Establish the release contract", "git describe --tags --abbrev=0",
                "gh pr list --base", "The repository's rules win",
                "Where the version literal lives", "What the repository's own validation gate is",
                "Who clears the approval gate", "Between patch and minor, take the minor",
                "closing keyword",
                '"$RUNDESK_SKILLS/publishing-github-releases/scripts/issues-closed-by.py"'):
            with self.subTest(expected=expected):
                self.assertIn(expected, page)
        # This repository's own policy belongs in this repository, not in guidance every
        # other project reads. A path or a version here is the split having failed.
        for excluded in (
                "rundesk-ai/rundesk-cli", "src/rundesk/__init__.py",
                ".knowledge/scripts/gate", "release/v0.", "rundesk update --check"):
            with self.subTest(excluded=excluded):
                self.assertNotIn(excluded, page)

    def test_release_guidance_ships_without_being_required(self):
        """R-AGT-53 — cutting releases is specialist work, so the package is in the library
        for anyone to be granted and is given to nobody by default."""
        self.assertTrue((REALLY_SHIPPED / "publishing-github-releases" / "SKILL.md").exists())
        self.assertIn("publishing-github-releases", skill.shipped())
        self.assertNotIn("publishing-github-releases", config.RUNDESK_REQUIRED_GRANTS)
        self.assertNotIn("publishing-github-releases",
                         config.INITIAL["skills"]["granted"])
        # An owner skill retired in favour of this one is not a renamed built-in: it carries
        # no ownership marker, so a RENAMED entry would never fire and must not be added.
        self.assertNotIn("rundesk-cli-releases", skill.RENAMED)

    def test_the_release_checker_defaults_to_the_repository_it_runs_in(self):
        """R-AGT-53 — a command beside a shared skill names no project, so it answers about
        the checkout it is run in and refuses rather than guessing when there is none."""
        script = (REALLY_SHIPPED / "publishing-github-releases" / "scripts"
                  / "issues-closed-by.py")
        self.assertTrue(os.access(script, os.X_OK))
        source = script.read_text()
        self.assertNotIn("rundesk", source)
        self.assertIn("gh\", \"repo\", \"view\"", source)
        self.assertIn("pass --repo owner/name", source)
        # Every unanswerable path says why before stopping: the definition and both callers.
        # Asserted positively, because the shape being excluded — `sys.exit(f"..." and 2)`,
        # which returns the 2 and throws the message away — is quoted in the code that
        # explains it, so a negative match would find its own documentation.
        self.assertIn("print(why, file=sys.stderr)", source)
        self.assertEqual(3, source.count("unanswerable("))

    def test_github_collaboration_overlays_consolidate_into_generic_skills(self):
        """R-AGT-49 — old Rundesk-specific grants retain their capability without
        shipping two copies of the same repository-aware workflow."""
        for old, shared in (
                ("filing-rundesk-issues", "filing-github-issues"),
                ("writing-rundesk-pull-requests", "writing-github-pull-requests")):
            with self.subTest(old=old, shared=shared):
                self.assertEqual(shared, skill.RENAMED[old])
                self.assertFalse((REALLY_SHIPPED / old).exists())
                self.assertTrue((REALLY_SHIPPED / shared / "SKILL.md").is_file())

    def test_generic_github_guidance_defers_to_each_repository_and_verifies_the_result(self):
        issue = (REALLY_SHIPPED / "filing-github-issues" / "SKILL.md").read_text()
        pull = (REALLY_SHIPPED / "writing-github-pull-requests" / "SKILL.md").read_text()
        for page in (issue, pull):
            with self.subTest(skill="issue" if page is issue else "pull request"):
                self.assertIn("CONTRIBUTING.md", page)
                self.assertIn("--body-file", page)
                self.assertIn("verify", page.lower())
        self.assertIn("--state all", issue)
        self.assertIn("SECURITY.md", issue)
        self.assertIn("<base-remote>/<base>...HEAD", pull)
        self.assertIn("headRepositoryOwner", pull)
        self.assertIn("--head <branch>", pull)
        self.assertIn("--head <user>:<branch>", pull)
        self.assertIn("closingIssuesReferences", pull)
        for expected in ("body contract", "placeholders", "template compliance"):
            with self.subTest(expected=expected):
                self.assertIn(expected, issue)
                self.assertIn(expected, pull)
        self.assertIn("required sections", issue)
        self.assertIn("required headings", pull)
        self.assertIn("YAML issue form", issue)
        self.assertIn("validations.required", issue)

    def test_rundesk_repository_supplies_bug_feature_and_pull_request_templates(self):
        issue_templates = REPOSITORY / ".github" / "ISSUE_TEMPLATE"
        bug = (issue_templates / "bug.yml").read_text()
        feature = (issue_templates / "feature.yml").read_text()
        pull = (REPOSITORY / ".github" / "pull_request_template.md").read_text()

        for page, issue_type in ((bug, "Bug"), (feature, "Feature")):
            with self.subTest(issue_type=issue_type):
                self.assertIn(f"type: {issue_type}", page)
                self.assertIn("label: Acceptance criteria", page)
                self.assertIn("label: Filing identity", page)
                self.assertIn("required: true", page)
        for heading in (
                "## Summary", "## Problem", "## Implementation", "## Validation",
                "## Issue linkage", "## Agent"):
            with self.subTest(heading=heading):
                self.assertIn(heading, pull)
        self.assertIn("🤖 by <Agent>", pull)


class WhatTheReleaseNoLongerOwns(unittest.TestCase):
    def test_optional_external_skills_are_not_rundesk_built_ins(self):
        """R-CAT-6, R-AGT-35 — optional skills have an external owner or none yet."""
        for called in (
                "frontend-design", "laravel-patterns", "python-patterns",
                "python-testing", "vue-patterns", "pdf-creation", "seo"):
            with self.subTest(skill=called):
                self.assertNotIn(called, skill.shipped())


class WhatTheLibraryHolds(WithALibrary):
    def test_grant_changes_share_one_install_wide_lock(self):
        """R-CAT-9 — a grant cannot enter while catalog retirement is deciding."""
        with skill.changing_grants(self.library):
            contender = os.open(self.library, os.O_RDONLY)
            self.addCleanup(os.close, contender)
            with self.assertRaises(OSError):
                fcntl.flock(contender, fcntl.LOCK_EX | fcntl.LOCK_NB)

        fcntl.flock(contender, fcntl.LOCK_EX | fcntl.LOCK_NB)

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
    def test_every_required_skill_is_part_of_the_release(self):
        """R-AGT-36 — the non-removable baseline can always be laid down and granted."""
        shipped = {one.name for one in REALLY_SHIPPED.iterdir() if (one / skill.NAMED).is_file()}
        self.assertEqual(set(), set(config.RUNDESK_REQUIRED_GRANTS) - shipped)

    def test_every_built_in_is_a_valid_skill(self):
        """R-AGT-27, R-AGT-30 — a release must not lay down a built-in that every brain
        silently refuses to index."""
        for name in sorted(one.name for one in REALLY_SHIPPED.iterdir()
                           if (one / skill.NAMED).is_file()):
            with self.subTest(skill=name):
                self.assertIsNone(skill.valid(REALLY_SHIPPED / name))

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

    def test_a_complete_skill_package_is_valid(self):
        """R-AGT-44 — SKILL.md makes the directory a skill; its bundled resources do not
        need separate installation or registration."""
        self.assertIsNone(skill.valid(a_complete_skill(self.library, "deploy")))


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

    def test_a_grant_reaches_every_resource_in_a_skill_package(self):
        """R-AGT-44 — granting the directory, rather than copying SKILL.md, is what keeps
        an integration's instructions and executable capability on one lifecycle."""
        made = a_complete_skill(self.library, "deploy")
        skill.grant(self.mine, "deploy", self.library)
        granted = self.mine / "deploy"
        ran = subprocess.run(
            [str(granted / "scripts" / "deploy")],
            capture_output=True, text=True, check=True)
        self.assertEqual("ready\n", ran.stdout)
        self.assertEqual((made / "references" / "usage.md").read_text(),
                         (granted / "references" / "usage.md").read_text())
        self.assertEqual((made / "assets" / "report.txt").read_text(),
                         (granted / "assets" / "report.txt").read_text())
        self.assertEqual((made / "data" / "schema.json").read_text(),
                         (granted / "data" / "schema.json").read_text())
        self.assertEqual(0o751, (granted / "scripts" / "deploy").stat().st_mode & 0o777)

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

    def test_revoking_a_complete_skill_package_removes_only_access(self):
        """R-AGT-29, R-AGT-44 — revoking an integration removes the agent's route to its
        whole package without deleting any part of the reusable library copy."""
        package = a_complete_skill(self.library, "deploy")
        skill.grant(self.mine, "deploy", self.library)
        skill.revoke(self.mine, "deploy", self.library)
        self.assertFalse((self.mine / "deploy").exists())
        self.assertTrue((package / "scripts" / "deploy").is_file())
        self.assertTrue((package / "references" / "usage.md").is_file())
        self.assertTrue((package / "assets" / "report.txt").is_file())
        self.assertTrue((package / "data" / "schema.json").is_file())

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

    def test_installing_and_updating_preserve_a_complete_skill_package(self):
        """R-AGT-30, R-AGT-44 — a built-in is the complete directory, not the one file
        that makes a brain index it."""
        shipped = a_complete_skill(self.release, "writing-skills")
        skill.lay_down(self.library)
        installed = self.library / "writing-skills"
        self.assertEqual("{{ result }}\n",
                         (installed / "assets" / "report.txt").read_text())
        self.assertEqual(0o751,
                         (installed / "scripts" / "writing-skills").stat().st_mode & 0o777)

        (shipped / "references" / "usage.md").write_text(
            "# Usage\n\nNew release.\n", encoding="utf-8")
        skill.lay_down(self.library, force=True)
        self.assertIn("New release.",
                      (installed / "references" / "usage.md").read_text())
        self.assertEqual('{"version": 1}\n',
                         (installed / "data" / "schema.json").read_text())
        self.assertEqual(0o751,
                         (installed / "scripts" / "writing-skills").stat().st_mode & 0o777)

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

    def test_an_expired_built_in_name_is_no_longer_runtime_policy(self):
        """R-AGT-35 — names absent from this release are ordinary owner data, even when
        an ownership marker shows that an older release once placed them."""
        expired = a_skill(self.library, "expired-built-in", says="historical words")
        (expired / skill.OWNED).write_text("rundesk built-in\n", encoding="utf-8")
        a_skill(self.release, "current-built-in")

        self.assertEqual(["current-built-in"], skill.lay_down(self.library, force=True))
        self.assertEqual(["current-built-in"], skill.take_back(self.library))
        self.assertTrue((expired / skill.NAMED).is_file(),
                        "runtime policy still reached a name this release does not ship")

    def test_a_renamed_built_in_replaces_only_the_copy_rundesk_owned(self):
        """R-AGT-49 — an intentional rename does not leave duplicate shipped guidance,
        and the ownership marker is still the boundary on what an update may remove."""
        a_skill(self.release, "writing-skills", says="current words")
        old = a_skill(self.library, "writing-rundesk-skills", says="historical words")
        (old / skill.OWNED).write_text("rundesk built-in\n", encoding="utf-8")

        skill.lay_down(self.library, force=True)
        skill.retire_renamed([], self.library)

        self.assertFalse(old.exists())
        self.assertIn("current words", (self.library / "writing-skills" / "SKILL.md").read_text())

    def test_a_renamed_built_in_leaves_an_owner_skill_under_the_old_name(self):
        """R-AGT-49"""
        a_skill(self.release, "writing-skills")
        old = a_skill(self.library, "writing-rundesk-skills", says="owner words")

        skill.lay_down(self.library, force=True)
        skill.retire_renamed([], self.library)

        self.assertIn("owner words", (old / "SKILL.md").read_text())

    def test_a_blocked_replacement_keeps_the_previous_built_in_working(self):
        """R-AGT-49 — a coincident owner skill under the new name cannot make an update
        delete the old working built-in before its replacement exists."""
        a_skill(self.release, "writing-skills", says="release words")
        old = a_skill(self.library, "writing-rundesk-skills", says="historical words")
        (old / skill.OWNED).write_text("rundesk built-in\n", encoding="utf-8")
        a_skill(self.library, "writing-skills", says="owner words")

        skill.lay_down(self.library, force=True)
        skill.retire_renamed([], self.library)

        self.assertTrue(old.is_dir())

    def test_take_back_leaves_a_shipped_name_the_install_did_not_lay_down(self):
        """R-RM-7 — uninstall ownership is proved by a marker, not the release's names."""
        theirs = a_skill(self.library, "later-addition", says="an owner's work")
        a_skill(self.release, "later-addition", says="the release's words")

        self.assertEqual([], skill.take_back(self.library))
        self.assertTrue((theirs / "SKILL.md").is_file(),
                        "uninstall took an owner skill it had preserved")

    def test_uninstall_takes_a_blocked_renamed_builtin_but_keeps_the_owner_collision(self):
        """R-RM-7, R-AGT-49 — ownership, not current spelling, determines removal."""
        a_skill(self.release, "writing-skills", says="release words")
        old = a_skill(self.library, "writing-rundesk-skills", says="historical words")
        (old / skill.OWNED).write_text("rundesk built-in\n", encoding="utf-8")
        owner = a_skill(self.library, "writing-skills", says="owner words")

        removed = skill.take_back(self.library)

        self.assertIn("writing-rundesk-skills", removed)
        self.assertFalse(old.exists())
        self.assertIn("owner words", (owner / skill.NAMED).read_text())

    def test_uninstalling_removes_a_complete_built_in_skill_package(self):
        """R-AGT-44, R-RM-7 — the complete built-in belongs to the release, so uninstall
        neither strands its executable nor leaves a partial package behind."""
        a_complete_skill(self.release, "writing-skills")
        skill.lay_down(self.library)
        self.assertEqual(["writing-skills"], skill.take_back(self.library))
        self.assertFalse(self.library.exists())


    def test_a_library_that_cannot_be_written_to_does_not_break_the_install(self):
        """R-AGT-30 — an install that otherwise worked says what is wrong in words, and a
        diagnosis reports the missing skill; it does not traceback out of the middle."""
        a_skill(self.release, "writing-skills")
        blocked = self.where / "read-only" / "skills"
        blocked.mkdir(parents=True)
        blocked.chmod(0o500)
        self.addCleanup(blocked.chmod, 0o700)
        self.assertEqual([], skill.lay_down(blocked))



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

    def test_every_shipped_adapter_presents_a_complete_skill_package(self):
        """R-AGT-44, R-PRV-24 — every supported brain receives the same complete package,
        including the executable bit its bundled command needs."""
        a_complete_skill(self.library, "deploy")
        skill.grant(self.mine, "deploy", self.library)
        for brain in self.BRAINS:
            with self.subTest(brain=brain):
                package = self.standing(brain) / "deploy"
                ran = subprocess.run(
                    [str(package / "scripts" / "deploy")],
                    capture_output=True, text=True, check=True)
                self.assertEqual("ready\n", ran.stdout)
                self.assertTrue((package / "references" / "usage.md").is_file())
                self.assertTrue((package / "assets" / "report.txt").is_file())
                self.assertTrue((package / "data" / "schema.json").is_file())
                self.assertEqual(
                    0o751, (package / "scripts" / "deploy").stat().st_mode & 0o777)

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
        for called in config.RUNDESK_REQUIRED_GRANTS:
            a_skill(self.release, called)
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

        self.assertEqual(sorted((*config.RUNDESK_REQUIRED_GRANTS, "writing-skills")),
                         skill.granted(self.agents.skills("ava")),
                         "an agent was given a skill the configuration did not name")

    def test_an_existing_agent_is_reconciled_to_the_required_baseline(self):
        """R-AGT-36 — adding a required value on update applies to agents that already
        exist; otherwise config.json governs only future users of the install."""
        self.agents.add("ava")
        a_skill(self.release, "later-addition")
        a_skill(self.release, "owner-chose-this")
        skill.lay_down(self.library)
        skill.grant(self.agents.skills("ava"), "owner-chose-this")
        (self.where / "data" / "config.json").write_text(
            '{"skills": {"granted": ["writing-skills", "later-addition"]}}\n',
            encoding="utf-8")

        self.agents.require_skills("ava")

        self.assertEqual(sorted((*config.RUNDESK_REQUIRED_GRANTS, "later-addition",
                                 "owner-chose-this", "writing-skills")),
                         skill.granted(self.agents.skills("ava")))

    def test_reconciliation_adds_the_plan_home_to_an_existing_workspace(self):
        """R-AGT-48 — update reconciliation gives existing agents the same canonical plan
        home as newly created agents."""
        self.agents.add("ava")
        shutil.rmtree(self.agents.plans("ava"))

        self.agents.require_skills("ava")

        self.assertTrue(self.agents.plans("ava").is_dir())

    def test_an_existing_rundesk_grant_follows_a_built_in_rename(self):
        """R-AGT-49 — optional grants migrate too, while a foreign entry under the old
        spelling remains outside Rundesk's authority."""
        shutil.rmtree(self.release / "writing-skills")
        a_skill(self.release, "writing-rundesk-skills")
        skill.lay_down(self.library)
        skill.grant(self.agents.skills("ava"), "writing-rundesk-skills")
        old = self.library / "writing-rundesk-skills"
        (old / skill.OWNED).write_text("rundesk built-in\n", encoding="utf-8")
        a_skill(self.release, "writing-skills")
        skill.lay_down(self.library, force=True)

        self.agents.require_skills("ava")
        self.agents.retire_renamed_skills()

        granted = skill.granted(self.agents.skills("ava"))
        self.assertIn("writing-skills", granted)
        self.assertNotIn("writing-rundesk-skills", granted)
        self.assertFalse(old.exists())

    def test_an_owner_skill_and_its_grant_keep_the_old_name(self):
        """R-AGT-49 — the old spelling is migration evidence only after Rundesk's owned
        source was retired; an owner skill that still stands keeps its grant."""
        owner_skill = a_skill(self.library, "writing-rundesk-skills", says="owner words")
        skill.grant(self.agents.skills("ava"), "writing-rundesk-skills")

        self.agents.require_skills("ava")

        self.assertTrue(owner_skill.is_dir())
        self.assertIn("writing-rundesk-skills", skill.granted(self.agents.skills("ava")))

    def test_a_new_name_collision_keeps_the_old_working_grant(self):
        """R-AGT-49 — an owner entry in the agent's skill directory cannot be treated as
        a successful replacement for Rundesk's old grant."""
        shutil.rmtree(self.release / "writing-skills")
        a_skill(self.release, "writing-rundesk-skills")
        skill.lay_down(self.library)
        skill.grant(self.agents.skills("ava"), "writing-rundesk-skills")
        a_skill(self.release, "writing-skills")
        skill.lay_down(self.library, force=True)
        owner_entry = a_skill(self.agents.skills("ava"), "writing-skills", says="owner words")

        self.agents.require_skills("ava")
        self.agents.retire_renamed_skills()

        self.assertTrue(owner_entry.is_dir())
        self.assertIn("writing-rundesk-skills", skill.granted(self.agents.skills("ava")))
        self.assertTrue((self.library / "writing-rundesk-skills").is_dir())

    def test_a_failed_replacement_grant_keeps_the_old_package_for_retry(self):
        """R-AGT-49 — failure to create the new link cannot strand the old grant."""
        shutil.rmtree(self.release / "writing-skills")
        a_skill(self.release, "writing-rundesk-skills")
        skill.lay_down(self.library)
        skill.grant(self.agents.skills("ava"), "writing-rundesk-skills")
        a_skill(self.release, "writing-skills")
        skill.lay_down(self.library, force=True)
        real = skill.grant
        skill.grant = lambda *args, **kwargs: (_ for _ in ()).throw(OSError("read only"))
        self.addCleanup(setattr, skill, "grant", real)

        self.agents.require_skills("ava")
        self.agents.retire_renamed_skills()

        self.assertIn("writing-rundesk-skills", skill.granted(self.agents.skills("ava")))
        self.assertTrue((self.library / "writing-rundesk-skills").is_dir())

    def test_an_owner_replacement_collision_preserves_config_grant_and_package(self):
        """R-UPD-48, R-AGT-49 — the full upgrade boundary: an owner package under the
        new spelling prevents configuration, grants, and the old package from moving."""
        shutil.rmtree(self.release / "writing-skills")
        shutil.rmtree(self.library / "writing-skills")
        old = a_skill(self.release, "writing-rundesk-skills")
        skill.lay_down(self.library)
        skill.grant(self.agents.skills("ava"), "writing-rundesk-skills")
        (self.where / "data" / "config.json").write_text(
            '{"skills": {"granted": ["writing-rundesk-skills"]}}\n', encoding="utf-8")
        a_skill(self.release, "writing-skills")
        a_skill(self.library, "writing-skills", says="owner replacement")

        skill.lay_down(self.library, force=True)
        self.agents.reconcile_skill_config()
        self.agents.require_skills("ava")
        self.agents.retire_renamed_skills()

        configured = config.skills(self.where / "data")["granted"]
        self.assertIn("writing-rundesk-skills", configured)
        self.assertIn("writing-rundesk-skills", skill.granted(self.agents.skills("ava")))
        self.assertTrue((self.library / old.name).is_dir())

    def test_a_required_management_collision_keeps_the_owned_old_capability(self):
        """R-AGT-36, R-AGT-49 — the complete provision order never promotes an owner
        package under a new required name into Rundesk's operating floor."""
        new = "managing-schedules"
        old = "managing-rundesk-schedules"
        shutil.rmtree(self.release / new)
        shutil.rmtree(self.library / new)
        a_skill(self.release, old)
        skill.lay_down(self.library)
        owner = a_skill(self.library, new, says="owner backup process")
        (self.where / "data" / "config.json").write_text(
            json.dumps({"skills": {"granted": [old]}}) + "\n", encoding="utf-8")
        self.agents.add("ava")

        shutil.rmtree(self.release / old)
        a_skill(self.release, new)
        config.ensure(self.where / "data")
        skill.lay_down(self.library, force=True)
        self.agents.reconcile_skill_config()
        self.agents.require_skills("ava")
        self.agents.retire_renamed_skills()

        configured = config.skills(self.where / "data")["granted"]
        granted = skill.granted(self.agents.skills("ava"))
        self.assertIn(old, configured)
        self.assertNotIn(new, configured)
        self.assertIn(old, granted)
        self.assertNotIn(new, granted)
        self.assertIn("owner backup process", (owner / skill.NAMED).read_text())
        self.assertTrue((self.library / old / skill.OWNED).is_file())

    def test_an_agent_is_made_with_the_skills_written_into_a_new_configuration(self):
        """R-AGT-36 — the required set is what an agent needs to work with rundesk
        itself, written where the owner and the command both read it."""
        (self.where / "data" / "config.json").unlink()
        config.ensure(self.where / "data")
        required = config.INITIAL["skills"]["granted"]
        for called in required:
            a_skill(self.release, called)
        skill.lay_down(self.library)

        self.agents.add("ava")

        self.assertEqual(sorted(required), skill.granted(self.agents.skills("ava")))

    def test_an_owner_who_wants_no_optional_skills_still_gets_rundesk_stewardship(self):
        """R-AGT-36 — owner choice begins above the product skill every agent retains."""
        (self.where / "data" / "config.json").write_text(
            '{"skills": {"granted": []}}\n', encoding="utf-8")

        self.agents.add("ava")

        self.assertEqual(sorted(config.RUNDESK_REQUIRED_GRANTS),
                         skill.granted(self.agents.skills("ava")))

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
