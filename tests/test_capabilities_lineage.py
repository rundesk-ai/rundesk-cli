"""Whose grants an answer about this machine would be a fact about.

Every case fabricates a process table. **Nothing here runs `ps`**, and that is not only for speed:
this module exists because the answer depends on how the process was started, so a case that read
the real table would be a case whose result depends on how the suite was launched — green under
`python3 tests/…` and red in CI, or the other way round, for a reason nobody would find.

The two shapes that matter are drawn from what was measured on a real machine and written up in
`docs/research/2026-08-08-what-this-mac-lets-a-process-do.md`:

    from a terminal   responsible = iTerm.app   → TERMINAL, and it lends its grants
    under launchd     responsible = itself      → GATEWAY, and it holds nothing

Run directly: `python3 tests/test_capabilities_lineage.py`
"""

import plistlib
import shutil
import tempfile
import unittest
from pathlib import Path

import support  # noqa: F401 — puts `src/` on the path
from rundesk.capabilities import lineage

SHIM = "rundesk-gateway-"

#: The image a gateway really runs as, kept verbatim from the measurement: the shim `exec`s the
#: interpreter, and Homebrew's interpreter is itself an application bundle.
PYTHON = ("/opt/homebrew/Cellar/python@3.14/3.14.6/Frameworks/Python.framework"
          "/Versions/3.14/Resources/Python.app/Contents/MacOS/Python")


def a_machine(images, parents, responsible):
    """A process table that answers exactly what a case says it does, and `None` otherwise."""
    return lineage.Machine(
        responsible=lambda pid: responsible.get(pid),
        image=lambda pid: images.get(pid),
        parent=lambda pid: parents.get(pid),
    )


class UnderLaunchd(unittest.TestCase):
    """A gateway: its own responsible process, with the shim standing in its parent chain."""

    def setUp(self) -> None:
        # The shim stands between launchd and the interpreter, which is the whole shape: launchd
        # runs the named shim, the shim `exec`s Python, and Python is its own responsible process.
        self.machine = a_machine(
            images={100: PYTHON, 90: "/x/rundesk-gateway-marcus"},
            parents={100: (90, "rundesk-gateway-marcus"), 90: (1, "launchd")},
            responsible={100: 100},
        )

    def test_it_is_a_gateway(self) -> None:
        found = lineage.read(100, shim=SHIM, machine=self.machine)
        self.assertEqual(lineage.GATEWAY, found.how)

    def test_the_interpreter_being_a_bundle_does_not_make_it_a_terminal(self) -> None:
        """Homebrew's interpreter lives inside a `.app`, so a gateway matches the bundle pattern.

        What makes a lineage a terminal is that **something else** is responsible for it. Drop that
        clause and every gateway on the commonest install there is reads as a terminal — a lineage
        whose grants are somebody else's and in which a consent dialog can appear.
        """
        self.assertRegex(PYTHON, lineage.INSIDE_A_BUNDLE)
        found = lineage.read(100, shim=SHIM, machine=self.machine)
        self.assertNotEqual(lineage.TERMINAL, found.how)
        self.assertFalse(found.can_be_asked)

    def test_the_agent_comes_out_of_the_chain(self) -> None:
        """The name survives in the chain and nowhere else — the shim execs the interpreter away."""
        machine = a_machine(
            images={100: PYTHON, 90: "/x/rundesk-gateway-marcus"},
            parents={100: (90, "rundesk-gateway-marcus"), 90: (1, "launchd")},
            responsible={100: 100},
        )
        found = lineage.read(100, shim=SHIM, machine=machine)
        self.assertEqual(lineage.GATEWAY, found.how)
        self.assertEqual("marcus", found.agent)

    def test_it_is_named_for_the_interpreter_and_never_for_the_agent(self) -> None:
        """The pane shows the running image. A fix line naming the shim sends somebody nowhere."""
        machine = a_machine(
            images={100: PYTHON},
            parents={100: (90, "rundesk-gateway-marcus"), 90: (1, "launchd")},
            responsible={100: 100},
        )
        found = lineage.read(100, shim=SHIM, machine=machine)
        self.assertEqual(PYTHON, found.named)
        self.assertNotIn("rundesk-gateway", found.named)

    def test_no_dialog_can_appear_for_it(self) -> None:
        self.assertFalse(lineage.read(100, shim=SHIM, machine=self.machine).can_be_asked)


class FromATerminal(unittest.TestCase):
    """Started by hand: the terminal is responsible, and lends whatever it was granted."""

    def setUp(self) -> None:
        self.where = Path(tempfile.mkdtemp(prefix="rundesk-lineage-"))
        self.addCleanup(shutil.rmtree, self.where, ignore_errors=True)

    def a_bundle(self, called: str, identifier=None) -> str:
        """A real `.app` on disk, because `read` opens the `Info.plist` rather than being told."""
        bundle = self.where / f"{called}.app"
        (bundle / "Contents" / "MacOS").mkdir(parents=True)
        if identifier is not None:
            with open(bundle / "Contents" / "Info.plist", "wb") as writing:
                plistlib.dump({"CFBundleIdentifier": identifier}, writing)
        return str(bundle / "Contents" / "MacOS" / called)

    def test_a_bundle_is_named_by_its_identifier(self) -> None:
        told = self.a_bundle("iTerm2", "com.googlecode.iterm2")
        found = lineage.read(100, shim=SHIM, machine=a_machine(
            images={100: PYTHON, 50: told},
            parents={100: (50, "iTerm2"), 50: (1, "launchd")},
            responsible={100: 50}))
        self.assertEqual(lineage.TERMINAL, found.how)
        self.assertEqual("com.googlecode.iterm2", found.named)
        self.assertTrue(found.can_be_asked)

    def test_a_bundle_that_will_not_read_falls_back_and_says_so(self) -> None:
        """A guess reported as a guess. Naming a row wrongly is worse than admitting which it is."""
        told = self.a_bundle("Nothing")                      # a bundle with no Info.plist at all
        found = lineage.read(100, shim=SHIM, machine=a_machine(
            images={100: PYTHON, 50: told},
            parents={100: (50, "Nothing"), 50: (1, "launchd")},
            responsible={100: 50}))
        self.assertEqual(lineage.TERMINAL, found.how)
        self.assertEqual("Nothing", found.named)
        self.assertIn("could not be read", found.said)

    def test_a_terminal_wins_over_a_shim_in_the_chain(self) -> None:
        """The measured failure: a shim run by hand is answered for by the terminal, not the agent.

        This is the case that makes the whole module necessary. Get it the other way round and a
        check run at a terminal reports a gateway's grants using the terminal's answers.
        """
        told = self.a_bundle("iTerm2", "com.googlecode.iterm2")
        found = lineage.read(100, shim=SHIM, machine=a_machine(
            images={100: PYTHON, 50: told},
            parents={100: (90, "rundesk-gateway-marcus"), 90: (50, "iTerm2"), 50: (1, "launchd")},
            responsible={100: 50}))
        self.assertEqual(lineage.TERMINAL, found.how)
        self.assertEqual("com.googlecode.iterm2", found.named)


class OverSsh(unittest.TestCase):
    def test_sshd_is_remote_and_cannot_be_asked(self) -> None:
        machine = a_machine(
            images={100: PYTHON},
            parents={100: (70, "sshd"), 70: (1, "launchd")},
            responsible={100: 100},
        )
        found = lineage.read(100, shim=SHIM, machine=machine)
        self.assertEqual(lineage.REMOTE, found.how)
        self.assertFalse(found.can_be_asked)
        self.assertNotIn(lineage.REMOTE, lineage.CAN_BE_ASKED)


class TheThirdState(unittest.TestCase):
    """`UNKNOWN` and `CANNOT_TELL` are opposite claims, and the suite says so out loud."""

    def test_a_chain_read_whole_that_matched_nothing_is_unknown(self) -> None:
        machine = a_machine(
            images={100: PYTHON},
            parents={100: (60, "some-supervisor"), 60: (1, "launchd")},
            responsible={100: 100},
        )
        found = lineage.read(100, shim=SHIM, machine=machine)
        self.assertEqual(lineage.UNKNOWN, found.how)
        self.assertTrue(found.certain)

    def test_a_chain_that_could_not_be_read_cannot_tell(self) -> None:
        machine = a_machine(
            images={100: PYTHON},
            parents={100: (60, "some-supervisor")},          # 60's parent answers nothing
            responsible={100: 100},
        )
        found = lineage.read(100, shim=SHIM, machine=machine)
        self.assertEqual(lineage.CANNOT_TELL, found.how)
        self.assertFalse(found.certain)

    def test_no_two_lineages_are_the_same_word(self) -> None:
        """Every other case here compares a result against `lineage.<NAME>`, so aliasing two of
        those constants to one string leaves the whole file green while the distinction it protects
        is gone. The constants have to be compared with each other, once, or nothing checks them."""
        every = {"GATEWAY": lineage.GATEWAY, "TERMINAL": lineage.TERMINAL,
                 "REMOTE": lineage.REMOTE, "UNKNOWN": lineage.UNKNOWN,
                 "CANNOT_TELL": lineage.CANNOT_TELL}
        self.assertEqual(len(every), len(set(every.values())),
                         f"two lineages share a word, so nothing tells them apart: {every}")

    def test_a_platform_that_will_not_name_a_responsible_process_cannot_tell(self) -> None:
        machine = a_machine(images={100: PYTHON}, parents={100: (1, "launchd")}, responsible={})
        found = lineage.read(100, shim=SHIM, machine=machine)
        self.assertEqual(lineage.CANNOT_TELL, found.how)

    def test_a_responsible_pid_nobody_can_read_cannot_tell(self) -> None:
        machine = a_machine(images={100: PYTHON}, parents={100: (1, "launchd")},
                            responsible={100: 55})
        found = lineage.read(100, shim=SHIM, machine=machine)
        self.assertEqual(lineage.CANNOT_TELL, found.how)

    def test_a_process_nobody_can_read_cannot_tell(self) -> None:
        machine = a_machine(images={}, parents={}, responsible={})
        self.assertEqual(lineage.CANNOT_TELL, lineage.read(100, shim=SHIM, machine=machine).how)


class TheWalkStops(unittest.TestCase):
    """A diagnosis run on a broken machine may not be the thing that hangs."""

    def test_a_cycle_stops(self) -> None:
        machine = a_machine(
            images={100: PYTHON},
            parents={100: (100, "itself")},
            responsible={100: 100},
        )
        found = lineage.read(100, shim=SHIM, machine=machine)
        self.assertEqual(lineage.UNKNOWN, found.how)

    def test_a_chain_deeper_than_the_ceiling_stops(self) -> None:
        deep = {one: (one + 1, f"p{one + 1}") for one in range(100, 100 + lineage.AS_FAR_AS + 8)}
        machine = a_machine(images={100: PYTHON}, parents=deep, responsible={100: 100})
        found = lineage.read(100, shim=SHIM, machine=machine)
        self.assertEqual(lineage.CANNOT_TELL, found.how)
        self.assertLessEqual(len(found.chain), lineage.AS_FAR_AS)


if __name__ == "__main__":
    unittest.main()
