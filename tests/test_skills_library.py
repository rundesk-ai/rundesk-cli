"""What makes a directory a catalog and a skill, and what is read off each.

Every rule proved here mirrors something a provider CLI enforces in silence. A skill that breaks one
is not a skill that works less well — it is one that is skipped without a word, so the only place
anybody finds out is the moment a catalog is installed.

Run directly: `python3 tests/test_skills_library.py`
"""

import unittest
from pathlib import Path

from fixtures_skills import a_catalog, a_skill, written

import support
from rundesk.skills import library


class Library(support.Isolated):
    """A scratch install with the library directory made, and nothing in it."""

    def setUp(self) -> None:
        super().setUp()
        library.where().mkdir(parents=True, exist_ok=True)

    def given(self, name: str = "acme", **how) -> Path:
        """A catalog installed under `name`."""
        return a_catalog(library.where() / name, name=name, **how)


class WhereACatalogStands(Library):
    def test_the_library_is_derived_and_never_reaches_outside_the_root(self):
        self.assertEqual(self.home / "data" / "skills", library.where())

    def test_a_name_that_would_land_the_directory_elsewhere_is_refused(self):
        for said in ("../elsewhere", "a/b", "", ".", "..", "with\0null", ".hidden"):
            with self.subTest(said=said):
                with self.assertRaises(library.Refused):
                    library.stands(said)

    def test_the_installs_own_note_cannot_also_be_a_catalog(self):
        # The library holds `README.md`, written by the install. A catalog of that name would want
        # the same path, and whichever was written second would silently be the only one left.
        self.assertIn("note", library.name_trouble(library.NOTE))

    def test_a_name_standing_on_a_link_out_of_the_library_is_refused(self):
        # Every removal below a link refuses to follow it and is individually correct, and the
        # operation still reaches a directory that has nothing to do with rundesk. The guard has to
        # be on the way in.
        somewhere = self.home / "somewhere-else"
        somewhere.mkdir()
        (library.where() / "acme").symlink_to(somewhere)
        with self.assertRaises(library.Refused):
            library.stands("acme")


class WhatASkillMayBeCalled(Library):
    def test_a_name_no_brain_would_index_is_refused(self):
        for said in ("Writing-Plans", "writing_plans", "writing plans", "-plans", "plans-",
                     "writing--plans", "wr!ting"):
            with self.subTest(said=said):
                self.assertNotEqual("", library.skill_trouble(said))

    def test_an_ordinary_name_is_taken(self):
        for said in ("writing-plans", "jira", "a", "cloudflare-dns-2"):
            with self.subTest(said=said):
                self.assertEqual("", library.skill_trouble(said))

    def test_a_name_longer_than_the_shortest_brains_limit_is_refused(self):
        self.assertEqual("", library.skill_trouble("a" * library.NAMED_LIMIT))
        self.assertNotEqual("", library.skill_trouble("a" * (library.NAMED_LIMIT + 1)))


class WhatAManifestMustSay(Library):
    def test_a_catalog_with_no_manifest_is_not_a_catalog(self):
        (library.where() / "acme" / library.TREE).mkdir(parents=True)
        with self.assertRaises(library.Refused):
            library.read_manifest(library.where() / "acme" / library.TREE)

    def test_a_schema_this_release_has_not_seen_is_refused_rather_than_read(self):
        # A hopeful reading of an unknown schema installs an empty catalog and reports success: the
        # field this release cannot see may be the one saying where the skills are.
        at = self.given()
        written(at / library.TREE / library.MANIFEST, {
            "schema": 99, "name": "acme", "version": "1.0.0", "description": "x"})
        with self.assertRaises(library.Refused) as refused:
            library.read_manifest(at / library.TREE)
        self.assertIn("99", str(refused.exception))

    def test_a_manifest_missing_any_field_names_the_field(self):
        for field in ("name", "version", "description"):
            with self.subTest(field=field):
                at = self.given()
                said = {"schema": library.SCHEMA, "name": "acme", "version": "1.0.0",
                        "description": "x"}
                del said[field]
                written(at / library.TREE / library.MANIFEST, said)
                with self.assertRaises(library.Refused) as refused:
                    library.read_manifest(at / library.TREE)
                self.assertIn(field, str(refused.exception))

    def test_an_unreadable_manifest_is_told_apart_from_a_missing_one(self):
        at = self.given()
        (at / library.TREE / library.MANIFEST).write_text("{not json", encoding="utf-8")
        with self.assertRaises(library.Refused) as refused:
            library.read_manifest(at / library.TREE)
        self.assertIn("not readable", str(refused.exception))


class WhatMakesADirectoryASkill(Library):
    def test_a_directory_with_no_skill_md_is_not_one(self):
        at = self.home / "writing-plans"
        at.mkdir()
        self.assertIn(library.DECLARED, library.trouble_with(at))

    def test_the_frontmatter_name_must_be_the_directory_name(self):
        # A brain indexes a skill by its directory. A frontmatter name that disagrees is a skill
        # that loads under a name nothing granted, on some brains and not others.
        at = a_skill(self.home / "writing-plans", name="something-else")
        self.assertIn("must agree", library.trouble_with(at))

    def test_a_skill_with_no_description_is_refused(self):
        at = a_skill(self.home / "writing-plans", description="")
        self.assertIn("description", library.trouble_with(at))

    def test_a_description_longer_than_the_limit_is_refused(self):
        at = a_skill(self.home / "writing-plans", description="x" * (library.DESCRIBED_LIMIT + 1))
        self.assertIn(str(library.DESCRIBED_LIMIT), library.trouble_with(at))

    def test_a_block_never_closed_is_not_frontmatter(self):
        at = self.home / "writing-plans"
        at.mkdir()
        (at / library.DECLARED).write_text("---\nname: writing-plans\n", encoding="utf-8")
        self.assertIn("---", library.trouble_with(at))

    def test_a_file_that_does_not_open_with_a_block_is_not_frontmatter(self):
        at = self.home / "writing-plans"
        at.mkdir()
        (at / library.DECLARED).write_text("# writing-plans\n\nJust prose.\n", encoding="utf-8")
        self.assertNotEqual("", library.trouble_with(at))

    def test_a_folded_description_is_read_whole_rather_than_truncated(self):
        # The build this replaces read only the first line, so its own shipped guide carried an
        # example its own validator would have cut in half. A description is the whole triggering
        # mechanism, and half of one is a skill that triggers on half its cases.
        at = self.home / "writing-plans"
        at.mkdir()
        (at / library.DECLARED).write_text(
            "---\nname: writing-plans\ndescription: >\n  Plan work before doing it.\n"
            "  Use when a task has three or more steps.\n---\n", encoding="utf-8")
        self.assertEqual("", library.trouble_with(at))
        self.assertEqual("Plan work before doing it. Use when a task has three or more steps.",
                         library.read_skill("acme", at).description)

    def test_a_quoted_description_has_one_layer_of_quotes_taken_off(self):
        at = self.home / "writing-plans"
        at.mkdir()
        (at / library.DECLARED).write_text(
            '---\nname: writing-plans\ndescription: "Plan work. Use when planning."\n---\n',
            encoding="utf-8")
        self.assertEqual("Plan work. Use when planning.",
                         library.read_skill("acme", at).description)


class WhichSkillsACatalogHolds(Library):
    def test_skills_are_found_rather_than_listed(self):
        # The manifest never says which skills a catalog holds. Three places agreeing about one
        # name is three places that can disagree, and every disagreement was a catalog that
        # installed and then behaved as though a skill were not there.
        at = self.given(skills=("writing-plans", "filing-issues"))
        self.assertEqual(["filing-issues", "writing-plans"], library.found(at / library.TREE / library.INSIDE))

    def test_a_directory_that_is_not_a_skill_is_passed_over_rather_than_refused(self):
        # A catalog may ship docs beside its skills, and a walk that objected would refuse most
        # real repositories.
        at = self.given()
        (at / library.TREE / library.INSIDE / "notes").mkdir()
        self.assertEqual(["writing-plans"], library.found(at / library.TREE / library.INSIDE))

    def test_a_half_written_skill_is_never_offered(self):
        at = self.given()
        a_skill(at / library.TREE / library.INSIDE / ".coming.incoming")
        self.assertEqual(["writing-plans"], library.found(at / library.TREE / library.INSIDE))

    def test_a_catalog_with_no_skills_at_all_finds_none(self):
        at = self.given(skills=())
        self.assertEqual([], library.found(at / library.TREE / library.INSIDE))

    def test_a_broken_skill_is_found_but_not_held(self):
        # Found, so that something can say what is wrong with it. Not held, because held answers a
        # listing and a listing that offered it would offer something no brain will load.
        at = self.given()
        a_skill(at / library.TREE / library.INSIDE / "broken", name="mismatched")
        self.assertEqual(["broken", "writing-plans"], library.found(at / library.TREE / library.INSIDE))
        self.assertEqual(["writing-plans"], [one.name for one in library.held("acme")])


class WhichCatalogsThereAre(Library):
    def test_an_install_with_none_says_so_rather_than_failing(self):
        self.assertEqual([], library.known())
        self.assertEqual([], library.catalogs())

    def test_a_directory_without_a_manifest_is_not_a_catalog(self):
        (library.where() / "half-made" / library.TREE).mkdir(parents=True)
        self.assertEqual([], library.known())

    def test_a_catalog_reached_through_a_link_is_never_walked(self):
        # A link here is somebody pointing the library at a directory rundesk would then feel free
        # to replace, and following one is how an update overwrites a checkout somebody was in.
        elsewhere = a_catalog(self.home / "elsewhere")
        (library.where() / "acme").symlink_to(elsewhere)
        self.assertEqual([], library.known())

    def test_a_swap_in_flight_is_never_offered(self):
        self.given()
        a_catalog(library.where() / ".acme.incoming", name="acme")
        self.assertEqual(["acme"], library.known())

    def test_one_catalog_that_cannot_be_read_does_not_hide_the_others(self):
        self.given(name="acme")
        self.given(name="broken")
        written(library.where() / "broken" / library.TREE / library.MANIFEST,
                           {"schema": 99, "name": "broken", "version": "1", "description": "x"})
        self.assertEqual(["acme", "broken"], library.known())
        self.assertEqual(["acme"], [one.name for one in library.catalogs()])


class WhatIsWrittenBesideACatalog(Library):
    def test_never_fetched_and_fetched_from_nowhere_are_different_answers(self):
        # Absent rather than blank: a caller that could not tell them apart would offer to update
        # `local`, which nothing fetches into.
        at = self.given()
        self.assertIsNone(library.read_provenance(at))

    def test_what_was_written_comes_back(self):
        at = self.given()
        said = library.Provenance("https://example.invalid/acme", 'W/"abc"', "1.0.0",
                                  library.stamped())
        library.stated_provenance(at, said)
        self.assertEqual(said, library.read_provenance(at))

    def test_an_unreadable_record_answers_none_so_a_fetch_can_repair_it(self):
        # Everything a caller does with `None` is fetch again, which rewrites this file. Raising
        # instead would leave a catalog no command could repair.
        at = self.given()
        (at / library.PROVENANCE).write_text("{not json", encoding="utf-8")
        self.assertIsNone(library.read_provenance(at))

    def test_a_record_with_no_source_is_no_record(self):
        at = self.given()
        written(at / library.PROVENANCE, {"etag": "x", "version": "1.0.0"})
        self.assertIsNone(library.read_provenance(at))


class LookingASkillUp(Library):
    def test_a_skill_is_addressed_by_its_catalog_and_its_name(self):
        self.given()
        found = library.look_up("acme/writing-plans")
        self.assertEqual(("acme", "writing-plans"), (found.catalog, found.name))
        self.assertEqual("acme/writing-plans", found.address)

    def test_a_bare_name_is_refused_and_says_where_that_name_is(self):
        # Refused rather than resolved even when only one catalog holds it: a name that is
        # unambiguous today stops being so the moment a second catalog is installed, and a command
        # that guessed would then quietly start doing something else.
        self.given(name="acme")
        self.given(name="other")
        with self.assertRaises(library.Refused) as refused:
            library.look_up("writing-plans")
        self.assertIn("acme/writing-plans", str(refused.exception))
        self.assertIn("other/writing-plans", str(refused.exception))

    def test_a_bare_name_nothing_holds_is_refused_without_a_suggestion(self):
        self.given()
        with self.assertRaises(library.Refused) as refused:
            library.look_up("nothing-like-this")
        self.assertIn(library.ADDRESS, str(refused.exception))

    def test_an_unknown_catalog_and_an_unknown_skill_are_told_apart(self):
        self.given()
        with self.assertRaises(library.Refused) as no_catalog:
            library.look_up("nope/writing-plans")
        self.assertIn("no catalog", str(no_catalog.exception))
        with self.assertRaises(library.Refused) as no_skill:
            library.look_up("acme/nope")
        self.assertIn("no skill", str(no_skill.exception))

    def test_an_address_that_would_reach_outside_the_library_is_refused(self):
        for said in ("../../etc/passwd", "acme/../../elsewhere", "/acme/x", "acme/"):
            with self.subTest(said=said):
                with self.assertRaises(library.Refused):
                    library.look_up(said)


class WhatATreeComesTo(Library):
    """`digest` — one value that changes when any of a tree does.

    Two callers ask it: has a copied grant drifted from its source, and is what came back off a
    repository the tree this install already has. Both are "did anything change", and neither can use
    a version number to answer it.
    """

    def a_tree(self, name: str = "one", **files: str) -> Path:
        at = self.home / name
        for where, said in files.items():
            one = at / where.replace("__", "/")
            one.parent.mkdir(parents=True, exist_ok=True)
            one.write_text(said, encoding="utf-8")
        return at

    def test_the_same_contents_come_to_the_same_value(self):
        first = self.a_tree("first", a="one", b__c="two")
        second = self.a_tree("second", a="one", b__c="two")
        self.assertEqual(library.digest(first), library.digest(second))

    def test_changing_a_byte_changes_it(self):
        was = library.digest(self.a_tree("first", a="one"))
        self.assertNotEqual(was, library.digest(self.a_tree("second", a="ONE")))

    def test_renaming_a_file_changes_it_though_every_byte_is_the_same(self):
        # Why the path is hashed as well as the contents. Renamed, added and removed are all changes
        # to a tree, and hashing only contents misses the first of the three entirely.
        was = library.digest(self.a_tree("first", a="one"))
        self.assertNotEqual(was, library.digest(self.a_tree("second", b="one")))

    def test_adding_a_file_changes_it(self):
        was = library.digest(self.a_tree("first", a="one"))
        self.assertNotEqual(was, library.digest(self.a_tree("second", a="one", b="")))

    def test_moving_a_file_between_directories_changes_it(self):
        was = library.digest(self.a_tree("first", a__b="one"))
        self.assertNotEqual(was, library.digest(self.a_tree("second", c__b="one")))

    def test_a_link_pointing_outside_the_tree_does_not_get_read(self):
        # Followed, a link would digest something that is not part of the tree — so a file elsewhere
        # on the machine changing would read as this tree having changed.
        at = self.a_tree("first", a="one")
        outside = self.home / "elsewhere"
        outside.write_text("first", encoding="utf-8")
        (at / "link").symlink_to(outside)
        was = library.digest(at)
        outside.write_text("second", encoding="utf-8")
        self.assertEqual(was, library.digest(at))

    def test_an_empty_directory_has_an_answer_and_it_is_not_the_answer_for_a_full_one(self):
        # Reached: a catalog whose tree is momentarily empty is asked about like any other. Compared
        # against a tree holding something rather than against another empty one, so this cannot pass
        # by everything digesting to the same value.
        empty = self.home / "empty"
        empty.mkdir()
        self.assertEqual(64, len(library.digest(empty)))
        self.assertNotEqual(library.digest(empty), library.digest(self.a_tree("full", a="one")))


if __name__ == "__main__":
    unittest.main()
