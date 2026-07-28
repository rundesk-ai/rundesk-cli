"""A plugin somebody else wrote — every row of the plugins work.

Offline and complete. The network is one function (`plugin._fetch`) and every test here
replaces it, so what is exercised is the decision — which release is taken, what is refused,
what happens when a stranger's step fails mid-update — and never somebody else's uptime.

Nothing here writes outside its own scratch directory: every place rundesk resolves a
plugin, a script or a skill is redirected, so a suite cannot reach the library of whoever
is running it.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from rundesk import migration, plugin, skill


A_STEP = '''
def up(conn, state):
    conn.execute("CREATE TABLE item (ref TEXT PRIMARY KEY, title TEXT NOT NULL)")
    return []
'''

A_SECOND_STEP = '''
def up(conn, state):
    conn.execute("ALTER TABLE item ADD COLUMN seen_at TEXT")
    return []
'''

A_STEP_THAT_FAILS = '''
def up(conn, state):
    raise RuntimeError("this step is broken")
'''


def a_plugin(at: Path, name: str = "example", version: str = "1.0.0", commands=None,
             skills=("example",), steps=(), requires=None, credentials=None,
             manifest_format: int = 1, extra=None) -> Path:
    """One plugin on disk, in the shape `read` accepts unless a test asks otherwise."""
    at = at / name
    at.mkdir(parents=True, exist_ok=True)
    commands = (name,) if commands is None else commands
    said = {"manifest": manifest_format, "name": name, "version": version,
            "description": f"{name} does a thing", "provides": {}}
    if commands:
        (at / "bin").mkdir(exist_ok=True)
        listed = []
        for one in commands:
            made = at / "bin" / one
            made.write_text("#!/bin/sh\necho hello\n", encoding="utf-8")
            made.chmod(0o755)
            listed.append({"name": one, "path": f"bin/{one}"})
        said["provides"]["commands"] = listed
    if skills:
        listed = []
        for one in skills:
            made = at / "skills" / one
            made.mkdir(parents=True, exist_ok=True)
            (made / "SKILL.md").write_text(
                f"---\nname: {one}\ndescription: Use when a task mentions {one}.\n---\n\nDo it.\n",
                encoding="utf-8")
            listed.append(f"skills/{one}")
        said["provides"]["skills"] = listed
    if steps:
        (at / "migrations").mkdir(exist_ok=True)
        for number, body in steps:
            (at / "migrations" / f"{number:03d}.py").write_text(body, encoding="utf-8")
        said["migrations"] = "migrations"
    if requires is not None:
        said["requires"] = {"rundesk": requires}
    if credentials is not None:
        said["credentials"] = credentials
    if extra:
        said.update(extra)
    (at / plugin.MANIFEST).write_text(json.dumps(said, indent=2), encoding="utf-8")
    return at


class WithAMachine(unittest.TestCase):
    """A plugins directory, a script library and a skill library, all scratch."""

    def setUp(self):
        self.where = Path(tempfile.mkdtemp(prefix="rundesk-plugins-"))
        self.addCleanup(shutil.rmtree, self.where, ignore_errors=True)
        self.plugins = self.where / "data" / "plugins"
        self.scripts = self.where / "data" / "scripts"
        self.skills = self.where / "data" / "skills"
        for one in (self.plugins, self.scripts, self.skills):
            one.mkdir(parents=True)
        self.made = self.where / "made"
        self.made.mkdir()

    def install(self, source, version="1.0.0", **kw):
        return plugin.install(source, self.plugins, self.scripts, self.skills,
                              version=version, **kw)

    def update(self, name, source=None, version="1.0.0", **kw):
        if source is not None:
            kw["fetch"] = _fetching(source)
        return plugin.update(name, self.plugins, self.scripts, self.skills,
                             version=version, **kw)


def _fetching(at: Path, tag: str | None = None, sha: str | None = None):
    """A replacement for the one function that reaches the network."""
    def fetch(source, work, say):
        return plugin.Got(plugin.unpack(Path(at), Path(work) / "unpacked"),
                          str(source), tag, sha)
    return fetch


# ---------------------------------------------------------------------------
# What a manifest is
# ---------------------------------------------------------------------------

class WhatAManifestIs(WithAMachine):
    def test_a_plugin_declares_its_name_its_version_and_what_it_provides(self):
        """R-PLG-1 — the manifest is the whole contract, and it is read rather than guessed."""
        manifest = plugin.read(a_plugin(self.made))
        self.assertEqual("example", manifest.name)
        self.assertEqual("1.0.0", manifest.version)
        self.assertEqual((("example", "bin/example"),), manifest.commands)
        self.assertEqual(("skills/example",), manifest.skills)

    def test_a_plugin_that_is_refused_leaves_no_directory_behind_to_clean_up(self):
        """R-PLG-2 — the whole refusal happens against a temporary directory."""
        at = a_plugin(self.made)
        (at / plugin.MANIFEST).write_text("{ not json", encoding="utf-8")
        with self.assertRaises(plugin.NotAPlugin):
            self.install(at)
        self.assertEqual([], sorted(self.plugins.iterdir()))

    def test_a_directory_with_no_manifest_is_not_a_plugin(self):
        """R-PLG-1 — somebody half way through writing one has not broken anything."""
        (self.made / "started").mkdir()
        with self.assertRaises(plugin.NotAPlugin):
            plugin.read(self.made / "started")

    def test_a_manifest_format_from_the_future_is_refused_rather_than_guessed_at(self):
        """R-PLG-3 — a step forward exists and a step back does not, one level up."""
        at = a_plugin(self.made, manifest_format=plugin.SCHEMA + 1)
        with self.assertRaises(plugin.NotAPlugin) as caught:
            plugin.read(at)
        self.assertIn("update rundesk first", str(caught.exception))

    def test_a_manifest_that_does_not_say_which_format_it_is_written_in_is_refused(self):
        """R-PLG-3 — an unversioned format is one nobody can ever change safely."""
        at = a_plugin(self.made)
        said = json.loads((at / plugin.MANIFEST).read_text())
        del said["manifest"]
        (at / plugin.MANIFEST).write_text(json.dumps(said), encoding="utf-8")
        with self.assertRaises(plugin.NotAPlugin):
            plugin.read(at)

    def test_a_name_no_brain_or_shell_would_accept_is_refused(self):
        """R-PLG-4 — a name a loader drops is a skill that exists and never fires."""
        at = a_plugin(self.made, name="Example_Plugin", skills=(), commands=("ok",))
        with self.assertRaises(plugin.NotAPlugin) as caught:
            plugin.read(at)
        self.assertIn("lowercase", str(caught.exception))

    def test_a_command_that_is_not_executable_is_refused_before_anybody_installs_it(self):
        """R-PLG-5 — found on the machine of whoever wrote it, not of whoever installs it."""
        at = a_plugin(self.made)
        (at / "bin" / "example").chmod(0o644)
        with self.assertRaises(plugin.NotAPlugin) as caught:
            plugin.read(at)
        self.assertIn("chmod +x", str(caught.exception))

    def test_a_command_path_pointing_outside_the_plugin_is_refused(self):
        """R-PLG-6 — a manifest may not name any file on the machine."""
        at = a_plugin(self.made)
        said = json.loads((at / plugin.MANIFEST).read_text())
        said["provides"]["commands"] = [{"name": "example", "path": "../../../bin/sh"}]
        (at / plugin.MANIFEST).write_text(json.dumps(said), encoding="utf-8")
        with self.assertRaises(plugin.NotAPlugin) as caught:
            plugin.read(at)
        self.assertIn("outside the plugin", str(caught.exception))

    def test_an_absolute_command_path_is_refused(self):
        """R-PLG-6 — joining an absolute path discards the left side entirely."""
        at = a_plugin(self.made)
        said = json.loads((at / plugin.MANIFEST).read_text())
        said["provides"]["commands"] = [{"name": "example", "path": "/bin/sh"}]
        (at / plugin.MANIFEST).write_text(json.dumps(said), encoding="utf-8")
        with self.assertRaises(plugin.NotAPlugin):
            plugin.read(at)

    def test_a_skill_no_brain_would_index_is_refused_with_the_reason(self):
        """R-PLG-7 — the same rules `skill.valid` holds an owner's library to."""
        at = a_plugin(self.made, skills=())
        said = json.loads((at / plugin.MANIFEST).read_text())
        (at / "skills" / "broken").mkdir(parents=True)
        (at / "skills" / "broken" / "SKILL.md").write_text(
            "---\nname: something-else\ndescription: x\n---\n", encoding="utf-8")
        said["provides"]["skills"] = ["skills/broken"]
        (at / plugin.MANIFEST).write_text(json.dumps(said), encoding="utf-8")
        with self.assertRaises(plugin.NotAPlugin) as caught:
            plugin.read(at)
        self.assertIn("no brain would index", str(caught.exception))

    def test_a_manifest_carrying_a_credential_value_is_refused(self):
        """R-PLG-8 — a manifest is published, so it holds names and never values."""
        at = a_plugin(self.made, credentials=[{"name": "EXAMPLE_TOKEN", "value": "sk-live"}])
        with self.assertRaises(plugin.NotAPlugin) as caught:
            plugin.read(at)
        self.assertIn("names and never values", str(caught.exception))

    def test_a_credential_is_declared_by_name_and_whether_it_is_needed(self):
        """R-PLG-8 — so an owner is told what is missing before an agent finds out."""
        manifest = plugin.read(a_plugin(self.made, credentials=[
            {"name": "EXAMPLE_TOKEN", "required": True, "about": "the token"}]))
        self.assertEqual((("EXAMPLE_TOKEN", True, "the token"),), manifest.credentials)

    def test_a_plugin_providing_nothing_at_all_is_refused(self):
        """R-PLG-1 — installing it would give every agent nothing."""
        at = a_plugin(self.made, commands=(), skills=())
        with self.assertRaises(plugin.NotAPlugin):
            plugin.read(at)

    def test_the_records_version_is_read_off_the_steps_that_ship(self):
        """R-PLG-10 — a number declared twice is one that disagrees with itself (R-MIG-15)."""
        manifest = plugin.read(a_plugin(self.made, steps=((1, A_STEP), (2, A_SECOND_STEP))))
        self.assertEqual(2, manifest.wants())

    def test_steps_that_cannot_be_ordered_are_refused_before_anything_is_installed(self):
        """R-PLG-10 — two steps claiming one version are refused, as rundesk's own are."""
        at = a_plugin(self.made, steps=((1, A_STEP),))
        (at / "migrations" / "1.py").write_text(A_SECOND_STEP, encoding="utf-8")
        with self.assertRaises(plugin.NotAPlugin):
            plugin.read(at)


class WhichRundeskAPluginFits(WithAMachine):
    def test_a_plugin_that_names_no_range_fits_anything(self):
        """R-PLG-13 — the honest reading of saying nothing."""
        self.assertTrue(plugin.fits(None, "0.15.0"))

    def test_a_range_is_judged_against_the_version_it_is_given(self):
        """R-PLG-13 — floors, ceilings, and both together."""
        self.assertTrue(plugin.fits(">=0.15.0", "0.15.0"))
        self.assertFalse(plugin.fits(">=0.16.0", "0.15.0"))
        self.assertTrue(plugin.fits(">=0.15.0,<1.0.0", "0.20.1"))
        self.assertFalse(plugin.fits(">=0.15.0,<1.0.0", "1.0.0"))

    def test_a_range_this_cannot_judge_is_refused_rather_than_guessed(self):
        """R-PLG-13 — a narrow answer with an honest refusal beats a broad guess."""
        self.assertFalse(plugin.fits("~=0.15", "0.15.0"))
        with self.assertRaises(plugin.NotAPlugin) as caught:
            plugin.read(a_plugin(self.made, requires="~=0.15"))
        self.assertIn("cannot judge", str(caught.exception))


# ---------------------------------------------------------------------------
# Getting one onto the machine
# ---------------------------------------------------------------------------

class InstallingOne(WithAMachine):
    def test_a_plugin_installs_from_a_directory_on_this_machine(self):
        """R-PLG-11 — a path is the primitive; reaching a forge is laid over it."""
        landed = self.install(a_plugin(self.made))
        self.assertEqual("example", landed.name)
        self.assertTrue((self.plugins / "example" / plugin.APP / plugin.MANIFEST).is_file())
        self.assertTrue((self.plugins / "example" / plugin.STATE).is_dir())

    def test_a_plugin_installs_from_an_archive(self):
        """R-PLG-11 — the same primitive, packed."""
        at = a_plugin(self.made)
        archive = self.where / "example.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            tar.add(at, arcname="example-1.0.0")
        landed = self.install(archive)
        self.assertEqual("1.0.0", landed.version)

    def test_an_archive_that_would_write_outside_where_it_is_unpacked_is_refused(self):
        """R-PLG-12 — a plugin is a stranger's archive, which is what the guard is for."""
        archive = self.where / "escaping.tar.gz"
        escapee = self.where / "escapee"
        escapee.write_text("owned", encoding="utf-8")
        with tarfile.open(archive, "w:gz") as tar:
            tar.add(escapee, arcname="../../escaped")
        with self.assertRaises(plugin.NotAPlugin):
            plugin.unpack(archive, self.where / "unpacked")

    def test_a_plugin_puts_its_command_on_every_agents_path(self):
        """R-PLG-17 — installing one is what shares it; there is no per-agent step."""
        self.install(a_plugin(self.made))
        standing = self.scripts / "example"
        self.assertTrue(standing.is_symlink())
        self.assertEqual((self.plugins / "example" / plugin.APP / "bin" / "example").resolve(),
                         standing.resolve())

    def test_a_plugin_puts_its_skills_in_the_library_every_agent_reads(self):
        """R-PLG-18 — a plugin ships skills, and they stand beside an owner's own."""
        self.install(a_plugin(self.made))
        self.assertIn("example", skill.library(self.skills))

    def test_a_link_a_plugin_stands_is_relative_so_the_install_can_be_moved(self):
        """R-PLG-19 — copying an install must not leave every command pointing at the old machine."""
        self.install(a_plugin(self.made))
        self.assertFalse(Path(os.readlink(self.scripts / "example")).is_absolute())

    def test_an_owners_own_script_of_the_same_name_refuses_the_install(self):
        """R-PLG-20 — a name is never proof of ownership, and the plugin does not win."""
        mine = self.scripts / "example"
        mine.write_text("#!/bin/sh\necho mine\n", encoding="utf-8")
        with self.assertRaises(plugin.InTheWay):
            self.install(a_plugin(self.made))
        self.assertEqual("#!/bin/sh\necho mine\n", mine.read_text())
        self.assertEqual({}, plugin.installed(self.plugins))

    def test_an_owners_own_skill_of_the_same_name_refuses_the_install(self):
        """R-PLG-20 — the same rule, in the other library."""
        mine = self.skills / "example"
        mine.mkdir()
        (mine / "SKILL.md").write_text(
            "---\nname: example\ndescription: mine.\n---\n", encoding="utf-8")
        with self.assertRaises(plugin.InTheWay):
            self.install(a_plugin(self.made))
        self.assertIn("mine.", (mine / "SKILL.md").read_text())

    def test_installing_the_same_plugin_twice_says_to_update_it_instead(self):
        """R-PLG-21 — an install that silently replaced records would be found out once."""
        self.install(a_plugin(self.made))
        with self.assertRaises(plugin.InTheWay) as caught:
            self.install(a_plugin(self.made / "again", name="example"))
        self.assertIn("plugins update example", str(caught.exception))

    def test_a_plugin_needing_a_newer_rundesk_is_refused_with_both_versions_named(self):
        """R-PLG-14 — judged against the rundesk that will run it."""
        with self.assertRaises(plugin.NotAPlugin) as caught:
            self.install(a_plugin(self.made, requires=">=9.0.0"), version="0.15.0")
        self.assertIn("0.15.0", str(caught.exception))

    def test_a_release_tagged_differently_from_what_it_declares_is_refused(self):
        """R-PLG-22 — the rule rundesk holds itself to (`updater.tag_matches`)."""
        at = a_plugin(self.made, version="1.0.0")
        with self.assertRaises(plugin.NotAPlugin) as caught:
            plugin.install("owner/repo", self.plugins, self.scripts, self.skills,
                           version="0.15.0", fetch=_fetching(at, tag="v2.0.0"))
        self.assertIn("nobody can reason about", str(caught.exception))

    def test_where_a_plugin_came_from_and_at_which_tag_is_recorded(self):
        """R-PLG-23 — provenance, so an update is a diff somebody can look at."""
        at = a_plugin(self.made, version="1.0.0")
        plugin.install("owner/repo", self.plugins, self.scripts, self.skills,
                       version="0.15.0", fetch=_fetching(at, tag="v1.0.0", sha="abc"),
                       clock=lambda: "2026-07-28 10:00:00")
        entry = plugin.ledger(self.plugins)["example"]
        self.assertEqual("owner/repo", entry["source"])
        self.assertEqual("v1.0.0", entry["tag"])
        self.assertEqual("abc", entry["sha256"])
        self.assertEqual("2026-07-28 10:00:00", entry["installed_at"])

    def test_a_plugin_that_is_not_installed_leaves_nothing_of_itself_behind(self):
        """R-PLG-9 — linking is last, so a failed install is invisible rather than half visible."""
        at = a_plugin(self.made, steps=((1, A_STEP_THAT_FAILS),))
        with self.assertRaises(plugin.NotAPlugin):
            self.install(at)
        self.assertEqual({}, plugin.installed(self.plugins))
        self.assertEqual([], sorted(self.scripts.iterdir()))
        self.assertEqual([], sorted(self.skills.iterdir()))

    def test_the_records_a_plugin_keeps_are_made_by_running_its_steps(self):
        """R-PLG-10 — one store and one version, so one pass rather than one per agent."""
        self.install(a_plugin(self.made, steps=((1, A_STEP), (2, A_SECOND_STEP))))
        records = self.plugins / "example" / plugin.STATE / migration.RECORDS
        self.assertEqual(2, migration.version_on_disk(records))
        conn = sqlite3.connect(str(records))
        try:
            columns = [row[1] for row in conn.execute("PRAGMA table_info(item)")]
        finally:
            conn.close()
        self.assertIn("seen_at", columns)

    def test_a_plugin_with_no_steps_is_installed_without_records_being_made(self):
        """R-PLG-10 — a plugin that keeps nothing is the ordinary case, never an error."""
        self.install(a_plugin(self.made))
        self.assertFalse((self.plugins / "example" / plugin.STATE
                          / migration.RECORDS).exists())

    def test_what_a_plugins_migration_did_is_left_in_its_own_log_not_an_agents(self):
        """R-PLG-24 — a stranger's step does not belong in an account about an agent."""
        self.install(a_plugin(self.made, steps=((1, A_STEP),)))
        wrote = (self.plugins / "example" / plugin.LOG).read_text(encoding="utf-8")
        self.assertIn("001.py finished", wrote)


# ---------------------------------------------------------------------------
# Sharing one
# ---------------------------------------------------------------------------

class SharedByEveryAgent(WithAMachine):
    def test_one_install_serves_every_agent_through_one_directory(self):
        """R-PLG-17 — the command stands where every agent already looks, once."""
        self.install(a_plugin(self.made))
        self.assertEqual(["example"], sorted(one.name for one in self.scripts.iterdir()))

    def test_every_agent_reaches_one_copy_of_what_a_plugin_keeps(self):
        """R-PLG-25 — shared state is the point: two agents read what one wrote."""
        self.install(a_plugin(self.made, steps=((1, A_STEP),)))
        records = self.plugins / "example" / plugin.STATE / migration.RECORDS
        first = sqlite3.connect(str(records))
        second = sqlite3.connect(str(records))
        try:
            first.execute("INSERT INTO item VALUES ('a', 'written by one agent')")
            first.commit()
            self.assertEqual(("written by one agent",),
                             second.execute("SELECT title FROM item").fetchone())
        finally:
            first.close()
            second.close()

    def test_a_skill_a_plugin_ships_can_be_granted_and_then_revoked(self):
        """R-PLG-18 — a grant through a link is still a grant rundesk may take back."""
        self.install(a_plugin(self.made))
        was = os.environ.get("RUNDESK_PLUGINS")
        os.environ["RUNDESK_PLUGINS"] = str(self.plugins)
        self.addCleanup(lambda: os.environ.__setitem__("RUNDESK_PLUGINS", was)
                        if was is not None else os.environ.pop("RUNDESK_PLUGINS", None))
        mine = self.where / "agents" / "ava" / "home" / "skills"
        mine.mkdir(parents=True)
        skill.grant(mine, "example", self.skills)
        self.assertEqual(["example"], skill.granted(mine))
        skill.revoke(mine, "example", self.skills)
        self.assertEqual([], skill.granted(mine))


# ---------------------------------------------------------------------------
# Moving one forward
# ---------------------------------------------------------------------------

class UpdatingOne(WithAMachine):
    def setUp(self):
        super().setUp()
        self.install("owner/repo", fetch=_fetching(a_plugin(self.made, version="1.0.0")))

    def _published(self, **kw):
        at = self.where / "published"
        shutil.rmtree(at, ignore_errors=True)
        at.mkdir()
        return a_plugin(at, **kw)

    def test_a_newer_release_replaces_the_one_installed(self):
        """R-PLG-26 — the whole point of a version being in the manifest."""
        said = self.update("example", self._published(version="1.1.0"))
        self.assertEqual(plugin.Outcome.UPDATED, said.state)
        self.assertEqual(("1.0.0", "1.1.0"), (said.was, said.now))
        self.assertEqual("example: 1.0.0 -> 1.1.0", str(said))
        self.assertEqual("1.1.0", plugin.installed(self.plugins)["example"].version)

    def test_a_release_that_is_not_newer_leaves_everything_where_it_was(self):
        """R-PLG-26 — current is not a failure and is not news."""
        said = self.update("example", self._published(version="1.0.0"))
        self.assertEqual(plugin.Outcome.CURRENT, said.state)
        self.assertEqual("1.0.0", plugin.installed(self.plugins)["example"].version)

    def test_what_a_plugin_keeps_survives_being_moved_forward(self):
        """R-PLG-27 — `app/` is replaced whole and `state/` is never touched."""
        plugin.remove("example", self.plugins, self.scripts, self.skills, purge=True)
        self.install("owner/repo",
                     fetch=_fetching(a_plugin(self.where / "v1", version="1.0.0",
                                              steps=((1, A_STEP),))))
        records = self.plugins / "example" / plugin.STATE / migration.RECORDS
        conn = sqlite3.connect(str(records))
        conn.execute("INSERT INTO item VALUES ('kept', 'from before the update')")
        conn.commit()
        conn.close()
        self.update("example", a_plugin(self.where / "v2", version="1.1.0",
                                        steps=((1, A_STEP), (2, A_SECOND_STEP))))
        conn = sqlite3.connect(str(records))
        try:
            self.assertEqual(("from before the update",),
                             conn.execute("SELECT title FROM item").fetchone())
        finally:
            conn.close()
        self.assertEqual(2, migration.version_on_disk(records))

    def test_a_new_release_whose_step_fails_stays_on_the_version_that_worked(self):
        """R-PLG-28 — a stranger's broken step costs an owner nothing."""
        said = self.update("example", self._published(version="2.0.0",
                                                      steps=((1, A_STEP_THAT_FAILS),)))
        self.assertTrue(said.held, said)
        standing = plugin.installed(self.plugins)["example"]
        self.assertEqual("1.0.0", standing.version)
        self.assertTrue(standing.quarantined)

    def test_a_plugin_held_back_is_taken_off_every_agents_path(self):
        """R-PLG-29 — quarantine that leaves the command standing is not quarantine."""
        self.update("example", self._published(version="2.0.0",
                                               steps=((1, A_STEP_THAT_FAILS),)))
        self.assertFalse((self.scripts / "example").is_symlink())

    def test_a_release_needing_a_newer_rundesk_is_not_dragged_into_this_one(self):
        """R-PLG-14 — the plugin installed still works; the new one would not."""
        said = self.update("example", self._published(version="2.0.0", requires=">=9.0.0"),
                           version="0.15.0")
        self.assertEqual(plugin.Outcome.CURRENT, said.state)
        self.assertEqual("1.0.0", said.was)
        self.assertIn("needs rundesk", said.why)
        self.assertEqual("1.0.0", plugin.installed(self.plugins)["example"].version)

    def test_a_release_tagged_differently_from_its_manifest_is_not_taken(self):
        """R-PLG-22 — the same rule an install holds, on the way forward."""
        said = plugin.update("example", self.plugins, self.scripts, self.skills,
                             version="0.15.0",
                             fetch=_fetching(self._published(version="2.0.0"), tag="v9.9.9"))
        self.assertEqual(plugin.Outcome.CURRENT, said.state)
        self.assertEqual("1.0.0", said.was)

    def test_a_plugin_that_calls_itself_something_else_now_is_refused(self):
        """R-PLG-30 — a repository that changed hands does not get to become another plugin."""
        said = self.update("example", self._published(name="other", version="2.0.0"))
        self.assertEqual(plugin.Outcome.UNCHANGED, said.state)
        self.assertIn("calls itself other", said.why)

    def test_a_release_that_stops_providing_a_command_takes_it_off_the_path(self):
        """R-PLG-29 — what every agent sees agrees with what is installed."""
        self.update("example", self._published(version="1.1.0", commands=("renamed",)))
        self.assertFalse((self.scripts / "example").is_symlink())
        self.assertTrue((self.scripts / "renamed").is_symlink())


class WhenAnUpdateLands(WithAMachine):
    def test_a_plugin_that_cannot_be_moved_never_fails_the_update_it_rides(self):
        """R-PLG-15 — a stranger's release cannot take an owner's agents down."""
        self.install("owner/repo", fetch=_fetching(a_plugin(self.made, version="1.0.0")))
        said = plugin.bring_forward(
            self.plugins, self.scripts, self.skills, version="0.15.0",
            fetch=_fetching(a_plugin(self.where / "next", version="2.0.0",
                                     steps=((1, A_STEP_THAT_FAILS),))))
        self.assertTrue(any(one.held for one in said), said)
        self.assertTrue(plugin.installed(self.plugins)["example"].quarantined)

    def test_an_installed_plugin_that_no_longer_fits_is_held_back_before_it_is_moved(self):
        """R-PLG-14 — the one already installed is what no longer belongs on a PATH."""
        self.install("owner/repo", version="0.9.0",
                     fetch=_fetching(a_plugin(self.made, version="1.0.0", requires="<1.0.0")))
        said = plugin.bring_forward(self.plugins, self.scripts, self.skills,
                                    version="1.2.0", fetch=_fetching(self.made / "example"))
        self.assertTrue(any(one.held for one in said), said)
        self.assertFalse((self.scripts / "example").is_symlink())

    def test_a_plugin_that_fits_again_comes_back_by_itself(self):
        """R-PLG-31 — quarantine is a state to leave, not a sentence."""
        at = a_plugin(self.made, version="1.0.0", requires=">=1.0.0")
        self.install("owner/repo", version="1.0.0", fetch=_fetching(at))
        plugin.bring_forward(self.plugins, self.scripts, self.skills, version="0.9.0",
                             fetch=_fetching(at))
        self.assertTrue(plugin.installed(self.plugins)["example"].quarantined)
        plugin.bring_forward(self.plugins, self.scripts, self.skills, version="1.0.0",
                             fetch=_fetching(at))
        self.assertFalse(plugin.installed(self.plugins)["example"].quarantined)
        self.assertTrue((self.scripts / "example").is_symlink())

    def test_a_machine_with_no_plugins_does_nothing_and_says_nothing(self):
        """R-PLG-15 — an update on an ordinary machine is unchanged by any of this."""
        self.assertEqual([], plugin.bring_forward(self.plugins, self.scripts, self.skills,
                                                  version="0.15.0"))

    def test_an_install_that_has_never_had_a_plugins_directory_updates_as_it_always_did(self):
        """R-PLG-45 — every existing owner's first update, and the commonest case there is.

        A rundesk from before plugins existed has no `data/plugins/` at all. Reading a
        directory that is not there has to be "no plugins", never an error the update then
        has to survive — and this is the path every single existing install takes once.
        """
        absent = self.where / "never-existed" / "plugins"
        self.assertFalse(absent.exists())
        self.assertEqual({}, plugin.installed(absent))
        self.assertEqual([], plugin.bring_forward(absent, self.scripts, self.skills,
                                                  version="0.15.0"))
        self.assertFalse(absent.exists(), "asking made a directory nobody wanted")

    def test_a_plugin_whose_manifest_cannot_be_read_is_held_back_rather_than_skipped(self):
        """R-PLG-15 — an update must have something to say about every plugin it finds."""
        self.install("owner/repo", fetch=_fetching(a_plugin(self.made, version="1.0.0")))
        (self.plugins / "example" / plugin.APP / plugin.MANIFEST).write_text(
            "{ not json", encoding="utf-8")
        said = plugin.bring_forward(self.plugins, self.scripts, self.skills,
                                    version="0.15.0")
        self.assertEqual(1, len(said))
        self.assertTrue(said[0].held, said)
        self.assertFalse((self.scripts / "example").is_symlink())

    def test_every_plugin_gets_a_row_whether_or_not_anything_happened_to_it(self):
        """R-PLG-44 — a list an owner reads is one where silence is not an outcome."""
        at = a_plugin(self.made, version="1.0.0")
        self.install("owner/repo", fetch=_fetching(at))
        said = plugin.bring_forward(self.plugins, self.scripts, self.skills,
                                    version="0.15.0", fetch=_fetching(at))
        self.assertEqual(["example"], [one.name for one in said])
        self.assertEqual(plugin.Outcome.CURRENT, said[0].state)


# ---------------------------------------------------------------------------
# Taking one away
# ---------------------------------------------------------------------------

class RemovingOne(WithAMachine):
    def setUp(self):
        super().setUp()
        self.install(a_plugin(self.made, steps=((1, A_STEP),)))

    def test_removing_a_plugin_takes_its_command_off_every_agents_path(self):
        """R-PLG-32 — one removal takes it from all of them, as one install gave it to all."""
        plugin.remove("example", self.plugins, self.scripts, self.skills)
        self.assertFalse((self.scripts / "example").is_symlink())
        self.assertFalse((self.skills / "example").is_symlink())

    def test_what_a_plugin_kept_stays_unless_somebody_asks_for_it_to_go(self):
        """R-PLG-33 — removing one to reinstall it must not cost an owner its records."""
        said = plugin.remove("example", self.plugins, self.scripts, self.skills)
        self.assertIn("still in", said)
        self.assertTrue((self.plugins / "example" / plugin.STATE
                         / migration.RECORDS).is_file())

    def test_asking_for_it_to_go_takes_the_records_as_well(self):
        """R-PLG-33 — and only then."""
        plugin.remove("example", self.plugins, self.scripts, self.skills, purge=True)
        self.assertFalse((self.plugins / "example").exists())
        self.assertEqual({}, plugin.ledger(self.plugins))

    def test_installing_again_after_a_removal_picks_the_kept_records_back_up(self):
        """R-PLG-42 — the whole reason a removal keeps them: reinstalling has to work.

        Refusing here told an owner to run `plugins update` on a plugin with no release in
        it — a verb that cannot work — while the records they were promised sat unreachable.
        """
        conn = sqlite3.connect(
            str(self.plugins / "example" / plugin.STATE / migration.RECORDS))
        conn.execute("INSERT INTO item VALUES ('kept', 'from before the removal')")
        conn.commit()
        conn.close()
        plugin.remove("example", self.plugins, self.scripts, self.skills)

        landed = self.install(a_plugin(self.where / "again", steps=((1, A_STEP),)))
        self.assertEqual("example", landed.name)
        self.assertFalse(plugin.installed(self.plugins)["example"].quarantined)
        self.assertTrue((self.scripts / "example").is_symlink())
        conn = sqlite3.connect(
            str(self.plugins / "example" / plugin.STATE / migration.RECORDS))
        try:
            self.assertEqual(("from before the removal",),
                             conn.execute("SELECT title FROM item").fetchone())
        finally:
            conn.close()

    def test_removing_touches_nothing_an_owner_wrote_that_shares_a_name(self):
        """R-PLG-20 — only links that point into this plugin are pulled."""
        mine = self.scripts / "mine"
        mine.write_text("#!/bin/sh\n", encoding="utf-8")
        plugin.remove("example", self.plugins, self.scripts, self.skills, purge=True)
        self.assertTrue(mine.is_file())

    def test_a_name_that_is_a_path_is_refused_before_it_is_joined_to_anything(self):
        """R-PLG-34 — `Path('/a') / '/elsewhere'` is `/elsewhere`, and this removes."""
        for name in ("../../etc", "/etc", ".", ""):
            with self.assertRaises(plugin.Unknown):
                plugin.remove(name, self.plugins, self.scripts, self.skills, purge=True)

    def test_a_plugin_nobody_installed_cannot_be_removed(self):
        """R-PLG-34 — and says so rather than reporting a removal that removed nothing."""
        with self.assertRaises(plugin.Unknown):
            plugin.remove("absent", self.plugins, self.scripts, self.skills)

    def test_removal_never_reaches_a_directory_rundesk_did_not_lay_down(self):
        """R-PLG-34 — the marker is the proof, and a name is not."""
        theirs = self.plugins / "theirs"
        theirs.mkdir()
        (theirs / "important").write_text("mine", encoding="utf-8")
        with self.assertRaises(plugin.Unknown):
            plugin.remove("theirs", self.plugins, self.scripts, self.skills, purge=True)
        self.assertTrue((theirs / "important").is_file())

    def test_taking_rundesk_off_pulls_every_link_a_plugin_stood(self):
        """R-PLG-16 — a command resolving to nothing is worse than one that is gone."""
        self.assertEqual(["example"],
                         plugin.take_back(self.plugins, self.scripts, self.skills))
        self.assertEqual([], sorted(self.scripts.iterdir()))
        self.assertTrue((self.plugins / "example" / plugin.STATE).is_dir())


# ---------------------------------------------------------------------------
# Starting one
# ---------------------------------------------------------------------------

class StartingOne(WithAMachine):
    def test_the_plugin_that_is_scaffolded_is_one_that_installs(self):
        """R-PLG-35 — a working plugin rather than a page about one.

        Installed at the version actually running, never at one this test chose: a scaffold
        declaring a floor above the rundesk that wrote it is a plugin `init` produces and
        `install` refuses, which is exactly what the first draft did.
        """
        from rundesk import __version__
        at = plugin.scaffold("weather", self.made / "weather")
        manifest = plugin.read(at)
        self.assertEqual("weather", manifest.name)
        self.assertTrue(plugin.fits(manifest.requires, __version__),
                        f"a new plugin declares {manifest.requires}, "
                        f"which the rundesk that wrote it ({__version__}) does not satisfy")
        landed = plugin.install(at, self.plugins, self.scripts, self.skills,
                                version=__version__)
        self.assertEqual("weather", landed.name)
        self.assertTrue((self.scripts / "weather").is_symlink())

    def test_the_template_is_renamed_throughout_rather_than_only_in_its_manifest(self):
        """R-PLG-35 — a command called `example` in somebody's repository is the trap."""
        at = plugin.scaffold("weather", self.made / "weather")
        self.assertTrue((at / "bin" / "weather").is_file())
        self.assertTrue((at / "skills" / "weather" / "SKILL.md").is_file())
        self.assertNotIn("example", (at / "lib" / "weather.py").read_text())

    def test_a_hyphenated_name_still_produces_credential_names_a_shell_can_export(self):
        """R-PLG-43 — `weather-eu` wants `WEATHER_EU_TOKEN`, never `WEATHER-EU_TOKEN`.

        The obvious `.upper()` produced a name no shell can export, which `read` then
        refused — so `plugins init` failed for every hyphenated name there is, which is most
        of the interesting ones.
        """
        at = plugin.scaffold("weather-eu", self.made / "weather-eu")
        named = [one for one, _required, _about in plugin.read(at).credentials]
        self.assertTrue(named, "the template declares no credentials to check")
        for one in named:
            self.assertTrue(one.replace("_", "").isalnum(), f"{one} is not exportable")
            self.assertTrue(one.startswith("WEATHER_EU_"), one)

    def test_a_scaffold_that_fails_leaves_nothing_half_written_behind(self):
        """R-PLG-43 — a hidden half-written directory found weeks later explains nothing."""
        was = plugin.TEMPLATE
        plugin.TEMPLATE = self.made          # has a manifest? no — so `read` refuses
        (self.made / plugin.MANIFEST).write_text("{}", encoding="utf-8")
        self.addCleanup(lambda: setattr(plugin, "TEMPLATE", was))
        with self.assertRaises(plugin.NotAPlugin):
            plugin.scaffold("weather", self.made / "weather")
        self.assertEqual([], [one.name for one in self.made.iterdir()
                              if one.name.startswith(".") and one.name.endswith(".coming")])

    def test_a_name_no_brain_would_accept_is_refused_before_anything_is_written(self):
        """R-PLG-4 — the same rule, at the only moment it is cheap to obey."""
        with self.assertRaises(plugin.NotAPlugin):
            plugin.scaffold("Weather_2", self.made / "weather")
        self.assertFalse((self.made / "weather").exists())

    def test_scaffolding_over_something_that_is_already_there_is_refused(self):
        """R-PLG-35 — never the thing that overwrites somebody's work."""
        (self.made / "taken").mkdir()
        with self.assertRaises(plugin.InTheWay):
            plugin.scaffold("taken", self.made / "taken")


# ---------------------------------------------------------------------------
# What is on this machine
# ---------------------------------------------------------------------------

class WhatIsInstalled(WithAMachine):
    def test_a_plugin_that_is_there_and_broken_is_listed_with_why(self):
        """R-PLG-36 — absent and broken are different facts and read differently."""
        self.install(a_plugin(self.made))
        (self.plugins / "example" / plugin.APP / plugin.MANIFEST).write_text(
            "{ not json", encoding="utf-8")
        standing = plugin.installed(self.plugins)["example"]
        self.assertTrue(standing.quarantined)
        self.assertIn("could not be read", standing.why_unfit)

    def test_a_directory_rundesk_did_not_lay_down_is_not_a_plugin(self):
        """R-PLG-36 — the marker is what makes one ours to report on, replace or remove."""
        (self.plugins / "somebody-elses").mkdir()
        self.assertEqual({}, plugin.installed(self.plugins))

    def test_a_ledger_that_cannot_be_read_is_never_written_back_as_empty(self):
        """R-PLG-23 — unreadable state is not empty state (`AGENTS.md`)."""
        self.install(a_plugin(self.made))
        (self.plugins / plugin.LEDGER).write_text("{ not json", encoding="utf-8")
        with self.assertRaises(plugin.NotAPlugin):
            plugin.ledger(self.plugins)
        self.assertEqual("{ not json", (self.plugins / plugin.LEDGER).read_text())

    def test_every_directory_a_plugin_touches_follows_the_override_it_was_given(self):
        """R-PLG-40 — one resolver each, so a scratch install cannot reach the real one.

        The regression this exists for is real: linking through `scripts_home()` rather than
        `script.home()` ignored the override, and a suite left a live link in the developer's
        own script library pointing into a temporary directory that was already gone.
        """
        from rundesk import script as scripts
        was = {name: os.environ.get(name) for name in
               ("RUNDESK_PLUGINS", "RUNDESK_SCRIPTS", "RUNDESK_SKILL_LIBRARY")}
        os.environ["RUNDESK_PLUGINS"] = str(self.plugins)
        os.environ["RUNDESK_SCRIPTS"] = str(self.scripts)
        os.environ["RUNDESK_SKILL_LIBRARY"] = str(self.skills)

        def put_back():
            for name, value in was.items():
                os.environ.pop(name, None) if value is None else os.environ.__setitem__(name, value)
        self.addCleanup(put_back)

        self.assertEqual(self.plugins, plugin.home())
        self.assertEqual(self.scripts, scripts.home())
        self.assertEqual(self.skills, skill.home())
        # And the defaults actually used when nothing is passed are those three.
        plugin.install(a_plugin(self.made), version="1.0.0")
        self.assertTrue((self.scripts / "example").is_symlink())
        self.assertTrue((self.skills / "example").is_symlink())

    def test_a_path_on_this_machine_is_never_mistaken_for_a_repository(self):
        """R-PLG-11 — a directory that happens to be called `a/b` is still a directory."""
        self.assertIsNone(plugin.source_is_remote(str(self.made)))
        self.assertEqual(("owner/repo", None), plugin.source_is_remote("owner/repo"))
        self.assertEqual(("owner/repo", "v1.2.0"), plugin.source_is_remote("owner/repo@v1.2.0"))


if __name__ == "__main__":
    unittest.main()
