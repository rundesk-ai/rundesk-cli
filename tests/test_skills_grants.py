"""What an agent holds, and where a brain finds it.

The cases that matter here are the ones about *not* touching things: a directory somebody made by
hand, a link pointing somewhere else, a dangling link that is not ours. The build this replaces got
each of those wrong once, and each cost somebody a file.

Run directly: `python3 tests/test_skills_grants.py`
"""

import contextlib
import os
import pathlib
import shutil
import unittest
from pathlib import Path
from unittest import mock

from fixtures_skills import a_published_catalog

import support
from rundesk.agents import directory, records
from rundesk.core import paths
from rundesk.skills import catalogs, grants, library
from rundesk.utils import locking


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
        (library.inside(library.MINE) / "my-thing").symlink_to(working)

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

    def test_the_link_a_provider_would_read_is_pruned_too(self):
        # A brain reads the vendor root, not `held()`. A regression that stopped `retired` calling
        # `presented` would leave a dangling link a provider could still discover, and every case here
        # asserted only on the source of truth.
        self.grant("alan", "acme/writing-plans")
        at = directory.home("alan") / grants.VENDOR_ROOTS[0] / "writing-plans"
        self.assertTrue(at.is_symlink())
        grants.retired("acme", ["writing-plans"])
        self.assertFalse(at.is_symlink(), "a provider would still find this")

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

    def test_a_failure_to_present_is_not_an_ordinary_refusal_either(self):
        self.assertTrue(issubclass(grants.NotPresented, Exception))
        self.assertFalse(issubclass(grants.NotPresented, grants.Refused),
                         "a handler for an ordinary refusal must not be able to swallow this")

    def test_a_half_copy_is_not_an_ordinary_refusal(self):
        # Structural, because the difference only shows in a caller that does not exist yet: one
        # that catches an ordinary refusal and says "nothing changed". Declared as a `Refused` — which
        # it was — every blanket handler swallows it into that same sentence, so the distinction lives
        # in the docstring and nowhere anybody can act on. Its two siblings, `catalogs.HalfInstalled`
        # and `lifecycle.tree.HalfReplaced`, both subclass `Exception` for exactly this reason.
        self.assertTrue(issubclass(grants.HalfCopied, Exception))
        self.assertFalse(issubclass(grants.HalfCopied, grants.Refused),
                         "a handler for an ordinary refusal must not be able to swallow this")
        self.assertFalse(issubclass(catalogs.HalfInstalled, catalogs.Refused))

    def test_nothing_staged_is_left_behind_either(self):
        with self.assertRaises(OSError):
            with _replaces_failing_on(2):
                grants.refreshed()
        left = sorted(one.name for one in grants.where("alan").iterdir())
        self.assertEqual(["other-plans", "writing-plans"], left)


class HowTheLockIsHeld(Grants):
    """The nesting the new locking depends on, proven rather than assumed.

    `granted` takes the install lock and then calls `_copied`, which takes it again on the same
    thread. `locking.only_one` counts nesting per `(thread, realpath)` and yields without touching
    the `flock` the second time — so this works by construction. It is worth a case anyway, because
    it is the one thing that would deadlock rather than fail, and a deadlock in a verb somebody typed
    is the worst shape of failure this product has.
    """

    def test_an_alias_grant_takes_the_install_lock_twice_on_one_thread(self):
        self.a_catalog("other", skills=("writing-plans",))
        self.grant("alan", "acme/writing-plans")
        held = self.grant("alan", "other/writing-plans", alias="other-plans")
        self.assertTrue(held.copied)

    def test_a_grant_still_works_while_this_thread_already_holds_the_lock(self):
        # The shape a caller a layer up produces: `commands` takes the lock for a wider operation and
        # something below it takes the same lock again.
        with locking.only_one(paths.lock(), "this install", locking.WHILE_A_DIRECTORY_MOVES):
            held = self.grant("alan", "acme/writing-plans")
        self.assertEqual("acme", held.catalog)

    def test_nothing_here_writes_through_a_lock_that_takes_a_second_one(self):
        # `AGENTS.md`: take the install lock before any per-file lock, never after. The only durable
        # write inside a locked region here is `files.write_json`, which takes no lock of its own —
        # `files.changing_json` is the one that does. Asked of the text, because the failure it
        # prevents is a deadlock between two processes taking two locks in two orders, and that is
        # not something a single-process suite can produce.
        said = pathlib.Path(support.CHECKOUT / "src" / "rundesk" / "skills" / "grants.py").read_text(
            encoding="utf-8")
        self.assertNotIn("changing_json", said)


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


class WhetherAProviderCanFindIt(Grants):
    """`unseen` — a grant that landed while the linking after it did not.

    Reachable, and not hypothetically: presenting is a second lock acquisition taken after the grant
    is written, so it can be refused on its own. What it leaves behind is a skill that is correct in
    every listing and invisible to every brain, which is the worst shape a fault can have.
    """

    def setUp(self) -> None:
        super().setUp()
        self.held = self.grant("alan", "acme/writing-plans")

    def unlink(self, *roots: str) -> None:
        for root in roots:
            self.vendor("alan", root, "writing-plans").unlink()

    def test_a_presented_grant_is_missing_from_no_root(self):
        self.assertEqual([], grants.unseen(self.held))

    def test_a_grant_nothing_links_names_every_root(self):
        self.unlink(*grants.VENDOR_ROOTS)
        self.assertEqual(list(grants.VENDOR_ROOTS), grants.unseen(self.held))

    def test_one_root_tidied_by_hand_names_only_that_one(self):
        self.unlink(".grok/skills")
        self.assertEqual([".grok/skills"], grants.unseen(self.held))

    def test_a_directory_standing_where_the_link_belongs_does_not_count_as_a_link(self):
        # A brain reads a link rundesk made. Something else standing under that name is not that,
        # and `is_symlink` is what tells them apart — `exists` would have called this presented.
        at = self.vendor("alan", ".claude/skills", "writing-plans")
        at.unlink()
        at.mkdir()
        self.assertIn(".claude/skills", grants.unseen(self.held))

    def test_a_grant_pointing_at_nothing_is_not_also_reported_as_unseen(self):
        # One fault, one answer. A dangling grant is already `DANGLING`, and nothing should be linked
        # to it — reporting it as unseen as well would send somebody to repair the linking of a skill
        # that has left its catalog, where nothing they type can help.
        self.unlink(*grants.VENDOR_ROOTS)
        shutil.rmtree(library.tree("acme") / library.INSIDE / "writing-plans")
        held = grants.holding("alan", "writing-plans")
        self.assertFalse(held.resolves)
        self.assertEqual([], grants.unseen(held))

    def test_an_alias_copy_is_asked_about_by_the_name_it_stands_under(self):
        # A copy is granted under a name of its own, and the link a provider needs carries that name
        # rather than the skill's. Asked by the wrong one, every alias would read as unseen for ever.
        copied = self.grant("alan", "acme/filing-issues", "acme-issues")
        self.assertEqual([], grants.unseen(copied))
        self.vendor("alan", ".codex/skills", "acme-issues").unlink()
        self.assertEqual([".codex/skills"], grants.unseen(copied))


class BringingProviderLinksBackIntoLine(Grants):
    """The sweep is what makes `doctor`'s `UNSEEN` fix line true, so it has to really repair it."""

    def test_refreshing_puts_back_the_links_a_refused_presentation_never_made(self):
        held = self.grant("alan", "acme/writing-plans")
        for root in grants.VENDOR_ROOTS:
            self.vendor("alan", root, "writing-plans").unlink()
        said = []
        grants.refreshed(said.append)
        self.assertEqual([], grants.unseen(held))
        self.assertIn("brought 4 provider link(s) into line for alan", said)

    def test_refreshing_says_nothing_about_links_that_were_already_right(self):
        # It runs on every `rundesk update`. A line per agent per update saying nothing happened is
        # noise that teaches people to stop reading the output.
        self.grant("alan", "acme/writing-plans")
        said = []
        grants.refreshed(said.append)
        self.assertEqual([], [one for one in said if "into line" in one])

    def test_refreshing_presents_every_agent_and_not_only_the_first(self):
        directory.made("ben", "codex")
        held = [self.grant("alan", "acme/writing-plans"), self.grant("ben", "acme/writing-plans")]
        for one in held:
            for root in grants.VENDOR_ROOTS:
                (directory.home(one.agent) / root / "writing-plans").unlink()
        grants.refreshed()
        self.assertEqual([[], []], [grants.unseen(one) for one in held])


class AVendorRootHoldingSomebodyElsesLink(Grants):
    """A link under the granted name that rundesk did not make is the grant *not* standing.

    `_linked` refuses to replace one, deliberately and with a test of its own, so this state is
    reachable and it does not heal: the brain follows their link and never sees the granted skill.
    Ownership is decided by where a link points, and `unseen` asked a weaker question than the two
    functions that stand and remove links — so a foreign link read as the grant being present, and
    `doctor` said READY about a skill no provider could reach.
    """

    def setUp(self) -> None:
        super().setUp()
        self.elsewhere = self.home / "of-my-own"
        self.elsewhere.mkdir()
        at = self.vendor("alan", ".claude/skills", "writing-plans")
        at.parent.mkdir(parents=True, exist_ok=True)
        at.symlink_to(self.elsewhere)
        self.held = self.grant("alan", "acme/writing-plans")

    def test_the_foreign_link_is_left_exactly_as_it_was_found(self):
        at = self.vendor("alan", ".claude/skills", "writing-plans")
        self.assertEqual(str(self.elsewhere), os.readlink(at))

    def test_that_root_is_reported_as_holding_no_link_to_the_grant(self):
        self.assertEqual([".claude/skills"], grants.unseen(self.held))

    def test_the_roots_rundesk_did_link_are_not_reported(self):
        self.assertNotIn(".codex/skills", grants.unseen(self.held))

    def test_a_sweep_does_not_quietly_take_it_either(self):
        # The report has to stay true after the repair everything else points at: `rundesk update`
        # cannot fix this one, because fixing it would mean deleting something of theirs.
        grants.refreshed()
        self.assertEqual(str(self.elsewhere), os.readlink(
            self.vendor("alan", ".claude/skills", "writing-plans")))
        self.assertEqual([".claude/skills"], grants.unseen(self.held))


class WhichRootsHoldSomethingOfTheirOwn(Grants):
    """`taken` — the subset of `unseen` that no command rundesk has can repair."""

    def setUp(self) -> None:
        super().setUp()
        self.held = self.grant("alan", "acme/writing-plans")

    def theirs(self, root: str, broken: bool = False) -> None:
        at = self.vendor("alan", root, "writing-plans")
        if at.is_symlink():
            at.unlink()
        at.symlink_to(self.home / ("gone" if broken else "of-my-own"))

    def test_a_root_rundesk_linked_holds_nothing_of_theirs(self):
        self.assertEqual([], grants.taken(self.held))

    def test_a_root_that_is_merely_empty_holds_nothing_of_theirs(self):
        # The distinction that decides whether there is anything to type: unseen, but repairable.
        self.vendor("alan", ".grok/skills", "writing-plans").unlink()
        self.assertEqual([".grok/skills"], grants.unseen(self.held))
        self.assertEqual([], grants.taken(self.held))

    def test_a_link_of_their_own_is_named(self):
        (self.home / "of-my-own").mkdir()
        self.theirs(".claude/skills")
        self.assertEqual([".claude/skills"], grants.taken(self.held))

    def test_a_broken_link_of_their_own_still_occupies_the_name(self):
        # `exists` follows a link and answers False for a broken one — but a link to a volume that is
        # not mounted is exactly the case this module must never delete, and it holds the name either
        # way. Asked with `exists` alone, this read as a root rundesk could simply link into.
        self.theirs(".claude/skills", broken=True)
        self.assertEqual([".claude/skills"], grants.taken(self.held))

    def test_a_directory_of_their_own_is_named(self):
        at = self.vendor("alan", ".codex/skills", "writing-plans")
        at.unlink()
        at.mkdir()
        self.assertEqual([".codex/skills"], grants.taken(self.held))

    def test_a_grant_pointing_at_nothing_names_none_of_them(self):
        # `DANGLING` is its one verdict, as with `unseen`.
        shutil.rmtree(library.tree("acme") / library.INSIDE / "writing-plans")
        self.assertEqual([], grants.taken(grants.holding("alan", "writing-plans")))


class TheSkillEveryAgentHolds(Grants):
    """`rundesk/managing-rundesk` is a floor of the product, not a choice made at grant time."""

    def setUp(self) -> None:
        super().setUp()
        catalogs.place_bundled()

    def test_it_cannot_be_revoked_and_nothing_is_taken(self):
        # An agent that cannot operate the install running it answers questions about this machine
        # by guessing, and the failure is invisible — it reads as a model being unhelpful.
        grants.refreshed()
        with self.assertRaises(grants.Refused) as refused:
            grants.revoked("alan", library.REQUIRED_SKILL)
        self.assertIn("cannot be taken away", str(refused.exception))
        # Still standing, and still where every brain looks — a refusal that had already removed
        # the link would be the worst of both.
        self.assertIsNotNone(grants.holding("alan", library.REQUIRED_SKILL))
        self.assertTrue(self.vendor("alan", ".claude/skills", library.REQUIRED_SKILL).is_symlink())

    def test_a_skill_of_that_name_from_another_catalog_is_still_revocable(self):
        # Keyed on the name the grant stands under, not on where it came from — but an alias is a
        # name of its own, and nothing about the floor makes somebody else's copy undeletable.
        self.a_catalog("other", skills=(library.REQUIRED_SKILL,))
        self.grant("alan", f"other/{library.REQUIRED_SKILL}", alias="helper")
        self.assertEqual("helper", grants.revoked("alan", "helper").name)

    def test_an_agent_that_does_not_hold_it_is_told_that_first(self):
        # "You do not hold it" and "you may not take it away" are different answers, and the first
        # is true first: an agent that never had it must not be told it is undeletable.
        with self.assertRaises(grants.Refused) as refused:
            grants.revoked("alan", library.REQUIRED_SKILL)
        self.assertIn("does not hold", str(refused.exception))

    def test_the_sweep_gives_it_to_an_agent_standing_without_it(self):
        # An agent made by a release before this rule existed, and one whose grant somebody removed
        # by hand, are both repaired by the thing that already runs on every update.
        said = []
        grants.refreshed(said.append)
        self.assertIsNotNone(grants.holding("alan", library.REQUIRED_SKILL))
        self.assertTrue(any(library.REQUIRED in one for one in said))
        # And linked where a brain looks, in the same sweep rather than one update later.
        for root in grants.VENDOR_ROOTS:
            with self.subTest(root=root):
                self.assertTrue(self.vendor("alan", root, library.REQUIRED_SKILL).is_symlink())

    def test_the_sweep_aligns_the_delegation_skill_with_each_agents_scope(self):
        directory.made("bea", "claude")
        records.stated(directory.records("alan"), {"delegates_to": "[]"})
        grants.granted("alan", library.look_up(library.DELEGATING))

        said = []
        grants.refreshed(said.append)

        self.assertIsNone(grants.holding("alan", library.DELEGATING_SKILL))
        self.assertIsNotNone(grants.holding("bea", library.DELEGATING_SKILL))
        self.assertTrue(any("took" in one and "alan" in one for one in said))
        self.assertTrue(any("gave" in one and "bea" in one for one in said))

    def test_the_sweep_says_nothing_the_second_time(self):
        grants.refreshed()
        said = []
        grants.refreshed(said.append)
        self.assertEqual([], [one for one in said if library.REQUIRED in one])

    def test_a_name_somebody_else_put_there_is_left_alone(self):
        # Fills an absence, never replaces an answer — the same narrowness the pruning keeps.
        theirs = grants.where("alan") / library.REQUIRED_SKILL
        theirs.mkdir(parents=True)
        (theirs / library.DECLARED).write_text("mine\n", encoding="utf-8")
        grants.refreshed()
        self.assertEqual("mine\n", (theirs / library.DECLARED).read_text(encoding="utf-8"))

    def test_a_release_whose_catalog_no_longer_holds_it_is_not_an_error(self):
        # A release that moved the floor has nothing here to grant. Raising would turn every
        # `rundesk update` on it into a reported failure with no repair anybody could perform.
        shutil.rmtree(library.tree(library.BUNDLED) / library.INSIDE / library.REQUIRED_SKILL)
        said = []
        grants.refreshed(said.append)
        self.assertEqual([], [one for one in said if library.REQUIRED in one])
        self.assertIsNone(grants.holding("alan", library.REQUIRED_SKILL))


if __name__ == "__main__":
    unittest.main()
