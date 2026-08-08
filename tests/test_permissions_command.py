"""`rundesk permissions` — what it prints, what it exits, and what it refuses to run.

Every case drives a stand-in machine. `support.run_with` hands one in by default and replaces the
real resolver with something that raises, so a case that forgot would fail loudly rather than reach
`osascript` on the developer's own Mac — where it could raise a consent dialog, and where a capture
from an ungranted process was measured making macOS write a Screen Recording grant.

Run directly: `python3 tests/test_permissions_command.py`
"""

import json
import unittest
from unittest import mock

import support
from rundesk.capabilities import lineage, proving
from rundesk.core import config
from rundesk.exits import FAILED, OK

PYTHON = ("/opt/homebrew/Cellar/python@3.14/3.14.6/Frameworks/Python.framework"
          "/Versions/3.14/Resources/Python.app/Contents/MacOS/Python")

A_GATEWAY = lineage.Lineage(lineage.GATEWAY, PYTHON, "marcus", ["launchd"], "its own client")
A_TERMINAL = lineage.Lineage(lineage.TERMINAL, "com.googlecode.iterm2", None, ["iTerm2"], "iTerm")
NOBODY = lineage.Lineage(lineage.CANNOT_TELL, "", None, [], "/bin/ps would not answer")


class Permissions(support.Isolated):
    """A scratch install, with the lineage decided by the case rather than by the machine."""

    def permissions(self, *argv, whose=A_GATEWAY, machine=None):
        machine = machine if machine is not None else support.AMachine()
        with mock.patch("rundesk.commands.permissions._mine", return_value=whose):
            code, out, err = support.run_with(["permissions", *argv], probing=machine)
        return code, out, err, machine


class WhatItRefusesToDo(Permissions):
    def test_nothing_is_proved_when_nobody_can_say_whose_grants_it_would_be(self) -> None:
        """Structural, not a caveat: a verdict with no process named is a claim about nobody.

        Asserted by what the stand-in was *asked to run* — an empty table would look the same.
        """
        code, _out, err, machine = self.permissions("check", whose=NOBODY)
        self.assertEqual(FAILED, code)
        self.assertEqual([], machine.asked, "it probed despite not knowing whose grants these are")
        self.assertIn("claim about nobody", err)

    def test_a_name_nobody_has_is_refused_with_the_list(self) -> None:
        """Never an empty table that exits zero."""
        code, _out, err, machine = self.permissions("check", "browser/netscape")
        self.assertEqual(FAILED, code)
        self.assertIn("nothing here is called browser/netscape", err)
        self.assertIn("control/accessibility", err)
        self.assertEqual([], machine.asked)

    def test_the_bare_verb_runs_nothing_at_all(self) -> None:
        """Typing the verb to see what it is must not start anything on somebody's machine."""
        _code, _out, _err, machine = self.permissions()
        self.assertEqual([], machine.asked)

    def test_listing_runs_nothing_and_says_what_each_probe_touches(self) -> None:
        code, out, _err, machine = self.permissions("list")
        self.assertEqual(OK, code)
        self.assertEqual([], machine.asked)
        self.assertIn("what settling each one does to this machine", out)


class WhatItSays(Permissions):
    def test_the_lineage_line_is_on_stdout_and_comes_first(self) -> None:
        """A script reading only stdout must see what qualifies every row below it."""
        _code, out, _err, _machine = self.permissions("check", "files")
        self.assertTrue(out.strip(), "nothing was printed to stdout")
        self.assertIn("these answers are about", out.splitlines()[0])

    def test_a_terminal_says_a_gateway_may_be_answered_differently(self) -> None:
        """The measured failure, said out loud where somebody will read it."""
        _code, out, _err, _machine = self.permissions("check", "files", whose=A_TERMINAL)
        self.assertIn("a gateway is a different process", out)

    def test_a_gateway_is_told_one_grant_covers_every_agent(self) -> None:
        _code, out, _err, _machine = self.permissions("check", "files")
        self.assertIn("one grant covers every agent", out)

    def test_findings_go_to_stdout_and_the_summary_to_stderr(self) -> None:
        machine = support.AMachine(**{"-c": support.ran(1, "PermissionError 1")})
        _code, out, err, _machine = self.permissions("check", "files", machine=machine)
        self.assertIn("files", out)
        self.assertIn("cannot be used by", err)
        self.assertIn("systempreferences", err)

    def test_one_pane_is_named_once_however_many_probes_want_it(self) -> None:
        machine = support.AMachine(**{"-c": support.ran(1, "PermissionError 1")})
        _code, _out, err, _machine = self.permissions("check", "files", machine=machine)
        self.assertEqual(1, err.count("Privacy_AllFiles"))


class WhatItExits(Permissions):
    def test_all_ready_exits_zero(self) -> None:
        machine = support.AMachine(**{"-c": support.ran(0, "read")})
        code, _out, _err, _machine = self.permissions("check", "files", machine=machine)
        self.assertEqual(OK, code)

    def test_anything_not_ready_exits_non_zero(self) -> None:
        machine = support.AMachine(**{"-c": support.ran(1, "PermissionError 1")})
        code, _out, _err, _machine = self.permissions("check", "files", machine=machine)
        self.assertEqual(FAILED, code)

    def test_a_probe_that_could_not_be_settled_also_fails(self) -> None:
        """A check that proved nothing has proved nothing, so it may not exit zero."""
        machine = support.AMachine(**{"-c": support.ran(0, "something else entirely")})
        code, _out, _err, _machine = self.permissions("check", "control/accessibility",
                                                      machine=machine)
        self.assertEqual(FAILED, code)

    def test_a_bare_check_leaves_out_what_is_not_needed(self) -> None:
        """`shell/admin` is reported, never gated — a check that always failed for want of
        passwordless sudo is a gate nobody could use."""
        machine = support.AMachine(**{"-c": support.ran(0, "read")})
        _code, out, _err, _machine = self.permissions("check", machine=machine)
        self.assertNotIn("admin", out)

    def test_everything_includes_it(self) -> None:
        machine = support.AMachine(**{"-c": support.ran(0, "read")})
        _code, out, _err, _machine = self.permissions("check", "--everything", machine=machine)
        self.assertIn("admin", out)


class WhatItKeeps(Permissions):
    """A report of what was true when last asked — never a cache anything decides on."""

    def kept(self):
        return config.read().get("permissions") or {}

    def test_nothing_checked_says_so_rather_than_looking_clean(self) -> None:
        code, _out, err, _machine = self.permissions()
        self.assertEqual(FAILED, code)
        self.assertIn("nothing has been checked", err)

    def test_what_was_found_is_written_down_with_its_lineage(self) -> None:
        machine = support.AMachine(**{"-c": support.ran(0, "read")})
        self.permissions("check", "files", machine=machine)
        kept = self.kept()
        self.assertEqual(lineage.GATEWAY, kept["lineage"]["how"])
        self.assertEqual(PYTHON, kept["lineage"]["named"])
        self.assertTrue(kept["checked_at"])
        self.assertEqual("ready", kept["found"]["files/desktop"])

    def test_a_partial_check_leaves_every_other_answer_alone(self) -> None:
        """Saying nothing about a probe this run never ran is honest; overwriting it is not."""
        self.permissions("check", "files", machine=support.AMachine(**{"-c": support.ran(0, "read")}))
        self.permissions("check", "control/accessibility",
                         machine=support.AMachine(**{"-c": support.ran(0, "no")}))
        found = self.kept()["found"]
        self.assertEqual("ready", found["files/desktop"], "a files answer was lost")
        self.assertEqual("blocked", found["control/accessibility"])

    def test_a_probe_never_run_is_absent_rather_than_unproven(self) -> None:
        """Never asked and asked-and-unanswerable are different answers."""
        self.permissions("check", "files", machine=support.AMachine(**{"-c": support.ran(0, "read")}))
        self.assertNotIn("control/accessibility", self.kept()["found"])

    def test_the_bare_verb_reads_it_back_without_running_anything(self) -> None:
        self.permissions("check", "files", machine=support.AMachine(**{"-c": support.ran(0, "read")}))
        _code, out, _err, machine = self.permissions()
        self.assertEqual([], machine.asked)
        self.assertIn("files/desktop", out)
        self.assertIn("not checked", out, "a probe nobody ran should say so")

    def test_a_stored_answer_from_another_lineage_is_marked(self) -> None:
        """A terminal's answer is not a gateway's, and a reader must not take one for the other."""
        self.permissions("check", "files", whose=A_TERMINAL,
                         machine=support.AMachine(**{"-c": support.ran(0, "read")}))
        _code, out, _err, _machine = self.permissions(whose=A_GATEWAY)
        self.assertIn("proved somewhere else", out)

    def test_it_is_valid_json_on_disk(self) -> None:
        self.permissions("check", "files", machine=support.AMachine(**{"-c": support.ran(0, "read")}))
        said = json.loads(config.where().read_text(encoding="utf-8"))
        self.assertIn("permissions", said)


class TheGuardItself(Permissions):
    """The suite's own safety net, asserted rather than intended."""

    def test_reaching_the_real_machine_raises_for_any_suite(self) -> None:
        """The seam is closed at import, for every case here and not only the ones using run_with.

        A case that calls `proving` directly never goes through `run_with`, and `proved()` resolves
        the real machine when nobody hands one in. Closing it once, module-wide, is what stops a
        forgotten argument reaching `osascript` on the developer's own Mac.
        """
        with self.assertRaises(AssertionError):
            proving.by_the_machine()

    def test_a_probe_with_no_machine_handed_in_fails_loudly(self) -> None:
        """The gap this guard exists for, driven end to end rather than asserted about."""
        with self.assertRaises(AssertionError):
            proving.proved(proving.every()[0], A_GATEWAY, self.home)


if __name__ == "__main__":
    unittest.main()
