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
from rundesk.exits import FAILED, OK
from rundesk.providers import environment
from rundesk.skills import catalogs as skill_catalogs
from rundesk.skills import grants, library
from rundesk.teams import reconcile


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
