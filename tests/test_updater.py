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
import sys
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
