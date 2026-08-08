"""What this machine lets rundesk do, and every way an answer can be got wrong.

**The machine arrives as two arguments** — something that runs a program, and a directory to write
into — so no case here starts `osascript`, `screencapture`, `pgrep` or `sudo`. That is not only for
speed. There is no closed port for `osascript`: a case that reached the real one would not merely
touch the machine, it could raise a consent dialog on a developer's screen, and one wrong click there
denies a grant on their Mac permanently.

The answers the stand-in gives are the ones that were really measured, and they are kept verbatim
from `docs/research/2026-08-08-what-this-mac-lets-a-process-do.md` — including the one that makes
this whole module necessary: a capture with no grant exits `0` and writes a perfectly good PNG.

Run directly: `python3 tests/test_capabilities.py`
"""

import shutil
import struct
import tempfile
import unittest
import zlib
from pathlib import Path

import support  # noqa: F401 — puts `src/` on the path
from rundesk.capabilities import lineage, proving
from rundesk.utils import programs

PYTHON = ("/opt/homebrew/Cellar/python@3.14/3.14.6/Frameworks/Python.framework"
          "/Versions/3.14/Resources/Python.app/Contents/MacOS/Python")

A_GATEWAY = lineage.Lineage(lineage.GATEWAY, PYTHON, "marcus", ["rundesk-gateway-marcus"], "")
A_TERMINAL = lineage.Lineage(lineage.TERMINAL, "com.googlecode.iterm2", None, ["iTerm2"], "")


def a_png(wide: int = 8, high: int = 8) -> bytes:
    """A real, minimal PNG. Built rather than pasted, so the dimensions are the case's to choose."""
    def chunk(kind: bytes, body: bytes) -> bytes:
        return (struct.pack(">I", len(body)) + kind + body
                + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF))
    header = struct.pack(">IIBBBBB", wide, high, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header)
            + chunk(b"IDAT", zlib.compress(b"\x00" * (wide * 3 + 1) * high)) + chunk(b"IEND", b""))


class AMachine:
    """A stand-in for the machine: answers what a case says, and records what it was asked.

    Matched on a distinctive word in the argv rather than on the whole list, because the exact
    command is the module's business and a case pinning all of it would break every time a flag
    moved. `writes` lets the capture case put bytes where the probe will look for them.
    """

    def __init__(self, answers=None, writes=None):
        self.answers = dict(answers or {})
        self.writes = dict(writes or {})
        self.asked = []

    def __call__(self, argv, waiting):
        argv = [str(one) for one in argv]
        self.asked.append(argv)
        for word, answer in self.answers.items():
            if any(word in one for one in argv):
                if word in self.writes:
                    Path(argv[-1]).write_bytes(self.writes[word])
                return answer
        return programs.Ran(0, "", "", None)

    def words(self):
        return [" ".join(one) for one in self.asked]


def ran(code=0, out="", err="", trouble=None):
    return programs.Ran(code, out, err, trouble)


class Probing(unittest.TestCase):
    def setUp(self) -> None:
        self.into = Path(tempfile.mkdtemp(prefix="rundesk-probe-"))
        self.addCleanup(shutil.rmtree, self.into, ignore_errors=True)

    def prove(self, address, machine, whose=A_GATEWAY):
        found = proving.named([address])
        self.assertEqual(1, len(found), f"{address} names one probe")
        return proving.proved(found[0], whose, self.into, machine)


class TheProbeSet(Probing):
    def test_there_is_something_to_prove(self) -> None:
        """A set that quietly shrank would report a clean machine, so empty is an error."""
        self.assertTrue(proving.every())

    def test_a_name_nobody_has_matches_nothing(self) -> None:
        self.assertEqual([], proving.named(["browser/netscape"]))

    def test_a_group_names_all_of_it(self) -> None:
        self.assertEqual({one.address for one in proving.named(["control"])},
                         {one.address for one in proving.every() if one.group == "control"})

    def test_needed_and_not_needed_are_told_apart(self) -> None:
        """A bare check that always failed for want of a sudo grant is a gate nobody could use."""
        self.assertTrue(proving.needed())
        self.assertLess(len(proving.needed()), len(proving.every()))
        self.assertNotIn("shell/admin", [one.address for one in proving.needed()])

    def test_every_probe_says_what_it_touches(self) -> None:
        for one in proving.every():
            with self.subTest(probe=one.address):
                self.assertTrue(one.touches.strip(), f"{one.address} does not say what it touches")

    def test_every_proof_carries_its_lineage(self) -> None:
        """Walked rather than listed, so a probe added later cannot forget."""
        found = proving.looked_over(proving.every(), A_GATEWAY, self.into, AMachine())
        for one in found:
            with self.subTest(probe=one.probe.address):
                self.assertIs(A_GATEWAY, one.lineage)


class DrivingTheMachine(Probing):
    """Four grants, not one — an agent with Accessibility still cannot type."""

    def test_the_four_control_grants_are_four_findings(self) -> None:
        addresses = {one.address for one in proving.named(["control"])}
        self.assertEqual({"control/accessibility", "control/post-events",
                          "control/listen-events", "control/system-events"}, addresses)

    def test_accessibility_without_post_events_is_blocked_on_posting(self) -> None:
        """The case that stops the four collapsing into one line."""
        machine = AMachine({"AXIsProcessTrusted": ran(0, "yes"),
                            "CGPreflightPostEventAccess": ran(0, "no")})
        self.assertEqual(proving.READY, self.prove("control/accessibility", machine).verdict)
        posting = self.prove("control/post-events", machine)
        self.assertEqual(proving.BLOCKED, posting.verdict)
        self.assertTrue(posting.fix)

    def test_a_framework_that_answers_nothing_is_unproven(self) -> None:
        machine = AMachine({"AXIsProcessTrusted": ran(0, "perhaps")})
        self.assertEqual(proving.UNPROVEN, self.prove("control/accessibility", machine).verdict)

    def test_apple_events_denied_and_accessibility_denied_are_two_fixes(self) -> None:
        """One script, two grants in front of it, and the wrong pane helps nobody."""
        events = self.prove("control/system-events", AMachine(
            {"osascript": ran(1, "", "execution error: Not authorized to send Apple events (-1743)")}))
        assistive = self.prove("control/system-events", AMachine(
            {"osascript": ran(1, "", "execution error: osascript is not allowed assistive access. "
                                     "(-25211)")}))
        self.assertEqual(proving.BLOCKED, events.verdict)
        self.assertEqual(proving.BLOCKED, assistive.verdict)
        self.assertNotEqual(events.fix, assistive.fix)
        self.assertIn("Automation", events.fix)
        self.assertIn("Accessibility", assistive.fix)


class SeeingTheScreen(Probing):
    """The measured trap: a capture with no grant exits 0 and writes a perfectly good PNG."""

    def test_a_capture_that_came_back_readable_is_ready(self) -> None:
        found = self.prove("screen/capture",
                           AMachine({"screencapture": ran(0)}, {"screencapture": a_png()}))
        self.assertEqual(proving.READY, found.verdict)

    def test_the_capture_and_the_grant_are_two_probes_that_may_disagree(self) -> None:
        """Measured: screencapture is Apple-signed with its own identity and works either way.

        Reporting only the grant tells an owner their agent cannot take a screenshot when it
        demonstrably can. Reporting only the capture claims a grant this process does not hold.
        """
        machine = AMachine({"screencapture": ran(0),
                            "CGPreflightScreenCaptureAccess": ran(0, "no")},
                           {"screencapture": a_png()})
        self.assertEqual(proving.READY, self.prove("screen/capture", machine).verdict)
        self.assertEqual(proving.BLOCKED, self.prove("screen/grant", machine).verdict)

    def test_a_capture_that_would_not_run_is_unproven_and_not_blocked(self) -> None:
        """Measured: a sleeping display answers exactly here, and it is not a refusal."""
        found = self.prove("screen/capture", AMachine(
            {"screencapture": ran(1, "", "could not create image from rect")}))
        self.assertEqual(proving.UNPROVEN, found.verdict)
        self.assertIn("not a refusal", found.said)

    def test_a_capture_that_wrote_nothing_is_unproven(self) -> None:
        found = self.prove("screen/capture", AMachine({"screencapture": ran(0)}))
        self.assertEqual(proving.UNPROVEN, found.verdict)

    def test_a_capture_that_wrote_something_unreadable_is_unproven(self) -> None:
        """Exit zero and a file is not proof a machine can be seen."""
        found = self.prove("screen/capture", AMachine({"screencapture": ran(0)},
                                                      {"screencapture": b"not a png at all...."}))
        self.assertEqual(proving.UNPROVEN, found.verdict)

    def test_a_capture_of_the_wrong_size_is_unproven(self) -> None:
        found = self.prove("screen/capture", AMachine({"screencapture": ran(0)},
                                                      {"screencapture": a_png(4, 4)}))
        self.assertEqual(proving.UNPROVEN, found.verdict)

    def test_the_picture_is_never_left_behind(self) -> None:
        """A probe that leaves a picture of somebody's screen behind has done worse than fail."""
        self.prove("screen/capture", AMachine({"screencapture": ran(0)},
                                              {"screencapture": a_png()}))
        self.assertEqual([], list(self.into.iterdir()))


class ReachingTheDisk(Probing):
    def test_a_tcc_refusal_and_a_mode_refusal_are_two_fixes(self) -> None:
        """EPERM is a grant to give; EACCES is a mode bit. One pane fixes neither of the other."""
        tcc = self.prove("files/desktop", AMachine({"-c": ran(1, "PermissionError 1")}))
        mode = self.prove("files/desktop", AMachine({"-c": ran(1, "PermissionError 13")}))
        self.assertEqual(proving.BLOCKED, tcc.verdict)
        self.assertEqual(proving.BLOCKED, mode.verdict)
        self.assertNotEqual(tcc.fix, mode.fix)
        self.assertIn("chmod", mode.fix)
        self.assertNotIn("chmod", tcc.fix)

    def test_a_folder_that_reads_is_ready(self) -> None:
        self.assertEqual(proving.READY,
                         self.prove("files/desktop", AMachine({"-c": ran(0, "read")})).verdict)

    def test_a_missing_canary_is_unproven_and_never_absent(self) -> None:
        """A missing canary is not a missing capability — `ABSENT` would be a claim nothing made."""
        found = self.prove("files/full-disk", AMachine({"-c": ran(1, "FileNotFoundError 2")}))
        self.assertEqual(proving.UNPROVEN, found.verdict)
        self.assertNotEqual(proving.ABSENT, found.verdict)

    def test_a_missing_folder_is_absent(self) -> None:
        found = self.prove("files/desktop", AMachine({"-c": ran(1, "FileNotFoundError 2")}))
        self.assertEqual(proving.ABSENT, found.verdict)


class TheThirdState(Probing):
    """Unanswered is never reported as answered, and the lineage decides which unanswered it is."""

    def test_a_program_that_never_started_is_unrunnable_and_never_blocked(self) -> None:
        found = self.prove("control/accessibility",
                           AMachine({"-c": ran(None, trouble=programs.DID_NOT_START + ": nope")}))
        self.assertEqual(proving.UNRUNNABLE, found.verdict)
        self.assertNotEqual(proving.BLOCKED, found.verdict)

    def test_the_same_answer_becomes_two_verdicts_in_two_lineages(self) -> None:
        """The case that proves the lineage is part of the answer and not a heading.

        A probe that never came back is a dialog waiting on a desktop in one lineage and a flat
        nothing in the other, and those are two different things for a person to do.
        """
        machine = AMachine({"-c": ran(None, trouble=programs.WOULD_NOT_FINISH + " within 15s")})
        self.assertEqual(proving.UNASKED,
                         self.prove("control/accessibility", machine, A_TERMINAL).verdict)
        self.assertEqual(proving.UNPROVEN,
                         self.prove("control/accessibility", machine, A_GATEWAY).verdict)

    def test_unproven_is_trouble(self) -> None:
        """A check that proved nothing has proved nothing, so it may not exit zero."""
        self.assertIn(proving.UNPROVEN, proving.TROUBLE)
        self.assertNotIn(proving.READY, proving.TROUBLE)

    def test_no_two_verdicts_are_the_same_word(self) -> None:
        """Every verdict is a distinct thing to do about it, asserted rather than intended.

        **This case exists because the suite was toothless without it.** Every other assertion here
        compares a result against `proving.<VERDICT>`, so aliasing two of those constants to one
        string — folding `UNPROVEN` into `BLOCKED`, say — leaves the whole file green while the
        distinction it is written to protect is gone. The comparison has to be between the constants
        themselves, once, or nothing is checking them at all.
        """
        every = {
            "READY": proving.READY, "BLOCKED": proving.BLOCKED, "UNASKED": proving.UNASKED,
            "CLOSED": proving.CLOSED, "ABSENT": proving.ABSENT,
            "UNRUNNABLE": proving.UNRUNNABLE, "UNPROVEN": proving.UNPROVEN,
        }
        self.assertEqual(len(every), len(set(every.values())),
                         f"two verdicts share a word, so nothing tells them apart: {every}")
        self.assertEqual(len(every) - 1, len(proving.TROUBLE),
                         "every verdict but READY is something for somebody to do")

    def test_a_probe_that_broke_is_unproven_rather_than_a_traceback(self) -> None:
        def explode(argv, waiting):
            raise RuntimeError("the machine fell over")
        found = self.prove("control/accessibility", explode)
        self.assertEqual(proving.UNPROVEN, found.verdict)


class WhatToGoAndDo(Probing):
    def test_one_pane_is_named_once_for_several_probes(self) -> None:
        """Six probes blocked on one pane is one thing to do, and printing it six times is noise."""
        machine = AMachine({"-c": ran(0, "no")})
        found = proving.looked_over(proving.named(["control"]), A_GATEWAY, self.into, machine)
        self.assertGreater(len(proving.counted(found)), len(proving.fixes(found)))

    def test_fixes_come_in_the_order_they_are_first_needed(self) -> None:
        first = proving.Proof(proving.every()[0], A_GATEWAY, proving.BLOCKED, "", "do this")
        second = proving.Proof(proving.every()[1], A_GATEWAY, proving.BLOCKED, "", "then this")
        again = proving.Proof(proving.every()[2], A_GATEWAY, proving.BLOCKED, "", "do this")
        self.assertEqual(["do this", "then this"], proving.fixes([first, second, again]))

    def test_a_ready_proof_asks_for_nothing(self) -> None:
        found = self.prove("control/accessibility", AMachine({"-c": ran(0, "yes")}))
        self.assertEqual("", found.fix)
        self.assertFalse(found.trouble)


if __name__ == "__main__":
    unittest.main()
