"""One-shot update notices passed between the old and new gateway processes.

Run directly: `python3 tests/test_gateway_maintenance.py`
"""

import os
import time
import unittest
from unittest import mock

import support
from rundesk.gateways import maintenance
from rundesk.utils import files


class UpdateNotices(support.Isolated):
    def setUp(self):
        super().setUp()
        self.agent = self.home / "agent"
        self.agent.mkdir()

    def test_installing_is_exact_and_one_shot(self):
        maintenance.installing(self.agent, "0.37.0")
        self.assertEqual(
            "🛠️ Installing an update — I'm installing the new rundesk update, be back shortly.",
            maintenance.stopping(self.agent))
        self.assertIsNone(maintenance.stopping(self.agent))

    def test_installed_names_and_links_the_version_that_started(self):
        notes = "https://github.com/rundesk-ai/rundesk-cli/releases/tag/v0.37.0"
        maintenance.installed(self.agent, "0.37.0", notes)
        self.assertEqual(
            "👋 I'm back — new rundesk update installed, "
            "[release notes for v0.37.0]"
            "(https://github.com/rundesk-ai/rundesk-cli/releases/tag/v0.37.0)",
            maintenance.starting(self.agent, "0.37.0"))
        self.assertIsNone(maintenance.starting(self.agent, "0.37.0"))

    def test_a_different_release_cannot_claim_the_update(self):
        maintenance.installed(self.agent, "0.37.0", "https://example.test/v0.37.0")
        self.assertIsNone(maintenance.starting(self.agent, "0.36.0"))
        self.assertFalse((self.agent / maintenance.MARKER).exists())

    def test_a_stale_or_future_intent_is_not_replayed(self):
        for issued in (time.time() - maintenance.VALID_FOR - 1, time.time() + 1):
            with self.subTest(issued=issued):
                files.write_json(self.agent / maintenance.MARKER, {
                    "phase": "installed", "version": "0.37.0",
                    "notes": "https://example.test/v0.37.0", "issued_at": issued,
                })
                with mock.patch.object(maintenance.time, "time", return_value=time.time()):
                    self.assertIsNone(maintenance.starting(self.agent, "0.37.0"))

    def test_a_link_is_removed_without_reading_or_removing_its_target(self):
        outside = self.home / "outside.json"
        outside.write_text('{"credential":"still here"}', encoding="utf-8")
        marker = self.agent / maintenance.MARKER
        marker.symlink_to(outside)

        self.assertIsNone(maintenance.starting(self.agent, "0.37.0"))

        self.assertFalse(marker.exists())
        self.assertEqual('{"credential":"still here"}', outside.read_text(encoding="utf-8"))

    def test_the_intent_is_private(self):
        maintenance.installing(self.agent, "0.37.0")
        self.assertEqual(0o600, os.stat(self.agent / maintenance.MARKER).st_mode & 0o777)

    def test_a_notice_is_not_returned_when_its_marker_cannot_be_consumed(self):
        maintenance.installing(self.agent, "0.37.0")
        with mock.patch.object(maintenance.files, "remove_one", side_effect=OSError("busy")):
            self.assertIsNone(maintenance.stopping(self.agent))
        self.assertTrue((self.agent / maintenance.MARKER).exists())


if __name__ == "__main__":
    unittest.main()
