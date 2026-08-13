"""Provider-neutral additional-account metadata, never credential custody."""

import os
import stat
import unittest

import support
from rundesk.core import paths
from rundesk.providers import accounts, adapters


class Accounts(support.Isolated):
    def setUp(self):
        super().setUp()
        (paths.home() / "app" / "src").mkdir(parents=True)
        adapter = paths.code() / adapters.SHIPPED_IN / "mine"
        adapter.parent.mkdir(parents=True)
        adapter.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        adapter.chmod(0o755)

    def test_default_is_reserved_and_never_a_registered_alias(self):
        for spelling in ("default", "Default", "DEFAULT"):
            with self.subTest(spelling=spelling), self.assertRaises(accounts.Refused):
                accounts.registered("mine", spelling)

    def test_omission_is_the_implicit_provider_default_and_makes_nothing(self):
        self.assertIsNone(accounts.account_home("mine", None))
        self.assertFalse(accounts.provider_at("mine").exists())

    def test_an_alias_is_only_a_private_empty_provider_owned_home(self):
        one = accounts.registered("mine", "work")
        self.assertEqual("work", one.alias)
        self.assertEqual([], list(one.home.iterdir()))
        self.assertEqual(0o700, stat.S_IMODE(one.home.stat().st_mode))
        self.assertEqual([one], accounts.known("mine"))

    def test_relative_and_absolute_adapter_spellings_share_one_alias_registry(self):
        adapter = paths.code() / adapters.SHIPPED_IN / "mine"
        here = os.getcwd()
        os.chdir(adapter.parent)
        self.addCleanup(os.chdir, here)

        one = accounts.registered("./mine", "work")

        self.assertEqual(str(adapter.resolve()), one.provider_name)
        self.assertEqual(one.home, accounts.account_home(str(adapter.resolve()), "work"))
        with self.assertRaisesRegex(accounts.Refused, "already registered"):
            accounts.registered(str(adapter.resolve()), "work")

    def test_a_missing_alias_never_falls_back_to_default(self):
        with self.assertRaisesRegex(accounts.Refused, "not a registered alias"):
            accounts.account_home("mine", "missing")

    def test_case_collisions_are_refused(self):
        accounts.registered("mine", "Work")
        with self.assertRaisesRegex(accounts.Refused, "may not tell"):
            accounts.registered("mine", "work")

    def test_remove_takes_only_the_exact_alias(self):
        first = accounts.registered("mine", "first")
        second = accounts.registered("mine", "second")
        accounts.removed("mine", "first")
        self.assertFalse(first.home.exists())
        self.assertTrue(second.home.exists())


if __name__ == "__main__":
    unittest.main()
