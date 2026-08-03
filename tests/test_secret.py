"""The values this install keeps for every program it starts.

Offline and complete: no vault, no keeper anybody has to have installed, and no gateway. The
one place a real process is started is where the operating system's own behaviour is the
subject — a command that will not answer, and a program that is not there.

What is asserted here is the module. That a program actually receives what is kept is
`test_process`'s, and what the command prints is `test_cli`'s.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from rundesk import secret


NOW = "2026-08-02T10:11:12Z"
LATER = "2026-08-03T10:11:12Z"
HERE = "this terminal"

#: Long enough that a hint shows characters, so a case can tell one value from another.
A_VALUE = "sk-test-00000000f3a9"
ANOTHER = "sk-test-00000000b0c5"


def a_command(script: str) -> tuple:
    """A keeper written as a shell line, so no case needs a vault or a keeper installed."""
    return ("/bin/sh", "-c", script)


def a_keeper(at: Path, value: str) -> tuple:
    """A keeper that reads its value from somewhere else.

    **The words of a command are kept, so a value written into one is written down.** Every
    case proving nothing is recorded has to fetch from a file rather than print a literal,
    or it proves the opposite of what it says. The same is true of an owner: this is why
    `--from` is documented as the words of a command and never a place to put a value.
    """
    at.write_text(value)
    return ("/bin/cat", str(at))


class WithSomewhereToKeepThings(unittest.TestCase):
    """A scratch root, passed in rather than set in the environment where that is possible.

    Both are exercised: everything below passes `where=`, and `WhereThingsAreKept` proves
    the resolver a gateway actually uses.
    """

    def setUp(self):
        self.where = Path(tempfile.mkdtemp(prefix="rundesk-secret-"))
        self.addCleanup(shutil.rmtree, self.where, ignore_errors=True)

    def hold(self, name: str, value: str, **more) -> secret.Change:
        return secret.remember(name, value, now=NOW, kept_from=HERE, where=self.where,
                               **more)

    def registry(self) -> dict:
        return json.loads(secret.registry_path(self.where).read_text())


class WhatANameMayBe(WithSomewhereToKeepThings):
    """The refusals, which are the security boundary rather than a tidiness rule."""

    def test_every_name_rundesk_decides_for_a_program_is_refused(self):
        """R-SEC-11 — a value that could overwrite one rundesk built would be deciding what
        a program *is* rather than what it is told, and the two must never come apart."""
        was = os.environ.get("RUNDESK_JOB_PREFIX")
        os.environ["RUNDESK_JOB_PREFIX"] = "ai.rundesk-test"
        self.addCleanup(
            lambda: os.environ.__setitem__("RUNDESK_JOB_PREFIX", was) if was is not None
            else os.environ.pop("RUNDESK_JOB_PREFIX", None))

        decided = secret.placed()
        self.assertIn("PATH", decided)
        self.assertIn("HOME", decided)
        self.assertIn("RUNDESK_JOB_PREFIX", decided)
        for name in sorted(decided):
            with self.subTest(name=name):
                self.assertTrue(secret.refused(name),
                                f"rundesk decides {name} and a value could take it")
                with self.assertRaises((secret.Refused, secret.NotAName)):
                    self.hold(name, A_VALUE)

    def test_a_name_that_changes_which_code_a_program_loads_is_refused(self):
        """R-SEC-12 — an agent may keep a value, and every program this install starts would
        load what one of these named, for ever, with nothing else involved in the decision."""
        for name in ("DYLD_INSERT_LIBRARIES", "LD_PRELOAD", "NODE_OPTIONS",
                     "PYTHONSTARTUP", "PYTHONPATH", "BASH_FUNC_X", "GIT_SSH_COMMAND",
                     "SSL_CERT_FILE", "IFS", "XDG_CONFIG_HOME"):
            with self.subTest(name=name):
                self.assertTrue(secret.refused(name))
                with self.assertRaises(secret.Refused):
                    self.hold(name, A_VALUE)
        self.assertEqual([], secret.listed(self.where))

    def test_a_name_that_could_reach_outside_where_values_are_kept_is_refused(self):
        """R-SEC-13 — a name is joined to a directory, and joining an absolute one discards
        the directory outright."""
        outside = self.where.parent / "reached-outside"
        for name in ("../../evil", "/etc/passwd", "a/b", ".", "..", "", "lowercase",
                     "9LIVES", str(outside)):
            with self.subTest(name=name):
                with self.assertRaises((secret.NotAName, secret.Refused)):
                    self.hold(name, A_VALUE)
        self.assertFalse(outside.exists())

    def test_a_name_of_the_right_shape_is_kept(self):
        """The control: the rule refuses what it is for and nothing else."""
        for name in ("GITHUB_TOKEN", "A", "X9_Z"):
            with self.subTest(name=name):
                self.assertEqual("", secret.refused(name))
                self.assertEqual(name, secret.checked(name))


class WhatIsKept(WithSomewhereToKeepThings):
    """Holding a value, replacing one, and taking one away."""

    def test_a_held_value_is_kept_where_nothing_else_can_read_it(self):
        """R-SEC-24 — the mode is the guard, and it is the mode the file is created with."""
        self.hold("GITHUB_TOKEN", A_VALUE)

        standing = secret.values_home(self.where) / "GITHUB_TOKEN"
        self.assertEqual(A_VALUE + "\n", standing.read_text())
        self.assertEqual(0o600, standing.stat().st_mode & 0o777)
        # What is kept beside it is names, hints and marks rather than values — the
        # directory's own mode is what keeps those to their owner.
        self.assertEqual(0o700, self.where.stat().st_mode & 0o777)
        self.assertEqual(0o700, secret.values_home(self.where).stat().st_mode & 0o777)

    def test_what_is_kept_holds_no_value(self):
        """R-SEC-4 — the record of a value is names and marks, and never one."""
        self.hold("GITHUB_TOKEN", A_VALUE)
        secret.remember_command("OP_TOKEN", a_keeper(self.where / "vault", ANOTHER),
                                now=NOW, kept_from=HERE, where=self.where)

        written = secret.registry_path(self.where).read_text()
        self.assertNotIn(A_VALUE, written)
        self.assertNotIn(ANOTHER, written)
        self.assertIn("GITHUB_TOKEN", written)

    def test_keeping_a_value_under_a_name_already_kept_is_refused(self):
        with self.assertRaises(secret.Exists):
            self.hold("GITHUB_TOKEN", A_VALUE)
            self.hold("GITHUB_TOKEN", ANOTHER)

    def test_replacing_a_value_says_which_one_it_replaced(self):
        """R-SEC-18 — the hint of what went is the only way an owner knows they replaced
        the one they meant to."""
        first = self.hold("GITHUB_TOKEN", A_VALUE)
        self.assertIsNone(first.before)

        again = secret.remember("GITHUB_TOKEN", ANOTHER, now=LATER, kept_from=HERE,
                                where=self.where, replace=True)
        self.assertIsNotNone(again.before)
        self.assertEqual(first.kept.hint, again.before.hint)
        self.assertEqual(first.kept.mark, again.before.mark)
        self.assertNotEqual(first.kept.mark, again.kept.mark)
        self.assertFalse(again.unchanged)
        self.assertEqual(LATER, again.kept.kept_at)

    def test_keeping_the_value_already_there_changes_nothing(self):
        """R-SEC-19 — saying a value was replaced when the same one went back would make
        the one date an owner has for a credential mean nothing."""
        self.hold("GITHUB_TOKEN", A_VALUE)
        again = secret.remember("GITHUB_TOKEN", A_VALUE, now=LATER, kept_from="ava",
                                where=self.where, replace=True)

        self.assertTrue(again.unchanged)
        self.assertEqual(NOW, again.kept.kept_at)
        self.assertEqual(HERE, again.kept.kept_from)

    def test_nothing_given_is_refused_rather_than_kept_as_nothing(self):
        """An empty value would blank a working credential while reporting success."""
        for value in ("", "\n", "\r\n"):
            with self.subTest(value=repr(value)):
                with self.assertRaises(secret.NotKept):
                    self.hold("GITHUB_TOKEN", value)

    def test_a_value_no_program_could_be_given_is_refused(self):
        with self.assertRaises(secret.NotKept):
            self.hold("GITHUB_TOKEN", "a\0b")
        with self.assertRaises(secret.NotKept):
            self.hold("GITHUB_TOKEN", "x" * (secret.VALUE_LIMIT_BYTES + 1))

    def test_exactly_one_trailing_newline_is_taken_off_a_value(self):
        """Every keeper worth using adds one, and a key ending in several is legitimate."""
        self.assertEqual("abc", secret.normalised("abc\n"))
        self.assertEqual("abc", secret.normalised("abc\r\n"))
        self.assertEqual("abc\n", secret.normalised("abc\n\n"))
        self.assertEqual("abc ", secret.normalised("abc "))

    def test_taking_a_value_away_names_the_one_that_went(self):
        """R-SEC-20 — and takes the value with the record, rather than one of the two."""
        self.hold("GITHUB_TOKEN", A_VALUE)
        standing = secret.values_home(self.where) / "GITHUB_TOKEN"

        gone = secret.forget("GITHUB_TOKEN", where=self.where)

        self.assertEqual(secret.hint(A_VALUE), gone.hint)
        self.assertFalse(standing.exists())
        self.assertEqual([], secret.listed(self.where))

    def test_asking_about_a_name_nothing_is_kept_under_is_refused(self):
        """R-SEC-21 — answered rather than invented, both ways round."""
        with self.assertRaises(secret.Unknown):
            secret.described("GITHUB_TOKEN", self.where)
        with self.assertRaises(secret.Unknown):
            secret.forget("GITHUB_TOKEN", where=self.where)


class HowOneIsToldApartFromAnother(WithSomewhereToKeepThings):
    """R-SEC-5, R-SEC-6, R-SEC-7 — identification without ever showing a value."""

    def test_a_hint_shows_the_end_of_a_long_value_and_none_of_a_short_one(self):
        self.assertEqual(secret.HINT_MASK + "f3a9", secret.hint(A_VALUE))
        self.assertEqual(secret.HINT_MASK, secret.hint("short"))
        self.assertEqual(secret.HINT_MASK, secret.hint("x" * (secret.HINT_MINIMUM - 1)))
        self.assertNotIn(A_VALUE, secret.hint(A_VALUE))

    def test_two_names_holding_one_value_share_a_mark(self):
        """The whole use of it: an owner sees at a glance that a value reached them twice."""
        first = self.hold("GITHUB_TOKEN", A_VALUE)
        second = self.hold("GH_TOKEN", A_VALUE)
        self.assertEqual(first.kept.mark, second.kept.mark)

    def test_two_names_holding_different_values_do_not(self):
        first = self.hold("GITHUB_TOKEN", A_VALUE)
        second = self.hold("GH_TOKEN", ANOTHER)
        self.assertNotEqual(first.kept.mark, second.kept.mark)

    def test_a_mark_from_one_install_does_not_match_another(self):
        """R-SEC-7 — a mark is taken with a key of this install's, so what is shown to an
        agent and pasted anywhere cannot be tested against a guess."""
        elsewhere = Path(tempfile.mkdtemp(prefix="rundesk-secret-other-"))
        self.addCleanup(shutil.rmtree, elsewhere, ignore_errors=True)

        mine = self.hold("GITHUB_TOKEN", A_VALUE)
        theirs = secret.remember("GITHUB_TOKEN", A_VALUE, now=NOW, kept_from=HERE,
                                 where=elsewhere)

        self.assertNotEqual(mine.kept.mark, theirs.kept.mark)
        self.assertNotIn(A_VALUE, mine.kept.mark)

    def test_this_installs_own_key_is_made_once_and_kept_to_its_owner(self):
        self.hold("GITHUB_TOKEN", A_VALUE)
        at = secret.key_path(self.where)
        first = at.read_text()

        self.assertEqual(0o600, at.stat().st_mode & 0o777)
        self.hold("GH_TOKEN", ANOTHER)
        self.assertEqual(first, at.read_text())


class AValueFetchedByACommand(WithSomewhereToKeepThings):
    """The keeper rundesk stores no value for at all."""

    def test_the_command_is_kept_and_what_it_printed_is_not(self):
        """R-SEC-3 — the point of this keeper is that the value is never on this disk."""
        kept = secret.remember_command(
            "OP_TOKEN", a_keeper(self.where / "vault", A_VALUE),
            now=NOW, kept_from=HERE, where=self.where).kept

        self.assertEqual(secret.FETCHED, kept.kept_as)
        self.assertEqual(secret.hint(A_VALUE), kept.hint)
        self.assertFalse((secret.values_home(self.where) / "OP_TOKEN").exists())
        self.assertNotIn(A_VALUE, secret.registry_path(self.where).read_text())

    def test_a_command_that_gives_nothing_back_keeps_nothing(self):
        """R-SEC-15 — a name registered on a promise is one every program is told nothing
        by, quietly, for as long as nobody looks."""
        for script in ("exit 3", "exit 0", "printf '' "):
            with self.subTest(script=script):
                with self.assertRaises(secret.NotKept):
                    secret.remember_command("OP_TOKEN", a_command(script), now=NOW,
                                            kept_from=HERE, where=self.where)
        self.assertEqual([], secret.listed(self.where))

    def test_a_command_that_will_not_answer_is_not_a_command_that_said_no(self):
        """A probe that could not answer is a third state — the value may be perfectly
        good, and reading a timeout as 'there is no value' is how one is thrown away."""
        said = secret.ran(a_command("sleep 5"), timeout_seconds=0.2)

        self.assertFalse(said.answered)
        self.assertFalse(said.ok)
        self.assertIn("did not answer", said.why)

    def test_a_command_that_is_not_there_is_a_definite_answer(self):
        said = secret.ran((str(self.where / "no-such-keeper"),))

        self.assertTrue(said.answered)
        self.assertFalse(said.ok)

    def test_what_a_keeper_said_went_wrong_is_captured_rather_than_inherited(self):
        """A failing keeper prints the thing it was reading, and a gateway's log rotates,
        is read out loud, and is not where any of that goes."""
        said = secret.ran(a_command("echo 'op: could not read op://work/gh' >&2; exit 1"))

        self.assertTrue(said.answered)
        self.assertFalse(said.ok)
        self.assertEqual("op: could not read op://work/gh", said.why)

    def test_a_keeper_that_asks_a_question_is_not_waited_on_for_ever(self):
        """Its input is closed rather than inherited, so it fails at the timeout instead of
        holding a gateway for as long as the machine is up."""
        said = secret.ran(a_command("read -r line; printf %s \"$line\""),
                          timeout_seconds=2.0)

        self.assertTrue(said.answered)
        self.assertFalse(said.ok)


class WhatEveryProgramIsGiven(WithSomewhereToKeepThings):
    """R-SEC-1 and the three ways a value fails to arrive."""

    def test_every_kept_value_is_produced(self):
        self.hold("GITHUB_TOKEN", A_VALUE)
        secret.remember_command("OP_TOKEN", a_command(f"printf %s {ANOTHER}"),
                                now=NOW, kept_from=HERE, where=self.where)

        said = secret.resolve(where=self.where)

        self.assertEqual({"GITHUB_TOKEN": A_VALUE, "OP_TOKEN": ANOTHER}, said.values)
        self.assertEqual((), said.trouble)
        self.assertEqual("", said.unreadable)

    def test_a_value_rundesk_was_not_allowed_to_keep_is_left_out(self):
        """R-SEC-14 — what is kept is a file somebody can edit, and a name that becomes
        refused in a later release must stop being given out with nobody re-running
        anything. The refusal at the moment it is placed cannot catch either."""
        self.hold("GITHUB_TOKEN", A_VALUE)
        smuggled = json.loads(secret.registry_path(self.where).read_text())
        for name in ("PATH", "DYLD_INSERT_LIBRARIES", "RUNDESK_AGENTS_DIR"):
            smuggled["secrets"][name] = dict(smuggled["secrets"]["GITHUB_TOKEN"])
        secret.registry_path(self.where).write_text(json.dumps(smuggled))
        for name in ("PATH", "DYLD_INSERT_LIBRARIES", "RUNDESK_AGENTS_DIR"):
            secret.write_private(secret.values_home(self.where) / name, "taken\n")

        said = secret.resolve(where=self.where)

        self.assertEqual({"GITHUB_TOKEN": A_VALUE}, said.values)
        self.assertEqual({"PATH", "DYLD_INSERT_LIBRARIES", "RUNDESK_AGENTS_DIR"},
                         {one.name for one in said.trouble})

    def test_a_value_that_cannot_be_fetched_is_left_out_rather_than_emptied(self):
        """R-SEC-16 — a name set to the empty string is present to a program that asks
        whether it is there, and absent to one that asks whether it is true."""
        secret.remember_command("OP_TOKEN", a_command(f"printf %s {A_VALUE}"),
                                now=NOW, kept_from=HERE, where=self.where)
        broken = json.loads(secret.registry_path(self.where).read_text())
        broken["secrets"]["OP_TOKEN"]["command"] = ["/bin/sh", "-c", "exit 1"]
        secret.registry_path(self.where).write_text(json.dumps(broken))

        said = secret.resolve(where=self.where)

        self.assertNotIn("OP_TOKEN", said.values)
        self.assertEqual(("OP_TOKEN",), tuple(one.name for one in said.trouble))
        self.assertTrue(said.trouble[0].answered)

    def test_a_held_value_whose_file_went_missing_is_said_rather_than_passed_over(self):
        """R-SEC-17 — the program is the only thing that knows whether it needed it, so the
        turn goes on; what must not happen is that nothing anywhere says so."""
        self.hold("GITHUB_TOKEN", A_VALUE)
        (secret.values_home(self.where) / "GITHUB_TOKEN").unlink()

        said = secret.resolve(where=self.where)

        self.assertEqual({}, said.values)
        self.assertEqual("GITHUB_TOKEN", said.trouble[0].name)

    def test_what_the_caller_already_has_an_answer_for_is_left_out(self):
        """A channel adapter reads its own credential before anything else, and two agents
        may hold two different bots — one install-wide value would make them the same one."""
        self.hold("DISCORD_TOKEN", A_VALUE)
        self.hold("GITHUB_TOKEN", ANOTHER)

        said = secret.resolve(where=self.where, exclude=("DISCORD_TOKEN",))

        self.assertEqual({"GITHUB_TOKEN": ANOTHER}, said.values)

    def test_what_is_kept_and_cannot_be_read_is_said_rather_than_taken_as_nothing(self):
        """Reading it as nothing kept is how every value an owner placed silently stops
        reaching anything, with no error naming the cause."""
        self.hold("GITHUB_TOKEN", A_VALUE)
        secret.registry_path(self.where).write_text("{not json")

        said = secret.resolve(where=self.where)

        self.assertEqual({}, said.values)
        self.assertTrue(said.unreadable)
        with self.assertRaises(secret.Unreadable):
            secret.listed(self.where)

    def test_what_is_kept_cannot_grow_past_what_a_program_can_be_started_with(self):
        """One keeper that goes wrong would otherwise stop every program on the machine
        from starting at all, and the failure would name nothing."""
        big = "x" * (secret.VALUE_LIMIT_BYTES - 1)
        for at in range(4):
            self.hold(f"BIG_{at}", big)

        said = secret.resolve(where=self.where)

        self.assertLess(len("".join(said.values.values())), secret.SET_LIMIT_BYTES)
        self.assertTrue(said.trouble)

    def test_a_listing_fetches_nothing(self):
        """R-SEC-23 — a listing that unlocked a vault is a listing nobody runs, and one
        that ran every keeper could not be run unattended at all."""
        marker = self.where / "was-asked"
        secret.remember_command("OP_TOKEN", a_command(f"touch {marker}; printf %s {A_VALUE}"),
                                now=NOW, kept_from=HERE, where=self.where)
        self.assertTrue(marker.exists(), "the command is run once, when it is kept")
        marker.unlink()

        self.assertEqual(["OP_TOKEN"], [one.name for one in secret.listed(self.where)])
        secret.described("OP_TOKEN", self.where)

        self.assertFalse(marker.exists())

    def test_a_brain_and_every_command_it_runs_is_given_them(self):
        """R-SEC-1 — the delivery for an integration command, end to end at the seam: a
        brain's tool shell is a child of the program started with this environment, so
        `cf-cli` finds its credential as an ordinary variable with nothing exported."""
        from rundesk import provider

        built = provider.environment(
            home=self.where, cwd=self.where, provider_home=self.where,
            skills=self.where, run="a-run", secrets={"CLOUDFLARE_API_TOKEN": "cf-x"})

        self.assertEqual("cf-x", built["CLOUDFLARE_API_TOKEN"])
        self.assertNotEqual("cf-x", built["PATH"], "a value took a name rundesk decided")

    def test_the_same_answer_is_given_off_the_event_loop(self):
        """A keeper is a program somebody else wrote and may take seconds; run on the loop
        it would hold every other turn and channel the gateway is carrying."""
        import asyncio

        self.hold("GITHUB_TOKEN", A_VALUE)
        said = asyncio.run(secret.resolved(where=self.where))

        self.assertEqual({"GITHUB_TOKEN": A_VALUE}, said.values)


class WhereThingsAreKept(unittest.TestCase):
    """The resolver a gateway actually uses, which no case above goes through."""

    def setUp(self):
        self.where = Path(tempfile.mkdtemp(prefix="rundesk-secret-home-"))
        self.addCleanup(shutil.rmtree, self.where, ignore_errors=True)
        self.was = {name: os.environ.get(name)
                    for name in ("RUNDESK_SECRETS_DIR", "XDG_CONFIG_HOME", "HOME")}
        self.addCleanup(self.put_back)

    def put_back(self):
        for name, value in self.was.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    def point(self, **at):
        for name in ("RUNDESK_SECRETS_DIR", "XDG_CONFIG_HOME"):
            os.environ.pop(name, None)
        for name, value in at.items():
            os.environ[name] = value

    def test_its_own_variable_says_where_things_are_kept(self):
        self.point(RUNDESK_SECRETS_DIR=str(self.where / "elsewhere"))
        self.assertEqual(self.where / "elsewhere", secret.home())

    def test_it_stands_where_every_integration_command_already_looks(self):
        self.point(XDG_CONFIG_HOME=str(self.where / "config"))
        self.assertEqual(self.where / "config" / "rundesk" / "secrets", secret.home())

    def test_a_relative_configuration_home_is_ignored_rather_than_resolved(self):
        """The specification says so, and honouring one would resolve this against whatever
        directory a gateway happened to be started in."""
        self.point(XDG_CONFIG_HOME="relative/config", HOME=str(self.where))
        self.assertEqual(self.where / ".config" / "rundesk" / "secrets", secret.home())

    def test_what_is_kept_stands_outside_everything_a_copy_of_this_install_holds(self):
        """R-SEC-26 — a backup copies the data directory and nothing else, so this is
        structurally incapable of being carried rather than carefully left out."""
        from rundesk import backups_home, data_home

        self.point(RUNDESK_SECRETS_DIR=str(self.where / "secrets"))
        os.environ["RUNDESK_DATA_DIR"] = str(self.where / "data")
        os.environ["RUNDESK_BACKUP_DIR"] = str(self.where / "backups")
        self.addCleanup(os.environ.pop, "RUNDESK_DATA_DIR", None)
        self.addCleanup(os.environ.pop, "RUNDESK_BACKUP_DIR", None)

        kept = secret.home().resolve()
        self.assertNotEqual(kept, data_home().resolve())
        self.assertNotIn(data_home().resolve(), kept.parents)
        self.assertNotIn(backups_home().resolve(), kept.parents)

    def test_the_installer_and_this_module_resolve_the_same_place(self):
        """The one rule this feature writes down twice, and the guard on it.

        A purge runs while the command is being taken off the machine, so the installer
        cannot ask `rundesk env --where` for the answer — it works the directory out in
        shell. Two copies of a rule is two rules, and the day they disagree is the day a
        purge reports removing credentials it left behind, or deletes a directory nobody
        pointed it at. Asserted by running the installer's own lines.
        """
        import subprocess

        script = (Path(__file__).resolve().parent.parent / "install.sh").read_text()
        lines = [one for one in script.splitlines()
                 if one.startswith(("CONFIG_DIR=", "SECRETS_DIR="))]
        self.assertEqual(2, len(lines), "the installer no longer resolves it this way")

        for pointed in ({"XDG_CONFIG_HOME": str(self.where / "config")},
                        {"RUNDESK_SECRETS_DIR": str(self.where / "elsewhere")},
                        {}):
            with self.subTest(pointed=pointed):
                self.point(**pointed)
                os.environ["HOME"] = str(self.where)
                said = subprocess.run(
                    ["/bin/bash", "-c", "\n".join(lines) + '\nprintf %s "$SECRETS_DIR"'],
                    stdout=subprocess.PIPE, check=True,
                    env={**os.environ, "HOME": str(self.where)}).stdout.decode()
                self.assertEqual(str(secret.home()), said)

    def test_the_default_stands_outside_the_installs_own_data(self):
        """The one that matters, because it is the one nobody redirects."""
        self.point(HOME=str(self.where))
        for name in ("RUNDESK_DATA_DIR", "RUNDESK_INSTALL_DIR"):
            self.was.setdefault(name, os.environ.get(name))
            os.environ.pop(name, None)

        from rundesk import data_home

        self.assertNotIn(data_home().resolve(), secret.home().resolve().parents)


class ATerminalThatIsNotThere:
    """Standard input that exists, is not a terminal, and will never hand anything over.

    What a brain's tool shell gives its children, and what a suite walking the surface
    gives the command. Reading it blocks until the far end closes, which may be never — so
    a case that lets the real one through proves the opposite of what it says.
    """

    def __init__(self, said: str = "", terminal: bool = False):
        self.said = said
        self.terminal = terminal
        self.asked = 0

    def isatty(self) -> bool:
        return self.terminal

    def readline(self) -> str:
        self.asked += 1
        return self.said


class WhatTheCommandSays(unittest.TestCase):
    """The surface, driven through `cli.main` — nothing here reaches the owner's own."""

    def setUp(self):
        self.where = Path(tempfile.mkdtemp(prefix="rundesk-env-surface-"))
        self.addCleanup(shutil.rmtree, self.where, ignore_errors=True)
        was = os.environ.get("RUNDESK_SECRETS_DIR")
        os.environ["RUNDESK_SECRETS_DIR"] = str(self.where)
        self.addCleanup(
            lambda: os.environ.__setitem__("RUNDESK_SECRETS_DIR", was) if was is not None
            else os.environ.pop("RUNDESK_SECRETS_DIR", None))
        self.assertIn(str(self.where), str(secret.home()),
                      "this suite would otherwise read the owner's own values")

    def typed(self, argv, stdin=None):
        """One command, exactly as `rundesk` runs it, with nothing of the owner's near it."""
        import contextlib
        import io

        from rundesk import cli

        out, err = io.StringIO(), io.StringIO()
        was = sys.stdin
        sys.stdin = stdin if stdin is not None else ATerminalThatIsNotThere()
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                try:
                    code = cli.main(argv)
                except SystemExit as why:
                    code = why.code
        finally:
            sys.stdin = was
        return code, out.getvalue(), err.getvalue()

    def keep(self, name: str, value: str) -> None:
        secret.remember(name, value, now=NOW, kept_from=HERE, where=self.where)

    def actions(self) -> list:
        """Every action under `env`, read off the parser rather than listed here.

        So an action added tomorrow is covered by the case below the day it lands, rather
        than the day somebody remembers this list exists.
        """
        import argparse

        from rundesk import cli

        parser = cli.build_parser()
        under = next(one for one in parser._actions
                     if isinstance(one, argparse._SubParsersAction))
        env = under.choices["env"]
        beneath = next((one for one in env._actions
                        if isinstance(one, argparse._SubParsersAction)), None)
        return sorted(beneath.choices) if beneath else []

    def test_no_action_ever_prints_a_whole_value(self):
        """R-SEC-4 — walked off the parser, so an action added tomorrow is covered the day
        it lands rather than the day somebody remembers to add it here."""
        self.keep("GITHUB_TOKEN", A_VALUE)
        asked = [["env"], ["env", "--help"]]
        asked += [["env", act] for act in self.actions()]
        asked += [["env", act, "GITHUB_TOKEN"] for act in self.actions()]

        for argv in asked:
            with self.subTest(argv=" ".join(argv)):
                _code, out, err = self.typed(argv)
                self.assertNotIn(A_VALUE, out)
                self.assertNotIn(A_VALUE, err)

    def test_a_value_given_as_an_argument_is_refused(self):
        """R-SEC-8 — an option's value is in the process table for every user on the
        machine and in a shell history for ever."""
        code, _out, _err = self.typed(["env", "set", "GITHUB_TOKEN", A_VALUE])

        self.assertEqual(2, code)
        self.assertEqual([], secret.listed(self.where))

    def test_no_option_on_the_command_takes_a_value(self):
        """R-SEC-8 — the guard on the one above: the only thing `set` takes is a name, a
        way to read one, and the words of a command that prints one."""
        import argparse

        from rundesk import cli

        parser = cli.build_parser()
        under = next(one for one in parser._actions
                     if isinstance(one, argparse._SubParsersAction))
        beneath = next(one for one in under.choices["env"]._actions
                       if isinstance(one, argparse._SubParsersAction))
        put = beneath.choices["set"]

        positional = [one.dest for one in put._actions if not one.option_strings]
        self.assertEqual(["value_name"], positional)
        taking = sorted(one.dest for one in put._actions
                        if one.option_strings and one.nargs != 0 and one.dest != "help")
        self.assertEqual(["fetched_by"], taking)

    def test_a_value_nobody_can_supply_is_a_refusal_rather_than_a_wait(self):
        """R-SEC-10 — reading standard input is asked for and never inferred. Inferring it
        reads an open pipe with nothing in it, which is what a brain's tool shell hands its
        children, and blocks until the far end closes — which may be never."""
        nobody = ATerminalThatIsNotThere()

        code, _out, err = self.typed(["env", "set", "GITHUB_TOKEN"], stdin=nobody)

        self.assertEqual(1, code)
        self.assertEqual(0, nobody.asked, "it read a pipe nobody was going to write to")
        self.assertIn("NOT KEPT", err)
        self.assertEqual([], secret.listed(self.where))

    def test_a_value_is_taken_from_a_pipe(self):
        """R-SEC-9 — the shape a script uses, and the only one that reads standard input."""
        code, out, _err = self.typed(["env", "set", "GITHUB_TOKEN", "--stdin"],
                                     stdin=ATerminalThatIsNotThere(A_VALUE + "\n"))

        self.assertEqual(0, code)
        self.assertIn("KEPT", out)
        self.assertEqual(A_VALUE, secret.resolve(where=self.where).values["GITHUB_TOKEN"])

    def test_a_value_is_typed_without_being_echoed(self):
        """R-SEC-9 — at a terminal it is asked for through the one call that turns echo
        off, so it is not left on the screen behind whoever typed it."""
        from rundesk.commands import env as command

        asked = []
        real = command.getpass.getpass
        command.getpass.getpass = lambda prompt="": (asked.append(prompt) or A_VALUE)
        self.addCleanup(setattr, command.getpass, "getpass", real)

        code, _out, _err = self.typed(["env", "set", "GITHUB_TOKEN"],
                                      stdin=ATerminalThatIsNotThere(terminal=True))

        self.assertEqual(0, code)
        self.assertEqual(1, len(asked), "the value was not asked for with echo off")
        self.assertIn("GITHUB_TOKEN", asked[0])

    def test_every_kept_value_can_be_proved_reachable_without_being_shown(self):
        """R-SEC-22 — the answer an owner needs before they replace a credential that was
        working, and the one an agent needs before it says an integration is broken."""
        self.keep("GITHUB_TOKEN", A_VALUE)

        code, out, _err = self.typed(["env", "check"])

        self.assertEqual(0, code)
        self.assertIn("GITHUB_TOKEN", out)
        self.assertNotIn(A_VALUE, out)

    def test_a_check_that_could_not_reach_one_ends_unsuccessfully(self):
        """R-SEC-22 — a script reads the code, so saying so on the screen is not enough."""
        self.keep("GITHUB_TOKEN", A_VALUE)
        (secret.values_home(self.where) / "GITHUB_TOKEN").unlink()

        code, _out, _err = self.typed(["env", "check"])

        self.assertEqual(1, code)

    def test_where_values_are_kept_is_printed_and_nothing_else(self):
        """R-SEC-31 — the installer asks the command rather than resolving the directory a
        second time in shell, where the fallback would be a second copy of one rule."""
        code, out, _err = self.typed(["env", "--where"])

        self.assertEqual(0, code)
        self.assertEqual(str(self.where), out.strip())

    def test_a_listing_with_nothing_kept_says_so_rather_than_printing_nothing(self):
        code, out, _err = self.typed(["env"])

        self.assertEqual(0, code)
        self.assertIn("NO VALUES KEPT", out)

    def test_a_name_the_command_may_not_keep_is_refused_in_our_own_words(self):
        """R-SEC-11, R-SEC-12 — a usage dump would read as a command somebody typed wrong."""
        for name in ("PATH", "DYLD_INSERT_LIBRARIES"):
            with self.subTest(name=name):
                code, _out, err = self.typed(["env", "set", name, "--stdin"],
                                             stdin=ATerminalThatIsNotThere(A_VALUE))
                self.assertEqual(1, code)
                self.assertIn("NOT KEPT", err)
        self.assertEqual([], secret.listed(self.where))

    def test_a_change_records_where_it_was_made_from(self):
        """The only account a change to install-wide state an agent may make can have."""
        from rundesk.commands import env as command

        self.assertEqual("this terminal", command.kept_from())
        os.environ["RUNDESK_RUN"] = "run-1"
        os.environ["RUNDESK_AGENT_NAME"] = "ava"
        self.addCleanup(os.environ.pop, "RUNDESK_RUN", None)
        self.addCleanup(os.environ.pop, "RUNDESK_AGENT_NAME", None)

        self.assertEqual("ava's gateway", command.kept_from())


if __name__ == "__main__":
    unittest.main(verbosity=2)
