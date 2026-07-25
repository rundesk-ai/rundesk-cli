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

from rundesk_cli import updater  # noqa: E402


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
            latest=lambda: "v1.0.0",
            apply=lambda root, tag: applied.append(tag) or 0,
        )
        self.assertEqual(code, 0)
        self.assertIn("up to date", said)
        self.assertEqual(applied, [], "an up-to-date install was updated anyway")

    def test_being_behind_moves_the_install(self):
        applied: list[str] = []
        code, said = run(
            repo_root=Path("/nowhere"),
            current_version="0.1.0",
            latest=lambda: "v0.2.0",
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
            latest=lambda: "v0.2.0",
            check_only=True,
            apply=lambda root, tag: applied.append(tag) or 0,
        )
        self.assertEqual(code, 0)
        self.assertIn("v0.2.0", said)
        self.assertEqual(applied, [], "--check moved the install")

    def test_an_unreachable_forge_is_reported_as_unknown_never_as_current(self):
        # "up to date" when we simply could not ask is the one answer that would
        # leave someone on an old version believing they are current.
        code, said = run(repo_root=Path("/nowhere"), current_version="0.1.0", latest=lambda: None)
        self.assertEqual(code, 1)
        self.assertIn("could not reach", said)
        self.assertNotIn("up to date", said)


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



class BehindTests(unittest.TestCase):
    """Whether this install can tell it is behind — the question the whole module exists for."""

    def test_the_version_in_the_code_is_one_that_can_be_compared(self):
        # If `__version__` were ever something unparseable — "dev", "0.1.0-rc" is fine, "next"
        # is not — `is_newer` would answer False forever and this install would never learn it
        # was behind. Nothing else in the suite would notice.
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
        from rundesk_cli import __version__

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
        self.assertNotIn("up to date", unknown)


def _release(root: Path, version: str) -> Path:
    """A tree shaped like a release archive, unpacked."""
    top = root / f"rundesk-cli-{version}"
    (top / "src" / "rundesk_cli").mkdir(parents=True)
    (top / "rundesk").write_text(f"#!/usr/bin/env python3\n# {version}\n")
    (top / "install.sh").write_text(f"#!/usr/bin/env bash\n# {version}\n")
    (top / "README.md").write_text(f"rundesk {version}\n")
    (top / "src" / "rundesk_cli" / "__init__.py").write_text(f'__version__ = "{version}"\n')
    return top


class ReplacesTheInstallTests(unittest.TestCase):
    """An update has to actually replace what is on disk — and leave what is not its business."""

    def setUp(self):
        self._work = tempfile.TemporaryDirectory()
        self.root = Path(self._work.name)
        # An install as it stands before the update: older content, plus things a release
        # does not ship and must not lose.
        self.install = self.root / "install"
        (self.install / "src" / "rundesk_cli").mkdir(parents=True)
        (self.install / "rundesk").write_text("# 0.1.0\n")
        (self.install / "src" / "rundesk_cli" / "__init__.py").write_text('__version__ = "0.1.0"\n')
        (self.install / "src" / "rundesk_cli" / "gone_next_release.py").write_text("# removed upstream\n")
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
            (self.install / "src" / "rundesk_cli" / "__init__.py").read_text(),
            "the version on disk still reports the old release",
        )
        self.assertTrue((self.install / "README.md").exists(), "a file new in the release never arrived")

    def test_a_directory_is_replaced_rather_than_merged(self):
        # A module deleted upstream must not survive inside the new tree, still importable.
        updater._copy_over(_release(self.root, "0.2.0"), self.install)
        self.assertFalse(
            (self.install / "src" / "rundesk_cli" / "gone_next_release.py").exists(),
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
            (install / "src" / "rundesk_cli").mkdir(parents=True)
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
            self.assertIn("updated to v0.2.0", said)

    def test_a_download_that_fails_leaves_the_install_as_it_was(self):
        with tempfile.TemporaryDirectory() as work:
            install = Path(work) / "install"
            install.mkdir()
            (install / "rundesk").write_text("# 0.1.0\n")

            code, said = _with_download(urllib.error.URLError("no route to host"),
                                        lambda: updater.download_and_apply(install, "v0.2.0"))

            self.assertEqual(code, 1)
            self.assertIn("could not download", said)
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
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out):
            code = call()
    finally:
        updater.urllib.request.urlopen = real
    return code, out.getvalue()


class AskingTheForgeTests(unittest.TestCase):
    """The one function that actually talks to GitHub — stubbed everywhere else, so tested here."""

    def test_the_published_tag_is_read_out_of_the_release(self):
        code, _ = _with_json(b'{"tag_name": "v0.4.0", "name": "0.4.0"}', updater.latest_version_online)
        self.assertEqual(code, "v0.4.0")

    def test_a_release_with_no_tag_is_not_turned_into_one(self):
        # A shape we did not expect must read as "could not tell", never as a version.
        for payload in (b'{}', b'{"tag_name": ""}', b'{"tag_name": null}', b'[]'):
            with self.subTest(payload=payload):
                got, _ = _with_json(payload, updater.latest_version_online)
                self.assertIsNone(got)

    def test_a_forge_that_cannot_be_reached_says_nothing_rather_than_guessing(self):
        for boom in (urllib.error.URLError("no route"), TimeoutError(), OSError("refused")):
            with self.subTest(boom=type(boom).__name__):
                got, _ = _with_json(boom, updater.latest_version_online)
                self.assertIsNone(got)

    def test_a_reply_that_is_not_json_is_survived(self):
        got, _ = _with_json(b"<html>rate limited</html>", updater.latest_version_online)
        self.assertIsNone(got)

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
            self.assertIn("did not unpack", said)
            self.assertEqual((install / "rundesk").read_text(), "# 0.1.0\n", "a bad archive still changed the install")


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
        from rundesk_cli import __version__

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
        missing, _ = _with_json(urllib.error.HTTPError("u", 404, "Not Found", {}, None),
                                updater.latest_version_online)
        self.assertIsNone(missing)
        self.assertEqual(updater.why_unavailable, updater.NOTHING_PUBLISHED)

        offline, _ = _with_json(urllib.error.URLError("no route"), updater.latest_version_online)
        self.assertIsNone(offline)
        self.assertEqual(updater.why_unavailable, updater.UNREACHABLE)

        self.assertNotEqual(
            updater.describe("0.1.0", None, updater.NOTHING_PUBLISHED),
            updater.describe("0.1.0", None, updater.UNREACHABLE),
            "both kinds of nothing read the same",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
