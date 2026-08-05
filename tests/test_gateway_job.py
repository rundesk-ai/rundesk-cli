"""The launchd job — driven entirely against a stand-in, because the real one is not sandboxable.

**No case here may reach `launchctl`.** That is not a preference. `release.Asking` and
`update.Fetching` are replaced in their suites so that nothing leaves the machine, and a case that
forgot would fail loudly on somebody's network. This seam has no such safety net: the real
implementation would answer a case perfectly well, in the owner's own login session, booting out
jobs that keep real work running. So `Supervising` is a fake throughout, and `job.Launchd` is
replaced in `setUp` with something that raises if anything ever constructs it — a case that fell
through to the real supervisor goes red instead of running.

**And `~/Library/LaunchAgents` is checked at the end of the module**, name by name, size and mtime,
against how it was found. Every plist here is written into a scratch directory; this is the proof
rather than the intention.

Run directly: `python3 tests/test_gateway_job.py`
"""

import contextlib
import inspect
import os
import plistlib
import unittest
from pathlib import Path
from typing import List, Optional, Tuple
from unittest import mock

import support
from rundesk.gateways import job, standing
from rundesk.utils import programs

#: The owner's real login items. Read, listed and compared — never written, and never passed to
#: anything here as somewhere to write.
THEIRS = Path.home() / "Library" / "LaunchAgents"


def as_it_stands() -> Optional[List[Tuple[str, int, int]]]:
    """Every entry in the owner's `LaunchAgents`, with enough of each to see a rewrite.

    `None` when it cannot be listed at all, which is a machine that has never had one — told apart
    from an empty list so that a directory appearing during the run is not read as no change.
    """
    try:
        return sorted((one.name, one.stat().st_size, one.stat().st_mtime_ns)
                      for one in THEIRS.iterdir())
    except OSError:
        return None


#: How it was found, read once when this module is imported and compared at the end of it.
AS_FOUND = as_it_stands()

#: The real `job.Launchd`, held before `WithAJob` replaces the module's name for it. One class here
#: reads the argv it *would* run without running any of it; every other case still cannot reach the
#: real supervisor even by accident, because the name `job.Launchd` raises for the whole suite.
_LAUNCHD = job.Launchd


def tearDownModule() -> None:
    """Fail the whole module if anything in here touched the owner's login items."""
    now = as_it_stands()
    if now != AS_FOUND:
        raise AssertionError(
            f"{THEIRS} was changed by this suite — it held {AS_FOUND} and now holds {now}")


class NeverTheRealOne:
    """What `job.Launchd` is replaced with, so a case that reached for it cannot quietly run."""

    def __init__(self, *_args: object, **_kw: object) -> None:
        raise AssertionError(
            "a case reached the real launchctl — every case here drives a fake Supervising, "
            "because the real one would answer perfectly well against the owner's own jobs")


class ASupervisor:
    """A stand-in for launchd that records what it was asked and answers what the case wants.

    Every method answers `programs.Ran`, which is the whole of the seam: a `launchctl` that ran and
    said `113` and a `launchctl` that was not on the machine are different facts, and a stand-in
    that could not express both would let this module collapse them.
    """

    def __init__(self, **answers: programs.Ran) -> None:
        self.asked: List[Tuple[str, str]] = []
        self.answers = answers
        #: What the world looked like at each call, so a case can prove ordering against the disk
        #: rather than against the order the calls happen to be recorded in.
        self.saw: List[Tuple[str, bool, Optional[int]]] = []
        self.watching: Optional[Path] = None

    def allow(self, label: str) -> programs.Ran:
        return self._answer("enable", label)

    def take_back(self, label: str) -> programs.Ran:
        return self._answer("bootout", label)

    def place(self, plist: Path) -> programs.Ran:
        return self._answer("bootstrap", str(plist))

    def end(self, label: str) -> programs.Ran:
        return self._answer("kill", label)

    def kick(self, label: str) -> programs.Ran:
        return self._answer("kickstart", label)

    def asked_about(self, label: str) -> programs.Ran:
        return self._answer("print", label)

    def refusals(self) -> programs.Ran:
        return self._answer("print-disabled", "")

    def verbs(self) -> List[str]:
        return [verb for verb, _what in self.asked]

    def _answer(self, verb: str, what: str) -> programs.Ran:
        self.asked.append((verb, what))
        if self.watching is not None:
            mode = None
            with contextlib.suppress(OSError):
                mode = self.watching.stat().st_mode & 0o777
            self.saw.append((verb, self.watching.is_dir(), mode))
        return self.answers.get(verb, programs.Ran(0, "", "", None))


def ran(code: Optional[int] = 0, out: str = "", err: str = "",
        trouble: Optional[str] = None) -> programs.Ran:
    """One answer from a supervisor, in the shape `utils.programs` hands back."""
    return programs.Ran(code, out, err, trouble)


class WithAJob(support.Isolated):
    """A scratch install, a scratch agent directory, and a scratch place to keep plists."""

    def setUp(self) -> None:
        super().setUp()
        self.into = self.home / "LaunchAgents"
        self.into.mkdir(parents=True)
        self.at = self.home / "data" / "agents" / "cole"
        self.one = job.job("cole", self.at, self.home, self.into)
        # Structural, not a convention: nothing here may construct the real supervisor.
        patched = mock.patch.object(job, "Launchd", NeverTheRealOne)
        patched.start()
        self.addCleanup(patched.stop)

    def placed(self, **answers: programs.Ran) -> Tuple[ASupervisor, job.Placed]:
        by = ASupervisor(**answers)
        by.watching = standing.logs_at(self.at)
        return by, job.place(self.one, by)

    def document(self) -> dict:
        with open(job.plist_of(self.one), "rb") as reading:
            return plistlib.load(reading)


class TheNameLaunchdKnowsAGatewayBy(WithAJob):
    """The label — the one thing `RUNDESK_HOME` cannot isolate, so the root is written into it."""

    def test_the_label_carries_the_family_the_install_and_the_agent(self):
        self.assertEqual(f"ai.rundesk.{job.fingerprint(self.home)}.gateway.cole", self.one.label)

    def test_two_installs_derive_two_different_labels_for_one_agent_name(self):
        # The recorded incident: a second install's uninstall booted out the live install's job,
        # because a label is a name in the *person's* login domain and both installs had chosen the
        # same one. Nothing about RUNDESK_HOME reaches launchd.
        other = self.home.parent / f"{self.home.name}-second"
        other.mkdir()
        self.addCleanup(other.rmdir)
        self.assertNotEqual(job.label_for("cole", self.home), job.label_for("cole", other))

    def test_one_install_spelled_two_ways_is_one_label(self):
        # A root reached through `..` or a link is the same directory, and two labels for it would
        # be two jobs for one agent — both of which would start.
        crooked = self.home / "data" / ".." / ".."/ self.home.name
        self.assertEqual(job.label_for("cole", self.home), job.label_for("cole", crooked))

    def test_the_fingerprint_is_eight_hex_characters(self):
        said = job.fingerprint(self.home)
        self.assertEqual(job.FINGERPRINT, len(said))
        self.assertTrue(all(one in "0123456789abcdef" for one in said), said)

    def test_a_name_a_label_cannot_carry_is_refused(self):
        # launchd cannot persist the disable state of a label holding a character outside
        # `[A-Za-z0-9._-]`, so such an agent could never be enabled again after anything disabled it.
        for said in ("has a space", "quo\"te", "<angle>", "é", "", "sla/sh"):
            with self.subTest(name=said):
                with self.assertRaises(job.Refused):
                    job.label_for(said, self.home)

    def test_the_names_an_agent_may_ordinarily_have_are_taken(self):
        for said in ("cole", "cole-two", "cole_two", "cole.two", "Cole9"):
            with self.subTest(name=said):
                self.assertTrue(job.label_for(said, self.home).endswith(f".{said}"))

    def test_the_plist_is_named_for_the_label(self):
        # `man 5 launchd.plist` requires it, and a mismatch is a job nothing can find by either name.
        self.assertEqual(f"{self.one.label}.plist", job.plist_of(self.one).name)

    def test_where_plists_are_kept_defaults_to_the_owners_own_login_items(self):
        # Asserted rather than written to: a caller that passes nothing must get the real directory,
        # and a suite that reached it would be editing somebody's real login items.
        self.assertEqual(THEIRS, job.job("cole", self.at, self.home).into)


class ALabelThatIsNotThisInstalls(WithAJob):
    """Never a sweep, never a prefix match: the one full label this root derives, and nothing else."""

    def foreign(self) -> job.Job:
        return self.one._replace(label="ai.rundesk.deadbeef.gateway.cole")

    def test_placing_a_foreign_label_is_refused(self):
        with self.assertRaises(job.Refused) as refused:
            job.place(self.foreign(), ASupervisor())
        self.assertIn("deadbeef", str(refused.exception))

    def test_removing_a_foreign_label_is_refused(self):
        with self.assertRaises(job.Refused):
            job.remove(self.foreign(), ASupervisor())

    def test_reading_a_foreign_label_is_refused(self):
        with self.assertRaises(job.Refused):
            job.stands(self.foreign(), ASupervisor())

    def test_a_foreign_label_is_refused_before_the_supervisor_is_asked_anything(self):
        # The refusal has to come first. Asked and then refused, the damage is already done.
        by = ASupervisor()
        with self.assertRaises(job.Refused):
            job.remove(self.foreign(), by)
        self.assertEqual([], by.asked)

    def test_a_label_of_the_same_family_but_another_agent_is_still_foreign(self):
        with self.assertRaises(job.Refused):
            job.place(self.one._replace(label=job.label_for("dana", self.home)), ASupervisor())


class ThePlistThatIsWritten(WithAJob):
    """What launchd is actually handed — every key here is a finding from the research."""

    def setUp(self) -> None:
        super().setUp()
        self.by, self.landed = self.placed()
        self.said = self.document()

    def test_it_is_placed(self):
        self.assertEqual(job.PLACED, self.landed.how, self.landed.why)

    def test_the_program_is_a_named_shim_and_never_a_bare_interpreter(self):
        # The highest-value line on the research page. macOS names a Login Items row by the
        # executable's basename, so a bare interpreter shows the owner an anonymous `python` row —
        # several identical ones for several agents — and a denial there **removes the service from
        # launchd** with no command anywhere that puts it back.
        first = Path(self.said["ProgramArguments"][0])
        self.assertEqual(job.shim_of(self.one), first)
        self.assertNotIn(first.name, ("python", "python3", "sh", "bash", "env"))
        self.assertIn("cole", first.name)

    def test_the_shim_is_a_real_executable_file_of_its_own(self):
        shim = job.shim_of(self.one)
        self.assertTrue(shim.is_file())
        self.assertEqual(0o700, shim.stat().st_mode & 0o777)
        self.assertTrue(shim.read_text().startswith("#!"))
        self.assertIn("rundesk.gateways.host", shim.read_text())

    def test_keepalive_is_the_one_that_means_do_not_bring_a_clean_exit_back(self):
        self.assertEqual({"SuccessfulExit": False}, self.said["KeepAlive"])

    def test_runatload_is_not_written_because_keepalive_already_implies_it(self):
        # Writing it as well would suggest there is a way to place this job without starting it.
        # There is not — bootstrapping *is* starting — and a command surface must not imply one.
        self.assertNotIn("RunAtLoad", self.said)

    def test_the_throttle_is_meaningful_rather_than_the_documented_default(self):
        # Ten is what launchd already does. A gateway that dies inside ten seconds is broken
        # rather than busy, and a key that buys nothing is a key that reads as a decision.
        self.assertGreater(self.said["ThrottleInterval"], 10)

    def test_the_exit_timeout_is_written_down_because_two_things_depend_on_it(self):
        # It bounds SIGTERM→SIGKILL, and `bootout --wait` blocks for the whole of it.
        self.assertEqual(job.EXIT_TIMEOUT, self.said["ExitTimeOut"])
        self.assertGreater(self.said["ExitTimeOut"], standing.BEAT_SECONDS)

    def test_the_capture_paths_are_the_two_files_standing_already_names(self):
        out, err = standing.captured(self.at)
        self.assertEqual(str(out), self.said["StandardOutPath"])
        self.assertEqual(str(err), self.said["StandardErrorPath"])

    def test_the_environment_carries_the_root_the_home_and_a_whole_path(self):
        # A launchd job inherits `PATH=/usr/bin:/bin:/usr/sbin:/sbin` and nothing else — measured.
        # `~/.local/bin` is absent from that, which is exactly how the build this replaces lost a
        # provider that its owner's login shell found instantly.
        said = self.said["EnvironmentVariables"]
        self.assertEqual(str(self.home), said["RUNDESK_HOME"])
        self.assertEqual(str(Path.home()), said["HOME"])
        self.assertIn(str(Path.home() / ".local" / "bin"), said["PATH"].split(":"))
        for one in ("/usr/bin", "/bin", "/usr/sbin", "/sbin"):
            self.assertIn(one, said["PATH"].split(":"))

    def test_every_environment_value_is_a_string(self):
        # `man 5 launchd.plist`: *values other than strings will be ignored*. Silently — so an
        # accidental `int` is a variable the gateway simply never gets.
        for name, value in self.said["EnvironmentVariables"].items():
            with self.subTest(variable=name):
                self.assertIsInstance(value, str)

    def test_the_label_in_the_file_is_the_label_in_the_name(self):
        self.assertEqual(self.one.label, self.said["Label"])

    def test_the_plist_is_written_at_exactly_owner_read_write(self):
        # `O_CREAT`'s mode is masked by the umask, so this is asked for again once the descriptor
        # is open: a permissive umask otherwise lands `0664`, which launchd refuses with 122.
        self.assertEqual(0o600, job.plist_of(self.one).stat().st_mode & 0o777)

    def test_a_permissive_umask_still_lands_a_private_plist(self):
        was = os.umask(0o000)
        self.addCleanup(os.umask, was)
        job.plist_of(self.one).unlink()
        self.placed()
        self.assertEqual(0o600, job.plist_of(self.one).stat().st_mode & 0o777)

    def test_a_plist_already_there_under_another_mode_is_tightened_rather_than_left(self):
        # The case a umask cannot show, and the one that actually happens: `O_TRUNC` on a file that
        # is already there replaces its contents and **not** its mode. A plist left `0644` by an
        # older rundesk, or `0666` by something else entirely, would keep that mode for ever — and
        # launchd refuses a plist that allows group or world writes with error 122.
        plist = job.plist_of(self.one)
        plist.chmod(0o666)
        self.placed()
        self.assertEqual(0o600, plist.stat().st_mode & 0o777)

    def test_a_shim_already_there_under_another_mode_is_tightened_too(self):
        shim = job.shim_of(self.one)
        shim.chmod(0o777)
        self.placed()
        self.assertEqual(0o700, shim.stat().st_mode & 0o777)

    def test_the_plist_is_a_real_file_and_never_written_through_a_symlink(self):
        # Whether launchd follows a symlinked plist could not be established read-only, and there is
        # no upside to finding out: agent plists must be owned by the user loading them.
        elsewhere = self.home / "somebody-elses.plist"
        elsewhere.write_text("not ours")
        plist = job.plist_of(self.one)
        plist.unlink()
        plist.symlink_to(elsewhere)
        with self.assertRaises(OSError):
            self.placed()
        self.assertEqual("not ours", elsewhere.read_text())


class TheOrderThingsHappenIn(WithAJob):
    """Enable, then bootout, then bootstrap — and the logs directory before any of them."""

    def test_the_label_is_enabled_before_it_is_bootstrapped(self):
        # The override store is keyed by label, persists across reboots and **outlives the plist**:
        # the machine this was researched on carries a record for a label whose plist no longer
        # exists anywhere. There is no verb that deletes an entry, so enabling unconditionally is
        # the only defence against an override nobody remembers.
        by, _landed = self.placed()
        self.assertLess(by.verbs().index("enable"), by.verbs().index("bootstrap"))

    def test_every_plist_write_is_followed_by_bootout_and_then_bootstrap(self):
        # launchd holds an imported copy and nothing watches the file, and re-bootstrapping a label
        # from a different path **keeps the existing definition without failing**. A build that
        # rewrote a plist and bootstrapped over it would run the old program for ever.
        by, _landed = self.placed()
        self.assertEqual(["enable", "bootout", "bootstrap"], by.verbs())

    def test_placing_it_again_boots_it_out_again_rather_than_bootstrapping_over_it(self):
        self.placed()
        by, _landed = self.placed()
        self.assertEqual(["enable", "bootout", "bootstrap"], by.verbs())

    def test_the_logs_directory_is_there_and_private_before_the_job_is_placed(self):
        # launchd does create the parent of a capture path, but that is undocumented — and a spawn
        # that cannot open `StandardErrorPath` fails with the reason going to the unified log only,
        # which is how a correctly-installed gateway becomes a 113.
        by, _landed = self.placed()
        for verb, there, mode in by.saw:
            with self.subTest(before=verb):
                self.assertTrue(there, f"logs/ was not there when {verb} ran")
                self.assertEqual(0o700, mode)

    def test_the_logs_directory_is_private_under_a_permissive_umask_too(self):
        # `mkdir`'s mode is masked by the umask, so it is set afterwards rather than trusted.
        was = os.umask(0o000)
        self.addCleanup(os.umask, was)
        self.placed()
        self.assertEqual(0o700, standing.logs_at(self.at).stat().st_mode & 0o777)


class WhatABootstrapAnswered(WithAJob):
    """Each exit code, in the words the research's failure table uses."""

    def test_zero_is_placed(self):
        _by, landed = self.placed(bootstrap=ran(0))
        self.assertEqual(job.PLACED, landed.how)
        self.assertEqual("", landed.why)

    def test_already_bootstrapped_is_placed_and_says_it_may_be_the_old_definition(self):
        for code in job.ALREADY_THERE:
            with self.subTest(code=code):
                _by, landed = self.placed(bootstrap=ran(code))
                self.assertEqual(job.PLACED, landed.how)
                self.assertIn("already loaded", landed.why)

    def test_launchds_catch_all_says_go_and_read_the_log(self):
        # `5` is launchd's I/O error and it says nothing at all. The only account of it is the
        # unified log, so the answer is the command that reads it rather than a guess.
        _by, landed = self.placed(bootstrap=ran(job.GO_AND_READ_THE_LOG))
        self.assertEqual(job.CANNOT_TELL, landed.how)
        self.assertIn("log show", landed.why)

    def test_no_login_session_is_never_reported_as_a_failure_to_place(self):
        # Over SSH into a machine nobody has logged into at the desktop, this is every job.
        for code in job.NO_GUI_SESSION:
            with self.subTest(code=code):
                _by, landed = self.placed(bootstrap=ran(code))
                self.assertEqual(job.CANNOT_TELL, landed.how)
                self.assertIn("login session", landed.why)

    def test_a_disabled_label_is_not_placed_and_says_something_is_disabling_it(self):
        _by, landed = self.placed(bootstrap=ran(job.IS_DISABLED))
        self.assertEqual(job.NOT_PLACED, landed.how)
        self.assertIn("disabl", landed.why)

    def test_anything_else_is_not_placed_and_carries_the_number(self):
        _by, landed = self.placed(bootstrap=ran(110, err="Bootstrap failed: 110: bad plist"))
        self.assertEqual(job.NOT_PLACED, landed.how)
        self.assertIn("110", landed.why)

    def test_a_launchctl_that_was_never_on_the_machine_is_not_a_refusal(self):
        # The distinction `utils.programs` exists to keep: it ran and disagreed, or it never ran.
        _by, landed = self.placed(bootstrap=ran(None, trouble=programs.DID_NOT_START))
        self.assertEqual(job.CANNOT_TELL, landed.how)
        self.assertIn(programs.DID_NOT_START, landed.why)


class WhatABootoutAnswered(WithAJob):
    """Nothing is bootstrapped over a job that may still be loaded."""

    def test_a_label_that_was_never_loaded_is_the_state_that_was_asked_for(self):
        for code in job.ALREADY_GONE:
            with self.subTest(code=code):
                by, landed = self.placed(bootout=ran(code))
                self.assertEqual(job.PLACED, landed.how, landed.why)
                self.assertIn("bootstrap", by.verbs())

    def test_a_bootout_that_answered_anything_else_stops_the_bootstrap(self):
        # `bootout` reporting anything but gone may have left the old definition loaded, and
        # bootstrapping onto that keeps the old one **and does not fail**.
        by, landed = self.placed(bootout=ran(9))
        self.assertEqual(job.CANNOT_TELL, landed.how)
        self.assertNotIn("bootstrap", by.verbs())

    def test_a_bootout_that_would_not_finish_stops_the_bootstrap(self):
        # `launchctl help bootout` warns that `--wait` may block indefinitely, so this really
        # happens: a gateway ignoring SIGTERM holds it for the whole ExitTimeOut.
        by, landed = self.placed(bootout=ran(None, trouble=programs.WOULD_NOT_FINISH))
        self.assertEqual(job.CANNOT_TELL, landed.how)
        self.assertNotIn("bootstrap", by.verbs())


class TakingAJobAway(WithAJob):
    """`remove` — and the override record it deliberately leaves behind enabled."""

    def test_it_takes_the_job_the_plist_and_the_shim(self):
        self.placed()
        by = ASupervisor()
        self.assertEqual("", job.remove(self.one, by))
        self.assertFalse(job.plist_of(self.one).exists())
        self.assertFalse(job.shim_of(self.one).exists())
        self.assertIn("bootout", by.verbs())

    def test_a_job_that_was_never_there_is_removed_without_complaint(self):
        for code in job.ALREADY_GONE:
            with self.subTest(code=code):
                self.assertEqual("", job.remove(self.one, ASupervisor(bootout=ran(code))))

    def test_it_leaves_the_override_enabled_rather_than_disabled(self):
        # There is no verb that deletes a record from the override store, so what an uninstall can
        # do is make sure the entry it leaves is inert. A `disabled` record left behind is how the
        # *next* install inherits a decision nobody remembers making — live on the researched
        # machine, for an install that no longer exists.
        by = ASupervisor()
        job.remove(self.one, by)
        self.assertIn("enable", by.verbs())

    def test_an_enable_that_did_not_work_is_said_rather_than_swallowed(self):
        # The answer to `enable` used to be thrown away here, and `place` is why that looked safe:
        # there, everything after it goes back to the same launchctl and would report a disabled
        # label itself. Nothing follows it here — the files come off the disk and the function
        # returns — so an enable that quietly did not happen leaves exactly the poisoned record this
        # verb exists to avoid, left by the uninstall itself, while the caller is told it is gone.
        self.placed()
        why = job.remove(self.one, ASupervisor(enable=ran(5)))
        self.assertIn("inert", why)
        self.assertIn(self.one.label, why)
        self.assertIn("launchctl enable", why, "it did not say how to finish the job by hand")

    def test_the_files_still_go_when_the_record_could_not_be_made_inert(self):
        # The job really was taken back and the files really are ours to remove. Refusing to finish
        # would leave a plist behind for a job that no longer exists, which is worse than a record
        # somebody has one command to clear.
        self.placed()
        job.remove(self.one, ASupervisor(enable=ran(5)))
        self.assertFalse(job.plist_of(self.one).exists())
        self.assertFalse(job.shim_of(self.one).exists())

    def test_an_enable_the_supervisor_could_not_even_be_asked_for_is_said_too(self):
        # `trouble` and a non-zero code are different facts — launchctl never ran, versus launchctl
        # ran and disagreed — and both leave the record in the same unknown state.
        self.placed()
        why = job.remove(self.one, ASupervisor(enable=programs.Ran(None, "", "", "did not start")))
        self.assertIn("inert", why)
        self.assertIn("did not start", why)

    def test_a_bootout_that_did_not_clearly_work_does_not_report_a_removal(self):
        # Never report a success that was not earned: the files would go and the job would stay.
        self.placed()
        why = job.remove(self.one, ASupervisor(bootout=ran(5)))
        self.assertIn("5", why)
        self.assertTrue(job.plist_of(self.one).exists(), "the plist went while the job stayed")

    def test_the_files_are_only_taken_after_the_job_is(self):
        self.placed()
        job.remove(self.one, ASupervisor(bootout=ran(None, trouble=programs.WOULD_NOT_FINISH)))
        self.assertTrue(job.plist_of(self.one).exists())


class WhereAJobStands(WithAJob):
    """Four sources, because `print` answering 113 is ambiguous at least four ways."""

    def stands(self, **answers: programs.Ran) -> job.Stands:
        return job.stands(self.one, ASupervisor(**answers))

    def test_no_login_session_is_never_reported_as_not_running(self):
        # Over SSH, every gateway on the machine would otherwise look absent.
        for code in job.NO_GUI_SESSION:
            with self.subTest(code=code):
                how = self.stands(print=ran(code))
                self.assertEqual(job.CANNOT_TELL, how.how)
                self.assertIn("login session", how.why)

    def test_a_label_launchd_knows_and_no_plist_anywhere_is_the_only_safe_no(self):
        how = self.stands(print=ran(job.NOT_KNOWN))
        self.assertEqual(job.NOT_PLACED, how.how)
        self.assertFalse(how.plist)

    def test_a_plist_on_disk_that_launchd_has_no_record_of_is_cannot_tell(self):
        # Three plists had sat on the researched machine for two weeks doing nothing: writing the
        # file is not installing the job. It is also what a spawn failure leaves behind, and what a
        # Login Items denial leaves behind, and the three are byte-identical from here.
        self.placed()
        how = self.stands(print=ran(job.NOT_KNOWN))
        self.assertEqual(job.CANNOT_TELL, how.how)
        self.assertTrue(how.plist)
        self.assertIn("log show", how.why)

    def test_a_label_launchd_answers_for_is_placed(self):
        how = self.stands(print=ran(0, out="\tstate = running\n\tpid = 4242\n"))
        self.assertEqual(job.PLACED, how.how)

    def test_a_disabled_job_prints_as_a_healthy_one_and_is_said_out_loud(self):
        # `disabled` is not among the property words launchd renders at all, so a job that will
        # never start prints exactly like one that is fine. It has to be asked separately, always.
        listed = f'\tdisabled services = {{\n\t\t"{self.one.label}" => disabled\n\t}}\n'
        how = self.stands(print=ran(0), **{"print-disabled": ran(0, out=listed)})
        self.assertTrue(how.disabled)
        self.assertIn("never start", how.why)

    def test_absence_from_the_override_listing_means_enabled(self):
        listed = '\tdisabled services = {\n\t\t"com.apple.Siri.agent" => disabled\n\t}\n'
        how = self.stands(print=ran(0), **{"print-disabled": ran(0, out=listed)})
        self.assertFalse(how.disabled)

    def test_an_override_store_that_could_not_be_read_is_not_a_job_that_is_enabled(self):
        how = self.stands(print=ran(0), **{"print-disabled": ran(1, err="nope")})
        self.assertIsNone(how.disabled, "an unreadable store was reported as enabled")

    def test_launchd_running_a_different_plist_than_the_one_written_is_said_out_loud(self):
        # The finding that matters most: re-bootstrapping a label from a different path keeps the
        # existing definition and does **not** fail, so the only way this is ever visible is by
        # comparing what `print` says it loaded against what was written.
        self.placed()
        how = self.stands(print=ran(0, out="\tpath = /somewhere/else.plist\n"))
        self.assertEqual(job.PLACED, how.how)
        self.assertIn("/somewhere/else.plist", how.why)

    def test_the_path_it_loaded_matching_what_was_written_says_nothing(self):
        self.placed()
        how = self.stands(print=ran(0, out=f"\tpath = {job.plist_of(self.one)}\n"))
        self.assertEqual("", how.why)

    def test_a_supervisor_that_could_not_be_asked_at_all_is_cannot_tell(self):
        how = self.stands(print=ran(None, trouble=programs.DID_NOT_START))
        self.assertEqual(job.CANNOT_TELL, how.how)

    def test_it_asks_all_four_places(self):
        by = ASupervisor()
        job.stands(self.one, by)
        self.assertIn("print", by.verbs())
        self.assertIn("print-disabled", by.verbs())


class WhetherTheOwnerStillAllowsIt(WithAJob):
    """Background Task Management — the one lockout with no command, so worth detecting and no more."""

    def store(self, rows: List[Tuple[str, int]]) -> Path:
        """A `BackgroundItems` archive of the shape the real one has, for the rows given."""
        objects: List[object] = ["$null"]
        for identifier, disposition in rows:
            objects.append({"disposition": disposition, "identifier": plistlib.UID(len(objects) + 1)})
            objects.append(identifier)
        where = self.home / "BackgroundItems-v16.btm"
        with open(where, "wb") as writing:
            plistlib.dump({"$objects": objects}, writing, fmt=plistlib.FMT_BINARY)
        return where

    def test_an_item_the_owner_has_switched_on_reads_as_allowed(self):
        where = self.store([(f"8.{self.one.label}", 9)])
        self.assertTrue(job.allowed_by_the_owner(self.one.label, where))

    def test_an_item_the_owner_has_switched_off_reads_as_not_allowed(self):
        where = self.store([(f"8.{self.one.label}", 8)])
        self.assertFalse(job.allowed_by_the_owner(self.one.label, where))

    def test_a_label_that_is_not_in_the_store_cannot_be_told_either_way(self):
        where = self.store([("8.com.apple.something", 9)])
        self.assertIsNone(job.allowed_by_the_owner(self.one.label, where))

    def test_a_store_that_is_not_there_cannot_be_told_either_way(self):
        self.assertIsNone(job.allowed_by_the_owner(self.one.label, self.home / "nothing.btm"))

    def test_a_store_of_a_shape_nobody_published_cannot_be_told_either_way(self):
        # The format is undocumented, so every shape it could change into has to answer "cannot
        # tell" rather than a guess. Telling somebody their gateway is switched off on the strength
        # of a bit nobody published is worse than saying nothing.
        for said in (b"not a plist at all", b"", b"\x00\x01\x02"):
            with self.subTest(store=said):
                where = self.home / "broken.btm"
                where.write_bytes(said)
                self.assertIsNone(job.allowed_by_the_owner(self.one.label, where))

    def test_an_archive_with_the_right_keys_and_the_wrong_shapes_cannot_be_told_either_way(self):
        where = self.home / "odd.btm"
        with open(where, "wb") as writing:
            plistlib.dump({"$objects": [{"disposition": "nine", "identifier": 4}]}, writing,
                          fmt=plistlib.FMT_BINARY)
        self.assertIsNone(job.allowed_by_the_owner(self.one.label, where))

    def test_a_denial_names_the_one_thing_the_owner_can_actually_do(self):
        # There is no `launchctl` command and no user-level command of any kind that undoes this.
        self.placed()
        where = self.store([(f"8.{self.one.label}", 8)])
        with mock.patch.object(job, "BTM", where):
            how = job.stands(self.one, ASupervisor(print=ran(job.NOT_KNOWN)))
        self.assertEqual(job.CANNOT_TELL, how.how)
        self.assertFalse(how.allowed)
        self.assertIn("Login Items", how.why)


class WhatTheRealSupervisorWouldRun(WithAJob):
    """The argv the real one builds and the ceiling it gives each call. **Read, never run.**

    `_ran` is replaced, so the arguments are captured and no process starts — nothing in this suite
    executes `launchctl`. What is pinned here is the two things a stand-in can never show: the exact
    verb, and how long that verb is allowed to take before it is called wedged. The second of those
    was one number for every call, and it was a defect rather than a simplification.
    """

    def asked(self, call: str, label: str = "some.label") -> Tuple[List[str], float]:
        """What `Launchd.<call>` would run, and with what ceiling. Nothing is executed."""
        seen: List[Tuple[List[str], float]] = []

        def watched(_self, verb: List[str], waiting: float) -> programs.Ran:
            # Answered `0`, because `allow` reads what it got back and falls to the user domain on
            # `125`. A recorder that answered nothing would make this case about that instead.
            seen.append((verb, waiting))
            return ran(0)

        real = _LAUNCHD(uid=501)
        with mock.patch.object(_LAUNCHD, "_ran", watched):
            getattr(real, call)(label)
        return seen[0]

    def test_a_kill_is_the_signal_name_the_manual_page_documents(self):
        # `man launchctl`: *kill signal-name | signal-number service-target*, and `SIGKILL` is that
        # page's own example. `-KILL` is `/bin/kill`'s shorthand and is not what this verb takes.
        verb, _waiting = self.asked("end")
        self.assertEqual(["kill", "SIGKILL", "gui/501/some.label"], verb)

    def test_a_kill_is_a_request_rather_than_a_wait_and_gets_the_ordinary_ceiling(self):
        # It signals and does not unload: launchctl returns once launchd has sent the signal, and
        # the death is asynchronous. What waits for the process to really be gone is the
        # `bootout --wait` behind it, which is why that one has a ceiling of its own.
        _verb, waiting = self.asked("end")
        self.assertEqual(job.ASK_SECONDS, waiting)

    def test_taking_a_job_back_is_given_the_whole_window_it_waits_out(self):
        # `bootout --wait` sends `SIGTERM` and waits for the process to be gone, up to the job's own
        # `ExitTimeOut` — and `launchctl help bootout` warns in as many words that it may block
        # indefinitely, which is why there is a ceiling on it at all.
        verb, waiting = self.asked("take_back")
        self.assertEqual(["bootout", "--wait", "gui/501/some.label"], verb)
        self.assertEqual(job.TAKE_BACK_SECONDS, waiting)
        self.assertGreater(waiting, job.EXIT_TIMEOUT)

    def test_a_kick_is_given_the_throttle_it_blocks_for_and_not_the_ordinary_ceiling(self):
        # **The measured defect, 2026-08-05.** `kickstart -k` does not get past a
        # `ThrottleInterval`; it waits the whole of one out — 30 s against a throttle of 30 — with
        # the caller blocked for every second. Under `ASK_SECONDS` that reported a supervisor which
        # could not be asked, on a machine where launchd was doing exactly what it documents.
        verb, waiting = self.asked("kick")
        self.assertEqual(["kickstart", "-kp", "gui/501/some.label"], verb)
        self.assertEqual(job.KICK_SECONDS, waiting)
        self.assertGreater(waiting, job.THROTTLE + job.EXIT_TIMEOUT)

    def test_the_calls_that_wait_for_nothing_are_not_given_the_throttle_as_well(self):
        # A ceiling raised everywhere is a command that hangs for a minute on a launchd that is
        # merely wedged. These are requests launchd accepts, or reads it answers out of what it
        # holds — and a fresh `bootstrap` waits for no throttle at all, measured.
        for call in ("allow", "place", "asked_about"):
            with self.subTest(call=call):
                _verb, waiting = self.asked(call)
                self.assertEqual(job.ASK_SECONDS, waiting)
        self.assertLess(job.ASK_SECONDS, job.THROTTLE)


class TheSeamItself(WithAJob):
    """That the supervisor is passed in, and resolved in a body rather than bound in a signature."""

    def test_nothing_here_binds_a_supervisor_in_a_signature(self):
        # A default bound in a signature is decided once, when this module is defined, and nothing
        # can reach past it — which for this seam means a suite against the owner's real jobs.
        for named in (job.place, job.remove, job.stands):
            with self.subTest(function=named.__name__):
                said = inspect.signature(named).parameters["supervising"]
                self.assertIsNone(said.default)

    def test_the_real_supervisor_is_never_reached_by_anything_here(self):
        # `setUp` replaced it with something that raises. This is that guard, proven.
        with self.assertRaises(AssertionError):
            job.Launchd()

    def test_the_real_supervisor_asks_launchctl_by_absolute_path(self):
        # Read rather than run. Nothing in this suite executes launchctl, and the one thing worth
        # asserting about the real implementation is that it does not depend on a PATH.
        self.assertTrue(Path(job.LAUNCHCTL).is_absolute())

    def test_a_stand_in_inherits_nothing_at_all_and_is_still_accepted(self):
        # A `Protocol` rather than a base class, so a stand-in has nothing in common with the real
        # supervisor but the shape — and nothing in `job` can reach a method the seam does not name.
        self.assertEqual((object,), ASupervisor.__bases__)
        self.assertEqual(job.PLACED, job.place(self.one, ASupervisor()).how)


class TheOwnersLoginItems(unittest.TestCase):
    """Proof, in the middle of the run as well as at the end of it."""

    def test_nothing_in_this_suite_has_changed_them(self):
        self.assertEqual(AS_FOUND, as_it_stands(), f"{THEIRS} was changed by this suite")

    def test_every_plist_this_suite_wrote_landed_somewhere_that_is_not_theirs(self):
        # The whole reason `into` is an argument. Stated as a case so that a default quietly
        # resolving to the real directory goes red here rather than on somebody's machine.
        written = [one for one in (as_it_stands() or []) if job.FAMILY in one[0]]
        self.assertEqual([], written, f"a rundesk plist was written into {THEIRS}")


class TheCommandsLaunchdIsActuallyGiven(support.Isolated):
    """`Launchd` itself — the seven one-liners every other case in this file replaces.

    **Everything else here drives a fake, and it has to.** The real supervisor would answer a case
    perfectly well, in the owner's own login session, booting out jobs that keep real work running.
    But that leaves the argv these methods *build* proven by nothing: a fake records that `bootout`
    was asked for, never that it was asked for as `["bootout", "--wait", "gui/501/<label>"]`. A
    missing `--wait` turns a synchronous take-back into the asynchronous one whose race cost this
    project a documented incident; `-pk` for `-kp` is a flag that does not exist; `kill -KILL` is
    `/bin/kill`'s spelling and not `launchctl`'s. Every one of those would pass every other case in
    this file and surface only against a real machine.

    So this class mocks one layer lower — `utils.programs.run`, the seam `job` already goes through
    — and asserts the exact list. Nothing here reaches `launchctl` either.
    """

    def setUp(self) -> None:
        super().setUp()
        self.by = job.Launchd(uid=501)
        self.asked: List[List[str]] = []
        self.answer = ran(0)
        patched = mock.patch.object(
            programs, "run",
            side_effect=lambda argv, waiting, **_kw: (self.asked.append(list(argv)), self.answer)[1])
        patched.start()
        self.addCleanup(patched.stop)

    def test_the_domain_and_the_target_are_shaped_the_way_launchctl_wants_them(self):
        self.assertEqual("gui/501", self.by.domain)
        self.assertEqual("gui/501/ai.rundesk.abcd1234.gateway.cole",
                         self.by.target("ai.rundesk.abcd1234.gateway.cole"))

    def test_every_verb_builds_exactly_the_command_it_documents(self):
        plist = self.home / "one.plist"
        for asked, wanted in (
                (lambda: self.by.allow("L"), [job.LAUNCHCTL, "enable", "gui/501/L"]),
                (lambda: self.by.take_back("L"), [job.LAUNCHCTL, "bootout", "--wait", "gui/501/L"]),
                (lambda: self.by.place(plist), [job.LAUNCHCTL, "bootstrap", "gui/501", str(plist)]),
                (lambda: self.by.end("L"), [job.LAUNCHCTL, "kill", "SIGKILL", "gui/501/L"]),
                (lambda: self.by.kick("L"), [job.LAUNCHCTL, "kickstart", "-kp", "gui/501/L"]),
                (lambda: self.by.asked_about("L"), [job.LAUNCHCTL, "print", "gui/501/L"]),
                (lambda: self.by.refusals(), [job.LAUNCHCTL, "print-disabled", "gui/501"])):
            with self.subTest(wanted=wanted[1]):
                self.asked.clear()
                asked()
                self.assertEqual([wanted], self.asked)

    def test_a_kill_is_spelled_the_way_launchctl_spells_it_and_not_the_way_kill_does(self):
        # `launchctl kill` takes a signal NAME or number; `-KILL` is /bin/kill's shorthand and is
        # read here as an option that does not exist. Its own man page's example is `SIGKILL`.
        self.by.end("L")
        self.assertIn("SIGKILL", self.asked[0])
        self.assertNotIn("-KILL", self.asked[0])

    def test_taking_a_job_back_always_waits(self):
        # Without --wait, bootout returns while the label is still registered and the process still
        # running — measured on a real gateway. A build that read rc 0 as "it is gone" and
        # bootstrapped next met launchd's I/O error and ended with no job at all.
        self.by.take_back("L")
        self.assertIn("--wait", self.asked[0])

    def test_enabling_falls_back_to_the_user_domain_when_the_login_one_refuses_the_verb(self):
        # enable and disable may only target the system domain or the user and user-login domains,
        # so a 125 here is the wrong domain for the verb rather than a machine with nobody logged
        # in — and the same label is reachable under `user/<uid>`.
        answers = [ran(125), ran(0)]
        with mock.patch.object(programs, "run",
                               side_effect=lambda argv, waiting, **_kw:
                               (self.asked.append(list(argv)), answers.pop(0))[1]):
            self.by.allow("L")
        self.assertEqual(["gui/501/L", "user/501/L"], [one[-1] for one in self.asked])

    def test_it_asks_for_the_supervisor_by_absolute_path(self):
        # A launchd job's PATH is /usr/bin:/bin:/usr/sbin:/sbin and nothing else, and this runs from
        # commands a person types as well. Neither should depend on where launchctl is found.
        self.by.asked_about("L")
        self.assertTrue(self.asked[0][0].startswith("/"), self.asked[0][0])

    def test_nothing_it_runs_is_ever_handed_to_a_shell(self):
        # A label carries an agent's name, and a name is the owner's to choose. A string through a
        # shell is a name that can be word-split or expanded.
        self.by.asked_about("L")
        self.assertIsInstance(self.asked[0], list)


if __name__ == "__main__":
    unittest.main()
