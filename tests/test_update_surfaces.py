"""Reconcile application, ordinary catalogs, and team catalogs through one update lifecycle."""

import argparse
import contextlib
import datetime
import io
import json
import os
import unittest
from pathlib import Path
from typing import List, Optional
from unittest import mock

from fixtures_skills import a_published_catalog, a_team_catalog, written

import support
from rundesk import __version__
from rundesk.agents import delegating, directory, records
from rundesk.commands import automatic_updates, teams, update
from rundesk.core import config, paths
from rundesk.exits import OK
from rundesk.gateways import standing
from rundesk.lifecycle import migration
from rundesk.providers import turns
from rundesk.skills import catalogs, grants, library
from rundesk.utils import locking


class CatalogFetcher:
    """Return the local catalog source named by each installed provenance record."""

    def __init__(self, depended: Path) -> None:
        self.depended = depended

    def __call__(self, source: str, _etag: str,
                 _into: Path) -> Optional[catalogs.Brought]:
        at = Path(source)
        if source == catalogs.DEPENDED_SOURCE:
            at = self.depended
        elif not at.is_dir():
            raise OSError(f"{source} is unavailable")
        return catalogs.Brought(at, "")


class GatewayCycle:
    """Record which member gateways the lifecycle stands down and restores."""

    def __init__(self, failing_down: str = "") -> None:
        self.failing_down = failing_down
        self.went_down: List[str] = []
        self.came_up: List[str] = []
        self.transition_lock_during_up: List[Optional[bool]] = []

    def down(self, name: str) -> str:
        self.went_down.append(name)
        return "supervisor refused" if name == self.failing_down else ""

    def up(self, name: str) -> str:
        self.came_up.append(name)
        self.transition_lock_during_up.append(
            locking.is_held(paths.gateway_transition_lock()))
        return ""


class UpdateSurfaces(support.Isolated):
    def setUp(self) -> None:
        super().setUp()
        self.root = self.home / "install"
        os.environ[paths.HOME_IS] = str(self.root)
        support.a_real_tree(paths.app(), "installed")
        paths.data().mkdir(parents=True, exist_ok=True)
        config.write_fresh(paths.data())
        migration.stamp_without_running(paths.data())

        self.sources = self.home / "published"
        self.depended = a_published_catalog(
            self.sources / "depended", name=library.DEPENDED, skills=("general-skill",))
        self.ordinary = a_published_catalog(
            self.sources / "ordinary", name="ordinary", skills=("ordinary-skill",))
        self.team = a_team_catalog(self.sources / "team")
        with catalogs.brought(str(self.ordinary)) as coming:
            catalogs.installed(coming)
        args = argparse.Namespace(
            what="install", repository=str(self.team), team="test-team",
            provider="codex", confirm=True)
        self.assertEqual(OK, teams.cmd_teams(args))
        self.fetching = CatalogFetcher(self.depended)
        automatic_updates.reconcile(support.ASupervisor(), self.home / "LaunchAgents")

    def run_manual(self, gateways: GatewayCycle):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), \
                mock.patch.object(update, "settled_by_the_new_release", return_value=""):
            code = update.cmd_update(
                argparse.Namespace(continuation=False),
                asking=lambda: (f"v{__version__}", None),
                refreshing=self.fetching, gateways=gateways)
        return code, out.getvalue(), err.getvalue()

    def publish_second_versions(self) -> None:
        a_published_catalog(
            self.ordinary, name="ordinary", version="2.0.0",
            skills=("ordinary-skill", "second-skill"))
        declaration = json.loads((self.team / library.TEAM).read_text())
        declaration["members"][0].update({
            "description": "Implements the second canonical workflow.",
            "skills": ["reviewing"],
            "delegates_to": [],
            "self_improve": False,
        })
        written(self.team / library.TEAM, declaration)
        written(self.team / library.MANIFEST, {
            "schema": library.SCHEMA, "name": "test-team", "version": "2.0.0",
            "description": "Skills for test-team.",
        })
        (self.team / "agents/forge/AGENTS.md").write_text(
            "# forge\n\nSecond canonical workflow.\n", encoding="utf-8")

    def declare_shared_dependency(self, shared: Path) -> None:
        """Republish the team as schema 2, taking one member skill from a shared catalog."""
        declaration = json.loads((self.team / library.TEAM).read_text())
        declaration["schema"] = 2
        declaration["catalogs"] = [{"name": "shared", "source": str(shared)}]
        declaration["members"][0]["skills"] = ["shared/researching"]
        declaration["members"][1]["skills"] = ["test-team/reviewing"]
        written(self.team / library.TEAM, declaration)

    def an_unmanaged_agent(self, name: str) -> Path:
        """An agent the owner made, which no installed team declares."""
        directory.made(name, "codex", "Keeps the owner's own notes.")
        at = directory.home(name)
        at.mkdir(parents=True, exist_ok=True)
        (at / "AGENTS.md").write_text(f"# {name}\n\nThe owner wrote this.\n", encoding="utf-8")
        (at / "CLAUDE.md").write_text(f"# {name}\n\nAnd this.\n", encoding="utf-8")
        (at / "MEMORY.md").write_text("what it remembers", encoding="utf-8")
        grants.granted(name, library.look_up("ordinary/ordinary-skill"))
        return at

    def test_manual_current_application_reconciles_both_catalog_surfaces_and_gateway_state(self):
        self.publish_second_versions()
        forge_home = directory.home("forge")
        (forge_home / "AGENTS.md").write_text("drift", encoding="utf-8")
        (forge_home / "CLAUDE.md").write_text("other drift", encoding="utf-8")
        (forge_home / "MEMORY.md").write_text("drift", encoding="utf-8")
        (forge_home / "owner-notes.md").write_text("keep me", encoding="utf-8")
        records.stated(directory.records("forge"), {
            "describes": "drift", "delegates_to": delegating.encoded(("piper",)),
            "self_improve": 1,
        })
        gateways = GatewayCycle()

        with standing.holding(directory.where("forge")):
            code, out, err = self.run_manual(gateways)

        self.assertEqual(OK, code, err)
        self.assertIn("application:", out)
        self.assertIn("ordinary catalogs:", out)
        self.assertIn("team catalogs:", out)
        self.assertEqual("2.0.0", library.read("ordinary").manifest.version)
        self.assertEqual("2.0.0", library.read("test-team").manifest.version)
        self.assertEqual("# forge\n\nSecond canonical workflow.\n",
                         (forge_home / "AGENTS.md").read_text())
        self.assertEqual((forge_home / "AGENTS.md").read_bytes(),
                         (forge_home / "CLAUDE.md").read_bytes())
        self.assertFalse((forge_home / "MEMORY.md").exists())
        self.assertEqual("keep me", (forge_home / "owner-notes.md").read_text())
        settled = records.read(directory.records("forge"))
        self.assertEqual("Implements the second canonical workflow.", settled["describes"])
        self.assertEqual((), delegating.scope_of("forge"))
        self.assertEqual(0, settled["self_improve"])
        self.assertIsNone(grants.holding("forge", "implementing"))
        self.assertEqual("test-team/reviewing", grants.holding("forge", "reviewing").address)
        self.assertEqual(["forge"], gateways.went_down)
        self.assertEqual(["forge"], gateways.came_up)
        self.assertEqual([False], gateways.transition_lock_during_up)

        second_code, second_out, second_err = self.run_manual(GatewayCycle())
        self.assertEqual(OK, second_code, second_err)
        self.assertIn("team catalogs:", second_out)
        self.assertEqual("2.0.0", library.read("test-team").manifest.version)

    def test_failed_member_stop_restores_prior_gateways_after_releasing_transition_lock(self):
        self.publish_second_versions()
        gateways = GatewayCycle(failing_down="piper")

        with standing.holding(directory.where("forge")), \
                standing.holding(directory.where("piper")):
            code, _out, err = self.run_manual(gateways)

        self.assertEqual(OK, code, err)
        self.assertIn("team catalogs: completed with failures", err)
        self.assertIn("the gateway for piper would not stand down", err)
        self.assertEqual("1.0.0", library.read("test-team").manifest.version)
        self.assertEqual(["forge", "piper"], gateways.went_down)
        self.assertEqual(["forge"], gateways.came_up)
        self.assertEqual([False], gateways.transition_lock_during_up)

    def test_active_work_defers_every_surface_then_the_quiet_retry_completes(self):
        self.publish_second_versions()
        with turns.claiming("forge", 17), \
                mock.patch.object(automatic_updates, "queued", return_value="queued — busy"):
            code, out, err = self.run_manual(GatewayCycle())

        self.assertEqual(OK, code, err)
        self.assertIn("queued — busy", out)
        self.assertEqual("1.0.0", library.read("ordinary").manifest.version)
        self.assertEqual("1.0.0", library.read("test-team").manifest.version)

        retry_code, _retry_out, retry_err = self.run_manual(GatewayCycle())
        self.assertEqual(OK, retry_code, retry_err)
        self.assertEqual("2.0.0", library.read("ordinary").manifest.version)
        self.assertEqual("2.0.0", library.read("test-team").manifest.version)

    def test_invalid_team_preserves_last_working_state_while_ordinary_catalog_settles(self):
        second_members = [{
            "name": "amber", "description": "Triages the first workflow.",
            "instructions": "agents/amber/AGENTS.md", "skills": ["triaging"],
            "delegates_to": [], "self_improve": False,
        }]
        second_team = a_team_catalog(
            self.sources / "second-team", name="second-team", members=second_members,
            skills=("triaging",))
        install_second = argparse.Namespace(
            what="install", repository=str(second_team), team="second-team",
            provider="codex", confirm=True)
        self.assertEqual(OK, teams.cmd_teams(install_second))
        self.publish_second_versions()
        second_members[0]["description"] = "Triages the second workflow."
        a_team_catalog(
            second_team, name="second-team", version="2.0.0", members=second_members,
            skills=("triaging",))
        declaration = json.loads((self.team / library.TEAM).read_text())
        declaration["members"][0]["instructions"] = "../outside/AGENTS.md"
        written(self.team / library.TEAM, declaration)
        before_page = (directory.home("forge") / "AGENTS.md").read_bytes()
        gateways = GatewayCycle()

        code, out, err = self.run_manual(gateways)

        self.assertEqual(OK, code, err)
        self.assertEqual("2.0.0", library.read("ordinary").manifest.version)
        self.assertEqual("1.0.0", library.read("test-team").manifest.version)
        self.assertEqual("2.0.0", library.read("second-team").manifest.version)
        self.assertEqual(before_page, (directory.home("forge") / "AGENTS.md").read_bytes())
        self.assertEqual("Triages the second workflow.",
                         records.read(directory.records("amber"))["describes"])
        self.assertIn("ordinary catalogs:", out)
        self.assertIn("team catalogs: completed with failures", err)
        self.assertIn("test-team could not be checked", err)
        self.assertEqual(([], []), (gateways.went_down, gateways.came_up))

    def test_daily_coordinator_uses_the_same_surfaces_and_logs_each_outcome(self):
        self.publish_second_versions()
        gateways = GatewayCycle()
        out, err = io.StringIO(), io.StringIO()
        now = datetime.datetime(2026, 8, 24, 3, 0).astimezone()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), \
                mock.patch.object(automatic_updates, "_busy_reason", return_value=""), \
                mock.patch.object(update, "settled_by_the_new_release", return_value=""):
            code = automatic_updates.run(
                now, asking=lambda: (f"v{__version__}", None),
                refreshing=self.fetching, gateways=gateways)

        self.assertEqual(OK, code, err.getvalue())
        self.assertEqual("2.0.0", library.read("ordinary").manifest.version)
        self.assertEqual("2.0.0", library.read("test-team").manifest.version)
        log_text = "\n".join(
            one.read_text(encoding="utf-8")
            for one in automatic_updates.logs_at(
                automatic_updates.coordinator()).glob("*.log"))
        for surface in ("application:", "ordinary catalogs:", "team catalogs:"):
            self.assertIn(surface, log_text)

        forge_home = directory.home("forge")
        (forge_home / "AGENTS.md").write_text("daily drift", encoding="utf-8")
        second = automatic_updates.run(
            now + datetime.timedelta(days=1), asking=lambda: (f"v{__version__}", None),
            refreshing=self.fetching, gateways=GatewayCycle())
        self.assertEqual(OK, second)
        self.assertEqual("# forge\n\nSecond canonical workflow.\n",
                         (forge_home / "AGENTS.md").read_text())

    def test_a_declared_name_held_by_an_unmanaged_agent_is_refused_and_left_untouched(self):
        scribe = self.an_unmanaged_agent("scribe")
        self.publish_second_versions()
        declaration = json.loads((self.team / library.TEAM).read_text())
        declaration["members"].append({
            "name": "scribe", "description": "Would be governed by this team.",
            "instructions": "agents/scribe/AGENTS.md", "skills": [],
            "delegates_to": [], "self_improve": True,
        })
        written(self.team / library.TEAM, declaration)
        page = self.team / "agents/scribe/AGENTS.md"
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text("# scribe\n\nTeam instructions.\n", encoding="utf-8")
        gateways = GatewayCycle()

        with standing.holding(directory.where("forge")):
            code, _out, err = self.run_manual(gateways)

        self.assertEqual(OK, code, err)
        self.assertEqual("# scribe\n\nThe owner wrote this.\n", (scribe / "AGENTS.md").read_text())
        self.assertEqual("# scribe\n\nAnd this.\n", (scribe / "CLAUDE.md").read_text())
        self.assertEqual("what it remembers", (scribe / "MEMORY.md").read_text())
        self.assertEqual("Keeps the owner's own notes.",
                         records.read(directory.records("scribe"))["describes"])
        self.assertEqual("ordinary/ordinary-skill",
                         grants.holding("scribe", "ordinary-skill").address)
        self.assertEqual("1.0.0", library.read("test-team").manifest.version)
        self.assertIn("team catalogs: completed with failures", err)
        self.assertIn("rundesk agents remove scribe --confirm", err)
        self.assertEqual("test-team/implementing",
                         grants.holding("forge", "implementing").address)
        self.assertEqual(([], []), (gateways.went_down, gateways.came_up))
        self.assertEqual("2.0.0", library.read("ordinary").manifest.version)

    def test_a_team_update_installs_a_missing_shared_catalog_before_granting_its_skill(self):
        shared = a_published_catalog(
            self.sources / "shared", name="shared", skills=("researching",))
        self.publish_second_versions()
        self.declare_shared_dependency(shared)
        gateways = GatewayCycle()

        with standing.holding(directory.where("forge")):
            code, out, err = self.run_manual(gateways)

        self.assertEqual(OK, code, err)
        self.assertIn("team catalogs: checked", out)
        self.assertEqual("2.0.0", library.read("test-team").manifest.version)
        self.assertIn("shared", library.known())
        self.assertEqual(str(shared), library.read("shared").provenance.source)
        self.assertEqual("shared/researching", grants.holding("forge", "researching").address)
        self.assertIsNone(grants.holding("forge", "implementing"))
        self.assertEqual("test-team/reviewing", grants.holding("piper", "reviewing").address)
        self.assertEqual(["forge"], gateways.went_down)
        self.assertEqual(["forge"], gateways.came_up)

    def test_a_dependency_missing_a_required_skill_preserves_the_team_and_its_members(self):
        shared = a_published_catalog(
            self.sources / "shared", name="shared", skills=("something-else",))
        self.publish_second_versions()
        self.declare_shared_dependency(shared)
        before_page = (directory.home("forge") / "AGENTS.md").read_bytes()
        gateways = GatewayCycle()

        with standing.holding(directory.where("forge")):
            code, _out, err = self.run_manual(gateways)

        self.assertEqual(OK, code, err)
        self.assertIn("team catalogs: completed with failures", err)
        self.assertIn("does not hold required skills: researching", err)
        self.assertEqual("1.0.0", library.read("test-team").manifest.version)
        self.assertNotIn("shared", library.known())
        self.assertEqual(before_page, (directory.home("forge") / "AGENTS.md").read_bytes())
        self.assertEqual("test-team/implementing",
                         grants.holding("forge", "implementing").address)
        # Nothing stood down, so the dependency was proved before the members were touched.
        self.assertEqual(([], []), (gateways.went_down, gateways.came_up))
        self.assertEqual("2.0.0", library.read("ordinary").manifest.version)


if __name__ == "__main__":
    unittest.main()
