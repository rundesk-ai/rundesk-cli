"""The values this install keeps for what it talks to, and the ways one could get away from you.

Most of these cases are about the *absence* of something — a value not in a backup, not in output,
not in `argv`, not readable by anybody else. That is what a secret store is: the interesting
assertions are all negative, and each one names the route it is closing.

Run directly: `python3 tests/test_env.py`
"""

import base64
import io
import os
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

    def test_the_key_is_kept_where_a_copy_cannot_reach_it(self):
        self.given(DISCORD_TOKEN=A_TOKEN)
        self.assertNotIn(paths.data(), secrets.key_at().parents)

    def test_a_value_written_by_a_shape_this_release_does_not_know_is_refused(self):
        files.write_json(secrets.where(), {"A_KEY": "v9:not:this:release"}, private=True)
        held = secrets.kept()["A_KEY"]
        self.assertIsNone(held.value)
        self.assertIn("v9", held.trouble)


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


class WhatACopyCannotContain(Values):
    """The whole security of where these are kept: a backup is a copy of `data/` and nothing else."""

    def test_a_credential_is_not_below_the_data_directory(self):
        self.given(DISCORD_TOKEN=A_TOKEN)
        self.assertNotIn(paths.data(), secrets.where().parents)

    def test_a_backup_is_structurally_incapable_of_holding_one(self):
        # Not "careful not to" — there is no code path from a copy to here, so there is none to
        # get wrong. This is the reason the directory is where it is.
        paths.data().mkdir(parents=True, exist_ok=True)
        files.write_json(paths.data() / "config.json", {"backup_enabled": True})
        self.given(DISCORD_TOKEN=A_TOKEN)

        name = backups.save()

        landed = [one for one in (paths.backups() / name).rglob("*") if one.is_file()]
        self.assertTrue(landed, "the copy is empty, so this proves nothing")
        for one in landed:
            with self.subTest(file=one.name):
                self.assertNotIn(A_TOKEN, one.read_text(errors="replace"))

    def test_a_restore_does_not_put_a_credential_back(self):
        # The other half of the same decision, and the right way round: a value somebody typed once
        # is not state a copy should be able to reinstate.
        paths.data().mkdir(parents=True, exist_ok=True)
        files.write_json(paths.data() / "config.json", {"backup_enabled": True})
        name = backups.save()
        self.given(DISCORD_TOKEN=A_TOKEN)

        backups.restore(name)

        self.assertEqual(A_TOKEN, secrets.value("DISCORD_TOKEN"),
                         "a restore reached into the secrets")


class TheCommand(Values):
    """`rundesk env`, driven the way somebody types it."""

    def typing(self, said):
        """Stand in for the person at the terminal, so nothing is ever passed as an argument."""
        return mock.patch("rundesk.commands.env._typed", return_value=said)

    def test_with_nothing_named_it_lists(self):
        code, out, _ = self.rundesk("env")
        self.assertEqual(OK, code)
        self.assertIn("no values kept", out)

    def test_it_shows_every_name_in_order_and_only_a_hint(self):
        self.given(ZED_TOKEN=A_TOKEN, ALPHA_TOKEN=A_TOKEN)
        code, out, _ = self.rundesk("env", "list")
        self.assertEqual(OK, code)
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

    def test_a_sub_verb_that_is_not_one_is_a_usage_error(self):
        code, _, _ = self.rundesk("env", "dump-everything")
        self.assertEqual(2, code)


class WhatIsTyped(Values):
    """`_typed` — never `argv`, never echoed, and never a command that hangs."""

    def test_it_is_read_without_echoing_when_there_is_a_terminal(self):
        from rundesk.commands import env
        with mock.patch.object(env.sys.stdin, "isatty", return_value=True):
            with mock.patch.object(env.getpass, "getpass", return_value=A_TOKEN) as asked:
                self.assertEqual(A_TOKEN, env._typed("KEY: "))
        self.assertTrue(asked.called, "it echoed the value back to the terminal")

    def test_it_reads_a_pipe_rather_than_hanging_when_there_is_no_terminal(self):
        # A prompt in a script is a command that hangs, which this product refuses everywhere.
        from rundesk.commands import env
        with mock.patch.object(env, "sys") as pretending:
            pretending.stdin = io.StringIO(A_TOKEN + "\n")
            pretending.stdin.isatty = lambda: False
            self.assertEqual(A_TOKEN, env._typed("KEY: "))

    def test_nothing_typed_is_nothing_kept(self):
        from rundesk.commands import env
        with mock.patch.object(env, "sys") as pretending:
            pretending.stdin = io.StringIO("\n")
            pretending.stdin.isatty = lambda: False
            self.assertIsNone(env._typed("KEY: "))


if __name__ == "__main__":
    unittest.main()
