"""Install and update a synthetic team catalog under a disposable Rundesk root."""

import argparse
import json
import unittest
from pathlib import Path
from typing import Optional
from unittest import mock

from fixtures_skills import a_published_catalog, a_team_catalog, written

import support
from rundesk.agents import delegating, directory, records
from rundesk.commands.teams import cmd_teams
from rundesk.core import paths
from rundesk.exits import FAILED, OK
from rundesk.providers import environment
from rundesk.skills import catalogs as skill_catalogs
from rundesk.skills import grants, library
from rundesk.teams import reconcile
from rundesk.utils import locking


class Teams(support.Isolated):
    def setUp(self) -> None:
        super().setUp()
        library.where().mkdir(parents=True)
        self.source = a_team_catalog(self.home / "published")

    def command(self, what: str, *, source: Optional[Path] = None, team: str = "test-team",
                provider: str = "codex", confirm: bool = True) -> int:
        args = argparse.Namespace(what=what, repository=str(source or self.source), team=team,
                                  provider=provider, confirm=confirm)
        return cmd_teams(args)

    def dependent_team(self, dependency: Path, dependency_name: str = "shared",
                       skill: str = "researching") -> Path:
        source = a_team_catalog(self.home / "dependent-team", members=[{
            "name": "forge", "description": "Implements bounded software changes.",
            "instructions": "agents/forge/AGENTS.md",
            "skills": [f"{dependency_name}/{skill}"], "delegates_to": [],
            "self_improve": False,
        }], skills=("implementing",))
        manifest = json.loads((source / library.TEAM).read_text())
        manifest["schema"] = 2
        manifest["catalogs"] = [{"name": dependency_name, "source": str(dependency)}]
        written(source / library.TEAM, manifest)
        return source

    def test_schema_two_installs_a_missing_shared_catalog_and_grants_its_skill(self):
        dependency = a_published_catalog(self.home / "shared", name="shared",
                                         skills=("researching",))
        source = self.dependent_team(dependency)
        code, _out, err = support.run_with(
            ["teams", "install", str(source), "--provider", "codex"])
        self.assertEqual(FAILED, code)
        self.assertIn("shared — install from", err)
        self.assertEqual([], library.known())

        self.assertEqual(OK, self.command("install", source=source))
        self.assertEqual(["shared", "test-team"], library.known())
        self.assertEqual("shared/researching", grants.holding("forge", "researching").address)

    def test_schema_two_reuses_a_matching_installed_catalog(self):
        dependency = a_published_catalog(self.home / "shared", name="shared",
                                         skills=("researching",))
        with skill_catalogs.brought(str(dependency)) as coming:
            skill_catalogs.installed(coming)
        source = self.dependent_team(dependency)
        code, _out, err = support.run_with(
            ["teams", "install", str(source), "--provider", "codex"])
        self.assertEqual(FAILED, code)
        self.assertIn("shared — reuse installed", err)
        self.assertEqual(OK, self.command("install", source=source))

    def test_schema_two_refuses_a_same_named_catalog_from_another_source(self):
        installed_source = a_published_catalog(self.home / "first", name="shared",
                                               skills=("researching",))
        declared_source = a_published_catalog(self.home / "second", name="shared",
                                              skills=("researching",))
        with skill_catalogs.brought(str(installed_source)) as coming:
            skill_catalogs.installed(coming)
        source = self.dependent_team(declared_source)
        code, _out, err = support.run_with(
            ["teams", "install", str(source), "--provider", "codex", "--confirm"])
        self.assertEqual(FAILED, code)
        self.assertIn("not " + str(declared_source), err)
        self.assertNotIn("test-team", library.known())

    def test_schema_two_refuses_a_dependency_missing_a_required_skill(self):
        dependency = a_published_catalog(self.home / "shared", name="shared",
                                         skills=("something-else",))
        source = self.dependent_team(dependency)
        code, _out, err = support.run_with(
            ["teams", "install", str(source), "--provider", "codex", "--confirm"])
        self.assertEqual(FAILED, code)
        self.assertIn("does not hold required skills: researching", err)
        self.assertEqual([], library.known())

    def test_a_failure_after_dependency_install_reports_the_partial_safe_result(self):
        dependency = a_published_catalog(self.home / "shared", name="shared",
                                         skills=("researching",))
        source = self.dependent_team(dependency)
        installing = skill_catalogs.installed

        def fail_team(coming, *args, **kwargs):
            if coming.manifest.name == "test-team":
                raise OSError("synthetic team write failure")
            return installing(coming, *args, **kwargs)

        with mock.patch("rundesk.commands.teams.skill_catalogs.installed",
                        side_effect=fail_team):
            code, _out, err = support.run_with(
                ["teams", "install", str(source), "--provider", "codex", "--confirm"])
        self.assertEqual(FAILED, code)
        self.assertIn("dependency catalogs installed: shared", err)
        self.assertIn("retry the same confirmed team install", err)
        self.assertEqual(["shared"], library.known())

    def test_an_installed_team_protects_its_dependency_from_removal_and_retirement(self):
        dependency = a_published_catalog(self.home / "shared", name="shared",
                                         skills=("researching", "other"))
        source = self.dependent_team(dependency)
        self.assertEqual(OK, self.command("install", source=source))

        code, _out, err = support.run_with(["skills", "remove", "shared", "--confirm"])
        self.assertEqual(FAILED, code)
        self.assertIn("required by installed teams: test-team", err)

        a_published_catalog(dependency, name="shared", version="2.0.0", skills=("other",))
        code, _out, err = support.run_with(["skills", "update", "shared", "--confirm"])
        self.assertEqual(FAILED, code)
        self.assertIn("test-team: researching", err)
        self.assertIn("researching", library.found(library.inside("shared")))

    def test_preview_changes_nothing_and_names_member_effects(self):
        code, out, err = support.run_with(
            ["teams", "install", str(self.source), "--provider", "codex"])
        self.assertEqual(FAILED, code)
        self.assertEqual([], directory.known())
        self.assertEqual([], library.known())
        self.assertIn("replace AGENTS.md and CLAUDE.md; remove MEMORY.md", err)
        self.assertIn("weekly upkeep off", err)
        self.assertIn("leave gateway stopped", err)
        self.assertEqual("", out)

    def test_confirm_creates_and_reconciles_every_member_with_gateways_stopped(self):
        code, out, err = support.run_with(
            ["teams", "install", str(self.source), "--provider", "codex", "--confirm"])
        self.assertEqual(OK, code, err)
        self.assertTrue(library.is_team("test-team"))
        self.assertTrue((library.stands("test-team") / library.TEAM_MARKER).is_file())
        self.assertEqual(["forge", "piper"], directory.known())
        self.assertIn("gateways stopped", out)
        self.assertIn("rundesk gateways start <agent>", out)
        for name, skill in (("forge", "implementing"), ("piper", "reviewing")):
            home = directory.home(name)
            expected = (self.source / "agents" / name / "AGENTS.md").read_text()
            self.assertEqual(expected, (home / "AGENTS.md").read_text())
            self.assertEqual(expected, (home / "CLAUDE.md").read_text())
            self.assertFalse((home / "MEMORY.md").exists())
            self.assertEqual(f"test-team/{skill}", grants.holding(name, skill).address)
        self.assertEqual(1, records.read(directory.records("forge"))["self_improve"])
        self.assertEqual(0, records.read(directory.records("piper"))["self_improve"])
        self.assertEqual(("piper",), delegating.scope_of("forge"))
        self.assertEqual((), delegating.scope_of("piper"))
        self.assertEqual("Implements bounded software changes.",
                         records.read(directory.records("forge"))["describes"])

    def test_install_refuses_an_existing_agent_and_names_its_removal_command(self):
        directory.made("forge", "claude", "An owner description.")
        home = directory.home("forge")
        (home / "AGENTS.md").write_text("owner rules")
        (home / "MEMORY.md").write_text("owner memory")
        code, _out, err = support.run_with(
            ["teams", "install", str(self.source), "--provider", "codex", "--confirm"])
        self.assertEqual(FAILED, code)
        self.assertIn("forge (rundesk agents remove forge --confirm)", err)
        self.assertEqual("claude", records.read(directory.records("forge"))["provider_name"])
        self.assertEqual("owner rules", (home / "AGENTS.md").read_text())
        self.assertEqual("owner memory", (home / "MEMORY.md").read_text())
        self.assertNotIn("test-team", library.known())

    def test_confirm_does_not_repair_or_change_an_unmanaged_agent(self):
        directory.made("spectator", "claude", "An unrelated agent.")
        other = a_published_catalog(self.home / "spectator-skills", name="spectator-skills",
                                    skills=("extra",))
        with skill_catalogs.brought(str(other)) as coming:
            skill_catalogs.installed(coming)
        grants.granted("spectator", library.look_up("spectator-skills/extra"))
        missing_link = directory.home("spectator") / ".codex/skills/extra"
        missing_link.unlink()
        before = records.read(directory.records("spectator"))

        self.assertEqual(OK, self.command("install"))

        self.assertFalse(missing_link.exists())
        self.assertEqual(before, records.read(directory.records("spectator")))
        self.assertEqual("spectator-skills/extra",
                         grants.holding("spectator", "extra").address)

    def test_update_repairs_drift_even_when_the_catalog_tree_is_unchanged(self):
        self.assertEqual(OK, self.command("install"))
        forge = directory.home("forge")
        (forge / "AGENTS.md").write_text("drift")
        (forge / "CLAUDE.md").write_text("different drift")
        (forge / "MEMORY.md").write_text("should not persist")
        grants.revoked("forge", "implementing")
        records.stated(directory.records("forge"), {
            "describes": "drift", "delegates_to": delegating.encoded(()), "self_improve": 0})

        self.assertEqual(OK, self.command("update", provider=None))
        expected = (self.source / "agents/forge/AGENTS.md").read_text()
        self.assertEqual(expected, (forge / "AGENTS.md").read_text())
        self.assertEqual(expected, (forge / "CLAUDE.md").read_text())
        self.assertFalse((forge / "MEMORY.md").exists())
        self.assertEqual("test-team/implementing", grants.holding("forge", "implementing").address)
        self.assertEqual(("piper",), delegating.scope_of("forge"))
        self.assertEqual(1, records.read(directory.records("forge"))["self_improve"])

    def test_update_refuses_to_take_over_an_agent_no_team_manages(self):
        self.assertEqual(OK, self.command("install"))
        directory.made("scribe", "claude", "Keeps the owner's own notes.")
        scribe = directory.home("scribe")
        (scribe / "AGENTS.md").write_text("owner rules")
        (scribe / "CLAUDE.md").write_text("owner rules as well")
        (scribe / "MEMORY.md").write_text("owner memory")
        other = a_published_catalog(self.home / "scribe-skills", name="scribe-skills",
                                    skills=("extra",))
        with skill_catalogs.brought(str(other)) as coming:
            skill_catalogs.installed(coming)
        grants.granted("scribe", library.look_up("scribe-skills/extra"))
        before = records.read(directory.records("scribe"))
        manifest = json.loads((self.source / library.TEAM).read_text())
        manifest["members"].append({
            "name": "scribe", "description": "Would be governed by this team.",
            "instructions": "agents/scribe/AGENTS.md", "skills": [],
            "delegates_to": [], "self_improve": True,
        })
        written(self.source / library.TEAM, manifest)
        page = self.source / "agents/scribe/AGENTS.md"
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text("# scribe\n\nTeam instructions.\n", encoding="utf-8")
        catalog = json.loads((self.source / library.MANIFEST).read_text())
        catalog["version"] = "2.0.0"
        written(self.source / library.MANIFEST, catalog)

        previewed, _preview_out, preview_err = support.run_with(
            ["teams", "update", "test-team"])
        code, _out, err = support.run_with(["teams", "update", "test-team", "--confirm"])

        self.assertEqual("owner rules", (scribe / "AGENTS.md").read_text())
        self.assertEqual("owner rules as well", (scribe / "CLAUDE.md").read_text())
        self.assertEqual("owner memory", (scribe / "MEMORY.md").read_text())
        self.assertEqual(before, records.read(directory.records("scribe")))
        self.assertEqual("scribe-skills/extra", grants.holding("scribe", "extra").address)
        self.assertEqual("1.0.0", library.read("test-team").manifest.version)
        self.assertEqual(["forge", "piper", "scribe"], directory.known())
        self.assertEqual(FAILED, code)
        self.assertIn("scribe (rundesk agents remove scribe --confirm)", err)
        self.assertEqual(FAILED, previewed)
        self.assertIn("rundesk agents remove scribe --confirm", preview_err)
        self.assertNotIn("this would reconcile team", preview_err)

    def test_update_reconciles_members_with_the_install_lock_still_held(self):
        """The window between the catalog swap and `apply` must not exist.

        Once the new declaration is installed, `catalogs.owners()` claims every name in it, so the
        ownership re-check can no longer tell a member this team managed from an agent created a
        moment ago. Only the install lock never being released in between keeps the two apart, so
        this asks the last boundary inside it whether it is still there.
        """
        self.assertEqual(OK, self.command("install"))
        catalog = json.loads((self.source / library.MANIFEST).read_text())
        catalog["version"] = "2.0.0"
        written(self.source / library.MANIFEST, catalog)
        reconciling = reconcile.apply
        held = []

        def watched(*args, **kwargs):
            held.append(locking.is_held(paths.lock()))
            return reconciling(*args, **kwargs)

        with mock.patch.object(reconcile, "apply", watched):
            self.assertEqual(OK, self.command("update", provider=None))

        self.assertEqual([True], held)

    def test_turn_admission_reconciliation_repairs_installed_state_without_fetching(self):
        self.assertEqual(OK, self.command("install"))
        home = directory.home("forge")
        other = a_published_catalog(self.home / "turn-extra", name="turn-extra",
                                    skills=("extra",))
        with skill_catalogs.brought(str(other)) as coming:
            skill_catalogs.installed(coming)
        grants.granted("forge", library.look_up("turn-extra/extra"))
        directory.made("spectator", "claude", "An unrelated agent.")
        grants.granted("spectator", library.look_up("turn-extra/extra"))
        missing_link = directory.home("spectator") / ".codex/skills/extra"
        missing_link.unlink()
        (home / "AGENTS.md").write_text("drift")
        (home / "MEMORY.md").write_text("drift")
        records.stated(directory.records("forge"), {"self_improve": 0})
        grants.revoked("forge", "implementing")
        reconcile.current("forge")
        self.assertEqual((self.source / "agents/forge/AGENTS.md").read_text(),
                         (home / "AGENTS.md").read_text())
        self.assertFalse((home / "MEMORY.md").exists())
        self.assertEqual("test-team/implementing",
                         grants.holding("forge", "implementing").address)
        self.assertEqual(1, records.read(directory.records("forge"))["self_improve"])
        self.assertIsNone(grants.holding("forge", "extra"))
        self.assertFalse(missing_link.exists())
        self.assertEqual("turn-extra/extra", grants.holding("spectator", "extra").address)

    def test_changed_catalog_moves_instructions_skills_and_scope_together(self):
        self.assertEqual(OK, self.command("install"))
        manifest = json.loads((self.source / library.TEAM).read_text())
        manifest["members"][0]["skills"] = ["reviewing"]
        manifest["members"][0]["delegates_to"] = []
        written(self.source / library.TEAM, manifest)
        (self.source / "agents/forge/AGENTS.md").write_text("# forge\n\nVersion two.\n")
        catalog = json.loads((self.source / library.MANIFEST).read_text())
        catalog["version"] = "2.0.0"
        written(self.source / library.MANIFEST, catalog)

        self.assertEqual(OK, self.command("update", provider=None))
        self.assertEqual("# forge\n\nVersion two.\n",
                         (directory.home("forge") / "AGENTS.md").read_text())
        self.assertTrue(library.is_team("test-team"))
        self.assertIsNone(grants.holding("forge", "implementing"))
        self.assertEqual("test-team/reviewing", grants.holding("forge", "reviewing").address)
        self.assertEqual((), delegating.scope_of("forge"))

    def test_update_applies_a_changed_weekly_upkeep_setting(self):
        self.assertEqual(OK, self.command("install"))
        manifest = json.loads((self.source / library.TEAM).read_text())
        manifest["members"][1]["self_improve"] = True
        written(self.source / library.TEAM, manifest)

        self.assertEqual(OK, self.command("update", provider=None))
        self.assertEqual(1, records.read(directory.records("piper"))["self_improve"])

    def test_the_positive_allowed_list_removes_an_unlisted_catalog_grant(self):
        self.assertEqual(OK, self.command("install"))
        other = a_published_catalog(self.home / "other", name="other", skills=("extra",))
        with skill_catalogs.brought(str(other)) as coming:
            skill_catalogs.installed(coming)
        grants.granted("forge", library.look_up("other/extra"))
        self.assertEqual(OK, self.command("update", provider=None))
        self.assertIsNone(grants.holding("forge", "extra"))

    def test_an_empty_allowed_list_removes_every_optional_skill(self):
        self.assertEqual(OK, self.command("install"))
        manifest = json.loads((self.source / library.TEAM).read_text())
        manifest["members"][1]["skills"] = []
        written(self.source / library.TEAM, manifest)
        catalog = json.loads((self.source / library.MANIFEST).read_text())
        catalog["version"] = "2.0.0"
        written(self.source / library.MANIFEST, catalog)
        self.assertEqual(OK, self.command("update", provider=None))
        self.assertIsNone(grants.holding("piper", "reviewing"))

    def test_only_rundesks_exact_conditional_delegation_skill_is_product_protected(self):
        self.assertEqual(OK, self.command("install"))
        other = a_published_catalog(self.home / "other-delegating", name="other-delegating",
                                    skills=(library.DELEGATING_SKILL,))
        with skill_catalogs.brought(str(other)) as coming:
            skill_catalogs.installed(coming)
        grants.granted("piper", library.look_up(
            f"other-delegating/{library.DELEGATING_SKILL}"))
        self.assertEqual(OK, self.command("update", provider=None))
        self.assertIsNone(grants.holding("piper", library.DELEGATING_SKILL))

    def test_a_missing_provider_and_a_second_team_owner_are_refused(self):
        self.assertEqual(FAILED, self.command("install", provider=None))
        self.assertEqual([], directory.known())
        self.assertEqual(OK, self.command("install"))
        second = a_team_catalog(self.home / "second", name="second-team", members=[{
            "name": "forge", "description": "A conflicting owner.",
            "instructions": "agents/forge/AGENTS.md", "skills": ["implementing"],
            "delegates_to": [], "self_improve": True,
        }], skills=("implementing",))
        self.assertEqual(FAILED, self.command("install", source=second, team="second-team"))
        self.assertNotIn("second-team", library.known())

    def test_skill_commands_install_a_team_catalog_without_installing_the_team(self):
        code, _out, err = support.run_with(
            ["skills", "install", str(self.source), "--confirm"])
        self.assertEqual(OK, code, err)
        self.assertIn("test-team", library.known())
        self.assertFalse(library.is_team("test-team"))
        self.assertEqual([], directory.known())

        skill = self.source / "skills/implementing/SKILL.md"
        skill.write_text(skill.read_text() + "\nPromoted version.\n")
        manifest = json.loads((self.source / library.MANIFEST).read_text())
        manifest["version"] = "2.0.0"
        written(self.source / library.MANIFEST, manifest)

        code, _out, err = support.run_with(
            ["teams", "install", str(self.source), "--provider", "codex", "--confirm"])
        self.assertEqual(OK, code, err)
        self.assertTrue(library.is_team("test-team"))
        self.assertEqual(["forge", "piper"], directory.known())
        self.assertEqual(["implementing", "reviewing"],
                         library.found(library.inside("test-team")))
        self.assertIn("Promoted version.",
                      (library.look_up("test-team/implementing").at /
                       library.DECLARED).read_text())

    def test_skill_commands_cannot_move_a_catalog_installed_as_a_team(self):
        self.assertEqual(OK, self.command("install"))
        code, _out, err = support.run_with(["skills", "update", "test-team", "--confirm"])
        self.assertEqual(FAILED, code)
        self.assertIn("teams update", err)
        code, _out, err = support.run_with(["skills", "remove", "test-team", "--confirm"])
        self.assertEqual(FAILED, code)
        self.assertIn("cannot be removed through skills", err)

    def test_an_ordinary_catalog_may_carry_an_unrelated_team_json(self):
        ordinary = a_published_catalog(self.home / "ordinary", name="ordinary")
        written(ordinary / library.TEAM, {"metadata": "belongs to this skill catalog"})
        code, _out, err = support.run_with(
            ["skills", "install", str(ordinary), "--confirm"])
        self.assertEqual(OK, code, err)
        self.assertIn("ordinary", library.known())
        self.assertFalse(library.is_team("ordinary"))
        written(ordinary / library.TEAM, {
            "schema": 1, "name": "ordinary", "members": [],
        })
        code, _out, err = support.run_with(["skills", "update", "ordinary", "--confirm"])
        self.assertEqual(OK, code, err)
        self.assertFalse(library.is_team("ordinary"))

    def test_an_agent_turn_with_command_access_can_apply_a_confirmed_team_catalog(self):
        with mock.patch.dict("os.environ", {environment.AGENT: "forge", environment.RUN: "1"}):
            self.assertEqual(OK, self.command("install"))
        self.assertEqual(["forge", "piper"], directory.known())
        self.assertTrue(library.is_team("test-team"))


if __name__ == "__main__":
    unittest.main()
