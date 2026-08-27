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
from rundesk.utils import files, locking


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

    def a_later_team(self) -> Path:
        """A second installed team whose name sorts after test-team, so it refreshes afterwards."""
        members = [{
            "name": "amber", "description": "Triages the first workflow.",
            "instructions": "agents/amber/AGENTS.md", "skills": ["triaging"],
            "delegates_to": [], "self_improve": False,
        }]
        source = a_team_catalog(self.sources / "zeta-team", name="zeta-team", members=members,
                               skills=("triaging",))
        self.assertEqual(OK, teams.cmd_teams(argparse.Namespace(
            what="install", repository=str(source), team="zeta-team",
            provider="codex", confirm=True)))
        members[0]["description"] = "Triages the second workflow."
        a_team_catalog(source, name="zeta-team", version="2.0.0", members=members,
                       skills=("triaging",))
        return source

    def test_manual_current_application_reconciles_both_catalog_surfaces_and_gateway_state(self):
        self.publish_second_versions()
        forge_home = directory.home("forge")
        (forge_home / "AGENTS.md").write_text("drift", encoding="utf-8")
        (forge_home / "CLAUDE.md").write_text("other drift", encoding="utf-8")
        (forge_home / "MEMORY.md").write_text("drift", encoding="utf-8")
        (forge_home / "owner-notes.md").write_text("keep me", encoding="utf-8")
        grants.granted("forge", library.look_up("ordinary/ordinary-skill"))
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
        self.assertEqual("ordinary/ordinary-skill",
                         grants.holding("forge", "ordinary-skill").address)
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
        grants.granted("forge", library.look_up("ordinary/ordinary-skill"))
        gateways = GatewayCycle()
        out, err = io.StringIO(), io.StringIO()
        now = datetime.datetime(2026, 8, 24, 3, 0).astimezone()
        with standing.holding(directory.where("forge")), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), \
                mock.patch.object(automatic_updates, "_busy_reason", return_value=""), \
                mock.patch.object(update, "settled_by_the_new_release", return_value=""):
            code = automatic_updates.run(
                now, asking=lambda: (f"v{__version__}", None),
                refreshing=self.fetching, gateways=gateways)

        self.assertEqual(OK, code, err.getvalue())
        self.assertEqual("2.0.0", library.read("ordinary").manifest.version)
        self.assertEqual("2.0.0", library.read("test-team").manifest.version)
        self.assertEqual("test-team/reviewing", grants.holding("forge", "reviewing").address)
        self.assertEqual("ordinary/ordinary-skill",
                         grants.holding("forge", "ordinary-skill").address)
        self.assertEqual((["forge"], ["forge"]), (gateways.went_down, gateways.came_up))
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

    def test_an_occupied_grant_name_refuses_one_team_before_a_gateway_moves(self):
        """A member stood down for an update that was never going to finish is an outage nobody
        asked for, so the collision is answered while every gateway is still where it was."""
        collided = a_published_catalog(self.sources / "collided", name="collided",
                                       skills=("implementing",))
        with catalogs.brought(str(collided)) as coming:
            catalogs.installed(coming)
        grants.revoked("forge", "implementing")
        grants.granted("forge", library.look_up("collided/implementing"))
        a_published_catalog(self.ordinary, name="ordinary", version="2.0.0",
                            skills=("ordinary-skill", "second-skill"))
        written(self.team / library.MANIFEST, {
            "schema": library.SCHEMA, "name": "test-team", "version": "2.0.0",
            "description": "Skills for test-team.",
        })
        gateways = GatewayCycle()

        with standing.holding(directory.where("forge")):
            code, _out, err = self.run_manual(gateways)

        self.assertEqual(OK, code, err)
        self.assertIn("team catalogs: completed with failures", err)
        self.assertIn("test-team declares test-team/implementing for forge", err)
        self.assertIn("rundesk skills revoke forge implementing", err)
        self.assertEqual("1.0.0", library.read("test-team").manifest.version)
        self.assertEqual("collided/implementing", grants.holding("forge", "implementing").address)
        self.assertEqual(([], []), (gateways.went_down, gateways.came_up))
        self.assertEqual("2.0.0", library.read("ordinary").manifest.version)

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

    def test_unreadable_member_records_fail_one_team_and_leave_it_and_the_next_alone(self):
        self.a_later_team()
        self.publish_second_versions()
        forge_home = directory.home("forge")
        before_page = (forge_home / "AGENTS.md").read_bytes()
        directory.records("forge").write_bytes(b"this is not a database")
        gateways = GatewayCycle()

        with standing.holding(directory.where("forge")):
            code, _out, err = self.run_manual(gateways)

        self.assertEqual(OK, code, err)
        self.assertEqual(before_page, (forge_home / "AGENTS.md").read_bytes())
        self.assertEqual("1.0.0", library.read("test-team").manifest.version)
        self.assertEqual("2.0.0", library.read("zeta-team").manifest.version)
        self.assertEqual("Triages the second workflow.",
                         records.read(directory.records("amber"))["describes"])
        self.assertIn("team catalogs: completed with failures", err)
        self.assertIn("test-team could not be checked or reconciled", err)
        # Refused before the gateway moved, not repaired after it did.
        self.assertEqual(([], []), (gateways.went_down, gateways.came_up))

    def test_a_failure_part_way_through_reconciliation_puts_every_member_back(self):
        self.a_later_team()
        self.publish_second_versions()
        forge_home, piper_home = directory.home("forge"), directory.home("piper")
        before = {
            "forge_agents": (forge_home / "AGENTS.md").read_bytes(),
            "forge_claude": (forge_home / "CLAUDE.md").read_bytes(),
            "piper_agents": (piper_home / "AGENTS.md").read_bytes(),
            "forge_records": records.read(directory.records("forge")),
            "forge_scope": delegating.scope_of("forge"),
        }
        (forge_home / "MEMORY.md").write_text("forge remembers this", encoding="utf-8")
        granting = grants.granted

        def fail_the_new_grant(agent, skill, alias=""):
            # The second version moves forge from `implementing` to `reviewing`. Failing on that one
            # grant lands the failure after its pages, records and old grant have already moved, and
            # leaves every other grant this operation makes — including the ones putting it
            # back — working normally.
            if (agent, skill.name) == ("forge", "reviewing"):
                raise OSError("synthetic mid-reconciliation failure")
            return granting(agent, skill, alias)

        gateways = GatewayCycle()
        with mock.patch.object(grants, "granted", side_effect=fail_the_new_grant), \
                standing.holding(directory.where("forge")):
            code, _out, err = self.run_manual(gateways)

        self.assertEqual(OK, code, err)
        self.assertEqual("1.0.0", library.read("test-team").manifest.version)
        self.assertEqual(before["forge_agents"], (forge_home / "AGENTS.md").read_bytes())
        self.assertEqual(before["forge_claude"], (forge_home / "CLAUDE.md").read_bytes())
        self.assertEqual(before["piper_agents"], (piper_home / "AGENTS.md").read_bytes())
        self.assertEqual("forge remembers this", (forge_home / "MEMORY.md").read_text())
        self.assertEqual(before["forge_records"], records.read(directory.records("forge")))
        self.assertEqual(before["forge_scope"], delegating.scope_of("forge"))
        self.assertEqual("test-team/implementing",
                         grants.holding("forge", "implementing").address)
        self.assertIsNone(grants.holding("forge", "reviewing"))
        self.assertEqual(["forge"], gateways.went_down)
        self.assertEqual(["forge"], gateways.came_up)
        self.assertIn("team catalogs: completed with failures", err)
        self.assertEqual("2.0.0", library.read("zeta-team").manifest.version)

    def test_a_restore_that_cannot_finish_is_named_instead_of_reported_as_settled(self):
        """Putting state back can fail too, and that is a third outcome rather than a success.

        `restoring.kept` says what it could not put back. A lifecycle that could not name that would
        leave a half-reconciled team indistinguishable from one that settled.
        """
        self.a_later_team()
        self.publish_second_versions()
        granting = grants.granted

        def fail_both_ways(agent, skill, alias=""):
            # `reviewing` is the grant the second version makes, so failing it fails the
            # reconciliation; `implementing` is the one putting it back, so failing that too is a
            # restore that cannot finish.
            if agent == "forge" and skill.name in ("reviewing", "implementing"):
                raise OSError(f"synthetic failure granting {skill.name}")
            return granting(agent, skill, alias)

        with mock.patch.object(grants, "granted", side_effect=fail_both_ways):
            code, _out, err = self.run_manual(GatewayCycle())

        self.assertEqual(OK, code, err)
        self.assertIn("test-team could not be checked or reconciled", err)
        self.assertIn("could not be put back", err)
        # Everything the restore could reach still went back, and what it could not is what it said.
        self.assertEqual("1.0.0", library.read("test-team").manifest.version)
        self.assertIsNone(grants.holding("forge", "implementing"))
        self.assertEqual("2.0.0", library.read("zeta-team").manifest.version)

    def test_a_directory_where_a_managed_page_belongs_refuses_before_a_gateway_moves(self):
        """The page rule is asked by the preflight, so it lands ahead of the gateway transition.

        `kept` asks it again under the install lock, but by then the member gateways are already
        down. Refusing here is what keeps a running member from being stood down and put back for
        a team that was never going to reconcile.
        """
        self.a_later_team()
        self.publish_second_versions()
        forge_home = directory.home("forge")
        notes = forge_home / "AGENTS.md"
        files.remove_one(notes)
        notes.mkdir()
        (notes / "kept.md").write_text("what the owner keeps here", encoding="utf-8")
        gateways = GatewayCycle()

        with standing.holding(directory.where("forge")):
            code, _out, err = self.run_manual(gateways)

        self.assertEqual(OK, code, err)
        self.assertTrue(notes.is_dir())
        self.assertEqual(["kept.md"], [one.name for one in notes.iterdir()])
        self.assertEqual("what the owner keeps here", (notes / "kept.md").read_text())
        self.assertEqual("1.0.0", library.read("test-team").manifest.version)
        self.assertEqual("test-team/implementing", grants.holding("forge", "implementing").address)
        self.assertIsNone(grants.holding("forge", "reviewing"))
        # Refused before the gateway moved, not stood down and put back for nothing.
        self.assertEqual(([], []), (gateways.went_down, gateways.came_up))
        self.assertIn("test-team could not be checked or reconciled", err)
        self.assertIn("neither a file nor a link", err)
        self.assertEqual("2.0.0", library.read("zeta-team").manifest.version)

    def test_a_grant_holder_no_team_declares_is_held_for_its_grants_and_nothing_else(self):
        """Retiring a skill reaches it, so its grants are held. Its own pages and records are not.

        Held like a member, the directory below would refuse the whole team over a page nothing in
        this lifecycle reads, and a rollback would write back pages and records it never touched.
        """
        outsider = self.an_unmanaged_agent("scribe")
        grants.granted("scribe", library.look_up("test-team/implementing"))
        memory = outsider / "MEMORY.md"
        files.remove_one(memory)
        memory.mkdir()
        (memory / "kept.md").write_text("the owner's own", encoding="utf-8")
        before = records.read(directory.records("scribe"))
        self.publish_second_versions()
        granting = grants.granted

        def fail_the_new_grant(agent, skill, alias=""):
            if (agent, skill.name) == ("forge", "reviewing"):
                raise OSError("synthetic mid-reconciliation failure")
            return granting(agent, skill, alias)

        with mock.patch.object(grants, "granted", side_effect=fail_the_new_grant):
            code, _out, err = self.run_manual(GatewayCycle())

        self.assertEqual(OK, code, err)
        # The team failed on the injected grant, not on a page belonging to somebody it does not
        # declare — which is what it would have failed on if scribe were held like a member.
        self.assertIn("synthetic mid-reconciliation failure", err)
        self.assertNotIn("neither a file nor a link", err)
        self.assertEqual("1.0.0", library.read("test-team").manifest.version)
        self.assertEqual("test-team/implementing", grants.holding("scribe", "implementing").address)
        self.assertTrue(memory.is_dir())
        self.assertEqual("the owner's own", (memory / "kept.md").read_text())
        self.assertEqual(before, records.read(directory.records("scribe")))
        self.assertEqual("# scribe\n\nThe owner wrote this.\n",
                         (outsider / "AGENTS.md").read_text())


if __name__ == "__main__":
    unittest.main()
