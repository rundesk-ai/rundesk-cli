"""Install and update a synthetic team catalog under a disposable Rundesk root."""

import argparse
import json
import os
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
from rundesk.teams import reconcile, restoring
from rundesk.utils import files, locking


class Teams(support.Isolated):
    def setUp(self) -> None:
        super().setUp()
        library.where().mkdir(parents=True)
        self.source = a_team_catalog(self.home / "published")

    def command(self, what: str, *, source: Optional[Path] = None, team: str = "test-team",
                provider: str = "codex", confirm: bool = True,
                update_source: Optional[Path] = None) -> int:
        args = argparse.Namespace(what=what, repository=str(source or self.source), team=team,
                                  provider=provider, confirm=confirm,
                                  source=str(update_source) if update_source else None)
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

    def test_a_failed_install_leaves_no_catalog_and_no_agents_but_keeps_its_dependency(self):
        """A confirmed install is all-or-nothing about the team, and deliberately not about a
        dependency catalog it installed to get there."""
        dependency = a_published_catalog(self.home / "shared", name="shared",
                                         skills=("researching",))
        source = self.dependent_team(dependency)
        declaration = json.loads((source / library.TEAM).read_text())
        declaration["members"].append({
            "name": "piper", "description": "Reviews code and judges release quality.",
            "instructions": "agents/piper/AGENTS.md", "skills": ["test-team/implementing"],
            "delegates_to": [], "self_improve": False,
        })
        written(source / library.TEAM, declaration)
        page = source / "agents/piper/AGENTS.md"
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text("# piper\n\nTeam instructions.\n", encoding="utf-8")
        granting = grants.granted

        def fail_the_second_member(agent, skill, alias=""):
            # forge is granted shared/researching first, so this lands after a member reconciled.
            if agent == "piper":
                raise OSError("synthetic failure reconciling the second member")
            return granting(agent, skill, alias)

        with mock.patch.object(grants, "granted", side_effect=fail_the_second_member):
            code, _out, err = support.run_with(
                ["teams", "install", str(source), "--provider", "codex", "--confirm"])

        self.assertEqual([], directory.known())
        self.assertFalse(directory.where("forge").exists())
        self.assertEqual(["shared"], library.known())
        self.assertEqual([], [one.name for one in library.where().iterdir()
                              if files.staged(one.name)])
        self.assertEqual(FAILED, code)
        self.assertIn("no team was installed", err)
        self.assertIn("dependency catalogs installed: shared", err)

    def test_a_failed_promotion_leaves_the_catalog_it_promoted_as_it_was(self):
        """Promotion is a swap of an installed catalog, so undoing it is putting that one back."""
        with skill_catalogs.brought(str(self.source)) as coming:
            skill_catalogs.installed(coming)
        directory.made("scribe", "codex", "Keeps the owner's own notes.")
        grants.granted("scribe", library.look_up("test-team/reviewing"))
        catalog = json.loads((self.source / library.MANIFEST).read_text())
        catalog["version"] = "2.0.0"
        written(self.source / library.MANIFEST, catalog)
        granting = grants.granted

        def fail_the_second_member(agent, skill, alias=""):
            if agent == "piper":
                raise OSError("synthetic failure reconciling the second member")
            return granting(agent, skill, alias)

        with mock.patch.object(grants, "granted", side_effect=fail_the_second_member):
            code, _out, err = support.run_with(
                ["teams", "install", str(self.source), "--provider", "codex", "--confirm"])

        self.assertEqual(["test-team"], library.known())
        self.assertFalse(library.is_team("test-team"))
        self.assertEqual("1.0.0", library.read("test-team").manifest.version)
        self.assertEqual("test-team/reviewing", grants.holding("scribe", "reviewing").address)
        self.assertEqual(["scribe"], directory.known())
        self.assertFalse(directory.where("forge").exists())
        self.assertEqual(FAILED, code)
        self.assertIn("nothing was installed or changed", err)

    def test_a_failed_install_restore_names_the_state_that_remains_and_a_valid_retry(self):
        dependency = a_published_catalog(self.home / "shared", name="shared",
                                         skills=("researching",))
        source = self.dependent_team(dependency)
        declaration = json.loads((source / library.TEAM).read_text())
        declaration["members"].append({
            "name": "piper", "description": "Reviews code and judges release quality.",
            "instructions": "agents/piper/AGENTS.md", "skills": ["test-team/implementing"],
            "delegates_to": [], "self_improve": False,
        })
        written(source / library.TEAM, declaration)
        page = source / "agents/piper/AGENTS.md"
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text("# piper\n\nTeam instructions.\n", encoding="utf-8")
        granting = grants.granted
        forgetting = directory.forgotten

        def fail_the_second_member(agent, skill, alias=""):
            if agent == "piper":
                raise OSError("synthetic failure reconciling the second member")
            return granting(agent, skill, alias)

        def leave_forge(name):
            if name == "forge":
                raise OSError("synthetic failure removing the first member")
            return forgetting(name)

        with mock.patch.object(grants, "granted", side_effect=fail_the_second_member), \
                mock.patch.object(directory, "forgotten", side_effect=leave_forge):
            code, _out, err = support.run_with(
                ["teams", "install", str(source), "--provider", "codex", "--confirm"])

        self.assertFalse(library.is_team("test-team"))
        self.assertEqual(["forge"], directory.known())
        self.assertEqual(FAILED, code)
        self.assertIn("rundesk agents remove forge --confirm", err)
        self.assertIn(f"rundesk teams install {source} --provider codex --confirm", err)
        self.assertIn("dependency catalogs installed: shared", err)
        self.assertNotIn("rundesk teams update", err)

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

    def test_update_may_change_the_recorded_source_without_deleting_the_team(self):
        self.assertEqual(OK, self.command("install"))
        replacement = a_team_catalog(self.home / "replacement")
        forge = directory.home("forge")
        (forge / "AGENTS.md").write_text("drift", encoding="utf-8")

        code, _out, err = support.run_with([
            "teams", "update", "test-team", "--source", str(replacement),
        ])

        self.assertEqual(FAILED, code)
        self.assertIn(f"source    {self.source} -> {replacement}", err)
        self.assertIn(f"--source {replacement} --confirm", err)
        self.assertEqual(str(self.source), library.read("test-team").provenance.source)
        self.assertEqual("drift", (forge / "AGENTS.md").read_text())

        self.assertEqual(OK, self.command("update", provider=None,
                                          update_source=replacement))

        self.assertTrue(library.is_team("test-team"))
        self.assertEqual(str(replacement), library.read("test-team").provenance.source)
        self.assertEqual((replacement / "agents/forge/AGENTS.md").read_text(),
                         (forge / "AGENTS.md").read_text())
        self.assertEqual(["forge", "piper"], directory.known())

    def test_source_change_fetches_and_reconciles_the_new_catalog(self):
        self.assertEqual(OK, self.command("install"))
        replacement = a_team_catalog(self.home / "replacement", version="2.0.0")
        (replacement / "agents/forge/AGENTS.md").write_text(
            "# forge\n\nReplacement workflow.\n", encoding="utf-8")

        self.assertEqual(OK, self.command("update", provider=None,
                                          update_source=replacement))

        settled = library.read("test-team")
        self.assertEqual("2.0.0", settled.manifest.version)
        self.assertEqual(str(replacement), settled.provenance.source)
        self.assertEqual("# forge\n\nReplacement workflow.\n",
                         (directory.home("forge") / "AGENTS.md").read_text())

    def test_source_change_to_github_does_not_send_the_previous_sources_etag(self):
        self.assertEqual(OK, self.command("install"))
        settled = library.read("test-team")
        library.stated_provenance(settled.at, settled.provenance._replace(etag='W/"old"'))
        replacement = a_team_catalog(self.home / "replacement")
        github = "https://github.com/example/test-team"
        asked = []

        def fetched(source, etag, _working):
            asked.append((source, etag))
            return skill_catalogs.Brought(replacement, 'W/"new"')

        args = argparse.Namespace(what="update", team="test-team", source=github,
                                  provider=None, confirm=True)
        self.assertEqual(OK, cmd_teams(args, fetching=fetched))

        self.assertEqual([(github, "")], asked)
        provenance = library.read("test-team").provenance
        self.assertEqual(github, provenance.source)
        self.assertEqual('W/"new"', provenance.etag)

    def test_source_change_refuses_a_repository_with_another_catalog_name(self):
        self.assertEqual(OK, self.command("install"))
        wrong = a_team_catalog(self.home / "wrong", name="another-team")

        code = self.command("update", provider=None, update_source=wrong)

        self.assertEqual(FAILED, code)
        self.assertEqual(str(self.source), library.read("test-team").provenance.source)
        self.assertEqual("1.0.0", library.read("test-team").manifest.version)

    def test_failed_source_change_restores_the_original_source_and_members(self):
        self.assertEqual(OK, self.command("install"))
        replacement = a_team_catalog(self.home / "replacement", version="2.0.0")
        declaration = json.loads((replacement / library.TEAM).read_text())
        declaration["members"][0]["skills"] = ["reviewing"]
        written(replacement / library.TEAM, declaration)
        forge = directory.home("forge")
        before = (forge / "AGENTS.md").read_bytes()
        granting = grants.granted

        def fail_the_new_grant(agent, skill, alias=""):
            if (agent, skill.name) == ("forge", "reviewing"):
                raise OSError("synthetic failure after the source changed")
            return granting(agent, skill, alias)

        with mock.patch.object(grants, "granted", side_effect=fail_the_new_grant):
            code = self.command("update", provider=None, update_source=replacement)

        settled = library.read("test-team")
        self.assertEqual(FAILED, code)
        self.assertEqual(str(self.source), settled.provenance.source)
        self.assertEqual("1.0.0", settled.manifest.version)
        self.assertEqual(before, (forge / "AGENTS.md").read_bytes())
        self.assertEqual("test-team/implementing",
                         grants.holding("forge", "implementing").address)

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

    def test_a_failure_part_way_through_an_update_puts_the_team_and_its_members_back(self):
        self.assertEqual(OK, self.command("install"))
        forge, piper = directory.home("forge"), directory.home("piper")
        manifest = json.loads((self.source / library.TEAM).read_text())
        manifest["members"][0].update({"skills": ["reviewing"],
                                       "description": "Implements the second workflow."})
        written(self.source / library.TEAM, manifest)
        (self.source / "agents/forge/AGENTS.md").write_text(
            "# forge\n\nSecond canonical workflow.\n", encoding="utf-8")
        catalog = json.loads((self.source / library.MANIFEST).read_text())
        catalog["version"] = "2.0.0"
        written(self.source / library.MANIFEST, catalog)
        (forge / "MEMORY.md").write_text("forge remembers this", encoding="utf-8")
        before = {
            "forge_agents": (forge / "AGENTS.md").read_bytes(),
            "forge_claude": (forge / "CLAUDE.md").read_bytes(),
            "piper_agents": (piper / "AGENTS.md").read_bytes(),
            "forge_records": records.read(directory.records("forge")),
        }
        granting = grants.granted

        def fail_the_new_grant(agent, skill, alias=""):
            # The second version moves forge from `implementing` to `reviewing`. Failing that one
            # grant lands the failure after its pages, records and old grant have already moved,
            # and leaves every other grant — including the ones putting it back — working.
            if (agent, skill.name) == ("forge", "reviewing"):
                raise OSError("synthetic mid-reconciliation failure")
            return granting(agent, skill, alias)

        with mock.patch.object(grants, "granted", side_effect=fail_the_new_grant):
            code, _out, err = support.run_with(["teams", "update", "test-team", "--confirm"])

        self.assertEqual(FAILED, code)
        self.assertIn("test-team was not fully reconciled", err)
        self.assertEqual("1.0.0", library.read("test-team").manifest.version)
        self.assertEqual(before["forge_agents"], (forge / "AGENTS.md").read_bytes())
        self.assertEqual(before["forge_claude"], (forge / "CLAUDE.md").read_bytes())
        self.assertEqual(before["piper_agents"], (piper / "AGENTS.md").read_bytes())
        self.assertEqual("forge remembers this", (forge / "MEMORY.md").read_text())
        self.assertEqual(before["forge_records"], records.read(directory.records("forge")))
        self.assertEqual(("piper",), delegating.scope_of("forge"))
        self.assertEqual("test-team/implementing", grants.holding("forge", "implementing").address)
        self.assertIsNone(grants.holding("forge", "reviewing"))

    def test_a_member_created_before_the_failure_is_not_an_agent_afterwards(self):
        self.assertEqual(OK, self.command("install"))
        manifest = json.loads((self.source / library.TEAM).read_text())
        # First in the declaration, so it is created and reconciled before the member that fails.
        manifest["members"].insert(0, {
            "name": "scribe", "description": "Joined by the second version.",
            "instructions": "agents/scribe/AGENTS.md", "skills": ["implementing"],
            "delegates_to": [], "self_improve": False,
        })
        # piper moves to a skill it does not hold, so the member after scribe asks for a grant.
        manifest["members"][2]["skills"] = ["implementing"]
        written(self.source / library.TEAM, manifest)
        page = self.source / "agents/scribe/AGENTS.md"
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text("# scribe\n\nTeam instructions.\n", encoding="utf-8")
        catalog = json.loads((self.source / library.MANIFEST).read_text())
        catalog["version"] = "2.0.0"
        written(self.source / library.MANIFEST, catalog)
        piper = directory.home("piper")
        before_piper = (piper / "AGENTS.md").read_bytes()
        granting = grants.granted

        def fail_after_scribe_is_made(agent, skill, alias=""):
            # Only the grant the new version makes, so the ones putting piper back still work.
            if (agent, skill.name) == ("piper", "implementing"):
                raise OSError("synthetic failure after a member was created")
            return granting(agent, skill, alias)

        with mock.patch.object(grants, "granted", side_effect=fail_after_scribe_is_made):
            code, _out, err = support.run_with(
                ["teams", "update", "test-team", "--provider", "codex", "--confirm"])

        self.assertEqual(FAILED, code)
        self.assertIn("test-team was not fully reconciled", err)
        self.assertEqual(["forge", "piper"], directory.known())
        self.assertFalse(directory.where("scribe").exists())
        self.assertEqual("1.0.0", library.read("test-team").manifest.version)
        self.assertEqual(before_piper, (piper / "AGENTS.md").read_bytes())
        self.assertEqual("test-team/reviewing", grants.holding("piper", "reviewing").address)
        self.assertEqual("test-team/implementing", grants.holding("forge", "implementing").address)

    def test_a_members_symlinked_page_goes_back_as_that_symlink(self):
        self.assertEqual(OK, self.command("install"))
        forge = directory.home("forge")
        elsewhere = self.home / "forge-notes.md"
        elsewhere.write_text("what the owner keeps here", encoding="utf-8")
        (forge / "MEMORY.md").symlink_to(elsewhere)
        manifest = json.loads((self.source / library.TEAM).read_text())
        manifest["members"][0]["skills"] = ["reviewing"]
        written(self.source / library.TEAM, manifest)
        catalog = json.loads((self.source / library.MANIFEST).read_text())
        catalog["version"] = "2.0.0"
        written(self.source / library.MANIFEST, catalog)
        granting = grants.granted

        def fail_the_new_grant(agent, skill, alias=""):
            if (agent, skill.name) == ("forge", "reviewing"):
                raise OSError("synthetic mid-reconciliation failure")
            return granting(agent, skill, alias)

        with mock.patch.object(grants, "granted", side_effect=fail_the_new_grant):
            self.assertEqual(FAILED, support.run_with(
                ["teams", "update", "test-team", "--confirm"])[0])

        memory = forge / "MEMORY.md"
        self.assertTrue(memory.is_symlink())
        self.assertEqual(str(elsewhere), os.readlink(memory))
        self.assertEqual("what the owner keeps here", elsewhere.read_text())

    def test_a_directory_where_a_managed_page_belongs_refuses_before_anything_moves(self):
        """A page path this could not put back is refused, not held as absent and then removed.

        Without the refusal the update gets as far as `pages.replace_team`, whose rename onto a
        directory fails, and the restore then puts the page back by removing what is there — which
        for a directory is everything inside it.
        """
        self.assertEqual(OK, self.command("install"))
        forge = directory.home("forge")
        notes = forge / "AGENTS.md"
        files.remove_one(notes)
        notes.mkdir()
        (notes / "kept.md").write_text("what the owner keeps here", encoding="utf-8")
        manifest = json.loads((self.source / library.TEAM).read_text())
        manifest["members"][0]["skills"] = ["reviewing"]
        written(self.source / library.TEAM, manifest)
        catalog = json.loads((self.source / library.MANIFEST).read_text())
        catalog["version"] = "2.0.0"
        written(self.source / library.MANIFEST, catalog)
        piper_page = (directory.home("piper") / "AGENTS.md").read_bytes()

        code, _out, err = support.run_with(["teams", "update", "test-team", "--confirm"])

        # State first: what this guard exists to protect is the directory, not the wording.
        self.assertTrue(notes.is_dir())
        self.assertEqual(["kept.md"], [one.name for one in notes.iterdir()])
        self.assertEqual("what the owner keeps here", (notes / "kept.md").read_text())
        self.assertEqual("1.0.0", library.read("test-team").manifest.version)
        self.assertEqual(piper_page, (directory.home("piper") / "AGENTS.md").read_bytes())
        self.assertEqual("test-team/implementing", grants.holding("forge", "implementing").address)
        self.assertIsNone(grants.holding("forge", "reviewing"))
        self.assertEqual(["forge", "piper"], directory.known())
        # The explicit command moves no gateway, and a refusal leaves nothing for one to have left.
        self.assertFalse(directory.gateway_record("forge").exists())
        self.assertEqual(FAILED, code)
        self.assertIn("neither a file nor a link", err)

    def test_the_hold_itself_refuses_a_page_it_could_not_put_back(self):
        """`preflight_update` asks the page rule first; `kept` asks it again under the install lock.

        No lifecycle case can make the two answers differ, because the lock is exactly what holds
        these paths still between them — so the second one is asked of `kept` directly. It is the
        boundary the restore depends on: whatever `kept` accepted is what it will try to put back.
        """
        self.assertEqual(OK, self.command("install"))
        notes = directory.home("forge") / "AGENTS.md"
        files.remove_one(notes)
        notes.mkdir()

        with self.assertRaises(restoring.Refused) as refused:
            with restoring.kept("test-team", ["forge"]):
                self.fail("the hold should have refused before the block ran")

        self.assertIn("neither a file nor a link", str(refused.exception))
        self.assertTrue(notes.is_dir())
        # The held copy goes even when the hold refuses while taking it.
        self.assertEqual([], [one.name for one in library.where().iterdir()
                              if files.staged(one.name)])

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
