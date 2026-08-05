"""What an agent holds, and where a brain finds it.

The cases that matter here are the ones about *not* touching things: a directory somebody made by
hand, a link pointing somewhere else, a dangling link that is not ours. The build this replaces got
each of those wrong once, and each cost somebody a file.

Run directly: `python3 tests/test_skills_grants.py`
"""

import contextlib
import os
import unittest
from pathlib import Path
from unittest import mock

from fixtures_skills import a_published_catalog

import support
from rundesk.agents import directory
from rundesk.skills import catalogs, grants, library


@contextlib.contextmanager
def _replaces_failing_on(*which: int):
    """Let `os.replace`/`os.rename` work except on the numbered calls, which fail as a full disk would."""
    real_rename = os.rename
    counted = []

    def rename(source, target):
        counted.append(source)
        if len(counted) in which:
            raise OSError(f"call {len(counted)} to rename was not allowed to work")
        return real_rename(source, target)

    with mock.patch("os.rename", rename):
        yield


class Grants(support.Isolated):
    """A scratch install with one catalog installed and one agent added."""

    def setUp(self) -> None:
        super().setUp()
        library.where().mkdir(parents=True, exist_ok=True)
        self.published = self.home / "published"
        self.a_catalog("acme", skills=("writing-plans", "filing-issues"))
        directory.made("alan", "claude")

    def a_catalog(self, name: str, **how) -> library.Catalog:
        source = a_published_catalog(self.published / name, name=name, **how)
        with catalogs.brought(str(source)) as coming:
            catalogs.installed(coming)
        return library.read(name)

    def grant(self, agent: str, address: str, alias: str = "") -> grants.Grant:
        return grants.granted(agent, library.look_up(address), alias)

    def vendor(self, agent: str, root: str, name: str) -> Path:
        return directory.home(agent) / root / name


class GivingAnAgentASkill(Grants):
    def test_a_grant_is_a_relative_link_into_the_library(self):
        # Relative, so copying an agent's whole directory to another machine does not leave every
        # grant pointing at where the first machine kept its library.
        held = self.grant("alan", "acme/writing-plans")
        self.assertTrue(held.at.is_symlink())
        self.assertFalse(os.path.isabs(os.readlink(held.at)))
        self.assertEqual(library.tree("acme") / library.INSIDE / "writing-plans",
                         held.at.resolve())

    def test_a_grant_says_which_catalog_it_came_from_without_anything_writing_it_down(self):
        held = self.grant("alan", "acme/writing-plans")
        self.assertEqual(("acme", "writing-plans"), (held.catalog, held.skill))
        self.assertEqual("acme/writing-plans", held.address)

    def test_granting_to_an_agent_that_is_not_there_is_refused_before_anything_is_written(self):
        with self.assertRaises(grants.Refused):
            self.grant("nobody", "acme/writing-plans")
        self.assertFalse((self.home / "data" / "agents" / "nobody").exists())

    def test_what_an_agent_holds_is_read_off_the_directory(self):
        self.grant("alan", "acme/writing-plans")
        self.grant("alan", "acme/filing-issues")
        self.assertEqual(["filing-issues", "writing-plans"],
                         [one.name for one in grants.held("alan")])

    def test_an_agent_holding_nothing_says_so_rather_than_failing(self):
        self.assertEqual([], grants.held("alan"))

    def test_a_grant_names_the_catalog_it_was_linked_into_and_not_wherever_the_chain_ends(self):
        # A skill in your own catalog may itself be a link into a repository you are working in —
        # which is the obvious thing to do while writing one. Following the chain to the end lands
        # outside the library, and the grant would then be unable to say which catalog it came
        # from: no listing could group it, and nothing could retire it when the catalog went.
        catalogs.place_mine()
        working = self.home / "a-repo" / "my-thing"
        working.mkdir(parents=True)
        (working / library.DECLARED).write_text(
            "---\nname: my-thing\ndescription: Mine. Use when mine.\n---\n", encoding="utf-8")
        (library.tree(library.MINE) / library.INSIDE / "my-thing").symlink_to(working)

        held = self.grant("alan", f"{library.MINE}/my-thing")
        self.assertEqual((library.MINE, "my-thing"), (held.catalog, held.skill))

    def test_something_somebody_put_there_by_hand_is_a_grant_too(self):
        # The brain will load it, so a listing that showed only rundesk's own would describe a
        # smaller set than the agent actually has.
        by_hand = grants.where("alan")
        by_hand.mkdir(parents=True)
        (by_hand / "mine").mkdir()
        (by_hand / "mine" / library.DECLARED).write_text(
            "---\nname: mine\ndescription: x\n---\n", encoding="utf-8")
        self.assertEqual(["mine"], [one.name for one in grants.held("alan")])
        self.assertEqual("", grants.held("alan")[0].catalog)


class TwoSkillsOfOneName(Grants):
    def setUp(self) -> None:
        super().setUp()
        self.a_catalog("other", skills=("writing-plans",))

    def test_the_second_is_refused_and_names_the_one_in_the_way(self):
        self.grant("alan", "acme/writing-plans")
        with self.assertRaises(grants.Refused) as refused:
            self.grant("alan", "other/writing-plans")
        self.assertIn("acme", str(refused.exception))
        self.assertIn("directory name", str(refused.exception))

    def test_two_agents_may_each_hold_a_different_one(self):
        # Nothing about the library refuses this. The collision is one agent's directory, and only
        # that.
        directory.made("ben", "grok")
        self.grant("alan", "acme/writing-plans")
        self.grant("ben", "other/writing-plans")
        self.assertEqual("acme", grants.held("alan")[0].catalog)
        self.assertEqual("other", grants.held("ben")[0].catalog)

    def test_an_alias_lets_one_agent_hold_both(self):
        self.grant("alan", "acme/writing-plans")
        held = self.grant("alan", "other/writing-plans", alias="other-plans")
        self.assertEqual(["other-plans", "writing-plans"],
                         [one.name for one in grants.held("alan")])
        self.assertEqual(("other", "writing-plans"), (held.catalog, held.skill))

    def test_an_alias_is_a_copy_with_its_name_rewritten_to_match_the_directory(self):
        # A brain indexes by the directory, so a copy whose frontmatter still said `writing-plans`
        # would be indexed under the name the alias existed to avoid.
        held = self.grant("alan", "other/writing-plans", alias="other-plans")
        self.assertTrue(held.copied)
        self.assertFalse(held.at.is_symlink())
        self.assertIn("name: other-plans",
                      (held.at / library.DECLARED).read_text(encoding="utf-8"))
        self.assertEqual("", library.trouble_with(held.at))

    def test_an_alias_that_is_not_a_name_a_brain_would_index_is_refused(self):
        with self.assertRaises(grants.Refused):
            self.grant("alan", "acme/writing-plans", alias="Other Plans")

    def test_a_refused_alias_leaves_nothing_behind_at_all(self):
        # The name is checked, then the collision, then anything is written. A refusal that has
        # already made a directory is a refusal that leaves the agent in a state nobody asked for —
        # and this agent holds nothing, so the whole skills directory should still not exist.
        with self.assertRaises(grants.Refused):
            self.grant("alan", "acme/writing-plans", alias="Other Plans")
        self.assertFalse(grants.where("alan").exists())

    def test_a_frontmatter_naming_the_skill_twice_is_caught_rather_than_copied_wrong(self):
        # The reader takes the last of two keys and the rewriter changes the first, so a source
        # written this way copies to a directory whose frontmatter still names the source. Every
        # brain would then index the copy under exactly the name the alias existed to avoid.
        # Two parsers of one block disagreeing is the bug class the check after the rewrite exists
        # for, and this is the shape it really takes.
        source = library.tree("other") / library.INSIDE / "writing-plans" / library.DECLARED
        source.write_text("---\nname: decoy\nname: writing-plans\n"
                          "description: Plan. Use when planning.\n---\n", encoding="utf-8")
        with self.assertRaises(grants.Refused) as refused:
            self.grant("alan", "other/writing-plans", alias="other-plans")
        self.assertIn("must agree", str(refused.exception))
        self.assertFalse((grants.where("alan") / "other-plans").exists())

    def test_an_alias_colliding_with_something_already_held_is_refused(self):
        self.grant("alan", "acme/writing-plans")
        with self.assertRaises(grants.Refused):
            self.grant("alan", "acme/filing-issues", alias="writing-plans")

    def test_only_the_frontmatter_name_is_rewritten_and_not_the_body(self):
        # The body here is exactly what a skill about writing skills contains: a worked example of
        # frontmatter, `name:` at the start of a line. Rewriting that would be this changing
        # somebody's documentation to suit a directory, and the skill would then teach the wrong
        # thing to every agent that read it.
        source = library.tree("other") / library.INSIDE / "writing-plans" / library.DECLARED
        source.write_text("---\nname: writing-plans\ndescription: Plan. Use when planning.\n---\n"
                          "\nWrite the frontmatter like this:\n\n```\n---\n"
                          "name: your-skill\ndescription: What it is for.\n---\n```\n",
                          encoding="utf-8")
        held = self.grant("alan", "other/writing-plans", alias="other-plans")
        said = (held.at / library.DECLARED).read_text(encoding="utf-8")
        self.assertIn("name: other-plans\n", said)
        self.assertIn("name: your-skill\n", said)
        self.assertNotIn("name: writing-plans", said)


class WhereABrainFindsIt(Grants):
    def test_every_root_a_brain_reads_gets_its_own_link_to_the_grant(self):
        self.grant("alan", "acme/writing-plans")
        for root in grants.VENDOR_ROOTS:
            with self.subTest(root=root):
                at = self.vendor("alan", root, "writing-plans")
                self.assertTrue(at.is_symlink())
                # One hop, to the grant — never straight into the library. What a brain reads is
                # the agent's own directory, and the grant is the only thing that decides what is
                # in it.
                self.assertEqual(grants.where("alan") / "writing-plans",
                                 Path(os.path.normpath(at.parent / os.readlink(at))))

    def test_a_root_is_never_a_link_to_the_whole_directory(self):
        # That would make a path the vendor owns an alias for rundesk's own, so the vendor's skill
        # installer would write into the source of truth.
        self.grant("alan", "acme/writing-plans")
        for root in grants.VENDOR_ROOTS:
            with self.subTest(root=root):
                at = directory.home("alan") / root
                self.assertTrue(at.is_dir())
                self.assertFalse(at.is_symlink())

    def test_an_agent_with_no_skills_has_no_vendor_directory_to_explain(self):
        grants.presented("alan")
        for root in grants.VENDOR_ROOTS:
            with self.subTest(root=root):
                self.assertFalse((directory.home("alan") / root).exists())

    def test_presenting_twice_writes_nothing_the_second_time(self):
        # Safe to call after everything, which is what lets every other verb call it without
        # working out whether it is needed.
        self.grant("alan", "acme/writing-plans")
        self.assertEqual([], grants.presented("alan"))

    def test_a_revoked_grant_is_taken_out_of_every_root(self):
        self.grant("alan", "acme/writing-plans")
        grants.revoked("alan", "writing-plans")
        for root in grants.VENDOR_ROOTS:
            with self.subTest(root=root):
                self.assertFalse(self.vendor("alan", root, "writing-plans").exists())
        self.assertEqual([], grants.held("alan"))

    def test_revoking_something_not_held_is_refused(self):
        with self.assertRaises(grants.Refused):
            grants.revoked("alan", "writing-plans")

    def test_a_revoke_says_which_catalog_it_came_from(self):
        # The one fact somebody needs to grant it again, and after the removal nothing is left to ask.
        self.grant("alan", "acme/writing-plans")
        self.assertEqual("acme", grants.revoked("alan", "writing-plans").catalog)


class WhatPresentingWillNotTouch(Grants):
    def setUp(self) -> None:
        super().setUp()
        self.grant("alan", "acme/writing-plans")
        self.root = directory.home("alan") / grants.VENDOR_ROOTS[0]

    def test_a_directory_somebody_wrote_by_hand_is_left_alone(self):
        theirs = self.root / "their-own"
        theirs.mkdir()
        (theirs / library.DECLARED).write_text("---\nname: their-own\ndescription: x\n---\n",
                                               encoding="utf-8")
        grants.presented("alan")
        self.assertTrue(theirs.is_dir())

    def test_a_link_pointing_somewhere_else_is_left_alone(self):
        elsewhere = self.home / "elsewhere"
        elsewhere.mkdir()
        theirs = self.root / "theirs"
        theirs.symlink_to(elsewhere)
        grants.presented("alan")
        self.assertTrue(theirs.is_symlink())

    def test_a_dangling_link_of_their_own_is_left_alone(self):
        # **Ours is decided by where a link points, not by it being broken.** An owner's link to a
        # volume that is not mounted is dangling and is not ours. The build this replaced deleted
        # any dangling link it found, and took somebody's while a drive was unplugged.
        theirs = self.root / "theirs"
        theirs.symlink_to(self.home / "a-drive-that-is-not-mounted")
        grants.presented("alan")
        self.assertTrue(theirs.is_symlink())

    def test_a_link_into_the_grants_directory_that_is_no_longer_granted_does_go(self):
        stale = self.root / "gone"
        stale.symlink_to(os.path.relpath(grants.where("alan") / "gone", self.root))
        grants.presented("alan")
        self.assertFalse(stale.is_symlink())

    def test_a_root_entry_that_is_not_ours_is_never_replaced_by_a_link(self):
        theirs = self.root / "filing-issues"
        theirs.mkdir()
        self.grant("alan", "acme/filing-issues")
        self.assertTrue(theirs.is_dir())
        self.assertFalse(theirs.is_symlink())


class WhenASkillLeavesItsCatalog(Grants):
    def test_a_grant_of_it_is_taken_away_and_the_agent_is_named(self):
        self.grant("alan", "acme/writing-plans")
        self.assertEqual({"alan": ["writing-plans"]}, grants.retired("acme", ["writing-plans"]))
        self.assertEqual([], grants.held("alan"))

    def test_a_grant_of_the_same_name_from_another_catalog_is_kept(self):
        # Matched on where the grant points rather than on its name. The name is the same and the
        # skill is not, and a match on the name would revoke the wrong one.
        self.a_catalog("other", skills=("writing-plans",))
        directory.made("ben", "grok")
        self.grant("alan", "acme/writing-plans")
        self.grant("ben", "other/writing-plans")
        grants.retired("acme", ["writing-plans"])
        self.assertEqual([], grants.held("alan"))
        self.assertEqual(["writing-plans"], [one.name for one in grants.held("ben")])

    def test_an_alias_of_a_retired_skill_goes_under_its_own_name(self):
        self.a_catalog("other", skills=("writing-plans",))
        self.grant("alan", "acme/writing-plans")
        self.grant("alan", "other/writing-plans", alias="other-plans")
        self.assertEqual({"alan": ["other-plans"]}, grants.retired("other", ["writing-plans"]))
        self.assertEqual(["writing-plans"], [one.name for one in grants.held("alan")])

    def test_nothing_going_away_touches_nothing(self):
        self.grant("alan", "acme/writing-plans")
        self.assertEqual({}, grants.retired("acme", []))
        self.assertEqual(["writing-plans"], [one.name for one in grants.held("alan")])

    def test_a_grant_whose_catalog_was_removed_still_says_where_it_came_from(self):
        # Read with `readlink` rather than `resolve`: a link whose target has gone is exactly the
        # one somebody needs told about, and resolving would lose the catalog with the path.
        self.grant("alan", "acme/writing-plans")
        catalogs.remove("acme")
        left = grants.held("alan")[0]
        self.assertFalse(left.resolves)
        self.assertEqual("acme/writing-plans", left.address)


class KeepingACopyUpToDate(Grants):
    def setUp(self) -> None:
        super().setUp()
        self.a_catalog("other", skills=("writing-plans",))
        self.grant("alan", "acme/writing-plans")
        self.held = self.grant("alan", "other/writing-plans", alias="other-plans")

    def test_a_copy_that_matches_its_source_is_not_stale(self):
        self.assertFalse(grants.stale(self.held))
        self.assertEqual([], grants.refreshed())

    def test_a_link_can_never_be_stale(self):
        # Which is the whole reason the ordinary grant is one.
        self.assertFalse(grants.stale(grants.holding("alan", "writing-plans")))

    def test_a_source_edited_without_its_version_moving_is_still_noticed(self):
        # A catalog author who edits a skill without bumping a number is the ordinary case this
        # product follows, so a version comparison would report the copy as current while it was not.
        source = library.tree("other") / library.INSIDE / "writing-plans" / library.DECLARED
        source.write_text("---\nname: writing-plans\ndescription: Different now. Use when.\n---\n",
                          encoding="utf-8")
        self.assertTrue(grants.stale(self.held))
        self.assertEqual(["alan/other-plans"], grants.refreshed())
        self.assertFalse(grants.stale(grants.holding("alan", "other-plans")))
        self.assertIn("Different now",
                      (self.held.at / library.DECLARED).read_text(encoding="utf-8"))

    def test_a_file_renamed_in_the_source_is_noticed(self):
        # Same bytes, different name. Hashing only contents would miss a rename, a move and half of
        # what an author does between two versions of a skill — and the copy would go on standing
        # with the old layout while reporting itself current.
        reference = library.tree("other") / library.INSIDE / "writing-plans" / "notes.md"
        reference.write_text("the same words", encoding="utf-8")
        grants.refreshed()
        self.assertFalse(grants.stale(grants.holding("alan", "other-plans")))
        reference.rename(reference.with_name("guidance.md"))
        self.assertTrue(grants.stale(grants.holding("alan", "other-plans")))

    def test_a_file_added_to_the_source_is_noticed(self):
        (library.tree("other") / library.INSIDE / "writing-plans" / "references").mkdir()
        (library.tree("other") / library.INSIDE / "writing-plans" / "references"
         / "more.md").write_text("more", encoding="utf-8")
        self.assertTrue(grants.stale(self.held))
        grants.refreshed()
        self.assertTrue((self.held.at / "references" / "more.md").is_file())

    def test_a_copy_whose_source_has_gone_is_not_reported_stale(self):
        # It is dangling, which is a different thing and a different answer. Making it again is
        # impossible and reporting it as out of date would send somebody to a command that cannot help.
        catalogs.remove("other")
        self.assertFalse(grants.stale(self.held))

    def test_a_copy_whose_record_has_gone_is_no_longer_rundesks_to_remake(self):
        # Without the record nothing says rundesk put this directory here, so it reads as something
        # the owner made — and remaking it would overwrite work this cannot prove is its own. The
        # same reasoning as the narrow pruning, and the safe direction of the two.
        (self.held.at / grants.RECORD).unlink()
        left = grants.holding("alan", "other-plans")
        self.assertFalse(left.copied)
        self.assertFalse(grants.stale(left))
        self.assertEqual([], grants.refreshed())
        self.assertTrue((self.held.at / library.DECLARED).is_file())

    def test_a_record_written_before_digests_existed_makes_the_copy_again(self):
        (self.held.at / grants.RECORD).write_text(
            '{"catalog": "other", "skill": "writing-plans", "as": "other-plans"}', encoding="utf-8")
        self.assertTrue(grants.stale(grants.holding("alan", "other-plans")))
        self.assertEqual(["alan/other-plans"], grants.refreshed())

    def test_a_remade_copy_still_wears_its_alias(self):
        source = library.tree("other") / library.INSIDE / "writing-plans" / library.DECLARED
        source.write_text("---\nname: writing-plans\ndescription: Moved on. Use when.\n---\n",
                          encoding="utf-8")
        grants.refreshed()
        self.assertIn("name: other-plans",
                      (self.held.at / library.DECLARED).read_text(encoding="utf-8"))


class WhenRemakingACopyFails(Grants):
    """The copy is the one grant that can be lost, so it is the one that has to survive failing."""

    def setUp(self) -> None:
        super().setUp()
        self.a_catalog("other", skills=("writing-plans",))
        self.grant("alan", "acme/writing-plans")
        self.held = self.grant("alan", "other/writing-plans", alias="other-plans")
        self.was = (self.held.at / library.DECLARED).read_text(encoding="utf-8")
        source = library.tree("other") / library.INSIDE / "writing-plans" / library.DECLARED
        source.write_text("---\nname: writing-plans\ndescription: Moved on. Use when.\n---\n",
                          encoding="utf-8")

    def test_the_copy_that_was_working_is_still_there(self):
        # An earlier version deleted the standing copy and *then* renamed the replacement in, so a
        # rename that failed left the agent with no skill at all where one had been working a moment
        # before — and nothing to report it, because a grant that is gone cannot be dangling. This
        # runs on every update for every stale alias, which is the shape of thing that has to survive.
        with self.assertRaises(OSError):
            with _replaces_failing_on(2):
                grants.refreshed()
        left = grants.holding("alan", "other-plans")
        self.assertIsNotNone(left)
        self.assertEqual(self.was, (left.at / library.DECLARED).read_text(encoding="utf-8"))
        self.assertEqual("", library.trouble_with(left.at))

    def test_a_copy_that_cannot_be_put_back_says_so_in_its_own_words(self):
        with self.assertRaises(grants.HalfCopied) as broken:
            with _replaces_failing_on(2, 3):
                grants.refreshed()
        self.assertIn("other-plans", str(broken.exception))

    def test_nothing_staged_is_left_behind_either(self):
        with self.assertRaises(OSError):
            with _replaces_failing_on(2):
                grants.refreshed()
        left = sorted(one.name for one in grants.where("alan").iterdir())
        self.assertEqual(["other-plans", "writing-plans"], left)


class WhatAVendorRootAlreadyHolds(Grants):
    def test_a_link_of_their_own_under_a_granted_name_is_not_replaced(self):
        # `_pruned` will not remove a link rundesk did not make, and this is the same rule on the way
        # in. Replacing on a name collision alone was the one place this module took something it had
        # not put there, and it contradicted the rule its own docstring states.
        root = directory.home("alan") / grants.VENDOR_ROOTS[0]
        root.mkdir(parents=True)
        elsewhere = self.home / "somewhere-of-mine"
        elsewhere.mkdir()
        theirs = root / "writing-plans"
        theirs.symlink_to(elsewhere)

        self.grant("alan", "acme/writing-plans")
        self.assertTrue(theirs.is_symlink())
        self.assertEqual(elsewhere, theirs.resolve())

    def test_our_own_link_is_still_corrected_when_it_points_at_the_wrong_thing(self):
        # The other half: a link that *does* point into this agent's own grants is ours, and a stale
        # one is repaired rather than left.
        self.grant("alan", "acme/writing-plans")
        root = directory.home("alan") / grants.VENDOR_ROOTS[0]
        ours = root / "writing-plans"
        ours.unlink()
        ours.symlink_to(os.path.relpath(grants.where("alan") / "something-else", root))
        grants.presented("alan")
        self.assertEqual(grants.where("alan") / "writing-plans",
                         Path(os.path.normpath(ours.parent / os.readlink(ours))))


if __name__ == "__main__":
    unittest.main()
