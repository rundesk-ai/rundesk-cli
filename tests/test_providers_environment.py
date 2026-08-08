"""Everything an adapter is told about one turn — and everything it is not told.

This is the whole interface between rundesk and a brain, so the cases are mostly about absence: what
is left out, what may not be overwritten, and what a variable set to nothing would mean.

Run directly: `python3 tests/test_providers_environment.py`
"""

import os
import unittest
from pathlib import Path

import support
from rundesk.core import config, paths, secrets
from rundesk.providers import environment, protocol


def built(**also):
    """One turn's environment, with everything a caller must supply already filled in."""
    said = {"agent": "ava", "home": Path("/agents/ava/home"),
            "provider_home": Path("/agents/ava/providers/mine"),
            "skills": Path("/agents/ava/home/skills"), "turn": 7, "access_mode": protocol.ACCESS_WORK}
    said.update(also)
    return environment.for_turn(**said)


class WhatEveryTurnIsTold(support.Isolated):
    def test_the_ones_that_are_always_there(self):
        said = built()
        for name in (environment.CWD, environment.PROVIDER_HOME, environment.SKILLS,
                     environment.RUN, environment.AGENT, environment.ACCESS_MODE,
                     environment.CONTINUITY, environment.INSTALL, environment.COMMAND):
            with self.subTest(name=name):
                self.assertIn(name, said)
                self.assertTrue(said[name])

    def test_the_turn_is_named_by_its_own_id(self):
        """An adapter keeping a running total needs a key that means something afterwards."""
        self.assertEqual(built(turn=412)[environment.RUN], "412")

    def test_which_files_the_agent_lives_by_are_named_with_what_changing_one_is_called(self):
        said = built()[environment.CONTINUITY]
        self.assertEqual(said, "AGENTS.md=rules,MEMORY.md=memory")

    def test_nothing_is_a_terminal(self):
        self.assertEqual(built()["TERM"], "dumb")


class WhatIsLeftOutIsUnsetAndNeverEmpty(support.Isolated):
    """`${RUNDESK_MODEL:-default}` is what an adapter is written expecting."""

    def test_the_optional_ones_are_absent_when_there_is_nothing_to_say(self):
        said = built()
        for name in (environment.MODEL, environment.RESUME, environment.SETTINGS,
                     environment.RAW, environment.PREFACE):
            with self.subTest(name=name):
                self.assertNotIn(name, said)

    def test_each_is_there_when_there_is_something_to_say(self):
        said = built(model="m-1", resume="thread-9", settings='{"a": 1}',
                     raw=Path("/agents/ava/conversations/3/raw.jsonl"), preface="be brief")
        self.assertEqual(said[environment.MODEL], "m-1")
        self.assertEqual(said[environment.RESUME], "thread-9")
        self.assertEqual(said[environment.SETTINGS], '{"a": 1}')
        self.assertTrue(said[environment.RAW].endswith("raw.jsonl"))
        self.assertEqual(said[environment.PREFACE], "be brief")

    def test_a_preface_of_only_whitespace_is_nothing_to_say(self):
        self.assertNotIn(environment.PREFACE, built(preface="   \n  "))


class TheOwnersOwnValues(support.Isolated):
    def test_they_reach_the_adapter(self):
        said = built(owners={"CLOUDFLARE_API_TOKEN": "a-token"})
        self.assertEqual(said["CLOUDFLARE_API_TOKEN"], "a-token")

    def test_they_may_never_take_a_name_rundesk_decided(self):
        """Asked against the environment as it has just been built, so the rule cannot come apart
        from the builder as the builder grows."""
        said = built(owners={environment.CWD: "/somewhere/else",
                             environment.AGENT: "somebody-else"})
        self.assertEqual(said[environment.CWD], "/agents/ava/home")
        self.assertEqual(said[environment.AGENT], "ava")

    def test_a_name_added_to_the_interface_is_protected_from_the_moment_it_lands(self):
        """The point of asking `name not in said` rather than consulting a list kept here."""
        for name in (environment.CWD, environment.PROVIDER_HOME, environment.SKILLS,
                     environment.RUN, environment.AGENT, environment.ACCESS_MODE,
                     environment.CONTINUITY, environment.INSTALL, environment.COMMAND,
                     "PATH", "TERM"):
            with self.subTest(name=name):
                said = built(owners={name: "hijacked"})
                self.assertNotEqual(said[name], "hijacked")

    def test_a_name_rundesk_left_unset_is_reserved_just_as_hard(self):
        """**Deciding to leave one unset is still rundesk deciding.** These are the six names that
        are absent on an ordinary turn, so asking only the built environment let an owner's value
        fill every one of them in — which is not a name being free, it is rundesk having nothing to
        say on this turn.

        Measured before this was closed: a value stored as `RUNDESK_DELEGATION` reached every
        ordinary turn, and `delegations.admitting` reads *present* as "this work was handed to you",
        so one stored value refused every delegation on the install.
        """
        for name in (environment.MODEL, environment.RESUME, environment.SETTINGS,
                     environment.RAW, environment.ANSWERING, environment.PREFACE):
            with self.subTest(name=name):
                said = built(owners={name: "hijacked"})
                self.assertNotIn(name, said,
                                 f"an owner's value took {name}, which rundesk decided to leave "
                                 "unset on this turn")

    def test_one_rundesk_did_fill_in_is_still_the_one_that_wins(self):
        """The reservation must not become a way of losing rundesk's own value."""
        said = built(resume="the-real-handle", model="the-real-model",
                     owners={environment.RESUME: "hijacked", environment.MODEL: "hijacked"})
        self.assertEqual(said[environment.RESUME], "the-real-handle")
        self.assertEqual(said[environment.MODEL], "the-real-model")

    def test_the_same_values_are_the_same_bytes_every_turn(self):
        """So one turn can be compared with another."""
        owners = {"B": "2", "A": "1", "C": "3"}
        self.assertEqual(list(built(owners=owners)), list(built(owners=dict(reversed(
            list(owners.items()))))))


class WhatThisProcessKnowsDoesNotLeak(support.Isolated):
    def test_a_variable_nobody_named_does_not_reach_the_adapter(self):
        os.environ["SOMETHING_PRIVATE"] = "a secret"
        self.addCleanup(os.environ.pop, "SOMETHING_PRIVATE", None)
        self.assertNotIn("SOMETHING_PRIVATE", built())


class ReachingThisInstallsOwnCommand(support.Isolated):
    """An agent runs `rundesk` from inside its own turn to read its history back."""

    def test_the_recorded_command_directory_goes_in_front(self):
        at = self.home / "bin" / "rundesk"
        at.parent.mkdir(parents=True)
        at.write_text("#!/bin/sh\n", encoding="utf-8")
        config.write_fresh(paths.data())
        config.stated("command_link", str(at), paths.data())
        self.assertTrue(built()["PATH"].startswith(str(at.parent) + ":"))

    def test_a_configuration_that_cannot_be_read_does_not_refuse_the_turn(self):
        paths.data().mkdir(parents=True, exist_ok=True)
        config.where(paths.data()).write_text("{ this is not json", encoding="utf-8")
        self.assertIn("PATH", built())

    def test_nothing_recorded_still_reaches_the_launcher_beside_the_code(self):
        """A checkout has never been installed, so nothing is linked and the launcher beside the
        code is the only `rundesk` there is.

        Left out, an agent's own `rundesk messages` answers `command not found` — which is what the
        first live turn of this release did, with the turn otherwise perfectly healthy and nothing
        anywhere saying why the agent could not read its own history back.
        """
        self.assertIn(str(paths.program()), built()["PATH"].split(":"))

    def test_the_launcher_is_reached_even_when_something_is_recorded(self):
        """Both, and in that order: a recorded link is the better answer and never the only one."""
        at = self.home / "bin" / "rundesk"
        at.parent.mkdir(parents=True)
        at.write_text("#!/bin/sh\n", encoding="utf-8")
        config.write_fresh(paths.data())
        config.stated("command_link", str(at), paths.data())
        given = built()["PATH"].split(":")
        self.assertEqual([str(at.parent), str(paths.program())], given[:2])

    def test_a_turn_is_told_which_install_is_running_it(self):
        """Without it an agent's own `rundesk` reads the default `~/.rundesk` rather than the
        install it belongs to. Measured live: a turn ran `rundesk messages` and was told the agent
        speaking was not an agent on this install."""
        self.assertEqual(str(paths.home()), built()[environment.INSTALL])

    def test_the_install_it_is_told_is_derived_and_never_inherited(self):
        """This process may have the variable unset and still resolve a root, so carrying it through
        from the environment would carry nothing in the ordinary case."""
        os.environ.pop(paths.HOME_IS, None)
        self.addCleanup(os.environ.__setitem__, paths.HOME_IS, str(self.home))
        self.assertEqual(str(paths.home()), built()[environment.INSTALL])

    def test_the_command_is_named_absolutely_so_a_brain_that_rebuilds_path_can_still_run_it(self):
        """`PATH` is not a guarantee. One measured brain hands its shell a `PATH` rebuilt from the
        owner's login profile, so the directory put in front is gone and a bare `rundesk` exits 127
        on a healthy install — while the variables it was given arrive intact."""
        at = self.home / "bin" / "rundesk"
        at.parent.mkdir(parents=True)
        at.write_text("#!/bin/sh\n", encoding="utf-8")
        config.write_fresh(paths.data())
        config.stated("command_link", str(at), paths.data())
        said = built()[environment.COMMAND]
        self.assertEqual(str(at), said)
        self.assertTrue(Path(said).is_absolute())

    def test_the_path_in_front_is_still_there_beside_the_whole_path(self):
        """The two are complementary. Two brains inherit the environment and find a bare `rundesk`
        by `PATH`; this guards a later change that reads the variable as replacing the prepend."""
        said = built()
        self.assertIn(str(paths.program()), said["PATH"].split(":"))
        self.assertTrue(said[environment.COMMAND])

    def test_the_command_a_scheduled_turn_starts_is_the_same_install(self):
        """`providers.answering` spawns one and this puts one on a path. **One answer, one place** —
        two would let a machine with two installs reach a different one from each."""
        self.assertEqual(str(paths.program() / "rundesk"), config.the_command())


class ValuesThatCouldNotBeRead(support.Isolated):
    def test_one_that_was_deliberately_emptied_is_not_a_fault(self):
        """`secrets.Held` keeps never-placed, emptied and unreadable apart, and so does this."""
        secrets.stated("A_TOKEN", "a value")
        secrets.cleared("A_TOKEN")
        self.assertEqual(environment.unreadable(), [])

    def test_one_that_cannot_be_read_is_named_and_its_value_is_not(self):
        secrets.stated("A_TOKEN", "a value")
        held = secrets.where()
        held.write_text(held.read_text(encoding="utf-8").replace("v2:", "v9:"), encoding="utf-8")
        self.assertEqual(environment.unreadable(), ["A_TOKEN"])

    def test_a_value_that_cannot_be_read_is_simply_not_given(self):
        secrets.stated("A_TOKEN", "a value")
        held = secrets.where()
        held.write_text(held.read_text(encoding="utf-8").replace("v2:", "v9:"), encoding="utf-8")
        self.assertNotIn("A_TOKEN", environment.owners_own())


if __name__ == "__main__":
    unittest.main()
