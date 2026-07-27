#!/usr/bin/env python3
"""Where this install stands against what is published, and what it does about it.

Offline throughout: the updater takes "what is published" and "how to apply it" as
arguments, so the decision — the part that is easy to get wrong — is tested without
a network, and the tarball handling is not what these assertions rest on.

Run: python3 tests/test_updater.py
"""

from __future__ import annotations

import io
import contextlib
import os
import sys
import urllib.error
import tarfile
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from rundesk import updater  # noqa: E402


def run(**kwargs) -> tuple[int, str]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = updater.run(**kwargs)
    return code, out.getvalue()


class VersionTests(unittest.TestCase):
    def test_a_version_is_read_with_or_without_its_v(self):
        self.assertEqual(updater.parse_version("v1.2.3"), (1, 2, 3))
        self.assertEqual(updater.parse_version("1.2"), (1, 2, 0))
        self.assertEqual(updater.parse_version("0.1.0"), (0, 1, 0))

    def test_something_that_is_not_a_version_is_not_guessed_at(self):
        self.assertIsNone(updater.parse_version("nightly"))
        self.assertIsNone(updater.parse_version(""))

    def test_newer_is_compared_by_number_and_not_by_text(self):
        # "0.10.0" sorts before "0.9.0" as text, and is after it as a version.
        self.assertTrue(updater.is_newer("0.10.0", "0.9.0"))
        self.assertFalse(updater.is_newer("0.9.0", "0.10.0"))
        self.assertFalse(updater.is_newer("1.0.0", "1.0.0"))

    def test_a_version_that_cannot_be_read_never_claims_an_update(self):
        # Saying "behind" on a garbled tag sends someone chasing a release that
        # does not exist, which is worse than saying nothing.
        self.assertFalse(updater.is_newer("nightly", "0.1.0"))
        self.assertFalse(updater.is_newer("0.2.0", "who-knows"))


class OutcomeTests(unittest.TestCase):
    def test_up_to_date_says_so_and_changes_nothing(self):
        applied: list[str] = []
        code, said = run(
            repo_root=Path("/nowhere"),
            current_version="1.0.0",
            latest=lambda: ("v1.0.0", None),
            apply=lambda root, tag: applied.append(tag) or 0,
        )
        self.assertEqual(code, 0)
        self.assertIn("UP TO DATE", said)
        self.assertEqual(applied, [], "an up-to-date install was updated anyway")

    def test_being_behind_moves_the_install(self):
        applied: list[str] = []
        code, said = run(
            repo_root=Path("/nowhere"),
            current_version="0.1.0",
            latest=lambda: ("v0.2.0", None),
            apply=lambda root, tag: applied.append(tag) or 0,
        )
        self.assertEqual(code, 0)
        self.assertIn("v0.2.0", said)
        self.assertEqual(applied, ["v0.2.0"])

    def test_check_only_reports_and_changes_nothing(self):
        applied: list[str] = []
        code, said = run(
            repo_root=Path("/nowhere"),
            current_version="0.1.0",
            latest=lambda: ("v0.2.0", None),
            check_only=True,
            apply=lambda root, tag: applied.append(tag) or 0,
        )
        self.assertEqual(code, 0)
        self.assertIn("v0.2.0", said)
        self.assertEqual(applied, [], "--check moved the install")

    def test_an_unreachable_forge_is_reported_as_unknown_never_as_current(self):
        # "up to date" when we simply could not ask is the one answer that would
        # leave someone on an old version believing they are current.
        code, said = run(repo_root=Path("/nowhere"), current_version="0.1.0", latest=lambda: (None, updater.UNREACHABLE))
        self.assertEqual(code, 1)
        self.assertIn("UNKNOWN", said)
        self.assertNotIn("UP TO DATE", said)


class ArchiveTests(unittest.TestCase):
    def test_an_archive_cannot_write_outside_where_it_is_unpacked(self):
        # A release archive is untrusted input; a member with a path that escapes
        # the destination is how an update becomes an arbitrary write.
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            nasty = root / "nasty.tar"
            payload = root / "payload"
            payload.write_text("x")
            with tarfile.open(nasty, "w") as tar:
                tar.add(payload, arcname="../escaped.txt")

            dest = root / "dest"
            dest.mkdir()
            with tarfile.open(nasty) as tar:
                with self.assertRaises(ValueError):
                    updater._safe_extract(tar, dest)
            self.assertFalse((root / "escaped.txt").exists(), "the archive wrote outside its destination")

    def test_an_archive_cannot_write_through_a_link_that_points_outside(self):
        # The second way out, and the one the name check cannot see: a symlink aimed out of
        # the tree, then a file whose path runs through it. When the names are checked
        # nothing has been extracted yet, so there is no link there for resolve() to follow.
        # The standard library only began refusing this by default in 3.14; on 3.9, the
        # floor this project supports, an archive shaped this way wrote wherever it liked.
        for label, linkname in [("absolute", None), ("relative", "../../outside")]:
            with self.subTest(link=label):
                with tempfile.TemporaryDirectory() as work:
                    root = Path(work)
                    outside = root / "outside"
                    outside.mkdir()
                    dest = root / "dest"
                    dest.mkdir()

                    nasty = root / "nasty.tar"
                    with tarfile.open(nasty, "w") as tar:
                        link = tarfile.TarInfo("release/escape")
                        link.type = tarfile.SYMTYPE
                        link.linkname = linkname if linkname else str(outside)
                        tar.addfile(link)
                        body = b"PWNED"
                        through = tarfile.TarInfo("release/escape/authorized_keys")
                        through.size = len(body)
                        tar.addfile(through, io.BytesIO(body))

                    with tarfile.open(nasty) as tar:
                        with self.assertRaises(ValueError):
                            updater._safe_extract(tar, dest)
                    self.assertFalse((outside / "authorized_keys").exists(),
                                     "the archive wrote outside its destination through a link")



class BehindTests(unittest.TestCase):
    """Whether this install can tell it is behind — the question the whole module exists for."""

    def test_the_version_in_the_code_is_one_that_can_be_compared(self):
        # If `__version__` were ever something unparseable — "dev", "0.1.0-rc" is fine, "next"
        # is not — `is_newer` would answer False forever and this install would never learn it
        # was behind. Nothing else in the suite would notice.
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
        from rundesk import __version__

        self.assertIsNotNone(
            updater.parse_version(__version__),
            f"__version__ is {__version__!r}, which cannot be compared to a release tag",
        )

    def test_a_published_tag_is_compared_against_a_bare_local_version(self):
        # The shape this actually takes in the wild: GitHub says "v0.2.0", the code says "0.1.0".
        # A comparison that tripped on the v would report every release as not-newer.
        self.assertTrue(updater.is_newer("v0.2.0", "0.1.0"))
        self.assertTrue(updater.is_newer("v0.1.1", "0.1.0"))
        self.assertFalse(updater.is_newer("v0.1.0", "0.1.0"))
        self.assertFalse(updater.is_newer("v0.0.9", "0.1.0"))

    def test_being_behind_is_said_in_words_that_name_the_way_out(self):
        said = updater.describe("0.1.0", "v0.2.0")
        self.assertIn("v0.2.0", said)
        self.assertIn("rundesk update", said, "it says you are behind without saying what to do")

    def test_each_of_the_three_answers_is_distinguishable(self):
        behind = updater.describe("0.1.0", "v0.2.0")
        current = updater.describe("0.1.0", "v0.1.0")
        unknown = updater.describe("0.1.0", None)
        self.assertEqual(len({behind, current, unknown}), 3, "two different situations read the same")
        self.assertNotIn("UP TO DATE", unknown)


def _release(root: Path, version: str) -> Path:
    """A tree shaped like a release archive, unpacked."""
    top = root / f"rundesk-cli-{version}"
    (top / "src" / "rundesk").mkdir(parents=True)
    (top / "rundesk").write_text(f"#!/usr/bin/env python3\n# {version}\n")
    (top / "install.sh").write_text(f"#!/usr/bin/env bash\n# {version}\n")
    (top / "README.md").write_text(f"rundesk {version}\n")
    (top / "src" / "rundesk" / "__init__.py").write_text(f'__version__ = "{version}"\n')
    return top


class InterruptedUpdateTests(unittest.TestCase):
    """What is on disk when an update stops halfway.

    The likeliest real failure is not a hostile archive, it is Ctrl-C or a full disk. The
    shape this replaces removed each directory before copying the new one in, so `src/
    rundesk` — the package implementing update, version and uninstall — was absent for
    the length of a copy. A kill inside that window left nothing able to repair itself.
    """

    def setUp(self):
        self._work = tempfile.TemporaryDirectory()
        self.root = Path(self._work.name)
        self.install = self.root / "install"
        (self.install / "src" / "rundesk").mkdir(parents=True)
        (self.install / "rundesk").write_text("# 0.1.0\n")
        (self.install / "src" / "rundesk" / "__init__.py").write_text('__version__ = "0.1.0"\n')
        (self.install / "src" / "rundesk" / "cli.py").write_text("# 0.1.0 surface\n")

    def tearDown(self):
        self._work.cleanup()

    def _dies_on(self, victim: str):
        """A copy that fails the moment it reaches `victim` — a disk filling up, or a kill."""
        real = updater.shutil.copytree

        def falls_over(src, dst, *a, **kw):
            if Path(src).name == victim:
                raise OSError(28, "No space left on device")
            return real(src, dst, *a, **kw)

        return falls_over

    def test_an_update_that_stops_partway_leaves_the_command_able_to_run(self):
        original = updater.shutil.copytree
        updater.shutil.copytree = self._dies_on("src")
        try:
            with self.assertRaises(OSError):
                updater._copy_over(_release(self.root, "0.2.0"), self.install)
        finally:
            updater.shutil.copytree = original

        package = self.install / "src" / "rundesk"
        self.assertTrue((package / "__init__.py").is_file(),
                        "an interrupted update left the package it needs to run missing")
        self.assertTrue((package / "cli.py").is_file(),
                        "an interrupted update left the command surface missing")
        self.assertIn('"0.1.0"', (package / "__init__.py").read_text(),
                      "an interrupted update left a half-written version on disk")

    def test_an_update_that_stops_partway_leaves_nothing_of_itself_behind(self):
        original = updater.shutil.copytree
        updater.shutil.copytree = self._dies_on("src")
        try:
            with self.assertRaises(OSError):
                updater._copy_over(_release(self.root, "0.2.0"), self.install)
        finally:
            updater.shutil.copytree = original

        litter = [p.name for p in self.install.iterdir()
                  if p.name.startswith(".") and (".incoming" in p.name or ".outgoing" in p.name)]
        self.assertEqual(litter, [], f"an interrupted update left staging paths behind: {litter}")

    def _renaming_dies_on(self, victim: str, and_putting_back: str = ""):
        """A rename that refuses one target — the swap loop failing part of the way through.

        Staging is complete by then, so this is the window the copytree cases above cannot
        reach: some paths are already the new release and the rest are still the old one.
        """
        real = updater.os.rename

        def falls_over(src, dst, *a, **kw):
            # Only the move *into* place: what was there has already been set aside by
            # then, so this is a swap that failed with the old thing still recoverable.
            if Path(dst).name == victim and Path(src).name.endswith(".incoming"):
                raise OSError(28, "No space left on device")
            # And, when asked for, the move that would put one of them back.
            if and_putting_back and Path(src).name == f".{and_putting_back}.outgoing":
                raise OSError(28, "No space left on device")
            return real(src, dst, *a, **kw)

        return falls_over

    def test_an_update_that_replaced_only_part_of_a_release_puts_back_what_was_there(self):
        """R-UPD-25 — each swap is atomic and the loop over them was not. A release ships
        `README.md`, `install.sh`, `rundesk` and `src` in that order, so failing on the last
        left three of them new and one old: `rundesk` from one version and its package from
        another, which the caller then brought every gateway back onto."""
        original = updater.os.rename
        updater.os.rename = self._renaming_dies_on("src")
        try:
            with self.assertRaises(OSError):
                updater._copy_over(_release(self.root, "0.2.0"), self.install)
        finally:
            updater.os.rename = original

        self.assertIn("# 0.1.0", (self.install / "rundesk").read_text(),
                      "the entry point was left on the release that never finished landing")
        self.assertIn('"0.1.0"', (self.install / "src" / "rundesk" / "__init__.py").read_text(),
                      "the package was left on a different version from the entry point")
        self.assertFalse((self.install / "README.md").exists(),
                         "a file only the new release ships was left behind")
        self.assertFalse((self.install / "install.sh").exists(),
                         "a file only the new release ships was left behind")
        litter = [p.name for p in self.install.iterdir() if p.name.startswith(".")]
        self.assertEqual(litter, [], f"a reverted update left staging paths behind: {litter}")

    def test_an_install_that_could_not_be_put_back_says_so_rather_than_reporting_a_failure(self):
        """R-UPD-25 — the one outcome running it again cannot mend. An install that is
        neither version must not be reported in the same words as one that is simply still
        the old version, because those two need completely different things of a person."""
        original = updater.os.rename
        updater.os.rename = self._renaming_dies_on("src", and_putting_back="rundesk")
        try:
            with self.assertRaises(updater.HalfReplaced) as stopped:
                updater._copy_over(_release(self.root, "0.2.0"), self.install)
        finally:
            updater.os.rename = original
        self.assertIn("rundesk", str(stopped.exception), "it never said what was left stuck")


class OneAtATimeTests(unittest.TestCase):
    """Two updates at once each replace what the other is halfway through reading."""

    def setUp(self):
        self._work = tempfile.TemporaryDirectory()
        self.install = Path(self._work.name)

    def tearDown(self):
        self._work.cleanup()

    def test_an_update_refuses_while_another_is_already_running(self):
        # The work is stubbed rather than merely expected not to happen: if the lock ever
        # stops holding, this fails on the stub having been called instead of quietly
        # reaching for the network the way the real one would.
        started = []
        original = updater._download_and_apply

        def should_not_run(*args, **kw):
            started.append(args)
            return 0

        updater._download_and_apply = should_not_run
        try:
            with updater._only_one(self.install):
                # The error stream, because that is where a refusal belongs and where
                # every other verb puts one.
                with contextlib.redirect_stderr(io.StringIO()) as said:
                    code = updater.download_and_apply(self.install, "v9.9.9")
        finally:
            updater._download_and_apply = original

        self.assertEqual(started, [], "a second update began while the first held the install")
        self.assertEqual(code, 1, "a refused update reported success")
        self.assertIn("already running", said.getvalue())

    def test_an_update_that_finishes_leaves_the_way_clear_for_the_next(self):
        # A lock that outlives the process holding it is worse than none: every later
        # update refuses, and the only way out is deleting a file nobody mentioned.
        with updater._only_one(self.install):
            pass
        with updater._only_one(self.install):
            pass  # would raise Busy if the first had not let go


class ReplacesTheInstallTests(unittest.TestCase):
    """An update has to actually replace what is on disk — and leave what is not its business."""

    def setUp(self):
        self._work = tempfile.TemporaryDirectory()
        self.root = Path(self._work.name)
        # An install as it stands before the update: older content, plus things a release
        # does not ship and must not lose.
        self.install = self.root / "install"
        (self.install / "src" / "rundesk").mkdir(parents=True)
        (self.install / "rundesk").write_text("# 0.1.0\n")
        (self.install / "src" / "rundesk" / "__init__.py").write_text('__version__ = "0.1.0"\n')
        (self.install / "src" / "rundesk" / "gone_next_release.py").write_text("# removed upstream\n")
        (self.install / ".git").mkdir()
        (self.install / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
        (self.install / "local-note.txt").write_text("mine\n")

    def tearDown(self):
        self._work.cleanup()

    def test_the_new_release_replaces_what_was_there(self):
        updater._copy_over(_release(self.root, "0.2.0"), self.install)

        self.assertIn("0.2.0", (self.install / "rundesk").read_text(), "the entry point was not replaced")
        self.assertIn(
            '"0.2.0"',
            (self.install / "src" / "rundesk" / "__init__.py").read_text(),
            "the version on disk still reports the old release",
        )
        self.assertTrue((self.install / "README.md").exists(), "a file new in the release never arrived")

    def test_a_directory_is_replaced_rather_than_merged(self):
        # A module deleted upstream must not survive inside the new tree, still importable.
        updater._copy_over(_release(self.root, "0.2.0"), self.install)
        self.assertFalse(
            (self.install / "src" / "rundesk" / "gone_next_release.py").exists(),
            "a file removed upstream survived the update and is still importable",
        )

    def test_what_the_release_does_not_ship_is_left_alone(self):
        # The checkout's own git directory, and anything the owner put beside it.
        updater._copy_over(_release(self.root, "0.2.0"), self.install)
        self.assertTrue((self.install / ".git" / "HEAD").exists(), "the update destroyed the git directory")
        self.assertEqual((self.install / "local-note.txt").read_text(), "mine\n")

    def test_the_entry_point_and_installer_come_out_executable(self):
        # Copied without the bit, `rundesk` is on PATH and answers EACCES — installed, and dead.
        updater._copy_over(_release(self.root, "0.2.0"), self.install)
        for name in ("rundesk", "install.sh"):
            self.assertTrue(os.access(self.install / name, os.X_OK), f"{name} came out not executable")


class DownloadTests(unittest.TestCase):
    """The whole path: fetch a tag, unpack it, and lay it over the install."""

    def test_a_release_is_downloaded_unpacked_and_laid_over_the_install(self):
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            install = root / "install"
            (install / "src" / "rundesk").mkdir(parents=True)
            (install / "rundesk").write_text("# 0.1.0\n")

            staged = root / "staged"
            staged.mkdir()
            _release(staged, "0.2.0")
            archive = root / "release.tar.gz"
            with tarfile.open(archive, "w:gz") as tar:
                tar.add(staged / "rundesk-cli-0.2.0", arcname="rundesk-cli-0.2.0")

            served = archive.read_bytes()
            code, said = _with_download(served, lambda: updater.download_and_apply(install, "v0.2.0"))

            self.assertEqual(code, 0, said)
            self.assertIn("0.2.0", (install / "rundesk").read_text(), "the install was not replaced")
            self.assertIn("v0.2.0: UPDATED", said)

    def test_a_download_that_fails_leaves_the_install_as_it_was(self):
        with tempfile.TemporaryDirectory() as work:
            install = Path(work) / "install"
            install.mkdir()
            (install / "rundesk").write_text("# 0.1.0\n")

            code, said = _with_download(urllib.error.URLError("no route to host"),
                                        lambda: updater.download_and_apply(install, "v0.2.0"))

            self.assertEqual(code, 1)
            self.assertIn("FAILED", said)
            self.assertEqual((install / "rundesk").read_text(), "# 0.1.0\n", "a failed update still changed the install")


def _with_download(payload, call):
    """Run `call` with the network replaced by `payload` — bytes to serve, or an error to raise."""
    class _Response:
        def __init__(self, data): self._data = data
        def read(self): return self._data
        def __enter__(self): return self
        def __exit__(self, *_): return False

    def fake_urlopen(_request, timeout=None):
        if isinstance(payload, Exception):
            raise payload
        return _Response(payload)

    real = updater.urllib.request.urlopen
    updater.urllib.request.urlopen = fake_urlopen
    out, err = io.StringIO(), io.StringIO()
    try:
        # Both streams: what went wrong is reported on the error stream, like every
        # other verb, and a helper that only watched one would miss it.
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = call()
    finally:
        updater.urllib.request.urlopen = real
    return code, out.getvalue() + err.getvalue()


class AskingTheForgeTests(unittest.TestCase):
    """The one function that actually talks to GitHub — stubbed everywhere else, so tested here."""

    def test_the_published_tag_is_read_out_of_the_release(self):
        (tag, why), _ = _with_json(b'{"tag_name": "v0.4.0", "name": "0.4.0"}',
                                   updater.latest_version_online)
        self.assertEqual(tag, "v0.4.0")
        self.assertIsNone(why, "a look-up that worked still said why it had not")

    def test_a_release_with_no_tag_is_not_turned_into_one(self):
        # A shape we did not expect must read as "could not tell", never as a version.
        for payload in (b'{}', b'{"tag_name": ""}', b'{"tag_name": null}', b'[]'):
            with self.subTest(payload=payload):
                (tag, _why), _ = _with_json(payload, updater.latest_version_online)
                self.assertIsNone(tag)

    def test_a_forge_that_cannot_be_reached_says_nothing_rather_than_guessing(self):
        for boom in (urllib.error.URLError("no route"), TimeoutError(), OSError("refused")):
            with self.subTest(boom=type(boom).__name__):
                (tag, _why), _ = _with_json(boom, updater.latest_version_online)
                self.assertIsNone(tag)

    def test_a_reply_that_is_not_json_is_survived(self):
        (tag, _why), _ = _with_json(b"<html>rate limited</html>", updater.latest_version_online)
        self.assertIsNone(tag)

    def test_it_asks_the_releases_endpoint_for_this_repository(self):
        # A wrong URL is invisible from the outside: everything would simply report
        # "could not reach the forge" forever, which reads like being offline.
        self.assertIn("rundesk-ai/rundesk-cli", updater.RELEASES_LATEST_URL)
        self.assertIn("releases/latest", updater.RELEASES_LATEST_URL)


class MalformedArchiveTests(unittest.TestCase):
    def test_an_archive_that_is_not_shaped_like_a_release_is_refused(self):
        # One top-level directory is what a release archive is. Two means we are looking at
        # something else, and copying it over an install would scatter it.
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            for name in ("one", "two"):
                (root / "staged" / name).mkdir(parents=True)
                (root / "staged" / name / "f.txt").write_text(name)
            archive = root / "odd.tar.gz"
            with tarfile.open(archive, "w:gz") as tar:
                for name in ("one", "two"):
                    tar.add(root / "staged" / name, arcname=name)

            install = root / "install"
            install.mkdir()
            (install / "rundesk").write_text("# 0.1.0\n")

            code, said = _with_download(archive.read_bytes(),
                                        lambda: updater.download_and_apply(install, "v0.2.0"))

            self.assertEqual(code, 1)
            self.assertIn("not shaped like a release", said)
            self.assertEqual((install / "rundesk").read_text(), "# 0.1.0\n", "a bad archive still changed the install")


class SaysWhatItIsDoingTests(unittest.TestCase):
    """An update was silent from the moment it started until it finished.

    It downloads over a network and then replaces the program running it. Silence there
    reads as a hang, and the reflex for a hang is Ctrl-C — which is the exact thing that
    used to leave an install with no `src` at all.
    """

    def setUp(self):
        self._work = tempfile.TemporaryDirectory()
        self.root = Path(self._work.name)
        self.install = self.root / "install"
        (self.install / "src" / "rundesk").mkdir(parents=True)
        (self.install / "rundesk").write_text("# 0.1.0\n")

    def tearDown(self):
        self._work.cleanup()

    def test_an_update_names_each_step_as_it_reaches_it(self):
        top = _release(self.root, "0.2.0")
        archive = self.root / "rel.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            tar.add(top, arcname=top.name)

        code, said = _with_download(archive.read_bytes(),
                                    lambda: updater.download_and_apply(self.install, "v0.2.0"))

        self.assertEqual(code, 0, said)
        for step in ("v0.2.0: downloading", "unpacking", "v0.2.0: installing", "v0.2.0: UPDATED"):
            self.assertIn(step, said, f"an update never said {step!r}")

    def test_an_update_says_where_it_is_writing(self):
        top = _release(self.root, "0.2.0")
        archive = self.root / "rel.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            tar.add(top, arcname=top.name)

        _, said = _with_download(archive.read_bytes(),
                                 lambda: updater.download_and_apply(self.install, "v0.2.0"))

        self.assertIn(str(self.install), said, "an update never said which install it was changing")


class RecoveryTests(unittest.TestCase):
    """The paths that only run when something has already gone wrong.

    Every one of these was written and then never executed by anything — found by measuring
    which lines the suite reaches, not by reading. Untested recovery code is worse than none:
    it is reached exactly when the install is already in trouble.
    """

    def setUp(self):
        self._work = tempfile.TemporaryDirectory()
        self.root = Path(self._work.name)
        self.install = self.root / "install"
        (self.install / "src" / "rundesk").mkdir(parents=True)
        (self.install / "rundesk").write_text("# 0.1.0\n")

    def tearDown(self):
        self._work.cleanup()

    def _archive(self) -> bytes:
        top = _release(self.root, "0.2.0")
        path = self.root / "rel.tar.gz"
        with tarfile.open(path, "w:gz") as tar:
            tar.add(top, arcname=top.name)
        return path.read_bytes()

    def test_an_archive_that_will_not_open_is_reported_rather_than_raised(self):
        # Not a tarball at all — a truncated download, or a proxy serving an error page.
        code, said = _with_download(b"this is not a tar archive",
                                    lambda: updater.download_and_apply(self.install, "v0.2.0"))
        self.assertEqual(code, 1)
        self.assertIn("not shaped like a release", said)
        self.assertEqual((self.install / "rundesk").read_text(), "# 0.1.0\n")

    def test_an_archive_that_reaches_outside_is_reported_rather_than_raised(self):
        # _safe_extract raises; download_and_apply has to turn that into a worded refusal
        # instead of a traceback. Nothing drove a rejected archive through the wrapper.
        nasty = self.root / "nasty.tar.gz"
        with tarfile.open(nasty, "w:gz") as tar:
            escaping = tarfile.TarInfo("../escaped.txt")
            escaping.size = 1
            tar.addfile(escaping, io.BytesIO(b"x"))
        code, said = _with_download(nasty.read_bytes(),
                                    lambda: updater.download_and_apply(self.install, "v0.2.0"))
        self.assertEqual(code, 1)
        self.assertIn("not shaped like a release", said)
        self.assertFalse((self.root / "escaped.txt").exists())

    def test_being_unable_to_put_a_release_in_place_is_reported_rather_than_raised(self):
        real = updater._copy_over
        updater._copy_over = lambda *a, **kw: (_ for _ in ()).throw(OSError(28, "No space left on device"))
        try:
            code, said = _with_download(self._archive(),
                                        lambda: updater.download_and_apply(self.install, "v0.2.0"))
        finally:
            updater._copy_over = real
        self.assertEqual(code, 1)
        self.assertIn("could not install", said)

    def test_a_swap_that_fails_puts_back_what_was_working(self):
        # The old directory has already been renamed aside when the new one fails to move
        # in, so between those two moments the install has no `src` at all. The halves live
        # apart — `_set_aside` moves it out, `_put_back` moves it home — so that nothing
        # set aside is ever outside what the revert knows about: recovery inside the swap
        # itself kept that knowledge to itself, and failing there stranded the only copy.
        package = self.install / "src"
        outgoing = updater._set_aside(package)
        self.assertFalse(package.exists(), "what was there was never moved out of the way")

        self.assertEqual([], updater._put_back([(package, outgoing)]))
        self.assertTrue(package.is_dir(), "a failed swap left the install without its package")
        self.assertTrue((package / "rundesk").is_dir(),
                        "a failed swap put back something other than what was there")

    def test_staging_left_by_an_earlier_crash_is_cleared_rather_than_reused(self):
        # A kill between staging and swapping leaves `.src.incoming` on disk. The next
        # update must not lay that half-copy over the install.
        stale = self.install / ".src.incoming"
        stale.mkdir()
        (stale / "half-written.py").write_text("# from a crash\n")
        stale_file = self.install / ".rundesk.incoming"
        stale_file.write_text("# from a crash\n")

        updater._copy_over(_release(self.root, "0.2.0"), self.install)

        self.assertFalse(stale.exists(), "a stale staging directory survived an update")
        self.assertFalse(stale_file.exists(), "a stale staging file survived an update")
        self.assertFalse((self.install / "src" / "half-written.py").exists(),
                         "an update laid a crashed run's half-copy over the install")

    def test_a_member_named_with_an_absolute_path_is_refused(self):
        # The other absolute case: not a link's target, the member's own name.
        self.assertFalse(updater._lands_inside(self.install, "/etc/passwd"))
        self.assertTrue(updater._lands_inside(self.install, "release/src/cli.py"))


def _with_json(payload, call):
    """Run `call` with the forge replaced — bytes to serve, or an error to raise."""
    class _Response:
        def __init__(self, data): self._data = data
        def read(self): return self._data
        def __enter__(self): return self
        def __exit__(self, *_): return False

    def fake_urlopen(_request, timeout=None):
        if isinstance(payload, BaseException):
            raise payload
        return _Response(payload)

    real = updater.urllib.request.urlopen
    updater.urllib.request.urlopen = fake_urlopen
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out):
            got = call()
    finally:
        updater.urllib.request.urlopen = real
    return got, out.getvalue()

class PublishedNameTests(unittest.TestCase):
    """A release tag and the version the command reports must name the same thing."""

    def test_a_tag_names_the_version_it_carries(self):
        self.assertTrue(updater.tag_matches("v0.1.0", "0.1.0"))
        self.assertTrue(updater.tag_matches("0.1.0", "0.1.0"))

    def test_a_tag_naming_something_else_is_refused(self):
        # The failure this exists to stop: a release tagged v0.2.0 carrying code that still
        # reports 0.1.0. Everyone who updates lands on a version that denies being it.
        self.assertFalse(updater.tag_matches("v0.2.0", "0.1.0"))
        self.assertFalse(updater.tag_matches("v0.1.0", "0.1.1"))
        self.assertFalse(updater.tag_matches("v0.1", "0.1.0"))

    def test_the_version_this_code_reports_would_be_accepted_by_its_own_tag(self):
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
        from rundesk import __version__

        self.assertTrue(
            updater.tag_matches(f"v{__version__}", __version__),
            f"nothing could tag this release: __version__ is {__version__!r}",
        )

    def test_publishing_a_release_actually_applies_the_rule(self):
        # The rule is only worth having if the thing that publishes a release runs it.
        workflow = (Path(__file__).resolve().parent.parent / ".github" / "workflows" / "release.yml").read_text()
        self.assertIn("tag_matches", workflow, "a release can be published without checking what it is named")

class WhyItCouldNotSayTests(unittest.TestCase):
    def test_nothing_published_is_told_apart_from_being_unable_to_ask(self):
        # They send a reader somewhere completely different: one is "wait and try again",
        # the other is "there is nothing there, or you cannot see it". Reporting a private
        # or release-less repository as a network problem sends someone to check their wifi.
        (missing, why), _ = _with_json(urllib.error.HTTPError("u", 404, "Not Found", {}, None),
                                       updater.latest_version_online)
        self.assertIsNone(missing)
        self.assertEqual(why, updater.NOTHING_PUBLISHED)

        # Refused, not empty. The anonymous limit is sixty an hour per address and a shared
        # one reaches it on somebody else's traffic, so this is the ordinary way a perfectly
        # healthy install is told no — and answering "nothing is published" would be a
        # confident falsehood about a release that is right there.
        (refused, why), _ = _with_json(urllib.error.HTTPError("u", 403, "rate limited", {}, None),
                                       updater.latest_version_online)
        self.assertIsNone(refused)
        self.assertEqual(why, updater.UNREACHABLE)
        self.assertIn("could not reach", updater.describe("0.4.0", None, why))

        (offline, why), _ = _with_json(urllib.error.URLError("no route"),
                                       updater.latest_version_online)
        self.assertIsNone(offline)
        self.assertEqual(why, updater.UNREACHABLE)

        self.assertNotEqual(
            updater.describe("0.1.0", None, updater.NOTHING_PUBLISHED),
            updater.describe("0.1.0", None, updater.UNREACHABLE),
            "both kinds of nothing read the same",
        )

    def test_which_kind_of_nothing_it_was_comes_back_from_the_look_up_that_found_it(self):
        """The reason travelled as a module global, set by the real network call. Injected
        look-ups — the seam this module is built around — never set it, so `update` read
        whatever the last real call had left there and reported the wrong kind of nothing."""
        _, nothing_there = run(repo_root=Path("/nowhere"), current_version="0.1.0",
                               latest=lambda: (None, updater.NOTHING_PUBLISHED))
        self.assertIn("NO RELEASES", nothing_there)

        _, could_not_ask = run(repo_root=Path("/nowhere"), current_version="0.1.0",
                               latest=lambda: (None, updater.UNREACHABLE))
        self.assertIn("could not reach", could_not_ask)


class AnUpdateAndWorkInFlight(unittest.TestCase):
    """R-UPD-23 — an update replaces the files a running gateway is made of.

    The process keeps whatever it has already imported, so what breaks is whatever it
    imports *next* — minutes later, part-way through a provider session, in a way that
    reads like anything but an update. Refusing is the whole of the safety: stopping the
    work instead would be deciding on the owner's behalf that the turn was worth less
    than the release.
    """

    def _run(self, busy, check_only=False):
        applied = []
        code = updater.run(
            Path("/tmp/rundesk-not-real"), "0.1.0", check_only=check_only,
            latest=lambda: ("9.9.9", None),
            apply=lambda root, version: applied.append(version) or 0,
            busy=lambda: busy,
        )
        return code, applied

    def test_an_update_refuses_while_work_is_in_flight(self):
        code, applied = self._run(["gateway/schedule:nightly"])
        self.assertEqual(1, code, "an update that refused reported success")
        self.assertEqual([], applied, "it replaced the install out from under running work")

    def test_an_update_says_what_is_in_flight_rather_than_something(self):
        """An owner told only that 'something' is running has to go and find which."""
        with contextlib.redirect_stderr(io.StringIO()) as said:
            self._run(["one/turn-a", "two/turn-b"])
        self.assertIn("one/turn-a", said.getvalue())
        self.assertIn("two/turn-b", said.getvalue())

    def test_an_update_with_nothing_in_flight_goes_ahead(self):
        code, applied = self._run([])
        self.assertEqual(0, code)
        self.assertEqual(["9.9.9"], applied, "an idle machine was refused an update")

    def test_checking_never_refuses_for_work_in_flight(self):
        """R-UPD-8 — asking where this copy stands never changes it, so it never has a
        reason to refuse either."""
        code, applied = self._run(["gateway/busy"], check_only=True)
        self.assertEqual(0, code)
        self.assertEqual([], applied)

    def test_an_update_that_is_already_current_never_asks_what_is_in_flight(self):
        """R-UPD-18 — nothing is going to be moved, so nothing is worth refusing over."""
        asked = []
        code = updater.run(
            Path("/tmp/rundesk-not-real"), "9.9.9", latest=lambda: ("9.9.9", None),
            apply=lambda root, version: 0, busy=lambda: asked.append(True) or ["x"],
        )
        self.assertEqual(0, code)
        self.assertEqual([], asked, "it asked what was running when it was already current")


class AnUpdateAndWhatIsRunning(unittest.TestCase):
    """R-UPD-21, R-UPD-22 — an update replaces the files a running gateway is made of.

    Left running, a gateway keeps the code it already imported and reads the new files
    for everything it has not, so it goes on serving a version nobody can see it is on.
    """

    def _run(self, stopped=(), refused=None, down=(), applied_code=0, carried=None):
        self.brought_back = None
        self.applied = []
        self.carried = 0

        def pause():
            return list(stopped), refused

        def resume(names):
            self.brought_back = list(names)
            return list(down)

        def apply(root, version):
            self.applied.append(version)
            return applied_code

        def carry():
            self.carried += 1
            return carried

        code = updater.run(
            Path("/tmp/rundesk-not-real"), "0.1.0", latest=lambda: ("9.9.9", None),
            apply=apply, busy=lambda: [], pause=pause, resume=resume, carry=carry,
        )
        return code

    def test_an_update_stops_what_it_is_about_to_replace_the_files_of(self):
        """R-UPD-21"""
        self.assertEqual(0, self._run(stopped=["gateway"]))
        self.assertEqual(["9.9.9"], self.applied)
        self.assertEqual(["gateway"], self.brought_back, "it never brought back what it stopped")

    def test_an_update_brings_back_what_it_stopped(self):
        """R-UPD-22"""
        self._run(stopped=["alpha", "beta"])
        self.assertEqual(["alpha", "beta"], self.brought_back)

    def test_records_are_moved_forward_while_nothing_an_owner_runs_is_up(self):
        """R-MIG-1 — the only window there is: the new files are down and no gateway has
        been brought back onto them. Moving records at any other moment is either code
        reading a shape it does not know, or two gateways starting together and both
        beginning to move one forward."""
        order = []
        updater.run(
            Path("/tmp/rundesk-not-real"), "0.1.0", latest=lambda: ("9.9.9", None),
            busy=lambda: [], pause=lambda: (order.append("stopped") or ["alpha"], None),
            apply=lambda root, version: order.append("replaced") or 0,
            carry=lambda: order.append("carried") or None,
            resume=lambda names: order.append("started") or [],
        )
        self.assertEqual(["stopped", "replaced", "carried", "started"], order)

    def test_a_migration_that_fails_leaves_every_agent_down_and_says_which_and_why(self):
        """R-MIG-6 — the one failure `resume` must not answer for. Bringing agents back
        onto records half moved is worse than leaving them down: the first is an agent
        quietly reading a shape nobody wrote, and the second is a machine somebody looks at."""
        with contextlib.redirect_stderr(io.StringIO()) as said:
            code = self._run(stopped=["alpha"],
                             carried="migration 002.py did not finish — the data is still "
                                     "at version 1: no such column")
        self.assertEqual(1, code)
        self.assertIsNone(self.brought_back, "an agent came back onto records half moved")
        self.assertIn("002.py", said.getvalue(), "it never said which step")
        self.assertIn("no such column", said.getvalue(), "it never said why")
        self.assertIn("still down", said.getvalue())

    def test_records_are_left_alone_when_the_files_never_landed(self):
        """R-MIG-18 — moving records forward for code that is not there is how an install
        ends up with data no version of it understands, and there is no way back."""
        self.assertEqual(1, self._run(stopped=["alpha"], applied_code=1))
        self.assertEqual(0, self.carried, "it moved records onto a release that never landed")
        self.assertEqual(["alpha"], self.brought_back)

    def test_an_update_that_failed_still_brings_back_what_it_stopped(self):
        """R-UPD-22 — the path that matters. An update that fell over must not also leave
        the machine's gateways down behind it, which is the one outcome nobody recovers
        from without knowing to go and look."""
        code = self._run(stopped=["alpha"], applied_code=1)
        self.assertEqual(["alpha"], self.brought_back, "a failed update left the gateway down")
        self.assertEqual(1, code)

    def test_an_update_that_broke_a_gateway_says_so_rather_than_reporting_success(self):
        """R-UPD-22 — the update applying is not the gateway coming back, and a release
        needing something the install does not have starts a gateway that ends *well*
        so as not to be restarted forever. The machine calls that a job accepted."""
        with contextlib.redirect_stderr(io.StringIO()) as said:
            code = self._run(stopped=["alpha"], down=["alpha"])
        self.assertEqual(1, code, "it applied an update that left a gateway down and said 0")
        self.assertIn("did not come back", said.getvalue())
        self.assertIn("alpha", said.getvalue())

    def test_an_update_refused_by_what_is_running_replaces_nothing(self):
        """R-UPD-21 — a gateway it cannot start again is not one to take down."""
        with contextlib.redirect_stderr(io.StringIO()) as said:
            code = self._run(refused="'scratch' is running unsupervised")
        self.assertEqual(1, code)
        self.assertEqual([], self.applied, "it replaced the install anyway")
        self.assertIsNone(self.brought_back, "it brought back something it never stopped")
        self.assertIn("unsupervised", said.getvalue())

    def test_an_update_with_nothing_running_stops_and_starts_nothing(self):
        """R-UPD-21 — the ordinary case on a machine with no gateway up."""
        self.assertEqual(0, self._run())
        self.assertEqual(["9.9.9"], self.applied)
        self.assertEqual([], self.brought_back)

    def test_an_update_that_stops_before_replacing_anything_brings_back_what_it_stood_down(self):
        """R-UPD-24 — standing every gateway down is one act per gateway, so a refusal
        arrives with some already stopped. Reporting NOT APPLIED and leaving those down
        reads as "nothing happened" while an owner's agents are unreachable, and nothing
        named them: an update that changed no files still took the machine apart."""
        with contextlib.redirect_stderr(io.StringIO()) as said:
            code = self._run(stopped=["alpha", "beta"],
                             refused="'gamma' is running unsupervised")
        self.assertEqual(1, code)
        self.assertEqual([], self.applied, "it replaced the install anyway")
        self.assertEqual(["alpha", "beta"], self.brought_back,
                         "the ones it stopped before the refusal were left down")
        self.assertIn("brought back: alpha, beta", said.getvalue())

    def test_a_gateway_that_would_not_restart_after_a_refusal_is_named(self):
        """R-UPD-24 — putting them back is not the same as them coming back, and the one
        an owner has to go and look at is the one nothing said anything about."""
        with contextlib.redirect_stderr(io.StringIO()) as said:
            code = self._run(stopped=["alpha", "beta"], down=["beta"],
                             refused="'gamma' is running unsupervised")
        self.assertEqual(1, code)
        self.assertIn("brought back: alpha", said.getvalue())
        self.assertIn("did not come back: beta", said.getvalue())


if __name__ == "__main__":
    unittest.main(verbosity=2)
