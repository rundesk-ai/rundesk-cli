"""The owner's shared integration commands."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from rundesk import script


class TheScriptLibrary(unittest.TestCase):
    def setUp(self):
        self.where = Path(tempfile.mkdtemp(prefix="rundesk-scripts-"))
        self.addCleanup(shutil.rmtree, self.where, ignore_errors=True)

    def test_only_runnable_top_level_entries_are_commands(self):
        runnable = self.where / "jira"
        runnable.write_text("#!/bin/sh\n", encoding="utf-8")
        runnable.chmod(0o700)
        (self.where / "notes").write_text("not executable\n", encoding="utf-8")
        (self.where / "support").mkdir()
        hidden = self.where / ".coming"
        hidden.write_text("#!/bin/sh\n", encoding="utf-8")
        hidden.chmod(0o700)

        self.assertEqual({"jira": runnable}, script.commands(self.where))

    def test_a_runnable_link_is_a_command(self):
        target = self.where / "support" / "confluence"
        target.parent.mkdir()
        target.write_text("#!/bin/sh\n", encoding="utf-8")
        target.chmod(0o700)
        (self.where / "confluence").symlink_to(Path("support") / "confluence")

        self.assertEqual(
            {"confluence": self.where / "confluence"},
            script.commands(self.where))

    def test_no_directory_is_no_commands(self):
        self.assertEqual({}, script.commands(self.where / "not-there"))

    def test_the_provider_given_library_is_the_one_a_nested_command_reports(self):
        """R-PROC-23 — redirected installs keep one answer inside an agent turn."""
        was = os.environ.get("RUNDESK_SCRIPTS")
        os.environ["RUNDESK_SCRIPTS"] = str(self.where)
        self.addCleanup(lambda: os.environ.__setitem__("RUNDESK_SCRIPTS", was)
                        if was is not None else os.environ.pop("RUNDESK_SCRIPTS", None))

        self.assertEqual(self.where, script.home())
