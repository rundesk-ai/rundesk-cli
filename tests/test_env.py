"""The values this install keeps for what it talks to, and the ways one could get away from you.

Most of these cases are about the *absence* of something — a value not in a backup, not in output,
not in `argv`, not readable by anybody else. That is what a secret store is: the interesting
assertions are all negative, and each one names the route it is closing.

Run directly: `python3 tests/test_env.py`
"""

import base64
import io
import os
import shutil
import threading
import unittest
from unittest import mock

import support
from rundesk.core import paths, secrets
from rundesk.exits import FAILED, OK
from rundesk.lifecycle import backups
from rundesk.utils import files

#: Long enough to be hinted at rather than hidden, and shaped like a real one.
A_TOKEN = "MTIzNDU2Nzg5MDEyMzQ1Njc4.GaBcDe.super-secret-discord-token"


class Values(support.Isolated):
    """An install with somewhere to keep values."""

    def given(self, **values):
        for key, said in values.items():
            secrets.stated(key, said)
        return values


class WhatMayNameAValue(Values):
    """`name_trouble` — a name a program can actually be given."""

    def test_a_shell_variables_name_is_fine(self):
        for key in ("DISCORD_TOKEN", "A", "SLACK_BOT_TOKEN", "X9_Y"):
            with self.subTest(key=key):
                self.assertEqual("", secrets.name_trouble(key))

    def test_anything_a_program_could_not_be_given_is_refused(self):
        for key in ("discord", "Discord_Token", "9LIVES", "A-B", "A B", "A.B", "", "   ", "A/B"):
            with self.subTest(key=repr(key)):
                self.assertNotEqual("", secrets.name_trouble(key))

    def test_a_refusal_says_what_to_type_instead(self):
        why = secrets.name_trouble("discord")
        self.assertIn("capitals", why)
        self.assertGreater(len(why.split()), 5)

    def test_a_name_that_is_refused_keeps_nothing(self):
        with self.assertRaises(secrets.Refused):
            secrets.stated("not-a-name", A_TOKEN)
        self.assertEqual([], secrets.names())


class WhatIsShownOfAValue(Values):
    """`hinted` — enough to recognise, never enough to use."""

    def test_a_long_value_shows_three_at_each_end(self):
        self.assertEqual("MTIxxxxxxxxken", secrets.hinted(secrets.Held(A_TOKEN, None)))

    def test_a_short_value_shows_nothing_at_all(self):
        # Six characters of an eight-character value is not a hint, it is most of the value — and
        # the short ones are exactly the ones worth guessing.
        for said in ("short", "12345678", "abcdefghijk"):
            with self.subTest(said=said):
                self.assertEqual(secrets.BETWEEN, secrets.hinted(secrets.Held(said, None)))
                self.assertNotIn(said[:3], secrets.hinted(secrets.Held(said, None)))

    def test_the_boundary_is_where_it_says_it_is(self):
        just_under = "a" * (secrets.LONG_ENOUGH - 1)
        just_over = "abc" + "m" * (secrets.LONG_ENOUGH - 6) + "xyz"
        self.assertEqual(secrets.BETWEEN, secrets.hinted(secrets.Held(just_under, None)))
        self.assertTrue(secrets.hinted(secrets.Held(just_over, None)).startswith("abc"))

    def test_what_is_shown_never_says_how_long_the_value_is(self):
        # Length narrows a guess and identifies which kind of token it is. Two values of very
        # different lengths are hinted at identically wide.
        short_ish = "abc" + "m" * 20 + "xyz"
        long_one = "abc" + "m" * 400 + "xyz"
        self.assertEqual(len(secrets.hinted(secrets.Held(short_ish, None))), len(secrets.hinted(secrets.Held(long_one, None))))

    def test_nothing_kept_says_so_rather_than_showing_a_blank(self):
        self.assertEqual("not set", secrets.hinted(secrets.Held(None, None)))

    def test_a_hint_is_never_the_value(self):
        for said in (A_TOKEN, "short", "a" * 200):
            with self.subTest(said=said[:12]):
                self.assertNotEqual(said, secrets.hinted(secrets.Held(said, None)))


class KeepingAValue(Values):
    """`stated`, `cleared`, `value`, `placed`, `kept`."""

    def test_what_was_kept_comes_back(self):
        self.given(DISCORD_TOKEN=A_TOKEN)
        self.assertEqual(A_TOKEN, secrets.value("DISCORD_TOKEN"))
        self.assertTrue(secrets.placed("DISCORD_TOKEN"))

    def test_a_name_nobody_placed_holds_nothing(self):
        self.assertIsNone(secrets.value("NEVER_PLACED"))
        self.assertFalse(secrets.placed("NEVER_PLACED"))

    def test_keeping_it_again_replaces_it(self):
        self.given(A_KEY=A_TOKEN)
        secrets.stated("A_KEY", "a-different-long-value")
        self.assertEqual("a-different-long-value", secrets.value("A_KEY"))

    def test_emptying_a_name_leaves_the_name(self):
        # Never having placed a value and having taken one away are different answers, and the
        # second is how somebody sees an integration was set up here and is now switched off.
        self.given(SLACK_BOT_TOKEN=A_TOKEN)
        secrets.cleared("SLACK_BOT_TOKEN")
        self.assertIn("SLACK_BOT_TOKEN", secrets.names())
        self.assertIsNone(secrets.value("SLACK_BOT_TOKEN"))
        self.assertFalse(secrets.placed("SLACK_BOT_TOKEN"))

    def test_keeping_nothing_is_refused_and_points_at_unset(self):
        with self.assertRaises(secrets.Refused) as refused:
            secrets.stated("A_KEY", "")
        self.assertIn("unset", str(refused.exception))

    def test_names_come_back_in_the_order_a_person_reads(self):
        self.given(ZED=A_TOKEN, ALPHA=A_TOKEN, MIDDLE=A_TOKEN)
        self.assertEqual(["ALPHA", "MIDDLE", "ZED"], secrets.names())

    def test_a_file_that_cannot_be_read_is_said_rather_than_treated_as_empty(self):
        secrets.where().parent.mkdir(parents=True, exist_ok=True)
        secrets.where().write_text("{ not json")
        with self.assertRaises(secrets.Refused):
            secrets.kept()


class HowItIsKeptOnDisk(Values):
    """Sealed, signed, and honest about what that is worth.

    The limit is written in the module and repeated here so a reader of the tests meets it too: the
    key sits beside the values, because a gateway starts at boot with nobody typing. This stops a
    value being readable text on a disk. It does not stop the owner's own account, or root.
    """

    def test_the_value_is_not_on_disk_as_text(self):
        self.given(DISCORD_TOKEN=A_TOKEN)
        self.assertNotIn(A_TOKEN, secrets.where().read_text())

    def test_it_reads_back_exactly(self):
        self.given(DISCORD_TOKEN=A_TOKEN)
        self.assertEqual(A_TOKEN, secrets.value("DISCORD_TOKEN"))

    def test_anything_a_person_might_keep_survives_the_round_trip(self):
        for said in (A_TOKEN, "x", "a" * 5000, "spaces and — dashes", "emoji 🔐 in it",
                     "line\nbreak", '{"json": "shaped"}'):
            with self.subTest(said=said[:20]):
                secrets.stated("A_KEY", said)
                self.assertEqual(said, secrets.value("A_KEY"))

    def test_the_same_value_is_never_sealed_the_same_way_twice(self):
        # A keystream reused across two values is the one mistake that breaks this outright.
        self.given(ONE=A_TOKEN, TWO=A_TOKEN)
        written = files.read_json(secrets.where())[1]
        self.assertNotEqual(written["ONE"], written["TWO"])

    def test_a_tampered_value_is_refused_rather_than_opened(self):
        # Signed over the nonce and the sealed bytes, and checked before anything is unsealed.
        self.given(DISCORD_TOKEN=A_TOKEN)
        written = files.read_json(secrets.where())[1]
        parts = written["DISCORD_TOKEN"].split(":")
        body = bytearray(base64.b64decode(parts[3]))
        body[0] ^= 1
        parts[3] = base64.b64encode(bytes(body)).decode()
        written["DISCORD_TOKEN"] = ":".join(parts)
        files.write_json(secrets.where(), written, private=True)

        held = secrets.kept()["DISCORD_TOKEN"]

        self.assertIsNone(held.value)
        self.assertIn("cannot be read", held.trouble)

    def test_a_different_key_cannot_open_it(self):
        self.given(DISCORD_TOKEN=A_TOKEN)
        secrets.key_at().write_bytes(os.urandom(32))
        held = secrets.kept()["DISCORD_TOKEN"]
        self.assertIsNone(held.value)
        self.assertIn("cannot be read", held.trouble)

    def test_unreadable_is_not_the_same_answer_as_not_set(self):
        # Saying "not set" would send somebody to type a new value over one they may still want.
        self.given(DISCORD_TOKEN=A_TOKEN)
        secrets.key_at().write_bytes(os.urandom(32))
        self.assertNotEqual("not set", secrets.hinted(secrets.kept()["DISCORD_TOKEN"]))
        code, _, err = self.rundesk("env", "check", "DISCORD_TOKEN")
        self.assertEqual(FAILED, code)
        self.assertNotIn("never been set", err)

    def test_the_key_is_readable_only_by_its_owner(self):
        self.given(DISCORD_TOKEN=A_TOKEN)
        self.assertEqual(0o600, os.stat(secrets.key_at()).st_mode & 0o777)

    def test_the_key_is_kept_where_a_copy_can_reach_it(self):
        self.given(DISCORD_TOKEN=A_TOKEN)
        self.assertIn(paths.data(), secrets.key_at().parents)

    def test_a_value_written_by_a_shape_this_release_does_not_know_is_refused(self):
        files.write_json(secrets.where(), {"A_KEY": "v9:not:this:release"}, private=True)
        held = secrets.kept()["A_KEY"]
        self.assertIsNone(held.value)
        self.assertIn("v9", held.trouble)


class WhatASignatureCovers(Values):
    """The signature is over the name as well as the bytes, and why that is not decoration."""

    def test_a_value_moved_to_another_name_is_refused(self):
        # Signed over the bytes alone, a tag says only "this install sealed these bytes" — not
        # "…and they belong to this name". Anybody able to edit the file could then swap two
        # sealed values between names, with no key and no decryption, and both would open cleanly:
        # a program asking for its Discord token was handed the Slack one, and would go on to send
        # it to Slack.
        self.given(DISCORD_TOKEN="discord-secret-AAAAAAAA",
                   SLACK_BOT_TOKEN="slack-secret-BBBBBBBBB")
        written = files.read_json(secrets.where())[1]
        written["DISCORD_TOKEN"], written["SLACK_BOT_TOKEN"] = (
            written["SLACK_BOT_TOKEN"], written["DISCORD_TOKEN"])
        files.write_json(secrets.where(), written, private=True)

        held = secrets.kept()

        for key in ("DISCORD_TOKEN", "SLACK_BOT_TOKEN"):
            with self.subTest(key=key):
                self.assertIsNone(held[key].value, "a value opened under somebody else's name")
                self.assertIn("cannot be read", held[key].trouble)

    def test_a_value_copied_to_a_new_name_is_refused(self):
        self.given(DISCORD_TOKEN=A_TOKEN)
        written = files.read_json(secrets.where())[1]
        written["A_COPY"] = written["DISCORD_TOKEN"]
        files.write_json(secrets.where(), written, private=True)
        self.assertIsNone(secrets.kept()["A_COPY"].value)
        self.assertEqual(A_TOKEN, secrets.value("DISCORD_TOKEN"), "the original stopped working")


class WhereTheBytesMayLand(Values):
    """A symlink decides where bytes go, and here that defeats the placement outright."""

    def test_the_key_is_not_written_through_a_link(self):
        # A dangling `key` can send the one thing that opens every sealed value somewhere Rundesk
        # neither owns nor protects. Placement inside data does not make following a link safe.
        paths.secrets().mkdir(parents=True, exist_ok=True)
        aimed = self.home / "outside" / "somewhere-rundesk-does-not-own"
        aimed.parent.mkdir(parents=True, exist_ok=True)
        secrets.key_at().symlink_to(aimed)

        with self.assertRaises(secrets.Refused) as refused:
            secrets.stated("DISCORD_TOKEN", A_TOKEN)

        self.assertIn("is a link", str(refused.exception))
        self.assertFalse(aimed.exists(), "the key was written inside data/")

    def test_the_directory_is_not_written_through_a_link(self):
        elsewhere = self.home / "elsewhere"
        elsewhere.mkdir()
        paths.secrets().parent.mkdir(parents=True, exist_ok=True)
        paths.secrets().symlink_to(elsewhere)
        with self.assertRaises(secrets.Refused):
            secrets.stated("DISCORD_TOKEN", A_TOKEN)
        self.assertEqual([], sorted(one.name for one in elsewhere.iterdir()))


class WhenTwoAreKeepingAValueAtOnce(Values):
    """The key is made once, under the lock, or one of them is sealed with a key nothing keeps."""

    def test_two_first_writers_do_not_each_make_a_key(self):
        # Made outside the lock, both saw no key, both made a different one, and whichever landed
        # last is the key on disk — so the other value can never be opened again. Nothing else
        # about this feature is unrecoverable.
        made = []
        ready = threading.Barrier(2)

        def keeping(name):
            ready.wait()
            secrets.stated(name, A_TOKEN)
            made.append(name)

        both = [threading.Thread(target=keeping, args=(name,))
                for name in ("DISCORD_TOKEN", "SLACK_BOT_TOKEN")]
        for one in both:
            one.start()
        for one in both:
            one.join(15)

        self.assertEqual(2, len(made), "one of them never finished")
        held = secrets.kept()
        for name in ("DISCORD_TOKEN", "SLACK_BOT_TOKEN"):
            with self.subTest(name=name):
                self.assertEqual(A_TOKEN, held[name].value,
                                 f"{name} was sealed with a key that no longer exists")

    def test_a_key_written_only_part_way_is_refused_rather_than_used(self):
        secrets.key_at().parent.mkdir(parents=True, exist_ok=True)
        secrets.key_at().write_bytes(b"too short")
        with self.assertRaises(secrets.Refused) as refused:
            secrets.stated("DISCORD_TOKEN", A_TOKEN)
        self.assertIn("not a key this release can use", str(refused.exception))

    def test_the_store_uses_the_install_lock_while_nested_under_data(self):
        self.given(DISCORD_TOKEN=A_TOKEN)
        self.assertTrue(paths.lock().is_file())
        self.assertFalse((paths.data() / ".rundesk.lock").exists())


class WhoCanReadIt(Values):
    """The permissions, and the fact that they are repaired rather than merely set once."""

    def test_only_the_owner_can_read_the_file(self):
        self.given(DISCORD_TOKEN=A_TOKEN)
        self.assertEqual(0o600, os.stat(secrets.where()).st_mode & 0o777)

    def test_only_the_owner_can_look_in_the_directory(self):
        self.given(DISCORD_TOKEN=A_TOKEN)
        self.assertEqual(0o700, os.stat(paths.secrets()).st_mode & 0o777)

    def test_a_mode_loosened_by_something_else_is_repaired(self):
        self.given(DISCORD_TOKEN=A_TOKEN)
        os.chmod(secrets.where(), 0o644)
        os.chmod(paths.secrets(), 0o755)

        secrets.stated("ANOTHER_KEY", A_TOKEN)

        self.assertEqual(0o600, os.stat(secrets.where()).st_mode & 0o777)
        self.assertEqual(0o700, os.stat(paths.secrets()).st_mode & 0o777)

    def test_it_is_never_world_readable_even_for_an_instant(self):
        # Written at the umask and tightened afterwards, the value is on disk and readable by
        # everybody for as long as the write takes. The staging file is opened at 0600 instead.
        seen = []
        really = files.os.open

        def watching(path, flags, mode=0o777, **named):
            if ".incoming" in str(path):
                seen.append(mode)
            return really(path, flags, mode, **named)

        with mock.patch.object(files.os, "open", side_effect=watching):
            secrets.stated("DISCORD_TOKEN", A_TOKEN)
        self.assertIn(0o600, seen, "the staging file was not opened privately")


class WhatACopyCarries(Values):
    """Secrets are owner data, so a backup and restore carry the sealed store and its key."""

    def test_a_credential_is_below_the_data_directory(self):
        self.given(DISCORD_TOKEN=A_TOKEN)
        self.assertIn(paths.data(), secrets.where().parents)

    def test_a_backup_contains_the_sealed_store_and_the_key(self):
        paths.data().mkdir(parents=True, exist_ok=True)
        files.write_json(paths.data() / "config.json", {"backup_enabled": True})
        self.given(DISCORD_TOKEN=A_TOKEN)

        name = backups.save()

        with backups._opened_copy(paths.backups(), name) as data:
            copied = data / "secrets"
            self.assertEqual(secrets.where().read_bytes(), (copied / secrets.KEPT_IN).read_bytes())
            self.assertEqual(secrets.key_at().read_bytes(), (copied / secrets.KEY_IN).read_bytes())
            self.assertNotIn(A_TOKEN, (copied / secrets.KEPT_IN).read_text(encoding="utf-8"))
            self.assertEqual(0o700, os.stat(copied).st_mode & 0o777)
            self.assertEqual(0o600, os.stat(copied / secrets.KEY_IN).st_mode & 0o777)
            self.assertEqual(0o600, os.stat(copied / secrets.KEPT_IN).st_mode & 0o777)

    def test_a_backup_repairs_loose_secret_store_modes(self):
        paths.data().mkdir(parents=True, exist_ok=True)
        files.write_json(paths.data() / "config.json", {"backup_enabled": True})
        self.given(DISCORD_TOKEN=A_TOKEN)
        os.chmod(paths.secrets(), 0o755)
        os.chmod(secrets.key_at(), 0o644)
        os.chmod(secrets.where(), 0o644)

        name = backups.save()

        with backups._opened_copy(paths.backups(), name) as data:
            copied = data / "secrets"
            self.assertEqual(0o700, os.stat(copied).st_mode & 0o777)
            self.assertEqual(0o600, os.stat(copied / secrets.KEY_IN).st_mode & 0o777)
            self.assertEqual(0o600, os.stat(copied / secrets.KEPT_IN).st_mode & 0o777)

    def test_a_restore_puts_the_backed_up_credential_back(self):
        paths.data().mkdir(parents=True, exist_ok=True)
        files.write_json(paths.data() / "config.json", {"backup_enabled": True})
        self.given(DISCORD_TOKEN=A_TOKEN)
        name = backups.save()
        secrets.stated("DISCORD_TOKEN", "a-newer-secret-value")

        backups.restore(name)

        self.assertEqual(A_TOKEN, secrets.value("DISCORD_TOKEN"),
                         "the backed-up credential was not restored")

    def test_a_restore_repairs_loose_modes_in_the_copy(self):
        paths.data().mkdir(parents=True, exist_ok=True)
        files.write_json(paths.data() / "config.json", {"backup_enabled": True})
        self.given(DISCORD_TOKEN=A_TOKEN)
        name = "2026-08-04T03-00-00Z"
        copied_data = paths.backups() / name
        shutil.copytree(paths.data(), copied_data)
        copied = copied_data / "secrets"
        os.chmod(copied, 0o755)
        os.chmod(copied / secrets.KEY_IN, 0o644)
        os.chmod(copied / secrets.KEPT_IN, 0o644)

        backups.restore(name)

        self.assertEqual(0o700, os.stat(paths.secrets()).st_mode & 0o777)
        self.assertEqual(0o600, os.stat(secrets.key_at()).st_mode & 0o777)
        self.assertEqual(0o600, os.stat(secrets.where()).st_mode & 0o777)

    def test_a_link_cannot_make_a_finished_copy_contain_an_external_store(self):
        paths.data().mkdir(parents=True, exist_ok=True)
        files.write_json(paths.data() / "config.json", {"backup_enabled": True})
        elsewhere = self.home / "elsewhere"
        elsewhere.mkdir()
        paths.secrets().symlink_to(elsewhere)

        with self.assertRaises(backups.Refused) as refused:
            backups.save()

        self.assertIn("link", str(refused.exception))
        self.assertEqual([], backups.kept())


class WhenRundeskIsRemoved(Values):
    """A credential must not be left on a machine rundesk has been taken off — nor taken by an
    ordinary removal, which is not what somebody asked for."""

    def setUp(self):
        super().setUp()
        paths.data().mkdir(parents=True, exist_ok=True)
        files.write_json(paths.data() / "config.json", {"backup_enabled": True})
        self.given(DISCORD_TOKEN=A_TOKEN)

    def test_an_ordinary_removal_keeps_them(self):
        # They are owner data. Taking a token away because somebody uninstalled a program is not
        # what they asked for, and the data directory is kept as one unit.
        code, out, _ = self.rundesk("uninstall", "--confirm")
        self.assertEqual(OK, code)
        self.assertTrue(paths.secrets().is_dir())
        self.assertEqual(A_TOKEN, secrets.value("DISCORD_TOKEN"))
        self.assertIn(str(paths.data()), out)

    def test_a_purge_takes_them(self):
        # A purge takes what the owner accumulated, and a credential left lying on a machine
        # rundesk is no longer on is the worst thing here to leave behind.
        code, out, _ = self.rundesk("uninstall", "--confirm", "--purge")
        self.assertEqual(OK, code)
        self.assertFalse(paths.secrets().exists())
        self.assertIn(str(paths.data()), out)

    def test_a_purge_takes_the_key_with_them(self):
        # A key left behind is not harmless: it is half of what somebody needs if they also have
        # an old copy of the sealed file from somewhere else.
        self.rundesk("uninstall", "--confirm", "--purge")
        self.assertFalse(secrets.key_at().exists())

    def test_what_it_would_do_matches_what_it_does(self):
        # The dry run is the only thing somebody reads before agreeing to it.
        _, _, would = self.rundesk("uninstall", "--purge")
        self.assertIn(str(paths.data()), would)
        self.assertIn("take", would)
        _, _, would_keep = self.rundesk("uninstall")
        self.assertIn(str(paths.data()), would_keep)
        self.assertIn("keep", would_keep)

    def test_no_removal_ever_prints_a_value(self):
        for argv in (("uninstall",), ("uninstall", "--confirm", "--purge")):
            with self.subTest(argv=argv):
                _, out, err = self.rundesk(*argv)
                self.assertNotIn(A_TOKEN, out + err)


class TheCommand(Values):
    """`rundesk env`, driven the way somebody types it."""

    def typing(self, said):
        """Stand in for the person at the terminal, so nothing is ever passed as an argument."""
        return mock.patch("rundesk.commands.env.typed", return_value=said)

    def test_with_nothing_named_it_lists(self):
        code, out, _ = self.rundesk("env")
        self.assertEqual(OK, code)
        self.assertIn("no values kept", out)

    def test_it_shows_every_name_in_order_and_only_a_hint(self):
        self.given(ZED_TOKEN=A_TOKEN, ALPHA_TOKEN=A_TOKEN)
        code, out, _ = self.rundesk("env", "list")
        self.assertEqual(OK, code)
        self.assertIn("VALUE", out)
        self.assertLess(out.index("ALPHA_TOKEN"), out.index("ZED_TOKEN"))
        self.assertIn(secrets.hinted(secrets.Held(A_TOKEN, None)), out)
        self.assertNotIn(A_TOKEN, out)

    def test_setting_one_reads_it_rather_than_taking_it(self):
        with self.typing(A_TOKEN):
            code, out, _ = self.rundesk("env", "set", "DISCORD_TOKEN")
        self.assertEqual(OK, code)
        self.assertEqual(A_TOKEN, secrets.value("DISCORD_TOKEN"))
        self.assertNotIn(A_TOKEN, out)

    def test_a_value_cannot_be_passed_as_an_argument(self):
        # `argv` is in the shell's history the moment you press return, and visible in `ps` to
        # every other user on the machine while the command runs.
        code, _, _ = self.rundesk("env", "set", "DISCORD_TOKEN", A_TOKEN)
        self.assertEqual(2, code, "a value was accepted on the command line")
        self.assertEqual([], secrets.names())

    def test_typing_nothing_keeps_nothing(self):
        with self.typing(None):
            code, _, err = self.rundesk("env", "set", "DISCORD_TOKEN")
        self.assertEqual(FAILED, code)
        self.assertIn("nothing was kept", err)
        self.assertEqual([], secrets.names())

    def test_checking_one_that_is_set_says_so_and_exits_zero(self):
        self.given(DISCORD_TOKEN=A_TOKEN)
        code, out, _ = self.rundesk("env", "check", "DISCORD_TOKEN")
        self.assertEqual(OK, code)
        self.assertNotIn(A_TOKEN, out)

    def test_checking_one_that_is_not_set_exits_non_zero(self):
        # So `rundesk env check DISCORD_TOKEN && start-the-thing` does the right thing in a shell.
        code, _, _ = self.rundesk("env", "check", "NEVER_PLACED")
        self.assertEqual(FAILED, code)

    def test_never_placed_and_emptied_read_differently_to_a_person(self):
        self.given(SLACK_BOT_TOKEN=A_TOKEN)
        self.rundesk("env", "unset", "SLACK_BOT_TOKEN")
        _, _, emptied = self.rundesk("env", "check", "SLACK_BOT_TOKEN")
        _, _, never = self.rundesk("env", "check", "NEVER_PLACED")
        self.assertNotEqual(emptied, never)
        self.assertIn("never been set", never)

    def test_unsetting_says_so_and_leaves_the_name(self):
        self.given(SLACK_BOT_TOKEN=A_TOKEN)
        code, out, _ = self.rundesk("env", "unset", "SLACK_BOT_TOKEN")
        self.assertEqual(OK, code)
        self.assertIn("SLACK_BOT_TOKEN", secrets.names())
        self.assertNotIn(A_TOKEN, out)

    def test_a_name_that_is_not_one_is_refused_by_every_verb(self):
        for verb in ("check", "set", "unset"):
            with self.subTest(verb=verb):
                with self.typing(A_TOKEN):
                    code, _, err = self.rundesk("env", verb, "not-a-name")
                self.assertEqual(FAILED, code)
                self.assertIn("capitals", err)

    def test_no_verb_ever_prints_a_whole_value(self):
        self.given(DISCORD_TOKEN=A_TOKEN)
        for argv in (("env", "list"), ("env", "check", "DISCORD_TOKEN"), ("status",),
                     ("env", "unset", "DISCORD_TOKEN")):
            with self.subTest(argv=argv):
                _, out, err = self.rundesk(*argv)
                self.assertNotIn(A_TOKEN, out + err)

    def test_a_root_that_must_not_be_used_is_refused_before_anything_is_read(self):
        os.environ["RUNDESK_HOME"] = "/"
        code, out, err = self.rundesk("env", "list")
        self.assertEqual(FAILED, code)
        self.assertEqual("", out)
        self.assertIn("root of the filesystem", err)

    def test_a_store_that_cannot_be_read_is_said_rather_than_shown_as_empty(self):
        secrets.where().parent.mkdir(parents=True, exist_ok=True)
        secrets.where().write_text("{ not json")
        code, out, err = self.rundesk("env", "list")
        self.assertEqual(FAILED, code)
        self.assertNotIn("no values kept", out)
        self.assertIn("nothing was listed", err)

    def test_a_store_that_cannot_be_read_fails_check_too(self):
        secrets.where().parent.mkdir(parents=True, exist_ok=True)
        secrets.where().write_text("{ not json")
        code, _, err = self.rundesk("env", "check", "DISCORD_TOKEN")
        self.assertEqual(FAILED, code)
        self.assertIn("cannot be read", err)

    def test_a_value_that_cannot_be_kept_says_so_and_keeps_nothing(self):
        with mock.patch.object(secrets, "stated", side_effect=OSError("the disk filled")):
            with self.typing(A_TOKEN):
                code, _, err = self.rundesk("env", "set", "DISCORD_TOKEN")
        self.assertEqual(FAILED, code)
        self.assertIn("nothing was kept", err)

    def test_a_name_that_cannot_be_emptied_says_so(self):
        with mock.patch.object(secrets, "cleared", side_effect=OSError("the disk filled")):
            code, _, err = self.rundesk("env", "unset", "DISCORD_TOKEN")
        self.assertEqual(FAILED, code)
        self.assertIn("nothing was changed", err)

    def test_a_sub_verb_that_is_not_one_is_a_usage_error(self):
        code, _, _ = self.rundesk("env", "dump-everything")
        self.assertEqual(2, code)


class WhatIsTyped(Values):
    """`typed` — never `argv`, never echoed, and never a command that hangs."""

    def test_it_is_read_without_echoing_when_there_is_a_terminal(self):
        from rundesk.commands import env
        with mock.patch.object(env.sys.stdin, "isatty", return_value=True):
            with mock.patch.object(env.getpass, "getpass", return_value=A_TOKEN) as asked:
                self.assertEqual(A_TOKEN, env.typed("KEY: "))
        self.assertTrue(asked.called, "it echoed the value back to the terminal")

    def test_it_reads_a_pipe_rather_than_hanging_when_there_is_no_terminal(self):
        # A prompt in a script is a command that hangs, which this product refuses everywhere.
        from rundesk.commands import env
        with mock.patch.object(env, "sys") as pretending:
            pretending.stdin = io.StringIO(A_TOKEN + "\n")
            pretending.stdin.isatty = lambda: False
            self.assertEqual(A_TOKEN, env.typed("KEY: "))

    def test_nothing_typed_is_nothing_kept(self):
        from rundesk.commands import env
        with mock.patch.object(env, "sys") as pretending:
            pretending.stdin = io.StringIO("\n")
            pretending.stdin.isatty = lambda: False
            self.assertIsNone(env.typed("KEY: "))


if __name__ == "__main__":
    unittest.main()
