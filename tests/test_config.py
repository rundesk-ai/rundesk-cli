"""The file this install is configured through — what is written, and what is never touched.

Offline and complete. What each section *means* is proven where the thing it configures is
proven: how long a backup is kept in `test_backup`, when the machine looks for a release in
`test_updater`, which skills a new agent gets in `test_skill`. What is answered here is the
file itself — that it appears, that it grows a section a release added, and that nothing an
owner wrote into it is ever rewritten by us.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from rundesk import config, skill


class WithADataDirectory(unittest.TestCase):
    """A scratch data root, passed in rather than set in the environment."""

    def setUp(self):
        self.where = Path(tempfile.mkdtemp(prefix="rundesk-config-"))
        self.addCleanup(shutil.rmtree, self.where, ignore_errors=True)
        self.at = self.where / config.NAMED
        self.library = self.where / "skills"
        self.library.mkdir()
        real = skill.home
        skill.home = lambda: self.library
        self.addCleanup(setattr, skill, "home", real)

    def built_in(self, name: str) -> Path:
        at = self.library / name
        at.mkdir()
        (at / skill.NAMED).write_text(
            f"---\nname: {name}\ndescription: Use for tests.\n---\n",
            encoding="utf-8",
        )
        (at / skill.OWNED).write_text("rundesk built-in\n", encoding="utf-8")
        return at


class WhatInstallingWrites(WithADataDirectory):
    def test_installing_writes_the_configuration_an_owner_can_read(self):
        """R-INS-19 — a file an owner is expected to open and never sees is a file nobody
        edits, and every value in it is then folklore."""
        self.assertEqual(list(config.SECTIONS), config.ensure(self.where))
        self.assertEqual(config.INITIAL, json.loads(self.at.read_text()))

    def test_installing_writes_every_value_that_governs_the_install(self):
        """R-INS-19 — an empty section leaves the real configuration hidden in Python,
        which makes the file a menu rather than the source of truth."""
        config.ensure(self.where)

        written = json.loads(self.at.read_text())
        self.assertEqual({"at", "keep_days"}, set(written["backups"]))
        self.assertEqual({"at"}, set(written["updates"]))
        self.assertEqual({"granted"}, set(written["skills"]))
        self.assertEqual(tuple(written["skills"]["granted"]),
                         config.skills(self.where)["granted"])

    def test_the_documented_fresh_configuration_matches_the_install_seed(self):
        """R-INS-19 — an example described as complete must not omit defaults that a
        copied configuration would prevent an update from adding."""
        documented = (Path(__file__).resolve().parent.parent / "docs" /
                      "configuration.md").read_text(encoding="utf-8")
        example = documented.split("```json\n", 1)[1].split("\n```", 1)[0]

        self.assertEqual(config.INITIAL, json.loads(example))

    def test_installing_again_changes_nothing_an_owner_configured(self):
        """R-INS-19, R-AGT-4 — running the installer again is a repair, and it must not be
        how somebody loses what they set."""
        self.at.write_text('{"backups": {"keep_days": 400}}\n', encoding="utf-8")

        config.ensure(self.where)

        self.assertEqual(400, config.backups(self.where)["keep_days"])


class WhatAnUpdateAdds(WithADataDirectory):
    def test_v020s_empty_sections_are_filled_with_the_values_in_force(self):
        """R-UPD-48 — v0.20.0 wrote the names and kept the actual values hidden in code;
        carrying that file forward must make it a complete configuration."""
        self.at.write_text('{"backups": {}, "updates": {}, "skills": {}}\n',
                           encoding="utf-8")

        added = config.ensure(self.where)

        self.assertEqual(list(config.SECTIONS), added)
        self.assertEqual(config.INITIAL, json.loads(self.at.read_text()))

    def test_a_value_already_stated_survives_the_section_being_added(self):
        """R-UPD-48 — an update that rewrote the file would be an owner's configuration
        lost by a command that reported success."""
        self.at.write_text('{"backups": {"at": "23:30", "keep_days": 7}}\n', encoding="utf-8")

        config.ensure(self.where)

        self.assertEqual({"at": "23:30", "keep_days": 7},
                         json.loads(self.at.read_text())["backups"])

    def test_a_missing_value_is_added_without_touching_one_already_stated(self):
        """R-UPD-48 — migrating the empty v0.20.0 shape is key-wise: an owner may have
        filled one value before updating and that choice must survive."""
        self.at.write_text('{"backups": {"at": "23:30"}}\n', encoding="utf-8")

        config.ensure(self.where)

        self.assertEqual(
            {"at": "23:30", "keep_days": config.INITIAL["backups"]["keep_days"]},
            json.loads(self.at.read_text())["backups"],
        )

    def test_the_previous_unchanged_skill_default_is_brought_forward(self):
        """R-UPD-50, R-AGT-36 — agents on the release default receive the new common
        collaboration skills rather than keeping an accidental snapshot of an old default."""
        self.at.write_text(json.dumps({
            "skills": {"granted": list(config.PREVIOUS_DEFAULT_GRANTS[0])},
        }) + "\n", encoding="utf-8")

        changed = config.ensure(self.where)

        self.assertIn("skills", changed)
        self.assertEqual(
            config.INITIAL["skills"]["granted"],
            json.loads(self.at.read_text())["skills"]["granted"],
        )

    def test_the_immediately_previous_default_adds_workspace_guidance(self):
        """R-UPD-50, R-AGT-50, R-AGT-51 — an unchanged default remains Rundesk's
        choice and gains the new planning and organization baseline on update."""
        self.at.write_text(json.dumps({
            "skills": {"granted": list(config.PREVIOUS_DEFAULT_GRANTS[-1])},
        }) + "\n", encoding="utf-8")

        config.ensure(self.where)

        granted = json.loads(self.at.read_text())["skills"]["granted"]
        self.assertIn("writing-plans", granted)
        self.assertIn("organizing-workspaces", granted)

    def test_an_authoring_grant_follows_the_shipped_skill_rename(self):
        """R-AGT-49 — the persisted optional choice keeps meaning the same capability
        after its built-in name changes."""
        self.built_in("writing-rundesk-skills")
        self.built_in("writing-skills")
        self.at.write_text(json.dumps({
            "skills": {"granted": ["writing-rundesk-skills"]},
        }) + "\n", encoding="utf-8")

        config.ensure(self.where)

        granted = json.loads(self.at.read_text())["skills"]["granted"]
        self.assertIn("writing-skills", granted)
        self.assertNotIn("writing-rundesk-skills", granted)

    def test_required_management_grants_follow_the_shipped_renames(self):
        """R-AGT-49 — existing required choices keep their capabilities under the
        shorter backup and schedule names."""
        renamed = {
            "managing-rundesk-backups": "managing-backups",
            "managing-rundesk-schedules": "managing-schedules",
        }
        for old, new in renamed.items():
            self.built_in(old)
            self.built_in(new)
        self.at.write_text(json.dumps({
            "skills": {"granted": list(renamed)},
        }) + "\n", encoding="utf-8")

        config.ensure(self.where)

        granted = json.loads(self.at.read_text())["skills"]["granted"]
        for old, new in renamed.items():
            with self.subTest(old=old, new=new):
                self.assertNotIn(old, granted)
                self.assertEqual(1, granted.count(new))

    def test_a_management_name_collision_keeps_the_owned_previous_requirement(self):
        """R-AGT-36, R-AGT-49 — an owner package cannot become Rundesk's floor merely
        because it occupies the new spelling of a required capability."""
        old = self.built_in("managing-rundesk-backups")
        owner = self.built_in("managing-backups")
        (owner / skill.OWNED).unlink()
        self.at.write_text(json.dumps({
            "skills": {"granted": ["managing-rundesk-backups"]},
        }) + "\n", encoding="utf-8")

        config.ensure(self.where)

        granted = json.loads(self.at.read_text())["skills"]["granted"]
        self.assertIn("managing-rundesk-backups", granted)
        self.assertNotIn("managing-backups", granted)
        self.assertTrue((old / skill.OWNED).is_file())

    def test_an_owner_authoring_choice_keeps_its_name(self):
        """R-UPD-48, R-AGT-49 — matching a historical built-in name is not ownership
        proof for an owner's current package or configured choice."""
        owned = self.built_in("writing-rundesk-skills")
        (owned / skill.OWNED).unlink()
        self.at.write_text(json.dumps({
            "skills": {"granted": ["writing-rundesk-skills"]},
        }) + "\n", encoding="utf-8")

        config.ensure(self.where)

        granted = json.loads(self.at.read_text())["skills"]["granted"]
        self.assertIn("writing-rundesk-skills", granted)
        self.assertNotIn("writing-skills", granted)

    def test_an_owner_customized_skill_list_keeps_its_choices_and_the_required_floor(self):
        """R-UPD-48, R-UPD-50, R-AGT-36, R-AGT-50, R-AGT-51 — optional choices survive
        while a product-required skill is restored visibly rather than hidden policy."""
        chosen = ["managing-rundesk"]
        self.at.write_text(json.dumps({"skills": {"granted": chosen}}) + "\n",
                           encoding="utf-8")

        config.ensure(self.where)

        self.assertEqual(
            list(config.RUNDESK_REQUIRED_GRANTS),
            json.loads(self.at.read_text())["skills"]["granted"],
        )
        self.assertNotIn(
            "organizing-workspaces",
            json.loads(self.at.read_text())["skills"]["granted"],
        )
        self.assertNotIn(
            "writing-plans",
            json.loads(self.at.read_text())["skills"]["granted"],
        )

    def test_a_configuration_that_cannot_be_read_is_left_exactly_as_it_is(self):
        """R-UPD-48, R-STO-13 — refused rather than replaced. Rewriting it would turn a
        typo an owner can fix into their whole configuration silently gone."""
        was = "{ this is not json\n"
        self.at.write_text(was, encoding="utf-8")

        self.assertEqual([], config.ensure(self.where))
        self.assertEqual(was, self.at.read_text())

    def test_a_key_this_release_has_never_heard_of_is_kept(self):
        """R-UPD-48 — an install carried back to an older rundesk, or a section added by a
        release this one has not caught up with, is not ours to drop."""
        self.at.write_text('{"from-tomorrow": {"x": 1}}\n', encoding="utf-8")

        config.ensure(self.where)

        self.assertEqual({"x": 1}, json.loads(self.at.read_text())["from-tomorrow"])


class WhichSkillsANewAgentGets(WithADataDirectory):
    def test_a_new_agent_gets_the_set_written_in_the_install_configuration(self):
        """R-AGT-36 — the grant set is a value an owner can read and edit, not a hidden
        fallback that only the running code can name."""
        config.ensure(self.where)
        written = json.loads(self.at.read_text())["skills"]["granted"]
        self.assertEqual(tuple(written), config.skills(self.where)["granted"])

    def test_optional_skills_are_the_owners_to_state_above_the_required_floor(self):
        """R-AGT-36 — an owner running agents that do one job says so once, without
        removing the platform stewardship every Rundesk agent carries."""
        self.at.write_text('{"skills": {"granted": ["managing-rundesk"]}}\n', encoding="utf-8")

        self.assertEqual(config.RUNDESK_REQUIRED_GRANTS,
                         config.skills(self.where)["granted"])

    def test_an_empty_optional_list_still_keeps_the_rundesk_operating_baseline(self):
        """R-AGT-36 — empty means no owner-selected baseline, not that an agent stops
        participating in Rundesk platform stewardship."""
        self.at.write_text('{"skills": {"granted": []}}\n', encoding="utf-8")

        self.assertEqual(config.RUNDESK_REQUIRED_GRANTS,
                         config.skills(self.where)["granted"])

    def test_something_that_is_not_a_list_of_names_is_refused(self):
        """R-AGT-36 — never defaulted around: an owner who wrote a string meant something,
        and granting four skills instead is a decision made on their behalf in silence."""
        self.at.write_text('{"skills": {"granted": "managing-rundesk"}}\n', encoding="utf-8")

        with self.assertRaises(config.Unreadable):
            config.skills(self.where)

    def test_a_section_that_is_not_an_object_is_refused(self):
        """R-AGT-36 — the same, one level up."""
        self.at.write_text('{"skills": ["managing-rundesk"]}\n', encoding="utf-8")

        with self.assertRaises(config.Unreadable):
            config.skills(self.where)

    def test_a_missing_grant_list_is_refused_rather_than_defaulted_outside_the_file(self):
        """R-AGT-36 — otherwise deleting the value leaves the same behavior in force and
        proves the file never governed it."""
        self.at.write_text('{"skills": {}}\n', encoding="utf-8")

        with self.assertRaises(config.Unreadable):
            config.skills(self.where)


if __name__ == "__main__":
    unittest.main(verbosity=2)
