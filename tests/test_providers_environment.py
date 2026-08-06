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
            "skills": Path("/agents/ava/home/skills"), "turn": 7, "posture": protocol.WORK}
    said.update(also)
    return environment.for_turn(**said)


class WhatEveryTurnIsTold(support.Isolated):
    def test_the_ones_that_are_always_there(self):
        said = built()
        for name in (environment.CWD, environment.PROVIDER_HOME, environment.SKILLS,
                     environment.RUN, environment.AGENT, environment.POSTURE,
                     environment.CONTINUITY):
            with self.subTest(name=name):
                self.assertIn(name, said)
                self.assertTrue(said[name])

    def test_the_turn_is_named_by_its_own_id(self):
        """An adapter keeping a running total needs a key that means something afterwards."""
        self.assertEqual(built(turn=412)[environment.RUN], "412")

    def test_which_files_the_agent_lives_by_are_named_with_what_changing_one_is_called(self):
        said = built()[environment.CONTINUITY]
        self.assertEqual(said, "AGENTS.md=rules,MEMORY.md=memory,SOUL.md=identity")

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
                     environment.RUN, environment.AGENT, environment.POSTURE,
                     environment.CONTINUITY, "PATH", "TERM"):
            with self.subTest(name=name):
                said = built(owners={name: "hijacked"})
                self.assertNotEqual(said[name], "hijacked")

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

    def test_nothing_recorded_leaves_the_inherited_path_alone(self):
        self.assertIn("PATH", built())


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
