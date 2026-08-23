"""The untrusted, data-only team declaration and its ownership boundary."""

import json
import unittest

from fixtures_skills import a_published_catalog, a_team_catalog, written

import support
from rundesk.skills import catalogs as skill_catalogs
from rundesk.skills import library
from rundesk.teams import catalogs


class TeamCatalogs(support.Isolated):
    def setUp(self) -> None:
        super().setUp()
        library.where().mkdir(parents=True)
        self.source = a_team_catalog(self.home / "published")

    def read(self):
        with skill_catalogs.brought(str(self.source)) as coming:
            return catalogs.read(coming.at, coming.manifest)

    def test_a_complete_team_is_read_from_catalog_data(self):
        team = self.read()
        self.assertEqual("test-team", team.name)
        self.assertEqual(["forge", "piper"], [one.name for one in team.members])
        self.assertEqual(["piper"], team.members[0].delegates_to)

    def test_only_the_team_envelope_is_recognized_as_a_declaration(self):
        self.assertTrue(catalogs.declared(self.source))
        ordinary = a_published_catalog(self.home / "ordinary")
        written(ordinary / library.TEAM, {"metadata": "belongs to the ordinary catalog"})
        self.assertFalse(catalogs.declared(ordinary))

    def test_unknown_fields_and_unsafe_instruction_paths_are_refused(self):
        manifest = json.loads((self.source / library.TEAM).read_text())
        manifest["members"][0]["instructions"] = "../outside/AGENTS.md"
        written(self.source / library.TEAM, manifest)
        with self.assertRaises(catalogs.Refused) as refused:
            self.read()
        self.assertIn("unsafe instructions", str(refused.exception))

        manifest["members"][0]["instructions"] = "agents/forge/AGENTS.md"
        manifest["members"][0]["exclude_skills"] = ["anything"]
        written(self.source / library.TEAM, manifest)
        with self.assertRaises(catalogs.Refused) as refused:
            self.read()
        self.assertIn("exactly", str(refused.exception))

    def test_members_may_delegate_only_inside_the_declared_team(self):
        manifest = json.loads((self.source / library.TEAM).read_text())
        manifest["members"][0]["delegates_to"] = ["somebody-else"]
        written(self.source / library.TEAM, manifest)
        with self.assertRaises(catalogs.Refused) as refused:
            self.read()
        self.assertIn("outside this team", str(refused.exception))

    def test_a_member_may_have_no_optional_skills(self):
        manifest = json.loads((self.source / library.TEAM).read_text())
        manifest["members"][1]["skills"] = []
        written(self.source / library.TEAM, manifest)
        self.assertEqual([], self.read().members[1].skills)

    def test_weekly_upkeep_must_be_explicitly_on_or_off(self):
        manifest = json.loads((self.source / library.TEAM).read_text())
        manifest["members"][0]["self_improve"] = "sometimes"
        written(self.source / library.TEAM, manifest)
        with self.assertRaises(catalogs.Refused) as refused:
            self.read()
        self.assertIn("true or false self_improve", str(refused.exception))

    def test_an_empty_canonical_agent_workflow_is_refused(self):
        (self.source / "agents/forge/AGENTS.md").write_text("\n")
        with self.assertRaises(catalogs.Refused) as refused:
            self.read()
        self.assertIn("empty agent workflow", str(refused.exception))

    def test_a_team_cannot_replace_product_owned_operating_skills(self):
        manifest = json.loads((self.source / library.TEAM).read_text())
        manifest["members"][0]["skills"] = [library.REQUIRED_SKILL]
        written(self.source / library.TEAM, manifest)
        skill = self.source / library.INSIDE / library.REQUIRED_SKILL
        skill.mkdir()
        (skill / library.DECLARED).write_text(
            "---\nname: managing-rundesk\ndescription: Replace the floor.\n---\n")
        with self.assertRaises(catalogs.Refused) as refused:
            self.read()
        self.assertIn("product-owned", str(refused.exception))


if __name__ == "__main__":
    unittest.main()
