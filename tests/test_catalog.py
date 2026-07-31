"""Versioned repositories of complete skills — every row of the catalog contract."""

from __future__ import annotations

import io
import json
import os
import shutil
import sys
import tarfile
import tempfile
import unittest
from unittest import mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from rundesk import catalog, skill


def a_catalog(at: Path, name="development", version="1.0.0",
              names=("python-patterns",)) -> Path:
    made = at / name
    made.mkdir(parents=True)
    declared = []
    for called in names:
        package = made / "skills" / called
        package.mkdir(parents=True)
        (package / "SKILL.md").write_text(
            f"---\nname: {called}\ndescription: Use when working with {called}.\n---\n\nDo it.\n",
            encoding="utf-8",
        )
        declared.append({"name": called, "path": f"skills/{called}"})
    (made / catalog.MANIFEST).write_text(
        json.dumps({
            "schema": 1,
            "name": name,
            "version": version,
            "description": "Development guidance.",
            "skills": declared,
        }),
        encoding="utf-8",
    )
    return made


class WithCatalogs(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="rundesk-catalog-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.catalogs = self.root / "data" / "catalogs"
        self.library = self.root / "data" / "skills"
        self.sources = self.root / "sources"
        self.sources.mkdir()

    def install(self, source):
        return catalog.install(source, self.catalogs, self.library)


class WhatACatalogIs(WithCatalogs):
    def test_a_manifest_declares_its_version_and_every_complete_skill(self):
        """R-CAT-1 — the repository contract is read rather than inferred."""
        manifest = catalog.read(a_catalog(self.sources, names=("python-patterns", "vue-patterns")))
        self.assertEqual("development", manifest.name)
        self.assertEqual("1.0.0", manifest.version)
        self.assertEqual(
            (("python-patterns", "skills/python-patterns"),
             ("vue-patterns", "skills/vue-patterns")),
            manifest.skills,
        )

    def test_one_skill_uses_the_same_manifest_contract(self):
        """R-CAT-1 — a repository never needs a second package shape for one skill."""
        manifest = catalog.read(a_catalog(self.sources))
        self.assertEqual(
            (("python-patterns", "skills/python-patterns"),),
            manifest.skills,
        )

    def test_a_future_manifest_schema_is_refused(self):
        """R-CAT-2 — an unknown contract is never read hopefully."""
        made = a_catalog(self.sources)
        said = json.loads((made / catalog.MANIFEST).read_text())
        said["schema"] = 2
        (made / catalog.MANIFEST).write_text(json.dumps(said), encoding="utf-8")
        with self.assertRaises(catalog.NotACatalog):
            catalog.read(made)

    def test_a_version_must_be_complete_semantic_versioning(self):
        """R-CAT-1 — comparisons never accept a readable prefix and ignore the rest."""
        made = a_catalog(self.sources)
        said = json.loads((made / catalog.MANIFEST).read_text())
        said["version"] = "1.0.0-not-really"
        (made / catalog.MANIFEST).write_text(json.dumps(said), encoding="utf-8")
        with self.assertRaises(catalog.NotACatalog):
            catalog.read(made)

    def test_a_skill_path_cannot_leave_the_repository(self):
        """R-CAT-2 — a repository may name only packages it contains."""
        made = a_catalog(self.sources)
        said = json.loads((made / catalog.MANIFEST).read_text())
        said["skills"][0]["path"] = "../../outside"
        (made / catalog.MANIFEST).write_text(json.dumps(said), encoding="utf-8")
        with self.assertRaises(catalog.NotACatalog):
            catalog.read(made)

    def test_a_skill_no_brain_would_index_is_refused(self):
        """R-CAT-2 — catalog skills obey the existing complete-package contract."""
        made = a_catalog(self.sources)
        (made / "skills" / "python-patterns" / "SKILL.md").unlink()
        with self.assertRaises(catalog.NotACatalog):
            catalog.read(made)


class InstallingACatalog(WithCatalogs):
    def test_installing_exposes_every_skill_without_granting_any(self):
        """R-CAT-3 — installation fills the library; grants remain an agent decision."""
        self.install(a_catalog(self.sources, names=("python-patterns", "vue-patterns")))
        self.assertEqual(["python-patterns", "vue-patterns"], sorted(skill.library(self.library)))
        self.assertEqual([], list(self.root.glob("data/agents/*/home/skills/*")))

    def test_installed_provenance_names_the_repository_and_version(self):
        """R-CAT-4 — what changes later has a source and a version now."""
        source = a_catalog(self.sources)
        landed = self.install(source)
        self.assertEqual(str(source), landed.source)
        self.assertEqual("1.0.0", landed.version)
        self.assertEqual("1.0.0", catalog.provenance(landed.at)["version"])

    def test_provenance_that_disagrees_with_the_installed_version_is_refused(self):
        """R-CAT-4 — listing cannot hide a partial or manually damaged catalog."""
        landed = self.install(a_catalog(self.sources))
        (landed.at / catalog.PROVENANCE).write_text(
            json.dumps({"source": landed.source, "version": "9.9.9"}), encoding="utf-8"
        )
        with self.assertRaises(catalog.NotACatalog):
            catalog.installed(self.catalogs)

    def test_a_catalog_skill_can_be_granted_and_revoked_through_the_library(self):
        """R-CAT-3, R-AGT-28, R-AGT-29 — catalog provenance changes no grant behavior."""
        self.install(a_catalog(self.sources))
        mine = self.root / "data" / "agents" / "ava" / "home" / "skills"
        skill.grant(mine, "python-patterns", self.library)
        self.assertEqual(["python-patterns"], skill.granted(mine))
        skill.revoke(mine, "python-patterns", self.library)
        self.assertEqual([], skill.granted(mine))

    def test_owner_authored_skill_with_same_name_refuses_install(self):
        """R-CAT-5 — an explicit repository never makes a name proof of ownership."""
        owner = self.library / "python-patterns"
        owner.mkdir(parents=True)
        (owner / "SKILL.md").write_text(
            "---\nname: python-patterns\ndescription: Mine.\n---\n", encoding="utf-8"
        )
        with self.assertRaises(catalog.InTheWay):
            self.install(a_catalog(self.sources))
        self.assertFalse(self.catalogs.exists())

    def test_a_retired_built_in_is_adopted_without_breaking_its_grant(self):
        """R-CAT-6 — existing owners move from release ownership to catalog ownership."""
        retired = self.library / "python-patterns"
        retired.mkdir(parents=True)
        (retired / "SKILL.md").write_text(
            "---\nname: python-patterns\ndescription: Old.\n---\n", encoding="utf-8"
        )
        (retired / skill.OWNED).write_text("rundesk built-in\n", encoding="utf-8")
        mine = self.root / "data" / "agents" / "ava" / "home" / "skills"
        mine.mkdir(parents=True)
        (mine / "python-patterns").symlink_to(os.path.relpath(retired, mine))
        self.install(a_catalog(self.sources))
        self.assertTrue((mine / "python-patterns" / "SKILL.md").is_file())
        self.assertEqual("development", catalog.whose(self.library / "python-patterns", self.catalogs))


class UpdatingACatalog(WithCatalogs):
    def test_refresh_seeds_the_general_catalog_for_an_existing_install(self):
        """R-CAT-11 — an upgrade gives an existing install the default collection."""
        source = a_catalog(self.sources, name=catalog.DEFAULT_NAME)

        checked = catalog.refresh(
            self.catalogs, self.library, default_source=source,
        )

        self.assertEqual(
            (catalog.Refreshed(catalog.DEFAULT_NAME, None, "1.0.0"),), checked
        )
        self.assertIn(catalog.DEFAULT_NAME, catalog.installed(self.catalogs))

    def test_refresh_checks_every_installed_repository_by_manifest_version(self):
        """R-CAT-12 — one Rundesk update checks every installed repository."""
        general = a_catalog(self.sources / "general", name=catalog.DEFAULT_NAME)
        development = a_catalog(
            self.sources / "development", name="development", names=("vue-patterns",)
        )
        catalog.install(general, self.catalogs, self.library, seeded=True)
        catalog.install(development, self.catalogs, self.library)
        for source in (general, development):
            said = json.loads((source / catalog.MANIFEST).read_text())
            said["version"] = "1.1.0"
            (source / catalog.MANIFEST).write_text(json.dumps(said), encoding="utf-8")

        checked = catalog.refresh(self.catalogs, self.library)

        self.assertEqual(
            [("development", "1.0.0", "1.1.0"),
             (catalog.DEFAULT_NAME, "1.0.0", "1.1.0")],
            [(one.name, one.before, one.after) for one in checked],
        )

    def test_one_failed_repository_does_not_keep_the_others_from_being_checked(self):
        """R-CAT-12 — repositories remain independent failure boundaries."""
        general = a_catalog(self.sources / "general", name=catalog.DEFAULT_NAME)
        development = a_catalog(
            self.sources / "development", name="development", names=("vue-patterns",)
        )
        catalog.install(general, self.catalogs, self.library, seeded=True)
        catalog.install(development, self.catalogs, self.library)
        (general / "skills" / "python-patterns" / "SKILL.md").unlink()
        said = json.loads((development / catalog.MANIFEST).read_text())
        said["version"] = "1.1.0"
        (development / catalog.MANIFEST).write_text(json.dumps(said), encoding="utf-8")

        checked = catalog.refresh(self.catalogs, self.library)

        by_name = {one.name: one for one in checked}
        self.assertIsNotNone(by_name[catalog.DEFAULT_NAME].why)
        self.assertEqual("1.1.0", by_name["development"].after)

    def test_a_newer_repository_version_replaces_every_installed_skill(self):
        """R-CAT-7 — the repository is the version and update unit."""
        self.install(a_catalog(self.sources / "old", version="1.0.0",
                               names=("python-patterns", "vue-patterns")))
        newer = a_catalog(self.sources / "new", version="1.1.0",
                          names=("python-patterns", "frontend-design"))
        landed = catalog.update(
            "development", self.catalogs, self.library,
            fetch=lambda source, work: newer,
        )
        self.assertEqual("1.1.0", landed.version)
        self.assertEqual(["frontend-design", "python-patterns"], sorted(skill.library(self.library)))

    def test_a_failed_update_leaves_the_working_version(self):
        """R-CAT-8 — a catalog update has a working version or changes nothing."""
        self.install(a_catalog(self.sources / "old", version="1.0.0"))
        broken = a_catalog(self.sources / "new", version="1.1.0")
        (broken / "skills" / "python-patterns" / "SKILL.md").unlink()
        with self.assertRaises(catalog.NotACatalog):
            catalog.update(
                "development", self.catalogs, self.library,
                fetch=lambda source, work: broken,
            )
        self.assertEqual("1.0.0", catalog.installed(self.catalogs)["development"].version)
        self.assertTrue((self.library / "python-patterns" / "SKILL.md").is_file())

    def test_a_failure_after_activation_rolls_back_files_links_and_provenance(self):
        """R-CAT-8 — failure after the swap restores the last complete release."""
        self.install(a_catalog(self.sources / "old", version="1.0.0"))
        newer = a_catalog(
            self.sources / "new", version="1.1.0",
            names=("python-patterns", "frontend-design"),
        )
        write = catalog._write_provenance
        calls = 0

        def fail_once(at, source, version, seeded=None):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise OSError("disk stopped accepting the update")
            return write(at, source, version, seeded=seeded)

        with mock.patch.object(catalog, "_write_provenance", side_effect=fail_once):
            with self.assertRaises(OSError):
                catalog.update(
                    "development", self.catalogs, self.library,
                    fetch=lambda source, work: newer,
                )
        landed = catalog.installed(self.catalogs)["development"]
        self.assertEqual("1.0.0", landed.version)
        self.assertEqual("1.0.0", catalog.provenance(landed.at)["version"])
        self.assertEqual(["python-patterns"], sorted(skill.library(self.library)))

    def test_failed_adoption_restores_the_retired_built_in(self):
        """R-CAT-6, R-CAT-8 — migration never consumes the old package on failure."""
        self.install(a_catalog(self.sources / "old", version="1.0.0"))
        retired = self.library / "frontend-design"
        retired.mkdir()
        (retired / "SKILL.md").write_text(
            "---\nname: frontend-design\ndescription: Old.\n---\n", encoding="utf-8"
        )
        (retired / skill.OWNED).write_text("rundesk built-in\n", encoding="utf-8")
        newer = a_catalog(
            self.sources / "new", version="1.1.0",
            names=("python-patterns", "frontend-design"),
        )
        write = catalog._write_provenance
        calls = 0

        def fail_once(at, source, version, seeded=None):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise OSError("disk stopped accepting the update")
            return write(at, source, version, seeded=seeded)

        with mock.patch.object(catalog, "_write_provenance", side_effect=fail_once):
            with self.assertRaises(OSError):
                catalog.update(
                    "development", self.catalogs, self.library,
                    fetch=lambda source, work: newer,
                )
        self.assertFalse(retired.is_symlink())
        self.assertEqual(
            "---\nname: frontend-design\ndescription: Old.\n---\n",
            (retired / "SKILL.md").read_text(encoding="utf-8"),
        )

    def test_an_update_cannot_remove_a_granted_skill(self):
        """R-CAT-9 — updating cannot leave an agent with a broken grant."""
        self.install(a_catalog(self.sources / "old", names=("python-patterns", "vue-patterns")))
        newer = a_catalog(self.sources / "new", version="1.1.0", names=("python-patterns",))
        with self.assertRaises(catalog.InUse):
            catalog.update(
                "development", self.catalogs, self.library, granted={"vue-patterns"},
                fetch=lambda source, work: newer,
            )


class RemovingACatalog(WithCatalogs):
    def test_uninstall_takes_back_only_the_general_catalog_rundesk_seeded(self):
        """R-CAT-11 — an automatic default has a matching automatic removal."""
        source = a_catalog(self.sources, name=catalog.DEFAULT_NAME)
        catalog.install(source, self.catalogs, self.library, seeded=True)

        removed = catalog.take_back_seeded(self.catalogs, self.library)

        self.assertEqual(["python-patterns"], removed)
        self.assertEqual({}, catalog.installed(self.catalogs))

    def test_uninstall_leaves_a_manually_installed_same_named_catalog(self):
        """R-CAT-5 — a repository an owner installed never becomes Rundesk's to remove."""
        source = a_catalog(self.sources, name=catalog.DEFAULT_NAME)
        catalog.install(source, self.catalogs, self.library)

        self.assertEqual([], catalog.take_back_seeded(self.catalogs, self.library))
        self.assertIn(catalog.DEFAULT_NAME, catalog.installed(self.catalogs))

    def test_removing_refuses_while_one_of_its_skills_is_granted(self):
        """R-CAT-9 — removal cannot leave an agent with a broken grant."""
        self.install(a_catalog(self.sources))
        with self.assertRaises(catalog.InUse):
            catalog.remove(
                "development", self.catalogs, self.library, granted={"python-patterns"}
            )
        self.assertIn("development", catalog.installed(self.catalogs))

    def test_removing_takes_only_the_catalog_and_its_library_links(self):
        """R-CAT-5 — managed removal never reaches owner-authored content."""
        self.install(a_catalog(self.sources))
        owner = self.library / "owner-skill"
        owner.mkdir()
        (owner / "SKILL.md").write_text(
            "---\nname: owner-skill\ndescription: Mine.\n---\n", encoding="utf-8"
        )
        catalog.remove("development", self.catalogs, self.library)
        self.assertFalse((self.library / "python-patterns").exists())
        self.assertTrue((owner / "SKILL.md").is_file())


class UnpackingACatalog(WithCatalogs):
    def test_an_archive_cannot_write_outside_the_unpack_directory(self):
        """R-CAT-2 — a repository archive is untrusted input."""
        archive = self.root / "escape.tar.gz"
        with tarfile.open(archive, "w:gz") as opened:
            payload = b"outside"
            member = tarfile.TarInfo("../../outside")
            member.size = len(payload)
            opened.addfile(member, io.BytesIO(payload))
        with self.assertRaises(catalog.NotACatalog):
            catalog.unpack(archive, self.root / "unpacked")
        self.assertFalse((self.root.parent / "outside").exists())


if __name__ == "__main__":
    unittest.main()
