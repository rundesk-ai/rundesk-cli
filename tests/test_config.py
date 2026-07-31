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

from rundesk import config


class WithADataDirectory(unittest.TestCase):
    """A scratch data root, passed in rather than set in the environment."""

    def setUp(self):
        self.where = Path(tempfile.mkdtemp(prefix="rundesk-config-"))
        self.addCleanup(shutil.rmtree, self.where, ignore_errors=True)
        self.at = self.where / config.NAMED


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
            "skills": {"granted": list(config.PREVIOUS_DEFAULT_GRANTS)},
        }) + "\n", encoding="utf-8")

        changed = config.ensure(self.where)

        self.assertIn("skills", changed)
        self.assertEqual(
            config.INITIAL["skills"]["granted"],
            json.loads(self.at.read_text())["skills"]["granted"],
        )

    def test_an_owner_customized_skill_list_is_not_brought_to_the_new_default(self):
        """R-UPD-48, R-UPD-50 — even a strict subset of the old release default is an owner choice,
        so an update does not silently grant skills they removed."""
        chosen = ["managing-rundesk", "filing-rundesk-issues"]
        self.at.write_text(json.dumps({"skills": {"granted": chosen}}) + "\n",
                           encoding="utf-8")

        config.ensure(self.where)

        self.assertEqual(chosen, json.loads(self.at.read_text())["skills"]["granted"])

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

    def test_which_skills_a_new_agent_gets_is_the_owners_to_state(self):
        """R-AGT-36 — an owner running agents that do one job says so once."""
        self.at.write_text('{"skills": {"granted": ["managing-rundesk"]}}\n', encoding="utf-8")

        self.assertEqual(("managing-rundesk",), config.skills(self.where)["granted"])

    def test_an_empty_list_is_honoured_rather_than_read_as_saying_nothing(self):
        """R-AGT-36 — somebody who wants agents made with no skills has stated something,
        and turning it back into four is exactly the quiet override this file prevents."""
        self.at.write_text('{"skills": {"granted": []}}\n', encoding="utf-8")

        self.assertEqual((), config.skills(self.where)["granted"])

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
