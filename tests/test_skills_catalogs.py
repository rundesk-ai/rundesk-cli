"""Fetching a catalog, keeping it up to date, and taking one away.

Every case here is offline. A source is a directory on this machine, or a stand-in handed in as
`fetching` — the two things that leave the machine in this product are both arguments, and the
harness has the network closed off besides, so a case that forgot fails loudly rather than quietly
depending on somebody else's uptime.

Run directly: `python3 tests/test_skills_catalogs.py`
"""

import contextlib
import io
import os
import tarfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from typing import List, Optional
from unittest import mock

from fixtures_skills import a_published_catalog, a_skill, a_tarball

import support
from rundesk.skills import catalogs, library
from rundesk.utils import archives


class Answering:
    """A stand-in for the one thing here that leaves the machine.

    Records what it was asked and answers what the case told it to, so the `ETag` round trip — the
    whole reason a daily check is cheap — can be driven without a network.
    """

    def __init__(self, trees: List[Optional[Path]], etags: Optional[List[str]] = None) -> None:
        self.trees = list(trees)
        self.etags = list(etags or [])
        self.asked: List[tuple] = []

    def __call__(self, source: str, etag: str, into: Path) -> Optional[catalogs.Brought]:
        self.asked.append((source, etag))
        tree = self.trees.pop(0)
        if tree is None:
            return None
        return catalogs.Brought(tree, self.etags.pop(0) if self.etags else "")


@contextlib.contextmanager
def _renames_failing_on(*which: int):
    """Let `os.rename` work except on the numbered calls, which fail as a full disk would.

    The only way to reach the moment a catalog's tree has been moved aside and its replacement has
    not landed. That window is one rename wide, which is exactly why nothing else can drive it and
    why it is worth driving: it is the one state where a failure leaves a directory that is no
    longer a catalog by any test.
    """
    real = os.rename
    counted = []

    def rename(source, target):
        counted.append(source)
        if len(counted) in which:
            raise OSError(f"call {len(counted)} to rename was not allowed to work")
        return real(source, target)

    with mock.patch("os.rename", rename):
        yield


class _Answered(io.BytesIO):
    """What `urlopen` hands back, as much of it as a fetch touches."""

    def __init__(self, body: bytes, etag: str) -> None:
        super().__init__(body)
        self.headers = {"ETag": etag}

    def __enter__(self) -> "_Answered":
        return self

    def __exit__(self, *why) -> bool:
        return False


class Catalogs(support.Isolated):
    """A scratch install with the library made and nothing installed."""

    def setUp(self) -> None:
        super().setUp()
        library.where().mkdir(parents=True, exist_ok=True)
        self.published = self.home / "published"

    def a_source(self, name: str = "acme", **how) -> Path:
        """A catalog published in a directory on this machine."""
        return a_published_catalog(self.published / name, name=name, **how)

    def install(self, source: Path) -> catalogs.Installed:
        with catalogs.brought(str(source)) as coming:
            return catalogs.installed(coming)


class WhereACatalogMayComeFrom(Catalogs):
    def test_a_directory_and_a_github_repository_are_the_two_shapes(self):
        self.assertEqual("", catalogs.source_trouble("https://github.com/rundesk-ai/skills"))
        self.assertEqual("", catalogs.source_trouble("https://github.com/rundesk-ai/skills.git"))
        self.assertEqual("", catalogs.source_trouble(str(self.a_source())))

    def test_anything_else_is_refused_saying_what_the_two_shapes_are(self):
        for said in ("", "   ", "git@github.com:a/b", "https://gitlab.com/a/b",
                     "https://github.com/only-one-part", "/no/such/directory"):
            with self.subTest(said=said):
                self.assertNotEqual("", catalogs.source_trouble(said))

    def test_a_file_is_told_apart_from_something_that_is_not_there(self):
        a_file = self.home / "manifest.json"
        a_file.write_text("{}", encoding="utf-8")
        self.assertIn("is a file", catalogs.source_trouble(str(a_file)))

    def test_a_repository_is_asked_for_its_tree_as_an_archive(self):
        self.assertEqual("https://api.github.com/repos/a/b/tarball",
                         catalogs.archive_url("https://github.com/a/b.git/"))


class WhatIsFetchedBeforeAnythingIsInstalled(Catalogs):
    def test_nothing_is_installed_by_fetching_and_reading(self):
        # The whole point of the split: `rundesk skills install` without --confirm shows every one
        # of these fields and changes nothing.
        with catalogs.brought(str(self.a_source())) as coming:
            self.assertTrue(coming.fresh)
            self.assertEqual("acme", coming.manifest.name)
            self.assertEqual(["writing-plans"], coming.skills)
        self.assertEqual([], library.known())

    def test_the_working_directory_is_gone_however_it_ends(self):
        held = {}
        with catalogs.brought(str(self.a_source())) as coming:
            held["at"] = coming.at
        self.assertFalse(held["at"].exists())

        with self.assertRaises(catalogs.Refused):
            with catalogs.brought(str(self.a_source(name="broken", skills=()))):
                pass

    def test_a_catalog_holding_no_skills_is_refused(self):
        # Anything that finds its own work fails when it finds none. A repository pointed at the
        # wrong branch installs silently otherwise, and the symptom arrives days later as an agent
        # that does not know something.
        with self.assertRaises(catalogs.Refused) as refused:
            with catalogs.brought(str(self.a_source(skills=()))):
                pass
        self.assertIn("declares no skills", str(refused.exception))

    def test_every_unusable_skill_is_named_rather_than_the_first(self):
        # A refusal naming one is a refusal somebody fixes and meets again. Three bad skills would
        # otherwise take three rounds to install.
        source = self.a_source()
        a_skill(source / library.INSIDE / "one", name="mismatched")
        a_skill(source / library.INSIDE / "two", description="")
        with self.assertRaises(catalogs.Refused) as refused:
            with catalogs.brought(str(source)):
                pass
        self.assertIn("2 skill", str(refused.exception))
        self.assertIn("mismatched", str(refused.exception))

    def test_a_tree_under_one_wrapper_directory_is_found(self):
        # A repository archive holds everything under a directory named for the repo and the
        # commit, so the manifest is never at the top. Driven through the whole of `brought` with an
        # archive rather than against the private that finds it, because what matters is that a real
        # published shape installs.
        archive = a_tarball(self.a_source(), self.home / "acme.tar.gz",
                            wrapper="rundesk-ai-acme-abc123")

        def fetching(_source, _etag, into):
            return catalogs.Brought(archives.unpacked(archive, into / "unpacked"), "")

        with catalogs.brought("https://github.com/rundesk-ai/acme", "", fetching) as coming:
            self.assertEqual("acme", coming.manifest.name)
            self.assertEqual(["writing-plans"], coming.skills)

    def test_a_fetch_that_is_not_a_catalog_says_what_was_expected(self):
        nothing = self.home / "not-a-catalog"
        (nothing / "src").mkdir(parents=True)
        with self.assertRaises(catalogs.Refused) as refused:
            with catalogs.brought(str(nothing)):
                pass
        self.assertIn(library.MANIFEST, str(refused.exception))


class InstallingACatalog(Catalogs):
    def test_a_catalog_lands_with_its_tree_and_a_record_of_where_it_came_from(self):
        source = self.a_source()
        did = self.install(source)
        self.assertEqual(("acme", "", "1.0.0"), (did.name, did.before, did.after))
        self.assertEqual(["acme"], library.known())
        self.assertEqual(["writing-plans"], [one.name for one in library.held("acme")])
        self.assertEqual(str(source), library.read("acme").provenance.source)

    def test_installing_one_that_is_already_there_says_to_update_it_instead(self):
        source = self.a_source()
        self.install(source)
        with self.assertRaises(catalogs.Refused) as refused:
            self.install(source)
        self.assertIn("update", str(refused.exception))

    def test_a_name_rundesk_keeps_for_itself_may_not_be_installed_under(self):
        # Policy, asked where somebody typed something — not in `installed`, which has to be able to
        # place the version-coupled catalog out of the release under exactly the name this refuses.
        # Putting it in the mechanism made it refuse its own legitimate caller.
        for name in (library.MINE, library.BUNDLED):
            with self.subTest(catalog=name):
                self.assertNotEqual("", catalogs.reserved(name))

    def test_the_catalog_that_is_fetched_is_deliberately_not_reserved(self):
        # It is installed by fetching it, which is the ordinary path. Reserving it would mean the
        # ordinary path had to go round its own rule.
        self.assertEqual("", catalogs.reserved(library.DEPENDED))
        self.assertEqual("", catalogs.reserved("acme"))

    def test_a_failure_partway_leaves_no_directory_wearing_the_catalogs_name(self):
        # Half a catalog is worse than none, because it is the one somebody reaches for.
        source = self.a_source()
        with catalogs.brought(str(source)) as coming:
            broken = coming._replace(at=coming.at / "nowhere")
            with self.assertRaises(OSError):
                catalogs.installed(broken)
        self.assertEqual([], library.known())
        self.assertFalse((library.where() / "acme").exists())
        # And the half-built thing is taken away too. Litter under a staged name is survivable — a
        # walk skips it and the next install discards it — but a failure this one *caught* is one
        # it can tidy, and leaving it means every retry after a full disk adds another copy.
        self.assertEqual([], sorted(one.name for one in library.where().iterdir()))


class CheckingACatalogForChanges(Catalogs):
    def test_the_far_end_saying_nothing_changed_fetches_nothing_and_does_nothing(self):
        # This is the whole reason a daily check is affordable: one conditional request, no body.
        source = self.a_source()
        self.install(source)
        answering = Answering([None])
        did = catalogs.update("acme", answering)
        self.assertEqual((did.before, did.after, did.retired), ("1.0.0", "1.0.0", []))
        self.assertEqual(1, len(answering.asked))

    def test_the_etag_last_seen_goes_back_out(self):
        source = self.a_source()
        with catalogs.brought(str(source)) as coming:
            catalogs.installed(coming._replace(etag='W/"first"'))
        answering = Answering([source], ['W/"second"'])
        catalogs.update("acme", answering)
        self.assertEqual('W/"first"', answering.asked[0][1])
        self.assertEqual('W/"second"', library.read("acme").provenance.etag)

    def test_a_changed_tree_replaces_the_whole_of_it_and_says_what_moved(self):
        self.install(self.a_source())
        moved = self.a_source(name="acme", version="1.1.0",
                              skills=("writing-plans", "filing-issues"))
        did = catalogs.update("acme", Answering([moved]))
        self.assertEqual(("1.0.0", "1.1.0"), (did.before, did.after))
        self.assertEqual(["filing-issues", "writing-plans"],
                         [one.name for one in library.held("acme")])

    def test_a_skill_that_left_the_catalog_is_named_rather_than_counted(self):
        # Each is a grant standing in some agent's directory that has to be taken away, and
        # somebody has to be told which.
        self.install(self.a_source(skills=("writing-plans", "filing-issues")))
        did = catalogs.update("acme", Answering([self.a_source(skills=("writing-plans",))]))
        self.assertEqual(["filing-issues"], did.retired)

    def test_a_local_edit_inside_a_catalog_is_repaired_rather_than_kept(self):
        # The repository is the source of truth. An edit inside a catalog-managed skill is drift,
        # and a check that preserved it would leave every machine slightly different.
        self.install(self.a_source())
        drifted = library.tree("acme") / library.INSIDE / "writing-plans" / library.DECLARED
        drifted.write_text("---\nname: writing-plans\ndescription: edited\n---\n", encoding="utf-8")
        (library.tree("acme") / library.INSIDE / "writing-plans" / "extra.txt").write_text(
            "mine", encoding="utf-8")
        catalogs.update("acme", Answering([self.a_source()]))
        self.assertNotIn("edited", drifted.read_text(encoding="utf-8"))
        self.assertFalse((library.tree("acme") / library.INSIDE / "writing-plans"
                          / "extra.txt").exists())

    def test_a_repository_that_renamed_itself_is_refused_rather_than_silently_moved(self):
        self.install(self.a_source())
        with self.assertRaises(catalogs.Refused) as refused:
            catalogs.update("acme", Answering([self.a_source(name="renamed")]))
        self.assertIn("renamed", str(refused.exception))

    def test_a_catalog_with_nothing_written_down_about_it_cannot_be_checked(self):
        self.install(self.a_source())
        (library.where() / "acme" / library.PROVENANCE).unlink()
        with self.assertRaises(catalogs.Refused) as refused:
            catalogs.update("acme", Answering([self.a_source()]))
        self.assertIn("where", str(refused.exception))

    def test_nothing_fetches_into_the_catalog_your_own_skills_stand_in(self):
        catalogs.place_mine()
        with self.assertRaises(catalogs.Refused):
            catalogs.update(library.MINE, Answering([self.a_source()]))

    def test_a_fetch_that_fails_leaves_the_catalog_it_found(self):
        self.install(self.a_source())
        with self.assertRaises(OSError):
            catalogs.update("acme", Answering([self.published / "gone"]))
        self.assertEqual("1.0.0", library.read("acme").manifest.version)
        self.assertEqual(["writing-plans"], [one.name for one in library.held("acme")])

    def test_a_swap_that_fails_after_moving_the_old_tree_aside_puts_it_back(self):
        # The window this closes is one rename wide and it is the only moment a catalog is not
        # standing anywhere. A failure here that did not put the tree back would leave a directory
        # that is no longer a catalog by any test, and no command that could repair it.
        self.install(self.a_source())
        with self.assertRaises(OSError):
            with _renames_failing_on(2):
                catalogs.update("acme", Answering([self.a_source(version="1.1.0")]))
        self.assertEqual("1.0.0", library.read("acme").manifest.version)
        self.assertEqual(["writing-plans"], [one.name for one in library.held("acme")])

    def test_a_swap_that_cannot_put_the_old_tree_back_says_so_in_its_own_words(self):
        # Every other failure here leaves the install exactly as it was found, and this one does
        # not. Reported in the same words as the others, it would be telling somebody nothing had
        # happened while a catalog sat half-replaced.
        self.install(self.a_source())
        with self.assertRaises(catalogs.HalfInstalled) as broken:
            with _renames_failing_on(2, 3):
                catalogs.update("acme", Answering([self.a_source(version="1.1.0")]))
        self.assertIn(library.TREE, str(broken.exception))


class TakingACatalogAway(Catalogs):
    def test_a_catalog_goes_whole_and_says_which_skills_went_with_it(self):
        self.install(self.a_source(skills=("writing-plans", "filing-issues")))
        self.assertEqual(["filing-issues", "writing-plans"], catalogs.remove("acme"))
        self.assertEqual([], library.known())
        self.assertFalse((library.where() / "acme").exists())

    def test_the_catalog_rundesk_ships_cannot_be_removed(self):
        self.assertFalse(catalogs.may_be_removed(library.BUNDLED))
        self.assertIn("depends on", catalogs.what_stays(library.BUNDLED))

    def test_the_catalog_your_own_skills_stand_in_cannot_be_removed(self):
        catalogs.place_mine()
        self.assertFalse(catalogs.may_be_removed(library.MINE))
        with self.assertRaises(catalogs.Refused) as refused:
            catalogs.remove(library.MINE)
        self.assertIn("did not write", str(refused.exception))

    def test_an_ordinary_catalog_may_be_removed(self):
        self.assertTrue(catalogs.may_be_removed("acme"))
        self.assertEqual("", catalogs.what_stays("acme"))

    def test_removing_one_that_is_not_there_is_refused(self):
        with self.assertRaises(library.Refused):
            catalogs.remove("nothing-like-this")


class TheCatalogYourOwnSkillsStandIn(Catalogs):
    def test_it_is_made_by_the_install_rather_than_by_whatever_writes_the_first_skill(self):
        # So a fresh machine has the whole shape from the first moment, and somebody looking for
        # where to put a skill of their own finds a directory rather than having to know to make one.
        self.assertTrue(catalogs.place_mine())
        self.assertEqual([library.MINE], library.known())
        self.assertTrue((library.tree(library.MINE) / library.INSIDE).is_dir())

    def test_making_it_again_changes_nothing(self):
        catalogs.place_mine()
        self.assertFalse(catalogs.place_mine())

    def test_a_skill_written_into_it_by_hand_is_found(self):
        catalogs.place_mine()
        a_skill(library.tree(library.MINE) / library.INSIDE / "my-thing")
        self.assertEqual(["my-thing"], [one.name for one in library.held(library.MINE)])


class BringingEveryCatalogUpToDate(Catalogs):
    def test_one_catalog_that_cannot_be_reached_never_stops_the_others(self):
        # An install with four catalogs where the third repository has been deleted is three
        # catalogs that are fine.
        self.install(self.a_source(name="one"))
        self.install(self.a_source(name="two"))
        (self.published / "one").rename(self.published / "one-gone")

        outcomes = {one.name: one for one in catalogs.refresh(fetching=self._per_source())}
        self.assertNotEqual("", outcomes["one"].why)
        self.assertEqual("", outcomes["two"].why)

    def test_the_catalog_your_own_skills_stand_in_is_made_and_never_fetched(self):
        outcomes = catalogs.refresh(fetching=self._per_source())
        self.assertIn(library.MINE, library.known())
        self.assertNotIn(library.MINE, [one.name for one in outcomes])

    def _per_source(self) -> catalogs.Fetching:
        """Answer each catalog from the directory it was published in, or fail as a dead repo would."""
        def fetching(source: str, _etag: str, _into: Path) -> Optional[catalogs.Brought]:
            at = Path(source)
            if not at.is_dir():
                raise OSError(f"{source} is not there any more")
            return catalogs.Brought(at, "")
        return fetching


class TheCatalogRundeskShips(Catalogs):
    def test_it_is_placed_from_the_release_rather_than_from_the_network(self):
        # A machine that cannot reach GitHub finishes installing with skills. The build this
        # replaces finished with none, and nothing said why.
        #
        # Note the signature: there is no `fetching` to pass, so nothing here *can* reach the
        # network however it is called. That is the guarantee rather than a habit.
        if not catalogs.SHIPPED.is_dir():
            self.skipTest("this release ships no bundled catalog yet")
        self.assertTrue(catalogs.place_bundled())
        self.assertIn(library.BUNDLED, library.known())
        self.assertTrue(library.held(library.BUNDLED))

    def test_it_is_never_checked_against_a_repository_at_all(self):
        # Version-coupled: what is in it is how to operate *this* rundesk, so a repository moving on
        # its own schedule must not govern it — a machine on an older release would be handed a
        # newer release's instructions.
        if not catalogs.SHIPPED.is_dir():
            self.skipTest("this release ships no bundled catalog yet")
        catalogs.place_bundled()
        self.assertFalse(catalogs.may_be_fetched(library.BUNDLED))
        self.assertEqual(str(catalogs.SHIPPED),
                         library.read(library.BUNDLED).provenance.source)

    def test_the_general_catalog_it_depends_on_is_fetched_and_undeletable(self):
        # The other half of the split: nothing in that one is coupled to a version, so it lives on
        # its own release schedule and is brought down like anybody else's.
        published = self.a_source(name=library.DEPENDED)
        self.assertTrue(catalogs.depended(Answering([published])))
        self.assertIn(library.DEPENDED, library.known())
        self.assertTrue(catalogs.may_be_fetched(library.DEPENDED))
        self.assertFalse(catalogs.may_be_removed(library.DEPENDED))

    def test_a_repository_calling_itself_something_else_is_refused(self):
        published = self.a_source(name="not-what-was-expected")
        with self.assertRaises(catalogs.Refused) as refused:
            catalogs.depended(Answering([published]))
        self.assertIn(library.DEPENDED, str(refused.exception))

    def test_a_machine_with_no_network_still_gets_the_version_coupled_catalog(self):
        # The honest failure: the general catalog is missing and says so, and the install is not
        # failed by it, because the agent already knows how to operate the thing running it.
        if not catalogs.SHIPPED.is_dir():
            self.skipTest("this release ships no bundled catalog yet")

        def unreachable(source, _etag, _into):
            raise OSError(f"{source} could not be reached")

        outcomes = {one.name: one for one in catalogs.refresh(fetching=unreachable)}
        self.assertIn(library.BUNDLED, library.known())
        self.assertTrue(library.held(library.BUNDLED))
        self.assertNotIn(library.DEPENDED, library.known())
        self.assertNotEqual("", outcomes[library.DEPENDED].why)

    def test_placing_it_again_changes_nothing(self):
        if not catalogs.SHIPPED.is_dir():
            self.skipTest("this release ships no bundled catalog yet")
        catalogs.place_bundled()
        self.assertFalse(catalogs.place_bundled())


class WhatTheRealFetchDoes(Catalogs):
    """The one function in this package that leaves the machine, with `urlopen` replaced.

    Every other case here replaces the whole of `_brought_down` through the `fetching` seam, which
    is right for testing what *depends* on a fetch and leaves the fetch itself proven by nothing.
    These are the cases that hold it — and they are worth having, because the two things it does are
    the two things the daily check rests on.
    """

    def a_repository_answering(self, etag: str = 'W/"new"'):
        """A stand-in `urlopen` handing back this case's catalog as an archive."""
        archive = a_tarball(self.a_source(), self.home / "sent.tar.gz")
        body = archive.read_bytes()
        self.asked = []

        def urlopen(request, timeout=None):
            self.asked.append(request)
            return _Answered(body, etag)
        return urlopen

    def test_the_etag_last_seen_is_sent_as_if_none_match(self):
        # Without this header the far end has no way to answer cheaply, so every daily check
        # downloads a whole archive per catalog — which is what the build this replaces did.
        working = self.home / "working"
        working.mkdir()
        with mock.patch.object(urllib.request, "urlopen", self.a_repository_answering()):
            came = catalogs._brought_down("https://github.com/a/b", 'W/"held"', working)
        self.assertEqual('W/"held"', self.asked[0].get_header("If-none-match"))
        self.assertEqual('W/"new"', came.etag)

    def test_nothing_is_sent_when_there_is_no_etag_to_send(self):
        working = self.home / "working"
        working.mkdir()
        with mock.patch.object(urllib.request, "urlopen", self.a_repository_answering()):
            catalogs._brought_down("https://github.com/a/b", "", working)
        self.assertIsNone(self.asked[0].get_header("If-none-match"))

    def test_not_modified_arrives_as_an_error_and_means_nothing_to_do(self):
        sent = []

        def urlopen(request, timeout=None):
            answered = urllib.error.HTTPError(
                request.full_url, 304, "Not Modified", {}, io.BytesIO(b""))
            sent.append(answered)
            raise answered
        with mock.patch.object(urllib.request, "urlopen", urlopen):
            self.assertIsNone(
                catalogs._brought_down("https://github.com/a/b", 'W/"held"', self.home / "w"))
        # A `304` is a response as well as an exception and it holds a connection. This path runs
        # once per catalog per day for ever, so it has to let go of what it opened.
        self.assertTrue(sent[0].closed)

    def test_any_other_refusal_from_the_far_end_is_not_swallowed(self):
        # 404 and 304 are both `HTTPError` and only one of them means "there is nothing to do". A
        # repository that has been deleted must be reported, not read as up to date for ever.
        def urlopen(request, timeout=None):
            raise urllib.error.HTTPError(
                request.full_url, 404, "Not Found", {}, io.BytesIO(b""))
        with mock.patch.object(urllib.request, "urlopen", urlopen):
            with self.assertRaises(urllib.error.HTTPError) as refused:
                catalogs._brought_down("https://github.com/a/b", "", self.home / "w")
        refused.exception.close()

    def test_a_directory_is_copied_rather_than_fetched_and_has_no_etag(self):
        # A directory being edited is one whose whole point is that the last read is stale.
        working = self.home / "working"
        came = catalogs._brought_down(str(self.a_source()), 'W/"ignored"', working)
        self.assertEqual("", came.etag)
        self.assertTrue((came.at / library.MANIFEST).is_file())

    def test_a_checkouts_own_git_directory_is_never_carried_into_the_library(self):
        source = self.a_source()
        (source / ".git").mkdir()
        (source / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
        came = catalogs._brought_down(str(source), "", self.home / "working")
        self.assertFalse((came.at / ".git").exists())


class WhatAnArchiveIsNotAllowedToDo(Catalogs):
    def test_a_member_naming_a_path_outside_is_refused(self):
        outside = self.home / "escape.tar.gz"
        inside = self.home / "a-file"
        inside.write_text("x", encoding="utf-8")
        with tarfile.open(outside, "w:gz") as writing:
            writing.add(inside, arcname="../../escaped")
        with self.assertRaises(archives.Refused):
            archives.unpacked(outside, self.home / "unpacking")

    def test_a_hard_link_pointing_outside_is_refused(self):
        # The two kinds of link do not resolve their targets the same way: a hard link's target is
        # resolved by `tarfile` against the extraction root, a symlink's by the filesystem against
        # the link's own directory. Measuring a hard link against its own parent is the check that
        # looks right and lets the escape through.
        #
        # **The target is one level up and no further, deliberately.** A member deep enough to
        # escape by either measurement would pass this case with the wrong check in place — which
        # is exactly what happened the first time it was written. Named `deep/inside` with a target
        # of `../escaped`, the two measurements disagree: from the root it lands outside, and from
        # the link's own parent it lands inside and is allowed.
        held = self.home / "hardlink.tar.gz"
        with tarfile.open(held, "w:gz") as writing:
            member = tarfile.TarInfo("deep/inside")
            member.type = tarfile.LNKTYPE
            member.linkname = "../escaped"
            writing.addfile(member)
        with self.assertRaises(archives.Refused):
            archives.unpacked(held, self.home / "unpacking")

    def test_a_symbolic_link_pointing_outside_is_refused(self):
        held = self.home / "symlink.tar.gz"
        with tarfile.open(held, "w:gz") as writing:
            member = tarfile.TarInfo("inside")
            member.type = tarfile.SYMTYPE
            member.linkname = "../escaped"
            writing.addfile(member)
        with self.assertRaises(archives.Refused):
            archives.unpacked(held, self.home / "unpacking")

    def test_a_link_that_stays_inside_is_ordinary(self):
        # The guard has to let a real catalog through: a repository may legitimately link one file
        # to another inside itself, and a check that refused those would refuse the catalog.
        held = self.home / "fine.tar.gz"
        with tarfile.open(held, "w:gz") as writing:
            real = tarfile.TarInfo("a-file")
            real.size = 0
            writing.addfile(real, io.BytesIO(b""))
            member = tarfile.TarInfo("deep/inside")
            member.type = tarfile.SYMTYPE
            member.linkname = "../a-file"
            writing.addfile(member)
        self.assertTrue(archives.unpacked(held, self.home / "unpacking").is_dir())

    def test_an_ordinary_archive_unpacks(self):
        source = self.a_source()
        archive = a_tarball(source, self.home / "acme.tar.gz")
        into = archives.unpacked(archive, self.home / "unpacking")
        self.assertTrue((into / library.MANIFEST).is_file())


if __name__ == "__main__":
    unittest.main()
