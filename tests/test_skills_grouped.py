"""Catalogs that keep their skills in group folders, and the catalogs this release requires.

A grouped catalog lists each skill in its manifest as `{"name", "path"}`; one with no list is walked
exactly as before. The second half is the move this release makes: the general catalog it depends
on is `skills`, and `managing-github` no longer ships inside it.

Run directly: `python3 tests/test_skills_grouped.py`
"""

import json
import os
import unittest
from pathlib import Path
from typing import Dict, Optional
from unittest import mock

from fixtures_skills import a_grouped_catalog, a_published_catalog, a_skill, written

import support
from rundesk.agents import directory
from rundesk.commands import automatic_updates, update
from rundesk.core import config, paths
from rundesk.exits import FAILED, OK
from rundesk.lifecycle import migration
from rundesk.skills import catalogs, doctor, grants, library, oauth

#: The skill this release stopped shipping in `rundesk`, by the name its grants stand under.
MOVED = "managing-github"

#: An OAuth declaration that validates, so discovery can be asked of a grouped skill.
A_PROVIDER = {
    "schema": 1, "provider": "example", "display_name": "Example",
    "authorization_endpoint": "https://id.example/authorize",
    "token_endpoint": "https://id.example/token",
    "identity_endpoint": "https://id.example/me", "base_scopes": ["identity"],
    "identity": {"subject": "subject", "email": "mail", "email_verified": "verified"},
    "authorization_parameters": {"prompt": "consent"}, "client_secret": True,
    "capabilities": {"reports": "reports.read"},
}


class Fetched:
    """The stand-in for the network: each source answered from a directory on this machine."""

    def __init__(self, by_source: Dict[str, Path]) -> None:
        self.by_source = by_source

    def __call__(self, source: str, _etag: str, _into: Path) -> Optional[catalogs.Brought]:
        at = self.by_source.get(source) or Path(source)
        if not at.is_dir():
            raise OSError(f"{source} is unavailable")
        return catalogs.Brought(at, "")


class Grouped(support.Isolated):
    """A scratch install with the library made and one agent added."""

    def setUp(self) -> None:
        super().setUp()
        library.where().mkdir(parents=True, exist_ok=True)
        self.published = self.home / "published"
        directory.made("alan", "claude")

    def a_source(self, name: str = "acme", **how) -> Path:
        return a_grouped_catalog(self.published / name, name=name, **how)

    def install(self, source: Path) -> catalogs.Installed:
        with catalogs.brought(str(source)) as coming:
            return catalogs.installed(coming)

    def listing(self, source: Path, entries: list) -> Path:
        """Replace the manifest's `skills` list with exactly `entries`."""
        manifest = json.loads((source / library.MANIFEST).read_text())
        manifest[library.LISTED] = entries
        written(source / library.MANIFEST, manifest)
        return source

    def refused(self, source: Path) -> str:
        with self.assertRaises(catalogs.Refused) as refused, catalogs.brought(str(source)):
            pass
        return str(refused.exception)


class ReadingWhereEachSkillStands(Grouped):
    def test_a_listed_skill_stands_at_its_path_and_is_named_by_its_folder(self):
        source = self.a_source(skills={"game-design": "games", "writing-plans": "writing"})
        index = library.indexed(source)
        self.assertEqual([], index.trouble)
        self.assertEqual({"game-design": source / "skills/games/game-design",
                          "writing-plans": source / "skills/writing/writing-plans"}, index.skills)

    def test_a_manifest_without_a_list_is_walked_exactly_as_before(self):
        source = a_published_catalog(self.published / "flat", name="flat",
                                     skills=("filing-issues", "writing-plans"))
        a_skill(source / library.INSIDE / "group" / "nested")
        index = library.indexed(source)
        self.assertEqual([], index.trouble)
        self.assertEqual(library.found(source / library.INSIDE), list(index.skills))
        self.assertEqual(["filing-issues", "writing-plans"], list(index.skills))

    def test_every_unusable_entry_is_named_in_one_refusal(self):
        source = self.a_source(skills={"game-design": "games", "level-design": "games"})
        a_skill(self.published / "elsewhere" / "stray")
        a_skill(source / "docs" / "notes")
        a_skill(source / library.INSIDE / "games" / "renamed", name="renamed")
        (source / library.INSIDE / "games" / "empty").mkdir()
        self.listing(source, [
            {"name": "game-design", "path": "skills/games/game-design"},
            {"name": "game-design", "path": "skills/games/level-design"},
            {"name": "stray", "path": "../elsewhere/stray"},
            {"name": "notes", "path": "docs/notes"},
            {"name": "rooted", "path": "/skills/games/game-design"},
            {"name": "other-name", "path": "skills/games/renamed"},
            {"name": "empty", "path": "skills/games/empty"},
            {"name": "no-path"},
            {"name": "extra", "path": "skills/games/extra", "group": "games"},
            "a string",
        ])
        said = self.refused(source)
        for named in ("lists game-design more than once",
                      "puts stray at '../elsewhere/stray', which is not a folder under skills/",
                      "puts notes at 'docs/notes', which is not a folder under skills/",
                      "puts rooted at '/skills/games/game-design', which is not a folder",
                      "whose folder is called renamed",
                      "lists empty at 'skills/games/empty', and there is no SKILL.md there",
                      "malformed skill entry {'name': 'no-path'}",
                      "malformed skill entry {'name': 'extra'",
                      "malformed skill entry 'a string'"):
            with self.subTest(named=named):
                self.assertIn(named, said)
        self.assertEqual([], library.known(), "a refused catalog was installed")

    def test_a_listed_folder_that_links_outside_the_catalog_is_refused(self):
        # A fetch copies a local source with its links followed, and an archive refuses them, so
        # this is asked of a tree read where it stands: the index is the guard either way.
        source = self.a_source()
        outside = self.published / "elsewhere" / "stray"
        a_skill(outside, name="linked")
        (source / library.INSIDE / "games" / "linked").symlink_to(outside)
        self.listing(source, [{"name": "linked", "path": "skills/games/linked"}])
        index = library.indexed(source)
        self.assertEqual({}, index.skills)
        self.assertEqual(["manifest.json puts linked at 'skills/games/linked', which reaches "
                          "outside this catalog"], index.trouble)

    def test_a_list_that_is_not_a_list_is_refused(self):
        source = self.listing(self.a_source(), {"game-design": "skills/games/game-design"})
        self.assertIn("has a skills field that is not a list of entries", self.refused(source))

    def test_an_invalid_skill_name_in_a_list_is_refused(self):
        source = self.a_source()
        self.listing(source, [{"name": "Game_Design", "path": "skills/games/game-design"}])
        self.assertIn("lists 'Game_Design'", self.refused(source))

    def test_a_listed_skill_whose_frontmatter_disagrees_is_refused(self):
        source = self.a_source()
        a_skill(source / "skills/games/game-design", name="something-else")
        self.assertIn("calls this skill 'something-else'", self.refused(source))

    def test_an_empty_list_declares_no_skills(self):
        source = self.listing(self.a_source(), [])
        self.assertIn("declares no skills", self.refused(source))


class AGroupedCatalogThroughItsLife(Grouped):
    def test_it_installs_and_its_skills_are_found_listed_and_looked_up(self):
        source = self.a_source(skills={"game-design": "games", "writing-plans": "writing"})
        did = self.install(source)
        self.assertEqual(["game-design", "writing-plans"], did.skills)
        tree = library.tree("acme")
        self.assertEqual(tree / "skills/games/game-design", library.look_up("acme/game-design").at)
        self.assertEqual(["game-design", "writing-plans"],
                         [one.name for one in library.held("acme")])
        self.assertIn("acme/writing-plans", [one.address for one in library.every()])
        with self.assertRaises(library.Refused) as refused:
            library.look_up("acme/games")
        self.assertIn("acme has no skill called games", str(refused.exception))

    def test_a_grant_links_to_the_grouped_folder_and_reads_back_its_address(self):
        self.install(self.a_source())
        held = grants.granted("alan", library.look_up("acme/game-design"))
        self.assertTrue(held.at.is_symlink())
        self.assertEqual(library.tree("acme") / "skills/games/game-design", held.at.resolve())
        self.assertEqual("acme/game-design", grants.holding("alan", "game-design").address)
        self.assertTrue((directory.home("alan") / ".claude/skills/game-design").is_symlink())
        self.assertEqual([doctor.READY], [one.verdict for one in doctor.looked_at("alan")])

    def test_a_copy_granted_as_another_name_is_remade_from_the_grouped_folder(self):
        source = self.a_source()
        self.install(source)
        copy = grants.granted("alan", library.look_up("acme/game-design"), "designing")
        declared = source / "skills/games/game-design" / library.DECLARED
        declared.write_text(declared.read_text() + "\nA second edition.\n")
        catalogs.update("acme")
        self.assertTrue(grants.stale(grants.holding("alan", "designing")))
        self.assertEqual(["alan/designing"], grants.refreshed())
        self.assertIn("A second edition.", (copy.at / library.DECLARED).read_text())

    def test_a_grouped_skills_needs_and_oauth_declaration_are_discovered(self):
        source = self.a_source(skills={"jira": "integrations"})
        a_skill(source / "skills/integrations/jira", needs={"JIRA_TOKEN": "an API token"})
        written(source / "skills/integrations/jira" / oauth.DECLARED, A_PROVIDER)
        self.install(source)
        grants.granted("alan", library.look_up("acme/jira"))
        self.assertEqual([doctor.BLOCKED], [one.verdict for one in doctor.looked_at("alan")])
        self.assertEqual(["example"], [one.provider for one in oauth.every()])

    def test_an_update_retires_a_skill_and_revokes_its_grants(self):
        source = self.a_source(skills={"game-design": "games", "level-design": "games"})
        self.install(source)
        grants.granted("alan", library.look_up("acme/level-design"))
        self.a_source(version="2.0.0", skills={"game-design": "games"})
        did = catalogs.update("acme")
        self.assertEqual(["level-design"], did.retired)
        self.assertEqual({"alan": ["level-design"]}, grants.retired("acme", did.retired))
        self.assertIsNone(grants.holding("alan", "level-design"))

    def test_a_skill_moved_to_another_folder_keeps_its_grant_pointed_at_it(self):
        source = a_published_catalog(self.published / "acme", name="acme",
                                     skills=("game-design",))
        self.install(source)
        grants.granted("alan", library.look_up("acme/game-design"))
        self.a_source(version="2.0.0", skills={"game-design": "games"})
        did = catalogs.update("acme")
        self.assertEqual([], did.retired)
        said = []
        grants.refreshed(said.append)
        self.assertIn("pointed alan's game-design at where acme/game-design now stands", said)
        held = grants.holding("alan", "game-design")
        self.assertTrue(held.resolves)
        self.assertEqual(library.tree("acme") / "skills/games/game-design", held.at.resolve())
        self.assertFalse(os.path.isabs(os.readlink(held.at)))

    def test_removing_it_takes_every_grouped_skill_and_its_grants(self):
        self.install(self.a_source(skills={"game-design": "games", "writing-plans": "writing"}))
        grants.granted("alan", library.look_up("acme/writing-plans"))
        went = catalogs.remove("acme")
        self.assertEqual(["game-design", "writing-plans"], went)
        self.assertEqual({"alan": ["writing-plans"]}, grants.retired("acme", went))

    def test_the_commands_preview_and_count_a_grouped_catalog(self):
        source = self.a_source(skills={"game-design": "games", "writing-plans": "writing"})
        code, _out, err = support.run_with(["skills", "install", str(source)])
        self.assertEqual(FAILED, code)
        self.assertIn("skill    game-design", err)
        self.assertIn("skill    writing-plans", err)
        code, _out, err = support.run_with(["skills", "install", str(source), "--confirm"])
        self.assertEqual(OK, code, err)
        code, out, err = support.run_with(["skills", "catalogs"])
        self.assertEqual(OK, code, err)
        self.assertRegex(out, r"acme\s+1\.0\.0\s+2\s")
        code, _out, err = support.run_with(["skills", "grant", "alan", "acme/game-design"])
        self.assertEqual(OK, code, err)


class Bundled(Grouped):
    """The shipped catalog placed out of this checkout, with a grant to a skill it used to ship."""

    def setUp(self) -> None:
        super().setUp()
        catalogs.place_bundled()
        # What 0.61 left on disk: `managing-github` inside the shipped catalog, granted to alan.
        a_skill(library.tree(library.BUNDLED) / library.INSIDE / MOVED)
        grants.granted("alan", library.look_up(f"{library.BUNDLED}/{MOVED}"))
        catalogs.place_bundled()
        self.assertFalse(grants.holding("alan", MOVED).resolves)

    def required(self) -> Path:
        return self.a_source(name=library.DEPENDED, skills={MOVED: "development"})


class TheSkillThisReleaseStoppedShipping(Bundled):
    def test_it_is_granted_again_from_the_required_catalog_when_that_holds_it(self):
        self.install(self.required())
        said = []
        grants.refreshed(said.append)
        self.assertIn(f"gave alan {library.DEPENDED}/{MOVED} in place of "
                      f"{library.BUNDLED}/{MOVED}, which this release no longer ships", said)
        held = grants.holding("alan", MOVED)
        self.assertTrue(held.resolves)
        self.assertEqual(f"{library.DEPENDED}/{MOVED}", held.address)
        self.assertTrue((directory.home("alan") / ".claude/skills" / MOVED).exists())

    def test_it_is_revoked_and_said_when_the_required_catalog_is_not_installed(self):
        said = []
        grants.refreshed(said.append)
        self.assertIn(f"took {library.BUNDLED}/{MOVED} from alan — this release no longer ships "
                      f"it, and {library.DEPENDED} is not installed to hold it", said)
        self.assertIsNone(grants.holding("alan", MOVED))
        self.assertFalse(os.path.lexists(directory.home("alan") / ".claude/skills" / MOVED))

    def test_a_shipped_skill_missing_from_the_installed_tree_is_never_taken(self):
        # A placement that failed leaves a tree short of something this release still ships. The
        # grant waits for the next placement rather than being revoked over it.
        grants.granted("alan", library.look_up(f"{library.BUNDLED}/writing-skills"))
        os.rename(library.tree(library.BUNDLED) / library.INSIDE / "writing-skills",
                  self.home / "set-aside")
        grants.refreshed()
        self.assertEqual(f"{library.BUNDLED}/writing-skills",
                         grants.holding("alan", "writing-skills").address)

    def test_a_copy_and_an_owners_own_entry_are_left_as_they_are(self):
        grants.revoked("alan", MOVED)
        own = self.home / "own-github"
        a_skill(own, name=MOVED)
        (grants.where("alan") / MOVED).symlink_to(own)
        grants.refreshed()
        self.assertEqual(own, grants.holding("alan", MOVED).at.resolve())


class TheCatalogThisReleaseDependsOn(Bundled):
    def test_it_is_skills_from_the_rundesk_ai_repository_and_cannot_be_removed(self):
        self.assertEqual("skills", library.DEPENDED)
        self.assertEqual("https://github.com/rundesk-ai/skills", catalogs.DEPENDED_SOURCE)
        self.assertFalse(catalogs.may_be_removed(library.DEPENDED))
        self.assertTrue(catalogs.may_be_fetched(library.DEPENDED))
        self.assertTrue(catalogs.may_be_removed("rundesk-skills"))

    def test_an_install_from_0_61_gets_skills_and_keeps_rundesk_skills_removable(self):
        old = self.install(a_published_catalog(self.published / "rundesk-skills",
                                               name="rundesk-skills", skills=("writing-plans",)))
        grants.granted("alan", library.look_up("rundesk-skills/writing-plans"))
        fetching = Fetched({catalogs.DEPENDED_SOURCE: self.required()})
        outcomes = catalogs.required(fetching)
        self.assertEqual([], [one.why for one in outcomes if one.why])
        self.assertIn(library.DEPENDED, library.known())
        self.assertIn(old.name, library.known())
        grants.refreshed()
        self.assertEqual("rundesk-skills/writing-plans",
                         grants.holding("alan", "writing-plans").address)
        code, _out, err = support.run_with(["skills", "remove", "rundesk-skills", "--confirm"])
        self.assertEqual(OK, code, err)
        code, _out, err = support.run_with(["skills", "remove", library.DEPENDED, "--confirm"])
        self.assertEqual(FAILED, code)
        self.assertIn("is a catalog rundesk depends on and is not removable", err)


class SettlingTheReleaseThatLanded(Bundled):
    """The sweep after an update runs in the release being replaced, so settling has to do this."""

    def setUp(self) -> None:
        super().setUp()
        config.write_fresh(paths.data())
        migration.stamp_without_running(paths.data())

    def settled(self, fetching: Fetched) -> int:
        scheduled = mock.Mock(how="", why="")
        with mock.patch.object(automatic_updates, "reconcile", return_value=scheduled):
            return update.settle(gateways=mock.Mock(), refreshing=fetching)

    def test_settling_installs_skills_and_grants_the_moved_skill_from_it(self):
        self.assertEqual(OK, self.settled(Fetched({catalogs.DEPENDED_SOURCE: self.required()})))
        self.assertIn(library.DEPENDED, library.known())
        self.assertEqual(f"{library.DEPENDED}/{MOVED}", grants.holding("alan", MOVED).address)

    def test_settling_offline_still_succeeds_and_revokes_rather_than_dangles(self):
        self.assertEqual(OK, self.settled(Fetched({})))
        self.assertNotIn(library.DEPENDED, library.known())
        self.assertIsNone(grants.holding("alan", MOVED))


if __name__ == "__main__":
    unittest.main()
